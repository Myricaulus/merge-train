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
    laufend, lauf_sperre = [0], threading.Lock()  # Anfragen in Arbeit: ein Neustart wartet auf sie
    herkunft = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            self.mit_anlass(self.get, "GET " + self.path.split("?")[0])
        def do_POST(self):
            self.mit_anlass(self.post, "POST " + self.path)
        def mit_anlass(self, f, name):
            ANLASS.name = name[:32]
            with lauf_sperre:
                laufend[0] += 1
            try:
                f()
            finally:
                with lauf_sperre:
                    laufend[0] -= 1
                ANLASS.name = None
        def senden(self, code, body, typ="text/html; charset=utf-8"):
            if isinstance(body, str): body = body.encode()
            self.send_response(code); self.send_header("Content-Type", typ)
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def json_senden(self, code, d):
            self.senden(code, json.dumps(d, ensure_ascii=False), "application/json; charset=utf-8")
        def weiterleiten(self, ziel):
            self.send_response(302); self.send_header("Location", ziel); self.end_headers()
        def get(self):
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
                if pfad in ("api/zeilen", "api/datei", "api/vergleich"):  # Kontext / große Datei nachladen, Dateivergleich
                    if q.get("k") != schluessel():
                        return self.json_senden(403, {"ok": False, "text": "falscher Schlüssel – Seite neu laden"})
                    struktur = seiten_struktur(q.get("mr", ""), ansicht_lesen(q.get("ansicht")))
                    if struktur is None:
                        return self.json_senden(200, {"ok": False, "text": "Seite unbekannt – neu laden"})
                    if pfad == "api/vergleich":
                        return self.json_senden(200, vergleich_daten(struktur, q.get("a", ""), q.get("b", "")))
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
                if pfad in ("api/review", "api/stand"):  # Gespräch und (je nach Quelle) Review des Waggons
                    if q.get("k") != schluessel():
                        return self.json_senden(403, {"ok": False, "text": "falscher Schlüssel – Seite neu laden"})
                    g = schluessel_von(q.get("mr", ""))
                    if pfad == "api/stand":
                        seite_lebt(g)
                        return self.json_senden(200, {"stand": stand(g, review_laden(g)), "version": VERSION,
                                                      "server": server_stand()})
                    return self.json_senden(200, wagen_daten(g, ansicht_lesen(q.get("ansicht"))))
                if pfad in ("zug.js", "api/zug"):  # der gemischte Zug aller eingeschalteten Quellen
                    d = {"wagen": alle_wagen(q.get("akt")), "zeit": mr_liste()[1] if GITLAB.an() else None}
                    if pfad == "api/zug":
                        return self.json_senden(200, d)
                    return self.senden(200, "window.MR_ZUG=" + json.dumps(d, ensure_ascii=False) + ";",
                                       "text/javascript; charset=utf-8")
                if pfad == "":  # Start: erster offener lokaler Waggon, sonst Zug (mit MR-Feld)
                    if LOKAL.an():
                        offen = [w for w in LOKAL.wagen() if w["status"] == "offen"]
                        if offen:
                            return self.weiterleiten(offen[0]["datei"])
                        if not GITLAB.an():
                            return self.senden(200, ALLES_DURCH)
                    return self.senden(200, startseite())
                if pfad == "mrs" and GITLAB.an():
                    return self.senden(200, startseite())
                if pfad == "mr-oeffnen" and GITLAB.an():
                    return self.weiterleiten("/mr/" + mr_id(mr_vollstaendig(mr_ref(q.get("u", "")))))
                if pfad.startswith("mr/") and GITLAB.an():
                    try:
                        datei, _, mr = mr_seite(mr_aus_id(pfad[3:]), ansicht=ansicht)
                    except GitLabFehler as e:  # keine MR-Daten / kein Klon: Güterbahnhof anbieten
                        return self.senden(200, startseite(str(e), pfad[3:]))
                    if mr_id(mr) != pfad[3:]:
                        return self.weiterleiten("/mr/" + mr_id(mr) + (f"?{abfrage}" if abfrage else ""))
                    return self.senden(200, open(datei, "rb").read())
                if pfad.endswith(".html") and LOKAL.an():
                    repos = {dateiname(projektname(r)): r for r in finde_repos()}
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
        def post(self):
            zuletzt[0] = time.time()
            if self.headers.get("Origin", f"http://127.0.0.1:{PORT}") not in herkunft:
                return self.senden(403, "verboten", "text/plain")
            try:
                d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if d.get("aktion"):
                    ANLASS.name = f"{self.path} {d['aktion']}"[:32]
                if str(d.get("k", "")) != schluessel():
                    return self.json_senden(403, {"ok": False, "text": "Abgelehnt: falscher Schlüssel – Seite neu laden."})
                if self.path == "/api/gitlab" and GITLAB.an():  # Güterbahnhof: GitLab nur auf Knopfdruck
                    if d.get("aktion") == "mrliste":
                        items, _ = mr_liste_holen()
                        return self.json_senden(200, {"ok": True, "text": f"{len(items)} MR(s) aus GitLab geholt"})
                    if d.get("aktion") == "mrdaten":
                        mr = mr_aus_id(d.get("mr", ""))
                        vorher = review_laden(mr).get("struktur")
                        _, vorhanden = meta_und_entwuerfe(mr)
                        if isinstance(vorhanden, GitLabFehler):
                            raise vorhanden
                        with SPERRE:  # gesendete Kommentare abgleichen: in GitLab veröffentlicht oder verworfen?
                            st = review_laden(mr)
                            pub, verw = entwuerfe_abgleichen(mr, st, vorhanden)
                            if pub or verw:
                                review_speichern(mr, st)
                        try:  # Seite gleich bauen: neu laden muss der Browser nur, wenn sie sich geändert hat
                            mr_seite(mr)
                            neu_laden = review_laden(mr).get("struktur") != vorher
                        except GitLabFehler:
                            neu_laden = True
                        text = "MR-Daten geholt" + (f" · {verw} Entwurf/Entwürfe in GitLab verworfen – wieder lokal, "
                                                    "„Review abschließen“ sendet sie neu" if verw else "") + \
                            (f" · {pub} in GitLab veröffentlicht" if pub else "")
                        return self.json_senden(200, {"ok": True, "text": text, "neu_laden": neu_laden})
                    return self.json_senden(400, {"ok": False, "text": "unbekannte Aktion"})
                if self.path == "/fertig":
                    g = schluessel_von(d.get("mr") or "projekt:" + str(d.get("projekt", "")))
                    if not quelle(g).kann["fertig"]:
                        return self.senden(404, "nicht gefunden", "text/plain")
                    ok, text = fertig(g["lokal"], str(d.get("sha", "")), str(d.get("k", "")))
                    return self.json_senden(200 if ok else 400, {"ok": ok, "text": text, "wagen": alle_wagen(mr_id(g))})
                if self.path not in ("/api/kommentar", "/api/hinweis", "/api/abschliessen", "/api/gespraech"):
                    return self.senden(404, "nicht gefunden", "text/plain")
                g = schluessel_von(d.get("mr", ""))
                kann = quelle(g).kann
                ansicht = ansicht_lesen(d.get("ansicht"))
                antwort = {}
                if self.path == "/api/gespraech" or self.path == "/api/kommentar" and (d.get("gespraech") or not kann["review"]):
                    if self.path == "/api/kommentar":  # Fragen an den Agenten: Fäden, nie nach außen
                        ok, text = g_aktion(g, d)
                    elif d.get("aktion") == "senden":
                        ok, text, tid = feedback_senden(g)
                        antwort["todo"] = tid
                    elif d.get("aktion") == "starten":
                        ok, text = session_starten(g)
                    else:
                        return self.json_senden(400, {"ok": False, "text": "unbekannte Aktion"})
                elif not kann["review"]:
                    return self.json_senden(400, {"ok": False, "text": "Dieser Waggon hat kein Review"})
                elif self.path == "/api/abschliessen":
                    if ansicht and ansicht[0] == "commit":
                        return self.json_senden(200, {"ok": False, "text": NUR_LESEN})
                    ok, text, web = abschliessen(g)
                    antwort["web_url"] = web
                    return self.json_senden(200, dict(antwort, ok=ok, text=text, review=wagen_daten(g, ansicht)))
                else:
                    ok, text = (kommentar_aktion if self.path == "/api/kommentar" else hinweis_aktion)(g, d)
                return self.json_senden(200, dict(antwort, ok=ok, text=text, review=wagen_daten(g, ansicht) if ok else None))
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
        bis = time.time() + 600  # laufende Aktionen (z. B. „Review abschließen“) erst fertig werden lassen
        while laufend[0] > 0 and time.time() < bis:
            time.sleep(0.2)
        srv.shutdown()
    threading.Thread(target=waechter, daemon=True).start()
    srv.serve_forever()
    srv.server_close()
    if neu[0]:
        os.execv(sys.executable, [sys.executable, beobachtet[0], "--server"])

