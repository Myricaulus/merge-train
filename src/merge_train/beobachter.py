"""Ist eine offene Seite veraltet? (seite_veraltet) Dazu für Branches ohne MR und eigene MRs im Arbeitsstand: merkt, wann sich im Repo etwas getan hat.

Der Beobachter (inotify über ctypes, ohne Abhängigkeit; ohne inotify alle paar Sekunden „vielleicht“) meldet nur „seit
Zähler n hat sich etwas bewegt“. Ob sich der Stand wirklich geändert hat, prüft erst git, und das nur nach einer Meldung.
Dazu: welche Zeilen zwischen zwei Ständen neu sind (Rahmen um das Neue nach dem Tausch).
"""
import os, re, subprocess, sys, threading, time
from .einstellungen import SPERRE
from .git import arbeitsstand, git, ref_sha
from .akte import akte_lesen
from .seite import seiten_schluessel, struktur_der_seite

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


_BEOBACHTER, _GEPRUEFT = {}, {}  # wurzel → Beobachter; (wurzel, Kennung) → (Zähler, (Kopf-sha, von-sha)) der letzten git-Prüfung


def beobachter(wurzel):
    with SPERRE:
        if wurzel not in _BEOBACHTER:
            _BEOBACHTER[wurzel] = Beobachter(wurzel)
        return _BEOBACHTER[wurzel]


def seite_veraltet(waggon, seite, akte=None):
    """Zeigt die Seite mit Schlüssel seite (MR.seite) nicht mehr den neuesten Stand des Waggons? Ja, wenn seither eine
    andere Seite gebaut wurde (akte.struktur: CLI, MR-Daten, anderer Tab) oder – lokal bzw. im Arbeitsstand eines
    eigenen MR – sich im Repo etwas bewegt hat (repo_bewegt). Unbekannte Seite: ja."""
    struktur = struktur_der_seite(waggon, seite)
    if struktur is None:
        return True
    if seiten_schluessel((akte or akte_lesen(waggon)).get("struktur")) != seite:
        return True
    return repo_bewegt(waggon, struktur["refs"], struktur.get("ordner"))


def repo_bewegt(waggon, refs, ordner=None):
    """Steht das Repo nicht mehr auf refs (Arbeitsverzeichnis, Branch oder von bewegt)? git nur nach einer Meldung des
    Beobachters, sonst die letzte Antwort. Branches ohne MR (Kopf und von) und Branches im Arbeitsstand (refs.arbeitsstand);
    MRs auf dem Commit-Stand und Läufe ändern sich nur auf Knopfdruck."""
    sha = refs.get("head_sha")
    if not sha or not ordner or not os.path.isdir(ordner) or not waggon.branch:
        return False
    mit_mr = bool(akte_lesen(waggon).get("gitlab"))
    if mit_mr and not refs.get("arbeitsstand"):
        return False
    b = beobachter(ordner)
    k = (ordner, waggon.id)
    alt = _GEPRUEFT.get(k)
    if not alt or alt[0] != b.zaehler:
        n = b.zaehler
        try:  # anderer Branch ausgecheckt: anderer Arbeitsstand
            kopf = arbeitsstand(ordner) if refs.get("arbeitsstand") else ref_sha(ordner, waggon.branch)
            von = None if mit_mr else (git(ordner, "rev-parse", "--verify", "-q", refs.get("ziel") or "HEAD", check=False) or "").strip()
        except subprocess.CalledProcessError:
            return False
        alt = _GEPRUEFT[k] = (n, (kopf, von))
    start = None if mit_mr else refs.get("start_sha")
    return alt[1][0] != sha or bool(start and alt[1][1] != start)


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.M)


def neue_zeilen(ordner, alt, neu):
    """Zeilen, die zwischen den Ständen alt und neu (im Repo ordner) dazugekommen oder geändert sind: {pfad: [[von,
    bis], …]} (Zeilen im Stand neu). Reine Löschungen markieren die Zeile danach. Gleicher oder unbekannter Stand: {}."""
    if alt == neu or not (re.fullmatch(r"[0-9a-f]{7,40}", alt or "") and re.fullmatch(r"[0-9a-f]{7,40}", neu or "")):
        return {}
    roh = git(ordner, "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "-M", "-U0", alt, neu,
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
