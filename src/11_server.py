# ---------------------------------------------------------------- Server (nur bei Bedarf)

PORT = int(KONF["port"])
ALLES_DURCH = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">{ICON}<title>merge-train: alles durch</title>
<style>{CSS}
.durch{{display:grid;place-items:center;min-height:100vh;text-align:center}} .durch div{{font-size:22vmin;line-height:1.25;margin-bottom:2vmin}}
.durch p{{font-size:20px;margin:12px 0 0}} .durch code{{font-size:.9em}}</style></head>
<body><main class="durch"><section><div>👍</div><p>Alles durch – überall {VON} = {BIS}</p>
<p class="sub">Neue Commits holt <code>merge-train</code> beim nächsten Aufruf.</p></section></main></body></html>"""
LEERLAUF_S = 3600

def server_laeuft():
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/ping", timeout=0.5) as r:
            return r.read() == b"merge-train"
    except OSError:
        return False

def server_sicherstellen():
    import time
    if server_laeuft():
        return True
    log = open(os.path.join(ORDNER, "server.log"), "a")
    subprocess.Popen([sys.executable, os.path.realpath(__file__), "--server"], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    for _ in range(40):
        time.sleep(0.1)
        if server_laeuft():
            return True
    return False

_VORBAU = threading.Lock()

def vorbauen(repos):
    """Nach dem Abruf einer Projektseite die übrigen offenen im Hintergrund bauen (für „n“/Klick im Zug)."""
    def los():
        if not _VORBAU.acquire(blocking=False):
            return
        try:
            for r in repos.values():
                if statistik(r)["dateien"]:
                    projekt_seite(r)
        except Exception:
            pass
        finally:
            _VORBAU.release()
    threading.Thread(target=los, daemon=True).start()

def server():
    """Liefert ~/.cache/merge-train auf 127.0.0.1 aus, erzeugt Seiten beim Abruf frisch, nimmt „fertig“
    und die Review-Aktionen an. Beendet sich nach LEERLAUF_S ohne Anfrage."""
    import time
    from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
    schluessel()
    zuletzt = [time.time()]
    herkunft = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def senden(self, code, body, typ="text/html; charset=utf-8"):
            if isinstance(body, str): body = body.encode()
            self.send_response(code); self.send_header("Content-Type", typ)
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def json_senden(self, code, d):
            self.senden(code, json.dumps(d, ensure_ascii=False), "application/json; charset=utf-8")
        def weiterleiten(self, ziel):
            self.send_response(302); self.send_header("Location", ziel); self.end_headers()
        def do_GET(self):
            zuletzt[0] = time.time()
            pfad, _, abfrage = self.path.partition("?")
            pfad = urllib.parse.unquote(pfad).lstrip("/")
            q = {k: v[0] for k, v in urllib.parse.parse_qs(abfrage).items()}
            ansicht = ansicht_lesen(f'commit:{q["commit"]}' if q.get("commit") else
                                    f'seit:{q["seit"]}' if q.get("seit") else "")
            if (q.get("commit") or q.get("seit")) and not ansicht:
                return self.senden(400, "merge-train: ungültiger Commit", "text/plain; charset=utf-8")
            try:
                if pfad == "ping":
                    return self.senden(200, "merge-train", "text/plain")
                if pfad in ("favicon.ico", "favicon.svg"):
                    return self.senden(200, FAVICON.strip(), "image/svg+xml")
                if pfad in ("api/zeilen", "api/datei"):  # beide Modi: Kontext / große Datei nachladen
                    if q.get("k") != schluessel():
                        return self.json_senden(403, {"ok": False, "text": "falscher Schlüssel – Seite neu laden"})
                    struktur = seiten_struktur(q.get("mr", ""), ansicht_lesen(q.get("ansicht")))
                    if struktur is None:
                        return self.json_senden(200, {"ok": False, "text": "Seite unbekannt – neu laden"})
                    if pfad == "api/datei":
                        try:
                            return self.json_senden(200, datei_nachladen(struktur, int(q.get("i", -1))))
                        except ValueError:
                            return self.json_senden(400, {"ok": False, "text": "i ungültig"})
                    try:
                        von, bis = int(q.get("von", 1)), int(q.get("bis", 1))
                    except ValueError:
                        return self.json_senden(400, {"ok": False, "text": "von/bis ungültig"})
                    return self.json_senden(200, zeilen_daten(struktur, q.get("pfad", ""), von, bis))
                if pfad in ("api/review", "api/stand"):  # Review (GitLab-MR) bzw. Gespräch (lokales Projekt)
                    if q.get("k") != schluessel():
                        return self.json_senden(403, {"ok": False, "text": "falscher Schlüssel – Seite neu laden"})
                    mr = mr_aus_id(q.get("mr", ""))
                    if not KONF["lokal" if mr.get("lokal") else "gitlab"]:
                        return self.senden(404, "nicht gefunden", "text/plain")
                    if pfad == "api/stand":
                        return self.json_senden(200, {"stand": stand(mr, review_laden(mr))})
                    ansicht = ansicht_lesen(q.get("ansicht"))
                    return self.json_senden(200, g_daten(mr, ansicht) if mr.get("lokal") else review_daten(mr, ansicht))
                if KONF["gitlab"]:
                    if pfad in ("mrs", "") and not KONF["lokal"] or pfad == "mrs":
                        return self.senden(200, startseite())
                    if pfad == "mr-oeffnen":
                        return self.weiterleiten("/mr/" + mr_id(mr_vollstaendig(mr_ref(q.get("u", "")))))
                    if pfad.startswith("mr/"):
                        try:
                            datei, _, mr = mr_seite(mr_aus_id(pfad[3:]), ansicht=ansicht)
                        except GitLabFehler as e:  # keine MR-Daten / kein Klon: Güterbahnhof anbieten
                            return self.senden(200, startseite(str(e), pfad[3:]))
                        if mr_id(mr) != pfad[3:]:
                            return self.weiterleiten("/mr/" + mr_id(mr) + (f"?{abfrage}" if abfrage else ""))
                        return self.senden(200, open(datei, "rb").read())
                    if pfad == "api/mrzug":  # aus dem Cache, keine GitLab-Anfrage
                        return self.json_senden(200, {"wagen": mr_wagen(q.get("akt")), "zeit": mr_liste()[1]})
                if KONF["lokal"]:
                    repos = {dateiname(projektname(r)): r for r in finde_repos()}
                    if pfad == "zug.js":
                        zug_schreiben([statistik(r) for r in repos.values()])
                        return self.senden(200, open(os.path.join(ORDNER, "zug.js"), "rb").read(),
                                           "text/javascript; charset=utf-8")
                    if pfad == "":
                        wagen = zug_schreiben([statistik(r) for r in repos.values()])
                        offen = [w for w in wagen if w["status"] == "offen"]
                        if not offen:
                            return self.senden(200, ALLES_DURCH)
                        return self.weiterleiten("/" + offen[0]["datei"])
                    if pfad in repos:
                        datei, _ = projekt_seite(repos[pfad], ansicht=ansicht)
                        self.senden(200, open(datei, "rb").read())
                        if not ansicht:
                            vorbauen(repos)
                        return
                self.senden(404, "nicht gefunden", "text/plain")
            except GitLabFehler as e:
                self.senden(502, f"merge-train: {e}", "text/plain; charset=utf-8")
            except Exception as e:  # Fehler zeigen statt Verbindung abbrechen
                self.senden(500, f"merge-train: {type(e).__name__}: {e}", "text/plain; charset=utf-8")
        def do_POST(self):
            zuletzt[0] = time.time()
            if self.headers.get("Origin", f"http://127.0.0.1:{PORT}") not in herkunft:
                return self.senden(403, "verboten", "text/plain")
            try:
                d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path == "/fertig" and KONF["lokal"]:
                    ok, text = fertig(str(d.get("projekt", "")), str(d.get("sha", "")), str(d.get("k", "")))
                    wagen = json.loads(open(os.path.join(ORDNER, "zug.js")).read()[len("window.MR_ZUG="):-1])["wagen"]
                    return self.json_senden(200 if ok else 400, {"ok": ok, "text": text, "wagen": wagen})
                lokal = str(d.get("mr", "")).startswith("projekt:")
                if self.path not in ("/api/kommentar", "/api/hinweis", "/api/abschliessen", "/api/gitlab", "/api/gespraech") \
                        or not KONF["lokal" if lokal else "gitlab"]:
                    return self.senden(404, "nicht gefunden", "text/plain")
                if str(d.get("k", "")) != schluessel():
                    return self.json_senden(403, {"ok": False, "text": "Abgelehnt: falscher Schlüssel – Seite neu laden."})
                if lokal:  # Gespräch mit dem Agenten
                    mr = mr_aus_id(d.get("mr", ""))
                    ansicht = ansicht_lesen(d.get("ansicht"))
                    tid = None
                    if self.path == "/api/kommentar":
                        ok, text = g_aktion(mr, d)
                    elif self.path == "/api/gespraech" and d.get("aktion") == "senden":
                        ok, text, tid = feedback_senden(mr)
                    elif self.path == "/api/gespraech" and d.get("aktion") == "starten":
                        ok, text = session_starten(mr)
                    else:
                        return self.json_senden(400, {"ok": False, "text": "unbekannte Aktion"})
                    return self.json_senden(200, {"ok": ok, "text": text, "todo": tid,
                                                  "review": g_daten(mr, ansicht) if ok else None})
                if self.path == "/api/gitlab":  # Güterbahnhof: GitLab nur auf Knopfdruck
                    if d.get("aktion") == "mrliste":
                        items, _ = mr_liste_holen()
                        return self.json_senden(200, {"ok": True, "text": f"{len(items)} MR(s) aus GitLab geholt"})
                    if d.get("aktion") == "mrdaten":
                        mr, meta = mr_meta_holen(mr_aus_id(d.get("mr", "")))
                        return self.json_senden(200, {"ok": True, "text": "MR-Daten geholt"})
                    return self.json_senden(400, {"ok": False, "text": "unbekannte Aktion"})
                mr = mr_aus_id(d.get("mr", ""))
                ansicht = ansicht_lesen(d.get("ansicht"))
                if self.path == "/api/abschliessen":
                    if ansicht and ansicht[0] == "commit":
                        return self.json_senden(200, {"ok": False, "text": NUR_LESEN})
                    ok, text, web = abschliessen(mr)
                    return self.json_senden(200, {"ok": ok, "text": text, "web_url": web, "review": review_daten(mr, ansicht)})
                ok, text = (kommentar_aktion if self.path == "/api/kommentar" else hinweis_aktion)(mr, d)
                self.json_senden(200, {"ok": ok, "text": text, "review": review_daten(mr, ansicht) if ok else None})
            except GitLabFehler as e:
                self.json_senden(502, {"ok": False, "text": str(e)})
            except Exception as e:
                self.json_senden(500, {"ok": False, "text": f"merge-train: {type(e).__name__}: {e}"})

    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    global SERVER_SOCKET
    SERVER_SOCKET = srv.socket
    beobachtet = [os.path.realpath(__file__), KONFIG_DATEI]
    def mtimes():
        out = []
        for p in beobachtet:
            try: out.append(os.path.getmtime(p))
            except OSError: out.append(None)
        return out
    anfang = mtimes()
    neu = [False]
    def waechter():
        while time.time() - zuletzt[0] < LEERLAUF_S:
            time.sleep(2)
            jetzt = mtimes()
            if jetzt[0] is None:  # Skript umbenannt/gelöscht: beenden
                break
            if jetzt != anfang:  # Skript oder Einstellung geändert: mit neuem Stand weitermachen
                neu[0] = True; break
        srv.shutdown()
    threading.Thread(target=waechter, daemon=True).start()
    srv.serve_forever()
    srv.server_close()
    if neu[0]:
        os.execv(sys.executable, [sys.executable, beobachtet[0], "--server"])

def im_browser(pfad, nur_url=False):
    if not server_sicherstellen():
        sys.exit(f"merge-train: Server startet nicht – siehe {os.path.join(ORDNER, 'server.log')}")
    url = f"http://127.0.0.1:{PORT}{pfad}"
    print(url)
    if not nur_url:
        oeffnen(url)

