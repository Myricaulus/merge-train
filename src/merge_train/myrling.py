"""Läufe des Myrlings, die auf eine Prüfung warten: fragt den Befehl der Quelle (myrling_befehl, heute nas-lauf) mit
`--anstehend --json` und baut daraus je Lauf Klon, Basis und Stand für die Diff-Seite. merge-train liest und schreibt
nie selbst im Zustand des Befehls, es nimmt nur, was er ausgibt.

Ausgabe des Befehls (Vertrag mit nas-lauf):
  [{"skript": "07-luefter.sh", "fp": "<sha256>", "braucht": "02-grundsystem",
    "stand": "neu | geaendert | abgelehnt | gesehen", "abgelehnt": {"am", "grund"} | null,
    "dateien": [{"name", "repo": "/abs/repo", "pfad": "relativ/zum/repo", "basis": "<commit>" | null,
                 "commit": "<HEAD des Repos>"}, …]}]          – das Skript zuerst
Diff je Datei: basis gegen commit direkt (nicht über den gemeinsamen Vorgänger), basis null = neu. Der Aufruf dauert
etwa eine Sekunde: nicht im 4-s-Takt, sondern beim Laden einer Seite (im Hintergrund) und nach „↻“."""
import json, os, re, shlex, shutil, subprocess, threading, time
from .einstellungen import KONF
from .waggon import Fehler
from .git import aussen_log, stand_mit

FRISCH = 5  # so viele Sekunden gilt eine Antwort des Befehls als aktuell (Seite und zug.js kurz nacheinander)


_SPERRE = threading.Lock()
_STAND = {"zeit": 0.0, "laeufe": None, "fehler": None}
_FERTIG = threading.Event()
_FERTIG.set()


def befehl():
    """Argumente des Befehls (myrling_befehl, ~ erlaubt)."""
    argv = shlex.split(KONF["myrling_befehl"] or "")
    return [os.path.expanduser(argv[0])] + argv[1:] if argv else []


def befehl_da():
    argv = befehl()
    return bool(argv and shutil.which(argv[0]))


def befehl_aufrufen(*a, zeit=60):
    """Befehl mit Argumenten: CompletedProcess (stdout/stderr als Text), protokolliert wie git und GitLab."""
    argv = befehl() + list(a)
    t0 = time.time()
    try:
        r = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=zeit, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        aussen_log("myrling", os.path.basename(argv[0]), " ".join(a)[:200], time.time() - t0, type(e).__name__)
        raise Fehler(f"{os.path.basename(argv[0])} {' '.join(a)}: {e}")
    aussen_log("myrling", os.path.basename(argv[0]), " ".join(a)[:200], time.time() - t0,
               f"exit {r.returncode}" if r.returncode else f"ok {len(r.stdout)} B")
    return r


def lauf_pruefen(lauf):
    """Ein Eintrag aus --anstehend, nur mit dem, was die Seite braucht; Fehler bei falscher Form."""
    hexa = lambda x: isinstance(x, str) and re.fullmatch(r"[0-9a-f]{40}([0-9a-f]{24})?", x)
    if not (isinstance(lauf, dict) and isinstance(lauf.get("skript"), str) and re.fullmatch(r"[\w][\w.+-]*", lauf["skript"])
            and ".." not in lauf["skript"] and isinstance(lauf.get("fp"), str) and isinstance(lauf.get("dateien"), list)
            and lauf["dateien"]):
        raise ValueError(f"Eintrag ohne skript/fp/dateien: {str(lauf)[:200]}")
    dateien = []
    for d in lauf["dateien"]:
        if not (isinstance(d, dict) and isinstance(d.get("repo"), str) and os.path.isabs(d["repo"])
                and isinstance(d.get("pfad"), str) and d["pfad"] and not d["pfad"].startswith("/")
                and ".." not in d["pfad"].split("/") and hexa(d.get("commit")) and (d.get("basis") is None or hexa(d["basis"]))):
            raise ValueError(f"{lauf['skript']}: Datei mit falscher Form: {str(d)[:200]}")
        dateien.append({"name": d.get("name") or os.path.basename(d["pfad"]), "repo": d["repo"], "pfad": d["pfad"],
                        "basis": d["basis"], "commit": d["commit"]})
    abgelehnt = lauf.get("abgelehnt") if isinstance(lauf.get("abgelehnt"), dict) else None
    return {"skript": lauf["skript"], "fp": lauf["fp"], "stand": str(lauf.get("stand") or "geaendert"),
            "braucht": str(lauf.get("braucht") or ""), "abgelehnt": abgelehnt, "dateien": dateien}


