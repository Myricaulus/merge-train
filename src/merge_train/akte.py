"""Akte je Waggon: eine JSON-Datei mit Review-Kommentaren, Gesprächsfäden und Hinweis-Status, dazu die Struktur der
gebauten Seite.

Zugriff nur hierüber: ändern mit `with akte_bearbeiten(waggon) as akte:` (sperrt, lädt, speichert am Ende, wenn sich
etwas geändert hat; bei einer Ausnahme nicht), nur lesen mit `akte_lesen(waggon)`.

Ablage (docs/branch-waggon.md): ein Branch ist eine Akte, zweige/<repo>/<branch>.json (beides quote(…, safe="")), in
allen Klonen und Worktrees des Repos dieselbe; Myrling myrling/<skript>.json. Begleitdateien (.horcht, .prompt …)
daneben. lokal/<projekt>.json ist die Projekt-Akte eines Ordners: nur zweige (von/bis auf der Seite gewählt).
reviews/<mr>.json: nur alte MR-Akten ohne MR-Daten (Quell-Branch unbekannt) – das nächste „MR-Daten holen“ nimmt sie in
die Akte des Branches mit (mr_meta_holen). Fäden gelöschter oder in von gemergter Branches räumt
quellen.zweige_aufraeumen nach zweige/<repo>/archiv/. Alte Akten (vor Schritt 5) verteilt akten_migrieren einmal.

Aufbau einer Akte:
  mr               Waggon.als_dict() ({repo, branch} bzw. {myrling})
  gitlab           MR-Schicht: {host, projekt, iid, web_url, titel, source_branch, target_branch} des MR zu diesem
                   Branch, sobald MR-Daten geholt sind (gitlab.mr_meta_holen); ohne: keine Kommentare der Quelle
  meta             MR-Daten aus GitLab (META_FELDER in gitlab.py, _zeit = Abruf)
  klon             gemerkter Klon (agent zeigen, MR erstellen), falls er sonst nicht zu finden ist
  kommentare       Review-Kommentare und Gesprächsfäden gemischt; Fäden haben „nachrichten“.
                   Zugriff über review_kommentare / faeden_von / kommentar_finden / faden_finden.
  reihenfolge      ids/keys der Box „GitLab-Kommentare“, wie vom Nutzer sortiert
  hinweise         {key: uebernommen | verworfen} für Agent-Hinweise (drafts); fehlt der key, ist er offen
  hinweis_dateien  angemeldete Review-JSONs (agent zeigen)
  hinweis_agenten  {pfad: Name} der Agent, der die Review-JSON geprüft/angemeldet hat (agent pruefen|zeigen), falls
                   die JSON selbst kein „agent“ nennt
  struktur         Pfad der Cache-JSON der zuletzt gebauten Seite (struktur_laden), für die CLI und als Maß, ob eine
                   offene Seite veraltet ist (seite_veraltet); eine Seite selbst nennt ihre eigene (seiten_struktur)
  todo_id          todo-Eintrag aus „An Agent senden“, wenn niemand zuhörte
  abgeschlossen    Zeit des letzten vollständigen „Review abschließen“
  abgehakt, fuellung  abgehakte Dateien der Seite und die Füllung des Waggons (abhaken.py)

Review-Kommentar: id, refs {head_sha, base_sha, start_sha} beim Schreiben, erstellt, path, old_path, a (alte Zeile),
  b (neue Zeile), text, finding/hinweis/agent (aus einem übernommenen draft), gitlab_id, gitlab_text, gitlab_art
  (position | allgemein | mr | antwort), gitlab_weg (veröffentlicht), geloescht (beim Abschließen löschen),
  antwort_auf (id einer GitLab-Diskussion: Antwort darauf statt eigener Kommentar),
  gitlab_diskussion (veröffentlicht, von „MR-Daten“: id, note_id, erledigt {wer, zeit} oder None,
  antworten [{id, wer, wer_id, text, zeit}]).
  diskussionen     alle Diskussionen des MR aus GitLab („MR-Daten“, „MRs“): id, note_id, wer, wer_id, text, zeit, path,
                   old_path, a, b, head_sha (Stand des Kommentars), loesbar, erledigt, antworten – nur MRs
  ich_id           meine GitLab-Benutzer-id (wer: du oder extern)
  ausgecheckt      zeit, zu der mr_auschecken den Quell-Branch im Klon ausgecheckt hat (oder er schon/anderswo da war)
  auscheck_grund   warum der letzte Versuch nicht ausgecheckt hat (auschecken_versuchen; Hinweis auf der Seite)
  diskussionen_abgehakt  {diskussion-id: zeit}: „☑ abwarten“ (Ball ohne Antwort abgegeben, in GitLab noch offen); gilt,
                   bis ein anderer danach schreibt (diskussion_abgehakt)
  Stufe: kommentar_status, ist_staged, ist_sent (Begriffe in AGENTS.md).
Gesprächsfaden: id, branch, refs, erstellt, path, old_path, a, b, ab (erste Zeile, wenn der Faden an den neuen Zeilen
  ab–b hängt), zeile_text (Zeile b), ab_text (Zeile ab), an (Agent, sonst Claude), vom_agenten, see_also,
  zu („k:<Kommentar-id>“ | „h:<Hinweis-key>“: der Faden hängt an diesem GitLab-Kommentar, Ziel ist dessen Text),
  nachrichten [{id, von: ich | claude, wer, text, zeit, gesendet, abgeholt}], erledigt {von, zeit, wer} oder None,
  archiv (nach „fertig“ aus der Ansicht genommen). Stufe: faden_status.
  branch: der Branch der Akte (faeden_von(akte, branch)); ein Faden ohne Branch (alte Akten) gehört zu keinem.
"""
import fcntl, glob, json, os, sys, threading
from datetime import datetime
from urllib.parse import quote, unquote
from .einstellungen import DATEN, SPERRE, ersetzen, jetzt
from contextlib import contextmanager

