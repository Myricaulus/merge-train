"""Zustand je Waggon: eine JSON-Datei mit Review-Kommentaren und Gesprächsfäden, dazu die Struktur der gebauten Seite.

Zugriff nur hierüber: ändern mit `with zustand(waggon) as st:` (lädt unter SPERRE, speichert am Ende, wenn sich etwas
geändert hat; bei einer Ausnahme nicht), nur lesen mit `zustand_lesen(waggon)`.

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
  (position | allgemein | mr), gitlab_weg (veröffentlicht), geloescht (beim Abschließen löschen).
  Stufe: kommentar_status, ist_staged, ist_sent (Begriffe in AGENTS.md).
Gesprächsfaden: id, refs, erstellt, path, old_path, a, b, zeile_text, an (Agent, sonst Claude), vom_agenten, see_also,
  nachrichten [{id, von: ich | claude, wer, text, zeit, gesendet, abgeholt}], erledigt {von, zeit, wer} oder None,
  archiv (nach „fertig“ aus der Ansicht genommen). Stufe: faden_status.
"""
import json, os
from .einstellungen import DATEN, SPERRE, ersetzen, jetzt
from contextlib import contextmanager

def review_datei(waggon):
    return os.path.join(DATEN, "lokal" if waggon.lokal else "reviews", waggon.dateiname + ".json")


def review_laden(mr):
    try:
        st = json.load(open(review_datei(mr), encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        st = {}
    st.setdefault("mr", mr.als_dict())
    st.setdefault("kommentare", []); st.setdefault("hinweise", {}); st.setdefault("hinweis_dateien", [])
    return st


def review_kommentare(st):
    """Review-Kommentare (ohne Gesprächsfäden)."""
    return [k for k in st["kommentare"] if k.get("nachrichten") is None]


def review_speichern(mr, st):
    ersetzen(review_datei(mr), json.dumps(st, ensure_ascii=False, indent=1))


@contextmanager
def zustand(waggon, speichern=True):
    """Zustand des Waggons laden, unter der Sperre halten, am Ende speichern (nur wenn geändert)."""
    with SPERRE:
        st = review_laden(waggon)
        vorher = json.dumps(st, sort_keys=True)
        yield st
        if speichern and json.dumps(st, sort_keys=True) != vorher:
            review_speichern(waggon, st)


def zustand_lesen(waggon):
    """Zustand nur lesen (eigene Kopie). Ohne Sperre: ersetzen() schreibt atomar, man sieht immer eine ganze Datei –
    und wartet nicht, während ein anderer unter der Sperre GitLab fragt."""
    return review_laden(waggon)


def kommentar_finden(st, kid):
    return next((k for k in review_kommentare(st) if k["id"] == kid), None)


def faden_finden(st, fid):
    return next((k for k in faeden_von(st) if k["id"] == fid), None)


def kommentar_anhaengen(st, k):
    assert k.get("nachrichten") is None
    st["kommentare"].append(k)


def faden_anhaengen(st, k):
    assert isinstance(k.get("nachrichten"), list)
    st["kommentare"].append(k)


def eintrag_entfernen(st, k):
    """Review-Kommentar oder Faden aus der Datei nehmen."""
    st["kommentare"].remove(k)


STRUKTUR = {}


def struktur_laden(st):
    p = st.get("struktur")
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


def ausstehend(st):
    return sum(1 for k in review_kommentare(st) if ist_staged(k))


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


def faeden_von(st):
    return [k for k in st["kommentare"] if k.get("nachrichten") is not None and not k.get("archiv")]


def faeden_archivieren(mr):
    """Nach „fertig“: erledigte Fäden aus der Ansicht nehmen (bleiben in der Datei)."""
    with zustand(mr) as st:
        for k in faeden_von(st):
            if faden_status(k) == "erledigt":
                k["archiv"] = jetzt()


def faeden_zaehlen(waggon):
    """Für den Zug: (offene Fäden, Fäden mit neuer Antwort)."""
    try:
        st = zustand_lesen(waggon)
    except Exception:
        return 0, 0
    f = faeden_von(st)
    return sum(1 for k in f if faden_status(k) != "erledigt"), sum(1 for k in f if faden_status(k) == "antwort")
