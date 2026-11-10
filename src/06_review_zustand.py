# ---------------------------------------------------------------- Review-Zustand

# Eine Datei je Waggon. „kommentare“ enthält Review-Kommentare (gehen nach GitLab) und Gesprächsfäden (mit
# „nachrichten“, bleiben privat) – rk() und g_faeden() trennen sie.

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
    if not mr.get("lokal"):
        alt_gespraech_uebernehmen(mr, st)
    return st

def alt_gespraech_uebernehmen(mr, st):
    """Übergang: Fäden aus der früheren getrennten Ablage (gespraech/<mr>.json) in die Review-Datei holen."""
    alt = os.path.join(DATEN, "gespraech", mr_datei(mr) + ".json")
    if not os.path.exists(alt):
        return
    with SPERRE:
        try:
            g = json.load(open(alt, encoding="utf-8"))
        except (OSError, ValueError):
            return
        ids = {k["id"] for k in st["kommentare"]}
        st["kommentare"] += [k for k in g.get("kommentare") or [] if k.get("nachrichten") is not None and k["id"] not in ids]
        if g.get("todo_id") and not st.get("todo_id"):
            st["todo_id"] = g["todo_id"]
        review_speichern(mr, st)
        os.replace(alt, alt + ".uebernommen")

def rk(st):
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

def k_status(k):
    if k.get("geloescht"): return "loeschen"
    if k.get("gitlab_weg"): return "weg"
    if not k.get("gitlab_id"): return "neu"
    return "uebertragen" if k["text"] == k.get("gitlab_text") else "geaendert"

def ausstehend(st):
    return sum(1 for k in rk(st) if k_status(k) in ("neu", "geaendert", "loeschen"))

def datei_index(struktur, pfad):
    if struktur and pfad:
        for i, f in enumerate(struktur["dateien"]):
            if f["neu"] == pfad and f["status"] != "gelöscht":
                return i
        for i, f in enumerate(struktur["dateien"]):
            if f["alt"] == pfad:
                return i
    return None

