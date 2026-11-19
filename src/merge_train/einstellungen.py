"""Einstellungen (config.toml), Ordner und kleine Helfer, die überall gebraucht werden."""
import os, re, shlex, shutil, subprocess, sys, threading
from datetime import datetime

def _xdg(var, std):
    return os.environ.get(var) or os.path.expanduser(std)


# Das gebaute Skript (zipapp), beim Start aus dem Quellbaum der Ordner src/ – beides lässt sich mit python3 starten
SKRIPT = os.path.realpath(os.path.dirname(os.path.dirname(__file__)))
# Eigene Instanz (merge-train --beobachten): Einstellung, Cache und Daten in einem Ordner, eigener Port
INSTANZ = os.environ.get("MERGE_TRAIN_INSTANZ") or ""
KONFIG_DATEI = os.environ.get("MERGE_TRAIN_CONFIG") or (INSTANZ and os.path.join(INSTANZ, "config.toml")) or \
    os.path.join(_xdg("XDG_CONFIG_HOME", "~/.config"), "merge-train", "config.toml")


STANDARD = {
    "lokal": True,            # lokaler Projekt-Diff (von/bis-Branches aller Repos unter projekte)
    "projekte": "~/Projects",
    "von": "reviewed", "bis": "claude",
    "gitlab": True,           # GitLab-MRs über glab
    "gitlab_host": "",        # leer: Host aus MR-URL bzw. git-Remote, sonst glab-Standard
    "glab": "glab",
    "myrling": True,          # Läufe des Myrlings, die auf eine Prüfung warten (ein Waggon je Skript); aus, wenn der Befehl fehlt
    "myrling_befehl": "nas-lauf",  # liefert sie (--anstehend --json), z. B. "~/Projects/newterminal/nas-setup/werkzeuge/nas-lauf"
    "mr_liste": "reviewer,author",  # Zug im GitLab-Modus: reviewer, assignee, author (mehrere mit Komma) | keine
    "hinweise": [],           # Globs für Agent-Hinweis-Dateien, z. B. "~/src/*/tasks/*-review-markers.json"
    "repos": {},              # "gruppe/projekt" = "~/pfad/zum/klon" (schneller als Dateien über die API)
    "zweige": {},             # je lokalem Projekt eigene von/bis: [zweige.<projekt>] von = …, bis = … (Seite: Waggon aufklappen)
    "klon_ordner": [],        # Ordner, in denen Klone liegen: MR von gruppe/projekt → <ordner>/projekt, wenn origin passt
    "browser": "",            # leer: xdg-open, sonst wslview/explorer.exe; unter WSL z. B. "wslview"
    "port": 8771,
    "leerlauf": 3600,         # Server beendet sich nach so vielen Sekunden ohne Anfrage (offene Seiten fragen alle 4 s)
    "beobachten": False,      # von merge-train --beobachten gesetzt: Seite lädt bei Änderungen im Repo neu
    "feedback_befehl": "",    # lokaler Modus: Befehl, wenn keine Session zuhört (sonst todo-Eintrag)
    "agenten": {},            # Gespräch auch im GitLab-Modus: Name = Startbefehl, z. B. copilot = "… copilot -i {prompt}"
    "kontext_fenster": 0,     # HUD „ctx“: Kontextfenster der Agenten-Session in Tokens; 0 = 200k (1M bei [1m])
    "kontext_schwellen": [15, 20, 25, 35],  # HUD-Balken in %: bis a grün, bis b → orange, bis c → rot, ab d giftlila
    "mr_auschecken": True,    # erster Besuch eines MR: Quell-Branch im lokalen Klon auschecken, wenn der Stand sauber ist
    "ich_symbol": "🤓",       # Listen links: dein Symbol für „zuletzt von dir“ (🤖 = Agent, Logo der Quelle = extern)
    "vorfall_github": "",     # agent vorfall: GitHub-Repo „owner/repo“ für Issues; leer = origin des merge-train-Klons, „aus“ = nur Datei
    "gh": "gh",
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
        m = re.fullmatch(r"\[(.+)\]", z)
        if m:  # [a], [a.b], [a."b/c"]
            akt = out
            for teil in re.findall(r'"([^"]*)"|([^."]+)', m.group(1)):
                akt = akt.setdefault((teil[0] or teil[1]).strip(), {})
            continue
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


def konfig_maengel():
    """Was an der Einstellung nicht stimmt (für merge-train status): unbekannte Schlüssel (Tippfehler, sonst still
    übergangen), Werte vom falschen Typ, Ordner unter projekte, die es nicht gibt. Je Mangel ein Text."""
    out = [f"unbekannte Einstellung „{k}“ (Tippfehler? bekannt sind die in config.example.toml)"
           for k in sorted(set(KONF) - set(STANDARD))]
    for k, std in STANDARD.items():
        v = KONF[k]
        typen = (str, list) if k == "projekte" else (int,) if type(std) is int else (type(std),)
        if not isinstance(v, typen) or isinstance(v, bool) != isinstance(std, bool):
            out.append(f"„{k}“ = {v!r} hat den falschen Typ (erwartet wie im Standard: {std!r})")
    return out + [f"projekte: Ordner {p} gibt es nicht" for p in PROJEKTE_LISTE if not os.path.isdir(p)]


ORDNER = os.path.join(INSTANZ, "cache") if INSTANZ else os.path.join(_xdg("XDG_CACHE_HOME", "~/.cache"), "merge-train")


DATEN_HAUPT = os.path.join(_xdg("XDG_DATA_HOME", "~/.local/share"), "merge-train")  # Instanzen liegen darunter
DATEN = os.path.join(INSTANZ, "daten") if INSTANZ else DATEN_HAUPT


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
        with open(SCHLUESSEL) as f:
            return f.read().strip()
    except FileNotFoundError:
        import secrets
        k = secrets.token_hex(16)
        try:
            fd = os.open(SCHLUESSEL, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            with open(SCHLUESSEL) as f:
                return f.read().strip()
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
    try:
        subprocess.Popen(argv + [ziel], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        # z. B. Errno 8 bei explorer.exe, wenn die WSL-Interop (binfmt WSLInterop) weg ist
        print(f"merge-train: {argv[0]} ließ sich nicht starten ({e.strerror}) – {ziel} bitte selbst öffnen")


def melden(text):
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "merge-train", "-i", "vcs-merge-request", "merge-train", text], check=False)


def jetzt():
    return datetime.now().isoformat(timespec="seconds")
