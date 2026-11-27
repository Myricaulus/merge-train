#!/usr/bin/env python3
"""Ende-zu-Ende-Test des GitLab-Modus mit tests/fake-glab (kein echtes GitLab nötig).

Aufruf:  python3 tests/test_gitlab.py [teil …] [--behalten]     (Teile: gitlab lokal horchen arbeitsstand gemischt myrling;
         ohne = alle)
Legt alles in einem Temp-Ordner an (eigene XDG-Ordner, freie Ports, Ersatz für todo und notify-send), baut merge-train
dorthin (oder nimmt MERGE_TRAIN_SKRIPT) und startet eigene Server. Welche Teile bei welcher Änderung laufen: ./testen.
"""
import glob, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
# Teil → Teile, die er voraussetzt (gemischt braucht das Projekt aus lokal und den MR aus gitlab)
TEILE = {"gitlab": [], "lokal": [], "horchen": ["lokal"], "arbeitsstand": [], "gemischt": ["gitlab", "lokal"], "myrling": []}
AUSWAHL = set(TEILE)
def freier_port():
    """Freier Port vom System: feste Ports stoßen mit liegengebliebenen Servern (andere Sessions, abgebrochene Läufe)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT, PORT_LOKAL, PORT_GEMISCHT, PORT_MYRLING = freier_port(), freier_port(), freier_port(), freier_port()  # GitLab-Modus, lokal_test, gemischt_test, myrling_test
T = tempfile.mkdtemp(prefix="merge-train-test-")
# eigener Bau im Repo (tests/bau/, ignoriert), nicht ./merge-train: der Server des Nutzers bleibt unberührt, und der
# HUD-Stand (git log am Ort des Skripts) stimmt trotzdem
SKRIPT = os.environ.get("MERGE_TRAIN_SKRIPT") or os.path.join(HIER, "bau", f"merge-train-{os.getpid()}")
REPO = os.path.join(T, "repo")
BR1, BR2 = "gruppe/demo@feature", "gruppe/demo@zweiter"  # Branches von MR !1 und !2 (Waggon-Kennungen)
AGENT_VARS = ("AI_AGENT", "CLAUDECODE", "CURSOR_AGENT", "GEMINI_CLI", "CODEX_SANDBOX", "OPENCODE", "MERGE_TRAIN_AGENT")
ohne_agent = lambda env: {k: v for k, v in env.items() if k not in AGENT_VARS}  # kein Harness erkennbar
ENV = dict(ohne_agent(os.environ), CLAUDECODE="1", XDG_CONFIG_HOME=f"{T}/config", XDG_CACHE_HOME=f"{T}/cache", XDG_DATA_HOME=f"{T}/data",
           MERGE_TRAIN_CONFIG=f"{T}/config/merge-train/config.toml",
           FAKE_GLAB_REPO=REPO, FAKE_GLAB_STATE=f"{T}/glab", CLAUDE_CONFIG_DIR=f"{T}/claude",
           CLAUDE_CODE_SESSION_ID="sitzung-1",
           PATH=f"{T}/bin:" + os.environ["PATH"], TODO_DIR=f"{T}/todo", TODO_LOG=f"{T}/todo.log")  # todo, notify-send: Ersatz
fehler = []

def seiten_schluessel(html):
    """MR.seite einer gebauten Seite: Schlüssel ihrer Struktur."""
    return json.JSONDecoder().raw_decode(html.split("const MR=", 1)[1])[0]["seite"]


def pruefe(bed, text):
    print(("ok   " if bed else "FEHL ") + text)
    if not bed:
        fehler.append(text)

def sh(*a, cwd=None, check=True, env=None):
    r = subprocess.run(a, cwd=cwd, capture_output=True, text=True, env=env or ENV)
    if check and r.returncode:
        raise SystemExit(f"{a}: {r.stderr}{r.stdout}")
    return r

def repo_anlegen():
    os.makedirs(REPO)
    g = lambda *a: sh("git", "-C", REPO, *a)
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    g("remote", "add", "origin", "git@gitlab.example.com:gruppe/demo.git")
    zeilen = [f"    // Zeile {i}" for i in range(1, 61)]
    zeilen[4] = "    public void Alt() {}"
    zeilen[49] = "    public void WeitWeg() {}"
    open(f"{REPO}/App.cs", "w").write("class App {\n" + "\n".join(zeilen) + "\n}\n")
    open(f"{REPO}/seite.html", "w").write("<p>Hallo</p>\n")
    g("add", "-A"); g("commit", "-qm", "Start")
    g("checkout", "-qb", "feature")
    zeilen[9] = "    public void Neu(int x) { Bar(x); }"
    del zeilen[19]
    open(f"{REPO}/App.cs", "w").write("class App {\n" + "\n".join(zeilen) + "\n}\n")
    open(f"{REPO}/seite.html", "w").write("<p>Hallo Welt</p>\n<p>Bar(x)</p>\n")
    open(f"{REPO}/Neu.cs", "w").write("// neu\nclass Neu { void Bar(int x) {} }\n")
    open(f"{REPO}/Modell.Designer.cs", "w").write("// generiert\nclass Modell {}\n")
    g("add", "-A"); g("commit", "-qm", "Neu und Bar\n\nMit Rumpf.")
    os.makedirs(f"{REPO}/tasks")

def get(pfad):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{pfad}", timeout=60) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        return e.read().decode()

def post(pfad, d):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{pfad}", json.dumps(d).encode(),
                                 {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{PORT}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def drafts():
    try:
        return json.load(open(f"{T}/glab/drafts.json"))
    except FileNotFoundError:
        return []

FAKE_TODO = """#!/bin/sh
# Ersatz für todo: protokolliert, legt bei „neu“ den Eintrag t1 an, „erledigt“ nimmt ihn weg
echo "$*" >> "$TODO_LOG"
case "$1" in
  neu) touch "$TODO_DIR/offen/t1.md"; echo t1;;
  erledigt) rm -f "$TODO_DIR/offen/$2.md";;
esac
"""

# Alle Namen aller Module in einem Wörterbuch (die Tests rufen einzelne Funktionen direkt auf)
ALLES_LADEN = r"""
def alles_laden(skript):
    import importlib, pkgutil, sys
    sys.path.insert(0, skript)
    import merge_train
    m = {}
    for info in pkgutil.iter_modules(merge_train.__path__):
        m.update(vars(importlib.import_module("merge_train." + info.name)))
    return m
"""
exec(ALLES_LADEN)

ARBEIT_PRUEFEN = ALLES_LADEN + r"""
import json, os, subprocess, sys
def thread_pruefen(m, w):
    g = m["projekt_waggon"](w)
    fid, _ = m["faden_anlegen"]([g], "Unklar: a.py:1 und `neu.py` – fehlt.py nicht", "a.py:1",
                            [{"path": "neu.py", "line": 1, "label": "neu"}, {"path": "neu.py", "diff": "a.py"}])
    allg, _ = m["faden_anlegen"]([g], "Zusammenfassung", None)
    fehler = []
    for args in (("x", "gibtsnicht.py:1"), ("x", "a.py:99"), ("x", None, ["gibtsnicht.py"])):
        try:
            m["faden_anlegen"]([g], *args); fehler.append(False)
        except m["Fehler"]:
            fehler.append(True)
    d = m["gespraech_daten"](g)
    k = {x["id"]: x for x in d["kommentare"]}
    text, n = m["faeden_abholen"]([g], markieren=False)
    return {"faden": k.get(fid), "allg": k.get(allg), "fehler": fehler, "abholen": n}
m = alles_laden(sys.argv[1])
w = sys.argv[2]
g = lambda *a: subprocess.run(["git", "-C", w, *a], capture_output=True, text=True).stdout
vorher = (g("status", "--porcelain"), g("diff", "--cached", "--name-only"), g("rev-parse", "HEAD"))
s1 = m["arbeitsstand"](w); s2 = m["arbeitsstand"](w)
m["_ARBEIT"].clear(); s3 = m["arbeitsstand"](w)  # ohne Zwischenspeicher: gleicher Inhalt, gleicher sha
nachher = (g("status", "--porcelain"), g("diff", "--cached", "--name-only"), g("rev-parse", "HEAD"))
st = m["statistik"](w)
pfad, struktur = m["branch_seite"](m["projekt_waggon"](w))
print(json.dumps({"s1": s1, "s2": s2, "s3": s3, "unveraendert": vorher == nachher, "head": vorher[2].strip(),
                  "baum": g("ls-tree", "-r", "--name-only", s1).split(), "inhalt": g("show", s1 + ":a.py"),
                  "stat": st, "fertig": m["fertig_moeglich"](m["projektname"](w)), "dateien": [d["neu"] for d in struktur["dateien"]],
                  "seite": os.path.exists(pfad), "titel": open(pfad, encoding="utf-8").read().split("<h1>")[1].split("</h1>")[0],
                  **thread_pruefen(m, w)}))
