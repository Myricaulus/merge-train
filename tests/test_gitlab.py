#!/usr/bin/env python3
"""Ende-zu-Ende-Test des GitLab-Modus mit tests/fake-glab (kein echtes GitLab nötig).

Aufruf:  python3 tests/test_gitlab.py [--behalten]
Legt alles in einem Temp-Ordner an (eigene XDG-Ordner, Port 8799), startet einen eigenen Server.
"""
import runpy, json, os, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
SKRIPT = os.path.join(HIER, "..", "merge-train")
PORT = 8799
T = tempfile.mkdtemp(prefix="merge-train-test-")
REPO = os.path.join(T, "repo")
ENV = dict(os.environ, XDG_CONFIG_HOME=f"{T}/config", XDG_CACHE_HOME=f"{T}/cache", XDG_DATA_HOME=f"{T}/data",
           MERGE_TRAIN_CONFIG=f"{T}/config/merge-train/config.toml",
           FAKE_GLAB_REPO=REPO, FAKE_GLAB_STATE=f"{T}/glab")
fehler = []

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
    os.makedirs(f"{T}/bin"); os.makedirs(f"{T}/todo/offen")
    open(f"{T}/bin/todo", "w").write(FAKE_TODO); os.chmod(f"{T}/bin/todo", 0o755)
    open(f"{T}/bin/notify-send", "w").write("#!/bin/sh\n"); os.chmod(f"{T}/bin/notify-send", 0o755)  # keine Desktop-Meldungen
    env = dict(ENV, MERGE_TRAIN_CONFIG=f"{T}/config/merge-train/lokal.toml", XDG_CACHE_HOME=f"{T}/cache-lokal",
               PATH=f"{T}/bin:" + os.environ["PATH"], TODO_DIR=f"{T}/todo", TODO_LOG=f"{T}/todo.log")
    open(env["MERGE_TRAIN_CONFIG"], "w").write(f'lokal = true\ngitlab = false\nprojekte = "{T}/Projects"\nport = 8798\nbrowser = "true"\n')
    srv = subprocess.Popen([sys.executable, SKRIPT, "--server"], env=env)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen("http://127.0.0.1:8798/ping", timeout=1); break
            except OSError:
                time.sleep(0.1)
        hol = lambda p: urllib.request.urlopen(f"http://127.0.0.1:8798{p}", timeout=60).read().decode()
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
        horchen_waise_test(proj, env, k, hol)
        horchen_seite_zu_test(proj, env, k, hol)
    finally:
        srv.terminate(); srv.wait()

def gespraech_test(proj, env, k, hol, g):
    """Gespräch im lokalen Modus: Frage an einer Zeile → Feedback senden → Agent holt ab und antwortet."""
    port = 8798
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
    alt = open(f"{proj}/a.py").read()
    open(f"{proj}/a.py", "w").write("# Kopf\n# noch einer\n" + alt)
    g("commit", "-qam", "Kopfzeilen")
    hol("/proj.html")  # Seite zum neuen Stand; die Fäden werden auf den Stand der Seite umgerechnet
    rv = json.loads(hol(f"/api/review?mr=projekt:proj&k={k}"))
    f1 = next(x for x in rv["faeden"] if x["id"] == fid)
    pruefe(f1["b"] == 22 and f1["im_diff"], "Gespräch: nach neuem Commit steht der Faden an Zeile 22")
    r = post_l("/fertig", {"projekt": "proj", "sha": g("rev-parse", "claude"), "k": k})
    rv = json.loads(hol(f"/api/review?mr=projekt:proj&k={k}"))
    pruefe(r["ok"] and not rv["faeden"], "Gespräch: fertig räumt erledigte Fäden weg")

def horchen_waise_test(proj, env, k, hol):
    """Endet die Agenten-Session, hört horchen auf, und die Seite zeigt niemanden mehr als Zuhörer."""
    os.symlink("/bin/sh", f"{T}/bin/agentx")  # ein „Agent“ mit eigenem Prozessnamen
    ag = subprocess.Popen([f"{T}/bin/agentx", "-c", f'"{sys.executable}" "{SKRIPT}" agent horchen --als Fake; true'], cwd=proj, env=env)
    wer = None
    for _ in range(50):
        wer = json.loads(hol(f"/api/review?mr=projekt:proj&k={k}")).get("horcht")
        if wer == "Fake":
            break
        time.sleep(0.1)
    pruefe(wer == "Fake", "horchen: Seite zeigt den Zuhörer")
    datei = f"{T}/data/merge-train/lokal/proj.horcht"
    ag.kill(); ag.wait()  # Session hart beendet: horchen ist jetzt verwaist
    for _ in range(50):
        if not os.path.exists(datei):
            break
        time.sleep(0.1)
    pruefe(not os.path.exists(datei), "horchen: beendet sich, wenn die Agenten-Session weg ist")
    pruefe(json.loads(hol(f"/api/review?mr=projekt:proj&k={k}")).get("horcht") is None, "horchen: Seite zeigt danach niemanden")

