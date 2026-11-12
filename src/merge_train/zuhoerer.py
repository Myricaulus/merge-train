"""Wer hört zu? Agenten-Sessions, die auf Nachrichten warten, benachrichtigen oder neu starten."""
import glob, json, os, shlex, shutil, subprocess
from datetime import datetime
from .einstellungen import KONF, ersetzen, jetzt
from .waggon import Fehler
from .akte import akte_bearbeiten, akte_datei, akte_lesen, faeden_von
from .quellen import quelle

# ---- Wer bekommt das Feedback?

def horcht_datei(waggon):
    return akte_datei(waggon)[:-5] + ".horcht"


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
    prozess_zustand, ppid = stat[stat.rindex(")") + 2:].split()[:2]
    return None if prozess_zustand == "Z" else (stat[stat.index("(") + 1:stat.rindex(")")], int(ppid))  # Zombie: schon beendet


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
    return akte_datei(waggon)[:-5] + ".seite"


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


# ---- Kontext-Füllstand und Tätigkeit der Agenten-Session (fürs HUD und den Waggon, ohne Zutun des Agenten)
# „agent horchen“ merkt sich in <akte>.agent pid und Session-ID der Agenten-Session (Claude Code setzt
# CLAUDE_CODE_SESSION_ID). Der Server liest deren Transcript (Zeile für Zeile, nur was seit dem letzten Mal dazukam):
# Füllstand = usage der letzten Antwort (input + cache_creation + cache_read) bzw. nach /compact postTokens; ob sie
# arbeitet = ob die letzte Nachricht eine fertige Antwort ist. Solange die Session lebt, auch während sie arbeitet.

def agent_datei(waggon):
    return akte_datei(waggon)[:-5] + ".agent"

def claude_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


class TranscriptStand:
    """Was der Server aus einem Transcript wissen will. groesster: der höchste Füllstand, der je vorkam (auch preTokens
    vor /compact) – liegt er über 200k, hat die Session ein 1M-Fenster."""
    def __init__(self):
        self.gelesen, self.tokens, self.groesster, self.arbeitet = 0, None, 0, False

    def zeile(self, d):
        if d.get("isSidechain"):
            return
        if d.get("subtype") == "compact_boundary":
            meta = d.get("compactMetadata") or {}
            self.groesster = max(self.groesster, meta.get("preTokens") or 0)
            self.tokens = meta.get("postTokens") or self.tokens
            return
        if d.get("type") not in ("user", "assistant"):
            return  # Metadaten (Titel, Modus …) sagen nichts über die Arbeit
        m = d.get("message") or {}
        if d["type"] == "assistant":
            self.arbeitet = m.get("stop_reason") not in ("end_turn", "stop_sequence")
            u = m.get("usage")
            if u:
                self.tokens = (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                               + u.get("cache_read_input_tokens", 0))
                self.groesster = max(self.groesster, self.tokens)
        else:  # Prompt oder Tool-Ergebnis: jetzt ist der Agent dran – außer der Nutzer hat ihn abgebrochen (Esc)
            inhalt = m.get("content")
            text = inhalt if isinstance(inhalt, str) else " ".join(
                x.get("text", "") for x in inhalt or [] if isinstance(x, dict) and x.get("type") == "text")
            self.arbeitet = not text.startswith("[Request interrupted")


_TRANSCRIPT_STAND = {}  # Pfad → TranscriptStand

def transcript_stand(pfad):
    """TranscriptStand des Transcripts, nachgelesen bis zur letzten vollständigen Zeile; None, wenn es fehlt."""
    try:
        groesse = os.path.getsize(pfad)
    except (OSError, TypeError):
        return None
    st = _TRANSCRIPT_STAND.get(pfad)
    if st is None or groesse < st.gelesen:
        st = _TRANSCRIPT_STAND[pfad] = TranscriptStand()
    if groesse > st.gelesen:
        with open(pfad, "rb") as f:
            f.seek(st.gelesen)
            neu = f.read(groesse - st.gelesen)
        ende = neu.rfind(b"\n") + 1
        for zeile in neu[:ende].split(b"\n"):
            try:
                st.zeile(json.loads(zeile))
            except (ValueError, AttributeError):
                pass
        st.gelesen += ende
    return st


def _kontext_fenster(st):
    if KONF.get("kontext_fenster"):
        return int(KONF["kontext_fenster"])
    try:
        modell = json.load(open(os.path.join(claude_dir(), "settings.json"))).get("model") or ""
    except (OSError, ValueError):
        modell = ""
    return 1_000_000 if "[1m]" in modell or st.groesster > 200_000 else 200_000


_TRANSCRIPTS = {}  # Session-ID → Pfad des Transcripts

