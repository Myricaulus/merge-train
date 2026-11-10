"""Einstellungen (config.toml), Ordner und kleine Helfer, die überall gebraucht werden."""
import os, re, shlex, shutil, subprocess, sys, threading
from datetime import datetime

def _xdg(var, std):
    return os.environ.get(var) or os.path.expanduser(std)


# Das gebaute Skript (zipapp), beim Start aus dem Quellbaum der Ordner src/ – beides lässt sich mit python3 starten
SKRIPT = os.path.realpath(os.path.dirname(os.path.dirname(__file__)))
KONFIG_DATEI = os.environ.get("MERGE_TRAIN_CONFIG") or \
    os.path.join(_xdg("XDG_CONFIG_HOME", "~/.config"), "merge-train", "config.toml")


STANDARD = {
    "lokal": True,            # lokaler Projekt-Diff (von/bis-Branches aller Repos unter projekte)
    "projekte": "~/Projects",
    "von": "reviewed", "bis": "claude",
    "gitlab": True,           # GitLab-MRs über glab
    "gitlab_host": "",        # leer: Host aus MR-URL bzw. git-Remote, sonst glab-Standard
    "glab": "glab",
    "mr_liste": "reviewer",   # Zug im GitLab-Modus: reviewer | assignee | author | keine
    "hinweise": [],           # Globs für Agent-Hinweis-Dateien, z. B. "~/src/*/tasks/*-review-markers.json"
    "repos": {},              # "gruppe/projekt" = "~/pfad/zum/klon" (schneller als Dateien über die API)
    "browser": "",            # leer: xdg-open, sonst wslview/explorer.exe; unter WSL z. B. "wslview"
    "port": 8771,
    "feedback_befehl": "",    # lokaler Modus: Befehl, wenn keine Session zuhört (sonst todo-Eintrag)
    "agenten": {},            # Gespräch auch im GitLab-Modus: Name = Startbefehl, z. B. copilot = "… copilot -i {prompt}"
    "log_tage": 7,            # Log der Anfragen an die Quellen (git, GitLab): ~/.cache/merge-train/aussen-<datum>.log; 0 = aus
}


def _toml_einfach(text):
    """Notbehelf ohne tomllib (Python < 3.11): key = wert und [abschnitt], Werte wie in Python."""
    import ast
    out, akt = {}, None
    for z in text.splitlines():
        z = z.strip()
        if not z or z.startswith("#"):
            continue
        m = re.fullmatch(r"\[([\w.-]+)\]", z)
        if m:
            akt = out.setdefault(m.group(1), {}); continue
        k, _, v = z.partition("=")
        v = re.sub(r"\s+#[^\"']*$", "", v.strip())
        v = re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", v))
        (akt if akt is not None else out)[k.strip().strip('"')] = ast.literal_eval(v)
    return out


def konfig_laden():
    k = dict(STANDARD)
    try:
        text = open(KONFIG_DATEI, encoding="utf-8").read()
    except FileNotFoundError:
        return k
    try:
        import tomllib
        k.update(tomllib.loads(text))
    except ImportError:
        k.update(_toml_einfach(text))
    except Exception as e:
        sys.exit(f"merge-train: {KONFIG_DATEI} fehlerhaft: {e}")
    return k


KONF = konfig_laden()


ORDNER = os.path.join(_xdg("XDG_CACHE_HOME", "~/.cache"), "merge-train")


DATEN = os.path.join(_xdg("XDG_DATA_HOME", "~/.local/share"), "merge-train")


# projekte: Ordner mit Repos (auch eine Ebene tiefer) oder einzelne Repos – ein Eintrag oder eine Liste
PROJEKTE_LISTE = [os.path.expanduser(p) for p in (KONF["projekte"] if isinstance(KONF["projekte"], list) else [KONF["projekte"]])]


PROJEKTE = PROJEKTE_LISTE[0] if PROJEKTE_LISTE else os.path.expanduser("~")


VON, BIS = KONF["von"], KONF["bis"]


RUNDE = os.path.join(ORDNER, "runde.json")


SCHLUESSEL = os.path.join(ORDNER, "schluessel")


SPERRE = threading.RLock()


def ersetzen(ziel, inhalt):
    """Atomar schreiben (eigene Temp-Datei je Aufruf, damit parallele Abrufe sich nicht stören)."""
    import tempfile
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(ziel), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(inhalt)
    os.chmod(tmp, 0o644)
    os.replace(tmp, ziel)


def schluessel():
    os.makedirs(ORDNER, exist_ok=True)
    try:
        return open(SCHLUESSEL).read().strip()
    except FileNotFoundError:
        import secrets
        k = secrets.token_hex(16)
        try:
            fd = os.open(SCHLUESSEL, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return open(SCHLUESSEL).read().strip()
        os.write(fd, k.encode()); os.close(fd)
        return k


def projektname(wurzel):
    for p in PROJEKTE_LISTE:
        if wurzel.startswith(p.rstrip("/") + "/"):
            return os.path.relpath(wurzel, p)
    return os.path.basename(wurzel)


def dateiname(projekt):
    return projekt.replace("/", "_") + ".html"


ARBEITSSTAND = "arbeitsstand"  # bis = Arbeitsverzeichnis (auch nicht committet), z. B. von = "origin/main"


def oeffnen(ziel):
    """Im Browser öffnen: browser aus der Einstellung, sonst xdg-open / wslview / explorer.exe (WSL)."""
    if KONF["browser"]:
        argv = shlex.split(KONF["browser"])
    else:
        prog = next((p for p in ("xdg-open", "wslview", "explorer.exe") if shutil.which(p)), None)
        if not prog:
            print(f"merge-train: kein Browser-Befehl gefunden – {ziel} bitte selbst öffnen (browser = … in der Einstellung)")
            return
        argv = [prog]
    subprocess.Popen(argv + [ziel], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def melden(text):
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "merge-train", "-i", "vcs-merge-request", "merge-train", text], check=False)


# Im lokalen Projekt-Diff wird aus einem Kommentar ein Gesprächsfaden: der Nutzer schreibt (Entwurf), „Feedback senden“
# schickt alle Entwürfe ab, der Agent holt sie mit „merge-train agent feedback“ ab und antwortet mit „agent antworten“.
# Bei MRs genauso, für Kommentare, die „an <Agent>“ gespeichert werden; sie liegen als Fäden (mit „nachrichten“) in der
# Review-Datei des MR und gehen nie nach GitLab. Schlüssel g wie bei den Quellen: {"lokal": projekt} oder der MR.
# Zustand: gleiche Form wie bei MRs (kommentare mit path/a/b, refs des Stands beim Schreiben), je Faden
# „nachrichten“: [{id, von: ich|claude, wer, text, zeit, gesendet, abgeholt}], „erledigt“: {von, zeit} oder None, „an“.
# Wer zuhört: „agent horchen“ legt <zustand>.horcht an (pid, Name). Hört niemand zu, startet „Feedback senden“ den
# Agenten aus [agenten] bzw. feedback_befehl – oder legt einen todo-Eintrag an („Session starten“ öffnet ihn).

def jetzt():
    return datetime.now().isoformat(timespec="seconds")