def akte_datei(waggon, endung=".json"):
    """Branch: zweige/<repo>/<branch><endung>, Myrling: myrling/<skript><endung>; andere endung: Begleitdatei daneben
    (.horcht, .prompt …)."""
    akten_migrieren()
    if waggon.branch:
        return zweig_datei(waggon.repo, waggon.branch, endung)
    return os.path.join(DATEN, waggon.art.ordner, waggon.dateiname + endung)


ZWEIGE = "zweige"  # Ordner unter DATEN


def zweig_ordner(repo):
    return os.path.join(DATEN, ZWEIGE, quote(repo, safe=""))


def zweig_datei(repo, branch, endung=".json"):
    """zweige/<repo>/<branch>.json – quote(…, safe=""), damit a/b und a_b nicht kollidieren."""
    return os.path.join(zweig_ordner(repo), quote(branch, safe="") + endung)


def zweig_akten(repo):
    """Akten aller Branches des Repos: [(branch, pfad)] (ohne archiv/)."""
    ordner = zweig_ordner(repo)
    return [(unquote(n[:-5]), os.path.join(ordner, n)) for n in sorted(os.listdir(ordner) if os.path.isdir(ordner) else [])
            if n.endswith(".json") and not n.startswith(".")]


def andere_zweig_akten(waggon):
    """Branch: Pfade der Akten der anderen Branches seines Repos (für „fremde Fäden“, agent antworten), sonst []."""
    return [p for b, p in zweig_akten(waggon.repo) if b != waggon.branch] if waggon.branch else []


def projekt_akte_datei(projekt):
    """lokal/<name>.json: Projekt-Akte eines Ordners (von/bis der Seite)."""
    return os.path.join(DATEN, "lokal", projekt.replace("/", "_") + ".json")


def _json_lesen(pfad):
    """JSON-Datei, None wenn sie fehlt oder kaputt ist."""
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def projekt_akte_lesen(projekt):
    """Projekt-Akte roh."""
    return _json_lesen(projekt_akte_datei(projekt)) or {}


@contextmanager
def projekt_akte_bearbeiten(projekt):
    """Projekt-Akte gesperrt ändern (von/bis der Seite, projekt_einstellen)."""
    with akten_sperre():
        akte = projekt_akte_lesen(projekt)
        vorher = json.dumps(akte, sort_keys=True)
        yield akte
        if json.dumps(akte, sort_keys=True) != vorher:
            ersetzen(projekt_akte_datei(projekt), json.dumps(akte, ensure_ascii=False, indent=1))


def akten_vereinigen(ziel, dazu):
    """Akte dazu in ziel aufnehmen: Kommentare/Fäden nach id vereinigt, übrige Felder nur, wo ziel keins hat."""
    da = {k.get("id") for k in ziel.setdefault("kommentare", [])}
    ziel["kommentare"] += [k for k in dazu.get("kommentare") or [] if k.get("id") not in da]
    for f, v in dazu.items():
        if f not in ("kommentare", "mr"):
            ziel.setdefault(f, v)
    return ziel


