"""Der kleine HTTP-Server auf 127.0.0.1: liefert Seiten und nimmt die Aktionen der Seite entgegen."""
import json, os, re, threading, time
import urllib.parse
from datetime import datetime
from .einstellungen import KONF, SKRIPT, dateiname, projektname, schluessel
from .waggon import Fehler, Ungueltig, Waggon
from .git import ANLASS, anlass, branch_aktualisieren, branch_pushen, finde_repos, git, statistik
from .zeilen import diff_enden
from .web import CSS, FAVICON, ICON, bild
from .akte import akte_lesen
from .abhaken import abhaken
from .beobachter import neue_zeilen, seite_veraltet
from .gitlab import GitLabFehler, mr_aus_kennung, mr_index, mr_liste, mr_liste_holen, mr_meta_holen, mr_ref, mr_vollstaendig, mr_waggon
from .ansichten import ansicht_lesen
from .seite import VERSION, branch_seite, myrling_seite, seiten_teile, startseite
from .myrling import anstehend_warten, im_hintergrund_holen
from .quellen import (BRANCH, GITLAB, LOKAL, MYRLING, SCHICHTEN, abgeben, alle_wagen, fertig, mr_erstellen, mr_planen,
                      projekt_einstellen, projekt_einstellung, quelle, schluessel_von)
