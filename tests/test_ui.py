#!/usr/bin/env python3
"""UI-Tests im echten Browser: Knöpfe der Diff-Seite klicken und prüfen, was beim Server ankommt.

  python3 tests/test_ui.py [fall[:teil] …]      Fälle: lokal, ohne, mr, mr-ohne (Standard: alle mit allen Teilen)

Fälle: lokal (Test-Repo aus werkzeug/seiten_vergleich.py, „senden“ startet einen Befehl), ohne (dasselbe, aber kein
Agent eingerichtet), mr (MR !1 über tests/fake-glab, Agent Claude aus [agenten]), mr-ohne (MR ohne Agent). Baut den Arbeitsstand aus src/ in
einen Temp-Ordner, startet je Fall einen eigenen Server (eigener Port und Daten, nie der des Nutzers) und ein frisches
headless Chromium (DevTools über --remote-debugging-pipe, ohne Node). Ohne Chromium: übersprungen (Exit 0).
JS-Fehler auf der Seite (Runtime.exceptionThrown) lassen jeden Teil scheitern.
"""
import glob, json, os, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request

HIER = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path[:0] = [os.path.join(HIER, "werkzeug"), os.path.join(HIER, "perf")]
from cdp_messung import Pipe  # noqa: E402
from seiten_vergleich import Server, bauen, git, test_repo  # noqa: E402


def chromium():
    for name in ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome"):
        if shutil.which(name):
            return shutil.which(name)
    treffer = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")))
    return treffer[-1] if treffer else None