def horchen_seite_zu_test(proj, env, k, hol):
    """Wird die Seite geschlossen (kein Lebenszeichen mehr), hört horchen auf – aber erst, wenn sie nach dem Start da war."""
    lau = subprocess.Popen([sys.executable, SKRIPT, "agent", "horchen", "--timeout", "20"], cwd=proj, stdout=subprocess.PIPE,
                           text=True, env=dict(env, MERGE_TRAIN_SEITE_WEG_S="2"))
    time.sleep(3)
    pruefe(lau.poll() is None, "horchen: ohne Seite seit dem Start läuft es weiter")
    hol(f"/api/stand?mr=projekt:proj&k={k}")  # Seite meldet sich einmal, dann nicht mehr
    aus, _ = lau.communicate(timeout=20)
    pruefe("Seite geschlossen" in aus, "horchen: hört auf, wenn die Seite kein Lebenszeichen mehr schickt")

def gemischt_test(mr):
    """Beide Quellen an: ein Zug mit lokalen Waggons und MRs, jede Seite mit den Knöpfen ihrer Quelle."""
    env = dict(ENV, MERGE_TRAIN_CONFIG=f"{T}/config/merge-train/gemischt.toml", PATH=f"{T}/bin:" + os.environ["PATH"],
               TODO_DIR=f"{T}/todo", TODO_LOG=f"{T}/todo.log")
    open(env["MERGE_TRAIN_CONFIG"], "w").write(
        f'lokal = true\ngitlab = true\nglab = "{sys.executable} {HIER}/fake-glab"\nprojekte = "{T}/Projects"\n'
        f'port = 8797\nbrowser = "true"\n')
    srv = subprocess.Popen([sys.executable, SKRIPT, "--server"], env=env)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen("http://127.0.0.1:8797/ping", timeout=1); break
            except OSError:
                time.sleep(0.1)
        hol = lambda p: urllib.request.urlopen(f"http://127.0.0.1:8797{p}", timeout=60).read().decode()
        # neuer lokaler Stand, damit der lokale Waggon wieder offen ist
        proj = f"{T}/Projects/proj"
        open(f"{proj}/c.py", "w").write("neu = 1\n")
        sh("git", "-C", proj, "add", "-A"); sh("git", "-C", proj, "commit", "-qm", "Dritter Schritt")
        zug = hol("/zug.js?akt=" + urllib.parse.quote(mr))
        z = json.loads(zug[len("window.MR_ZUG="):-1])
        quellen = {w["quelle"]: w for w in z["wagen"]}
        pruefe(set(quellen) == {"lokal", "gitlab"} and quellen["lokal"]["p"] == "proj" and quellen["gitlab"]["p"] == mr,
               "gemischt: ein Zug mit lokalem Waggon und MR")
        pruefe([w["quelle"] for w in z["wagen"]][0] == "lokal", "gemischt: lokale Waggons vorn")
        ms = hol("/mr/" + mr)
        pruefe('id="abschliessen"' in ms and 'id="fertig"' not in ms and 'data-l="neu"' in ms and 'data-g="mrliste"' in ms,
               "gemischt: MR-Seite mit Review-Knopf, Leitstand beider Quellen")
        ls_ = hol("/proj.html")
        pruefe('id="fertig"' in ls_ and 'id="abschliessen"' not in ls_ and 'data-g="mrliste"' in ls_, "gemischt: lokale Seite mit fertig")
        start = urllib.request.urlopen("http://127.0.0.1:8797/", timeout=60)
        pruefe(start.geturl().endswith("/proj.html"), "gemischt: Start springt zum offenen lokalen Waggon")
    finally:
        srv.terminate(); srv.wait()

