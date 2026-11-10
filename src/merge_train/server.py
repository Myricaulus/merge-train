"""Der kleine HTTP-Server auf 127.0.0.1: liefert Seiten und nimmt die Aktionen der Seite entgegen."""
import json, os, re, subprocess, sys, threading, time
import urllib.parse
from datetime import datetime
from .einstellungen import BIS, KONF, KONFIG_DATEI, ORDNER, SKRIPT, VON, dateiname, oeffnen, projektname, schluessel
from .waggon import Fehler, Waggon
from .git import ANLASS, finde_repos, git, statistik
from .web import CSS, FAVICON, ICON
from .zustand import zustand, zustand_lesen
from .gitlab import mr_liste, mr_liste_holen, mr_ref, mr_vollstaendig
from .ansichten import ansicht_lesen
from .seite import VERSION, mr_seite, projekt_seite, startseite
from .quellen import GITLAB, LOKAL, alle_wagen, fertig, schluessel_von
from .zuhoerer import feedback_senden, seite_lebt, session_starten
from .review import (NUR_LESEN, abschliessen, datei_nachladen, entwuerfe_abgleichen, hinweis_aktion, kommentar_aktion, meta_und_entwuerfe, seiten_struktur,
    stand, vergleich_daten, zeilen_daten)
from .gespraech import gespraech_aktion, wagen_daten
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import NamedTuple
from . import syntax

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
    if server_laeuft():
        return True
    log = open(os.path.join(ORDNER, "server.log"), "a")
    subprocess.Popen([sys.executable, SKRIPT, "--server"], start_new_session=True,
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


# ---- Routen: Handler auf Modulebene, ein Eintrag je (Methode, Pfad). Was viele brauchen, erledigt bearbeiten():
# Schlüssel (mit_schluessel), eingeschaltete Quelle (quelle), Waggon aus „mr“ (waggon), „kann review“ (review),
# Struktur der Seite (struktur), Fehler. Rückgabe eines Handlers: dict → JSON 200, (status, dict) → JSON, Antwort → roh.

class Antwort(NamedTuple):
    status: int
    inhalt: object = b""
    typ: str = "text/html; charset=utf-8"
    ort: str = None  # Weiterleitung


def text_antwort(status, text, typ="text/plain; charset=utf-8"):
    return Antwort(status, text, typ)


def weiterleitung(ziel):
    return Antwort(302, ort=ziel)


NICHT_GEFUNDEN = Antwort(404, "nicht gefunden", "text/plain")


class Anfrage(NamedTuple):
    methode: str
    pfad: str            # ohne führendes „/“ (GET) bzw. wie gesendet (POST)
    abfrage: str         # roher Query-String
    daten: dict          # GET: Query-Parameter, POST: JSON-Rumpf
    seiten_ansicht: tuple  # GET ?commit=… / ?seit=… für Seiten

    @property
    def ansicht(self):
        """Ansicht, auf die sich eine API-Anfrage bezieht (Feld „ansicht“)."""
        return ansicht_lesen(self.daten.get("ansicht"))


ROUTEN = {}         # (methode, pfad) → (funktion, bedingungen)
PRAEFIX_ROUTEN = []  # (regex, funktion, bedingungen), nur GET, in dieser Reihenfolge nach ROUTEN


def route(methode, pfad, *, mit_schluessel=True, quelle=None, waggon=False, review=False, struktur=False):
    """Handler eintragen. pfad als re.Pattern: Präfix-Route, der Handler bekommt die Gruppen als Argumente."""
    bedingungen = dict(mit_schluessel=mit_schluessel, quelle=quelle, waggon=waggon, review=review, struktur=struktur)
    def eintragen(f):
        if isinstance(pfad, re.Pattern):
            PRAEFIX_ROUTEN.append((pfad, f, bedingungen))
        else:
            ROUTEN[(methode, pfad)] = (f, bedingungen)
        return f
    return eintragen


def route_finden(methode, pfad):
    if (methode, pfad) in ROUTEN:
        f, bed = ROUTEN[(methode, pfad)]
        return f, bed, ()
    if methode == "GET":
        for muster, f, bed in PRAEFIX_ROUTEN:
            m = muster.fullmatch(pfad)
            if m:
                return f, bed, m.groups()
    return None, None, ()


FALSCHER_SCHLUESSEL = {"GET": "falscher Schlüssel – Seite neu laden",
                       "POST": "Abgelehnt: falscher Schlüssel – Seite neu laden."}


def bearbeiten(anfrage):
    """Route nachschlagen, Bedingungen prüfen, Handler aufrufen. Rückgabe Antwort."""
    f, bed, gruppen = route_finden(anfrage.methode, anfrage.pfad)
    if not f or bed["quelle"] and not bed["quelle"].an():
        return NICHT_GEFUNDEN
    als_json = lambda status, d: Antwort(status, json.dumps(d, ensure_ascii=False), "application/json; charset=utf-8")
    try:
        if bed["mit_schluessel"] and str(anfrage.daten.get("k", "")) != schluessel():
            return als_json(403, {"ok": False, "text": FALSCHER_SCHLUESSEL[anfrage.methode]})
        args = list(gruppen)
        if bed["waggon"]:
            waggon = schluessel_von(anfrage.daten.get("mr", ""))
            if bed["review"] and not waggon.kann["review"]:
                return als_json(400, {"ok": False, "text": "Dieser Waggon hat kein Review"})
            args.append(waggon)
        if bed["struktur"]:
            struktur = seiten_struktur(anfrage.daten.get("mr", ""), anfrage.ansicht)
            if struktur is None:
                return als_json(200, {"ok": False, "text": "Seite unbekannt – neu laden"})
            args.append(struktur)
        r = f(anfrage, *args)
    except Fehler as e:
        r = (502, {"ok": False, "text": str(e)}) if anfrage.methode == "POST" else text_antwort(502, f"merge-train: {e}")
    except Exception as e:  # Fehler zeigen statt Verbindung abbrechen
        t = f"merge-train: {type(e).__name__}: {e}"
        r = (500, {"ok": False, "text": t}) if anfrage.methode == "POST" else text_antwort(500, t)
    if isinstance(r, Antwort):  # vor tuple: Antwort ist selbst ein (Named)Tuple
        return r
    if isinstance(r, dict):
        r = (200, r)
    return als_json(*r)


# ---- GET: Seiten

@route("GET", "ping", mit_schluessel=False)
def ping(anfrage):
    return Antwort(200, "merge-train", "text/plain")


@route("GET", "favicon.ico", mit_schluessel=False)
@route("GET", "favicon.svg", mit_schluessel=False)
def favicon(anfrage):
    return Antwort(200, FAVICON.strip(), "image/svg+xml")


@route("GET", "", mit_schluessel=False)
def start(anfrage):
    """Start: erster offener lokaler Waggon, sonst Zug (mit MR-Feld)."""
    if LOKAL.an():
        offen = [w for w in LOKAL.wagen() if w["status"] == "offen"]
        if offen:
            return weiterleitung(offen[0]["datei"])
        if not GITLAB.an():
            return Antwort(200, ALLES_DURCH)
    return Antwort(200, startseite())


@route("GET", "mrs", mit_schluessel=False, quelle=GITLAB)
def mrs(anfrage):
    return Antwort(200, startseite())


@route("GET", "mr-oeffnen", mit_schluessel=False, quelle=GITLAB)
def mr_oeffnen(anfrage):
    return weiterleitung(mr_vollstaendig(mr_ref(anfrage.daten.get("u", ""))).url)


@route("GET", re.compile(r"mr/(.*)", re.S), mit_schluessel=False, quelle=GITLAB)
def mr_seite_liefern(anfrage, kennung):
    try:
        datei, _, mr = mr_seite(Waggon.aus_id(kennung), ansicht=anfrage.seiten_ansicht)
    except Fehler as e:  # keine MR-Daten / kein Klon: Güterbahnhof anbieten
        return Antwort(200, startseite(str(e), kennung))
    if mr.id != kennung:  # Kennung kanonisch machen
        return weiterleitung("/mr/" + mr.id + (f"?{anfrage.abfrage}" if anfrage.abfrage else ""))
    return Antwort(200, open(datei, "rb").read())


@route("GET", re.compile(r".*\.html", re.S), mit_schluessel=False, quelle=LOKAL)
def projekt_seite_liefern(anfrage):
    repos = {dateiname(projektname(r)): r for r in finde_repos()}
    if anfrage.pfad not in repos:
        return NICHT_GEFUNDEN
    datei, _ = projekt_seite(repos[anfrage.pfad], ansicht=anfrage.seiten_ansicht)
    if not anfrage.seiten_ansicht:
        vorbauen(repos)  # startet im Hintergrund, die Seite geht trotzdem sofort raus
    return Antwort(200, open(datei, "rb").read())


# ---- GET: Daten der Seite

@route("GET", "zug.js", mit_schluessel=False)
@route("GET", "api/zug", mit_schluessel=False)
def zug(anfrage):
    """Der gemischte Zug aller eingeschalteten Quellen."""
    d = {"wagen": alle_wagen(anfrage.daten.get("akt")), "zeit": mr_liste()[1] if GITLAB.an() else None}
    if anfrage.pfad == "api/zug":
        return d
    return Antwort(200, "window.MR_ZUG=" + json.dumps(d, ensure_ascii=False) + ";", "text/javascript; charset=utf-8")


@route("GET", "api/review", waggon=True)
def api_review(anfrage, waggon):
    """Gespräch und (je nach Quelle) Review des Waggons."""
    return wagen_daten(waggon, anfrage.ansicht)


@route("GET", "api/stand", waggon=True)
def api_stand(anfrage, waggon):
    seite_lebt(waggon)
    return {"stand": stand(waggon, zustand_lesen(waggon)), "version": VERSION, "server": server_stand()}


@route("GET", "api/zeilen", struktur=True)
def api_zeilen(anfrage, struktur):
    """Kontext nachladen, Code im Popup."""
    try:
        von, bis = int(anfrage.daten.get("von", 1)), int(anfrage.daten.get("bis", 1))
    except ValueError:
        return 400, {"ok": False, "text": "von/bis ungültig"}
    return zeilen_daten(struktur, anfrage.daten.get("pfad", ""), von, bis)


@route("GET", "api/datei", struktur=True)
def api_datei(anfrage, struktur):
    """Zunächst ausgelassene (große/generierte) Datei nachladen."""
    try:
        return datei_nachladen(struktur, int(anfrage.daten.get("i", -1)))
    except ValueError:
        return 400, {"ok": False, "text": "i ungültig"}


@route("GET", "api/vergleich", struktur=True)
def api_vergleich(anfrage, struktur):
    return vergleich_daten(struktur, anfrage.daten.get("a", ""), anfrage.daten.get("b", ""))


# ---- POST: Aktionen der Seite (alle mit Schlüssel)

def mit_review(waggon, anfrage, ok, text, **mehr):
    """Antwort einer Aktion: bei Erfolg gleich die neuen Daten der Seite mit."""
    return dict(mehr, ok=ok, text=text, review=wagen_daten(waggon, anfrage.ansicht) if ok else None)


@route("POST", "/api/kommentar", waggon=True)
def api_kommentar(anfrage, waggon):
    if anfrage.daten.get("gespraech") or not waggon.kann["review"]:  # Fragen an den Agenten: Fäden, nie nach außen
        ok, text = gespraech_aktion(waggon, anfrage.daten)
    else:
        ok, text = kommentar_aktion(waggon, anfrage.daten)
    return mit_review(waggon, anfrage, ok, text)


@route("POST", "/api/gespraech", waggon=True)
def api_gespraech(anfrage, waggon):
    aktion = anfrage.daten.get("aktion")
    if aktion == "senden":
        ok, text, tid = feedback_senden(waggon)
        return mit_review(waggon, anfrage, ok, text, todo=tid)
    if aktion == "starten":
        return mit_review(waggon, anfrage, *session_starten(waggon))
    return 400, {"ok": False, "text": "unbekannte Aktion"}


@route("POST", "/api/hinweis", waggon=True, review=True)
def api_hinweis(anfrage, waggon):
    return mit_review(waggon, anfrage, *hinweis_aktion(waggon, anfrage.daten))


@route("POST", "/api/abschliessen", waggon=True, review=True)
def api_abschliessen(anfrage, waggon):
    ansicht = anfrage.ansicht
    if ansicht and ansicht[0] == "commit":
        return {"ok": False, "text": NUR_LESEN}
    ok, text, web = abschliessen(waggon)
    return {"web_url": web, "ok": ok, "text": text, "review": wagen_daten(waggon, ansicht)}


@route("POST", "/fertig")
def api_fertig(anfrage):
    d = anfrage.daten
    waggon = schluessel_von(d.get("mr") or Waggon(lokal=str(d.get("projekt", ""))).id)
    if not waggon.kann["fertig"]:
        return NICHT_GEFUNDEN
    ok, text = fertig(waggon.lokal, str(d.get("sha", "")))
    return 200 if ok else 400, {"ok": ok, "text": text, "wagen": alle_wagen(waggon.id)}


@route("POST", "/api/gitlab", quelle=GITLAB)
def api_gitlab(anfrage):
    """Güterbahnhof: GitLab nur auf Knopfdruck."""
    aktion = anfrage.daten.get("aktion")
    if aktion == "mrliste":
        items, _ = mr_liste_holen()
        return {"ok": True, "text": f"{len(items)} MR(s) aus GitLab geholt"}
    if aktion == "mrdaten":
        return mr_daten_holen(Waggon.aus_id(anfrage.daten.get("mr", "")))
    return 400, {"ok": False, "text": "unbekannte Aktion"}


def mr_daten_holen(mr):
    """MR-Daten und Entwürfe aus GitLab, gesendete Kommentare abgleichen, Seite gleich bauen."""
    vorher = zustand_lesen(mr).get("struktur")
    _, vorhanden = meta_und_entwuerfe(mr)
    if isinstance(vorhanden, Fehler):
        raise vorhanden
    with zustand(mr) as st:  # gesendete Kommentare abgleichen: in GitLab veröffentlicht oder verworfen?
        pub, verw = entwuerfe_abgleichen(mr, st, vorhanden)
    try:  # neu laden muss der Browser nur, wenn sich die Seite geändert hat
        mr_seite(mr)
        neu_laden = zustand_lesen(mr).get("struktur") != vorher
    except Fehler:
        neu_laden = True
    text = "MR-Daten geholt" + (f" · {verw} Entwurf/Entwürfe in GitLab verworfen – wieder lokal, "
                                "„Review abschließen“ sendet sie neu" if verw else "") + \
        (f" · {pub} in GitLab veröffentlicht" if pub else "")
    return {"ok": True, "text": text, "neu_laden": neu_laden}


# ---- HTTP

HERKUNFT = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
_LETZTE_ANFRAGE = [time.time()]
_LAUFEND, _LAUF_SPERRE = [0], threading.Lock()  # Anfragen in Arbeit: ein Neustart wartet auf sie


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.mit_anlass("GET " + self.path.split("?")[0], self.get)

    def do_POST(self):
        self.mit_anlass("POST " + self.path, self.post)

    def mit_anlass(self, name, f):
        ANLASS.name = name[:32]
        _LETZTE_ANFRAGE[0] = time.time()
        with _LAUF_SPERRE:
            _LAUFEND[0] += 1
        try:
            self.senden(f())
        finally:
            with _LAUF_SPERRE:
                _LAUFEND[0] -= 1
            ANLASS.name = None

    def get(self):
        pfad, _, abfrage = self.path.partition("?")
        q = {k: v[0] for k, v in urllib.parse.parse_qs(abfrage).items()}
        ansicht = ansicht_lesen(f'commit:{q["commit"]}' if q.get("commit") else f'seit:{q["seit"]}' if q.get("seit") else "")
        if (q.get("commit") or q.get("seit")) and not ansicht:
            return text_antwort(400, "merge-train: ungültiger Commit")
        return bearbeiten(Anfrage("GET", urllib.parse.unquote(pfad).lstrip("/"), abfrage, q, ansicht))

    def post(self):
        if self.headers.get("Origin", f"http://127.0.0.1:{PORT}") not in HERKUNFT:
            return Antwort(403, "verboten", "text/plain")
        try:
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except Exception as e:
            return Antwort(500, json.dumps({"ok": False, "text": f"merge-train: {type(e).__name__}: {e}"},
                                           ensure_ascii=False), "application/json; charset=utf-8")
        if d.get("aktion"):
            ANLASS.name = f"{self.path} {d['aktion']}"[:32]
        return bearbeiten(Anfrage("POST", self.path, "", d, None))

    def senden(self, antwort):
        if antwort.ort:
            self.send_response(antwort.status); self.send_header("Location", antwort.ort); self.end_headers()
            return
        body = antwort.inhalt.encode() if isinstance(antwort.inhalt, str) else antwort.inhalt
        self.send_response(antwort.status); self.send_header("Content-Type", antwort.typ)
        self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)