class Browser:
    def __init__(self, exe):
        self.c = Pipe(exe, False)
        ziel = self.c.rufen("Target.createTarget", {"url": "about:blank"})["targetId"]
        self.s = self.c.rufen("Target.attachToTarget", {"targetId": ziel, "flatten": True})["sessionId"]
        self.c.rufen("Page.enable", sitzung=self.s)
        self.c.rufen("Runtime.enable", sitzung=self.s)

    def laden(self, url):
        self.c.rufen("Page.navigate", {"url": url}, sitzung=self.s)
        self.c.warten("Page.loadEventFired", self.s)

    def js(self, ausdruck):
        r = self.c.rufen("Runtime.evaluate", {"expression": ausdruck, "returnByValue": True, "awaitPromise": True},
                         sitzung=self.s)
        if "exceptionDetails" in r:
            raise AssertionError(f"JS-Fehler in {ausdruck!r}: {r['exceptionDetails'].get('exception', {}).get('description')}")
        return r.get("result", {}).get("value")

    def warten_bis(self, ausdruck, timeout=8):
        ende = time.time() + timeout
        while time.time() < ende:
            if self.js(f"!!({ausdruck})"):
                return
            time.sleep(0.1)
        raise AssertionError(f"wurde nicht wahr: {ausdruck} (Meldung der Seite: {self.js('App.meldung.textContent')!r})")

    def tippen(self, text):
        self.c.rufen("Input.insertText", {"text": text}, sitzung=self.s)

    def taste(self, taste):
        for art in ("keyDown", "keyUp"):
            self.c.rufen("Input.dispatchKeyEvent", {"type": art, "key": taste, **({"text": taste} if len(taste) == 1 and art == "keyDown" else {})},
                         sitzung=self.s)

    def klicken(self, selektor):
        """Echter Mausklick auf die Mitte des Elements (trifft nur, was sichtbar und nicht verdeckt ist)."""
        # erst scrollen und zwei Frames warten: das Scrollen kann das Layout noch verschieben (Seitenleiste wird ganz
        # oben um den Himmel kürzer), dann erst die Koordinaten nehmen
        self.js(f"(e => e && e.scrollIntoView({{block: 'center'}}))(document.querySelector({json.dumps(selektor)}))")
        self.js("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        r = self.js(f"(() => {{ const e = document.querySelector({json.dumps(selektor)}); if (!e) return null;"
                    "const r = e.getBoundingClientRect();"
                    "const x = r.x + r.width / 2, y = r.y + r.height / 2, oben = document.elementFromPoint(x, y);"
                    "return [x, y, e.disabled || e.hidden, e.contains(oben) ? null : oben && oben.outerHTML.slice(0, 120)]; })()")
        if r is None:
            raise AssertionError(f"{selektor} fehlt auf der Seite")
        x, y, aus, verdeckt = r
        if aus:
            raise AssertionError(f"{selektor} ist ausgegraut oder versteckt")
        if verdeckt:
            raise AssertionError(f"{selektor} ist verdeckt von {verdeckt}")
        for art in ("mousePressed", "mouseReleased"):
            self.c.rufen("Input.dispatchMouseEvent", {"type": art, "x": x, "y": y, "button": "left", "clickCount": 1},
                         sitzung=self.s)

    def fehler(self):
        """JS-Ausnahmen der Seite seit dem letzten Aufruf."""
        f = [m["params"]["exceptionDetails"] for m in self.c.events if m.get("method") == "Runtime.exceptionThrown"]
        self.c.events = [m for m in self.c.events if m.get("method") != "Runtime.exceptionThrown"]
        return [(d.get("exception") or {}).get("description") or d.get("text") for d in f]

    def zu(self):
        self.c.zu()


class Fall:
    """Ein Server mit einer Seite: mr = Kennung für die API, pfad = URL der Seite."""
    def __init__(self, srv, mr, pfad, startet, ziel, repo):
        """ziel: (Zielbranch, Datei, Zeile, Text dort) – eine Zeile, die im Stand der Seite anders lautet (siehe_ziel).
        repo: das Repo bzw. der Klon des Waggons."""
        self.srv, self.mr, self.pfad, self.startet, self.ziel, self.repo = srv, mr, pfad, startet, ziel, repo

    def faeden(self):
        q = urllib.parse.urlencode({"mr": self.mr, "k": self.srv.schluessel})
        return json.loads(urllib.request.urlopen(self.srv.url(f"/api/review?{q}")).read())["faeden"]

    def horcht(self):
        q = urllib.parse.urlencode({"mr": self.mr, "k": self.srv.schluessel})
        return json.loads(urllib.request.urlopen(self.srv.url(f"/api/review?{q}")).read()).get("horcht")

    def gesendet(self):
        return [m for k in self.faeden() for m in k["nachrichten"] if m["von"] == "ich" and m.get("gesendet")]

    def gesendet_warten(self, n, timeout=8):
        ende = time.time() + timeout
        while time.time() < ende:
            if len(self.gesendet()) >= n:
                return
            time.sleep(0.1)
        raise AssertionError(f"nach {timeout} s nicht {n} gesendet: {self.faeden()}")

    def entwurf(self, text):
        d = self.srv.post("/api/kommentar", {"mr": self.mr, "aktion": "neu", "gespraech": 1, "an": "Claude", "text": text})
        assert d.get("ok"), d


def fall_lokal(t, port, agent=True):
    ordner = bauen(t, None)
    repo = test_repo(t)
    for i in range(60):  # genug Dateien, dass die Liste links scrollt
        open(os.path.join(repo, f"viele_{i:02}.txt"), "w").write("".join(f"zeile {j}\n" for j in range(30)))
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "viele Dateien")
    konfig = f'projekte = ["{repo}"]\ngitlab = false\nport = {port}\nleerlauf = 300\n' + ('feedback_befehl = "true"\n' if agent else "")
    return Fall(Server(ordner, repo, port, konfig), "projekt:probe", "/probe.html", agent,
                ("reviewed", "README.md", 3, "Nur zum Vergleichen."), repo)


def fall_mr(t, port, agent=True):
    ordner = bauen(t, None)
    repo = os.path.join(t, "mr-repo")
    os.makedirs(os.path.join(repo, "tasks"))
    git(repo, "init", "-q", "-b", "main"); git(repo, "config", "user.email", "t@t"); git(repo, "config", "user.name", "t")
    git(repo, "remote", "add", "origin", "git@gitlab.example.com:gruppe/demo.git")
    open(os.path.join(repo, "App.cs"), "w").write("".join(f"// Zeile {i}\n" for i in range(1, 31)))
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "Start"); git(repo, "checkout", "-qb", "feature")
    open(os.path.join(repo, "App.cs"), "w").write("".join(f"// Zeile {i}{' neu' if i == 10 else ''}\n" for i in range(1, 31)))
    git(repo, "add", "App.cs"); git(repo, "commit", "-qm", "Neu")
    hw = os.path.join(repo, "tasks", "DEMO-1-review-markers.json")
    json.dump({"key": "DEMO-1", "branch": "feature", "agent": "Claude",
               "markers": [{"path": "App.cs", "needle": "Zeile 10 neu", "text": "Hinweis"}]}, open(hw, "w"))
    os.makedirs(os.path.join(t, "glab"))
    konfig = (f'lokal = false\nglab = "{sys.executable} {HIER}/tests/fake-glab"\nport = {port}\nleerlauf = 300\n'
              f'browser = "true"\nhinweise = ["{repo}/tasks/*-review-markers.json"]\n' + ('[agenten]\nClaude = "true"\n' if agent else ""))
    srv = Server(ordner, repo, port, konfig, {"FAKE_GLAB_REPO": repo, "FAKE_GLAB_STATE": os.path.join(t, "glab")})
    subprocess.run([sys.executable, os.path.join(ordner, "merge-train"), "agent", "zeigen", hw, "--nicht-oeffnen"],
                   env=dict(srv.umgebung, MERGE_TRAIN_AGENT="Claude"), capture_output=True, check=True, cwd=repo)
    return Fall(srv, "gitlab.example.com/gruppe/demo/1", "/mr/gitlab.example.com/gruppe/demo/1", agent,
                ("main", "App.cs", 10, "// Zeile 10"), repo)


FAELLE = {"lokal": fall_lokal, "ohne": lambda t, port: fall_lokal(t, port, agent=False), "mr": fall_mr,
          "mr-ohne": lambda t, port: fall_mr(t, port, agent=False)}


def seite(b, f, vorher=False, sofort=False):
    b.laden(f.srv.url(f.pfad))
    b.js(f"localStorage.promptVorher = {'1' if vorher else chr(39) * 2}; localStorage.sofort = {'1' if sofort else chr(39) * 2}")
    b.laden(f.srv.url(f.pfad))
    b.warten_bis("typeof App.zeichnen === 'function' || document.getElementById('feedback')")


def dialog_text(b):
    b.warten_bis("document.querySelector('dialog.prompt-dialog[open] pre')")
    return b.js("[...document.querySelectorAll('dialog.prompt-dialog summary, dialog.prompt-dialog pre')]"
                ".map(x => x.textContent).join('\\n')")


def dialog_zu(b, knopf):
    b.js(f"[...document.querySelectorAll('dialog.prompt-dialog button')].find(x => x.textContent === '{knopf}').click()")
    b.warten_bis("!document.querySelector('dialog.prompt-dialog')")


def teil_senden(b, f):
    """„An Agent senden“ schickt den Entwurf ab (ohne Vorschau)."""
    vorher = len(f.gesendet())
    f.entwurf("Warum mal zwei?")
    seite(b, f)
    assert b.js("[...document.querySelectorAll('label.sofort')].some(l => !l.closest('.kbox'))"), "kein „sofort senden“ im Kopf"
    b.warten_bis("!document.getElementById('feedback').disabled")
    b.klicken("#feedback")
    f.gesendet_warten(vorher + 1)


def teil_vorschau(b, f):
    """Mit „vor dem Senden zeigen“: erst der Dialog mit dem Text beim Abholen (auch ohne Agent), abbrechen sendet
    nichts, „senden“ schon."""
    f.entwurf("Vorschau bitte")
    vorher = len(f.gesendet())
    seite(b, f, vorher=True)
    b.warten_bis("!document.getElementById('feedback').disabled")
    b.klicken("#feedback")
    text = dialog_text(b)
    assert "Vorschau bitte" in text and "beim Abholen" in text, text
    assert ("Startprompt" in text) == f.startet, text
    dialog_zu(b, "abbrechen")
    time.sleep(1)
    assert len(f.gesendet()) == vorher, "abbrechen hat gesendet"
    b.klicken("#feedback")
    b.warten_bis("document.querySelector('dialog.prompt-dialog[open] .pd-senden')")
    b.klicken("dialog.prompt-dialog .pd-senden")
    f.gesendet_warten(vorher + 1)


def teil_zuletzt(b, f):
    """„📨“ nach dem Senden: was noch nicht abgeholt ist (so bekommt es der Agent) und ggf. der Startprompt."""
    f.entwurf("Und was kam an?")
    vorher = len(f.gesendet())
    seite(b, f)
    b.warten_bis("!document.getElementById('feedback').disabled")
    b.klicken("#feedback")
    f.gesendet_warten(vorher + 1)
    b.klicken("#prompt")
    text = dialog_text(b)
    assert "Und was kam an?" in text and "noch nicht abgeholt" in text, text
    assert ("Startprompt" in text) == f.startet, text
    dialog_zu(b, "schließen")


def neue_box(b):
    """Klick auf die Nummer der ersten sichtbaren Zeile der neuen Seite: neue Eingabebox."""
    assert b.js("(() => { document.getElementById('ui-zeile')?.removeAttribute('id');"
                "const td = [...document.querySelectorAll('main tr[data-b] td.n')].find(td => td.offsetParent &&"
                " td.textContent.trim() === td.closest('tr').dataset.b); if (td) td.id = 'ui-zeile'; return !!td; })()"), \
        "keine sichtbare Zeile mit Nummer"
    b.klicken("#ui-zeile")
    b.warten_bis("document.activeElement && document.activeElement.matches('main .kbox textarea')")
    b.js("document.getElementById('ui-box')?.removeAttribute('id'); document.activeElement.closest('.kbox').id = 'ui-box'")


def teil_eingabe(b, f):
    """Leere Eingabebox: Klicks im Rahmen (Beschriftung „sofort senden“, Häkchen) lassen sie offen, ein Klick daneben
    schließt sie."""
    seite(b, f)
    neue_box(b)
    b.klicken("#ui-box label.sofort")
    assert b.js("!!document.querySelector('#ui-box textarea')"), "Klick auf „sofort senden“ schließt die Box"
    b.klicken("#ui-box label.sofort input")
    assert b.js("!!document.querySelector('#ui-box textarea')"), "Klick aufs Häkchen schließt die Box"
    stil = b.js("(() => { const k = document.createElement('button'); k.disabled = true; document.querySelector('#ui-box .knoepfe')"
                ".append(k); const st = getComputedStyle(k), w = [st.borderTopStyle, st.cursor]; k.remove(); return w; })()")
    assert stil == ["dashed", "not-allowed"], f"ausgegrauter Knopf nicht deutlich: {stil}"
    b.klicken("#ui-box .kk > span")
    assert b.js("!!document.querySelector('#ui-box textarea')"), "Klick in den Rahmen schließt die Box"
    b.js("(() => { const td = [...document.querySelectorAll('main td.c')].reverse().find(td => td.offsetParent &&"
         " !td.closest('.kbox')); td.scrollIntoView({block: 'center'}); td.id = 'ui-daneben'; })()")
    b.klicken("#ui-daneben")
    b.warten_bis("!document.querySelector('#ui-box textarea')")


def teil_faden(b, f):
    """Neue Frage an einer Zeile mit „sofort senden“: der Knopf „an Claude“ legt den Faden an und sendet ihn."""
    vorher = len(f.gesendet())
    seite(b, f, sofort=True)
    neue_box(b)
    b.tippen("Frage aus der Box")
    knopf = b.js("(() => { const bs = [...document.querySelectorAll('#ui-box button')], k = bs.find(x => x.textContent === 'an Claude') || (App.kann.review ? null : bs.find(x => x.classList.contains('haupt')));"
                 "if (k) k.id = 'an-claude'; return !!k; })()")
    assert knopf, "kein Knopf „an Claude“: " + str(b.js("[...document.querySelectorAll('#ui-box button')].map(x => x.textContent)"))
    b.klicken("#an-claude")
    f.gesendet_warten(vorher + 1)


def teil_loeschen(b, f):
    """Faden löschen, während darin ein Antwort-Feld offen ist: der Faden verschwindet trotzdem."""
    f.entwurf("Gleich weg")
    seite(b, f)
    b.js("window.confirm = () => true")
    sel = "[...document.querySelectorAll('.kbox.gs')].find(x => x.textContent.includes('Gleich weg'))"
    b.warten_bis(sel)
    b.js(f"(() => {{ const k = {sel}; [...k.querySelectorAll('button')].find(x => /antworten/.test(x.textContent)).click(); }})()")
    b.warten_bis(f"{sel}.querySelector('textarea')")
    b.js(f"[...{sel}.querySelectorAll('button')].find(x => x.textContent === '🗑' && x.title.startsWith('ganzes')).click()")
    b.warten_bis(f"!{sel}")


def teil_liste(b, f):
    """Klick auf einen Faden in der Liste, während seine Dateibox zugeklappt ist: sie geht auf, der Faden ist zu sehen."""
    seite(b, f)
    neue_box(b)
    b.tippen("Aus der Liste")
    b.js("[...document.querySelectorAll('#ui-box button')].find(x => x.classList.contains('haupt') || x.textContent === 'an Claude').click()")
    sel = "[...document.querySelectorAll('.kbox.gs')].find(x => x.textContent.includes('Aus der Liste'))"
    b.warten_bis(sel)
    b.js(f"{sel}.closest('details.datei').open = false; scrollTo(0, 0)")  # (Rechtecke meldet Chromium trotzdem)
    b.js("[...document.querySelectorAll('.ke')].find(x => x.textContent.includes('Aus der Liste')).id = 'ui-eintrag'")
    b.klicken("#ui-eintrag")
    b.warten_bis(f"{sel}.closest('details.datei').open")
    b.warten_bis(f"(r => r.top >= 0 && r.bottom <= innerHeight)({sel}.getBoundingClientRect())")


def teil_seitenleiste(b, f):
    """Ganz oben (Bahnhof mit Himmel) passt die Dateiliste ins Fenster; selbst gescrollt bleibt sie stehen, auch wenn
    danach die Seite ein Stück scrollt (ohne Dateiwechsel)."""
    seite(b, f)
    b.js("scrollTo(0, 0)")
    time.sleep(0.3)
    unten = b.js("[document.getElementById('liste').getBoundingClientRect().bottom, innerHeight]")
    assert unten[0] <= unten[1], f"Liste ragt unten aus dem Fenster: {unten}"
    if not b.js("(l => l.scrollHeight > l.clientHeight)(document.getElementById('liste'))"):
        return  # zu wenige Dateien zum Scrollen (MR-Fall)
    b.js("(l => l.scrollTop = l.scrollHeight)(document.getElementById('liste'))")
    time.sleep(0.2)
    ende = "(l => l.scrollTop + l.clientHeight)(document.getElementById('liste'))"  # wächst die Liste, sinkt scrollTop
    vorher = b.js(ende)
    b.js("scrollBy(0, 40)")
    time.sleep(0.3)
    nachher = b.js(ende)
    assert nachher == vorher, f"Liste sprang beim Scrollen der Seite: {vorher} → {nachher}"


def teil_dateifilter(b, f):
    """Filter der Dateiliste: Endung im Klappmenü „Filter ▾“ ausblenden (Liste und Diff, nach Neuladen noch aus), j
    springt über Ausgefiltertes; Häkchen „abgehakte“ außen im Titel, „alle Endungen zeigen“ lässt es stehen."""
    seite(b, f)
    b.js("Object.keys(localStorage).filter(k => k.startsWith('filter:dateien:')).forEach(k => localStorage.removeItem(k))")
    b.laden(f.srv.url(f.pfad))
    haken = "document.querySelector('.dfilter-menue input[data-filter=\"{}\"]')"
    gezeigt = "[...document.querySelectorAll('.datei')].filter(d => !d.closest('#popup') && getComputedStyle(d).display !== 'none').map(d => d.dataset.pfad)"
    alle = b.js(gezeigt)
    b.klicken("#liste h2 .dfilter")
    b.warten_bis("!document.querySelector('.dfilter-menue').hidden")
    lage = b.js("[document.querySelector('.dfilter-menue').getBoundingClientRect().right,"
                " document.getElementById('liste').getBoundingClientRect().right]")
    assert lage[0] <= lage[1], f"Filtermenü ragt über die Liste hinaus nach rechts: {lage}"
    assert "null" not in b.js("document.querySelector('.dfilter-menue').textContent"), "„null“ im Filtermenü"
    endungen = b.js("[...document.querySelectorAll('.dfilter-menue input')].map(x => x.dataset.filter)")
    if len(endungen) < 2:
        return  # nur eine Endung (MR-Fall)
    e = endungen[0]
    b.js(haken.format(e) + ".id = 'ui-filter'")
    b.klicken("#ui-filter")
    assert b.js("!document.querySelector('.dfilter-menue').hidden"), "Menü schließt beim Klick auf ein Häkchen"
    rest = b.js(gezeigt)
    assert rest and all(not p.lower().endswith(e) for p in rest), f"{e} nicht ausgeblendet: {rest[:5]}"
    assert b.js("[...document.querySelectorAll('#liste a')].filter(a => getComputedStyle(a).display !== 'none').length") == len(rest)
    assert "/" in b.js("document.querySelector('#liste h2').textContent")
    assert "Filter (1)" in b.js("document.querySelector('#liste h2 .dfilter').textContent")
    b.taste("Escape")
    b.warten_bis("document.querySelector('.dfilter-menue').hidden")
    b.laden(f.srv.url(f.pfad))
    assert b.js(gezeigt) == rest, "Filter nach dem Neuladen vergessen"
    b.js("scrollTo(0, 0)")
    b.taste("j")
    time.sleep(0.3)
    oben = b.js("(() => { const g = document.getElementById('kopf').getBoundingClientRect().bottom + 20;"
                "return [...document.querySelectorAll('.datei')].filter(d => getComputedStyle(d).display !== 'none' && d.getBoundingClientRect().top <= g).pop()?.dataset.pfad })()")
    assert oben in rest, f"j landete auf {oben}"
    # abgehakte ausblenden, dann „alle zeigen“
    erste = rest[0]
    b.js(f"document.querySelector('.datei[data-pfad=\"{erste}\"] summary .haken').click()")
    b.warten_bis(f"document.querySelector('.datei[data-pfad=\"{erste}\"]').classList.contains('abgehakt')")
    b.klicken("#liste h2 .dabgehakt input")  # außen im Titel, nicht im Menü
    assert erste not in b.js(gezeigt), "abgehakte Datei nicht ausgeblendet"
    assert b.js("document.querySelector('.dfilter-menue').hidden"), "Häkchen „abgehakte“ öffnet das Menü"
    b.klicken("#liste h2 .dfilter")  # die Endung ist seit oben noch aus
    b.js("[...document.querySelectorAll('.dfilter-menue button')].find(x => x.textContent === 'alle Endungen zeigen').click()")
    assert erste not in b.js(gezeigt), "„alle Endungen zeigen“ darf „abgehakte“ nicht zurücksetzen"
    b.taste("Escape")
    b.klicken("#liste h2 .dabgehakt input")
    assert b.js(gezeigt) == alle, "nicht wieder alles gezeigt"
    assert b.js(f"document.querySelector('.datei[data-pfad=\"{erste}\"]').open"), "eingeblendete abgehakte Datei nicht aufgeklappt"
    b.js(f"document.querySelector('.datei[data-pfad=\"{erste}\"] summary .haken').click()")
    b.warten_bis(f"!document.querySelector('.datei[data-pfad=\"{erste}\"]').classList.contains('abgehakt')")


def teil_abhaken(b, f):
    """Abhaken einer Datei, in der man liest (Anfang über dem Kopf): die nächste offene Datei steht danach oben, wie mit
    j, abgehakte dazwischen übersprungen (Issue #4). Abhaken einer Datei, deren Anfang man sieht, springt nicht."""
    seite(b, f)
    b.js("Object.keys(localStorage).filter(k => k.startsWith('filter:dateien:')).forEach(k => localStorage.removeItem(k))")
    b.laden(f.srv.url(f.pfad))
    d = "document.querySelector('.datei[data-pfad=\"{}\"]')"
    kopf = "document.getElementById('kopf').getBoundingClientRect().bottom"
    pfade = b.js("[...document.querySelectorAll('.datei')].filter(d => !d.closest('#popup')).map(d => d.dataset.pfad)")
    if len(pfade) < 3:
        return  # MR-Fall: eine Datei
    i = next((i for i, p in enumerate(pfade[:-2]) if b.js(f"{d.format(p)}.open && {d.format(p)}.offsetHeight > 400")), None)
    assert i is not None, f"keine lange Datei mit zwei weiteren dahinter: {pfade[:8]}"
    erste, zweite, dritte = pfade[i:i + 3]
    b.js(d.format(zweite) + ".querySelector('summary .haken').click()")  # schon abgehakt: wird übersprungen
    b.warten_bis(d.format(zweite) + ".classList.contains('abgehakt')")
    for _ in range(3):  # der Kopf wird beim Scrollen kürzer (Himmel), also nachmessen
        b.js(f"scrollBy(0, {d.format(erste)}.getBoundingClientRect().top - {kopf} + 200)")
        time.sleep(0.1)
    assert b.js(f"{d.format(erste)}.getBoundingClientRect().top < {kopf} - 5"), "nicht in die Datei gescrollt"
    b.js(d.format(erste) + ".querySelector('summary .haken').click()")
    b.warten_bis(d.format(erste) + ".classList.contains('abgehakt')")
    b.warten_bis(f"Math.abs({d.format(dritte)}.getBoundingClientRect().top - {kopf} - 8) < 4")
    assert b.js(d.format(dritte) + ".open"), "nächste offene Datei nicht aufgeklappt"
    # Anfang im Blick: kein Sprung
    for p in (erste, zweite):
        b.js(d.format(p) + ".querySelector('summary .haken').click()")
        b.warten_bis("!" + d.format(p) + ".classList.contains('abgehakt')")
    b.js(f"{d.format(erste)}.open = true; {d.format(erste)}.scrollIntoView({{block: 'start'}})")
    time.sleep(0.1)
    y = b.js("scrollY")
    b.js(d.format(erste) + ".querySelector('summary .haken').click()")
    b.warten_bis(d.format(erste) + ".classList.contains('abgehakt')")
    time.sleep(0.2)
    assert b.js("scrollY") == y, "Abhaken einer Datei, deren Anfang man sieht, hat gesprungen"
    b.js(d.format(erste) + ".querySelector('summary .haken').click()")
    b.warten_bis("!" + d.format(erste) + ".classList.contains('abgehakt')")


# ein null/undefined, das als Text in der Seite gelandet ist (append/replaceChildren machen daraus „null“); das Test-Repo
# enthält die Wörter nicht
NULL_TEXT = ("(() => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), r = [];"
             "while (w.nextNode()) if (/^(null|undefined)$/.test(w.currentNode.nodeValue.trim()))"
             " r.push(w.currentNode.parentElement.outerHTML.slice(0, 100)); return r.slice(0, 3); })()")


def teil_abmelden(b, f):
    """„🎧 ✕“ neben „An Agent senden“: der Zuhörer ist weg, die horchen-Instanz bleibt stumm und endet nicht (ihr Ende
    weckte den Agenten). Der „Agent“ ist eine Shell mit eigenem Prozessnamen, damit merge-train die Session erkennt."""
    t = tempfile.mkdtemp(prefix="merge-train-agentx-")
    os.symlink("/bin/sh", os.path.join(t, "agentx"))
    aus, exe = os.path.join(t, "aus"), os.path.join(f.srv.ordner, "merge-train")
    befehl = f'"{sys.executable}" "{exe}" agent horchen "{f.mr.removeprefix("projekt:")}" --als Fake > "{aus}"; true'
    # Was die Teile davor an Fragen hinterlassen haben, abholen: sonst gibt horchen das sofort aus und meldet sich nicht an
    subprocess.run([sys.executable, exe, "agent", "feedback", f.mr.removeprefix("projekt:"), "--als", "Fake"],
                   env=f.srv.umgebung, capture_output=True, check=True)
    ag = subprocess.Popen([os.path.join(t, "agentx"), "-c", befehl], env=f.srv.umgebung)
    try:
        ende = time.time() + 8
        while f.horcht() != "Fake" and time.time() < ende:
            time.sleep(0.1)
        assert f.horcht() == "Fake", f"horchen hat sich nicht angemeldet (Exit {ag.poll()}, Ausgabe: {open(aus).read()[:300]!r})"
        seite(b, f)
        b.warten_bis("!document.getElementById('abmelden').hidden")
        b.klicken("#abmelden")
        b.warten_bis("document.getElementById('abmelden').hidden")
        assert f.horcht() is None, "nach „🎧 ✕“ hört noch jemand zu"
        time.sleep(1.5)
        assert ag.poll() is None and open(aus).read() == "", "horchen hat sich beendet oder etwas ausgegeben"
    finally:
        ag.kill(); ag.wait(); shutil.rmtree(t, ignore_errors=True)


def teil_siehe_ziel(b, f):
    """Siehe auch mit @ziel (Datei aus dem Zielbranch): Link „… @<ziel>“, das Popup zeigt die Zeile von dort, der
    Vergleich stellt den Stand der Seite dem Ziel gegenüber."""
    ziel, pfad, zeile, dort = f.ziel
    f.srv.agent("thread", "-p", f.mr.removeprefix("projekt:"), "--als", "Claude", "--ort", f"{pfad}:{zeile}",
                "--siehe", f"{pfad}:{zeile}@ziel|auf dem Ziel", "--vergleich", pfad, f"{pfad}@ziel|gegen Ziel", "Wie steht es auf dem Ziel?")
    seite(b, f)
    finde = "[...document.querySelectorAll('.sa a')].find(a => a.textContent === '{}')"
    b.warten_bis(finde.format(f"auf dem Ziel @{ziel}"))
    b.js(finde.format(f"auf dem Ziel @{ziel}") + ".click()")
    b.warten_bis("document.querySelector('#popup tr.ziel td.c')")
    kopf, info, text = b.js("[document.querySelector('#popup .pk b').textContent, document.querySelector('#popup .pk .sub').textContent,"
                            " document.querySelector('#popup tr.ziel td.c').textContent]")
    assert kopf.endswith(f"{pfad}:{zeile} @{ziel}") and f"Stand {ziel} " in info, (kopf, info)
    assert text == dort, f"Popup zeigt nicht die Zeile vom Ziel: {text!r}"
    b.js("document.querySelector('#popup .pk button[title^=\"schließen\"]').click()")
    b.js(finde.format(f"⇄ gegen Ziel @{ziel}") + ".click()")
    b.warten_bis("document.querySelector('#popup.vergleich .vkopf')")
    b.warten_bis("!document.querySelector('#popup .pk .sub').textContent.includes('lädt')")
    kopf, info = b.js("[document.querySelector('#popup .vkopf').textContent, document.querySelector('#popup .pk .sub').textContent]")
    assert kopf.endswith(f"{pfad} @{ziel}") and "Unterschied" in info, (kopf, info)
    b.js("document.querySelector('#popup .pk button[title^=\"schließen\"]').click()")


def teil_tausch(b, f):
    """Neuer Stand ohne Neuladen: die neue Datei steht an ihrem Platz in Diff und Liste, eingerahmt; die geänderte mit
    offenem Feld wartet (Marke „geändert“), Feld und Text bleiben, die Scroll-Lage auch. Ist das Feld zu, kommt die neue
    Fassung. Lokal merkt die Seite den Commit selbst, beim MR stößt der Test an (wie „↻ MR-Daten“)."""
    lokal = f.mr.startswith("projekt:")
    datei, neu, anker = ("lib/rechnen.py", "neu/dazu.txt", "viele_30.txt") if lokal else ("App.cs", "Neu.cs", None)
    seite(b, f)
    sel = f"document.querySelector('.datei[data-pfad=\"{datei}\"]')"
    assert b.js(f"(() => {{ const td = [...{sel}.querySelectorAll('table.sbs tr[data-b] td.n')].find(td => "
                "td.textContent.trim() === td.closest('tr').dataset.b); if (td) td.id = 'ui-zeile'; return !!td; })()"), \
        f"keine Zeilennummer in {datei}"
    b.klicken("#ui-zeile")
    b.warten_bis("document.activeElement && document.activeElement.matches('main .kbox textarea')")
    b.tippen("bleibt stehen")
    lage = "(() => { const r = document.querySelector('.datei[data-pfad=\"%s\"] tr[data-b=\"5\"]'); return r && r.getBoundingClientRect().top; })()" % anker
    if anker:
        b.js(f"document.querySelector('.datei[data-pfad=\"{anker}\"] tr[data-b=\"5\"]').scrollIntoView({{block: 'start'}});"
             "scrollBy(0, -document.getElementById('kopf').offsetHeight - 40)")
        vorher = b.js(lage)
    b.js("window.ohneNeuladen = 1")
    seite_vorher = b.js("App.waggon.seite")
    pfad = os.path.join(f.repo, datei)
    open(pfad, "a").write("# neu dazu\n" if lokal else "// neu dazu\n")
    os.makedirs(os.path.dirname(os.path.join(f.repo, neu)) or f.repo, exist_ok=True)
    open(os.path.join(f.repo, neu), "w").write("".join(f"neu {i}\n" for i in range(1, 6)))
    git(f.repo, "add", "-A"); git(f.repo, "commit", "-qm", "noch eine Datei")
    if not lokal:
        b.js("App.neuHolen('MR-Daten geholt')")
    b.warten_bis(f"document.querySelector('main .datei[data-pfad=\"{neu}\"] tr.neu-rahmen')", timeout=15)
    assert b.js("window.ohneNeuladen === 1"), "Seite wurde neu geladen"
    assert b.js("App.waggon.seite") != seite_vorher, "MR.seite nicht auf dem neuen Stand"
    assert b.js(f"{sel}.classList.contains('wartet') && !!{sel}.querySelector('.wartet-marke')"), "geänderte Datei ohne Marke"
    assert b.js(f"{sel}.querySelector('textarea').value") == "bleibt stehen", "Text im offenen Feld verloren"
    assert b.js(f"!!document.querySelector('#liste a[title=\"{neu}\"]') && App.dateien.length === document.querySelectorAll('main .datei').length"), \
        "neue Datei fehlt in der Liste oder App.dateien"
    if anker:
        nachher = b.js(lage)
        assert abs(nachher - vorher) < 3, f"Scroll-Lage verrutscht: {vorher} → {nachher}"
    b.js(f"{sel}.querySelector('tr.kr').remove()")  # Feld zu
    b.warten_bis(f"{sel} && !{sel}.classList.contains('wartet') && {sel}.textContent.includes('neu dazu')")


def teil_aussen(b, f):
    """Faden außerhalb der Änderungen (steht erst unter dem Dateinamen): Klick in der Liste und auf einen Siehe-auch-Link
    dorthin klappen den Kontext auf, der Faden steht an seiner Zeile, kein Popup."""
    pfad, von, bis = ("lib/rechnen.py", 32, 34) if f.mr.startswith("projekt:") else ("App.cs", 24, 26)
    _, zpfad, zeile, _ = f.ziel
    p = f.mr.removeprefix("projekt:")
    f.srv.agent("thread", "-p", p, "--als", "Claude", "--ort", f"{pfad}:{von}-{bis}", "Faden außen")
    f.srv.agent("thread", "-p", p, "--als", "Claude", "--ort", f"{zpfad}:{zeile}", "--siehe", f"{pfad}:{von}-{bis}|zum Außenfaden",
                "Siehe dort")
    sel = "[...document.querySelectorAll('.kbox.gs')].find(x => x.textContent.includes('Faden außen'))"
    an_zeile = (f"({sel} && !{sel}.closest('.kunter') && document.querySelector('tr.kx[data-b=\"{von}\"]')"
                f" && !document.getElementById('popup'))")
    for klick in ("[...document.querySelectorAll('.ke')].find(x => x.textContent.includes('Faden außen'))",
                  "[...document.querySelectorAll('.sa a')].find(a => a.textContent === 'zum Außenfaden')"):
        seite(b, f)
        b.warten_bis(f"{sel} && {sel}.closest('.kunter') && {klick}")
        b.js(f"{klick}.id = 'ui-aussen'")
        b.klicken("#ui-aussen")
        b.warten_bis(an_zeile)


def teil_anker(b, f):
    """Eigener MR, Quell-Branch ausgecheckt (Arbeitsstand): eine GitLab-Diskussion an einer lokal geänderten Zeile steht
    markiert „lokal geändert“ an ihrer Stelle; „passt hier“ macht den Ort zum Anker, die Marke verschwindet. Nur MR."""
    if f.mr.startswith("projekt:"):
        return
    zustand = f.srv.umgebung["FAKE_GLAB_STATE"]
    ap = os.path.join(f.srv.ordner, "data", "merge-train", "reviews", "gitlab.example.com_gruppe_demo_1.json")
    json.dump([{"id": 960, "body": "Warum hier?", "author": {"id": 2, "name": "Reviewerin"}, "system": False, "resolvable": True,
                "resolved": False, "position": {"new_path": "App.cs", "new_line": 10}}], open(os.path.join(zustand, "notes.json"), "w"))
    r = f.srv.post("/api/gitlab", {"mr": f.mr, "aktion": "mrdaten"})
    assert r.get("ok"), r
    akte = json.load(open(ap)); akte["meta"]["author"]["id"] = 1; json.dump(akte, open(ap, "w"))  # fake-glab: ich = 1
    app = os.path.join(f.repo, "App.cs")
    alt = open(app).read()
    open(app, "w").write(alt.replace("// Zeile 10 neu", "// Zeile 10 neu, lokal"))
    try:
        seite(b, f)
        sel = "[...document.querySelectorAll('.kbox.gl')].find(x => x.textContent.includes('Warum hier?'))"
        b.warten_bis(f"{sel} && {sel}.querySelector('.geaendert button.passt')")
        assert "lokal geändert" in b.js(f"{sel}.querySelector('.geaendert').textContent")
        b.js(f"{sel}.querySelector('.geaendert button.passt').id = 'ui-passt'")
        b.klicken("#ui-passt")
        b.warten_bis(f"{sel} && !{sel}.querySelector('.geaendert')")
    finally:
        open(app, "w").write(alt)
        akte = json.load(open(ap)); akte["meta"]["author"]["id"] = None; json.dump(akte, open(ap, "w"))


TEILE = {"senden": teil_senden, "vorschau": teil_vorschau, "zuletzt": teil_zuletzt, "eingabe": teil_eingabe,
         "faden": teil_faden, "loeschen": teil_loeschen, "liste": teil_liste, "seitenleiste": teil_seitenleiste, "dateifilter": teil_dateifilter,
         "abhaken": teil_abhaken, "abmelden": teil_abmelden, "siehe_ziel": teil_siehe_ziel, "tausch": teil_tausch,
         "aussen": teil_aussen, "anker": teil_anker}


def main():
    plan = {}
    for fall, _, teil in [a.partition(":") for a in sys.argv[1:]] or [(fall, "", "") for fall in FAELLE]:
        plan.setdefault(fall, []).extend([teil] if teil else list(TEILE))
    plan = list(plan.items())
    falsch = [f"{fall}:{t}" for fall, ts in plan for t in ts if fall not in FAELLE or t not in TEILE]
    if falsch:
        sys.exit(f"unbekannt: {' '.join(falsch)} (Fälle: {' '.join(FAELLE)}; Teile: {' '.join(TEILE)})")
    exe = chromium()
    if not exe:
        print("test_ui: kein Chromium gefunden – übersprungen")
        return 0
    t = tempfile.mkdtemp(prefix="merge-train-ui-")
    gescheitert = 0
    for i, (fall, teile) in enumerate(plan):
        os.makedirs(os.path.join(t, fall))
        f = FAELLE[fall](os.path.join(t, fall), 8797 + i)
        b = Browser(exe)
        try:
            for name in teile:
                try:
                    TEILE[name](b, f)
                    fehler = b.fehler()
                    assert not fehler, "JS-Fehler: " + " | ".join(fehler)
                    assert not b.js(NULL_TEXT), "„null“/„undefined“ als Text auf der Seite: " + str(b.js(NULL_TEXT))
                    print(f"✓ {fall}:{name}")
                except AssertionError as e:
                    gescheitert += 1
                    print(f"✗ {fall}:{name}: {e}  (JS-Fehler: {b.fehler() or 'keine'})")
        finally:
            b.zu(); f.srv.zu()
    if gescheitert:
        print(f"Server-Log und Daten: {t}")
        return 1
    shutil.rmtree(t, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