def _holen():
    try:
        r = befehl_aufrufen("--anstehend", "--json")
        if r.returncode:
            raise Fehler(f"{os.path.basename(befehl()[0])} --anstehend: exit {r.returncode}: {(r.stderr or r.stdout).strip()[-300:]}")
        try:
            laeufe = [lauf_pruefen(x) for x in json.loads(r.stdout or "[]")]
        except (ValueError, TypeError) as e:
            raise Fehler(f"{os.path.basename(befehl()[0])} --anstehend --json: unerwartete Ausgabe ({e})")
        _STAND.update(zeit=time.time(), laeufe=laeufe, fehler=None)
    except Fehler as e:
        _STAND.update(zeit=time.time(), fehler=str(e))  # alte Liste bleibt stehen
    finally:
        _FERTIG.set()


def anstehend(frisch=FRISCH):
    """Die anstehenden Läufe; älter als frisch Sekunden: den Befehl fragen (wartet). Fehler, wenn es noch keine Liste gibt."""
    with _SPERRE:
        if _STAND["laeufe"] is None or time.time() - _STAND["zeit"] > frisch:
            if _FERTIG.is_set():
                _FERTIG.clear()
                los = True
            else:
                los = False
        else:
            los = None
    if los:
        _holen()
    elif los is False:
        _FERTIG.wait(120)
    if _STAND["laeufe"] is None:
        raise Fehler(_STAND["fehler"] or "Myrling: keine Liste der anstehenden Läufe")
    return _STAND["laeufe"]


def im_hintergrund_holen():
    """Für das Laden einer Seite (zug.js): veraltete Liste im Hintergrund neu holen. True, wenn gerade geholt wird – die
    Seite fragt dann den Zug mit warten=1 nach (anstehend_warten)."""
    with _SPERRE:
        if _STAND["laeufe"] is not None and time.time() - _STAND["zeit"] <= FRISCH:
            return not _FERTIG.is_set()
        if not _FERTIG.is_set():
            return True
        _FERTIG.clear()
    threading.Thread(target=_holen, daemon=True).start()
    return True


def anstehend_warten(zeit=60):
    """Wartet, bis ein laufendes Holen fertig ist (api/zug?warten=1)."""
    _FERTIG.wait(zeit)


def gepuffert():
    """Die zuletzt geholte Liste ohne zu fragen (None: noch nie geholt) und der letzte Fehler."""
    return _STAND["laeufe"], _STAND["fehler"]


def lauf_von(skript, frisch=FRISCH):
    """Der anstehende Lauf dieses Skripts; Fehler, wenn er nicht (mehr) ansteht."""
    lauf = next((x for x in anstehend(frisch) if x["skript"] == skript), None)
    if not lauf:
        raise Fehler(f"{skript} wartet auf keine Prüfung (schon geprüft, gelaufen oder nicht committet)")
    return lauf


def lauf_ort(lauf):
    """(Klon, Basis, Stand, fehlen) eines Laufs: der Klon des Skripts; Basis = Stand, in dem jede Datei auf ihrer
    Vergleichsbasis steht (stand_mit), Stand = commit. fehlen: Dateien aus anderen Repos (zeigt der Waggon noch nicht)."""
    erste = lauf["dateien"][0]
    wurzel, head = erste["repo"], erste["commit"]
    hier = [d for d in lauf["dateien"] if d["repo"] == wurzel]
    fehlen = [d for d in lauf["dateien"] if d["repo"] != wurzel]
    if any(d["commit"] != head for d in hier):
        raise Fehler(f"{lauf['skript']}: Dateien eines Repos auf verschiedenen Ständen – neu laden")
    if not os.path.isdir(wurzel):
        raise Fehler(f"{lauf['skript']}: Repo {wurzel} fehlt")
    try:
        basis = _basis(wurzel, head, tuple((d["pfad"], d["basis"]) for d in hier))
    except subprocess.CalledProcessError as e:
        raise Fehler(f"{lauf['skript']}: {wurzel} kennt einen Stand nicht ({(e.stderr or '').strip()[-200:]})")
    return wurzel, basis, head, fehlen


_BASIS = {}


def _basis(wurzel, head, fassungen):
    k = (wurzel, head, fassungen)
    if k not in _BASIS:
        if len(_BASIS) > 200:
            _BASIS.clear()
        _BASIS[k] = stand_mit(wurzel, head, dict(fassungen), "merge-train: zuletzt angesehene Fassung (Myrling)")
    return _BASIS[k]
