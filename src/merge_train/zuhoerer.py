"""Wer hört zu? Agenten-Sessions, die auf Nachrichten warten, benachrichtigen oder neu starten."""
import os, shlex, shutil, subprocess
from datetime import datetime
from .einstellungen import KONF, SPERRE, ersetzen, jetzt
from .zustand import faeden_von, review_datei, review_laden, review_speichern
from .gitlab import GitLabFehler, mr_id
from .quellen import quelle

# ---- Wer bekommt das Feedback?

def horcht_datei(g):
    return review_datei(g)[:-5] + ".horcht"


# Was zwischen „agent horchen“ und der Agenten-Session (claude, copilot …) liegen darf. systemd/init: dorthin wandern
# verwaiste Prozesse, wenn die Session weg ist – dann hört niemand mehr zu.
_ZWISCHEN = {"sh", "bash", "zsh", "fish", "dash", "ksh", "python", "python3", "timeout", "env", "nohup", "setsid", "script"}


_WAISENHAUS = {"systemd", "init", "launchd"}


def _prozess(pid):
    """(name, ppid) aus /proc, None wenn es den Prozess nicht (mehr) gibt."""
    try:
        stat = open(f"/proc/{pid}/stat").read()
    except OSError:
        return None
    zustand, ppid = stat[stat.rindex(")") + 2:].split()[:2]
    return None if zustand == "Z" else (stat[stat.index("(") + 1:stat.rindex(")")], int(ppid))  # Zombie: schon beendet


def agent_session(pid):
    """Die Agenten-Session über pid: der nächste Vorfahr, der keine Shell/Python ist. None = verwaist (Session weg).
    Ohne /proc (kein Linux/WSL) lässt sich das nicht prüfen: dann gilt pid selbst."""
    if not os.path.isdir("/proc/self"):
        return pid
    p = pid
    for _ in range(30):
        info = _prozess(p)
        if info is None:
            return None
        name, ppid = info
        if p != pid and name not in _ZWISCHEN:
            return None if name in _WAISENHAUS or name.startswith(("Relay(", "SessionLeader")) else p
        if ppid <= 1:
            return None
        p = ppid
    return None


SEITE_WEG_S = int(os.environ.get("MERGE_TRAIN_SEITE_WEG_S") or 30)


def seite_datei(g):
    return review_datei(g)[:-5] + ".seite"


def seite_lebt(g):
    """Lebenszeichen einer offenen Seite (fragt alle 4 s nach dem Stand) – horchen hört auf, wenn keins mehr kommt."""
    p = seite_datei(g)
    try:
        os.utime(p)
    except FileNotFoundError:
        ersetzen(p, "")


def horcht(g):
    """Name der Session, die gerade mit „agent horchen“ zuhört (Standard „Claude“), sonst None. Zählt nur, solange über
    dem horchen-Prozess noch eine Agenten-Session lebt (sonst ist es ein Überbleibsel einer beendeten Session)."""
    try:
        teile = open(horcht_datei(g)).read().split()
        pid = int(teile[0])
        os.kill(pid, 0)
    except (OSError, ValueError, IndexError):
        return None
    if agent_session(pid) is None:
        return None
    return " ".join(teile[2:]) or "Claude"


def todo_offen(tid):
    if not tid:
        return False
    basis = os.environ.get("TODO_DIR") or os.path.expanduser("~/todo")
    return os.path.exists(os.path.join(basis, "offen", tid + ".md"))


def benachrichtigen(g, wurzel, n, namen=("Claude",)):
    """Nach „Feedback senden“: Session, die zuhört → nichts weiter; sonst Agent aus [agenten], feedback_befehl oder
    todo-Eintrag. Rückgabe (text für die Seite, todo_id oder None)."""
    wer = horcht(g)
    if wer:
        return f"an die Session übergeben, die zuhört ({wer})", None
    projekt = quelle(g).name_von(g)
    prompt = quelle(g).prompt(g, wurzel)
    agenten = KONF.get("agenten") or {}
    befehle = [(nm, agenten[nm]) for nm in namen if nm in agenten]
    if not befehle and KONF.get("feedback_befehl"):
        befehle = [("Claude", KONF["feedback_befehl"])]
    if befehle:
        gestartet = []
        for nm, befehl in befehle:
            argv = [a.format(ordner=wurzel, projekt=projekt, prompt=prompt) for a in shlex.split(befehl)]
            try:
                subprocess.Popen(argv, cwd=wurzel, start_new_session=True, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                gestartet.append(nm)
            except OSError as e:
                return f"{nm} startet nicht: {e}", None
        return " und ".join(gestartet) + " gestartet", None
    if not shutil.which("todo"):
        return f"Keine Session hört zu – in einer Agent-Session „merge-train agent feedback {mr_id(g)}“ sagen", None
    with SPERRE:
        tid = review_laden(g).get("todo_id")
    zeile = f"{n} neue Nachricht(en) um {datetime.now().strftime('%H:%M')}"
    if todo_offen(tid):
        subprocess.run(["todo", "notiz", tid, zeile, "--von", "merge-train"], capture_output=True)
    else:
        r = subprocess.run(["todo", "neu", f"merge-train: Fragen/Feedback zu {projekt}", "-p", wurzel,
                            "--von", "merge-train", "-n", "Aus merge-train „Feedback senden“. " + zeile, "--prompt", prompt],
                           capture_output=True, text=True)
        tid = (r.stdout.strip().splitlines() or [""])[-1].strip() if r.returncode == 0 else None
        if not tid:
            return f"todo-Eintrag ließ sich nicht anlegen: {(r.stderr or r.stdout).strip()[:200]}", None
        with SPERRE:
            st = review_laden(g); st["todo_id"] = tid; review_speichern(g, st)
    subprocess.run(["todo", "heute", tid, "-t", f"Fragen/Feedback aus merge-train ({zeile})"], capture_output=True)
    return "Keine Session hört zu – als todo eingetragen (Panel), „▶ Session starten“ öffnet sie", tid


def feedback_senden(g):
    """Alle Entwürfe abschicken. Rückgabe (ok, text, todo_id)."""
    try:
        wurzel, _ = quelle(g).ort(g)
    except GitLabFehler as e:
        return False, str(e), None
    with SPERRE:
        st = review_laden(g)
        n, namen = 0, []
        for k in faeden_von(st):
            for m in k["nachrichten"]:
                if m["von"] == "ich" and not m.get("gesendet"):
                    m["gesendet"] = jetzt(); n += 1
                    if (k.get("an") or "Claude") not in namen:
                        namen.append(k.get("an") or "Claude")
        if not n:
            return False, "Keine Entwürfe zum Senden", None
        review_speichern(g, st)
    text, tid = benachrichtigen(g, wurzel, n, namen)
    return True, f"{n} Nachricht(en) gesendet · {text}", tid


def session_starten(g):
    with SPERRE:
        tid = review_laden(g).get("todo_id")
    if not todo_offen(tid):
        return False, "Kein offener todo-Eintrag"
    r = subprocess.run(["todo", "los", tid], capture_output=True, text=True)
    return (True, "Konsole geöffnet – Enter startet Claude") if r.returncode == 0 else \
        (False, f"todo los: {(r.stderr or r.stdout).strip()[:200]}")
