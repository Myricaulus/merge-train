"""Akte je Waggon: eine JSON-Datei mit Review-Kommentaren, Gesprächsfäden und Hinweis-Status, dazu die Struktur der
gebauten Seite.

Zugriff nur hierüber: ändern mit `with akte_bearbeiten(waggon) as akte:` (sperrt, lädt, speichert am Ende, wenn sich
etwas geändert hat; bei einer Ausnahme nicht), nur lesen mit `akte_lesen(waggon)`.

Ablage: MR reviews/<name>.json, Myrling myrling/<skript>.json. Lokale Projekte haben eine Akte je Branch
(docs/branch-akte.md): zweige/<projekt>/<branch>.json (beides quote(…, safe="")), welche gilt, sagt der Branch der
Fäden (branch_von). Hat der Branch einen offenen MR, dessen Klon das Projekt ist, ist die Branch-Datei ein Verweis
{"verweis": "reviews/<name>.json"} (relativ zu DATEN, zweig_verknuepfen): lokaler und MR-Waggon teilen dann die Akte
des MR. Die Felder der lokalen Seite (SEITEN_FELDER) liegen dort unter seiten["projekt:<p>"] und werden beim Laden
nach oben getauscht. lokal/<name>.json ist die Projekt-Akte: nur mr, zweige (von/bis auf der Seite gewählt) und
zweige_migriert (Zeit, zu der die alte Akte je Projekt auf die Branch-Akten verteilt wurde, zweige_migrieren).
Fäden gelöschter oder in von gemergter Branches räumt quellen.zweige_aufraeumen nach zweige/<projekt>/archiv/.

Aufbau einer Akte:
  mr               Waggon.als_dict(), bei MRs dazu web_url, titel, source_branch, target_branch
  meta             MR-Daten aus GitLab (META_FELDER in gitlab.py, _zeit = Abruf), nur MRs
  klon             Repo, in dem die Hinweis-Datei liegt (agent zeigen), nur MRs
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
  seiten           {Waggon-Kennung: Seiten-Felder} anderer Waggons, die diese Akte über einen Verweis teilen
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
  branch: zu welchem Branch der Faden gehört (lokal: branch_von, MR: source_branch) – Seite, Zug, „An Agent senden“
  und der Agent sehen nur die Fäden des aktuellen Branches (faeden_von(akte, branch)); fehlt er (alte lokale Akten),
  gehört der Faden zu keinem Branch.
"""
import fcntl, json, os, sys, threading
from datetime import datetime
from urllib.parse import quote, unquote
from .einstellungen import DATEN, SPERRE, ersetzen, jetzt
from contextlib import contextmanager

def akte_datei(waggon, endung=".json"):
    """Ordner je Art des Waggons (Art.ordner in waggon.py); andere endung: Begleitdatei daneben (.horcht, .prompt …).
    Lokales Projekt, .json: die Akte des aktuellen Branches (zweig_akte_pfad)."""
    if waggon.lokal and endung == ".json":
        return zweig_akte_pfad(waggon.lokal)
    return os.path.join(DATEN, waggon.art.ordner, waggon.dateiname + endung)


# ---- Eine Akte je Branch (lokale Projekte, docs/branch-akte.md)

ZWEIGE = "zweige"  # Ordner unter DATEN
SEITEN_FELDER = ("struktur", "abgehakt", "fuellung")  # gehören zur Seite eines Waggons, nicht zum Branch
_WURZEL = {}  # Projekt → Klon, je Prozess (finde_repos ist teuer)


def projekt_akte_datei(projekt):
    """lokal/<name>.json: Projekt-Akte (mr, zweige, zweige_migriert), vor der Migration die alte Akte je Projekt."""
    from .waggon import LOKAL_ART, Waggon
    return os.path.join(DATEN, LOKAL_ART.ordner, Waggon(lokal=projekt).dateiname + ".json")


def projekt_akte_lesen(projekt):
    """Projekt-Akte roh (ohne Auflösen des Branches: von_bis braucht sie dafür selbst)."""
    return _json_lesen(projekt_akte_datei(projekt)) or {}


def zweig_ordner(projekt):
    return os.path.join(DATEN, ZWEIGE, quote(projekt, safe=""))


def zweig_datei(projekt, branch):
    """zweige/<projekt>/<branch>.json – quote(…, safe=""), damit a/b und a_b nicht kollidieren."""
    return os.path.join(zweig_ordner(projekt), quote(branch, safe="") + ".json")


def _json_lesen(pfad):
    """JSON-Datei, None wenn sie fehlt oder kaputt ist."""
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def verweis_ziel(pfad):
    """Ist die Branch-Datei ein Verweis auf eine (vorhandene) MR-Akte: deren Pfad, sonst None. Fehlt das Ziel, gilt die
    Branch-Datei selbst (das nächste Speichern ersetzt den Verweis)."""
    d = _json_lesen(pfad)
    if not isinstance(d, dict) or set(d) != {"verweis"}:
        return None
    ziel = os.path.join(DATEN, d["verweis"])
    return ziel if os.path.exists(ziel) else None