def dateizeiten(pfade):
    out = []
    for p in pfade:
        try: out.append(os.path.getmtime(p))
        except OSError: out.append(None)
    return out


def beobachten(srv, beobachtet):
    """Bis LEERLAUF_S ohne Anfrage oder bis Skript/Einstellung sich ändern; dann laufende Aktionen (z. B. „Review
    abschließen“) fertig werden lassen und den Server anhalten. Rückgabe: True = mit neuem Stand neu starten."""
    anfang, neu = dateizeiten(beobachtet), False
    while time.time() - _LETZTE_ANFRAGE[0] < LEERLAUF_S:
        time.sleep(2)
        jetzt = dateizeiten(beobachtet)
        if jetzt[0] is None:  # Skript umbenannt/gelöscht: beenden
            break
        if jetzt != anfang:
            neu = True; break
    bis = time.time() + 600
    while _LAUFEND[0] > 0 and time.time() < bis:
        time.sleep(0.2)
    srv.shutdown()
    return neu


def server():
    """Liefert ~/.cache/merge-train auf 127.0.0.1 aus, erzeugt Seiten beim Abruf frisch, nimmt „fertig“
    und die Review-Aktionen an. Beendet sich nach LEERLAUF_S ohne Anfrage, startet neu bei neuem Skript/neuer Einstellung."""
    schluessel()
    _LETZTE_ANFRAGE[0] = time.time()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    syntax.SERVER_SOCKET = srv.socket
    beobachtet = [SKRIPT, KONFIG_DATEI]
    neu = []
    threading.Thread(target=lambda: neu.append(beobachten(srv, beobachtet)), daemon=True).start()
    srv.serve_forever()
    srv.server_close()
    if neu and neu[0]:
        os.execv(sys.executable, [sys.executable, beobachtet[0], "--server"])


_SERVER_STAND = [0, None]


def server_stand():
    """Stand von merge-train selbst fürs HUD: letzter Commit des Repos, Zeit, noch nicht committete Änderungen in src/.
    Höchstens alle 30 s neu ermittelt (die Seiten fragen alle 4 s)."""
    if time.time() - _SERVER_STAND[0] > 30:
        repo = os.path.dirname(SKRIPT)
        roh = (git(repo, "log", "-1", "--format=%h%x1f%cd", "--date=format:%d.%m. %H:%M", check=False) or "").strip()
        if roh:
            commit, zeit = roh.split("\x1f")
            st = {"commit": commit, "zeit": zeit, "geaendert": bool((git(repo, "status", "--porcelain", "--", "src", check=False) or "").strip())}
        else:  # kein Git-Repo (z. B. kopierte Datei): Zeit der Datei
            st = {"commit": "", "zeit": datetime.fromtimestamp(os.path.getmtime(SKRIPT)).strftime("%d.%m. %H:%M"),
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