_SERVER_STAND = [0, None]

def server_stand():
    """Stand von merge-train selbst fürs HUD: letzter Commit des Repos, Zeit, noch nicht committete Änderungen in src/.
    Höchstens alle 30 s neu ermittelt (die Seiten fragen alle 4 s)."""
    if time.time() - _SERVER_STAND[0] > 30:
        repo = os.path.dirname(os.path.realpath(__file__))
        roh = (git(repo, "log", "-1", "--format=%h%x1f%cd", "--date=format:%d.%m. %H:%M", check=False) or "").strip()
        if roh:
            commit, zeit = roh.split("\x1f")
            st = {"commit": commit, "zeit": zeit, "geaendert": bool((git(repo, "status", "--porcelain", "--", "src", check=False) or "").strip())}
        else:  # kein Git-Repo (z. B. kopierte Datei): Zeit der Datei
            st = {"commit": "", "zeit": datetime.fromtimestamp(os.path.getmtime(os.path.realpath(__file__))).strftime("%d.%m. %H:%M"),
                  "geaendert": False}
        _SERVER_STAND[:] = [time.time(), st]
    return _SERVER_STAND[1]

def im_browser(pfad, nur_url=False):
    if not server_sicherstellen():
        sys.exit(f"merge-train: Server startet nicht – siehe {os.path.join(ORDNER, 'server.log')}")
    url = f"http://127.0.0.1:{PORT}{pfad}"
    print(url)
    if not nur_url:
        oeffnen(url)