def projekt_klon(projekt):
    """Klon des lokalen Projekts (je Prozess gemerkt), None ohne."""
    from .git import projekt_wurzel
    from .waggon import Fehler
    w = _WURZEL.get(projekt)
    if w and os.path.isdir(w):
        return w
    try:
        _WURZEL[projekt] = w = projekt_wurzel(projekt)
    except Fehler:
        return None
    return w


def zweig_akte_pfad(projekt, branch=None):
    """Akte des Branches (Standard: der aktuelle, branch_von) – ein Verweis zeigt auf die MR-Akte. Gibt es das Projekt
    nicht (mehr), die Projekt-Akte wie vor den Branch-Akten."""
    from .git import branch_von
    wurzel = projekt_klon(projekt)
    if not wurzel:
        return projekt_akte_datei(projekt)
    zweige_migrieren(projekt, wurzel)
    pfad = zweig_datei(projekt, branch or branch_von(wurzel))
    return verweis_ziel(pfad) or pfad


def zweige_migrieren(projekt, wurzel):
    """Einmal je Projekt („Hausaufgaben“): die alte Akte je Projekt auf die Branch-Akten verteilen – Fäden nach branch
    (vorhandene nach id vereinigt), Fäden ohne Branch und die übrigen Felder in die Akte des aktuellen Branches. Danach
    ist lokal/<name>.json die Projekt-Akte (mr, zweige, zweige_migriert)."""
    if "zweige_migriert" in projekt_akte_lesen(projekt):
        return
    from .git import branch_von
    from .waggon import Waggon
    with akten_sperre():
        alt = projekt_akte_lesen(projekt)
        if "zweige_migriert" in alt:
            return
        aktuell = branch_von(wurzel)
        je_branch = {}
        for k in alt.pop("kommentare", None) or []:
            je_branch.setdefault(k.get("branch") or aktuell, []).append(k)
        rest = {f: alt.pop(f) for f in list(alt) if f not in ("mr", "zweige")}
        for branch in set(je_branch) | ({aktuell} if rest else set()):
            pfad = zweig_datei(projekt, branch)
            ziel = verweis_ziel(pfad) or pfad
            akte = _json_lesen(ziel) or {"mr": Waggon(lokal=projekt).als_dict()}
            da = {k.get("id") for k in akte.setdefault("kommentare", [])}
            akte["kommentare"] += [k for k in je_branch.get(branch, []) if k.get("id") not in da]
            if branch == aktuell and ziel == pfad:
                for f, v in rest.items():
                    akte.setdefault(f, v)
            ersetzen(ziel, json.dumps(akte, ensure_ascii=False, indent=1))
        alt.setdefault("mr", Waggon(lokal=projekt).als_dict())
        alt["zweige_migriert"] = jetzt()
        ersetzen(projekt_akte_datei(projekt), json.dumps(alt, ensure_ascii=False, indent=1))


@contextmanager
def projekt_akte_bearbeiten(projekt):
    """Projekt-Akte gesperrt ändern (von/bis der Seite, projekt_einstellen)."""
    from .waggon import Waggon
    with akten_sperre():
        akte = projekt_akte_lesen(projekt)
        vorher = json.dumps(akte, sort_keys=True)
        yield akte
        if json.dumps(akte, sort_keys=True) != vorher:
            akte.setdefault("mr", Waggon(lokal=projekt).als_dict())
            ersetzen(projekt_akte_datei(projekt), json.dumps(akte, ensure_ascii=False, indent=1))


def zweig_akten(projekt):
    """Akten aller Branches des Projekts: [(branch, pfad)], Verweise aufgelöst (ohne archiv/)."""
    ordner = zweig_ordner(projekt)
    out = []
    for name in sorted(os.listdir(ordner)) if os.path.isdir(ordner) else []:
        if name.endswith(".json") and not name.startswith("."):
            pfad = os.path.join(ordner, name)
            out.append((unquote(name[:-5]), verweis_ziel(pfad) or pfad))
    return out


def andere_zweig_akten(waggon):
    """Lokales Projekt: Pfade der Akten seiner anderen Branches (zweig_akten ohne die aktuelle), sonst []."""
    if not waggon.lokal:
        return []
    eigen = os.path.realpath(akte_datei(waggon))
    out = []
    for _, p in zweig_akten(waggon.lokal):
        if os.path.realpath(p) != eigen and p not in out:
            out.append(p)
    return out