def mr_gespraech_test(mr, k, basis, struktur):
    """Fragen an einen Agenten zum MR: eigene Datei, nie im Review, agent feedback/antworten/horchen mit MR-Kennung."""
    genv = dict(ENV, PATH=f"{T}/gl-bin:" + os.environ["PATH"])
    i_app = next(i for i, f in enumerate(struktur["dateien"]) if f["neu"] == "App.cs")
    vorher = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    pruefe(vorher["agenten"] == ["Copilot"] and vorher["faeden"] == [], "MR-Gespräch: Agent aus [agenten] angeboten")
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
    pruefe(f"merge-train agent feedback {mr}" in prompt and "nichts committen" in prompt, "MR-Gespräch: Prompt nennt MR und verbietet Commits")
    r = sh(sys.executable, SKRIPT, "agent", "feedback", mr, env=genv, check=False)
    pruefe(r.returncode == 0 and f'[{f["id"]}] App.cs:11' in r.stdout and "an Copilot" in r.stdout and "Was macht Zeile 11?" in r.stdout,
           "MR-Gespräch: agent feedback mit MR-Kennung")
    r = sh(sys.executable, SKRIPT, "agent", "feedback", cwd=REPO, env=genv, check=False)
    pruefe(r.returncode == 0 and "gruppe/demo!1" in r.stdout, "MR-Gespräch: agent feedback im Klon findet den MR")
    r = sh(sys.executable, SKRIPT, "agent", "antworten", f["id"][:6], "Sie loggt.", env=genv, check=False)
    pruefe(r.returncode == 0 and "nichts mehr offen" in r.stdout, "MR-Gespräch: agent antworten (sucht in allen Gesprächen)")
    rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    m = rv["faeden"][0]["nachrichten"][-1]
    pruefe(rv["faeden"][0]["status"] == "antwort" and m["text"] == "Sie loggt." and m["wer"] == "Copilot", "MR-Gespräch: Antwort von Copilot auf der Seite")
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
    st = json.load(open(f'{T}/data/merge-train/reviews/gitlab.example.com_gruppe_demo_1.json'))
    pruefe(any(k.get("nachrichten") for k in st["kommentare"]), "MR-Gespräch: Faden liegt in der Datei des Waggons")
    sh(sys.executable, SKRIPT, "agent", "antworten", f["id"], "Weil.", "--erledigt", env=genv, check=False)
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
    r = sh(sys.executable, SKRIPT, "agent", "kommentar", "h:" + neu[0]["key"], "Shortest.", env=genv, check=False)
    rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    pruefe(r.returncode == 0 and len(rv["hinweise"]) == nh + 2 and any(h["text"] == "Shortest." for h in rv["hinweise"]),
           "Kommentar umformulieren: eigenen draft nochmal ändern")
    h = next(h for h in rv["hinweise"] if h["text"] == "Shortest.")
    r = post("/api/kommentar", dict(basis, aktion="neu", hinweis=h["key"]))
    rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
    pruefe(r["ok"] and len(rv["kommentare"]) == n + 1, "Kommentar umformulieren: staged erst durch „übernehmen“")
    for x in rv["kommentare"]:
        if x["id"] == km["id"] or x["text"] == "Shortest.":
            post("/api/kommentar", dict(basis, aktion="loeschen", id=x["id"]))
    pruefe(not os.path.exists(f'{T}/data/merge-train/reviews/gitlab.example.com_gruppe_demo_1.agent.json'),
           "Kommentar umformulieren: drafts in der Review-JSON, keine eigene Datei")
    open(hw, "w", encoding="utf-8").write(sicher)
    pruefe(sh(sys.executable, SKRIPT, "agent", "kommentar", "gibtsnicht", "x", env=genv, check=False).returncode == 2,
           "Kommentar umformulieren: unbekanntes Ziel")

