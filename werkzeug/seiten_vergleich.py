#!/usr/bin/env python3
"""Vergleicht die Diff-Seite zweier Stände von merge-train im Browser (für Umbauten am JS: „am Verhalten ändert sich nichts“).

  python3 werkzeug/seiten_vergleich.py [REF]      REF (Standard HEAD) gegen den Arbeitsstand in src/

Baut beide Stände in einen Temp-Ordner, legt ein kleines Test-Repo an (Branches reviewed/claude) und startet je Stand einen
eigenen Server (eigene Ports und Daten, nie der des Nutzers). Dann je Stand in einem frischen Chromium (DevTools über
--remote-debugging-pipe, ohne Node) dieselben Schritte: Seite laden, Gesprächsfäden anlegen, Antwort des Agenten,
Popup mit Diff, Popup mit Code und „▲ mehr“, Meldung als Toast. Nach jedem Schritt wird das DOM genommen, Zufälliges (ids, Uhrzeiten, Ports,
Schlüssel) geglättet und verglichen. Exit 1, wenn sich ein Schritt unterscheidet; die beiden Fassungen liegen dann im
Temp-Ordner (Pfad in der Ausgabe).
"""
import difflib, json, os, re, shutil, subprocess, sys, tempfile, time, urllib.request

HIER = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, os.path.join(HIER, "perf"))
from cdp_messung import Pipe  # noqa: E402

CHROME = shutil.which("chromium") or shutil.which("google-chrome-stable") or "chromium"


def git(ordner, *a):
    return subprocess.run(["git", "-C", ordner, *a], capture_output=True, text=True, check=True).stdout


def test_repo(t):
    repo = os.path.join(t, "repo", "probe")
    os.makedirs(repo)
    git(repo, "init", "-q", "-b", "reviewed"); git(repo, "config", "user.email", "t@t"); git(repo, "config", "user.name", "t")
    schreib = lambda p, s: (os.makedirs(os.path.dirname(os.path.join(repo, p)) or repo, exist_ok=True),
                            open(os.path.join(repo, p), "w", encoding="utf-8").write(s))
    schreib("lib/rechnen.py", "".join(f"def f{i}(x):\n    return x + {i}\n\n" for i in range(60)))
    schreib("README.md", "# Probe\n\nNur zum Vergleichen.\n")
    schreib("bleibt.txt", "".join(f"zeile {i}\n" for i in range(1, 41)))
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "Anfang")
    git(repo, "checkout", "-qb", "claude")
    schreib("lib/rechnen.py", "".join(f"def f{i}(x):\n    return x + {i * (2 if i % 7 == 0 else 1)}\n\n" for i in range(60)))
    schreib("README.md", "# Probe\n\nNur zum Vergleichen, jetzt mit mehr Text.\n\n- eins\n- zwei\n")
    schreib("neu/modul.js", "export const a = 1;\nexport function b(x) {\n  return x * 2;\n}\n")
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "Änderungen")
    return repo


