"""Agent-Hinweise (drafts) aus den review-markers.json lesen und auf Zeilen der Seite auflösen."""
import glob, hashlib, json, os, re
from .einstellungen import KONF
from .waggon import Fehler
from .git import inhalt
from .zeilen import alt_zeile, im_diff
from .diff_html import zeilenzahl
from .akte import datei_index
from .gitlab import mr_ref

HINWEIS_FELDER = {"finding", "title", "path", "needle", "text", "rationale", "resolved_when", "line", "see_also"}


def pfad_norm(p):
    p = str(p or "").strip().replace("\\", "/")
    return p[2:] if p.startswith("./") else p


def see_also_aufloesen(ordner, head, eintraege, tag, eigene=None):
    """see_also: Liste aus "pfad", "pfad:zeile", "pfad:von-bis" oder {"path", "line"|"needle", "end", "label", "diff"}
    → Zeilen im MR-Stand. Nur für merge-train (Links/Popup), nie Teil des GitLab-Kommentars.
    "diff": true vergleicht die eigene Datei des Hinweises mit dieser (Popup nebeneinander), "diff": "pfad" eine andere."""
    if isinstance(eintraege, (str, dict)):
        eintraege = [eintraege]
    out = []
    for e in eintraege if isinstance(eintraege, list) else []:
        if isinstance(e, str):
            m = re.fullmatch(r"(.+?)(?::(\d+)(?:-(\d+))?)?", e.strip())
            e = {"path": m.group(1), "line": int(m.group(2)) if m.group(2) else None,
                 "end": int(m.group(3)) if m.group(3) else None} if m else {}
        if not isinstance(e, dict):
            continue
        path, zeile, problem = pfad_norm(e.get("path")), None, None
        if isinstance(e.get("line"), int) and e["line"] > 0:
            zeile = e["line"]
        if not path:
            problem = "kein Pfad"
        elif head:
            t = inhalt(ordner, head, path)
            if t is None:
                problem = "Datei nicht im MR-Stand"
            elif zeile and zeile > zeilenzahl(t):
                problem = f"Zeile {zeile} gibt es nicht ({zeilenzahl(t)} Zeilen)"
            elif not zeile and e.get("needle"):
                z = needle_zeilen(t, str(e["needle"]), tag)
                zeile = z[0] if z else None
                problem = None if z else "needle nicht gefunden"
        bis = e.get("end") if isinstance(e.get("end"), int) and zeile and e["end"] > zeile else None
        gegen = None
        if e.get("diff"):
            gegen = pfad_norm(e["diff"]) if isinstance(e["diff"], str) else eigene
            if not gegen:
                problem = problem or "diff: Hinweis hat keine eigene Datei – Pfad angeben"
            elif head and not problem and inhalt(ordner, head, gegen) is None:
                problem = f"diff: {gegen} nicht im MR-Stand"
        out.append({"path": path, "zeile": zeile, "bis": bis, "label": e.get("label"), "problem": problem, "vergleich": gegen})
    return out


_HW_CACHE = {}


def hinweise_lesen(pfad):
    """Hinweis-Datei lesen und vereinheitlichen (auch Altformat: nur das markers-Array)."""
    info = os.stat(pfad)
    k = (pfad, info.st_mtime_ns, info.st_size)
    if k in _HW_CACHE:
        return _HW_CACHE[k]
    daten = json.load(open(pfad, encoding="utf-8-sig"))
    if isinstance(daten, list):
        daten = {"markers": daten}
    if not isinstance(daten, dict) or not isinstance(daten.get("markers", []), list):
        raise ValueError("erwartet ein Objekt mit „markers“-Liste (oder nur die Liste)")
    for i, m in enumerate(daten.get("markers") or []):
        if not isinstance(m, dict):
            raise ValueError(f"markers[{i}] ist kein Objekt")
        if not str(m.get("text") or "").strip():
            raise ValueError(f"markers[{i}]: „text“ fehlt")
    daten.setdefault("markers", [])
    _HW_CACHE[k] = daten
    return daten


def hinweis_passt(pfad, info):
    try:
        h = hinweise_lesen(pfad)
    except (OSError, ValueError):
        return False
    if h.get("mr"):
        try:
            ref = mr_ref(h["mr"], os.path.dirname(pfad))
        except Fehler:
            return False
        return ref.iid == info.get("iid") and (ref.projekt or "").lower() == (info.get("projekt") or "").lower()
    return bool(h.get("branch")) and h["branch"] == info.get("source_branch")