def main():
    r = subprocess.run([sys.executable, os.path.join(HIER, "..", "bauen")], capture_output=True, text=True)
    pruefe(r.returncode == 0, "merge-train aus src/ gebaut")
    if shutil.which("node"):  # Syntaxfehler im Seiten-Skript legen die ganze Seite lahm, ohne dass ein Test es merkt
        m = runpy.run_path(SKRIPT, run_name="pruefen")
        js = os.path.join(T, "seite.js")
        open(js, "w", encoding="utf-8").write("".join(m[n] for n in ("JS", "JS_ZUG", "JS_DIFF", "JS_REVIEW", "JS_BAHNHOF")))
        r = subprocess.run(["node", "--check", js], capture_output=True, text=True)
        pruefe(r.returncode == 0, "Seiten-Skript ohne Syntaxfehler" + (": " + r.stderr.strip().splitlines()[-1] if r.returncode else ""))
    repo_anlegen()
    os.makedirs(f"{T}/config/merge-train")
    open(ENV["MERGE_TRAIN_CONFIG"], "w").write(
        f'lokal = false\nglab = "{sys.executable} {HIER}/fake-glab"\nport = {PORT}\nbrowser = "true"\n'
        f'hinweise = ["{REPO}/tasks/*-review-markers.json"]\n'
        f'[agenten]\nCopilot = "{T}/gl-bin/copilot {{prompt}}"\n')  # Gespräch zum MR: Ersatz-Agent schreibt den Prompt mit
    os.makedirs(f"{T}/gl-bin")
    open(f"{T}/gl-bin/copilot", "w").write(f'#!/bin/sh\necho "$1" > {T}/copilot.prompt\n'); os.chmod(f"{T}/gl-bin/copilot", 0o755)
    open(f"{T}/gl-bin/notify-send", "w").write("#!/bin/sh\n"); os.chmod(f"{T}/gl-bin/notify-send", 0o755)
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
        pruefe("http://127.0.0.1:8799/mr/gitlab.example.com/gruppe/demo/1" in r.stdout, "zeigen gibt MR-URL aus")
        pruefe("Quelle: lokal" in r.stdout, "Repo der Hinweis-Datei wird als lokaler Klon genutzt")
        pruefe("#7" in r.stdout and "allgemeiner MR-Kommentar" in r.stdout, "Eintrag ohne Pfad = allgemeiner Kommentar, kein FEHLT")
        pruefe("siehe auch" not in r.stdout, "see_also aufgelöst")
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
        i_gen = next(i for i, f in enumerate(json.load(open(json.load(open(f'{T}/data/merge-train/reviews/gitlab.example.com_gruppe_demo_1.json'))["struktur"]))["dateien"]) if f["neu"] == "Modell.Designer.cs")
        z = json.loads(get(f"/api/datei?mr={mr}&k={k}&i={i_gen}"))
        pruefe(z["ok"] and 'class="sbs"' in z["html"] and "Modell" in z["html"], "generierte Datei nachladen")
        pruefe(not json.loads(get(f"/api/datei?mr={mr}&k={k}&i=-1"))["ok"], "ungültiger Datei-Index abgelehnt")
        pruefe('class="inl"' not in seite, "Inline-Tabelle baut erst der Browser")
        pruefe(rv["quellen"][0]["notes"] == "Team-Thema: Logging" and rv["quellen"][0]["alt"], "Notizen und veralteter Stand")
        pruefe(json.loads(get(f"/api/review?mr={mr}&k=falsch"))["ok"] is False, "falscher Schlüssel abgelehnt")
        sha = rv["hinweise"][0] and json.load(open(rv and f'{T}/data/merge-train/reviews/gitlab.example.com_gruppe_demo_1.json'))
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
        st = {h["finding"]: h["status"] for h in r["review"]["hinweise"]}
        pruefe(st["#1"] == "uebernommen" and st["#5"] == "verworfen" and st["#4"] == "offen", "Hinweis-Status")
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
        pruefe(next(x for x in rv["kommentare"] if x["text"] == "Insgesamt sehr gut.")["status"] == "weg", "veröffentlichter bleibt sent")
        # andere Abrufzeit der MR-Daten (wie ein späterer Klick auf „↻ MR-Daten“): Seite nicht neu bauen
        rp0 = f'{T}/data/merge-train/reviews/gitlab.example.com_gruppe_demo_1.json'
        get(f"/mr/{mr}"); vor = json.load(open(rp0))["struktur"]
        zst = json.load(open(rp0)); zst["meta"]["_zeit"] = "01.01. 00:00"; json.dump(zst, open(rp0, "w"))
        get(f"/mr/{mr}")
        pruefe(json.load(open(rp0))["struktur"] == vor, "MR-Daten: andere Abrufzeit baut die Seite nicht neu")
        r1 = post("/api/gitlab", dict(basis, aktion="mrdaten"))
        r2 = post("/api/gitlab", dict(basis, aktion="mrdaten"))
        pruefe(r1["ok"] and r2["ok"] and r2["neu_laden"] is False, "MR-Daten unverändert: Seite muss nicht neu laden")
        zst = json.load(open(rp0)); zst["meta"]["title"] = "Alter Titel"; json.dump(zst, open(rp0, "w"))
        get(f"/mr/{mr}")
        r = post("/api/gitlab", dict(basis, aktion="mrdaten"))
        pruefe(r["ok"] and r["neu_laden"] is True and "Alter Titel" not in get(f"/mr/{mr}"), "MR-Daten geändert (Titel): Seite lädt neu")
        # früher als „weg“ markiert, aber gar nicht veröffentlicht (altes Verhalten) → MR-Daten holt ihn zurück
        rp = f'{T}/data/merge-train/reviews/gitlab.example.com_gruppe_demo_1.json'
        zst = json.load(open(rp))
        alt = next(x for x in zst["kommentare"] if x.get("gitlab_id") and x.get("nachrichten") is None and x["text"] != "Insgesamt sehr gut.")
        alt["gitlab_weg"] = True
        json.dump(zst, open(rp, "w"))
        json.dump([x for x in drafts() if x["id"] != alt["gitlab_id"]], open(f"{T}/glab/drafts.json", "w"))
        r = post("/api/gitlab", dict(basis, aktion="mrdaten"))
        rv = json.loads(get(f"/api/review?mr={mr}&k={k}"))
        pruefe(r["ok"] and next(x for x in rv["kommentare"] if x["id"] == alt["id"])["status"] == "neu"
               and next(x for x in rv["kommentare"] if x["text"] == "Insgesamt sehr gut.")["status"] == "weg",
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
        st2 = json.load(open(f'{T}/data/merge-train/reviews/gitlab.example.com_gruppe_demo_1.json'))
        sv = json.load(open(next(p[:-5] + ".json" for p in [os.path.join(f"{T}/cache/merge-train/mr", f) for f in os.listdir(f"{T}/cache/merge-train/mr")]
                                 if f"-seit{c1[:12]}-" in p and p.endswith(".html"))))
        i_v = next(i for i, f in enumerate(sv["dateien"]) if f["neu"] == "App.cs")
        r = post("/api/kommentar", dict(basis2, ansicht=sa, aktion="neu", datei=i_v, a=None, b=4, text="Eingefügt?"))
        kn = r["ok"] and next(x for x in json.load(open(f'{T}/data/merge-train/reviews/gitlab.example.com_gruppe_demo_1.json'))["kommentare"] if x.get("text") == "Eingefügt?")
        pruefe(kn and kn["b"] == 4 and kn["a"] is None, "Seit-Ansicht: Kommentar wird auf die MR-Zeile (neu 4, im MR hinzugefügt) gelegt")
        pruefe(not post("/api/kommentar", dict(basis2, ansicht=sa, aktion="neu", datei=i_v, a=3, b=None, text="x"))["ok"],
               "Seit-Ansicht: alte Seite nicht kommentierbar")
        pruefe(st2["struktur"] == json.load(open(f'{T}/data/merge-train/reviews/gitlab.example.com_gruppe_demo_1.json'))["struktur"]
               and "-seit" not in st2["struktur"] and "-commit" not in st2["struktur"], "Ansichten ändern die Struktur des MR nicht")
        pruefe("gehört nicht zu diesem MR" in get(f"/mr/{mr}?commit={start}") and "ungültig" in get(f"/mr/{mr}?seit=xyz"),
               "fremder Commit / ungültige sha abgelehnt")
        # Übersicht, Zug, lokal=false
        pruefe("Güterbahnhof" in get("/") and "Demo-Änderung" not in get("/"), "Startseite ohne MR-Liste (lokal = false)")
        r = post("/api/gitlab", dict(k=k, aktion="mrliste"))
        z = json.loads(get("/api/zug?akt=" + mr))
        pruefe(r["ok"] and any(w["name"] == "!1 demo" and "Demo-Änderung" in w["titel"] for w in z["wagen"]) and z["zeit"],
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
        lokal_test()
        gemischt_test(mr)
    finally:
        srv.terminate()
        if "--behalten" in sys.argv:
            print("Testordner:", T)
        else:
            shutil.rmtree(T, ignore_errors=True)
    print(f"\n{len(fehler)} Fehler" if fehler else "\nalles ok")
    return 1 if fehler else 0

sys.exit(main())