def agent_sitzung(waggon):
    """(pid, Name, Transcript oder None) der zuletzt an diesem Waggon horchenden Agenten-Session, solange sie lebt,
    sonst None."""
    try:
        pid, sid, *name = open(agent_datei(waggon)).read().split()
        pid = int(pid)
    except (OSError, ValueError):
        return None
    if _prozess(pid) is None:
        return None
    if not os.path.exists(_TRANSCRIPTS.get(sid) or ""):
        pfade = glob.glob(os.path.join(claude_dir(), "projects", "*", sid + ".jsonl"))
        _TRANSCRIPTS[sid] = pfade[0] if pfade else None
    return pid, " ".join(name) or "Claude", _TRANSCRIPTS[sid]

def kontext(waggon):
    """{tokens, fenster, prozent, name} der zuletzt horchenden Agenten-Session, solange sie lebt, sonst None."""
    sitzung = agent_sitzung(waggon)
    st = transcript_stand(sitzung[2]) if sitzung else None
    if not st or not st.tokens:
        return None
    fenster = _kontext_fenster(st)
    return {"tokens": st.tokens, "fenster": fenster, "prozent": round(100 * st.tokens / fenster), "name": sitzung[1],
            "schwellen": kontext_schwellen()}


def zuhoerer(waggon):
    """Wer an diesem Waggon zuhört und was er gerade tut, für die Kopfhörer im Waggon und im HUD: {wer, tut}, sonst
    None. tut: hoert (wartet mit „agent horchen“ auf Fragen), arbeitet (die letzte Nachricht im Transcript ist keine
    fertige Antwort). Wartet die Session im Terminal, zeigt die Seite nichts: von dort ist sie ohnehin nicht zu
    erreichen. Horcht die Session an einem anderen Waggon, zählt sie hier nicht."""
    wer = horcht(waggon)
    if wer:
        return {"wer": wer, "tut": "hoert"}
    sitzung = agent_sitzung(waggon)
    if not sitzung:
        return None
    for d in glob.glob(os.path.join(os.path.dirname(akte_datei(waggon)), "*.horcht")):
        try:
            if agent_session(int(open(d).read().split()[0])) == sitzung[0]:
                return None
        except (OSError, ValueError, IndexError):
            pass
    st = transcript_stand(sitzung[2])
    return {"wer": sitzung[1], "tut": "arbeitet"} if st and st.arbeitet else None

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
    """Nach „An Agent senden“: Session, die zuhört → nichts weiter; sonst Agent aus [agenten], feedback_befehl oder
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
    tid = akte_lesen(waggon).get("todo_id")
    zeile = f"{n} neue Nachricht(en) um {datetime.now().strftime('%H:%M')}"
    if todo_offen(tid):
        subprocess.run(["todo", "notiz", tid, zeile, "--von", "merge-train"], capture_output=True)
    else:
        r = subprocess.run(["todo", "neu", f"merge-train: Fragen/Feedback zu {projekt}", "-p", wurzel,
                            "--von", "merge-train", "-n", "Aus merge-train „An Agent senden“. " + zeile, "--prompt", prompt],
                           capture_output=True, text=True)
        tid = (r.stdout.strip().splitlines() or [""])[-1].strip() if r.returncode == 0 else None
        if not tid:
            return f"todo-Eintrag ließ sich nicht anlegen: {(r.stderr or r.stdout).strip()[:200]}", None
        with akte_bearbeiten(waggon) as akte:
            akte["todo_id"] = tid
    subprocess.run(["todo", "heute", tid, "-t", f"Fragen/Feedback aus merge-train ({zeile})"], capture_output=True)
    return "Keine Session hört zu – als todo eingetragen (Panel), „▶ Session starten“ öffnet sie", tid


def feedback_senden(waggon):
    """Alle Entwürfe (des aktuellen Branches) abschicken. Rückgabe (ok, text, todo_id)."""
    try:
        wurzel, _ = quelle(waggon).ort(waggon)
    except Fehler as e:
        return False, str(e), None
    branch = quelle(waggon).branch(waggon)
    with akte_bearbeiten(waggon) as akte:
        n, namen = 0, []
        for k in faeden_von(akte, branch):
            for m in k["nachrichten"]:
                if m["von"] == "ich" and not m.get("gesendet"):
                    m["gesendet"] = jetzt(); n += 1
                    if (k.get("an") or "Claude") not in namen:
                        namen.append(k.get("an") or "Claude")
        if not n:
            return False, "Keine Entwürfe zum Senden", None
    text, tid = benachrichtigen(waggon, wurzel, n, namen)
    return True, f"{n} Nachricht(en) gesendet · {text}", tid


def session_starten(waggon):
    tid = akte_lesen(waggon).get("todo_id")
    if not todo_offen(tid):
        return False, "Kein offener todo-Eintrag"
    r = subprocess.run(["todo", "los", tid], capture_output=True, text=True)
    return (True, "Konsole geöffnet – Enter startet Claude") if r.returncode == 0 else \
        (False, f"todo los: {(r.stderr or r.stdout).strip()[:200]}")