from .zweig import branch_ort, projekt_von, projekt_waggon
from .zuhoerer import feedback_senden, horcht, kontext, prompt_lesen, prompt_vorschau, seite_lebt, session_starten, zuhoerer, zuhoerer_abmelden
from .review import (NUR_LESEN, abschliessen, auscheck_hinweis, auschecken_versuchen, datei_nachladen, hinweis_aktion, kommentar_aktion, mr_auschecken, mr_daten_holen, mr_gitlab_holen, seiten_struktur, stand,
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
                    branch_seite(projekt_waggon(r))
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

    @property
    def seite(self):
        """Schlüssel der Seite, von der die Anfrage kommt (Feld „seite“, MR.seite): der Server rechnet gegen ihre
        Struktur. Leer: die zuletzt gebaute."""
        return str(self.daten.get("seite") or "")


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
            mehr["struktur"] = seiten_struktur(Waggon.aus_id(anfrage.daten.get("mr", "")), anfrage.seite, anfrage.ansicht)
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
    """Logo einer Schicht (wer = extern in den Listen)."""
    q = next((q for q in SCHICHTEN if q.name == name and q.logo), None)
    return Antwort(200, bild(q.logo), "image/svg+xml") if q else NICHT_GEFUNDEN


@route("GET", "", mit_schluessel=False)
def start(anfrage):
    """Start: erster offener Waggon eines Projekts, sonst Zug (mit MR-Feld)."""
    if LOKAL.an():
        offen = [w for w in BRANCH.wagen() if w.get("projekt") and w["status"] == "offen"]
        if offen:
            return weiterleitung(offen[0]["datei"])
        if not (GITLAB.an() or MYRLING.an()):
            return Antwort(200, ALLES_DURCH)
    return Antwort(200, startseite())


@route("GET", "mrs", mit_schluessel=False, quelle=GITLAB)
def mrs(anfrage):
    return Antwort(200, startseite())


@route("GET", "mr-oeffnen", mit_schluessel=False, quelle=GITLAB)
def mr_oeffnen(anfrage):
    return weiterleitung(mr_vollstaendig(mr_ref(anfrage.daten.get("u", ""))).url)


@route("GET", re.compile(r"b/(.*)", re.S), mit_schluessel=False, quelle=BRANCH)
def branch_seite_liefern(anfrage, kennung):
    """Seite eines Branches (mit MR-Schicht, sobald MR-Daten geholt sind). Erster Besuch mit MR: Quell-Branch im
    Haupt-Klon auschecken (im Hintergrund)."""
    try:
        w = Waggon.aus_id(kennung)
        if not w.branch:
            return weiterleitung(w.url)
        datei, _ = branch_seite(w, ansicht=anfrage.seiten_ansicht)
    except Fehler as e:  # kein Klon, Branch fehlt …: Güterbahnhof mit dem Grund
        return Antwort(200, startseite(str(e), kennung))
    if w.id != kennung:  # Kennung kanonisch machen
        return weiterleitung(w.url + (f"?{anfrage.abfrage}" if anfrage.abfrage else ""))
    if akte_lesen(w).get("gitlab"):
        im_hintergrund(w, mr_auschecken)  # Seite nicht aufhalten; Meldung kommt über api/stand
    elif not anfrage.seiten_ansicht and LOKAL.an():
        vorbauen({r: r for r in finde_repos()})  # startet im Hintergrund, die Seite geht trotzdem sofort raus
    return Antwort(200, open(datei, "rb").read())


@route("GET", re.compile(r"mr/(.*)", re.S), mit_schluessel=False, quelle=GITLAB)
def mr_seite_liefern(anfrage, kennung):
    """Alte MR-Seite: weiter zum Branch, der den MR trägt; ohne MR-Daten der Güterbahnhof mit „↻ MR-Daten“."""
    mr = mr_aus_kennung(kennung)
    w = mr and mr_waggon(mr)
    if w:
        return weiterleitung(w.url + (f"?{anfrage.abfrage}" if anfrage.abfrage else ""))
    return Antwort(200, startseite(f"Für {mr.name if mr else kennung} gibt es noch keine MR-Daten – „↻ MR-Daten“ im "
                                   "Güterbahnhof holt sie", kennung))


@route("GET", re.compile(r"myrling/(.*)", re.S), mit_schluessel=False, quelle=MYRLING)
def myrling_seite_liefern(anfrage, skript):
    """Seite eines Laufs, der auf eine Prüfung wartet; steht er nicht (mehr) an: Güterbahnhof mit dem Grund."""
    waggon = Waggon.aus_id("myrling:" + skript)
    try:
        datei, _ = myrling_seite(waggon)
    except Fehler as e:
        return Antwort(200, startseite(str(e), waggon.id))
    return Antwort(200, open(datei, "rb").read())


@route("GET", re.compile(r".*\.html", re.S), mit_schluessel=False, quelle=LOKAL)
def projekt_seite_liefern(anfrage):
    """Alte Projekt-Seite: weiter zum Branch, den das Projekt gerade zeigt."""
    repos = {dateiname(projektname(r)): r for r in finde_repos(alle=True)}
    if anfrage.pfad not in repos:
        return NICHT_GEFUNDEN
    return weiterleitung(projekt_waggon(repos[anfrage.pfad]).url + (f"?{anfrage.abfrage}" if anfrage.abfrage else ""))


# ---- GET: Daten der Seite

@route("GET", "zug.js", mit_schluessel=False)
@route("GET", "api/zug", mit_schluessel=False)
def zug(anfrage):
    """Der gemischte Zug aller eingeschalteten Quellen. Myrling: zug.js (Laden einer Seite) holt dessen Liste im
    Hintergrund neu (nachladen: die Seite fragt dann api/zug?warten=1), api/zug nimmt die zuletzt geholte."""
    nachladen = anfrage.pfad == "zug.js" and MYRLING.an() and im_hintergrund_holen()
    if anfrage.pfad == "api/zug" and anfrage.daten.get("warten") and MYRLING.an():
        anstehend_warten()
    d = {"wagen": alle_wagen(anfrage.daten.get("akt")), "zeit": mr_liste()[1] if GITLAB.an() else None,
         "nachladen": bool(nachladen)}
    if anfrage.pfad == "api/zug":
        return d
    return Antwort(200, "window.MR_ZUG=" + json.dumps(d, ensure_ascii=False) + ";", "text/javascript; charset=utf-8")


@route("GET", "api/review", waggon=True)
def api_review(anfrage, waggon):
    """Gespräch und (je nach Quelle) Review des Waggons."""
    return wagen_daten(waggon, anfrage.ansicht, anfrage.seite)


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
    """Alle 4 s von jeder offenen Seite. veraltet: die Seite zeigt nicht mehr den neuesten Stand (seite_veraltet: neu
    gebaut, etwa von der CLI oder nach MR-Daten, bzw. mit --beobachten das Repo bewegt) → neu laden; Commit-Ansichten
    nie. meldung: Text aus im_hintergrund (z. B. „… ausgecheckt“) für die Glocke, einmal. auschecken: Hinweis, dass der
    Quell-Branch eines MR nicht ausgecheckt ist (auscheck_hinweis), mit Knopf."""
    seite_lebt(waggon)
    akte = akte_lesen(waggon)
    return {"stand": stand(waggon, akte), "meldung": MELDUNGEN.pop(waggon.id, None), "version": VERSION,
            "server": server_stand(), "auschecken": auscheck_hinweis(waggon, akte) if waggon.branch else None,
            "veraltet": bool(anfrage.seite) and not anfrage.ansicht and seite_veraltet(waggon, anfrage.seite, akte)}


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


@route("GET", "api/zuhoerer", mit_schluessel=False)
def api_zuhoerer(anfrage):
    """Kopfhörer in den Waggons (zug.js fragt alle 5 s): {Kennung: zuhoerer} für ids (Kennungen, durch Komma getrennt)."""
    erg = {}
    for kennung in str(anfrage.daten.get("ids", "")).split(",")[:100]:
        try:
            erg[kennung] = zuhoerer(Waggon.aus_id(kennung))
        except Fehler:
            pass
    return erg


@route("GET", "api/diff", waggon=True)
def api_diff(anfrage, waggon):
    """Neuer Stand für eine offene Seite (tausch.js), statt sie neu zu laden: baut die Seite zum heutigen Stand (derselben
    Ansicht) und liefert ihre Teile (seiten_teile) – von den Dateien nur die, deren Schlüssel die Seite noch nicht hat
    (die übrigen behält sie) –, dazu MR und die Zeilen, die seit ihrem Stand neu sind (Rahmen). gleich: nichts zu tun.
    Kennt der Server die Seite nicht mehr, kommen alle Dateien."""
    try:
        pfad, neu = quelle(waggon).seite(waggon, ansicht=anfrage.ansicht)
    except Fehler as e:
        return {"ok": False, "text": str(e)}
    teile = seiten_teile(pfad)
    if teile["mr"]["seite"] == anfrage.seite:
        return {"ok": True, "gleich": True}
    alt = seiten_struktur(waggon, anfrage.seite, anfrage.ansicht) if anfrage.seite else None
    da = {f.get("schluessel") for f in (alt or {}).get("dateien", [])}
    teile["dateien"] = [{"schluessel": s, "html": None if s in da else h} for s, h in teile["dateien"]]
    zeilen = neue_zeilen(neu["ordner"], diff_enden(alt)[1], diff_enden(neu)[1]) if alt else {}
    return dict(teile, ok=True, gleich=False, zeilen=zeilen)


@route("GET", "api/zeilen", struktur=True)
def api_zeilen(anfrage, struktur):
    """Kontext nachladen, Code im Popup."""
    try:
        von, bis = int(anfrage.daten.get("von", 1)), int(anfrage.daten.get("bis", 1))
    except ValueError:
        return abgelehnt(400, "von/bis ungültig")
    stand = anfrage.daten.get("sha") or None  # see_also "ref": Datei aus einem anderen Commit des Klons
    if stand and not re.fullmatch(r"[0-9a-f]{7,40}", stand):
        return abgelehnt(400, "sha ungültig")
    return zeilen_daten(struktur, anfrage.daten.get("pfad", ""), von, bis, stand)


@route("GET", "api/datei", struktur=True)
def api_datei(anfrage, struktur):
    """Zunächst ausgelassene (große/generierte) Datei nachladen."""
    try:
        return datei_nachladen(struktur, int(anfrage.daten.get("i", -1)))
    except ValueError:
        return abgelehnt(400, "i ungültig")


@route("GET", "api/vergleich", struktur=True)
def api_vergleich(anfrage, struktur):
    d = anfrage.daten
    def bereich(seite):
        try:
            return int(d[seite + "_von"]), int(d.get(seite + "_bis") or d[seite + "_von"])
        except (KeyError, ValueError):
            return None
    stand_b = d.get("b_sha") or None
    if stand_b and not re.fullmatch(r"[0-9a-f]{7,40}", stand_b):
        return abgelehnt(400, "b_sha ungültig")
    return vergleich_daten(struktur, d.get("a", ""), d.get("b", ""), bereich("a"), bereich("b"), stand_b)


def haken_struktur(waggon, seite):
    """Struktur der ganzen Seite (abgehakt wird immer im ganzen Diff, auch aus einer Commit-Ansicht)."""
    struktur = seiten_struktur(waggon, seite)
    if struktur is None:
        raise Fehler("Seite unbekannt – neu laden")
    return struktur


@route("GET", "api/abgehakt", waggon=True)
def api_abgehakt(anfrage, waggon):
    """Abgehakte Dateien beim Laden der Seite, Füllung dabei neu gerechnet (neuer Stand nimmt Haken weg)."""
    return abhaken(waggon, haken_struktur(waggon, anfrage.seite))


# ---- POST: Aktionen der Seite (alle mit Schlüssel)

@route("POST", "api/abgehakt", waggon=True)
def api_abhaken(anfrage, waggon):
    d = anfrage.daten
    return abhaken(waggon, haken_struktur(waggon, anfrage.seite), str(d.get("pfad", "")), bool(d.get("an")))


def mit_review(waggon, anfrage, ok, text, **mehr):
    """Antwort einer Aktion: bei Erfolg gleich die neuen Daten der Seite mit."""
    return dict(mehr, ok=ok, text=text, review=wagen_daten(waggon, anfrage.ansicht, anfrage.seite) if ok else None)


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


def prompt_aktion(anfrage, waggon):
    """vorschau: was der Agent beim Senden bekäme; prompt: was gesendet, aber noch nicht abgeholt ist, und was er
    zuletzt bekommen hat."""
    vorher = anfrage.daten.get("aktion") == "vorschau"
    try:
        p = prompt_vorschau(waggon) if vorher else \
            [dict(x, weg="wartet") for x in prompt_vorschau(waggon, entwuerfe=False)] + prompt_lesen(waggon)
    except Fehler as e:
        return {"ok": False, "text": str(e)}
    return {"ok": bool(p), "prompts": p,
            "text": "" if p else "Nichts zu senden – keine Entwürfe" if vorher else "Noch nichts an den Agenten gesendet"}


def abmelden_aktion(anfrage, waggon):
    wer = zuhoerer_abmelden(waggon)
    return mit_review(waggon, anfrage, bool(wer), f"{wer} hört nicht mehr zu – die Session bekommt davon nichts mit"
                      if wer else "Niemand hört zu")


GESPRAECH_AKTIONEN = {"senden": feedback_senden_aktion, "starten": session_starten_aktion,
                      "vorschau": prompt_aktion, "prompt": prompt_aktion, "abmelden": abmelden_aktion}


@route("POST", "api/gespraech", waggon=True)
def api_gespraech(anfrage, waggon):
    """Ganzes Gespräch: An Agent senden, Agenten-Session starten, Prompt zeigen (vorher bzw. zuletzt zugestellt),
    Zuhörer abmelden."""
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
    return {"web_url": web, "ok": ok, "text": text, "review": wagen_daten(waggon, ansicht, anfrage.seite)}


@route("POST", "fertig")
def api_fertig(anfrage):
    d = anfrage.daten
    waggon = schluessel_von(d.get("mr") or "projekt:" + str(d.get("projekt", "")))
    if not waggon.kann["fertig"]:
        return NICHT_GEFUNDEN
    sha = str(d.get("sha", ""))  # teil: „abgeben“ – nur die abgehakten Dateien (Teilstand <von>-wip)
    projekt = projekt_von(waggon)
    ok, text = abgeben(projekt, sha, haken_struktur(waggon, anfrage.seite)) if d.get("teil") else fertig(projekt, sha)
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
    name, index = anlass(), mr_index()
    def holen(mr):
        ANLASS.name = name
        try:
            w = mr_waggon(mr, index) or mr_meta_holen(mr)[0]  # neu: erst die MR-Daten, sie nennen den Branch
            return mr, mr_gitlab_holen(w), None
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
    """„↻ MR-Daten“: auf der Seite eines Branches mit MR-Schicht dessen MR; auf dem Güterbahnhof eines MR ohne Daten
    (Kennung des MR) holt es sie zum ersten Mal, die Seite geht dann zum Branch (url)."""
    kennung = str(anfrage.daten.get("mr", ""))
    mr = mr_aus_kennung(kennung)
    w = (mr and (mr_waggon(mr) or mr_meta_holen(mr)[0])) or Waggon.aus_id(kennung)
    return dict(mr_daten_holen(w), url=w.url)


def branch_aktion(anfrage, tun):
    """Knopf an der Stand-Meldung eines MR: tun(Klon, Branch, GitLab-SHA), dann die MR-Daten holen."""
    mr = Waggon.aus_id(anfrage.daten.get("mr", ""))
    meta = akte_lesen(mr).get("meta") or {}
    ordner, _ = branch_ort(mr)
    text = tun(ordner, mr.branch, (meta.get("diff_refs") or {}).get("head_sha") or "")
    try:  # der Branch ist schon geändert: scheitert GitLab, trotzdem melden und neu laden
        text += " · " + mr_daten_holen(mr)["text"]
    except Fehler as e:
        text += f" · MR-Daten nicht geholt: {e}"
    return {"ok": True, "text": text, "neu_laden": True}


def aktualisieren_aktion(anfrage):
    """Rote Meldung „GitLab ist weiter“: Quell-Branch im Klon von origin nachziehen (siehe branch_aktualisieren), dann
    die MR-Daten holen – wurde inzwischen weiter gepusht, ist origin schon neuer als der zuletzt geholte GitLab-Stand,
    und die Meldung bliebe sonst (ohne Knopf) stehen."""
    return branch_aktion(anfrage, lambda ordner, branch, _: branch_aktualisieren(ordner, branch))


def pushen_aktion(anfrage):
    """Meldung „lokal weiter / umgeschrieben“: Quell-Branch pushen (branch_pushen, umgeschrieben mit Lease auf den
    zuletzt geholten GitLab-Stand), dann die MR-Daten holen. Hat GitLab den Push noch nicht verarbeitet, sagt die
    Meldung danach „gepusht“ mit „↻ MR-Daten“."""
    return branch_aktion(anfrage, branch_pushen)


def lokales_projekt(anfrage):
    """Projekt (Ordner) des Branches ohne MR, von dessen Seite die Anfrage kommt (sonst Fehler)."""
    waggon = schluessel_von(anfrage.daten.get("mr", ""))
    if not waggon.branch or waggon.kann["review"]:
        raise Ungueltig("„MR erstellen“ gibt es nur auf der Seite eines Branches ohne MR")
    projekt = projekt_von(waggon)
    if not projekt:
        raise Fehler(f"{waggon.name}: kein Klon bekannt")
    return projekt


def mr_planen_aktion(anfrage):
    """„MR erstellen“, erster Klick: vorhandenen MR übernehmen oder den Vorschlag für die Rückfrage liefern."""
    return mr_planen(lokales_projekt(anfrage))


def mr_erstellen_aktion(anfrage):
    """„MR erstellen“ nach der Rückfrage (Ziel-Branch, Titel, Beschreibung, Entwurf aus dem Dialog)."""
    d = anfrage.daten
    return mr_erstellen(lokales_projekt(anfrage), str(d.get("ziel") or ""), str(d.get("titel") or ""),
                        str(d.get("beschreibung") or ""), bool(d.get("entwurf")))


def auschecken_aktion(anfrage):
    """Hinweis „nicht ausgecheckt“: Quell-Branch im Klon auschecken (nur bei sauberem Stand, auschecken_versuchen); ein
    eigener MR zeigt danach den Arbeitsstand."""
    mr = Waggon.aus_id(anfrage.daten.get("mr", ""))
    akte = akte_lesen(mr)
    if not akte.get("meta"):
        raise Fehler("Noch keine MR-Daten – erst „↻ MR-Daten“")
    erledigt, text = auschecken_versuchen(mr, akte)
    return {"ok": erledigt, "text": text or f"{mr.branch} ist ausgecheckt", "neu_laden": erledigt}


GITLAB_AKTIONEN = {"mrliste": mr_liste_aktion, "mrdaten": mr_daten_aktion, "aktualisieren": aktualisieren_aktion,
                   "pushen": pushen_aktion, "mrplanen": mr_planen_aktion, "mrerstellen": mr_erstellen_aktion,
                   "auschecken": auschecken_aktion}


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