MR_FELDER = ("web_url", "titel", "source_branch", "target_branch")  # standen bis Schritt 5 in „mr“ der MR-Akte


def gitlab_schicht(alt_mr, meta=None):
    """Feld „gitlab“ aus dem „mr“ einer alten MR-Akte (host, projekt, iid, MR_FELDER)."""
    meta = meta or {}
    return {"host": alt_mr.get("host"), "projekt": alt_mr.get("projekt"), "iid": alt_mr.get("iid"),
            **{f: alt_mr.get(f) or meta.get({"titel": "title"}.get(f, f)) or "" for f in MR_FELDER}}


_MIGRIERT = [False]
MIGRATION = ".schritt5"  # Marker unter DATEN


def akten_migrieren():
    """Einmal (Marker DATEN/.schritt5): Akten von vor Schritt 5 auf zweige/<repo>/<branch>.json verteilen – die alte
    Akte je Projekt (lokal/<p>.json) bzw. ihre Branch-Akten aus 4a (zweige/<p>/…, Verweise fallen weg) und jede MR-Akte
    mit Quell-Branch (reviews/…, MR-Felder nach „gitlab“). Vorher eine Kopie nach DATEN/vor-schritt-5/."""
    if _MIGRIERT[0] or not os.path.isdir(DATEN) or os.path.exists(os.path.join(DATEN, MIGRATION)):
        _MIGRIERT[0] = True
        return
    with akten_sperre():
        if os.path.exists(os.path.join(DATEN, MIGRATION)):
            _MIGRIERT[0] = True
            return
        _MIGRIERT[0] = True  # gegen Rekursion: die Teile unten lösen Repos auf
        import shutil
        sicher = os.path.join(DATEN, "vor-schritt-5")
        if not os.path.exists(sicher):
            shutil.copytree(DATEN, sicher, ignore=lambda d, n: [x for x in n if x == "vor-schritt-5" or x.startswith(".")])
        neu = {}  # Pfad der neuen Akte → Akte
        def dazu(repo, branch, akte, begleit=None):
            pfad = zweig_datei(repo, branch)
            ziel = neu.get(pfad) or _json_lesen(pfad) or {}
            ziel["mr"] = {"repo": repo, "branch": branch}
            for k in akte.get("kommentare") or []:
                if k.get("nachrichten") is not None:
                    k.setdefault("branch", branch)
            neu[pfad] = akten_vereinigen(ziel, akte)
            for alt in begleit or []:  # .prompt, .agent, .seite nebenher (.horcht gehört einem laufenden horchen)
                for e in (".prompt", ".agent", ".seite"):
                    if os.path.exists(alt + e) and not os.path.exists(zweig_datei(repo, branch, e)):
                        os.makedirs(zweig_ordner(repo), exist_ok=True)
                        os.replace(alt + e, zweig_datei(repo, branch, e))
        _lokale_migrieren(dazu)
        for p in glob.glob(os.path.join(DATEN, "reviews", "*.json")):
            akte = _json_lesen(p) or {}
            m = akte.get("mr") or {}
            quelle = m.get("source_branch") or (akte.get("meta") or {}).get("source_branch")
            if not (m.get("projekt") and m.get("iid") and quelle):
                continue  # ohne MR-Daten: bleibt, bis „MR-Daten holen“ sie mitnimmt
            akte["gitlab"] = gitlab_schicht(m, akte.get("meta"))
            akte.pop("mr")
            dazu(m["projekt"].lower(), quelle, akte, [p[:-5]])
            os.remove(p)
        for pfad, akte in neu.items():
            ersetzen(pfad, json.dumps(akte, ensure_ascii=False, indent=1))
        ersetzen(os.path.join(DATEN, MIGRATION), jetzt())