def bauen(t, ref):
    """REF bzw. Arbeitsstand (ref None) nach t/<name>/merge-train bauen."""
    ziel = os.path.join(t, ref or "arbeitsstand")
    os.makedirs(ziel)
    if ref:
        archiv = subprocess.run(["git", "-C", HIER, "archive", ref, "src", "bauen"], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", ziel], input=archiv, check=True)
    else:
        shutil.copytree(os.path.join(HIER, "src"), os.path.join(ziel, "src"), ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(os.path.join(HIER, "bauen"), ziel)
    subprocess.run([sys.executable, "bauen"], cwd=ziel, check=True, capture_output=True)
    return ziel


class Server:
    def __init__(self, ordner, repo, port, konfig=None, umgebung=None):
        """konfig: Inhalt der config.toml (Standard: lokal, nur repo); umgebung: zusätzliche Variablen."""
        self.port, self.ordner = port, ordner
        open(os.path.join(ordner, "config.toml"), "w").write(konfig or
            f'projekte = ["{repo}"]\ngitlab = false\nport = {port}\nleerlauf = 300\nfeedback_befehl = "true"\n')
        self.umgebung = dict(os.environ, **(umgebung or {}), MERGE_TRAIN_CONFIG=os.path.join(ordner, "config.toml"),
                             XDG_CACHE_HOME=os.path.join(ordner, "cache"), XDG_DATA_HOME=os.path.join(ordner, "data"),
                             XDG_CONFIG_HOME=os.path.join(ordner, "config"),
                             TODO_DIR=os.path.join(ordner, "todo"))  # todo-Einträge (Seite ohne Session) nicht beim Nutzer
        self.umgebung.pop("MERGE_TRAIN_INSTANZ", None)
        self.p = subprocess.Popen([sys.executable, os.path.join(ordner, "merge-train"), "--server"], env=self.umgebung,
                                  stdout=subprocess.DEVNULL, stderr=open(os.path.join(ordner, "server.log"), "w"))
        for _ in range(100):
            try:
                urllib.request.urlopen(self.url("/ping"), timeout=0.3).read(); break
            except OSError:
                time.sleep(0.1)
        self.schluessel = open(os.path.join(ordner, "cache", "merge-train", "schluessel")).read().strip()

    def url(self, pfad):
        return f"http://127.0.0.1:{self.port}{pfad}"

    def post(self, pfad, daten):
        anfrage = urllib.request.Request(self.url(pfad), json.dumps(dict(daten, k=self.schluessel)).encode(),
                                         {"Content-Type": "application/json", "Origin": self.url("")})
        return json.loads(urllib.request.urlopen(anfrage, timeout=30).read())

    def agent(self, *args):
        return subprocess.run([sys.executable, os.path.join(self.ordner, "merge-train"), "agent", *args], env=self.umgebung,
                              capture_output=True, text=True, check=True).stdout

    def antworten(self):
        """Agent antwortet auf den ersten Faden (abholen, dann antworten): ✓✓ und eine Nachricht von links."""
        self.agent("feedback", "probe")
        faeden = json.loads(urllib.request.urlopen(self.url(f"/api/review?mr=projekt:probe&k={self.schluessel}")).read())
        self.agent("antworten", faeden["faeden"][0]["id"], "Weil f7 doppelt zählt – siehe lib/rechnen.py:22", "-p", "probe")
        return []

    def zu(self):
        self.p.terminate(); self.p.wait(10)


GLAETTEN = [(r"<script\b[^>]*>.*?</script>", "<script/>"), (r"\b[0-9a-f]{40}\b", "SHA"), (r"\b[0-9a-f]{7,32}\b", "ID"), (r"\b\d\d:\d\d\b", "HH:MM"),
            (r"\b\d\d\.\d\d\.", "TT.MM."), (r"127\.0\.0\.1:\d+", "HOST"), (r"\d+(\.\d+)?ms", "MS")]


def glatt(html):
    for muster, ersatz in GLAETTEN:
        html = re.sub(muster, ersatz, html, flags=re.S)
    return re.sub(r">\s*<", ">\n<", html)


def schritte(srv):
    """(Name, JS-Ausdruck für den Schnappschuss, vorher: Python-Aktion oder JS) je Schritt."""
    seite = srv.url("/probe.html")
    dom = "document.body.outerHTML"
    popup = "(document.getElementById('popup') || {}).outerHTML || 'kein Popup'"
    return [
        ("Seite geladen", seite, None, dom),
        ("Fäden", seite, lambda sha: [srv.post("/api/kommentar", {"mr": "projekt:probe", "aktion": "neu", **f}) for f in (
            {"text": "Warum mal zwei?", "datei": 0, "a": None, "b": 2, "sha": sha},
            {"text": "Allgemein: sieht gut aus?"})], dom),
        ("Antwort des Agenten", seite, lambda sha: srv.antworten(), dom),
        ("Popup mit Diff", None, "App.popup('lib/rechnen.py', 15, 'Siehe auch')", popup),
        ("Popup mit Code", None, "document.getElementById('schleier').click(); App.popup('bleibt.txt', 20, '', 22)", popup),
        ("Popup mehr laden", None, "document.querySelector('#popup .knoepfe button').click()", popup),
        ("Toast", None, "document.getElementById('schleier').click(); App.melden('Probe-Meldung')",
         "document.getElementById('toasts').outerHTML"),
    ]


def aufnehmen(srv, ablage):
    c = Pipe(CHROME, False)
    try:
        ziel = c.rufen("Target.createTarget", {"url": "about:blank"})["targetId"]
        s = c.rufen("Target.attachToTarget", {"targetId": ziel, "flatten": True})["sessionId"]
        c.rufen("Page.enable", sitzung=s)
        auswerten = lambda js: c.rufen("Runtime.evaluate", {"expression": js, "returnByValue": True, "awaitPromise": True},
                                       sitzung=s).get("result", {}).get("value")
        sha = None
        for name, url, vorher, schnappschuss in schritte(srv):
            if callable(vorher):
                if sha is None:  # Klick auf eine Zeile braucht den Stand der Seite
                    sha = auswerten("App.waggon.sha")
                for f in vorher(sha):
                    if not f.get("ok"):
                        sys.exit(f"{name}: {f.get('text')}")
            if url:
                c.rufen("Page.navigate", {"url": url}, sitzung=s)
                c.warten("Page.loadEventFired", s)
            elif vorher:
                auswerten(vorher)
            time.sleep(1.5)
            ablage[name] = glatt(auswerten(schnappschuss) or "")
    finally:
        c.zu()


def main():
    ref = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    t = tempfile.mkdtemp(prefix="merge-train-vergleich-")
    repo = test_repo(t)
    staende = {"alt": bauen(t, ref), "neu": bauen(t, None)}
    ergebnis = {}
    for i, (name, ordner) in enumerate(staende.items()):
        srv = Server(ordner, repo, 8795 + i)
        try:
            ergebnis[name] = {}
            aufnehmen(srv, ergebnis[name])
        finally:
            srv.zu()
    anders = 0
    for schritt in ergebnis["alt"]:
        a, b = ergebnis["alt"][schritt], ergebnis["neu"].get(schritt, "")
        if a == b:
            print(f"gleich   {schritt} ({len(a)} Zeichen)")
            continue
        anders += 1
        datei = os.path.join(t, re.sub(r"\W+", "-", schritt.lower()))
        open(datei + ".alt.html", "w").write(a); open(datei + ".neu.html", "w").write(b)
        print(f"ANDERS   {schritt}: {datei}.alt.html / .neu.html")
        for z in list(difflib.unified_diff(a.split("\n"), b.split("\n"), "alt", "neu", n=1, lineterm=""))[:20]:
            print("         " + z[:160])
    if anders:
        sys.exit(f"\n{anders} Schritt(e) unterschiedlich ({ref} → Arbeitsstand)")
    shutil.rmtree(t, ignore_errors=True)
    print(f"{ref} → Arbeitsstand: alle {len(ergebnis['alt'])} Schritte gleich")


if __name__ == "__main__":
    main()
