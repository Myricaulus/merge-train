"""Der kleine HTTP-Server auf 127.0.0.1: liefert Seiten und nimmt die Aktionen der Seite entgegen."""
import json, os, re, threading, time
import urllib.parse
from datetime import datetime
from .einstellungen import KONF, SKRIPT, dateiname, projektname, schluessel
from .waggon import Fehler, Ungueltig, Waggon
from .git import ANLASS, anlass, branch_aktualisieren, finde_repos, git, statistik
from .web import CSS, FAVICON, ICON, bild
from .akte import akte_lesen
from .abhaken import abhaken
from .beobachter import neue_zeilen, veraltet
from .gitlab import GitLabFehler, mr_liste, mr_liste_holen, mr_lokal, mr_ref, mr_vollstaendig
from .ansichten import ansicht_lesen
from .seite import VERSION, mr_seite, projekt_seite, startseite
from .quellen import GITLAB, LOKAL, QUELLEN, abgeben, alle_wagen, fertig, projekt_einstellen, projekt_einstellung, schluessel_von
from .zuhoerer import feedback_senden, horcht, kontext, seite_lebt, session_starten
from .review import (NUR_LESEN, abschliessen, datei_nachladen, hinweis_aktion, kommentar_aktion, mr_auschecken, mr_daten_holen, mr_gitlab_holen, seiten_struktur, stand,
    vergleich_daten, zeilen_daten)
from .gespraech import gespraech_aktion, wagen_daten
from http.server import BaseHTTPRequestHandler
from dataclasses import dataclass
from typing import NamedTuple
from . import syntax

PORT = int(KONF["port"])