def _lokale_migrieren(dazu):
    """Teil von akten_migrieren: lokale Akten je Projekt (lokal/<p>.json mit Fäden) und die Branch-Akten aus 4a
    (zweige/<p>/<branch>.json) des Projekts p in die Akten seines Repos; die Projekt-Akte behält nur zweige."""
    from .git import branch_von, projekt_wurzel, repo_kennung
    from .waggon import Fehler
    def repo_von(p):
        try:
            w = projekt_wurzel(p)
        except Fehler:
            return None, None
        return w, repo_kennung(w)
    for p in glob.glob(os.path.join(DATEN, "lokal", "*.json")):
        akte = _json_lesen(p) or {}
        projekt = (akte.get("mr") or {}).get("lokal")
        if not projekt:
            continue
        wurzel, repo = repo_von(projekt)
        if not repo:
            continue
        aktuell = branch_von(wurzel)
        je_branch = {}
        for k in akte.pop("kommentare", None) or []:
            je_branch.setdefault(k.get("branch") or aktuell, []).append(k)
        rest = {f: akte.pop(f) for f in list(akte) if f not in ("mr", "zweige", "zweige_migriert")}
        for branch in set(je_branch) | ({aktuell} if rest else set()):
            dazu(repo, branch, dict(rest if branch == aktuell else {}, kommentare=je_branch.get(branch, [])),
                 [p[:-5]] if branch == aktuell else None)
        ersetzen(p, json.dumps({f: akte[f] for f in ("zweige",) if f in akte}, ensure_ascii=False, indent=1))
    for ordner in glob.glob(os.path.join(DATEN, ZWEIGE, "*")):
        projekt = unquote(os.path.basename(ordner))
        wurzel, repo = repo_von(projekt)
        if not repo or os.path.realpath(zweig_ordner(repo)) == os.path.realpath(ordner):
            continue
        for name in os.listdir(ordner):
            pfad = os.path.join(ordner, name)
            akte = _json_lesen(pfad) if name.endswith(".json") else None
            if akte is not None and "verweis" not in akte:
                akte.pop("mr", None); akte.pop("seiten", None)
                dazu(repo, unquote(name[:-5]), akte)
        import shutil
        if os.path.isdir(os.path.join(ordner, "archiv")):
            os.makedirs(os.path.join(zweig_ordner(repo), "archiv"), exist_ok=True)
            for n in os.listdir(os.path.join(ordner, "archiv")):
                os.replace(os.path.join(ordner, "archiv", n), os.path.join(zweig_ordner(repo), "archiv", n))
        shutil.rmtree(ordner)


def akte_archivieren(waggon, akte, grund):
    """Kopie der Akte nach <ordner>/archiv/<name>-<grund>-<zeit>.json (z. B. die alte MR-Schicht vor einem neuen MR)."""
    ordner = os.path.join(os.path.dirname(akte_datei(waggon)), "archiv")
    name = os.path.basename(akte_datei(waggon))[:-5]
    ersetzen(os.path.join(ordner, f"{name}-{grund}-{datetime.now():%Y%m%d-%H%M%S}.json"),
             json.dumps(akte, ensure_ascii=False, indent=1))


def akte_laden(waggon, kaputte_beiseite=False, pfad=None):
    """Akte laden (fehlende Felder ergänzt). Kaputte Datei: als leere Akte; mit kaputte_beiseite (nur unter der Sperre)
    vorher nach <datei>.kaputt-<zeit> verschieben, damit das nächste Speichern sie nicht überschreibt.
    pfad: diese Datei statt akte_datei(waggon) (die Akte eines anderen Branches)."""
    pfad = pfad or akte_datei(waggon)
    try:
        with open(pfad, encoding="utf-8") as f:
            akte = json.load(f)
    except FileNotFoundError:
        akte = {}
    except ValueError as e:
        if kaputte_beiseite:
            beiseite = f"{pfad}.kaputt-{jetzt().replace(':', '')}"
            os.replace(pfad, beiseite)
            print(f"merge-train: {pfad} ist kaputt ({e}) – verschoben nach {beiseite}", file=sys.stderr)
        akte = {}
    akte.setdefault("mr", waggon.als_dict())
    akte.setdefault("kommentare", []); akte.setdefault("hinweise", {}); akte.setdefault("hinweis_dateien", [])
    return akte


def review_kommentare(akte):
    """Review-Kommentare (ohne Gesprächsfäden)."""
    return [k for k in akte["kommentare"] if k.get("nachrichten") is None]


def akte_speichern(waggon, akte, pfad=None):
    ersetzen(pfad or akte_datei(waggon), json.dumps(akte, ensure_ascii=False, indent=1))


_DATEISPERRE = threading.local()  # Tiefe je Thread: verschachtelte akte_bearbeiten sperren die Datei nur einmal