def hinweis_dateien(mr, akte):
    dateien = [p for p in akte["hinweis_dateien"] if os.path.exists(p)]
    for muster in KONF["hinweise"]:
        for p in sorted(glob.glob(os.path.expanduser(muster))):
            p = os.path.abspath(p)
            if p not in dateien and hinweis_passt(p, akte["mr"]):
                dateien.append(p)
    return dateien


def needle_zeilen(text, needle, tag):
    rx = re.compile(r"\s*(//|<!--) " + re.escape(tag) + r"(?![0-9A-Za-z]).*$") if tag else None
    out = []
    for nr, z in enumerate(text.split("\n"), 1):
        if rx:
            z = rx.sub("", z)
        if (z.strip() == needle[1:].strip()) if needle.startswith("=") else (needle in z):
            out.append(nr)
    return out


def hinweise_aufloesen(mr, akte, struktur, nur=None):
    """Hinweise aller Dateien auf Zeilen des MR-Stands abbilden. Rückgabe (hinweise, quellen)."""
    hinweise, quellen = [], []
    head = (struktur or {}).get("refs", {}).get("head_sha")
    ordner = (struktur or {}).get("ordner")
    for pfad in (nur if nur is not None else hinweis_dateien(mr, akte)):
        try:
            h = hinweise_lesen(pfad)
        except (OSError, ValueError) as e:
            quellen.append({"datei": pfad, "fehler": f"nicht lesbar: {e}", "anzahl": 0}); continue
        tag = str(h.get("tag") or "")
        name = h.get("key") or os.path.basename(pfad)
        quellen.append({"datei": pfad, "key": h.get("key"), "notes": h.get("notes"), "anzahl": len(h["markers"]),
                        "reviewed_commit": h.get("reviewed_commit"), "reviewed_at": h.get("reviewed_at"),
                        "failing_tests": h.get("failing_tests"),
                        "alt": bool(head and h.get("reviewed_commit") and not head.startswith(str(h["reviewed_commit"])))})
        for nr, m in enumerate(h["markers"]):
            text = str(m.get("text") or "").strip()
            fid = str(m.get("finding") or (re.match(r"(#\d+|K\d+)\b", text) or [""])[0])  # ID nur noch lokal, nicht mehr im Text nötig
            path = pfad_norm(m.get("path"))
            needle = str(m.get("needle") or "")
            basis = {"finding": fid, "text": text, "rationale": m.get("rationale"), "resolved_when": m.get("resolved_when"),
                     "extra": {k: v for k, v in m.items() if k not in HINWEIS_FELDER}, "path": path, "quelle": name,
                     "json": pfad, "nr": nr,  # Herkunft: für „merge-train agent kommentar h:<key>“
                     "see_also": see_also_aufloesen(ordner, head, m.get("see_also"), tag, path),
                     "title": str(m.get("title") or "").strip() or None}
            zeilen, problem = [], None
            if not path:
                pass  # allgemeiner Hinweis zum MR
            elif isinstance(m.get("line"), int) and m["line"] > 0:
                zeilen = [m["line"]]
            elif not head:
                problem = "MR-Stand unbekannt"
            else:
                t = inhalt(ordner, head, path)
                if t is None:
                    problem = "Datei nicht im MR-Stand"
                elif not needle:
                    problem = "kein needle"
                else:
                    zeilen = needle_zeilen(t, needle, tag)
                    if not zeilen:
                        problem = "needle nicht gefunden"
            i = datei_index(struktur, path)
            f = struktur["dateien"][i] if i is not None else None
            for j, z in enumerate(zeilen or [None]):
                key = hashlib.sha1(f"{name}|{fid}|{path}|{needle}|{text}|{j}".encode()).hexdigest()[:12]
                a = alt_zeile(f, z) if f and z else None
                imd = bool(f and z and im_diff(f, a, z))
                pr = problem or (None if imd else ("Zeile außerhalb des Diffs" if f else "Datei nicht im Diff") if z else None)
                hinweise.append(dict(basis, key=key, zeile=z, datei=i, a=a, b=z, im_diff=imd, problem=pr,
                                     mehrfach=len(zeilen) if len(zeilen) > 1 else None,
                                     status=akte["hinweise"].get(key, "offen")))
    return hinweise, quellen
