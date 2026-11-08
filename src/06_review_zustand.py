# ---------------------------------------------------------------- Review-Zustand

def review_datei(mr):
    return os.path.join(DATEN, "reviews", mr_datei(mr) + ".json")

def review_laden(mr):
    try:
        st = json.load(open(review_datei(mr), encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        st = {}
    st.setdefault("mr", dict(mr))
    st.setdefault("kommentare", []); st.setdefault("hinweise", {}); st.setdefault("hinweis_dateien", [])
    return st

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
    return sum(1 for k in st["kommentare"] if k_status(k) in ("neu", "geaendert", "loeschen"))

def datei_index(struktur, pfad):
    if struktur and pfad:
        for i, f in enumerate(struktur["dateien"]):
            if f["neu"] == pfad and f["status"] != "gelöscht":
                return i
        for i, f in enumerate(struktur["dateien"]):
            if f["alt"] == pfad:
                return i
    return None