"""

def arbeitsstand_test():
    """bis = "arbeitsstand": Arbeitsverzeichnis (auch nicht committet) gegen von, ohne Index/Branch anzufassen."""
    w = f"{T}/Arbeit/klon"
    os.makedirs(w)
    g = lambda *a: sh("git", "-C", w, *a).stdout.strip()
    g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    open(f"{w}/a.py", "w").write("a = 1\n"); open(f"{w}/weg.py", "w").write("w = 1\n")
    g("add", "-A"); g("commit", "-qm", "Start")
    g("checkout", "-qb", "feature/x")
    open(f"{w}/a.py", "w").write("a = 2\n")             # geändert, nicht committet
    open(f"{w}/neu.py", "w").write("n = 1\n")            # neu, nicht hinzugefügt
    os.remove(f"{w}/weg.py")                              # gelöscht
    open(f"{w}/.gitignore", "w").write("*.log\n"); open(f"{w}/x.log", "w").write("ignoriert\n")
    konf = f"{T}/config/merge-train/arbeit.toml"
    open(konf, "w").write(f'lokal = true\ngitlab = false\nprojekte = ["{T}/Arbeit/klon"]\nvon = "main"\nbis = "arbeitsstand"\n')
    env = dict(ENV, MERGE_TRAIN_CONFIG=konf, XDG_CACHE_HOME=f"{T}/cache-arbeit")
    r = subprocess.run([sys.executable, "-c", ARBEIT_PRUEFEN, SKRIPT, w], capture_output=True, text=True, env=env)
    try:
        d = json.loads(r.stdout)
    except ValueError:
        pruefe(False, "Arbeitsstand: " + (r.stderr.strip().splitlines() or ["?"])[-1]); return
    pruefe(d["s1"] == d["s2"] == d["s3"] and d["s1"] != d["head"], "Arbeitsstand: eigener Commit, gleicher Inhalt → gleicher sha")
    pruefe(d["unveraendert"], "Arbeitsstand: Index, Arbeitsverzeichnis und Branch unverändert")
    pruefe(sorted(d["baum"]) == [".gitignore", "a.py", "neu.py"] and d["inhalt"] == "a = 2\n",
           "Arbeitsstand: geänderte, neue und gelöschte Dateien, ignorierte nicht")
    pruefe(d["stat"]["dateien"] == 4 and d["stat"]["sha"] == d["s1"] and sorted(d["dateien"]) == [".gitignore", "a.py", "neu.py", "weg.py"]
           and d["seite"], "Arbeitsstand: Waggon-Statistik und Diff-Seite gegen von")
    pruefe(d["fertig"] is False, "Arbeitsstand: „fertig“ ist aus (würde von verschieben)")
    pruefe(d["titel"] == "klon: Arbeitsstand feature/x → main", "Arbeitsstand: Titel „Arbeitsstand <branch>“ – " + d["titel"])
    f, a = d["faden"] or {}, d["allg"] or {}
    pruefe(f.get("path") == "a.py" and f.get("b") == 1 and f.get("vom_agenten") and f.get("status") == "antwort"
           and a.get("path") is None and a.get("status") == "antwort", "agent thread: an der Zeile und allgemein, wartet auf den Nutzer")
    pruefe(sorted((l["t"], l["path"], l["zeile"]) for l in f.get("links") or []) == [("a.py:1", "a.py", 1), ("neu.py", "neu.py", None)],
           "agent thread: Code-Verweise im Text werden Links (unbekannte Dateien nicht)")
    pruefe([(x["path"], x["zeile"], x["vergleich"], x["problem"]) for x in f.get("see_also") or []] == [("neu.py", 1, None, None), ("neu.py", None, "a.py", None)],
           "agent thread: siehe auch und Vergleich")
    pruefe(d["fehler"] == [True, True, True] and d["abholen"] == 0, "agent thread: falsche Orte abgelehnt, nichts für den Agenten offen")
    g("add", "-A"); g("commit", "-qm", "alles")
    r = subprocess.run([sys.executable, "-c", ALLES_LADEN + "import sys; m=alles_laden(sys.argv[1]); "
                        "print(open(m['branch_seite'](m['projekt_waggon'](sys.argv[2]))[0],encoding='utf-8').read().split('<h1>')[1].split('</h1>')[0])",
                        SKRIPT, w], capture_output=True, text=True, env=env)
    pruefe(r.stdout.strip() == "klon: HEAD feature/x → main", "Arbeitsstand: ohne offene Änderungen „HEAD <branch>“ – " + r.stdout.strip() + r.stderr[-300:])

def lokal_test():
    """Lokaler Projekt-Diff (claude gegen reviewed): gleiche Seite wie im GitLab-Modus, ohne glab."""
    proj = f"{T}/Projects/proj"
    os.makedirs(proj)
    g = lambda *a: sh("git", "-C", proj, *a).stdout.strip()
    g("init", "-q", "-b", "reviewed"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    open(f"{proj}/a.py", "w").write("".join(f"x{i} = {i}\n" for i in range(1, 41)))
    g("add", "-A"); g("commit", "-qm", "Start")
    g("checkout", "-qb", "claude")
    open(f"{proj}/a.py", "w").write("".join(f"x{i} = {i * 2 if i == 20 else i}\n" for i in range(1, 41)))
    open(f"{proj}/b.Designer.cs", "w").write("// generiert\n")
    g("add", "-A"); g("commit", "-qm", "Erster Schritt todo:demo")
    c1 = g("rev-parse", "HEAD")
    open(f"{proj}/a.py", "a").write("y = 1\n")
    g("commit", "-qam", "Zweiter Schritt")
    env = dict(ENV, MERGE_TRAIN_CONFIG=f"{T}/config/merge-train/lokal.toml", XDG_CACHE_HOME=f"{T}/cache-lokal")
    open(env["MERGE_TRAIN_CONFIG"], "w").write(f'lokal = true\ngitlab = false\nprojekte = "{T}/Projects"\nport = {PORT_LOKAL}\nbrowser = "true"\n')
    srv = subprocess.Popen([sys.executable, SKRIPT, "--server"], env=env)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT_LOKAL}/ping", timeout=1); break
            except OSError:
                time.sleep(0.1)
        hol = lambda p: urllib.request.urlopen(f"http://127.0.0.1:{PORT_LOKAL}{p}", timeout=60).read().decode()
        seite = hol("/proj.html")
        k = open(f"{T}/cache-lokal/merge-train/schluessel").read().strip()
        pruefe('class="lu" data-von="1" data-bis="16"' in seite and "generierte Datei" in seite and f"?commit={c1}" in seite
               and f"?seit={c1}" in seite and "todo" in seite, "lokal: Lücken, große Dateien später, Commit-Knöpfe")
        z = json.loads(hol(f"/api/zeilen?mr=projekt:proj&k={k}&pfad=a.py&von=1&bis=99"))
        pruefe(z["ok"] and z["n"] == 41, "lokal: Kontext nachladen")
        d = json.loads(hol(f"/api/datei?mr=projekt:proj&k={k}&i=1"))
        pruefe(d["ok"] and "generiert" in d["html"], "lokal: große/generierte Datei nachladen")
        s1 = hol(f"/proj.html?commit={c1}")
        pruefe('id="ansicht"' in s1 and "Erster Schritt" in s1 and 'id="d1"' in s1 and 'data-b="41"' not in s1, "lokal: Einzel-Commit-Ansicht")
        z = json.loads(hol(f"/api/zeilen?mr=projekt:proj&k={k}&pfad=a.py&von=1&bis=99&ansicht=commit:{c1}"))
        pruefe(z["ok"] and z["n"] == 40, "lokal: Kontext in der Commit-Ansicht aus dem Commit-Stand")
        s2 = hol(f"/proj.html?seit={c1}")
        pruefe('id="ansicht"' in s2 and 'id="d1"' not in s2 and 'data-b="41"' in s2 and 'data-b="20"' not in s2,
               "lokal: Seit-Ansicht zeigt nur den zweiten Schritt")
        gespraech_test(proj, env, k, hol, g)
        if "horchen" in AUSWAHL:
            horchen_waise_test(proj, env, k, hol)
            horchen_seite_zu_test(proj, env, k, hol)
            horchen_abmelden_test(proj, env, k, hol)
    finally:
        srv.terminate(); srv.wait()

def gespraech_test(proj, env, k, hol, g):
    """Gespräch im lokalen Modus: Frage an einer Zeile → Feedback senden → Agent holt ab und antwortet."""
    port = PORT_LOKAL
    def post_l(pfad, d):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{pfad}", json.dumps(d).encode(),
                                     {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    agent = lambda *a, **kw: subprocess.run([sys.executable, SKRIPT, "agent", *a], cwd=proj, env=env, capture_output=True,
                                            text=True, **kw)
    head = g("rev-parse", "claude")
    seite = hol("/proj.html")
    pruefe('id="feedback"' in seite and 'id="kliste"' in seite and 'class="diffseite"' in seite and 'id="fertig"' in seite
           and 'id="abschliessen"' not in seite, "Gespräch: Knöpfe und Kommentarliste auf der Seite (fertig, kein Review)")
    basis = {"mr": "projekt:proj", "k": k, "sha": head}
    r = post_l("/api/kommentar", dict(basis, aktion="neu", datei=0, a=None, b=20, text="Warum mal zwei?"))
    pruefe(r["ok"] and r["review"]["faeden"][0]["status"] == "entwurf" and r["review"]["g_ausstehend"] == 1, "Gespräch: Frage an Zeile 20 als Entwurf")
    fid = r["review"]["faeden"][0]["id"]
    pruefe(not post_l("/api/kommentar", dict(basis, aktion="neu", datei=0, a=5, b=6, text="x"))["ok"], "Gespräch: unstimmige Zeile abgelehnt")
    post_l("/api/kommentar", dict(basis, aktion="neu", text="Allgemein: sieht gut aus?"))
    r = agent("feedback")
    pruefe("(nichts offen)" in r.stdout, "Gespräch: Entwürfe sieht der Agent noch nicht")
    r = post_l("/api/gespraech", dict(basis, aktion="senden"))
    log = open(env["TODO_LOG"]).read()
    pruefe(r["ok"] and "2 Nachricht(en) gesendet" in r["text"] and "als todo eingetragen" in r["text"] and r["todo"] == "t1",
           "Gespräch: Feedback senden → todo-Eintrag, weil niemand zuhört")
    pruefe("neu merge-train: Fragen/Feedback zu proj" in log and "heute t1" in log and "--prompt" in log, "Gespräch: todo neu + heute mit Prompt")
    r = agent("feedback")
    pruefe(f"[{fid}] a.py:20" in r.stdout and "x20 = 40" in r.stdout and "Nutzer (" in r.stdout and "Warum mal zwei?" in r.stdout
           and "allgemein" in r.stdout and "2 Gespräch(e) warten" in r.stdout, "Gespräch: agent feedback zeigt Ort, Code und Verlauf")
    rv = json.loads(hol(f"/api/review?mr=projekt:proj&k={k}"))
    f1 = next(x for x in rv["faeden"] if x["id"] == fid)
    pruefe(f1["status"] == "wartet" and f1["nachrichten"][0]["abgeholt"], "Gespräch: abgeholt (✓✓) auf der Seite")
    r = agent("antworten", fid[:6], "Weil der Test das so will.")
    pruefe(r.returncode == 0 and "1 weitere(r) wartet" in r.stdout, "Gespräch: agent antworten (Anfang der id genügt)")
    rv = json.loads(hol(f"/api/review?mr=projekt:proj&k={k}"))
    f1 = next(x for x in rv["faeden"] if x["id"] == fid)
    pruefe(f1["status"] == "antwort" and f1["nachrichten"][-1]["von"] == "claude", "Gespräch: Antwort auf der Seite")
    zug = hol("/zug.js")
    pruefe('"gs_neu": 1' in zug, "Gespräch: Zug zeigt neue Antwort")
    r = subprocess.run([sys.executable, SKRIPT, "status"], cwd=proj, env=env, capture_output=True, text=True)
    allg = next(x["id"] for x in rv["faeden"] if not x["path"])
    pruefe(r.returncode == 0 and "Branch claude" in r.stdout and "gegen reviewed" in r.stdout and f"[{fid}] a.py:20 · offen" in r.stdout
           and f"[{allg}] allgemein · WARTET AUF DICH" in r.stdout and "1 warten auf dich" in r.stdout
           and "Erwartet:" in r.stdout and f"agent antworten {allg}" in r.stdout and "--vergleich" in r.stdout
           and r.stdout.index("1 warten auf dich") < r.stdout.index("Erwartet:") < r.stdout.index("Offene Fäden"),
           "merge-train status: Branch, Änderungen, was zu tun ist (Zusammenfassung an den offenen allgemeinen), Fäden zuletzt")
    r = agent("antworten", fid, "--siehe", "a.py:1-2|Anfang", "--vergleich", "a.py:1-2", "a.py:3-4", "Mit Links.")
    rv = json.loads(hol(f"/api/review?mr=projekt:proj&k={k}"))
    sa = next(x for x in rv["faeden"] if x["id"] == fid)["see_also"]
    pruefe(r.returncode == 0 and len(sa) == 2 and agent("antworten", fid, "--siehe", "fehlt.py", "x").returncode != 0,
           "agent antworten --siehe/--vergleich: hängt Links an den Faden, prüft sie")
    # Rückfrage des Nutzers, Agent hört zu
    post_l("/api/kommentar", dict(basis, aktion="antworten", id=fid, text="Und warum nicht drei?"))
    lauscher = subprocess.Popen([sys.executable, SKRIPT, "agent", "horchen", "--timeout", "30"], cwd=proj, env=env,
                                stdout=subprocess.PIPE, text=True)
    for _ in range(50):
        if json.loads(hol(f"/api/review?mr=projekt:proj&k={k}")).get("horcht"):
            break
        time.sleep(0.1)
    r = post_l("/api/gespraech", dict(basis, aktion="senden"))
    pruefe(r["ok"] and "zuhört" in r["text"] and r["todo"] is None, "Gespräch: Session hört zu → kein neuer todo-Eintrag")
    aus, _ = lauscher.communicate(timeout=30)
    pruefe(lauscher.returncode == 0 and "Und warum nicht drei?" in aus and "Weil der Test" in aus, "Gespräch: horchen gibt neue Nachricht samt Verlauf aus")
    # Nutzer schiebt etwas nach, während der Agent antwortet: antworten lehnt ab, feedback zeigt es
    post_l("/api/kommentar", dict(basis, aktion="antworten", id=fid, text="Nachtrag"))
    post_l("/api/gespraech", dict(basis, aktion="senden"))
    r = agent("antworten", fid, "Blind")
    pruefe(r.returncode == 2 and "Nachtrag" in r.stderr, "Gespräch: antworten lehnt ab, wenn Ungelesenes im Faden liegt")
    r = agent("feedback")
    pruefe("Nachtrag" in r.stdout and "Blind" not in r.stdout, "Gespräch: feedback zeigt den Nachtrag")
    allg = next(x for x in rv["faeden"] if x["id"] != fid)["id"]
    agent("antworten", allg, "Ja.", "--erledigt")
    r = agent("antworten", fid, "Drei wäre zu viel.", "--erledigt")
    pruefe("nichts mehr offen" in r.stdout and "erledigt t1" in open(env["TODO_LOG"]).read(), "Gespräch: alles beantwortet → todo abgehakt")
    # neuer Commit: Zeile wandert mit
    alte_seite = seiten_schluessel(hol("/proj.html"))
    alt = open(f"{proj}/a.py").read()
    open(f"{proj}/a.py", "w").write("# Kopf\n# noch einer\n" + alt)
    g("commit", "-qam", "Kopfzeilen")
    neue_seite = seiten_schluessel(hol("/proj.html"))  # Seite zum neuen Stand; Fäden auf den Stand der Seite umgerechnet
    rv = json.loads(hol(f"/api/review?mr=projekt:proj&k={k}&seite={urllib.parse.quote(neue_seite)}"))
    f1 = next(x for x in rv["faeden"] if x["id"] == fid)
    pruefe(f1["b"] == 22 and f1["im_diff"], "Gespräch: nach neuem Commit steht der Faden an Zeile 22")
    rv = json.loads(hol(f"/api/review?mr=projekt:proj&k={k}&seite={urllib.parse.quote(alte_seite)}"))
    stand_alt, stand_neu = (json.loads(hol(f"/api/stand?mr=projekt:proj&k={k}&seite={urllib.parse.quote(s)}"))
                            for s in (alte_seite, neue_seite))
    pruefe(next(x for x in rv["faeden"] if x["id"] == fid)["b"] == 20 and stand_alt["veraltet"]
           and not stand_neu["veraltet"] and not json.loads(hol(f"/api/review?mr=projekt:proj&k={k}&seite=../x.json"))["ok"],
           "Seite mit Schlüssel: die alte rechnet gegen ihren eigenen Stand (Zeile 20) und ist veraltet, die neue nicht; "
           "fremder Schlüssel abgelehnt")
    d = json.loads(hol(f"/api/diff?mr=projekt:proj&k={k}&seite={urllib.parse.quote(alte_seite)}"))
    a_py = next((x for x in d.get("dateien", []) if 'data-pfad="a.py"' in (x["html"] or "")), None)
    pruefe(d["ok"] and not d["gleich"] and d["mr"]["seite"] == neue_seite and a_py and d["zeilen"].get("a.py") == [[1, 2]]
           and all(x["html"] is None for x in d["dateien"] if x is not a_py) and 'data-schluessel="' in a_py["html"]
           and "Stand" in d["titel"] and json.loads(hol(f"/api/diff?mr=projekt:proj&k={k}&seite={urllib.parse.quote(neue_seite)}"))["gleich"],
           "api/diff: von der alten Seite nur die geänderte Datei (samt Schlüssel), MR, Kopf und die neuen Zeilen; "
           "von der neuen: gleich")
    haken = f"{proj}/.git/hooks/pre-push"  # fertig = git push . claude:reviewed: ein scheiternder Hook ändert nichts
    open(haken, "w").write("#!/bin/sh\necho 'Test rot' >&2\nexit 1\n"); os.chmod(haken, 0o755)
    reviewed = g("rev-parse", "reviewed")
    try:
        post_l("/fertig", {"projekt": "proj", "sha": g("rev-parse", "claude"), "k": k})
        r = {"ok": True}
    except urllib.error.HTTPError as e:
        r = json.loads(e.read())
    pruefe(not r["ok"] and "Test rot" in r["text"] and g("rev-parse", "reviewed") == reviewed,
           "fertig: pre-push-Hook scheitert → Meldung mit seiner Ausgabe, reviewed unverändert")
    os.remove(haken)
    r = post_l("/fertig", {"projekt": "proj", "sha": g("rev-parse", "claude"), "k": k})
    rv = json.loads(hol(f"/api/review?mr=projekt:proj&k={k}"))
    pruefe(r["ok"] and not rv["faeden"], "Gespräch: fertig räumt erledigte Fäden weg")

def horchen_waise_test(proj, env, k, hol):
    """Endet die Agenten-Session, hört horchen auf, und die Seite zeigt niemanden mehr als Zuhörer."""
    os.symlink("/bin/sh", f"{T}/bin/agentx")  # ein „Agent“ mit eigenem Prozessnamen
    os.makedirs(f"{T}/claude/projects/-proj")  # Transcript der Session: letzte Antwort mit 50k Tokens im Kontext
    with open(f"{T}/claude/projects/-proj/sitzung-1.jsonl", "w") as f:
        f.write(json.dumps({"type": "assistant", "isSidechain": False, "message": {"model": "m", "usage": {
            "input_tokens": 2, "cache_creation_input_tokens": 8000, "cache_read_input_tokens": 41998}}}) + "\n")
        f.write(json.dumps({"type": "assistant", "isSidechain": True, "message": {"usage": {"input_tokens": 9}}}) + "\n")
    ag = subprocess.Popen([f"{T}/bin/agentx", "-c", f'"{sys.executable}" "{SKRIPT}" agent horchen --als Fake; true'], cwd=proj, env=env)
    wer = None
    for _ in range(50):
        wer = json.loads(hol(f"/api/review?mr=projekt:proj&k={k}")).get("horcht")
        if wer == "Fake":
            break
        time.sleep(0.1)
    pruefe(wer == "Fake", "horchen: Seite zeigt den Zuhörer")
    kx = json.loads(hol(f"/api/review?mr=projekt:proj&k={k}")).get("kontext") or {}
    pruefe(kx.get("tokens") == 50000 and kx.get("prozent") == 25 and kx.get("name") == "Fake" and kx.get("schwellen") == [15, 20, 25, 35],
           f"horchen: HUD bekommt den Kontext-Füllstand der Session aus dem Transcript ({kx})")
    datei = f"{T}/data/merge-train/zweige/proj/claude.horcht"
    ag.kill(); ag.wait()  # Session hart beendet: horchen ist jetzt verwaist
    for _ in range(50):
        if not os.path.exists(datei):
            break
        time.sleep(0.1)
    pruefe(not os.path.exists(datei), "horchen: beendet sich, wenn die Agenten-Session weg ist")
    danach = json.loads(hol(f"/api/review?mr=projekt:proj&k={k}"))
    pruefe(danach.get("horcht") is None, "horchen: Seite zeigt danach niemanden")
    pruefe(danach.get("kontext") is None, "horchen: und keinen Kontext-Füllstand mehr")

def still_horchen(proj, env, aus):
    """horchen unter dem Fake-Agenten (agentx aus horchen_waise_test), Ausgabe in die Datei aus."""
    return subprocess.Popen([f"{T}/bin/agentx", "-c", f'"{sys.executable}" "{SKRIPT}" agent horchen --als Fake > "{aus}"; true'],
                            cwd=proj, env=env)

def warten_bis(bedingung, n=60):
    for _ in range(n):
        if bedingung():
            return True
        time.sleep(0.1)
    return False

def horchen_seite_zu_test(proj, env, k, hol):
    """Wird die Seite geschlossen (kein Lebenszeichen mehr), hört horchen auf – aber erst, wenn sie nach dem Start da war –,
    und zwar still: kein Wort und kein Ende (das weckte den Agenten), der Waggon zeigt niemanden mehr."""
    datei, aus = f"{T}/data/merge-train/zweige/proj/claude.horcht", f"{T}/still-seite.out"
    ag = still_horchen(proj, dict(env, MERGE_TRAIN_SEITE_WEG_S="2"), aus)
    time.sleep(3)
    pruefe(os.path.exists(datei), "horchen: ohne Seite seit dem Start hört es weiter zu")
    hol(f"/api/stand?mr=projekt:proj&k={k}")  # Seite meldet sich einmal, dann nicht mehr
    pruefe(warten_bis(lambda: not os.path.exists(datei)), "horchen: hört auf, wenn die Seite kein Lebenszeichen mehr schickt")
    time.sleep(1)
    pruefe(ag.poll() is None and open(aus).read() == "", "horchen: danach stumm, endet nicht (weckt den Agenten nicht)")
    ag.kill(); ag.wait()

def horchen_abmelden_test(proj, env, k, hol):
    """„🎧 ✕“ auf der Seite: der Zuhörer ist weg, horchen merkt es und bleibt stumm, bis die Session endet."""
    aus = f"{T}/still-abmelden.out"
    ag = still_horchen(proj, env, aus)
    pruefe(warten_bis(lambda: json.loads(hol(f"/api/review?mr=projekt:proj&k={k}")).get("horcht") == "Fake"),
           "abmelden: Seite zeigt erst den Zuhörer")
    port = PORT_LOKAL
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/gespraech",
                                 json.dumps({"mr": "projekt:proj", "k": k, "aktion": "abmelden"}).encode(),
                                 {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"})
    r = json.loads(urllib.request.urlopen(req, timeout=60).read())
    pruefe(r["ok"] and "Fake hört nicht mehr zu" in r["text"] and r["review"].get("horcht") is None,
           "abmelden: Seite zeigt danach niemanden")
    time.sleep(2)
    pruefe(ag.poll() is None and open(aus).read() == "", "abmelden: horchen bleibt stumm und endet nicht")
    ag.kill(); ag.wait()
    pruefe(warten_bis(lambda: "horchen" not in subprocess.run(["pgrep", "-af", "agent horchen --als Fake"],
                                                              capture_output=True, text=True).stdout, 60),
           "abmelden: endet die Session, endet auch das stumme horchen")

def gemischt_test(mr):
    """Beide Quellen an: ein Zug mit lokalen Waggons und MRs, jede Seite mit den Knöpfen ihrer Quelle."""
    env = dict(ENV, MERGE_TRAIN_CONFIG=f"{T}/config/merge-train/gemischt.toml")
    open(env["MERGE_TRAIN_CONFIG"], "w").write(
        f'lokal = true\ngitlab = true\nglab = "{sys.executable} {HIER}/fake-glab"\nprojekte = "{T}/Projects"\n'
        f'port = {PORT_GEMISCHT}\nbrowser = "true"\n')
    srv = gemischt_server(env)
    try:
        hol = lambda p: urllib.request.urlopen(f"http://127.0.0.1:{PORT_GEMISCHT}{p}", timeout=60).read().decode()
        # neuer lokaler Stand, damit der lokale Waggon wieder offen ist
        proj = f"{T}/Projects/proj"
        open(f"{proj}/c.py", "w").write("neu = 1\n")
        sh("git", "-C", proj, "add", "-A"); sh("git", "-C", proj, "commit", "-qm", "Dritter Schritt")
        zug = hol("/zug.js?akt=" + urllib.parse.quote(mr))
        z = json.loads(zug[len("window.MR_ZUG="):-1])
        quellen = {w["quelle"]: w for w in z["wagen"]}
        pruefe(set(quellen) == {"lokal", "gitlab"} and quellen["lokal"]["p"] == "proj@claude" and quellen["gitlab"]["p"] == BR1,
               "gemischt: ein Zug mit lokalem Waggon und MR")
        pruefe([w["quelle"] for w in z["wagen"]][0] == "lokal", "gemischt: lokale Waggons vorn")
        ms = hol("/mr/" + mr)
        pruefe('id="abschliessen"' in ms and 'id="fertig"' not in ms and 'data-l="neu"' in ms and 'data-g="mrliste"' in ms,
               "gemischt: MR-Seite mit Review-Knopf, Leitstand beider Quellen")
        ls_ = hol("/proj.html")
        pruefe('id="fertig"' in ls_ and 'id="abschliessen"' not in ls_ and 'data-g="mrliste"' in ls_, "gemischt: lokale Seite mit fertig")
        start = urllib.request.urlopen(f"http://127.0.0.1:{PORT_GEMISCHT}/", timeout=60)
        pruefe(start.geturl().endswith("/b/proj@claude"), "gemischt: Start springt zum offenen Waggon eines Projekts")
        # Klon eines fremden MR, zugleich lokales Projekt, Quell-Branch ausgecheckt: status zeigt das Review, thread geht zum MR
        env2 = dict(env, MERGE_TRAIN_CONFIG=f"{T}/config/merge-train/gemischt-klon.toml")
        open(env2["MERGE_TRAIN_CONFIG"], "w").write(open(env["MERGE_TRAIN_CONFIG"]).read().replace(
            f'projekte = "{T}/Projects"', f'projekte = ["{T}/Projects/proj", "{REPO}"]') + '\n[zweige.repo]\nvon = "main"\nbis = "arbeitsstand"\n')
        r = subprocess.run([sys.executable, SKRIPT, "status"], cwd=REPO, env=env2, capture_output=True, text=True)
        pruefe(r.returncode == 0 and "Review MR gruppe/demo!1" in r.stdout and f"thread -p {BR1}" in r.stdout
               and "Erwartet:" not in r.stdout, "status im Klon auf dem Quell-Branch eines fremden MR: Review statt Entwicklung")
    finally:
        srv.terminate(); srv.wait()
    fremd_test(mr, env2, hol)
    eigen_test(mr, env2, hol)
    mr_erstellen_test(env2, hol)
    branch_akte_test(env2)


def gemischt_server(env):
    """Eigener Server auf PORT_GEMISCHT (die Einstellung liest er nur beim Start), wartet, bis er antwortet."""
    srv = subprocess.Popen([sys.executable, SKRIPT, "--server"], env=env)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT_GEMISCHT}/ping", timeout=1); break
        except OSError:
            time.sleep(0.1)
    return srv


def mr_erstellen_test(env2, hol):
    """Branch ohne MR (docs/ein-waggon.md, Schritt 2): Knopf „MR erstellen“ auf der lokalen Seite, Vorschlag für die
    Rückfrage, pushen und anlegen, danach ein Waggon mit dem MR; ein zweites Mal wird der vorhandene übernommen."""
    srv = gemischt_server(env2)
    k = open(f"{T}/cache/merge-train/schluessel").read().strip()
    origin = f"{T}/origin.git"
    g = lambda *a: sh("git", "-C", REPO, *a)
    def post_l(d):
        req = urllib.request.Request(f"http://127.0.0.1:{PORT_GEMISCHT}/api/gitlab", json.dumps(dict(d, k=k)).encode(),
                                     {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{PORT_GEMISCHT}"})
        try:
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except urllib.error.HTTPError as e:
            return dict(json.loads(e.read()), status=e.code)
    try:
        sh("git", "init", "-q", "--bare", origin)
        g("config", "remote.origin.pushurl", origin)
        g("push", "-q", "origin", "main")  # setzt origin/main im Klon
        g("checkout", "-qb", "zweiter", "feature")
        open(f"{REPO}/Zwei.cs", "w").write("class Zwei {}\n")
        g("add", "Zwei.cs"); g("commit", "-qm", "Zweiter Schritt")
        seite = hol("/repo.html")
        pruefe('id="mrerstellen"' in seite, "MR erstellen: Knopf auf der Seite des lokalen Waggons")
        r = post_l({"aktion": "mrplanen", "mr": "projekt:repo"})
        v = r.get("vorschlag") or {}
        pruefe(r.get("ok") and v.get("quelle") == "zweiter" and v.get("ziel") == "main" and v.get("push") == "neu"
               and not v.get("hindernisse") and v.get("commits", 0) >= 2, "MR erstellen: Vorschlag für die Rückfrage" + ("" if v else f" – {r}"))
        r = post_l({"aktion": "mrplanen", "mr": "gitlab.example.com/gruppe/demo/1"})
        pruefe(r.get("status") == 400, "MR erstellen: nur auf der Seite eines lokalen Waggons")
        r = post_l({"aktion": "mrerstellen", "mr": "projekt:repo", "ziel": "main", "titel": "  Zweiter   MR ",
                    "beschreibung": "Text", "entwurf": True})
        erstellt = json.load(open(f"{T}/glab/erstellt.json")) if os.path.exists(f"{T}/glab/erstellt.json") else []
        pruefe(r.get("ok") and r.get("url") == "/b/" + BR2 and erstellt
               and erstellt[0]["title"] == "Draft: Zweiter MR" and erstellt[0]["source_branch"] == "zweiter"
               and erstellt[0]["target_branch"] == "main", "MR erstellen: angelegt (Entwurf, Titel bereinigt)" + ("" if r.get("ok") else f" – {r}"))
        pruefe(sh("git", "-C", origin, "rev-parse", "zweiter").stdout == g("rev-parse", "zweiter").stdout
               and g("rev-parse", "--abbrev-ref", "zweiter@{upstream}").stdout.strip() == "origin/zweiter",
               "MR erstellen: Branch neu gepusht, mit Upstream")
        z = json.loads(hol("/zug.js?akt=projekt:repo")[len("window.MR_ZUG="):-1])
        w = next((w for w in z["wagen"] if w["p"] == BR2), {})
        pruefe(sum(x["p"] == BR2 for x in z["wagen"]) == 1 and "eigener MR" in w.get("titel", ""),
               "MR erstellen: danach ein Waggon (eigener MR, ausgecheckt)")
        ap2 = f"{T}/data/merge-train/zweige/gruppe%2Fdemo/zweiter.json"  # MR in GitLab, merge-train kennt ihn noch nicht
        akte2 = json.load(open(ap2)); akte2.pop("gitlab"); akte2.pop("meta"); json.dump(akte2, open(ap2, "w"))
        r = post_l({"aktion": "mrplanen", "mr": "projekt:repo"})
        pruefe(r.get("ok") and "gibt es schon" in r.get("text", "") and r.get("url") == "/b/" + BR2,
               "MR erstellen: vorhandener MR wird übernommen statt doppelt angelegt" + ("" if r.get("ok") else f" – {r}"))
    finally:
        srv.terminate(); srv.wait()
        g("checkout", "-q", "feature"); g("branch", "-qD", "zweiter")
        g("config", "--unset", "remote.origin.pushurl")
        for ref in ("refs/remotes/origin/main", "refs/remotes/origin/zweiter"):
            sh("git", "-C", REPO, "update-ref", "-d", ref, check=False)
        for p in (f"{T}/glab/erstellt.json", f"{T}/data/merge-train/zweige/gruppe%2Fdemo/zweiter.json"):
            if os.path.exists(p):
                os.remove(p)


BRANCH_AKTE = ALLES_LADEN + r"""
import json, os, subprocess, sys
m = alles_laden(sys.argv[1]); repo = sys.argv[2]
D = m["DATEN"]
W = m["Waggon"](repo="gruppe/demo", branch="feature")
lies = lambda p: json.load(open(os.path.join(D, p)))
faden = lambda i, b=None: dict({"id": i, "nachrichten": [{"id": "n" + i, "von": "ich", "text": i, "zeit": "2026-11-27T00:00:00",
                                                          "gesendet": "2026-11-27T00:00:00", "abgeholt": "2026-11-27T00:00:00"}]},
                               **({"branch": b} if b else {}))
