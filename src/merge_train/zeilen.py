"""Zeilen-Arithmetik: welche Zeile der alten Seite gehört zu welcher der neuen – im Diff, vorwärts und zurück."""
from .git import git, zerlegen

def paare_und_hunks(d):
    """Je Diffzeile [alt, neu] (None = gibt es auf der Seite nicht) und Hunk-Grenzen [a, b, alen, blen]."""
    paare, hunks = [], []
    for h in d["hunks"]:
        a, b = h["a"], h["b"]
        al = sum(1 for t, _ in h["z"] if t != "+"); bl = sum(1 for t, _ in h["z"] if t != "-")
        hunks.append([h["a"], h["b"], al, bl])
        for t, _ in h["z"]:
            if t == " ": paare.append([a, b]); a += 1; b += 1
            elif t == "-": paare.append([a, None]); a += 1
            else: paare.append([None, b]); b += 1
    return paare, hunks


def alt_zeile(f, n):
    """Zeile n (neu) → Zeile im alten Stand; None bei hinzugefügter Zeile."""
    for a, b in f["paare"]:
        if b == n:
            return a
    delta = 0
    for a0, b0, al, bl in f["hunks"]:
        if b0 + bl <= n:
            delta += bl - al
    return n - delta


def im_diff(f, a, b):
    if b is not None:
        return any(p[1] == b and (a is None or p[0] == a) for p in f["paare"])
    return any(p[0] == a and p[1] is None for p in f["paare"])


def kontext_zeile(f, a, b):
    """Unveränderte Zeile außerhalb der Hunks (nachgeladener Kontext)?"""
    return (a is not None and b is not None and 0 < b <= (f.get("bn") or 0)
            and not any(p[1] == b for p in f["paare"]) and alt_zeile(f, b) == a)


def diff_enden(struktur):
    """(von, bis) des Diffs einer Seite: Ansicht oder ganzer MR."""
    a = struktur.get("ansicht")
    return (a["von"], a["bis"]) if a else (struktur["refs"]["base_sha"], struktur["refs"]["head_sha"])


_ZURUECK = {}


def zurueck_diffs(ordner, bis, head, pfade):
    """Diff bis → head für die Pfade: {pfad im MR-Stand: datei (paare/hunks/alt)}; fehlt = seitdem unverändert."""
    k = (ordner, bis, head, tuple(sorted(pfade)))
    if k not in _ZURUECK:
        out = git(ordner, "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "-M", "-U3",
                  bis, head, "--", *sorted(pfade), check=False) if pfade else ""
        r = {}
        for d in zerlegen(out or ""):
            paare, hunks = paare_und_hunks(d)
            r[d["neu"]] = {"alt": d["alt"], "status": d["status"], "paare": paare, "hunks": hunks}
        if len(_ZURUECK) > 50:
            _ZURUECK.clear()
        _ZURUECK[k] = r
    return _ZURUECK[k]


_VORWAERTS = {}


def bereich_anfang_vorwaerts(ordner, von, bis, pfad, ab, b_neu):
    """Erste Zeile ab eines Bereichs ab–b (Stand von) → Stand bis, passend zur schon umgerechneten letzten Zeile b_neu.
    None = kein Bereich mehr (Anfang geändert oder nicht mehr vor dem Ende): der Faden hängt dann nur an b_neu."""
    if not ab or not b_neu:
        return None
    neu = zeile_vorwaerts(ordner, von, bis, pfad, ab)
    return neu if neu and neu < b_neu else None


def zeile_vorwaerts(ordner, von, bis, pfad, b):
    """Zeile b (Stand von) → Zeile im Stand bis. None = Zeile seitdem geändert oder Datei weg."""
    if von == bis or not b:
        return b
    k = (ordner, von, bis, pfad)
    if k not in _VORWAERTS:
        if len(_VORWAERTS) > 500:
            _VORWAERTS.clear()
        out = git(ordner, "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "-U3", von, bis,
                  "--", pfad, check=False)
        d = zerlegen(out or "")
        _VORWAERTS[k] = (d[0]["status"], *paare_und_hunks(d[0])) if d else None
    f = _VORWAERTS[k]
    if f is None:
        return b  # unverändert
    status, paare, hunks = f
    if status == "gelöscht":
        return None
    for a, n in paare:
        if a == b:
            return n
    delta = 0
    for a0, b0, al, bl in hunks:
        if a0 + al <= b:
            delta += bl - al
    return b + delta
