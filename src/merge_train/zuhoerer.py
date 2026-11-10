"""Wer hört zu? Agenten-Sessions, die auf Nachrichten warten, benachrichtigen oder neu starten."""
import glob, json, os, shlex, shutil, subprocess
from datetime import datetime
from .einstellungen import KONF, SPERRE, ersetzen, jetzt
from .waggon import Fehler
from .zustand import faeden_von, review_datei, review_laden, review_speichern
from .quellen import quelle

# ---- Wer bekommt das Feedback?

def horcht_datei(waggon):
    return review_datei(waggon)[:-5] + ".horcht"


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


def seite_datei(waggon):
    return review_datei(waggon)[:-5] + ".seite"


def seite_lebt(waggon):
    """Lebenszeichen einer offenen Seite (fragt alle 4 s nach dem Stand) – horchen hört auf, wenn keins mehr kommt."""
    p = seite_datei(waggon)
    try:
        os.utime(p)
    except FileNotFoundError:
        ersetzen(p, "")


def horcht(waggon):
    """Name der Session, die gerade mit „agent horchen“ zuhört (Standard „Claude“), sonst None. Zählt nur, solange über
    dem horchen-Prozess noch eine Agenten-Session lebt (sonst ist es ein Überbleibsel einer beendeten Session)."""
    try:
        teile = open(horcht_datei(waggon)).read().split()
        pid = int(teile[0])
        os.kill(pid, 0)
    except (OSError, ValueError, IndexError):
        return None
    if agent_session(pid) is None:
        return None
    return " ".join(teile[2:]) or "Claude"


# ---- Kontext-Füllstand der Agenten-Session (fürs HUD, ohne Zutun des Agenten)
# „agent horchen“ merkt sich in <zustand>.agent pid und Session-ID der Agenten-Session (Claude Code setzt
# CLAUDE_CODE_SESSION_ID). Den Füllstand liest der Server aus deren Transcript: usage der letzten Antwort
# (input + cache_creation + cache_read) bzw. nach /compact postTokens. Solange die Session lebt, auch während sie
# arbeitet (dann hört sie gerade nicht zu).

def agent_datei(waggon):
    return review_datei(waggon)[:-5] + ".agent"

_KONTEXT = {}

def claude_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")

def _transcript_kontext(pfad):
    """(tokens, modell) aus dem Ende des Transcripts, None wenn nichts zu finden. Gecacht nach Größe/mtime."""
    try:
        s = os.stat(pfad)
    except OSError:
        return None
    alt = _KONTEXT.get(pfad)
    if alt and alt[0] == (s.st_size, s.st_mtime_ns):
        return alt[1]
    erg, block = None, 1 << 20
    with open(pfad, "rb") as f:
        for n in (block, 8 * block):  # meist reicht das letzte MB; lange Tool-Ausgaben → mehr
            f.seek(max(0, s.st_size - n))
            for zeile in reversed(f.read().split(b"\n")):
                if b'"usage"' not in zeile and b"compact_boundary" not in zeile:
                    continue
                try:
                    d = json.loads(zeile)
                except ValueError:
                    continue
                if d.get("isSidechain"):
                    continue
                if d.get("subtype") == "compact_boundary":
                    t = (d.get("compactMetadata") or {}).get("postTokens")
                    if t:
                        erg = (t, None)
                        break
                u = (d.get("message") or {}).get("usage") if d.get("type") == "assistant" else None
                if u:
                    erg = (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                           + u.get("cache_read_input_tokens", 0), d["message"].get("model"))
                    break
            if erg or s.st_size <= n:
                break
    _KONTEXT[pfad] = ((s.st_size, s.st_mtime_ns), erg)
    return erg

def _kontext_fenster(tokens):
    if KONF.get("kontext_fenster"):
        return int(KONF["kontext_fenster"])
    try:
        modell = json.load(open(os.path.join(claude_dir(), "settings.json"))).get("model") or ""
    except (OSError, ValueError):
        modell = ""
    return 1_000_000 if "[1m]" in modell or tokens > 200_000 else 200_000

