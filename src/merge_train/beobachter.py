"""merge-train --beobachten, Seite des Servers: merkt, wann sich im Repo etwas getan hat, und sagt der Seite „veraltet“.

Der Beobachter (inotify über ctypes, ohne Abhängigkeit; ohne inotify alle paar Sekunden „vielleicht“) meldet nur „seit
Zähler n hat sich etwas bewegt“. Ob sich der Stand wirklich geändert hat, prüft erst git, und das nur nach einer Meldung.
Dazu: welche Zeilen zwischen zwei Ständen neu sind (Rahmen um das Neue nach dem Neuladen).
"""
import os, re, subprocess, sys, threading, time
from .einstellungen import KONF, SPERRE
from .waggon import Fehler, von_bis
from .git import bis_sha, git, projekt_wurzel
from .akte import akte_lesen, struktur_laden

class Beobachter:
    MASKE = 0x8 | 0x40 | 0x80 | 0x100 | 0x200 | 0x400 | 0x800  # CLOSE_WRITE MOVED_FROM/TO CREATE DELETE DELETE/MOVE_SELF
    ORDNER_BIT, UEBERLAUF = 0x40000000, 0x4000
    RUECKFALL_S = 5

    def __init__(self, wurzel):
        self.wurzel, self.zaehler, self.wd, self.fd = wurzel, 1, {}, None
        try:
            self._inotify()
        except OSError as e:
            print(f"merge-train: kein inotify ({e}) – prüfe alle {self.RUECKFALL_S} s", file=sys.stderr)
            if self.fd is not None:
                os.close(self.fd); self.fd = None
            threading.Thread(target=self._rueckfall, daemon=True).start()

    def _rueckfall(self):
        while True:
            time.sleep(self.RUECKFALL_S); self.zaehler += 1

    def _inotify(self):
        import ctypes
        self.libc = ctypes.CDLL(None, use_errno=True)
        fd = self.libc.inotify_init1(0o2000000)  # IN_CLOEXEC
        if fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1")
        self.fd = fd
        self.ignoriert = {os.path.join(self.wurzel, p.rstrip("/")) for p in
                          (git(self.wurzel, "ls-files", "-z", "-o", "-i", "--exclude-standard", "--directory",
                               check=False) or "").split("\0") if p.endswith("/")}
        self._baum(self.wurzel)
        gitdir = git(self.wurzel, "rev-parse", "--absolute-git-dir").strip()
        gemeinsam = git(self.wurzel, "rev-parse", "--path-format=absolute", "--git-common-dir").strip()
        for d in {gitdir, gemeinsam}:  # HEAD, index, packed-refs (werden per rename geschrieben)
            self._dazu(d)
        self._baum(os.path.join(gemeinsam, "refs", "heads"), git_intern=True)
        threading.Thread(target=self._lesen, daemon=True).start()

    def _dazu(self, pfad):
        import ctypes
        wd = self.libc.inotify_add_watch(self.fd, os.fsencode(pfad), self.MASKE)
        if wd < 0:
            fehler = ctypes.get_errno()
            if fehler == 28:  # ENOSPC: fs.inotify.max_user_watches erreicht
                raise OSError(fehler, "zu viele Ordner für inotify (fs.inotify.max_user_watches)")
            return  # Ordner schon wieder weg o. ä.
        self.wd[wd] = pfad

    def _baum(self, start, git_intern=False):
        for d, unter, _ in os.walk(start):
            if not git_intern:
                unter[:] = [u for u in unter if u != ".git" and os.path.join(d, u) not in self.ignoriert]
            self._dazu(d)

    def _lesen(self):
        import struct
        while True:
            try:
                puffer = os.read(self.fd, 65536)
            except OSError:
                return
            self.zaehler += 1
            i = 0
            while i + 16 <= len(puffer):
                wd, maske, _, laenge = struct.unpack_from("iIII", puffer, i)
                name = puffer[i + 16:i + 16 + laenge].rstrip(b"\0").decode(errors="replace")
                i += 16 + laenge
                if maske & self.UEBERLAUF:
                    continue
                if maske & self.ORDNER_BIT and maske & (0x100 | 0x80) and wd in self.wd:  # neuer Ordner: mit beobachten
                    pfad = os.path.join(self.wd[wd], name)
                    intern = not pfad.startswith(self.wurzel.rstrip("/") + "/") or "/.git/" in pfad + "/"
                    if intern or git(self.wurzel, "check-ignore", "-q", pfad, check=False) is None:
                        try:
                            self._baum(pfad, git_intern=intern)
                        except OSError:
                            pass
            time.sleep(0.2)  # Schwall beim Speichern/Bauen zusammenfassen


_BEOBACHTER, _GEPRUEFT = {}, {}  # wurzel → Beobachter; wurzel → (Zähler, (bis-sha, von-sha)) der letzten git-Prüfung


def beobachter(wurzel):
    with SPERRE:
        if wurzel not in _BEOBACHTER:
            _BEOBACHTER[wurzel] = Beobachter(wurzel)
        return _BEOBACHTER[wurzel]


def veraltet(waggon, sha):
    """Ist die Seite mit Stand sha überholt (Arbeitsverzeichnis, HEAD oder von bewegt)? git nur nach einer Meldung des
    Beobachters, sonst die letzte Antwort. Nur bei --beobachten und lokalen Projekten."""
    if not (KONF["beobachten"] and waggon.lokal and sha):
        return False
    try:
        wurzel = projekt_wurzel(waggon.lokal)
    except Fehler:
        return False
    b = beobachter(wurzel)
    alt = _GEPRUEFT.get(wurzel)
    if not alt or alt[0] != b.zaehler:
        n = b.zaehler
        try:
            jetzt = (bis_sha(wurzel), git(wurzel, "rev-parse", von_bis(waggon.lokal)[0]).strip())
        except subprocess.CalledProcessError:
            return False
        alt = _GEPRUEFT[wurzel] = (n, jetzt)
    refs = (struktur_laden(akte_lesen(waggon)) or {}).get("refs") or {}
    start = refs.get("start_sha")
    return alt[1][0] != sha or bool(start and refs.get("head_sha") == sha and alt[1][1] != start)


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.M)


def neue_zeilen(waggon, alt, neu):
    """Zeilen, die zwischen den Ständen alt und neu dazugekommen oder geändert sind: {pfad: [[von, bis], …]} (Zeilen im
    Stand neu). Reine Löschungen markieren die Zeile danach. Unbekannter Stand alt (z. B. aufgeräumt): {}."""
    if not (waggon.lokal and re.fullmatch(r"[0-9a-f]{7,40}", alt or "") and re.fullmatch(r"[0-9a-f]{7,40}", neu or "")):
        return {}
    try:
        wurzel = projekt_wurzel(waggon.lokal)
    except Fehler:
        return {}
    roh = git(wurzel, "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "-M", "-U0", alt, neu,
              check=False) or ""
    out, pfad = {}, None
    for z in roh.splitlines():
        if z.startswith("+++ "):
            pfad = z[6:] if z.startswith("+++ b/") else None
        elif pfad and z.startswith("@@"):
            m = _HUNK.match(z)
            if m:
                von, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
                out.setdefault(pfad, []).append([max(von, 1), von + n - 1] if n else [von + 1, von + 1])
    return out
