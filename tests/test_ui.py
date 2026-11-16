#!/usr/bin/env python3
"""UI-Tests im echten Browser: Knöpfe der Diff-Seite klicken und prüfen, was beim Server ankommt.

  python3 tests/test_ui.py [teil …]      Teile: senden, vorschau, zuletzt (Standard: alle)

Baut den Arbeitsstand aus src/ in einen Temp-Ordner, legt das Test-Repo aus werkzeug/seiten_vergleich.py an, startet
einen eigenen Server (eigener Port und Daten, nie der des Nutzers) und ein frisches headless Chromium (DevTools über
--remote-debugging-pipe, ohne Node). Ohne Chromium: übersprungen (Exit 0, mit Hinweis).
JS-Fehler auf der Seite (Runtime.exceptionThrown) lassen jeden Teil scheitern.
"""
import glob, json, os, shutil, sys, tempfile, time, urllib.request

HIER = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path[:0] = [os.path.join(HIER, "werkzeug"), os.path.join(HIER, "perf")]
from cdp_messung import Pipe  # noqa: E402
from seiten_vergleich import Server, bauen, test_repo  # noqa: E402

MR = "projekt:probe"


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

    def klicken(self, selektor):
        """Echter Mausklick auf die Mitte des Elements (trifft nur, was sichtbar und nicht verdeckt ist)."""
        r = self.js(f"(() => {{ const e = document.querySelector({json.dumps(selektor)}); if (!e) return null;"
                    "e.scrollIntoView({block: 'center'}); const r = e.getBoundingClientRect();"
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


def entwurf(srv, text="Warum mal zwei?"):
    d = srv.post("/api/kommentar", {"mr": MR, "aktion": "neu", "text": text})
    assert d.get("ok"), d


def faeden(srv):
    return json.loads(urllib.request.urlopen(srv.url(f"/api/review?mr={MR}&k={srv.schluessel}")).read())["faeden"]


def gesendet(srv):
    return [m for k in faeden(srv) for m in k["nachrichten"] if m["von"] == "ich" and m.get("gesendet")]


def gesendet_warten(srv, n, timeout=8):
    ende = time.time() + timeout
    while time.time() < ende:
        if len(gesendet(srv)) >= n:
            return
        time.sleep(0.1)
    raise AssertionError(f"nach {timeout} s nicht {n} gesendet: {faeden(srv)}")


def seite(b, srv, vorher=False):
    b.laden(srv.url("/probe.html"))
    b.js(f"localStorage.promptVorher = {'1' if vorher else chr(39) * 2}")
    b.laden(srv.url("/probe.html"))
    b.warten_bis("!document.getElementById('feedback').disabled")


def teil_senden(b, srv):
    """„An Agent senden“ schickt den Entwurf ab (ohne Vorschau)."""
    entwurf(srv)
    seite(b, srv)
    b.klicken("#feedback")
    gesendet_warten(srv, 1)


def teil_vorschau(b, srv):
    """Mit „vor dem Senden zeigen“: erst der Dialog mit dem Prompt, abbrechen sendet nichts, „senden“ schon."""
    entwurf(srv, "Vorschau bitte")
    vorher = len(gesendet(srv))
    seite(b, srv, vorher=True)
    b.klicken("#feedback")
    b.warten_bis("document.querySelector('dialog.prompt-dialog[open] pre')")
    assert "merge-train" in b.js("document.querySelector('dialog.prompt-dialog pre').textContent")
    b.js("[...document.querySelectorAll('dialog.prompt-dialog button')].find(x => x.textContent === 'abbrechen').click()")
    b.warten_bis("!document.querySelector('dialog.prompt-dialog')")
    time.sleep(1)
    assert len(gesendet(srv)) == vorher, "abbrechen hat gesendet"
    b.klicken("#feedback")
    b.warten_bis("document.querySelector('dialog.prompt-dialog[open] .pd-senden')")
    b.klicken("dialog.prompt-dialog .pd-senden")
    gesendet_warten(srv, vorher + 1)


def teil_zuletzt(b, srv):
    """„📨“ zeigt, was zuletzt an den Agenten ging (hier: der Startprompt aus feedback_befehl)."""
    entwurf(srv, "Und was kam an?")
    vorher = len(gesendet(srv))
    seite(b, srv)
    b.klicken("#feedback")
    gesendet_warten(srv, vorher + 1)
    b.klicken("#prompt")
    b.warten_bis("document.querySelector('dialog.prompt-dialog[open] pre')")
    text = b.js("document.querySelector('dialog.prompt-dialog pre').textContent")
    assert "merge-train agent feedback" in text, text
    assert "Startprompt" in b.js("document.querySelector('dialog.prompt-dialog summary').textContent")


TEILE = {"senden": teil_senden, "vorschau": teil_vorschau, "zuletzt": teil_zuletzt}


def main():
    teile = sys.argv[1:] or list(TEILE)
    unbekannt = [t for t in teile if t not in TEILE]
    if unbekannt:
        sys.exit(f"unbekannte Teile: {' '.join(unbekannt)} (bekannt: {' '.join(TEILE)})")
    exe = chromium()
    if not exe:
        print("test_ui: kein Chromium gefunden – übersprungen")
        return 0
    t = tempfile.mkdtemp(prefix="merge-train-ui-")
    srv = Server(bauen(t, None), test_repo(t), 8797)
    b = Browser(exe)
    gescheitert = 0
    try:
        for name in teile:
            try:
                TEILE[name](b, srv)
                f = b.fehler()
                assert not f, "JS-Fehler: " + " | ".join(f)
                print(f"✓ {name}")
            except AssertionError as e:
                gescheitert += 1
                print(f"✗ {name}: {e}  (JS-Fehler: {b.fehler() or 'keine'})")
    finally:
        b.zu(); srv.zu()
    if gescheitert:
        print(f"Server-Log und Daten: {t}")
        return 1
    shutil.rmtree(t, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
