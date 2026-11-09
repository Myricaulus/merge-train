#!/usr/bin/env python3
"""Ladezeit einer merge-train-Seite in einem frischen Chromium messen, ohne Node/Puppeteer.

  python3 perf/cdp_messung.py URL [--runden 3] [--chrome /usr/bin/chromium] [--fenster]

Spricht das DevTools-Protokoll über --remote-debugging-pipe (fd 3/4, JSON mit \\0 getrennt). Je Runde ein frischer
Browser mit leerem Profil. Gibt Antwort, DOM fertig, load und die Summe der Layout-/Script-Zeit aus dem Trace aus.
Nur lesend: legt keine Kommentare an.
"""
import argparse, json, os, shutil, subprocess, sys, tempfile, time


class Pipe:
    def __init__(self, exe, fenster):
        self.profil = tempfile.mkdtemp(prefix="mt-cdp-")
        lesen_r, self.lesen_w = os.pipe()   # wir → Chromium (fd 3)
        self.schr_r, schr_w = os.pipe()     # Chromium → wir (fd 4)
        args = [exe, "--remote-debugging-pipe", f"--user-data-dir={self.profil}", "--no-first-run",
                "--no-default-browser-check", "--window-size=1600,1000", "about:blank"]
        if not fenster:
            args.insert(1, "--headless=new")
        def fds():
            os.dup2(lesen_r, 3); os.dup2(schr_w, 4)
        self.p = subprocess.Popen(args, preexec_fn=fds, pass_fds=(3, 4), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(lesen_r); os.close(schr_w)
        self.puffer, self.n, self.events = b"", 0, []

    def senden(self, methode, params=None, sitzung=None):
        self.n += 1
        m = {"id": self.n, "method": methode, "params": params or {}}
        if sitzung:
            m["sessionId"] = sitzung
        os.write(self.lesen_w, json.dumps(m).encode() + b"\0")
        return self.n

    def lesen(self):
        while b"\0" not in self.puffer:
            teil = os.read(self.schr_r, 1 << 20)
            if not teil:
                raise EOFError("Chromium beendet")
            self.puffer += teil
        m, _, self.puffer = self.puffer.partition(b"\0")
        return json.loads(m)

    def rufen(self, methode, params=None, sitzung=None):
        i = self.senden(methode, params, sitzung)
        while True:
            m = self.lesen()
            if m.get("id") == i:
                if "error" in m:
                    raise RuntimeError(f"{methode}: {m['error']}")
                return m.get("result", {})
            self.events.append(m)

    def warten(self, methode, sitzung=None, timeout=120):
        ende = time.time() + timeout
        for i, m in enumerate(self.events):
            if m.get("method") == methode:
                return self.events.pop(i)
        while time.time() < ende:
            m = self.lesen()
            if m.get("method") == methode and (not sitzung or m.get("sessionId") == sitzung):
                return m
            self.events.append(m)
        raise TimeoutError(methode)

    def zu(self):
        try:
            self.rufen("Browser.close")
        except Exception:
            pass
        try:
            self.p.wait(5)
        except subprocess.TimeoutExpired:
            self.p.kill()
        shutil.rmtree(self.profil, ignore_errors=True)


def runde(exe, url, fenster, trace):
    c = Pipe(exe, fenster)
    try:
        ziel = c.rufen("Target.createTarget", {"url": "about:blank"})["targetId"]
        s = c.rufen("Target.attachToTarget", {"targetId": ziel, "flatten": True})["sessionId"]
        c.rufen("Page.enable", sitzung=s)
        if trace:
            c.rufen("Tracing.start", {"traceConfig": {"includedCategories": ["devtools.timeline", "blink"]},
                                      "transferMode": "ReportEvents"})
        t0 = time.time()
        c.rufen("Page.navigate", {"url": url}, sitzung=s)
        c.warten("Page.loadEventFired", s)
        gemessen = (time.time() - t0) * 1000
        # erst messen, wenn der Browser einen Frame gezeichnet hat
        nav = c.rufen("Runtime.evaluate", {"expression": """new Promise(r=>requestAnimationFrame(()=>setTimeout(()=>{
            const n=performance.getEntriesByType('navigation')[0],p=performance.getEntriesByType('paint');
            r(JSON.stringify({antwort:Math.round(n.responseEnd),dom:Math.round(n.domContentLoadedEventEnd),load:Math.round(n.loadEventEnd),
              fcp:Math.round((p.find(x=>x.name==='first-contentful-paint')||{}).startTime||0),
              bytes:n.transferSize||n.encodedBodySize,dateien:document.querySelectorAll('.datei').length,
              zeilen:document.querySelectorAll('tr').length}))},0)))""", "awaitPromise": True, "returnByValue": True},
                       sitzung=s)["result"]["value"]
        d = json.loads(nav)
        d["gemessen"] = round(gemessen)
        if trace:
            c.senden("Tracing.end")
            summe = {}
            while True:
                m = c.lesen()
                if m.get("method") == "Tracing.dataCollected":
                    for e in m["params"]["value"]:
                        if e.get("ph") == "X" and e.get("dur"):
                            summe[e["name"]] = summe.get(e["name"], 0) + e["dur"] / 1000
                elif m.get("method") == "Tracing.tracingComplete":
                    break
            d["trace"] = {k: round(v) for k, v in sorted(summe.items(), key=lambda x: -x[1])[:8] if v > 30}
        return d
    finally:
        c.zu()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--runden", type=int, default=3)
    ap.add_argument("--chrome", default=shutil.which("chromium") or shutil.which("google-chrome") or "chromium")
    ap.add_argument("--fenster", action="store_true", help="mit Fenster (GPU) statt headless")
    ap.add_argument("--trace", action="store_true", help="Trace: Summe der längsten Event-Arten")
    o = ap.parse_args()
    for i in range(o.runden):
        d = runde(o.chrome, o.url, o.fenster, o.trace)
        print(f'Runde {i + 1}: Antwort {d["antwort"]} ms · DOM fertig {d["dom"]} ms · load {d["load"]} ms · '
              f'erstes Bild {d["fcp"]} ms · {d["dateien"]} Dateien, {d["zeilen"]} Zeilen'
              + (f' · Trace {d["trace"]}' if "trace" in d else ""))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