def kontext(waggon):
    """{tokens, fenster, prozent, name} der zuletzt horchenden Agenten-Session, solange sie lebt, sonst None."""
    try:
        pid, sid, *name = open(agent_datei(waggon)).read().split()
        pid = int(pid)
    except (OSError, ValueError):
        return None
    if _prozess(pid) is None:
        return None
    pfade = glob.glob(os.path.join(claude_dir(), "projects", "*", sid + ".jsonl"))
    erg = _transcript_kontext(pfade[0]) if pfade else None
    if not erg:
        return None
    fenster = _kontext_fenster(erg[0])
    return {"tokens": erg[0], "fenster": fenster, "prozent": round(100 * erg[0] / fenster), "name": " ".join(name) or "Claude",
            "schwellen": kontext_schwellen()}

def kontext_schwellen():
    """[grün bis, orange bei, rot bei, giftlila ab] aus kontext_schwellen; ungültig (nicht 4 aufsteigende Zahlen) → Standard."""
    s = KONF.get("kontext_schwellen")
    try:
        s = [float(x) for x in s]
        if len(s) == 4 and s == sorted(s):
            return s
    except (TypeError, ValueError):
        pass
    return [15, 20, 25, 35]


def todo_offen(tid):
    if not tid:
        return False
    basis = os.environ.get("TODO_DIR") or os.path.expanduser("~/todo")
    return os.path.exists(os.path.join(basis, "offen", tid + ".md"))


def benachrichtigen(waggon, wurzel, n, namen=("Claude",)):
    """Nach „Feedback senden“: Session, die zuhört → nichts weiter; sonst Agent aus [agenten], feedback_befehl oder
    todo-Eintrag. Rückgabe (text für die Seite, todo_id oder None)."""
    wer = horcht(waggon)
    if wer:
        return f"an die Session übergeben, die zuhört ({wer})", None
    projekt = waggon.name
    prompt = quelle(waggon).prompt(waggon, wurzel)
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
        return f"Keine Session hört zu – in einer Agent-Session „merge-train agent feedback {waggon.id}“ sagen", None
    with SPERRE:
        tid = review_laden(waggon).get("todo_id")
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
            st = review_laden(waggon); st["todo_id"] = tid; review_speichern(waggon, st)
    subprocess.run(["todo", "heute", tid, "-t", f"Fragen/Feedback aus merge-train ({zeile})"], capture_output=True)
    return "Keine Session hört zu – als todo eingetragen (Panel), „▶ Session starten“ öffnet sie", tid


def feedback_senden(waggon):
    """Alle Entwürfe abschicken. Rückgabe (ok, text, todo_id)."""
    try:
        wurzel, _ = quelle(waggon).ort(waggon)
    except Fehler as e:
        return False, str(e), None
    with SPERRE:
        st = review_laden(waggon)
        n, namen = 0, []
        for k in faeden_von(st):
            for m in k["nachrichten"]:
                if m["von"] == "ich" and not m.get("gesendet"):
                    m["gesendet"] = jetzt(); n += 1
                    if (k.get("an") or "Claude") not in namen:
                        namen.append(k.get("an") or "Claude")
        if not n:
            return False, "Keine Entwürfe zum Senden", None
        review_speichern(waggon, st)
    text, tid = benachrichtigen(waggon, wurzel, n, namen)
    return True, f"{n} Nachricht(en) gesendet · {text}", tid


def session_starten(waggon):
    with SPERRE:
        tid = review_laden(waggon).get("todo_id")
    if not todo_offen(tid):
        return False, "Kein offener todo-Eintrag"
    r = subprocess.run(["todo", "los", tid], capture_output=True, text=True)
    return (True, "Konsole geöffnet – Enter startet Claude") if r.returncode == 0 else \
        (False, f"todo los: {(r.stderr or r.stdout).strip()[:200]}")