def zweig_verknuepfen(mr, projekt, branch):
    """Branch mit offenem MR, dessen Klon das Projekt ist: die Branch-Datei wird ein Verweis auf die MR-Akte. Eine echte
    Branch-Akte gibt vorher ihre Fäden (und todo_id) an die MR-Akte ab, ihre Seiten-Felder nach seiten["projekt:<p>"];
    ein Verweis auf eine andere (alte) MR-Akte zieht die Fäden dieses Branches von dort um. Rückgabe: umgezogene Fäden."""
    pfad = zweig_datei(projekt, branch)
    ziel = os.path.relpath(akte_datei(mr), DATEN)
    if (_json_lesen(pfad) or {}).get("verweis") == ziel:
        return 0
    wurzel = projekt_klon(projekt)
    if wurzel:
        zweige_migrieren(projekt, wurzel)  # erst verteilen: die Migration schreibt nie über einen Verweis
    from .waggon import Waggon
    with akten_sperre():
        alt = _json_lesen(pfad) or {}
        if alt.get("verweis") == ziel:
            return 0
        n = 0
        if alt.get("verweis"):  # alte MR-Akte: die Fäden dieses Branches ziehen um
            alt_pfad = os.path.join(DATEN, alt["verweis"])
            alt_akte = _json_lesen(alt_pfad)
            if alt_akte:
                weg = [k for k in alt_akte.get("kommentare") or [] if k.get("nachrichten") is not None
                       and k.get("branch", (alt_akte.get("mr") or {}).get("source_branch")) == branch]
                n = _faeden_dazu(mr, weg)
                ids = {k.get("id") for k in weg}
                alt_akte["kommentare"] = [k for k in alt_akte["kommentare"] if k.get("id") not in ids or k.get("nachrichten") is None]
                ersetzen(alt_pfad, json.dumps(alt_akte, ensure_ascii=False, indent=1))
        elif alt:  # echte Branch-Akte
            weg = [k for k in alt.get("kommentare") or [] if k.get("nachrichten") is not None]
            with akte_bearbeiten(mr) as akte:
                n = _faeden_dazu(mr, weg, akte)
                if alt.get("todo_id") and not akte.get("todo_id"):
                    akte["todo_id"] = alt["todo_id"]
                seite = {f: alt[f] for f in SEITEN_FELDER if f in alt}
                if seite:
                    akte.setdefault("seiten", {})[Waggon(lokal=projekt).id] = seite
        ersetzen(pfad, json.dumps({"verweis": ziel}, ensure_ascii=False))
    if n:
        from .einstellungen import melden
        melden(f"{mr.name}: {n} Faden/Fäden aus dem lokalen Waggon übernommen (eine Akte je Branch)")
    return n


def _faeden_dazu(mr, faeden, akte=None):
    """Fäden in die MR-Akte (ids bleiben, schon vorhandene nicht doppelt). Rückgabe: Anzahl neu."""
    if akte is None:
        with akte_bearbeiten(mr) as a:
            return _faeden_dazu(mr, faeden, a)
    da = {k.get("id") for k in akte["kommentare"]}
    neu = [k for k in faeden if k.get("id") not in da]
    akte["kommentare"] += neu
    return len(neu)


def _seite_tauschen(waggon, akte, nach_oben):
    """Akte eines anderen Waggons (über einen Verweis geteilt): die Seiten-Felder des Ladenden liegen unter
    seiten[<waggon.id>]. nach_oben (laden): seine nach oben, die des Besitzers nach seiten[<besitzer>]; sonst zurück.
    Rückgabe: die getauschte Akte (eine Kopie) bzw. die Akte selbst, wenn sie dem Waggon gehört."""
    from .waggon import Waggon
    m = akte.get("mr") or {}
    if not m or m == waggon.als_dict():
        return akte
    besitzer, ich = Waggon.aus_dict(m).id, waggon.id
    akte = dict(akte)
    seiten = dict(akte.get("seiten") or {})
    weg, her = (besitzer, ich) if nach_oben else (ich, besitzer)
    seiten[weg] = {f: akte.pop(f) for f in SEITEN_FELDER if f in akte}
    akte.update(seiten.pop(her, None) or {})
    akte["seiten"] = {k: v for k, v in seiten.items() if v}
    if not akte["seiten"]:
        akte.pop("seiten")
    return akte


def akte_laden(waggon, kaputte_beiseite=False, pfad=None):
    """Akte laden (fehlende Felder ergänzt). Kaputte Datei: als leere Akte; mit kaputte_beiseite (nur unter der Sperre)
    vorher nach <datei>.kaputt-<zeit> verschieben, damit das nächste Speichern sie nicht überschreibt.
    pfad: diese Datei statt akte_datei(waggon) (eine Branch-Akte eines anderen Branches)."""
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
    akte = _seite_tauschen(waggon, akte, nach_oben=True)
    akte.setdefault("mr", waggon.als_dict())
    akte.setdefault("kommentare", []); akte.setdefault("hinweise", {}); akte.setdefault("hinweis_dateien", [])
    quell_branch = akte["mr"].get("source_branch")  # MR: alte Fäden gehören zum Quell-Branch des MR
    if quell_branch:
        for k in akte["kommentare"]:
            if k.get("nachrichten") is not None and "branch" not in k:
                k["branch"] = quell_branch
    return akte


def review_kommentare(akte):
    """Review-Kommentare (ohne Gesprächsfäden)."""
    return [k for k in akte["kommentare"] if k.get("nachrichten") is None]


def akte_speichern(waggon, akte, pfad=None):
    ersetzen(pfad or akte_datei(waggon), json.dumps(_seite_tauschen(waggon, akte, nach_oben=False), ensure_ascii=False, indent=1))


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