ALLES_DURCH = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">{ICON}<title>merge-train: alles durch</title>
<style>{CSS}
.durch{{display:grid;place-items:center;min-height:100vh;text-align:center}} .durch div{{font-size:22vmin;line-height:1.25;margin-bottom:2vmin}}
.durch p{{font-size:20px;margin:12px 0 0}} .durch code{{font-size:.9em}}</style></head>
<body><main class="durch"><section><div>👍</div><p>Alles durch – überall ist bis auf dem Stand von von</p>
<p class="sub">Neue Commits holt <code>merge-train</code> beim nächsten Aufruf.</p></section></main></body></html>"""


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


# ---- Routen: Handler auf Modulebene, ein Eintrag je (Methode, Pfad ohne führendes „/“). Was viele brauchen, erledigt
# bearbeiten(): Schlüssel (mit_schluessel), eingeschaltete Quelle (quelle), Waggon aus „mr“ (waggon), „kann review“
# (review), Struktur der Seite (struktur), Fehler.
# Aufruf: handler(anfrage, *gruppen_der_regex, waggon=…, struktur=…) – die Schlüsselwörter nur, wenn die Route sie hat.
# Rückgabe: dict → JSON 200, sonst eine Antwort (json_antwort für einen anderen Status).

@dataclass(frozen=True)
class Antwort:
    status: int
    inhalt: object = b""
    typ: str = "text/html; charset=utf-8"
    ort: str = None  # Weiterleitung


def text_antwort(status, text, typ="text/plain; charset=utf-8"):
    return Antwort(status, text, typ)


def json_antwort(status, d):
    return Antwort(status, json.dumps(d, ensure_ascii=False), "application/json; charset=utf-8")


def abgelehnt(status, text):
    return json_antwort(status, {"ok": False, "text": text})


def weiterleitung(ziel):
    return Antwort(302, ort=ziel)


NICHT_GEFUNDEN = Antwort(404, "nicht gefunden", "text/plain")


class Anfrage(NamedTuple):
    methode: str
    pfad: str            # ohne führendes „/“ und ohne Query
    abfrage: str         # roher Query-String
    daten: dict          # GET: Query-Parameter, POST: JSON-Rumpf
    seiten_ansicht: tuple  # GET ?commit=… / ?seit=… für Seiten

    @property
    def will_json(self):
        """Fehler als JSON (POST und api/…) oder als Text (Seiten)."""
        return self.methode == "POST" or self.pfad.startswith("api/")

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


def fehler_antwort(anfrage, status, text):
    return abgelehnt(status, text) if anfrage.will_json else text_antwort(status, f"merge-train: {text}")


def fehler_status(e):
    """Ungueltig → 400 (Eingabe), GitLabFehler → 502 (GitLab/glab), sonst Fehler → 409 (passt nicht zum Stand)."""
    return 400 if isinstance(e, Ungueltig) else 502 if isinstance(e, GitLabFehler) else 409


def bearbeiten(anfrage):
    """Route nachschlagen, Bedingungen prüfen, Handler aufrufen. Rückgabe Antwort."""
    f, bed, gruppen = route_finden(anfrage.methode, anfrage.pfad)
    if not f or bed["quelle"] and not bed["quelle"].an():
        return NICHT_GEFUNDEN
    try:
        if bed["mit_schluessel"] and str(anfrage.daten.get("k", "")) != schluessel():
            return fehler_antwort(anfrage, 403, "falscher Schlüssel – Seite neu laden")
        mehr = {}
        if bed["waggon"]:
            mehr["waggon"] = schluessel_von(anfrage.daten.get("mr", ""))
            if bed["review"] and not mehr["waggon"].kann["review"]:
                return abgelehnt(400, "Dieser Waggon hat kein Review")
        if bed["struktur"]:
            mehr["struktur"] = seiten_struktur(anfrage.daten.get("mr", ""), anfrage.ansicht)
            if mehr["struktur"] is None:
                return json_antwort(200, {"ok": False, "text": "Seite unbekannt – neu laden"})
        r = f(anfrage, *gruppen, **mehr)
    except Fehler as e:
        return fehler_antwort(anfrage, fehler_status(e), str(e))
    except Exception as e:  # Fehler zeigen statt Verbindung abbrechen
        return fehler_antwort(anfrage, 500, f"{type(e).__name__}: {e}")
    return json_antwort(200, r) if isinstance(r, dict) else r


# ---- GET: Seiten

@route("GET", "ping", mit_schluessel=False)
def ping(anfrage):
    return Antwort(200, "merge-train", "text/plain")


@route("GET", "favicon.ico", mit_schluessel=False)
@route("GET", "favicon.svg", mit_schluessel=False)
def favicon(anfrage):
    return Antwort(200, FAVICON.strip(), "image/svg+xml")


@route("GET", re.compile(r"logo/(\w+)\.svg"), mit_schluessel=False)
def logo(anfrage, name):
    """Logo einer Quelle (wer = extern in den Listen)."""
    q = next((q for q in QUELLEN if q.name == name and q.logo), None)
    return Antwort(200, bild(q.logo), "image/svg+xml") if q else NICHT_GEFUNDEN


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
    im_hintergrund(mr, mr_auschecken)  # Seite nicht aufhalten; Meldung kommt über api/stand
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


MELDUNGEN = {}  # Waggon-id → Text für die Glocke, den die nächste Abfrage von api/stand abholt


def im_hintergrund(waggon, arbeit):
    """arbeit(waggon) in einem Thread; ihr Text (falls einer) geht über api/stand an die offene Seite."""
    def los():
        try:
            text = arbeit(waggon)
        except Exception as e:  # z. B. git nicht erreichbar – die Seite soll trotzdem davon erfahren
            text = f"{arbeit.__name__}: {e}"
        if text:
            MELDUNGEN[waggon.id] = text
    threading.Thread(target=los, daemon=True).start()


@route("GET", "api/stand", waggon=True)
def api_stand(anfrage, waggon):
    """Alle 4 s von jeder offenen Seite. veraltet (nur --beobachten): im Repo hat sich etwas geändert → neu laden.
    seite: die zuletzt gebaute Seite des MR – im Hintergrund neu gebaut (z. B. MR-Daten aus dem Zug) → neu laden.
    meldung: Text aus im_hintergrund (z. B. „… ausgecheckt“) für die Glocke, einmal."""
    seite_lebt(waggon)
    akte = akte_lesen(waggon)
    return {"stand": stand(waggon, akte), "seite": None if waggon.lokal else akte.get("struktur"),
            "meldung": MELDUNGEN.pop(waggon.id, None), "version": VERSION, "server": server_stand(),
            "veraltet": not anfrage.daten.get("ansicht") and veraltet(waggon, anfrage.daten.get("sha", ""))}


@route("GET", "api/hud", mit_schluessel=False)
def api_hud(anfrage):
    """HUD der Startseite (ohne Review): Stand des Servers und, wenn sie zu einem Waggon gehört (z. B. „kein lokaler
    Klon“), wer dort zuhört und Meldungen für die Glocke (wie api/stand)."""
    d = {"server": server_stand(), "version": VERSION, "horcht": None, "kontext": None}
    try:
        waggon = schluessel_von(anfrage.daten.get("mr", ""))
    except Fehler:  # Startseite ohne Waggon
        return d
    seite_lebt(waggon)  # offene Seite des Waggons: horchen hört nicht auf
    return dict(d, horcht=horcht(waggon), kontext=kontext(waggon), meldung=MELDUNGEN.pop(waggon.id, None))


@route("GET", "api/neu", waggon=True)
def api_neu(anfrage, waggon):
    """--beobachten nach dem Neuladen: Zeilen, die seit dem vorher gezeigten Stand neu sind (Rahmen auf der Seite)."""
    return {"ok": True, "zeilen": neue_zeilen(waggon, anfrage.daten.get("alt", ""), anfrage.daten.get("sha", ""))}


@route("GET", "api/zeilen", struktur=True)
def api_zeilen(anfrage, struktur):
    """Kontext nachladen, Code im Popup."""
    try:
        von, bis = int(anfrage.daten.get("von", 1)), int(anfrage.daten.get("bis", 1))
    except ValueError:
        return abgelehnt(400, "von/bis ungültig")
    return zeilen_daten(struktur, anfrage.daten.get("pfad", ""), von, bis)


@route("GET", "api/datei", struktur=True)
def api_datei(anfrage, struktur):
    """Zunächst ausgelassene (große/generierte) Datei nachladen."""
    try:
        return datei_nachladen(struktur, int(anfrage.daten.get("i", -1)))
    except ValueError:
        return abgelehnt(400, "i ungültig")


@route("GET", "api/vergleich", struktur=True)
def api_vergleich(anfrage, struktur):
    return vergleich_daten(struktur, anfrage.daten.get("a", ""), anfrage.daten.get("b", ""))


def haken_struktur(waggon):
    """Struktur des ganzen Waggons (abgehakt wird immer im ganzen Diff, auch aus einer Commit-Ansicht)."""
    struktur = seiten_struktur(waggon.id)
    if struktur is None:
        raise Fehler("Seite unbekannt – neu laden")
    return struktur


@route("GET", "api/abgehakt", waggon=True)
def api_abgehakt(anfrage, waggon):
    """Abgehakte Dateien beim Laden der Seite, Füllung dabei neu gerechnet (neuer Stand nimmt Haken weg)."""
    return abhaken(waggon, haken_struktur(waggon))


# ---- POST: Aktionen der Seite (alle mit Schlüssel)

@route("POST", "api/abgehakt", waggon=True)
def api_abhaken(anfrage, waggon):
    d = anfrage.daten
    return abhaken(waggon, haken_struktur(waggon), str(d.get("pfad", "")), bool(d.get("an")))


def mit_review(waggon, anfrage, ok, text, **mehr):
    """Antwort einer Aktion: bei Erfolg gleich die neuen Daten der Seite mit."""
    return dict(mehr, ok=ok, text=text, review=wagen_daten(waggon, anfrage.ansicht) if ok else None)


@route("POST", "api/kommentar", waggon=True)
def api_kommentar(anfrage, waggon):
    if anfrage.daten.get("gespraech") or not waggon.kann["review"]:  # Fragen an den Agenten: Fäden, nie nach außen
        ok, text = gespraech_aktion(waggon, anfrage.daten)
    else:
        ok, text = kommentar_aktion(waggon, anfrage.daten)
    return mit_review(waggon, anfrage, ok, text)


def feedback_senden_aktion(anfrage, waggon):
    ok, text, todo_id = feedback_senden(waggon)
    return mit_review(waggon, anfrage, ok, text, todo=todo_id)


def session_starten_aktion(anfrage, waggon):
    return mit_review(waggon, anfrage, *session_starten(waggon))


GESPRAECH_AKTIONEN = {"senden": feedback_senden_aktion, "starten": session_starten_aktion}


@route("POST", "api/gespraech", waggon=True)
def api_gespraech(anfrage, waggon):
    """Ganzes Gespräch: Feedback senden, Agenten-Session starten."""
    aktion = GESPRAECH_AKTIONEN.get(anfrage.daten.get("aktion"))
    return aktion(anfrage, waggon) if aktion else abgelehnt(400, "unbekannte Aktion")


@route("POST", "api/hinweis", waggon=True, review=True)
def api_hinweis(anfrage, waggon):
    return mit_review(waggon, anfrage, *hinweis_aktion(waggon, anfrage.daten))


@route("POST", "api/abschliessen", waggon=True, review=True)
def api_abschliessen(anfrage, waggon):
    ansicht = anfrage.ansicht
    if ansicht and ansicht[0] == "commit":
        return {"ok": False, "text": NUR_LESEN}
    ok, text, web = abschliessen(waggon, direkt=bool(anfrage.daten.get("direkt")),
                                 urteil=anfrage.daten.get("urteil") or "kommentieren")
    return {"web_url": web, "ok": ok, "text": text, "review": wagen_daten(waggon, ansicht)}


@route("POST", "fertig")
def api_fertig(anfrage):
    d = anfrage.daten
    waggon = schluessel_von(d.get("mr") or Waggon(lokal=str(d.get("projekt", ""))).id)
    if not waggon.kann["fertig"]:
        return NICHT_GEFUNDEN
    sha = str(d.get("sha", ""))  # teil: „abgeben“ – nur die abgehakten Dateien (Teilstand <von>-wip)
    ok, text = abgeben(waggon.lokal, sha, haken_struktur(waggon)) if d.get("teil") else fertig(waggon.lokal, sha)
    return json_antwort(200 if ok else 400, {"ok": ok, "text": text, "wagen": alle_wagen(waggon.id)})


@route("GET", "api/projekt", quelle=LOKAL)
def api_projekt(anfrage):
    """Aufgeklappter Waggon eines lokalen Projekts: Infos, von/bis und die Branches zur Auswahl."""
    return projekt_einstellung(str(anfrage.daten.get("p", "")))


@route("POST", "api/projekt", quelle=LOKAL)
def api_projekt_einstellen(anfrage):
    """von/bis des Projekts wählen (leer bzw. gleich dem Standard: Standard aus der Einstellung). Danach der neue Zug."""
    d = anfrage.daten
    ok, text = projekt_einstellen(str(d.get("p", "")), str(d.get("von") or ""), str(d.get("bis") or ""))
    return json_antwort(200 if ok else 400, {"ok": ok, "text": text, "wagen": alle_wagen(d.get("akt"))})


def mr_liste_aktion(anfrage):
    """„↻ MRs“: die Liste, dann je MR MR-Daten, Entwürfe und Diskussionen (parallel, ohne die Seiten zu bauen)."""
    from concurrent.futures import ThreadPoolExecutor
    items, _ = mr_liste_holen()
    mrs = []
    for it in items:
        try:
            mrs.append(mr_ref(it.get("web_url", "")))
        except Fehler:
            pass
    name = anlass()
    def holen(mr):
        ANLASS.name = name
        try:
            return mr, mr_gitlab_holen(mr), None
        except Fehler as e:
            return mr, [], e
    with ThreadPoolExecutor(4) as ex:
        ergebnisse = list(ex.map(holen, mrs))
    text = f"{len(items)} MR(s) aus GitLab geholt"
    for mr, teile, fehler in ergebnisse:
        if fehler or teile:
            text += f"\n!{mr.iid}: " + (f"Fehler: {fehler}" if fehler else " · ".join(teile))
    return {"ok": True, "text": text}


def mr_daten_aktion(anfrage):
    return mr_daten_holen(Waggon.aus_id(anfrage.daten.get("mr", "")))


def aktualisieren_aktion(anfrage):
    """Rote Meldung „GitLab ist weiter“: Quell-Branch im Klon von origin nachziehen (siehe branch_aktualisieren), dann
    die MR-Daten holen – wurde inzwischen weiter gepusht, ist origin schon neuer als der zuletzt geholte GitLab-Stand,
    und die Meldung bliebe sonst (ohne Knopf) stehen."""
    mr = Waggon.aus_id(anfrage.daten.get("mr", ""))
    meta = akte_lesen(mr).get("meta") or {}
    ordner, _ = mr_lokal(mr, meta)
    text = branch_aktualisieren(ordner, meta.get("source_branch") or "")
    try:  # der Branch ist schon nachgezogen: scheitert GitLab, trotzdem melden und neu laden
        text += " · " + mr_daten_holen(mr)["text"]
    except Fehler as e:
        text += f" · MR-Daten nicht geholt: {e}"
    return {"ok": True, "text": text, "neu_laden": True}


GITLAB_AKTIONEN = {"mrliste": mr_liste_aktion, "mrdaten": mr_daten_aktion, "aktualisieren": aktualisieren_aktion}


@route("POST", "api/gitlab", quelle=GITLAB)
def api_gitlab(anfrage):
    """Güterbahnhof: GitLab nur auf Knopfdruck."""
    aktion = GITLAB_AKTIONEN.get(anfrage.daten.get("aktion"))
    return aktion(anfrage) if aktion else abgelehnt(400, "unbekannte Aktion")


@route("POST", "stopp")
def api_stopp(anfrage):
    """merge-train --stopp: wie Leerlauf, laufende Aktionen werden noch fertig."""
    _STOPP.set()
    return {"ok": True, "text": "Server beendet sich"}


@route("POST", "tschuess")
def api_tschuess(anfrage):
    """--beobachten: Tab verlassen (Beacon bei pagehide, auch beim Neuladen). Kommt danach nichts mehr, endet der Server."""
    if KONF["beobachten"]:
        _ABSCHIED[0] = _LETZTE_ANFRAGE[0]
    return {"ok": True}


# ---- HTTP

HERKUNFT = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
_LETZTE_ANFRAGE = [time.time()]
_STOPP = threading.Event()  # merge-train --stopp
_ABSCHIED = [None]  # --beobachten: Zeit der letzten Anfrage vor dem Beacon „Tab zu“
ABSCHIED_S = 10  # so lange nach dem Beacon auf eine neue Anfrage (Neuladen) warten
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
            daten = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if not isinstance(daten, dict):
                raise ValueError("kein JSON-Objekt")
        except ValueError as e:
            return abgelehnt(400, f"merge-train: ungültiges JSON: {e}")
        if daten.get("aktion"):
            ANLASS.name = f"{self.path} {daten['aktion']}"[:32]
        return bearbeiten(Anfrage("POST", self.path.partition("?")[0].lstrip("/"), "", daten, None))

    def senden(self, antwort):
        if antwort.ort:
            self.send_response(antwort.status); self.send_header("Location", antwort.ort); self.end_headers()
            return
        body = antwort.inhalt.encode() if isinstance(antwort.inhalt, str) else antwort.inhalt
        self.send_response(antwort.status); self.send_header("Content-Type", antwort.typ)
        self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)


_SERVER_STAND = [0, None]


def server_stand():
    """Stand von merge-train selbst fürs HUD: letzter Commit des Repos, Zeit, noch nicht committete Änderungen in src/.
    Höchstens alle 30 s neu ermittelt (die Seiten fragen alle 4 s)."""
    if time.time() - _SERVER_STAND[0] > 30:
        repo = os.path.dirname(SKRIPT)
        roh = (git(repo, "log", "-1", "--format=%h%x1f%cd", "--date=format:%d.%m. %H:%M", check=False) or "").strip()
        if roh:
            commit, zeit = roh.split("\x1f")
            akte = {"commit": commit, "zeit": zeit, "geaendert": bool((git(repo, "status", "--porcelain", "--", "src", check=False) or "").strip())}
        else:  # kein Git-Repo (z. B. kopierte Datei): Zeit der Datei
            akte = {"commit": "", "zeit": datetime.fromtimestamp(os.path.getmtime(SKRIPT)).strftime("%d.%m. %H:%M"),
                  "geaendert": False}
        _SERVER_STAND[:] = [time.time(), akte]
    return _SERVER_STAND[1]