for o in ("lokal", "reviews", "zweige/repo"):
    os.makedirs(os.path.join(D, o))
json.dump({"mr": {"lokal": "repo"}, "struktur": "/lokal.json", "kommentare": [faden("f1", "feature"), faden("f2", "weg"), faden("f3")]},
          open(D + "/lokal/repo.json", "w"))
json.dump({"mr": {"lokal": "repo"}, "kommentare": [faden("f5", "alt")]}, open(D + "/zweige/repo/alt.json", "w"))
json.dump({"verweis": "reviews/gitlab.example.com_gruppe_demo_1.json"}, open(D + "/zweige/repo/feature.json", "w"))
json.dump({"mr": {"host": "gitlab.example.com", "projekt": "gruppe/demo", "iid": 1, "source_branch": "feature",
                  "web_url": "https://gitlab.example.com/gruppe/demo/-/merge_requests/1"},
           "meta": {"source_branch": "feature", "target_branch": "main", "state": "opened"},
           "kommentare": [{"id": "k1", "text": "Review"}, faden("f9", "feature")]},
          open(D + "/reviews/gitlab.example.com_gruppe_demo_1.json", "w"))
json.dump({"mr": {"host": "gitlab.example.com", "projekt": "gruppe/demo", "iid": 5}, "hinweis_dateien": ["/x.json"]},
          open(D + "/reviews/gitlab.example.com_gruppe_demo_5.json", "w"))
out = {}
a = m["akte_lesen"](W)
out["migriert"] = (sorted(k["id"] for k in a["kommentare"]), (a.get("gitlab") or {}).get("iid"), lies("lokal/repo.json"),
                   [k["id"] for k in lies("zweige/gruppe%2Fdemo/weg.json")["kommentare"]],
                   [k["id"] for k in lies("zweige/gruppe%2Fdemo/alt.json")["kommentare"]],
                   sorted(os.listdir(D + "/reviews")), os.path.isdir(D + "/zweige/repo"),
                   os.path.exists(D + "/vor-schritt-5/reviews/gitlab.example.com_gruppe_demo_1.json"))
out["fremd"] = sorted(k["id"] for p in m["andere_zweig_akten"](W) for k in m["faeden_von"](m["akte_lesen"](W, pfad=p)))
m["faden_antworten"]("f2", "Antwort nach dem Wechsel", ziele=[W], als="Claude")
out["antwort"] = [n["text"] for n in lies("zweige/gruppe%2Fdemo/weg.json")["kommentare"][0]["nachrichten"]]
out["abkuerzung"] = [m["Waggon"].aus_id(k) == W for k in ("gitlab.example.com/gruppe/demo/1", "projekt:repo")]
wt = repo + "-wt"
subprocess.run(["git", "-C", repo, "worktree", "add", "-q", "-b", "wt", wt], check=True)
try:
    out["worktree"] = (os.path.realpath(wt) in m["repo_klone"]("gruppe/demo"),
                       m["branch_ort"](m["Waggon"](repo="gruppe/demo", branch="wt")) == (os.path.realpath(repo), False),
                       m["klon_waggon"](wt) == m["Waggon"](repo="gruppe/demo", branch="wt"))
finally:
    subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", wt], check=True)
    subprocess.run(["git", "-C", repo, "branch", "-qD", "wt"], check=True)