@contextmanager
def akten_sperre():
    """SPERRE (Threads im Server) und eine Dateisperre (andere Prozesse: „merge-train agent …“, zweiter Server)."""
    with SPERRE:
        tiefe = getattr(_DATEISPERRE, "tiefe", 0)
        if tiefe:
            _DATEISPERRE.tiefe += 1
            try:
                yield
            finally:
                _DATEISPERRE.tiefe -= 1
            return
        os.makedirs(DATEN, exist_ok=True)
        with open(os.path.join(DATEN, ".sperre"), "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            _DATEISPERRE.tiefe = 1
            try:
                yield
            finally:
                _DATEISPERRE.tiefe = 0
                fcntl.flock(f, fcntl.LOCK_UN)


@contextmanager
def akte_bearbeiten(waggon, speichern=True, pfad=None):
    """Akte des Waggons laden, gesperrt halten, am Ende speichern (nur wenn geändert, nicht bei einer Ausnahme) – in
    dieselbe Datei, auch wenn dazwischen der Branch wechselt. pfad: diese Datei (Faden eines anderen Branches)."""
    with akten_sperre():
        pfad = pfad or akte_datei(waggon)
        akte = akte_laden(waggon, kaputte_beiseite=True, pfad=pfad)
        vorher = json.dumps(akte, sort_keys=True)
        yield akte
        if speichern and json.dumps(akte, sort_keys=True) != vorher:
            akte_speichern(waggon, akte, pfad)


class Abgelehnt(Exception):
    """Eine Aktion lehnt ab (Text für den Nutzer). Innerhalb von akte_bearbeiten: nichts wird gespeichert."""


def aktion_ausfuehren(waggon, aktion):
    """aktion(akte) → (ok, text), gesperrt. Gespeichert wird nur bei ok: lehnt eine Aktion nach einer halben Änderung
    ab, bleibt die Datei, wie sie war. Rückgabe (ok, text)."""
    try:
        with akte_bearbeiten(waggon) as akte:
            ok, text = aktion(akte)
            if not ok:
                raise Abgelehnt(text)
    except Abgelehnt as e:
        return False, str(e)
    return True, text


def akte_lesen(waggon, pfad=None):
    """Akte nur lesen (eigene Kopie). Ohne Sperre: ersetzen() schreibt atomar, man sieht immer eine ganze Datei –
    und wartet nicht, während ein anderer gesperrt GitLab fragt. pfad: wie bei akte_laden."""
    return akte_laden(waggon, pfad=pfad)


def kommentar_finden(akte, kid):
    return next((k for k in review_kommentare(akte) if k["id"] == kid), None)


def faden_finden(akte, fid):
    return next((k for k in faeden_von(akte) if k["id"] == fid), None)


def kommentar_anhaengen(akte, k):
    assert k.get("nachrichten") is None
    akte["kommentare"].append(k)


def faden_anhaengen(akte, k):
    assert isinstance(k.get("nachrichten"), list)
    akte["kommentare"].append(k)


def eintrag_entfernen(akte, k):
    """Review-Kommentar oder Faden aus der Datei nehmen."""
    akte["kommentare"].remove(k)


STRUKTUR = {}


def struktur_laden(akte):
    """Struktur der zuletzt gebauten Seite des Waggons (akte.struktur), None ohne. Die Struktur einer bestimmten Seite:
    seiten_struktur (review.py)."""
    return struktur_lesen(akte.get("struktur"))


def struktur_lesen(p):
    """Cache-JSON einer gebauten Seite (seite_bauen), einmal je Prozess gelesen. None: fehlt oder kaputt."""
    if not p:
        return None
    if p not in STRUKTUR:
        try:
            STRUKTUR[p] = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            return None
    return STRUKTUR[p]


def kommentar_status(k):
    """Stufe eines Review-Kommentars (Begriffe siehe AGENTS.md): staged = neu | geaendert | loeschen,
    sent = uebertragen | weg. Ein draft ist ein noch nicht übernommener Agent-Hinweis, kein Kommentar."""
    if k.get("geloescht"): return "loeschen"
    if k.get("gitlab_weg"): return "weg"
    if not k.get("gitlab_id"): return "neu"
    return "uebertragen" if k["text"] == k.get("gitlab_text") else "geaendert"


def ist_staged(k):
    """Wird mit „Review abschließen“ gesendet (neu, geändert oder zu löschen)."""
    return kommentar_status(k) in ("neu", "geaendert", "loeschen")


def ist_sent(k):
    """In GitLab als Draft-Note oder dort veröffentlicht, ohne lokale Änderung."""
    return kommentar_status(k) in ("uebertragen", "weg")


def ausstehend(akte):
    return sum(1 for k in review_kommentare(akte) if ist_staged(k))


def in_gitlab(akte):
    """Kommentare, die als Entwurf (Draft-Note) in GitLab liegen und dort noch abzuschicken sind."""
    return sum(1 for k in review_kommentare(akte) if kommentar_status(k) == "uebertragen")


def datei_index(struktur, pfad):
    if struktur and pfad:
        for i, f in enumerate(struktur["dateien"]):
            if f["neu"] == pfad and f["status"] != "gelöscht":
                return i
        for i, f in enumerate(struktur["dateien"]):
            if f["alt"] == pfad:
                return i
    return None


def faden_damals(k):
    """Ort und Code eines Fadens, wie er angelegt wurde – für „hat sich seitdem geändert“ und „damals“, wenn der Ort im
    Stand der Seite nicht zu finden ist: („Zeilen ab–b“ bzw. „Zeile b“, Text der ersten Zeile oder None)."""
    ab, b = k.get("ab"), k.get("b")
    return (f"Zeilen {ab}–{b}" if ab and b else f"Zeile {b}"), k.get("ab_text") or k.get("zeile_text")


def faden_geaendert(k):
    """„Zeile 86 hat sich seit dem Kommentar geändert“ bzw. „Zeilen 61–86 haben sich …“."""
    return f'{faden_damals(k)[0]} {"haben" if k.get("ab") else "hat"} sich seit dem Kommentar geändert'


def faden_status(k):
    """entwurf (ungesendete eigene Nachricht) | wartet (auf den Agenten) | antwort (Agent hat zuletzt geschrieben) | erledigt"""
    n = k.get("nachrichten") or []
    if any(m["von"] == "ich" and not m.get("gesendet") for m in n):
        return "entwurf"
    if k.get("erledigt"):
        return "erledigt"
    gesendet = [m for m in n if m.get("gesendet")]
    return "antwort" if gesendet and gesendet[-1]["von"] == "claude" else "wartet"


ALLE = object()  # faeden_von: Fäden aller Branches


def faeden_von(akte, branch=ALLE):
    """Fäden (ohne archivierte) – nur die des Branches, wenn einer angegeben ist."""
    return [k for k in akte["kommentare"] if k.get("nachrichten") is not None and not k.get("archiv")
            and (branch is ALLE or k.get("branch") == branch)]


def entwuerfe_senden(akte, branch):
    """Eigene, noch nicht gesendete Nachrichten in den Fäden des Branches als gesendet markieren (senden, Vorschau).
    Rückgabe (Anzahl, Agenten der Fäden in Reihenfolge)."""
    n, namen = 0, []
    for k in faeden_von(akte, branch):
        for m in k["nachrichten"]:
            if m["von"] == "ich" and not m.get("gesendet"):
                m["gesendet"] = jetzt(); n += 1
                if (k.get("an") or "Claude") not in namen:
                    namen.append(k.get("an") or "Claude")
    return n, namen


def faeden_archivieren(waggon, branch):
    """Nach „fertig“: erledigte Fäden des Branches aus der Ansicht nehmen (bleiben in der Datei)."""
    with akte_bearbeiten(waggon) as akte:
        for k in faeden_von(akte, branch):
            if faden_status(k) == "erledigt":
                k["archiv"] = jetzt()


def faeden_zaehlen(waggon, branch):
    """Für den Zug: (offene Fäden, Fäden mit neuer Antwort) des Branches."""
    try:
        akte = akte_lesen(waggon)
    except Exception:
        return 0, 0
    f = faeden_von(akte, branch)
    return sum(1 for k in f if faden_status(k) != "erledigt"), sum(1 for k in f if faden_status(k) == "antwort")


def notizen_von_anderen(akte, ich_id):
    """(id, Diskussion) aller Beiträge anderer in den Diskussionen des MR – für die Meldung „n neue Antwort(en)“ beim Holen."""
    out = []
    for d in akte.get("diskussionen") or []:
        if d.get("wer_id") != ich_id:
            out.append((d.get("note_id") or 0, d))
        out += [(a.get("id") or 0, d) for a in d.get("antworten") or [] if a.get("wer_id") != ich_id]
    return out


def zeitpunkt(iso):
    """ISO-Zeit (GitLab mit Zone/„Z“, lokal ohne) → vergleichbarer Zeitpunkt, None wenn unlesbar."""
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.astimezone()


def diskussion_abgehakt(akte, d):
    """Zeit von „☑ abwarten“ – None, wenn nicht oder wenn ein anderer danach geschrieben hat."""
    z = (akte.get("diskussionen_abgehakt") or {}).get(str(d.get("id")))
    t = zeitpunkt(z) if z else None
    if not t:
        return None
    ich_id = akte.get("ich_id")
    spaeter = [x for x in [d] + (d.get("antworten") or []) if x.get("wer_id") != ich_id and (zeitpunkt(x.get("zeit")) or t) > t]
    return None if spaeter else z


# ---- Stand eines Eintrags der Listen links (Konzept: docs/funktionen.md, „Stände der Listen“). Je Eintrag zwei Achsen:
# stand = wer jetzt dran ist, wer = wer zuletzt gehandelt hat. Neue Listen und Eintragsarten bekommen hier eine Funktion.
STAENDE = ("entwurf",         # von dir, noch nicht gesendet
           "dran",            # du bist dran: dir wurde etwas hingelegt (Antwort, Hinweis, neue Nachricht)
           "gitlab_entwurf",  # liegt als Entwurf in der Quelle (GitLab), dort abschicken
           "wartet",          # die anderen sind dran
           "erledigt")        # abgeschlossen
WER = ("du", "agent", "extern")  # extern = aus der Quelle (GitLab …): wer dort schreibt, weiß man nicht sicher


def faden_stand(k):
    """(stand, wer) eines KI-Threads."""
    st = faden_status(k)
    if st == "erledigt":
        return "erledigt", "agent" if (k.get("erledigt") or {}).get("von") == "claude" else "du"
    return {"entwurf": ("entwurf", "du"), "wartet": ("wartet", "du"), "antwort": ("dran", "agent")}[st]


def kommentar_stand(k):
    """(stand, wer) eines Review-Kommentars: staged = entwurf, Draft-Note in GitLab = gitlab_entwurf, veröffentlicht =
    wartet (bis „MR-Daten“ ihn als Diskussion holt)."""
    st = kommentar_status(k)
    return {"uebertragen": "gitlab_entwurf", "weg": "wartet"}.get(st, "entwurf"), "du"


def hinweis_stand(h):
    """(stand, wer) eines Agent-Hinweises (draft): offen = du bist dran, sonst übernommen bzw. verworfen."""
    return ("dran", "agent") if h.get("status") == "offen" else ("erledigt", "du")


def diskussion_stand(akte, d):
    """(stand, wer) einer GitLab-Diskussion. Vorrang: eigener Entwurf (lokal, dann in GitLab) vor erledigt, vor wartet,
    vor dran. „☑ abwarten“ (diskussion_abgehakt) gibt den Ball ohne Antwort ab; schreibt danach jemand von außen, ist man
    wieder dran."""
    ich_id = akte.get("ich_id")
    antworten = [k for k in review_kommentare(akte) if k.get("antwort_auf") == d.get("id")]
    stufen = {kommentar_status(k) for k in antworten}
    if stufen & {"neu", "geaendert"}:
        return "entwurf", "du"
    if "uebertragen" in stufen:
        return "gitlab_entwurf", "du"
    if d.get("erledigt"):
        return "erledigt", "du" if d["erledigt"].get("wer_id") == ich_id else "extern"
    letzte = ([d] + (d.get("antworten") or []))[-1]
    if letzte.get("wer_id") == ich_id or diskussion_abgehakt(akte, d):
        return "wartet", "du"
    t = zeitpunkt(letzte.get("zeit"))  # eben veröffentlichte Antwort, noch nicht von „MR-Daten“ geholt
    if t and any(kommentar_status(k) == "weg" and (zeitpunkt(k.get("erstellt")) or t) > t for k in antworten):
        return "wartet", "du"
    return "dran", "extern"


def diskussionen_stand(akte):
    """Für Waggon und Seite: Anzahl je Stand (STAENDE) über die Diskussionen."""
    zahl = dict.fromkeys(STAENDE, 0)
    for d in akte.get("diskussionen") or []:
        zahl[diskussion_stand(akte, d)[0]] += 1
    return zahl
