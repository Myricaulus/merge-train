"""Zustand je Waggon: eine JSON-Datei mit Review-Kommentaren und Gesprächsfäden, dazu die Struktur der gebauten Seite."""
import json, os, re
from .einstellungen import DATEN, SPERRE, dateiname, ersetzen, jetzt

def mr_datei(mr):
    return re.sub(r"[^\w.-]", "_", f'{mr["host"] or "gitlab"}_{mr["projekt"]}_{mr["iid"]}')


# Eine Datei je Waggon. „kommentare“ enthält Review-Kommentare (gehen nach GitLab) und Gesprächsfäden (mit
# „nachrichten“, bleiben privat) – review_kommentare() und faeden_von() trennen sie.

def review_datei(mr):
    if mr.get("lokal"):  # lokales Projekt: nur Gespräch
        return os.path.join(DATEN, "lokal", dateiname(mr["lokal"])[:-5] + ".json")
    return os.path.join(DATEN, "reviews", mr_datei(mr) + ".json")


def review_laden(mr):
    try:
        st = json.load(open(review_datei(mr), encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        st = {}
    st.setdefault("mr", {k: v for k, v in mr.items() if k in ("lokal", "host", "projekt", "iid")})
    st.setdefault("kommentare", []); st.setdefault("hinweise", {}); st.setdefault("hinweis_dateien", [])
    return st


def review_kommentare(st):
    """Review-Kommentare (ohne Gesprächsfäden)."""
    return [k for k in st["kommentare"] if k.get("nachrichten") is None]


def review_speichern(mr, st):
    ersetzen(review_datei(mr), json.dumps(st, ensure_ascii=False, indent=1))


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


def ausstehend(st):
    return sum(1 for k in review_kommentare(st) if kommentar_status(k) in ("neu", "geaendert", "loeschen"))


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
    with SPERRE:
        st = review_laden(mr)
        n = 0
        for k in faeden_von(st):
            if faden_status(k) == "erledigt":
                k["archiv"] = jetzt(); n += 1
        if n:
            review_speichern(mr, st)


def faeden_zaehlen(g):
    """Für den Zug: (offene Fäden, Fäden mit neuer Antwort)."""
    try:
        st = review_laden(g)
    except Exception:
        return 0, 0
    f = faeden_von(st)
    return sum(1 for k in f if faden_status(k) != "erledigt"), sum(1 for k in f if faden_status(k) == "antwort")
