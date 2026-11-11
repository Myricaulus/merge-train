"""Akte je Waggon: eine JSON-Datei mit Review-Kommentaren, Gesprächsfäden und Hinweis-Status, dazu die Struktur der
gebauten Seite.

Zugriff nur hierüber: ändern mit `with akte_bearbeiten(waggon) as akte:` (sperrt, lädt, speichert am Ende, wenn sich
etwas geändert hat; bei einer Ausnahme nicht), nur lesen mit `akte_lesen(waggon)`.

Aufbau der Datei (lokal/<name>.json bzw. reviews/<name>.json):
  mr               Waggon.als_dict(), bei MRs dazu web_url, titel, source_branch, target_branch
  meta             MR-Daten aus GitLab (META_FELDER in gitlab.py, _zeit = Abruf), nur MRs
  klon             Repo, in dem die Hinweis-Datei liegt (agent zeigen), nur MRs
  kommentare       Review-Kommentare und Gesprächsfäden gemischt; Fäden haben „nachrichten“.
                   Zugriff über review_kommentare / faeden_von / kommentar_finden / faden_finden.
  reihenfolge      ids/keys der Box „GitLab-Kommentare“, wie vom Nutzer sortiert
  hinweise         {key: uebernommen | verworfen} für Agent-Hinweise (drafts); fehlt der key, ist er offen
  hinweis_dateien  angemeldete Review-JSONs (agent zeigen)
  struktur         Pfad der Cache-JSON der zuletzt gebauten Seite (struktur_laden)
  todo_id          todo-Eintrag aus „Feedback senden“, wenn niemand zuhörte
  abgeschlossen    Zeit des letzten vollständigen „Review abschließen“

Review-Kommentar: id, refs {head_sha, base_sha, start_sha} beim Schreiben, erstellt, path, old_path, a (alte Zeile),
  b (neue Zeile), text, finding/hinweis (aus einem übernommenen draft), gitlab_id, gitlab_text, gitlab_art
  (position | allgemein | mr), gitlab_weg (veröffentlicht), geloescht (beim Abschließen löschen),
  gitlab_diskussion (veröffentlicht, von „MR-Daten“: id, note_id, erledigt {wer, zeit} oder None,
  antworten [{id, wer, wer_id, text, zeit}]).
  diskussionen     alle Diskussionen des MR aus GitLab („MR-Daten“, „MRs“): id, note_id, wer, wer_id, text, zeit, path,
                   old_path, a, b, head_sha (Stand des Kommentars), loesbar, erledigt, antworten – nur MRs
  ich_id           meine GitLab-Benutzer-id (für „neu“: Beiträge anderer)
  diskussionen_gesehen  höchste note-id anderer beim letzten Öffnen der Seite; was danach kam, ist im Zug „neu“
  Stufe: kommentar_status, ist_staged, ist_sent (Begriffe in AGENTS.md).
Gesprächsfaden: id, branch, refs, erstellt, path, old_path, a, b, zeile_text, an (Agent, sonst Claude), vom_agenten, see_also,
  nachrichten [{id, von: ich | claude, wer, text, zeit, gesendet, abgeholt}], erledigt {von, zeit, wer} oder None,
  archiv (nach „fertig“ aus der Ansicht genommen). Stufe: faden_status.
  branch: zu welchem Branch der Faden gehört (lokal: branch_von, MR: source_branch) – Seite, Zug, „Feedback senden“
  und der Agent sehen nur die Fäden des aktuellen Branches (faeden_von(akte, branch)); fehlt er (alte lokale Akten),
  gehört der Faden zu keinem Branch.
"""
import fcntl, json, os, sys, threading
from .einstellungen import DATEN, SPERRE, ersetzen, jetzt
from contextlib import contextmanager

def akte_datei(waggon):
    return os.path.join(DATEN, "lokal" if waggon.lokal else "reviews", waggon.dateiname + ".json")


def akte_laden(waggon, kaputte_beiseite=False):
    """Akte laden (fehlende Felder ergänzt). Kaputte Datei: als leere Akte; mit kaputte_beiseite (nur unter der Sperre)
    vorher nach <datei>.kaputt-<zeit> verschieben, damit das nächste Speichern sie nicht überschreibt."""
    pfad = akte_datei(waggon)
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
    quell_branch = akte["mr"].get("source_branch")  # MR: alte Fäden gehören zum Quell-Branch des MR
    if quell_branch:
        for k in akte["kommentare"]:
            if k.get("nachrichten") is not None and "branch" not in k:
                k["branch"] = quell_branch
    return akte


def review_kommentare(akte):
    """Review-Kommentare (ohne Gesprächsfäden)."""
    return [k for k in akte["kommentare"] if k.get("nachrichten") is None]


def akte_speichern(waggon, akte):
    ersetzen(akte_datei(waggon), json.dumps(akte, ensure_ascii=False, indent=1))


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
def akte_bearbeiten(waggon, speichern=True):
    """Akte des Waggons laden, gesperrt halten, am Ende speichern (nur wenn geändert, nicht bei einer Ausnahme)."""
    with akten_sperre():
        akte = akte_laden(waggon, kaputte_beiseite=True)
        vorher = json.dumps(akte, sort_keys=True)
        yield akte
        if speichern and json.dumps(akte, sort_keys=True) != vorher:
            akte_speichern(waggon, akte)


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


def akte_lesen(waggon):
    """Akte nur lesen (eigene Kopie). Ohne Sperre: ersetzen() schreibt atomar, man sieht immer eine ganze Datei –
    und wartet nicht, während ein anderer gesperrt GitLab fragt."""
    return akte_laden(waggon)


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
    p = akte.get("struktur")
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


def datei_index(struktur, pfad):
    if struktur and pfad:
        for i, f in enumerate(struktur["dateien"]):
            if f["neu"] == pfad and f["status"] != "gelöscht":
                return i
        for i, f in enumerate(struktur["dateien"]):
            if f["alt"] == pfad:
                return i
    return None


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
    """(id, Diskussion) aller Beiträge anderer in den Diskussionen des MR – für „neu“ im Zug."""
    out = []
    for d in akte.get("diskussionen") or []:
        if d.get("wer_id") != ich_id:
            out.append((d.get("note_id") or 0, d))
        out += [(a.get("id") or 0, d) for a in d.get("antworten") or [] if a.get("wer_id") != ich_id]
    return out


def diskussionen_stand(akte):
    """Für Waggon und Seite: offen (lösbar, nicht erledigt), erledigt, neu (Beiträge anderer seit dem letzten Öffnen)."""
    ds = akte.get("diskussionen") or []
    gesehen = akte.get("diskussionen_gesehen") or 0
    return {"offen": sum(1 for d in ds if d.get("loesbar") and not d.get("erledigt")),
            "erledigt": sum(1 for d in ds if d.get("erledigt")),
            "neu": sum(1 for i, _ in notizen_von_anderen(akte, akte.get("ich_id")) if i > gesehen)}