out["aufgeraeumt"] = (sorted(m["zweige_aufraeumen"](repo)), sorted(n for n in os.listdir(D + "/zweige/gruppe%2Fdemo") if n.endswith(".json")))
print(json.dumps(out))
"""


def branch_akte_test(env2):
    """Eine Akte je Branch (docs/branch-waggon.md), in eigenem Datenordner: alte Akten (je Projekt, Branch-Akten aus 4a,
    MR-Akten) werden auf zweige/<repo>/<branch>.json verteilt, MR-Akten ohne MR-Daten bleiben; fremde Fäden, Antwort auf
    einen anderen Branch, Abkürzungen, Worktree (dieselbe Akte, Arbeitsstand nur im Haupt-Klon), Aufräumen."""
    env = dict(env2, XDG_DATA_HOME=f"{T}/data-branch")
    r = subprocess.run([sys.executable, "-c", BRANCH_AKTE, SKRIPT, REPO], cwd=REPO, env=env, capture_output=True, text=True)
    try:
        o = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        pruefe(False, f"Branch-Akte: Skript lief nicht – {r.stderr[-800:]}")
        return
    pruefe(o["migriert"] == [["f1", "f3", "f9", "k1"], 1, {}, ["f2"], ["f5"], ["gitlab.example.com_gruppe_demo_5.json"], False, True],
           f"Branch-Akte: alte Akten verteilt, MR-Schicht am Quell-Branch, MR ohne Daten bleibt, Sicherung ({o['migriert']})")
    pruefe(o["fremd"] == ["f2", "f5"], "Branch-Akte: fremde Fäden aus den Akten der anderen Branches")
    pruefe(o["antwort"] == ["f2", "Antwort nach dem Wechsel"], "Branch-Akte: agent antworten findet den Faden eines anderen Branches")
    pruefe(o["abkuerzung"] == [True, True], "Branch-Akte: MR-Kennung und projekt:<name> führen zum Branch")
    pruefe(o["worktree"] == [True, True, True], f"Branch-Akte: Worktree ist ein Klon des Repos, Stand aus dem Haupt-Klon ({o['worktree']})")
    pruefe(o["aufgeraeumt"] == [["alt", "weg"], ["feature.json"]],
           f"Branch-Akte: Akten gelöschter Branches im Archiv, der mit offenem MR bleibt ({o['aufgeraeumt']})")


LOKALER_FADEN = ALLES_LADEN + r"""
import sys
m = alles_laden(sys.argv[1])
print(m["faden_anlegen"]([m["Waggon"].aus_id("projekt:repo")], "Alt lokal", "App.cs:3")[0])
"""


def fremd_test(mr, env2, hol):
    """Fremder MR, Quell-Branch ausgecheckt (docs/ein-waggon.md, Schritt 3): ein Waggon (kein lokaler „repo“), Seite auf
    dem Commit-Stand; nicht ausgecheckt sagt api/stand „nur lesen“ samt Grund, „auschecken“ holt ihn (nur sauber)."""
    srv = gemischt_server(env2)
    k = open(f"{T}/cache/merge-train/schluessel").read().strip()
    g = lambda *a: sh("git", "-C", REPO, *a)
    hinweis = lambda: json.loads(hol(f"/api/stand?mr={urllib.parse.quote(mr)}&k={k}")).get("auschecken")
    def auschecken():
        req = urllib.request.Request(f"http://127.0.0.1:{PORT_GEMISCHT}/api/gitlab",
                                     json.dumps({"aktion": "auschecken", "mr": mr, "k": k}).encode(),
                                     {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{PORT_GEMISCHT}"})
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    try:
        z = json.loads(hol("/zug.js?akt=" + urllib.parse.quote(mr))[len("window.MR_ZUG="):-1])
        w = next((w for w in z["wagen"] if w["p"] == BR1), {})
        pruefe(sum(x["p"] == BR1 for x in z["wagen"]) == 1 and "im Haupt-Klon ausgecheckt" in w.get("titel", "") and "⎇" in w.get("name", "")
               and "eigener MR" not in w.get("titel", ""), "fremder MR: ausgecheckt ein Waggon, kein lokaler „repo“")
        seite = hol("/mr/" + mr)
        pruefe("Arbeitsstand (nicht Committetes dabei)" not in seite and hinweis() is None,
               "fremder MR: Seite auf dem Commit-Stand, kein Hinweis, solange ausgecheckt")
        g("checkout", "-q", "main")
        h = hinweis() or {}
        pruefe(h.get("branch") == "feature" and "nur lesen" in h.get("text", ""), "nicht ausgecheckt: Hinweis „nur lesen“ mit Branch")
        open(f"{REPO}/seite.html", "a").write("<p>offen</p>\n")
        r = auschecken()
        h = hinweis() or {}
        pruefe(not r["ok"] and g("symbolic-ref", "--short", "HEAD").stdout.strip() == "main" and h.get("text", "").startswith(r["text"]),
               "auschecken: bei offenen Änderungen nicht, der Grund steht im Hinweis")
        g("checkout", "-q", "--", "seite.html")
        r = auschecken()
        pruefe(r["ok"] and r.get("neu_laden") and g("symbolic-ref", "--short", "HEAD").stdout.strip() == "feature" and hinweis() is None,
               "auschecken: sauber → ausgecheckt, Hinweis weg")
    finally:
        g("checkout", "-q", "--", "seite.html"); g("checkout", "-q", "feature")
        srv.terminate(); srv.wait()


def eigen_test(mr, env2, hol):
    """Eigener MR, Quell-Branch ausgecheckt = ein Waggon (docs/ein-waggon.md, Schritt 1): Zug ohne lokalen Waggon, Seite
    im Arbeitsstand, Fäden ziehen um und gehen an den MR, Diskussion an lokal geänderter Zeile bleibt markiert stehen,
    „passt hier“, GitLab-Kommentar nur an Zeilen wie in GitLab."""
    srv = gemischt_server(env2)  # REPO ist auch lokales Projekt (Arbeitsstand)
    liste_pfad = f"{T}/cache/merge-train/mrliste.json"
    liste_alt = open(liste_pfad).read()
    k = open(f"{T}/cache/merge-train/schluessel").read().strip()
    ap = f"{T}/data/merge-train/zweige/gruppe%2Fdemo/feature.json"
    def post_g(pfad, d):
        req = urllib.request.Request(f"http://127.0.0.1:{PORT_GEMISCHT}{pfad}", json.dumps(dict(d, mr=mr, k=k)).encode(),
                                     {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{PORT_GEMISCHT}"})
        return json.loads(urllib.request.urlopen(req, timeout=60).read())
    def review():
        return json.loads(hol(f"/api/review?mr={urllib.parse.quote(mr)}&k={k}"))
    d950 = lambda rv: next(d for d in rv["diskussionen"] if d["diskussion"] == "d950")
    try:
        r = subprocess.run([sys.executable, "-c", LOKALER_FADEN, SKRIPT], cwd=REPO, env=env2, capture_output=True, text=True)
        alt_id = r.stdout.strip()
        pruefe(r.returncode == 0 and alt_id, "eigener MR: lokaler Faden vorher angelegt" + ("" if alt_id else f" – {r.stderr[-300:]}"))
        liste = json.loads(liste_alt)
        for it in liste["items"]:
            it["rollen"] = ["author"]
        json.dump(liste, open(liste_pfad, "w"))
        zeilen = open(f"{REPO}/App.cs").read().split("\n")
        damals = zeilen[10].strip()  # Zeile 11: dort hängt d950 (GitLab-Stand)
        zeilen[10] += " // lokal"
        open(f"{REPO}/App.cs", "w").write("\n".join(zeilen))
        z = json.loads(hol("/zug.js?akt=" + urllib.parse.quote(mr))[len("window.MR_ZUG="):-1])
        w = next((w for w in z["wagen"] if w["p"] == BR1), {})
        pruefe(sum(x["p"] == BR1 for x in z["wagen"]) == 1 and "eigener MR" in w.get("titel", ""),
               "eigener MR: im Zug nur der MR-Waggon, kein lokaler „repo“")
        seite = hol("/mr/" + mr)
        refs = json.load(open(json.load(open(ap))["struktur"]))["refs"]
        pruefe("Arbeitsstand (nicht Committetes dabei)" in seite and refs.get("arbeitsstand") and refs["head_sha"] != refs["commit_sha"]
               and "// lokal" in sh("git", "-C", REPO, "show", refs["head_sha"] + ":App.cs").stdout,
               "eigener MR: Seite zeigt den Arbeitsstand")
        akte = json.load(open(ap))
        pruefe(any(x.get("id") == alt_id for x in akte["kommentare"]), "eigener MR: Faden aus dem Klon steht in der Akte des Branches")
        rv = review()
        g = d950(rv)["geaendert"] or {}
        pruefe(d950(rv)["b"] == 11 and g.get("text") == "lokal geändert" and g.get("damals") == damals,
               "eigener MR: Diskussion an lokal geänderter Zeile bleibt dort, markiert, mit damaligem Code")
        mrj = lambda html: json.JSONDecoder().raw_decode(html.split("const MR=", 1)[1])[0]
        r = post_g("/api/kommentar", {"aktion": "anker", "diskussion": "d950", "seite": mrj(seite)["seite"]})
        rv = review()
        pruefe(r["ok"] and not d950(rv)["geaendert"] and d950(rv)["anker"] and d950(rv)["b"] == 11, "passt hier: Marke weg, neuer Anker")
        app = open(f"{REPO}/App.cs").read()
        open(f"{REPO}/App.cs", "w").write("// oben\n" + app)
        seite = hol("/mr/" + mr)
        rv = review()
        pruefe(d950(rv)["b"] == 12 and not d950(rv)["geaendert"], "passt hier: wandert vom Anker aus weiter mit")
        struktur = json.load(open(json.load(open(ap))["struktur"]))
        i_app = next(i for i, f in enumerate(struktur["dateien"]) if f["neu"] == "App.cs")
        paar = {b: a for a, b in struktur["dateien"][i_app]["paare"] if b}
        klick = lambda b, text: post_g("/api/kommentar", {"aktion": "neu", "datei": i_app, "a": paar.get(b), "b": b, "text": text,
                                                          "seite": mrj(seite)["seite"], "sha": mrj(seite)["sha"]})
        r = klick(12, "An geänderter Zeile")
        pruefe(not r["ok"] and "erst nach dem Push" in r["text"], "eigener MR: kein GitLab-Kommentar an lokal geänderter Zeile")
        r = klick(13, "An gleicher Zeile")
        km = next((x for x in (r.get("review") or {}).get("kommentare", []) if x["text"] == "An gleicher Zeile"), None)
        roh = next((x for x in json.load(open(ap))["kommentare"] if x.get("text") == "An gleicher Zeile"), {})
        pruefe(r["ok"] and km and km["b"] == 13 and roh.get("b") == 12 and (roh.get("refs") or {}).get("head_sha") ==
               json.load(open(ap))["meta"]["diff_refs"]["head_sha"],
               "eigener MR: GitLab-Kommentar an unveränderter Zeile, Position im GitLab-Stand")
        if km:
            post_g("/api/kommentar", {"aktion": "loeschen", "id": km["id"]})
        r = subprocess.run([sys.executable, SKRIPT, "agent", "thread", "--ort", "App.cs:4", "Neu im Klon"], cwd=REPO, env=env2,
                           capture_output=True, text=True)
        pruefe(r.returncode == 0 and any(x.get("nachrichten") and x["nachrichten"][0]["text"] == "Neu im Klon"
                                         for x in json.load(open(ap))["kommentare"]),
               "eigener MR: agent thread im Klon landet im MR")
        r = subprocess.run([sys.executable, SKRIPT, "status"], cwd=REPO, env=env2, capture_output=True, text=True)
        pruefe(r.returncode == 0 and "Branch feature" in r.stdout and "Erwartet:" in r.stdout and "Review MR" not in r.stdout
               and alt_id in r.stdout, "eigener MR: status zeigt Entwicklung samt Faden aus dem Klon")
    finally:
        sh("git", "-C", REPO, "checkout", "-q", "--", "App.cs")
        open(liste_pfad, "w").write(liste_alt)
        srv.terminate(); srv.wait()

def mr_gespraech_test(mr, k, basis, struktur):
    """Fragen an einen Agenten zum MR: eigene Datei, nie im Review, agent feedback/antworten/horchen mit MR-Kennung."""
    genv = dict(ENV, PATH=f"{T}/gl-bin:" + ENV["PATH"])
    i_app = next(i for i, f in enumerate(struktur["dateien"]) if f["neu"] == "App.cs")
    vorher = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    pruefe(vorher["agenten"] == ["Claude", "Copilot"] and vorher["faeden"] == [], "MR-Gespräch: Claude (immer) und Agent aus [agenten] angeboten")
    im_klon = subprocess.Popen([sys.executable, SKRIPT, "agent", "horchen", "--als", "Copilot", "--timeout", "3"], cwd=REPO,
                               env=genv, stdout=subprocess.PIPE, text=True)
    wer = None
    for _ in range(25):
        wer = json.loads(get(f"/api/review?mr={mr}&k={k}")).get("horcht")
        if wer == "Copilot":
            break
        time.sleep(0.1)
    im_klon.communicate(timeout=30)
    pruefe(wer == "Copilot", "MR-Gespräch: horchen im Klon belauscht den MR schon vor dem ersten Faden")
    pruefe(vorher["hinweise"] and all(h["agent"] == "Claude" for h in vorher["hinweise"]),
           "Hinweise: JSON ohne agent → wer sie mit agent zeigen angemeldet hat (erkannt: Claude)")
    r = post("/api/kommentar", dict(basis, gespraech=1, aktion="neu", an="Copilot", datei=i_app, a=None, b=11, text="Was macht Zeile 11?"))
    pruefe(r["ok"] and len(r["review"]["faeden"]) == 1 and r["review"]["g_ausstehend"] == 1, "MR-Gespräch: Frage an Copilot angelegt")
    pruefe(len(r["review"]["kommentare"]) == len(vorher["kommentare"]) and r["review"]["ausstehend"] == vorher["ausstehend"],
           "MR-Gespräch: Frage ist kein Review-Kommentar")
    f = r["review"]["faeden"][0]
    pruefe(f["b"] == 11 and f["an"] == "Copilot" and f["status"] == "entwurf", "MR-Gespräch: an Zeile 11, Entwurf")
    r = post("/api/gespraech", dict(basis, aktion="senden"))
    for _ in range(50):
        if os.path.exists(f"{T}/copilot.prompt"):
            break
        time.sleep(0.1)
    prompt = open(f"{T}/copilot.prompt").read() if os.path.exists(f"{T}/copilot.prompt") else ""
    pruefe(r["ok"] and "Copilot gestartet" in r["text"], "MR-Gespräch: senden startet den Agenten aus [agenten]")
    pruefe(f"merge-train agent feedback {BR1}" in prompt and "gruppe/demo!1" in prompt and "nichts committen" in prompt,
           "MR-Gespräch: Prompt nennt MR und verbietet Commits")
    r = sh(sys.executable, SKRIPT, "agent", "feedback", mr, env=genv, check=False)
    pruefe(r.returncode == 0 and f'[{f["id"]}] App.cs:11' in r.stdout and "an Copilot" in r.stdout and "Was macht Zeile 11?" in r.stdout,
           "MR-Gespräch: agent feedback mit MR-Kennung")
    ap = f'{T}/data/merge-train/zweige/gruppe%2Fdemo/feature.json'
    def autor(aid):
        a = json.load(open(ap)); a["meta"]["author"]["id"] = aid; json.dump(a, open(ap, "w"))
    autor(1)  # ich (fake-glab user id 1) bin Autor: eigener MR
    r = sh(sys.executable, SKRIPT, "agent", "feedback", mr, env=genv, check=False)
    autor(None)
    pruefe(r.returncode == 0 and "dein eigener MR: Wünsche" in r.stdout and "committen" in r.stdout
           and "nur antworten" not in r.stdout, "eigener MR: feedback erlaubt Umsetzen und Committen")
    r = sh(sys.executable, SKRIPT, "agent", "feedback", mr, "--horchen", "--als", "Copilot", "--timeout", "10", env=genv, check=False)
    pruefe(r.returncode == 0 and "Was macht Zeile 11?" in r.stdout, "feedback --horchen: was schon wartet, kommt sofort")
    r = sh(sys.executable, SKRIPT, "agent", "feedback", cwd=REPO, env=genv, check=False)
    pruefe(r.returncode == 0 and "gruppe/demo!1" in r.stdout, "MR-Gespräch: agent feedback im Klon findet den MR")
    r = sh(sys.executable, SKRIPT, "status", cwd=REPO, env=genv, check=False)
    pruefe(r.returncode == 0 and "Review MR gruppe/demo!1" in r.stdout and "WARTET AUF DICH" in r.stdout
           and f"agent feedback {BR1}" in r.stdout and "Erwartet:" not in r.stdout,
           "merge-train status im MR-Klon: Review, wartender Faden, feedback mit MR")
    r = sh(sys.executable, SKRIPT, "agent", "thread", "-p", mr, "Hallo", env=ohne_agent(genv), check=False)
    pruefe(r.returncode == 2 and "--als" in r.stderr, "Agent ohne Namen: thread verlangt --als")
    r = sh(sys.executable, SKRIPT, "agent", "antworten", f["id"][:6], "Sie loggt.", env=ohne_agent(genv), check=False)
    pruefe(r.returncode == 0 and "nichts mehr offen" in r.stdout, "MR-Gespräch: agent antworten (sucht in allen Gesprächen)")
    rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    m = rv["faeden"][0]["nachrichten"][-1]
    pruefe(rv["faeden"][0]["status"] == "antwort" and m["text"] == "Sie loggt." and m["wer"] == "Copilot",
           "MR-Gespräch: Antwort ohne erkennbaren Agenten unter dem gefragten (Copilot)")
    r = sh(sys.executable, SKRIPT, "agent", "feedback", mr, "--horchen", "--als", "Copilot", "--timeout", "2", env=genv, check=False)
    pruefe(r.returncode == 1 and "Zeit abgelaufen" in r.stdout, "feedback --horchen: wartet nichts, horcht es")
    lauscher = subprocess.Popen([sys.executable, SKRIPT, "agent", "horchen", mr, "--als", "Copilot", "--timeout", "30"], env=genv,
                                stdout=subprocess.PIPE, text=True)
    for _ in range(50):
        if json.loads(get(f"/api/review?mr={mr}&k={k}")).get("horcht") == "Copilot":
            break
        time.sleep(0.1)
    post("/api/kommentar", dict(basis, gespraech=1, aktion="antworten", id=f["id"], text="Und warum?"))
    r = post("/api/gespraech", dict(basis, aktion="senden"))
    pruefe(r["ok"] and "zuhört (Copilot)" in r["text"], "MR-Gespräch: Copilot hört zu → übergeben")
    aus, _ = lauscher.communicate(timeout=30)
    pruefe(lauscher.returncode == 0 and "Und warum?" in aus, "MR-Gespräch: horchen mit MR-Kennung bekommt die Nachfrage")
    akte = json.load(open(f'{T}/data/merge-train/zweige/gruppe%2Fdemo/feature.json'))
    pruefe(any(k.get("nachrichten") for k in akte["kommentare"]), "MR-Gespräch: Faden liegt in der Datei des Waggons")
    sh(sys.executable, SKRIPT, "agent", "antworten", f["id"], "Weil.", "--erledigt", env=genv, check=False)
    r1 = sh(sys.executable, SKRIPT, "agent", "thread", "-p", mr, "--als", "Copilot", "Stand 1", env=genv, check=False)
    r2 = sh(sys.executable, SKRIPT, "agent", "thread", "-p", mr, "--als", "Copilot", "Stand 2", env=genv, check=False)
    erst = r1.stdout.split("]")[0].lstrip("[")
    pruefe(r1.returncode == 0 and "Hinweis" not in r1.stdout and r2.returncode == 0 and "Hinweis" in r2.stdout and erst in r2.stdout,
           "agent thread: zweiter allgemeiner Faden nennt den offenen ersten (dort fortsetzen)")
    for x in (erst, r2.stdout.split("]")[0].lstrip("[")):
        sh(sys.executable, SKRIPT, "agent", "antworten", x, "--erledigt", "--als", "Copilot", env=genv, check=False)
    # GitLab-Kommentar umformulieren: draft ändern, sonst neuer draft daneben; staged nur per „übernehmen“
    rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    an11 = [h for h in rv["hinweise"] if h["path"] == "App.cs" and h["b"] == 11 and h["status"] == "offen"]
    km11 = [x for x in rv["kommentare"] if x["path"] == "App.cs" and x["b"] == 11 and x["status"] != "loeschen"]
    post("/api/kommentar", dict(basis, gespraech=1, aktion="antworten", id=f["id"], text="Formulier den Kommentar kürzer"))
    post("/api/gespraech", dict(basis, aktion="senden"))
    r = sh(sys.executable, SKRIPT, "agent", "feedback", mr, env=genv, check=False)
    pruefe(r.returncode == 0 and "agent kommentar" in r.stdout
           and all(f"Agent-Hinweis h:{h['key']}" in r.stdout and h["text"] in r.stdout for h in an11)
           and all(f"GitLab-Kommentar {x['id']}" in r.stdout for x in km11) and (an11 or km11),
           "Kommentar umformulieren: feedback zeigt Kommentare/Hinweise an der Zeile des Fadens")
    hw = f"{REPO}/tasks/DEMO-1-review-markers.json"
    sicher = open(hw, encoding="utf-8").read()
    if an11:
        r = sh(sys.executable, SKRIPT, "agent", "kommentar", "h:" + an11[0]["key"][:6], "Null check missing.", env=genv, check=False)
        neu = json.loads(open(hw, encoding="utf-8").read())
        pruefe(r.returncode == 0 and "geändert" in r.stdout and any(m.get("text") == "Null check missing." for m in neu["markers"]),
               "Kommentar umformulieren: offener Hinweis → text in der Review-JSON")
        open(hw, "w", encoding="utf-8").write(sicher)
    vorher = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    n, nh = len(vorher["kommentare"]), len(vorher["hinweise"])
    r = sh(sys.executable, SKRIPT, "agent", "kommentar", f["id"], "Shorter: add a null check.", env=genv, check=False)
    rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    neu = [h for h in rv["hinweise"] if h["text"] == "Shorter: add a null check."]
    pruefe(r.returncode == 0 and "draft" in r.stdout and len(rv["kommentare"]) == n and len(rv["hinweise"]) == nh + 1
           and neu and neu[0]["path"] == "App.cs" and neu[0]["b"] == 11 and neu[0]["status"] == "offen",
           "Kommentar umformulieren: Faden-id → neuer draft (Agent-Hinweis) an derselben Zeile, kein Review-Kommentar")
    r = post("/api/kommentar", dict(basis, aktion="neu", datei=i_app, a=None, b=11, text="Original comment."))  # vom Nutzer
    km = next(x for x in r["review"]["kommentare"] if x["text"] == "Original comment.")
    n += 1
    r = sh(sys.executable, SKRIPT, "agent", "kommentar", km["id"], "Even shorter.", env=genv, check=False)
    rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    pruefe(r.returncode == 0 and len(rv["kommentare"]) == n and any(x["id"] == km["id"] and x["text"] == km["text"] for x in rv["kommentare"])
           and any(h["text"] == "Even shorter." and h["extra"].get("ersetzt") == f"Kommentar {km['id']}" for h in rv["hinweise"]),
           "Kommentar umformulieren: staged/sent bleibt unverändert, neuer draft daneben")
    r = post("/api/kommentar", dict(basis, gespraech=1, aktion="neu", an="Copilot", zu="h:" + neu[0]["key"], text="Kürzer?"))
    fh = next(x for x in r["review"]["faeden"] if x["nachrichten"][-1]["text"] == "Kürzer?")
    r = sh(sys.executable, SKRIPT, "agent", "kommentar", "h:" + neu[0]["key"], "Shortest.", env=genv, check=False)
    rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    pruefe(r.returncode == 0 and len(rv["hinweise"]) == nh + 2 and any(h["text"] == "Shortest." for h in rv["hinweise"]),
           "Kommentar umformulieren: eigenen draft nochmal ändern")
    h = next(h for h in rv["hinweise"] if h["text"] == "Shortest.")
    zu = next(x for x in json.load(open(ap))["kommentare"] if x["id"] == fh["id"]).get("zu")
    pruefe(zu == "h:" + h["key"] and fh["id"] in r.stdout, f"Kommentar umformulieren: h:<key> hängt den Faden an den neuen Text um – {zu}")
    post("/api/kommentar", dict(basis, gespraech=1, aktion="loeschen", id=fh["id"]))
    r = post("/api/kommentar", dict(basis, aktion="neu", hinweis=h["key"]))
    rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    pruefe(r["ok"] and len(rv["kommentare"]) == n + 1, "Kommentar umformulieren: staged erst durch „übernehmen“")
    for x in rv["kommentare"]:
        if x["id"] == km["id"] or x["text"] == "Shortest.":
            post("/api/kommentar", dict(basis, aktion="loeschen", id=x["id"]))
    pruefe(not os.path.exists(f'{T}/data/merge-train/zweige/gruppe%2Fdemo/feature.agent.json'),
           "Kommentar umformulieren: drafts in der Review-JSON, keine eigene Datei")
    open(hw, "w", encoding="utf-8").write(sicher)
    pruefe(sh(sys.executable, SKRIPT, "agent", "kommentar", "gibtsnicht", "x", env=genv, check=False).returncode == 2,
           "Kommentar umformulieren: unbekanntes Ziel")
    # Faden an einem GitLab-Kommentar (zu): Wunsch gilt dem Kommentartext, geht nie nach GitLab
    r = post("/api/kommentar", dict(basis, aktion="neu", datei=i_app, a=None, b=11, text="Long original comment."))
    km = next(x for x in r["review"]["kommentare"] if x["text"] == "Long original comment.")
    n, ausstehend = len(r["review"]["kommentare"]), r["review"]["ausstehend"]
    r = post("/api/kommentar", dict(basis, gespraech=1, aktion="neu", an="Copilot", zu="k:" + km["id"], text="kürzer bitte"))
    fz = next((x for x in r["review"]["faeden"] if x.get("zu") == "k:" + km["id"]), None) if r["ok"] else None
    pruefe(fz and fz["path"] == "App.cs" and fz["b"] == 11 and len(r["review"]["kommentare"]) == n
           and r["review"]["ausstehend"] == ausstehend, "Faden am Kommentar: an dessen Zeile, kein Review-Kommentar")
    pruefe(not post("/api/kommentar", dict(basis, gespraech=1, aktion="neu", zu="k:gibtsnicht", text="x"))["ok"],
           "Faden am Kommentar: unbekannter Kommentar abgelehnt")
    post("/api/gespraech", dict(basis, aktion="senden"))
    r = sh(sys.executable, SKRIPT, "agent", "feedback", mr, env=genv, check=False)
    block = r.stdout.split(f'[{fz["id"]}]')[1].split("── [")[0] if fz and f'[{fz["id"]}]' in r.stdout else ""
    pruefe(f"HÄNGT AN GitLab-Kommentar {km['id']} (staged)" in block and "Long original comment." in block
           and block.count(f"GitLab-Kommentar {km['id']}") == 1, "Faden am Kommentar: feedback zeigt den Kommentar als Ziel")
    r = sh(sys.executable, SKRIPT, "agent", "kommentar", fz["id"], "Short comment.", "--als", "Copilot (Test)", env=genv, check=False)
    rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    h = next((h for h in rv["hinweise"] if h["text"] == "Short comment."), None)
    fz2 = next(x for x in rv["faeden"] if x["id"] == fz["id"])
    pruefe(r.returncode == 0 and "erledigt" in r.stdout and h and h["agent"] == "Copilot (Test)" and fz2["zu"] == "h:" + h["key"]
           and fz2["status"] == "erledigt" and len(fz2["nachrichten"]) == 1,
           "Faden am Kommentar: agent kommentar legt draft an, Faden hängt dann daran und ist erledigt, ohne Antwort")
    r = sh(sys.executable, SKRIPT, "agent", "kommentar", fz["id"], "Shorter comment.", env=genv, check=False)
    rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    h2 = next((h for h in rv["hinweise"] if h["text"] == "Shorter comment."), None)
    fz2 = next(x for x in rv["faeden"] if x["id"] == fz["id"])
    pruefe(r.returncode == 0 and h2 and not any(h["text"] == "Short comment." for h in rv["hinweise"]) and fz2["zu"] == "h:" + h2["key"],
           "Faden am Kommentar: hängt er an einem draft, wird dessen Text geändert (neuer key, Faden zieht mit)")
    post("/api/kommentar", dict(basis, aktion="loeschen", id=km["id"]))
    post("/api/kommentar", dict(basis, gespraech=1, aktion="loeschen", id=fz["id"]))
    open(hw, "w", encoding="utf-8").write(sicher)

def gitlab_test():
    """GitLab-Modus: agent pruefen/zeigen, MR-Seite, Review abschließen, Gespräch zum MR (mit tests/fake-glab)."""
    repo_anlegen()
    open(ENV["MERGE_TRAIN_CONFIG"], "w").write(
        f'lokal = false\nglab = "{sys.executable} {HIER}/fake-glab"\nport = {PORT}\nbrowser = "true"\n'
        f'hinweise = ["{REPO}/tasks/*-review-markers.json"]\n'
        f'[agenten]\nCopilot = "{T}/gl-bin/copilot {{prompt}}"\n')  # Gespräch zum MR: Ersatz-Agent schreibt den Prompt mit
    os.makedirs(f"{T}/gl-bin")
    open(f"{T}/gl-bin/copilot", "w").write(f'#!/bin/sh\necho "$1" > {T}/copilot.prompt\n'); os.chmod(f"{T}/gl-bin/copilot", 0o755)
    hw = f"{REPO}/tasks/DEMO-1-review-markers.json"
    json.dump({"key": "DEMO-1", "branch": "feature", "reviewed_commit": "abc", "tag": "TODO REVIEW DEMO-1",
               "notes": "Team-Thema: Logging", "failing_tests": {"#1": "AppTest.Neu"},
               "markers": [
                   {"finding": "#1", "path": "App.cs", "needle": "public void Neu(", "text": "#1 Missing null check",
                    "rationale": "siehe Ticket", "resolved_when": "Test grün", "status": "open (GitLab comment)",
                    "see_also": ["Neu.cs:2", {"path": "App.cs", "needle": "WeitWeg", "label": "Aufrufer"}, "App.cs:40-45",
                                 {"path": "Neu.cs", "diff": True, "label": "Kopie"}]},
                   {"finding": "#7", "text": "#7 General remark about the MR"},
                   {"path": "App.cs", "needle": "=public void WeitWeg() {}", "text": "K2 Rename method"},
                   {"finding": "#3", "path": "App.cs", "needle": "GibtEsNicht", "text": "#3 Weg"},
                   {"finding": "#4", "path": "seite.html", "needle": "Bar(x)", "text": "#4 Escape output",
                    "placement": None},
                   {"finding": "#5", "path": "Neu.cs", "needle": "Bar(", "text": "#5 Also here"},
                   {"finding": "#6", "path": "App.cs", "needle": "=// Zeile 9", "text": "#6 Context line"},
               ]}, open(hw, "w"))
    srv = subprocess.Popen([sys.executable, SKRIPT, "--server"], env=ENV)
    try:
        for _ in range(50):
            try:
                get("/ping"); break
            except OSError:
                time.sleep(0.1)
        # Agent-CLI
        r = sh(sys.executable, SKRIPT, "agent", "pruefen", hw, check=False)
        print(r.stdout, r.stderr)
        pruefe(r.returncode == 1, "pruefen meldet fehlenden needle mit Exit 1")
        pruefe("App.cs:11" in r.stdout and "im Diff" in r.stdout, "#1 auf App.cs:11 im Diff")
        pruefe("App.cs:50" in r.stdout and "allgemeiner Kommentar" in r.stdout, "K2 außerhalb des Diffs erkannt")
        pruefe("needle nicht gefunden" in r.stdout, "#3 needle nicht gefunden")
        r = sh(sys.executable, SKRIPT, "agent", "zeigen", hw, "--nicht-oeffnen", check=False)
        pruefe(f"http://127.0.0.1:{PORT}/b/gruppe/demo@feature" in r.stdout, "zeigen gibt die URL des Branches aus")
        pruefe("Quelle: lokal" in r.stdout, "Repo der Hinweis-Datei wird als lokaler Klon genutzt")
        pruefe("#7" in r.stdout and "allgemeiner MR-Kommentar" in r.stdout, "Eintrag ohne Pfad = allgemeiner Kommentar, kein FEHLT")
        pruefe(": FEHLT:" not in "".join(z for z in r.stdout.splitlines() if "siehe auch" in z), "see_also aufgelöst")
        pruefe("Achtung: Stand abc des Reviews nicht im Klon" in r.stdout,
               "see_also: reviewed_commit fehlt im Klon → Warnung, kein Fehler")
        r = sh(sys.executable, SKRIPT, "agent", "pruefen", hw, env=ohne_agent(ENV), check=False)
        pruefe("kein „agent“" in r.stdout, "pruefen: JSON ohne agent und kein Harness erkennbar → Hinweis")
        # Diff kommt immer vom Branch im Klon: lokale Änderungen und ausgecheckter Branch spielen keine Rolle
        open(f"{REPO}/App.cs", "a").write("// lokal geändert\n")
        sh("git", "-C", REPO, "stash", "-q")
        sh("git", "-C", REPO, "checkout", "-q", "main")
        sh("git", "-C", REPO, "stash", "pop", "-q")
        r = sh(sys.executable, SKRIPT, "agent", "pruefen", hw, check=False)
        pruefe("Quelle: lokal" in r.stdout and "App.cs:11" in r.stdout and r.returncode == 1, "anderer Branch ausgecheckt, Diff trotzdem vom Branch feature")
        sh("git", "-C", REPO, "checkout", "-q", "--", "App.cs")
        sh("git", "-C", REPO, "checkout", "-q", "feature")
        # Review-Update: --seit
        start = sh("git", "-C", REPO, "rev-parse", "main").stdout.strip()
        r = sh(sys.executable, SKRIPT, "agent", "pruefen", hw, "--seit", start, check=False)
        pruefe("offen* (Datei geändert)" in r.stdout and "GEÄNDERT: needle nicht gefunden" in r.stdout
               and "Datei(en) geändert" in r.stdout, "--seit zeigt geändert/offen")
        pruefe(r.returncode == 0, "--seit: weggefallene needles sind kein Fehler")
        # Seite + Review-Daten: keine GitLab-Anfrage beim Öffnen
        vorher = len(open(f"{T}/glab/aufrufe.log").readlines())
        seite = get("/mr/gitlab.example.com/gruppe/demo/1")
        get("/api/zug?akt=gitlab.example.com/gruppe/demo/1")
        pruefe(len(open(f"{T}/glab/aufrufe.log").readlines()) == vorher, "Seite und Zug ohne GitLab-Anfrage")
        pruefe('id="bahnhof"' in seite, "Güterbahnhof im Kopf")
        pruefe("Demo-Änderung &lt;b&gt;fett&lt;/b&gt;" in seite and 'data-b="10"' in seite, "MR-Seite mit Diff und escaptem Titel")
        k = open(f"{T}/cache/merge-train/schluessel").read().strip()
        mr = "gitlab.example.com/gruppe/demo/1"
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
        hs = {h["finding"]: h for h in rv["hinweise"]}
        pruefe(hs["#1"]["im_diff"] and hs["#1"]["b"] == 11 and hs["#1"]["a"] is None, "#1: neue Zeile 11")
        pruefe(not hs["K2"]["im_diff"] and hs["K2"]["b"] == 50 and hs["K2"]["a"] == 51, "K2: außerhalb, alt 51 (eine Zeile gelöscht)")
        pruefe(hs["#6"]["im_diff"] and hs["#6"]["a"] == 10 and hs["#6"]["b"] == 10, "#6: Kontextzeile alt 10 / neu 10")
        pruefe(hs["#4"]["datei"] is not None and hs["#4"]["im_diff"], "#4 in seite.html")
        sa = hs["#1"]["see_also"]
        pruefe([(s["path"], s["zeile"], s["bis"], s["label"]) for s in sa[:3]] == [("Neu.cs", 2, None, None), ("App.cs", 50, None, "Aufrufer"), ("App.cs", 40, 45, None)]
               and not any(s["problem"] for s in sa[:3]), "see_also: pfad:zeile, pfad:von-bis und needle aufgelöst")
        pruefe(sa[3]["vergleich"] == "App.cs" and not sa[3]["problem"] and sa[0]["vergleich"] is None,
               "see_also mit diff: Vergleich gegen die eigene Datei des Hinweises")
        v = json.loads(get(f"/api/vergleich?mr={mr}&k={k}&a=App.cs&b=Neu.cs"))
        pruefe(v["ok"] and v["plus"] == 2 and v["minus"] == 61 and 'class="sbs"' in v["html"] and "WeitWeg" in v["html"],
               "Dateivergleich: ganze Dateien nebeneinander")
        pruefe(not json.loads(get(f"/api/vergleich?mr={mr}&k={k}&a=App.cs&b=Gibts.cs"))["ok"]
               and not json.loads(get(f"/api/vergleich?mr={mr}&k=falsch&a=App.cs&b=Neu.cs"))["ok"], "Dateivergleich: fehlende Datei, Schlüssel")
        pruefe("see_also" not in hs["#1"]["extra"] and "see_also" not in hs["#1"]["text"], "see_also nicht im Kommentartext")
        pruefe('class="lu" data-von="1" data-bis="7" data-d="0"' in seite and 'data-von="15" data-bis="17" data-d="0"' in seite
               and 'data-von="24" data-bis="61" data-d="1"' in seite, "ausgeblendete Bereiche vor, zwischen und nach den Hunks")
        z = json.loads(get(f"/api/zeilen?mr={mr}&k={k}&pfad=App.cs&von=49&bis=99"))
        pruefe(z["ok"] and z["n"] == 61 and z["von"] == 49 and z["bis"] == 61 and len(z["zeilen"]) == 13
               and "WeitWeg" in z["zeilen"][1], "Zeilen nachladen (begrenzt auf Dateiende)")
        pruefe(not json.loads(get(f"/api/zeilen?mr={mr}&k={k}&pfad=Gibts.cs&von=1&bis=2"))["ok"], "unbekannte Datei beim Nachladen")
        pruefe(not json.loads(get(f"/api/zeilen?mr={mr}&k=falsch&pfad=App.cs&von=1&bis=2"))["ok"], "Nachladen braucht Schlüssel")
        pruefe('generierte Datei' in seite and 'class="laden"' in seite and "class Modell" not in seite, "generierte Datei erst auf Klick")
        i_gen = next(i for i, f in enumerate(json.load(open(json.load(open(f'{T}/data/merge-train/zweige/gruppe%2Fdemo/feature.json'))["struktur"]))["dateien"]) if f["neu"] == "Modell.Designer.cs")
        z = json.loads(get(f"/api/datei?mr={mr}&k={k}&i={i_gen}"))
        pruefe(z["ok"] and 'class="sbs"' in z["html"] and "Modell" in z["html"], "generierte Datei nachladen")
        pruefe(not json.loads(get(f"/api/datei?mr={mr}&k={k}&i=-1"))["ok"], "ungültiger Datei-Index abgelehnt")
        pruefe('class="inl"' not in seite, "Inline-Tabelle baut erst der Browser")
        pruefe(rv["quellen"][0]["notes"] == "Team-Thema: Logging" and rv["quellen"][0]["alt"], "Notizen und veralteter Stand")
        pruefe(json.loads(get(f"/api/review?mr={mr}&k=falsch"))["ok"] is False, "falscher Schlüssel abgelehnt")
        sha = rv["hinweise"][0] and json.load(open(rv and f'{T}/data/merge-train/zweige/gruppe%2Fdemo/feature.json'))
        struktur = json.load(open(sha["struktur"]))
        head = struktur["refs"]["head_sha"]
        basis = dict(mr=mr, k=k, sha=head)
        mr_gespraech_test(mr, k, basis, struktur)
        # übernehmen, anpassen, eigener Kommentar, allgemeiner Kommentar
        pruefe(post("/api/kommentar", dict(basis, aktion="neu", hinweis=hs["#1"]["key"]))["ok"], "#1 übernommen")
        pruefe(post("/api/kommentar", dict(basis, aktion="neu", hinweis=hs["K2"]["key"], text="K2 Please rename"))["ok"], "K2 angepasst übernommen")
        pruefe(post("/api/hinweis", dict(basis, aktion="verwerfen", key=hs["#5"]["key"]))["ok"], "#5 verworfen")
        i_app = next(i for i, f in enumerate(struktur["dateien"]) if f["neu"] == "App.cs")
        r = post("/api/kommentar", dict(basis, aktion="neu", datei=i_app, a=21, b=None, text="Warum gelöscht?"))
        pruefe(r["ok"], "Kommentar an gelöschter Zeile 21 (alt)")
        pruefe(not post("/api/kommentar", dict(basis, aktion="neu", datei=i_app, a=None, b=40, text="x"))["ok"], "Zeile außerhalb des Diffs per Klick abgelehnt")
        r = post("/api/kommentar", dict(basis, aktion="neu", datei=i_app, a=41, b=40, text="Kontext"))
        pruefe(r["ok"], "Kommentar an nachgeladener Kontextzeile (alt 41 / neu 40)")
        pruefe(not post("/api/kommentar", dict(basis, aktion="neu", datei=i_app, a=40, b=40, text="x"))["ok"], "falsche alte Zeile abgelehnt")
        kx = next(x for x in r["review"]["kommentare"] if x["text"] == "Kontext")
        post("/api/kommentar", dict(basis, aktion="loeschen", id=kx["id"]))
        pruefe(not post("/api/kommentar", dict(basis, sha="alt", aktion="neu", datei=i_app, a=21, b=None, text="x"))["ok"], "veralteter Stand abgelehnt")
        r = post("/api/kommentar", dict(basis, aktion="neu", text="Insgesamt gut."))
        ks = {x["text"]: x for x in r["review"]["kommentare"]}
        pruefe(len(ks) == 4 and ks["#1 Missing null check"]["finding"] == "#1", "4 Kommentare, einer aus Agent #1")
        akte = {h["finding"]: h["status"] for h in r["review"]["hinweise"]}
        pruefe(akte["#1"] == "uebernommen" and akte["#5"] == "verworfen" and akte["#4"] == "offen", "Hinweis-Status")
        # Reihenfolge der Box „GitLab-Kommentare“ = Sende-Reihenfolge
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
        kid = {x["id"]: x for x in rv["kommentare"]}
        nat = [(kid[i]["datei"] if kid[i]["datei"] is not None else -1, kid[i]["b"] or kid[i]["a"] or 0) for i in rv["reihenfolge"] if i in kid]
        pruefe(nat == sorted(nat) and len(nat) == 4 and set(rv["reihenfolge"]) >= {h["key"] for h in rv["hinweise"] if h["status"] == "offen"},
               "Reihenfolge: nach Datei und Zeile, mit offenen Hinweisen")
        gewuenscht = list(reversed(rv["reihenfolge"]))
        r = post("/api/kommentar", dict(basis, aktion="reihenfolge", ids=gewuenscht))
        pruefe(r["ok"] and r["review"]["reihenfolge"] == gewuenscht, "Reihenfolge: vom Nutzer umsortiert und gespeichert")
        pruefe(not post("/api/kommentar", dict(basis, aktion="reihenfolge", ids="x"))["ok"], "Reihenfolge: ungültige Liste abgelehnt")
        # Abschließen
        r = post("/api/abschliessen", basis)
        print(r["text"])
        d = drafts()
        pruefe(r["ok"] and len(d) == 4, "4 Draft-Notes angelegt")
        pruefe([x["note"] for x in d] == [kid[i]["text"] for i in gewuenscht if i in kid], "Draft-Notes in der Reihenfolge der Box angelegt")
        pruefe(not any("Was macht Zeile 11" in x["note"] or "Und warum" in x["note"] for x in d),
               "MR-Gespräch: Fragen an den Agenten gehen nicht nach GitLab")
        pos = {x["note"]: x["position"] for x in d}
        pruefe(pos["#1 Missing null check"]["new_line"] == 11 and "old_line" not in pos["#1 Missing null check"]
               and pos["#1 Missing null check"]["head_sha"] == head, "Position #1 (hinzugefügte Zeile: nur neu)")
        pruefe(pos["Warum gelöscht?"].get("old_line") == 21 and "new_line" not in pos["Warum gelöscht?"], "Position gelöschte Zeile")
        pruefe(pos["Insgesamt gut."] is None, "allgemeiner Kommentar ohne Position")
        pruefe(pos["K2 Please rename"]["new_line"] == 50, "außerhalb des Diffs: zuerst mit Position versucht")
        pruefe(not any(l.startswith("POST") and "bulk_publish" in l for l in open(f"{T}/glab/aufrufe.log")), "nichts veröffentlicht")
        # zweites Abschließen: nichts doppelt
        r = post("/api/abschliessen", basis)
        pruefe(r["ok"] and len(drafts()) == 4 and "Nichts zu übertragen" in r["text"], "erneutes Abschließen ohne Duplikate")
        # ändern + löschen → PUT + DELETE
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
        ks = {x["text"]: x for x in rv["kommentare"]}
        post("/api/kommentar", dict(basis, aktion="aendern", id=ks["Insgesamt gut."]["id"], text="Insgesamt sehr gut."))
        r = post("/api/kommentar", dict(basis, aktion="loeschen", id=ks["Warum gelöscht?"]["id"]))
        sts = {x["text"]: x["status"] for x in r["review"]["kommentare"]}
        pruefe(sts.get("Insgesamt sehr gut.") == "geaendert" and sts.get("Warum gelöscht?") == "loeschen", "Status geändert/wird gelöscht")
        r = post("/api/abschliessen", basis)
        notes = sorted(x["note"] for x in drafts())
        pruefe(r["ok"] and len(notes) == 3 and "Insgesamt sehr gut." in notes and "Warum gelöscht?" not in notes, "PUT und DELETE in GitLab")
        # in GitLab veröffentlicht (Draft weg, Kommentar da) → nicht erneut senden
        json.dump([{"id": 900, "body": "Insgesamt sehr gut.", "author": {"id": 1}, "system": False}], open(f"{T}/glab/notes.json", "w"))
        json.dump([x for x in drafts() if x["note"] != "Insgesamt sehr gut."], open(f"{T}/glab/drafts.json", "w"))
        r = post("/api/abschliessen", basis)
        pruefe(len(drafts()) == 2 and "schon veröffentlicht" in r["text"], "veröffentlichte Entwürfe werden nicht doppelt angelegt")
        # Abbruch zwischen Anlegen in GitLab und Speichern: beim nächsten Abschließen übernehmen, nicht doppelt anlegen
        rpd = f'{T}/data/merge-train/zweige/gruppe%2Fdemo/feature.json'
        zst = json.load(open(rpd))
        kd = next(x for x in zst["kommentare"] if x.get("gitlab_id") and not x.get("gitlab_weg") and x.get("nachrichten") is None)
        gid = kd["gitlab_id"]
        for f in ("gitlab_id", "gitlab_text", "gitlab_art"):
            kd.pop(f, None)
        json.dump(zst, open(rpd, "w"))
        n_vor = len(drafts())
        r = post("/api/abschliessen", basis)
        pruefe(r["ok"] and len(drafts()) == n_vor and "nicht doppelt" in r["text"]
               and next(x for x in json.load(open(rpd))["kommentare"] if x["id"] == kd["id"])["gitlab_id"] == gid,
               "Entwurf schon in GitLab, aber nicht gemerkt: übernommen statt doppelt angelegt")
        # Log der Anfragen an die Quellen
        logs = glob.glob(f"{T}/cache/merge-train/aussen-*.log")
        log = open(logs[0], encoding="utf-8").read() if logs else ""
        pruefe(len(logs) == 1 and " gitlab " in log and "POST /api/abschliessen" in log and "draft_notes" in log
               and " git " in log and "git cat-file --batch" in log, "Log: GitLab- und git-Anfragen mit Anlass")
        alt = f"{T}/cache/merge-train/aussen-2000-01-01.log"
        open(alt, "w").write("alt\n")
        open(f"{T}/cache/merge-train/aussen-2999-01-01.log", "w").write("")  # Zukunft bleibt
        sh(sys.executable, SKRIPT, "agent", "feedback", mr, env=ENV, check=False)  # neuer Prozess: räumt beim ersten Eintrag auf
        heute = open(logs[0], encoding="utf-8").read()
        pruefe(not os.path.exists(alt) and os.path.exists(f"{T}/cache/merge-train/aussen-2999-01-01.log")
               and "cli agent feedback" in heute, "Log: ältere Dateien als log_tage weg, CLI mit Anlass")
        # in GitLab verworfen (Draft weg, kein Kommentar) → „↻ MR-Daten“ macht sie wieder lokal, Abschließen sendet neu
        weg = drafts()[0]["note"]
        json.dump(drafts()[1:], open(f"{T}/glab/drafts.json", "w"))
        r = post("/api/gitlab", dict(basis, aktion="mrdaten"))
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
        pruefe(r["ok"] and "1 Entwurf/Entwürfe in GitLab verworfen" in r["text"]
               and next(x for x in rv["kommentare"] if x["text"] == weg or weg.endswith(x["text"]))["status"] == "neu",
               "verworfener Entwurf: MR-Daten macht ihn wieder lokal (staged)")
        r = post("/api/abschliessen", basis)
        pruefe(r["ok"] and len(drafts()) == 2 and any(x["note"] == weg for x in drafts()), "verworfener Entwurf wird neu gesendet")
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
        pruefe(any(x["text"] == "Insgesamt sehr gut." and x["status"] == "weg" for x in rv["kommentare"])
               or any(x["text"] == "Insgesamt sehr gut." and x["kommentar"] for x in rv["diskussionen"]),
               "veröffentlichter bleibt sent (bzw. steht als GitLab-Thread)")
        # Antwort in GitLab, Diskussion erledigt → „↻ MR-Daten“ zeigt beides am veröffentlichten Kommentar
        json.dump([{"id": 900, "body": "Insgesamt sehr gut.", "author": {"id": 1}, "system": False, "resolvable": True,
                    "resolved": True, "resolved_by": {"name": "Autorin"}}], open(f"{T}/glab/notes.json", "w"))
        json.dump({"d900": [{"id": 901, "body": "changed this line", "author": {"id": 2}, "system": True},
                            {"id": 902, "body": "Danke, erledigt", "author": {"id": 2, "name": "Autorin"}, "system": False,
                             "created_at": "2026-11-11T08:00:00Z", "resolvable": True, "resolved": True}]},
                  open(f"{T}/glab/discussions.json", "w"))
        r = post("/api/gitlab", dict(basis, aktion="mrdaten"))
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
        gl = next((x for x in rv["diskussionen"] if x["text"] == "Insgesamt sehr gut."), {})
        pruefe(r["ok"] and "1 neue Antwort(en)" in r["text"] and "1 in GitLab erledigt" in r["text"]
               and not any(x["text"] == "Insgesamt sehr gut." for x in rv["kommentare"])
               and [(m["von"], m["text"]) for m in gl.get("nachrichten", [])] == [("ich", "Insgesamt sehr gut."), ("andere", "Danke, erledigt")]
               and gl.get("stand") == "erledigt" and gl.get("wer") == "extern" and (gl.get("erledigt") or {}).get("wer") == "Autorin"
               and gl.get("url", "").endswith("#note_900"),
               "MR-Daten: veröffentlichter Kommentar als GitLab-Thread mit Antworten und Erledigt-Status")
        # Diskussion eines anderen (z. B. Reviewer im eigenen MR): auf der Seite an der Zeile, im Zug „● 1 dran“
        notes = json.load(open(f"{T}/glab/notes.json"))
        notes.append({"id": 950, "body": "Warum so?", "author": {"id": 2, "name": "Reviewerin"}, "system": False,
                      "resolvable": True, "resolved": False, "position": {"new_path": "App.cs", "new_line": 11}})
        json.dump(notes, open(f"{T}/glab/notes.json", "w"))
        r = post("/api/gitlab", dict(basis, aktion="mrliste"))
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
        fremd = [d for d in rv.get("diskussionen", []) if d["text"] == "Warum so?"]
        zw = next(w for w in json.loads(get("/api/zug"))["wagen"] if w["p"] == BR1)
        pruefe(r["ok"] and fremd and fremd[0]["b"] == 11 and fremd[0]["nachrichten"][0]["wer"] == "Reviewerin"
               and fremd[0]["nachrichten"][0]["von"] == "andere" and fremd[0]["stand"] == "dran" and fremd[0]["wer"] == "extern"
               and zw["marke"] == "● 1 dran" and zw["status"] == "offen" and "Reviewer, Autor" in zw["titel"],
               "MRs: holt Diskussionen; fremde an der Zeile, im Zug „● 1 dran“, Rollen im Titel")
        # Antwort auf die Diskussion: sofort → gleich veröffentlicht; sonst lokaler Entwurf → Abschließen als Draft-Antwort
        r = post("/api/kommentar", dict(basis, aktion="antworten", diskussion="d950", text="Darum.", sofort=1))
        fremd = next(d for d in r["review"]["diskussionen"] if d["diskussion"] == "d950")
        pruefe(r["ok"] and [m["text"] for m in fremd["nachrichten"]] == ["Warum so?", "Darum."] and fremd["stand"] == "wartet"
               and "Darum." in [x["body"] for x in json.load(open(f"{T}/glab/discussions.json"))["d950"]]
               and not any(k.get("antwort_auf") for k in r["review"]["kommentare"]),
               "Antwort mit sofort senden: gleich in GitLab, kein Entwurf")
        r = post("/api/kommentar", dict(basis, aktion="antworten", diskussion="d950", text="Noch was."))
        ent = [k for k in r["review"]["kommentare"] if k.get("antwort_auf") == "d950"]
        faden = next(d for d in r["review"]["diskussionen"] if d["diskussion"] == "d950")
        pruefe(r["ok"] and len(ent) == 1 and ent[0]["status"] == "neu" and r["review"]["ausstehend"] == 1
               and faden["stand"] == "entwurf" and faden["wer"] == "du" and faden["nachrichten"][-1] == dict(faden["nachrichten"][-1], von="ich", gesendet=None, stufe="neu"),
               "Antwort ohne sofort: lokaler Entwurf (staged)")
        r = post("/api/abschliessen", basis)
        faden = next(d for d in r["review"]["diskussionen"] if d["diskussion"] == "d950")
        pruefe(r["ok"] and any(x.get("in_reply_to_discussion_id") == "d950" and x["note"] == "Noch was." for x in drafts())
               and faden["stand"] == "gitlab_entwurf" and r["review"]["in_gitlab"] >= 1,
               "Abschließen: Antwort als Draft-Note in der Diskussion (Stand: Entwurf in GitLab)")
        # Antwortentwurf vom Agenten: agent kommentar <Diskussions-id> → draft mit reply_to, „übernehmen“ → Antwort (staged)
        r = sh(sys.executable, SKRIPT, "agent", "kommentar", "d950", "Weil es schneller ist.", "--als", "Claude", env=ENV, check=False)
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
        aw = [h for h in rv["hinweise"] if (h.get("extra") or {}).get("reply_to") == "d950"]
        pruefe(r.returncode == 0 and "Antwortentwurf" in r.stdout and len(aw) == 1 and aw[0]["status"] == "offen"
               and aw[0]["text"] == "Weil es schneller ist." and aw[0]["b"] == 11,
               f"agent kommentar <Diskussions-id>: Antwortentwurf als draft an der Zeile der Diskussion – {r.stdout} {r.stderr}")
        r = post("/api/kommentar", dict(basis, aktion="neu", hinweis=aw and aw[0]["key"]))
        ent = [x for x in r["review"]["kommentare"] if x.get("antwort_auf") == "d950" and x["text"] == "Weil es schneller ist."]
        faden = next(d for d in r["review"]["diskussionen"] if d["diskussion"] == "d950")
        pruefe(r["ok"] and len(ent) == 1 and faden["nachrichten"][-1]["text"] == "Weil es schneller ist."
               and faden["nachrichten"][-1].get("stufe") == "neu",
               "Antwortentwurf übernehmen: wird Antwort in der Diskussion (staged), kein neuer Kommentar")
        post("/api/kommentar", dict(basis, aktion="loeschen", id=ent[0]["id"])) if ent else None
        r = post("/api/kommentar", dict(basis, aktion="erledigen", diskussion="d950"))
        faden = next(d for d in r["review"]["diskussionen"] if d["diskussion"] == "d950")
        # Stand bleibt gitlab_entwurf: die Antwort „Noch was.“ liegt noch als Entwurf in GitLab, das geht vor
        pruefe(r["ok"] and faden["erledigt"]["von"] == "ich" and faden["stand"] == "gitlab_entwurf",
               "✓ erledigt: Diskussion gleich in GitLab aufgelöst, von mir")
        r = post("/api/kommentar", dict(basis, aktion="wiedereroeffnen", diskussion="d950"))
        faden = next(d for d in r["review"]["diskussionen"] if d["diskussion"] == "d950")
        pruefe(r["ok"] and not faden["erledigt"] and faden["stand"] != "erledigt", "wieder öffnen: in GitLab wieder offen")
        aufgeloest = lambda: json.load(open(f"{T}/glab/resolved.json")).get("d950")
        r = post("/api/kommentar", dict(basis, aktion="abhaken", diskussion="d950"))
        faden = next(d for d in r["review"]["diskussionen"] if d["diskussion"] == "d950")
        pruefe(r["ok"] and faden["abgehakt"] and not faden["erledigt"] and not aufgeloest(),
               "☑ abwarten: nur in merge-train, in GitLab offen")
        r = post("/api/kommentar", dict(basis, aktion="aufhaken", diskussion="d950"))
        faden = next(d for d in r["review"]["diskussionen"] if d["diskussion"] == "d950")
        pruefe(r["ok"] and not faden["abgehakt"], "↺ doch dran: Abwarten zurückgenommen")
        # andere Abrufzeit der MR-Daten (wie ein späterer Klick auf „↻ MR-Daten“): Seite nicht neu bauen
        rp0 = f'{T}/data/merge-train/zweige/gruppe%2Fdemo/feature.json'
        get(f"/mr/{mr}"); vor = json.load(open(rp0))["struktur"]
        zst = json.load(open(rp0)); zst["meta"]["_zeit"] = "01.01. 00:00"; json.dump(zst, open(rp0, "w"))
        get(f"/mr/{mr}")
        pruefe(json.load(open(rp0))["struktur"] == vor, "MR-Daten: andere Abrufzeit baut die Seite nicht neu")
        ss = json.loads(get(f"/api/stand?mr={mr}&k={k}")).get("server") or {}
        eigen = subprocess.run(["git", "-C", os.path.join(HIER, ".."), "log", "-1", "--format=%h"], capture_output=True, text=True).stdout.strip()
        pruefe(ss.get("zeit") and ss.get("commit") == eigen, "HUD: Stand von merge-train (letzter Commit des Repos, Zeit)")
        sv = json.loads(get(f"/api/stand?mr={mr}&k={k}")).get("version")
        pruefe(sv and f'"version": "{sv}"' in get(f"/mr/{mr}"), "Version des Servers in /api/stand und auf der Seite (neuer Server → Seite lädt neu)")
        r1 = post("/api/gitlab", dict(basis, aktion="mrdaten"))
        r2 = post("/api/gitlab", dict(basis, aktion="mrdaten"))
        pruefe(r1["ok"] and r2["ok"] and r2["neu_laden"] is False, "MR-Daten unverändert: Seite muss nicht neu laden")
        zst = json.load(open(rp0)); zst["meta"]["title"] = "Alter Titel"; json.dump(zst, open(rp0, "w"))
        get(f"/mr/{mr}")
        r = post("/api/gitlab", dict(basis, aktion="mrdaten"))
        pruefe(r["ok"] and r["neu_laden"] is True and "Alter Titel" not in get(f"/mr/{mr}"), "MR-Daten geändert (Titel): Seite lädt neu")
        # früher als „weg“ markiert, aber gar nicht veröffentlicht (altes Verhalten) → MR-Daten holt ihn zurück
        rp = f'{T}/data/merge-train/zweige/gruppe%2Fdemo/feature.json'
        zst = json.load(open(rp))
        alt = next(x for x in zst["kommentare"] if x.get("gitlab_id") and x.get("nachrichten") is None and x["text"] != "Insgesamt sehr gut.")
        alt["gitlab_weg"] = True
        json.dump(zst, open(rp, "w"))
        json.dump([x for x in drafts() if x["id"] != alt["gitlab_id"]], open(f"{T}/glab/drafts.json", "w"))
        r = post("/api/gitlab", dict(basis, aktion="mrdaten"))
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
        pruefe(r["ok"] and next(x for x in rv["kommentare"] if x["id"] == alt["id"])["status"] == "neu"
               and any(x["text"] == "Insgesamt sehr gut." and x["kommentar"] for x in rv["diskussionen"]),
               "fälschlich als veröffentlicht markiert: MR-Daten macht ihn wieder lokal, echter bleibt sent")
        # Fallback: GitLab lehnt Position ab → allgemeiner Kommentar mit Link
        os.environ["FAKE_GLAB_FEHLER_POSITION"] = "1"
        srv.terminate(); srv.wait()
        srv = subprocess.Popen([sys.executable, SKRIPT, "--server"], env=dict(ENV, FAKE_GLAB_FEHLER_POSITION="1"))
        for _ in range(50):
            try:
                get("/ping"); break
            except OSError:
                time.sleep(0.1)
        post("/api/kommentar", dict(basis, aktion="neu", hinweis=hs["#4"]["key"]))
        r = post("/api/abschliessen", basis)
        neu = [x for x in drafts() if "#4" in x["note"]]
        pruefe(r["ok"] and neu and neu[0]["position"] is None and "seite.html:2" in neu[0]["note"]
               and "/-/blob/" in neu[0]["note"], "abgelehnte Position → allgemeiner Kommentar mit Link")
        # Commit-Ansichten: zweiter Commit verschiebt App.cs um eine Zeile und ändert Neu.cs
        c1 = head
        app = open(f"{REPO}/App.cs").read().split("\n")
        app.insert(3, "    // eingefügt")
        open(f"{REPO}/App.cs", "w").write("\n".join(app))
        open(f"{REPO}/Neu.cs", "w").write("// neu\nclass Neu { void Bar(int y) {} }\n")
        sh("git", "-C", REPO, "commit", "-qam", "Zweiter Schritt")
        c2 = sh("git", "-C", REPO, "rev-parse", "HEAD").stdout.strip()
        seite = get(f"/mr/{mr}")
        pruefe(f"?commit={c1}" in seite and f"?seit={c1}" in seite and f"?commit={c2}" in seite
               and f"?seit={c2}" not in seite, "Commit-Liste: „nur dieser“ je Commit, „seit diesem“ außer beim letzten")
        basis2 = dict(basis, sha=c2)
        ca = f"commit:{c1}"
        s1 = get(f"/mr/{mr}?commit={c1}")
        pruefe('id="ansicht"' in s1 and "nur lesen" in s1 and '"lesen": true' in s1, "Einzel-Commit-Seite: Band, nur lesen")
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}&ansicht={ca}"))
        hs = {h["finding"]: h for h in rv["hinweise"]}
        pruefe(hs["#1"]["b"] == 11 and hs["#1"]["mr_b"] == 12 and hs["#1"]["im_diff"] and hs["#1"]["lesen"] and not hs["#1"]["unter"],
               "Commit-Ansicht: #1 von MR-Zeile 12 auf Zeile 11 nach dem Commit zurückgerechnet")
        pruefe(hs["#5"]["b"] is None and "nach diesem Commit noch geändert" in hs["#5"]["unter"],
               "Commit-Ansicht: später geänderte Zeile steht unter dem Dateinamen")
        pruefe(hs["K2"]["b"] == 50 and "außerhalb der Änderungen dieses Commits" in hs["K2"]["unter"], "Commit-Ansicht: Zeile außerhalb mit Hinweis")
        pruefe(all(x["lesen"] for x in rv["kommentare"] + rv["hinweise"]), "Commit-Ansicht: alles nur lesen")
        z1 = json.loads(get(f"/api/zeilen?mr={mr}&k={k}&pfad=App.cs&von=1&bis=99&ansicht={ca}"))
        z2 = json.loads(get(f"/api/zeilen?mr={mr}&k={k}&pfad=App.cs&von=1&bis=99"))
        pruefe(z1["n"] == 61 and z2["n"] == 62, "Kontext in der Commit-Ansicht aus dem Commit-Stand, Popup aus dem MR-Stand")
        pruefe(not post("/api/kommentar", dict(basis2, ansicht=ca, aktion="neu", text="x"))["ok"]
               and not post("/api/hinweis", dict(basis2, ansicht=ca, aktion="verwerfen", key=hs["#4"]["key"]))["ok"]
               and not post("/api/abschliessen", dict(basis2, ansicht=ca))["ok"], "Commit-Ansicht: Schreiben abgelehnt")
        sa = f"seit:{c1}"
        s2 = get(f"/mr/{mr}?seit={c1}")
        pruefe('id="ansicht"' in s2 and "Änderungen seit" in s2 and '"lesen": false' in s2, "Seit-Seite")
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}&ansicht={sa}"))
        hs = {h["finding"]: h for h in rv["hinweise"]}
        pruefe(hs["#1"]["b"] == 12 and not hs["#1"]["lesen"] and "außerhalb der Änderungen" in hs["#1"]["unter"],
               "Seit-Ansicht: #1 an MR-Zeile 12, änderbar")
        pruefe("#4" not in hs and rv["ausserhalb"] >= 1, "Seit-Ansicht: seite.html nicht geändert → nur gezählt")
        st2 = json.load(open(f'{T}/data/merge-train/zweige/gruppe%2Fdemo/feature.json'))
        sv = json.load(open(next(p[:-5] + ".json" for p in [os.path.join(f"{T}/cache/merge-train/zweige", f) for f in os.listdir(f"{T}/cache/merge-train/zweige")]
                                 if f"-seit{c1[:12]}-" in p and p.endswith(".html"))))
        i_v = next(i for i, f in enumerate(sv["dateien"]) if f["neu"] == "App.cs")
        r = post("/api/kommentar", dict(basis2, ansicht=sa, aktion="neu", datei=i_v, a=None, b=4, text="Eingefügt?"))
        kn = r["ok"] and next(x for x in json.load(open(f'{T}/data/merge-train/zweige/gruppe%2Fdemo/feature.json'))["kommentare"] if x.get("text") == "Eingefügt?")
        pruefe(kn and kn["b"] == 4 and kn["a"] is None, "Seit-Ansicht: Kommentar wird auf die MR-Zeile (neu 4, im MR hinzugefügt) gelegt")
        pruefe(not post("/api/kommentar", dict(basis2, ansicht=sa, aktion="neu", datei=i_v, a=3, b=None, text="x"))["ok"],
               "Seit-Ansicht: alte Seite nicht kommentierbar")
        pruefe(st2["struktur"] == json.load(open(f'{T}/data/merge-train/zweige/gruppe%2Fdemo/feature.json'))["struktur"]
               and "-seit" not in st2["struktur"] and "-commit" not in st2["struktur"], "Ansichten ändern die Struktur des MR nicht")
        pruefe("gehört nicht zu diesem MR" in get(f"/mr/{mr}?commit={start}") and "ungültig" in get(f"/mr/{mr}?seit=xyz"),
               "fremder Commit / ungültige sha abgelehnt")
        # „direkt veröffentlichen“: anlegen, dann alle Entwürfe veröffentlichen (bulk_publish), Diskussionen gleich holen
        r = post("/api/abschliessen", dict(basis2, direkt=1))
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
        d950 = next(d for d in rv["diskussionen"] if d["diskussion"] == "d950")
        pruefe(r["ok"] and r["text"].startswith("In GitLab veröffentlicht") and not drafts() and rv["in_gitlab"] == 0
               and any("bulk_publish" in z for z in open(f"{T}/glab/aufrufe.log"))
               and not any(x["stand"] in ("entwurf", "gitlab_entwurf") for x in rv["kommentare"])
               and any("Eingefügt?" in x["text"] for x in rv["diskussionen"])
               and d950["stand"] == "wartet" and d950["nachrichten"][-1]["text"] == "Noch was.",
               "direkt veröffentlichen: alles in GitLab veröffentlicht und gleich als Diskussionen geholt")
        # Urteil: genehmigen geht ohne Kommentare, ein zweites Mal meldet GitLab einen Fehler; ändern lassen per GraphQL
        r = post("/api/abschliessen", dict(basis2, direkt=1, urteil="genehmigen"))
        urteile = lambda: json.load(open(f"{T}/glab/urteile.json"))
        pruefe(r["ok"] and r["text"].startswith("In GitLab genehmigt") and urteile() == ["genehmigt"]
               and not any("bulk_publish" in z for z in open(f"{T}/glab/aufrufe.log").readlines()[-3:]),
               "Genehmigen ohne Kommentare: approve, kein bulk_publish")
        r = post("/api/abschliessen", dict(basis2, direkt=1, urteil="genehmigen"))
        pruefe(r["ok"] and r["text"].startswith("In GitLab genehmigt"), "zweites Genehmigen: GitLab lehnt ab, ist aber schon genehmigt")
        eof = lambda n: json.dump(n, open(f"{T}/glab/approve_eof.json", "w"))
        json.dump([], open(f"{T}/glab/urteile.json", "w")); eof(1)
        r = post("/api/abschliessen", dict(basis2, direkt=1, urteil="genehmigen"))
        pruefe(r["ok"] and urteile() == ["genehmigt"], "Genehmigen bricht mit EOF ab: einmal neu versucht")
        json.dump([], open(f"{T}/glab/urteile.json", "w")); eof(2)
        r = post("/api/abschliessen", dict(basis2, direkt=1, urteil="genehmigen"))
        pruefe(not r["ok"] and not r["text"].startswith("Fehler") and "Genehmigen fehlgeschlagen" in r["text"]
               and "noch einmal" in r["text"] and urteile() == [], "Genehmigen scheitert zweimal: nur das Urteil als Fehler gemeldet")
        r = post("/api/abschliessen", dict(basis2, direkt=1, urteil="aendern"))
        pruefe(r["ok"] and r["text"].startswith("In GitLab Änderungen angefordert") and urteile()[-1] == "aendern",
               "Ändern lassen: GraphQL mergeRequestRequestChanges")
        pruefe(not post("/api/abschliessen", dict(basis2, urteil="weg"))["ok"], "unbekanntes Urteil abgelehnt")
        # Übersicht, Zug, lokal=false
        pruefe("Güterbahnhof" in get("/") and "Demo-Änderung" not in get("/"), "Startseite ohne MR-Liste (lokal = false)")
        r = post("/api/gitlab", dict(k=k, aktion="mrliste"))
        z = json.loads(get("/api/zug?akt=" + mr))
        pruefe(r["ok"] and any(w["name"].startswith("!1 demo") and "Demo-Änderung" in w["titel"] for w in z["wagen"]) and z["zeit"],
               "Güterbahnhof holt die MR-Liste, der Zug kommt danach aus dem Cache")
        pruefe(post("/api/gitlab", dict(k=k, aktion="mrdaten", mr=mr))["ok"], "Güterbahnhof holt MR-Daten")
        pruefe(not post("/api/gitlab", dict(k="falsch", aktion="mrliste"))["ok"], "Güterbahnhof braucht Schlüssel")
        r = sh(sys.executable, SKRIPT, "irgendwas", check=False)
        pruefe(r.returncode and "abgeschaltet" in r.stderr, "lokaler Modus abgeschaltet")
        r = sh(sys.executable, SKRIPT, "--projekte", check=False)
        pruefe(r.stdout == "", "keine lokalen Projekte für die Vervollständigung")
        # Altformat (nur Array)
        alt = f"{T}/alt.json"
        json.dump([{"path": "Neu.cs", "needle": "class Neu", "text": "#9 Old format"}], open(alt, "w"))
        r = sh(sys.executable, SKRIPT, "agent", "pruefen", alt, "--mr", "https://gitlab.example.com/gruppe/demo/-/merge_requests/1", check=False)
        pruefe(r.returncode == 0 and "#9" in r.stdout and "Neu.cs:2" in r.stdout, "Altformat und --mr")
    finally:
        srv.terminate(); srv.wait()

def myrling_test():
    """Quelle Myrling mit tests/fake-nas-lauf: ein Waggon je anstehendem Skript, jede Datei gegen ihre eigene Basis,
    Begleitdatei aus einem anderen Repo als „fehlt“, Gespräch mit dem Agenten im Repo der Skripte."""
    w, anders, state = f"{T}/Myrling/skripte", f"{T}/Myrling/anders", f"{T}/nas-lauf"
    for o in (w, anders, state):
        os.makedirs(o)
    g = lambda *a, cwd=w: sh("git", "-C", cwd, *a).stdout.strip()
    for o in (w, anders):
        g("init", "-q", "-b", "claude", cwd=o); g("config", "user.email", "t@t", cwd=o); g("config", "user.name", "t", cwd=o)
    os.makedirs(f"{w}/nas-setup")
    skript = f"{w}/nas-setup/07-x.sh"
    open(skript, "w").write("".join(f"echo {i}\n" for i in range(1, 31))); os.chmod(skript, 0o755)
    open(f"{w}/nas-setup/09-gleich.sh", "w").write("echo gleich\n")
    open(f"{w}/sonst.txt", "w").write("eins\n")
    g("add", "-A"); g("commit", "-qm", "Start")
    c1 = g("rev-parse", "HEAD")
    open(skript, "w").write("".join(f"echo {i * 2 if i == 15 else i}\n" for i in range(1, 31)))
    open(f"{w}/nas-setup/x.conf", "w").write("a = 1\n")
    open(f"{w}/nas-setup/08-neu.sh", "w").write("echo neu\n")
    open(f"{w}/sonst.txt", "w").write("zwei\n")  # gehört zu keinem Lauf: darf in keinem Diff stehen
    g("add", "-A"); g("commit", "-qm", "Lüfter schneller\n\nRumpf.")
    c2 = g("rev-parse", "HEAD")
    open(f"{anders}/hilfe.sh", "w").write("x\n"); g("add", "-A", cwd=anders); g("commit", "-qm", "x", cwd=anders)
    datei = lambda pfad, basis, repo=w: {"name": os.path.basename(pfad), "repo": repo, "pfad": pfad, "basis": basis,
                                          "commit": g("rev-parse", "HEAD", cwd=repo)}
    liste = [{"skript": "07-x.sh", "fp": "f" * 64, "braucht": "02-grund", "stand": "geaendert", "abgelehnt": None,
              "dateien": [datei("nas-setup/07-x.sh", c1), datei("nas-setup/x.conf", None), datei("hilfe.sh", None, anders)]},
             {"skript": "08-neu.sh", "fp": "e" * 64, "braucht": "", "stand": "neu", "abgelehnt": None,
              "dateien": [datei("nas-setup/08-neu.sh", None)]},
             {"skript": "09-gleich.sh", "fp": "d" * 64, "braucht": "", "stand": "gesehen", "abgelehnt": None,
              "dateien": [datei("nas-setup/09-gleich.sh", c2)]}]
    json.dump(liste, open(f"{state}/anstehend.json", "w"))
    env = dict(ENV, MERGE_TRAIN_CONFIG=f"{T}/config/merge-train/myrling.toml", XDG_CACHE_HOME=f"{T}/cache-myrling",
               FAKE_NAS_LAUF_STATE=state)
    open(env["MERGE_TRAIN_CONFIG"], "w").write(
        f'lokal = false\ngitlab = false\nmyrling_befehl = "{sys.executable} {HIER}/fake-nas-lauf"\nport = {PORT_MYRLING}\n'
        'browser = "true"\n')
    r = subprocess.run([sys.executable, "-c", ALLES_LADEN + "import sys; m=alles_laden(sys.argv[1]); m['KONF']['myrling_befehl']='/gibt/es/nicht'; "
                        "print(m['MYRLING'].an())", SKRIPT], capture_output=True, text=True, env=env)
    pruefe(r.stdout.strip() == "False", "Myrling: ohne Befehl ist die Quelle aus" + r.stderr[-300:])
    srv = subprocess.Popen([sys.executable, SKRIPT, "--server"], env=env)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT_MYRLING}/ping", timeout=1); break
            except OSError:
                time.sleep(0.1)
        def hol(p):
            try:
                return urllib.request.urlopen(f"http://127.0.0.1:{PORT_MYRLING}{p}", timeout=60).read().decode()
            except urllib.error.HTTPError as e:
                return f"HTTP {e.code}: " + e.read().decode()
        zug = json.loads(hol("/zug.js").split("=", 1)[1].rstrip(";"))
        wagen = {x["p"]: x for x in zug["wagen"]}
        pruefe(list(wagen) == ["myrling:07-x.sh", "myrling:08-neu.sh", "myrling:09-gleich.sh"]
               and all(x["quelle"] == "myrling" and x["status"] == "offen" for x in wagen.values()),
               "Myrling: ein Waggon je anstehendem Skript – " + " ".join(wagen))
        x = wagen.get("myrling:07-x.sh") or {}
        pruefe((x.get("plus"), x.get("minus"), x.get("dateien")) == (2, 1, 3) and x.get("datei") == "/myrling/07-x.sh"
               and "braucht 02-grund" in x.get("titel", "") and "anderen Repos" in x.get("titel", ""),
               f"Myrling: Waggon mit Statistik je Datei gegen ihre Basis, braucht, fehlende Datei – {x}")
        pruefe(wagen.get("myrling:09-gleich.sh", {}).get("marke") == "● gesehen", "Myrling: Marke aus dem Stand (gesehen)")
        seite = hol("/myrling/07-x.sh")
        k = open(f"{T}/cache-myrling/merge-train/schluessel").read().strip()
        pruefe("⛭ 07-x.sh" in seite and "braucht 02-grund" in seite and "hilfe.sh" in seite and "Fehlt im Diff" in seite
               and "Lüfter schneller" in seite and 'id="feedback"' in seite and 'id="fertig"' not in seite
               and 'id="abschliessen"' not in seite and "?commit=" not in seite,
               "Myrling: Seite mit Kopf, Commits, fehlender Datei, ohne fertig/Review" + seite[:300] * seite.startswith("HTTP"))
        st = json.loads(hol(f"/api/zeilen?mr=myrling:07-x.sh&k={k}&pfad=nas-setup/07-x.sh&von=1&bis=99"))
        pruefe(st["ok"] and st["n"] == 30, "Myrling: Kontext nachladen")
        akte = json.load(open(f"{T}/data/merge-train/myrling/07-x.sh.json"))
        struktur = json.load(open(akte["struktur"]))
        pruefe([(d["neu"], d["status"]) for d in struktur["dateien"]] == [("nas-setup/07-x.sh", "geändert"), ("nas-setup/x.conf", "neu")]
               and struktur["refs"]["head_sha"] == c2 and struktur["ordner"] == w,
               "Myrling: Diff nur der Dateien des Laufs, ohne Rechte-Änderung – " + str([(d["neu"], d["status"]) for d in struktur["dateien"]]))
        basis = struktur["refs"]["base_sha"]
        pruefe(sh("git", "-C", w, "show", f"{basis}:nas-setup/07-x.sh").stdout == "".join(f"echo {i}\n" for i in range(1, 31))
               and sh("git", "-C", w, "for-each-ref").stdout.count("\n") == 1 and g("status", "--porcelain") == "",
               "Myrling: Basis ist ein eigener Commit ohne Ref, Repo unverändert")
        pruefe("Keine Unterschiede zur zuletzt angesehenen Fassung" in hol("/myrling/09-gleich.sh"), "Myrling: gesehen = leerer Diff")
        pruefe("wartet auf keine Prüfung" in hol("/myrling/10-weg.sh"), "Myrling: nicht anstehendes Skript → Güterbahnhof mit Grund")
        # Gespräch: Frage an der Zeile, der Agent im Repo der Skripte holt sie ab und antwortet
        def post_m(pfad, d):
            req = urllib.request.Request(f"http://127.0.0.1:{PORT_MYRLING}{pfad}", json.dumps(d).encode(),
                                         {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{PORT_MYRLING}"})
            with urllib.request.urlopen(req, timeout=60) as rr:
                return json.loads(rr.read())
        mb = {"mr": "myrling:07-x.sh", "k": k, "sha": c2}
        r = post_m("/api/kommentar", dict(mb, aktion="neu", datei=0, a=None, b=15, text="Warum 30?"))
        pruefe(r["ok"] and r["review"]["faeden"][0]["status"] == "entwurf", "Myrling: Frage an Zeile 15")
        fid = r["review"]["faeden"][0]["id"]
        r = post_m("/api/gespraech", dict(mb, aktion="senden"))
        log = open(env["TODO_LOG"]).read()
        pruefe(r["ok"] and "agent feedback myrling:07-x.sh" in log, "Myrling: Feedback senden → todo mit Prompt für diesen Lauf")
        agent = lambda *a: subprocess.run([sys.executable, SKRIPT, "agent", *a], cwd=w, env=env, capture_output=True, text=True)
        r = agent("feedback")
        pruefe(f"[{fid}] nas-setup/07-x.sh:15" in r.stdout and "echo 30" in r.stdout and "Lauf 07-x.sh" in r.stdout
               and "None" not in r.stdout,
               "Myrling: agent feedback im Repo findet den Lauf – " + (r.stdout + r.stderr)[-300:])
        r = agent("antworten", fid, "Weil es heiß ist.", "-p", "myrling:07-x.sh")
        rv = json.loads(hol(f"/api/review?mr=myrling:07-x.sh&k={k}"))
        f1 = next((x for x in rv["faeden"] if x["id"] == fid), {})
        pruefe(r.returncode == 0 and f1.get("status") == "antwort" and f1.get("b") == 15, "Myrling: Antwort an der Zeile – " + r.stderr[-300:])
        zug = json.loads(hol("/api/zug"))
        pruefe(next(x for x in zug["wagen"] if x["p"] == "myrling:07-x.sh").get("gs_neu") == 1, "Myrling: Zug zeigt neue Antwort")
        # neue Fassung: Faden wandert mit, Liste neu geholt beim Laden
        alt = open(skript).read()
        open(skript, "w").write("# neu\n" + alt); g("commit", "-qam", "Kopf")
        c3 = g("rev-parse", "HEAD")
        for lauf in liste:
            for d in lauf["dateien"]:
                if d["repo"] == w:
                    d["commit"] = c3
        json.dump(liste, open(f"{state}/anstehend.json", "w"))
        time.sleep(5.1)  # myrling.FRISCH
        neu = hol("/myrling/07-x.sh")
        pruefe(f"Stand {c3[:8]}" in neu, "Myrling: neue Fassung, Seite neu gebaut" + neu[:300] * neu.startswith("HTTP"))
        rv = json.loads(hol(f"/api/review?mr=myrling:07-x.sh&k={k}"))
        f1 = next((x for x in rv["faeden"] if x["id"] == fid), {})
        pruefe(f1.get("b") == 16, f"Myrling: neue Fassung, der Faden wandert mit (Zeile {f1.get('b')}, {f1.get('unter')})")
        aufrufe = open(f"{state}/aufrufe.log").read().splitlines()
        pruefe(all(a == "--anstehend --json" for a in aufrufe) and 2 <= len(aufrufe) <= 4,
               f"Myrling: Befehl nur beim Laden gefragt, nicht je Anfrage ({len(aufrufe)}×)")
    finally:
        srv.terminate(); srv.wait()


def main():
    teile = [a for a in sys.argv[1:] if not a.startswith("--")] or list(TEILE)
    unbekannt = [t for t in teile if t not in TEILE]
    if unbekannt:
        sys.exit(f"unbekannte Teile: {' '.join(unbekannt)} – es gibt: {' '.join(TEILE)}")
    for t in list(teile):
        teile += [v for v in TEILE[t] if v not in teile]
    if not os.environ.get("MERGE_TRAIN_SKRIPT"):
        r = subprocess.run([sys.executable, os.path.join(HIER, "..", "bauen"), "--ziel", SKRIPT], capture_output=True, text=True)
        pruefe(r.returncode == 0, "merge-train aus src/ gebaut (in den Testordner)")
    os.makedirs(f"{T}/config/merge-train"); os.makedirs(f"{T}/bin"); os.makedirs(f"{T}/todo/offen")
    open(f"{T}/bin/todo", "w").write(FAKE_TODO); os.chmod(f"{T}/bin/todo", 0o755)
    open(f"{T}/bin/notify-send", "w").write("#!/bin/sh\n"); os.chmod(f"{T}/bin/notify-send", 0o755)  # keine Desktop-Meldungen
    global AUSWAHL
    AUSWAHL = set(teile)
    try:
        if "gitlab" in teile:
            gitlab_test()
        if "lokal" in teile:
            lokal_test()
        if "arbeitsstand" in teile:
            arbeitsstand_test()
        if "gemischt" in teile:
            gemischt_test("gitlab.example.com/gruppe/demo/1")
        if "myrling" in teile:
            myrling_test()
        print("Teile:", " ".join(t for t in TEILE if t in teile))
    finally:
        if "--behalten" in sys.argv:
            print("Testordner:", T)
        else:
            shutil.rmtree(T, ignore_errors=True)
        if not os.environ.get("MERGE_TRAIN_SKRIPT"):
            for f in (SKRIPT, SKRIPT + ".neu"):
                if os.path.exists(f):
                    os.remove(f)
    print(f"\n{len(fehler)} Fehler" if fehler else "\nalles ok")
    return 1 if fehler else 0

sys.exit(main())
