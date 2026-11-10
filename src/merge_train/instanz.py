"""merge-train --beobachten, Seite der Kommandozeile: eine eigene Instanz je Repo/Worktree.

Arbeitsverzeichnis gegen HEAD (oder --von), freier Port, Einstellung/Cache/Daten in
~/.local/share/merge-train/beobachten/<name>-<hash>/ (MERGE_TRAIN_INSTANZ). Die Seite lädt bei Änderungen neu, der
Server beendet sich, wenn ihr Tab zu ist. agent-Befehle aus dem Repo landen von selbst bei dieser Instanz.
"""
import hashlib, json, os, re, subprocess, sys, time
from .einstellungen import ARBEITSSTAND, DATEN_HAUPT, INSTANZ, KONF, SKRIPT, dateiname, ersetzen, oeffnen
from .git import finde_repos, git, projekt_ordner
from .server import server_laeuft

def repo_wurzel(ordner):
    """Ordner oder Projektname → Wurzel des Repos (realpath), sonst None."""
    if not os.path.isdir(ordner):
        ordner = projekt_ordner(ordner)
    w = (git(ordner, "rev-parse", "--show-toplevel", check=False) or "").strip() if os.path.isdir(ordner) else ""
    return os.path.realpath(w) if w else None


def instanz_ordner(wurzel):
    name = re.sub(r"[^\w.-]", "_", os.path.basename(wurzel))
    return os.path.join(DATEN_HAUPT, "beobachten", f"{name}-{hashlib.sha1(wurzel.encode()).hexdigest()[:8]}")


def instanz_port(ordner):
    """Port der Instanz, wenn ihr Server läuft, sonst None."""
    try:
        text = open(os.path.join(ordner, "config.toml"), encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r"^port = (\d+)", text, re.M)
    return int(m.group(1)) if m and server_laeuft(int(m.group(1))) else None


def instanz_umgebung(ordner):
    env = dict(os.environ, MERGE_TRAIN_INSTANZ=ordner)
    env.pop("MERGE_TRAIN_CONFIG", None)
    return env


def freier_port():
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def beobachten_starten(ordner, von, nur_url):
    """merge-train --beobachten [ordner] [--von REF]: Instanz anlegen bzw. weiterverwenden, Server starten, Seite öffnen."""
    wurzel = repo_wurzel(ordner or os.getcwd())
    if not wurzel:
        sys.exit(f"merge-train: kein Git-Repo: {ordner or os.getcwd()}")
    von = von or "HEAD"
    if not git(wurzel, "rev-parse", "--verify", "-q", von, check=False):
        sys.exit(f"merge-train: {von} fehlt in {wurzel}")
    inst = instanz_ordner(wurzel)
    os.makedirs(inst, exist_ok=True)
    port = instanz_port(inst) or freier_port()
    werte = {"projekte": [wurzel], "von": von, "bis": ARBEITSSTAND, "lokal": True, "gitlab": False, "port": port,
             "leerlauf": 90, "beobachten": True}
    werte.update({k: KONF[k] for k in ("browser", "feedback_befehl", "kontext_fenster", "kontext_schwellen", "log_tage")})
    text = (f"# von merge-train --beobachten erzeugt ({wurzel})\n" +
            "".join(f"{k} = {json.dumps(v, ensure_ascii=False)}\n" for k, v in werte.items()))
    cfg = os.path.join(inst, "config.toml")
    try:
        alt = open(cfg, encoding="utf-8").read()
    except OSError:
        alt = None
    if alt != text:  # ein laufender Server startet mit der neuen Einstellung neu
        ersetzen(cfg, text)
    if not server_laeuft(port):
        log = open(os.path.join(inst, "server.log"), "a")
        subprocess.Popen([sys.executable, SKRIPT, "--server"], start_new_session=True,
                         env=instanz_umgebung(inst), stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        for _ in range(50):
            time.sleep(0.1)
            if server_laeuft(port):
                break
        else:
            sys.exit(f"merge-train: Server startet nicht – siehe {os.path.join(inst, 'server.log')}")
    url = f"http://127.0.0.1:{port}/{dateiname(os.path.basename(wurzel))}"
    print(url)
    if not nur_url:
        oeffnen(url)


def zur_instanz(argv, ordner=None, immer=False):
    """Läuft für das Repo (ordner bzw. aktuelles) eine --beobachten-Instanz, den Befehl dort ausführen (exec, kehrt nicht
    zurück). agent-Befehle nur, wenn das Repo nicht ohnehin im normalen Zug ist (immer=False)."""
    if INSTANZ:
        return
    wurzel = repo_wurzel(ordner or os.getcwd())
    if not wurzel:
        return
    inst = instanz_ordner(wurzel)
    if not instanz_port(inst):
        return
    if not immer and KONF["lokal"] and wurzel in {os.path.realpath(r) for r in finde_repos()}:
        return
    os.execve(sys.executable, [sys.executable, SKRIPT] + argv, instanz_umgebung(inst))
