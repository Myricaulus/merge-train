"""Gespräch mit dem Agenten: Fäden an Zeilen, Nachrichten, Daten für die Seite."""
import glob, hashlib, json, os, re
from .einstellungen import DATEN, KONF, SPERRE, jetzt
from .git import git, inhalt
from .zeilen import alt_zeile, im_diff, zeile_vorwaerts
from .zustand import datei_index, faeden_von, faden_status, review_laden, review_speichern, struktur_laden
from .gitlab import GitLabFehler
from .hinweise import see_also_aufloesen
from .ansichten import ansicht_lesen
from .seite import ansicht_struktur
from .quellen import quelle
from .zuhoerer import horcht, kontext, todo_offen
from .review import NUR_LESEN, ansicht_zuordnen, review_daten, stand, zeile_aus_klick

def wagen_daten(g, ansicht=None):
    """Alles, was die Seite über ihren Waggon braucht: Gespräch immer, Review (Kommentare, Hinweise) je nach Quelle."""
    q = quelle(g)
    gs = gespraech_daten(g, ansicht)
    if not gs.get("ok"):
        return gs
    rv = review_daten(g, ansicht) if q.kann["review"] else \
        {"ok": True, "kommentare": [], "hinweise": [], "quellen": [], "ausstehend": 0, "ausserhalb": 0, "web_url": ""}
    with SPERRE:
        st = review_laden(g)
    return dict(rv, faeden=gs["kommentare"], g_ausstehend=gs["ausstehend"], horcht=gs["horcht"], kontext=gs["kontext"], todo=gs["todo"],
                agenten=gs["agenten"], kann=q.kann, stand=stand(g, st), ausserhalb=rv["ausserhalb"] + gs["ausserhalb"])


def gespraech_agenten(g):
    """Namen, an die man im GitLab-Modus fragen kann: eingerichtete [agenten] und wer gerade zuhört."""
    namen = list(KONF.get("agenten") or {})
    if quelle(g).kann["committen"] and "Claude" not in namen:  # lokal ist Claude immer da (todo / feedback_befehl)
        namen.insert(0, "Claude")
    wer = horcht(g)
    return namen + ([wer] if wer and wer not in namen else [])


def gespraech_daten(mr, ansicht=None):
    """Wie review_daten, für ein Gespräch: Fäden auf den Stand der Seite umgerechnet."""
    with SPERRE:
        st = review_laden(mr)
    struktur = struktur_laden(st)
    if struktur is None:
        try:
            _, struktur = quelle(mr).seite(mr)
        except GitLabFehler as e:
            return {"ok": False, "text": str(e)}
    head = struktur["refs"]["head_sha"]
    kom = []
    for k in faeden_von(st):
        von = (k.get("refs") or {}).get("head_sha") or head
        b, unter = k.get("b"), None
        if k.get("path") and b:
            b = zeile_vorwaerts(struktur["ordner"], von, head, k["path"], b)
            if b is None:
                unter = f'Zeile {k["b"]} hat sich seit dem Kommentar geändert'
        i = datei_index(struktur, k.get("path"))
        f = struktur["dateien"][i] if i is not None else None
        a = alt_zeile(f, b) if f and b else (k.get("a") if not k.get("b") else None)
        imd = bool(f and (a or b) and im_diff(f, a, b))  # Kontextzeilen: unter dem Dateinamen, „aufklappen“
        if f and b and not imd and not unter:
            unter = f"Zeile {b} liegt außerhalb der Änderungen"
        kom.append({"id": k["id"], "text": k["nachrichten"][0]["text"] if k["nachrichten"] else "", "path": k.get("path"),
                    "a": a, "b": b, "datei": i, "im_diff": imd, "unter": unter if i is not None else None,
                    "problem": unter, "zeile_text": k.get("zeile_text"), "status": faden_status(k),
                    "nachrichten": k["nachrichten"], "erledigt": k.get("erledigt"), "an": k.get("an") or "Claude",
                    "vom_agenten": bool(k.get("vom_agenten")),
                    "see_also": see_also_aufloesen(struktur["ordner"], head, k.get("see_also"), None, k.get("path"))
                    if k.get("see_also") else [],
                    "links": code_links(struktur["ordner"], head, [m["text"] for m in k["nachrichten"]],
                                        [d["neu"] for d in struktur["dateien"]])})
    ausserhalb = 0
    if ansicht:
        ans_st = ansicht_struktur(struktur, ansicht)
        vorher = len(kom)
        kom = ansicht_zuordnen(struktur, ans_st, kom)
        ausserhalb = vorher - len(kom)
    entwuerfe = sum(1 for k in faeden_von(st) for m in k["nachrichten"] if m["von"] == "ich" and not m.get("gesendet"))
    return {"ok": True, "kommentare": kom, "stand": stand(mr, st),
            "ausstehend": entwuerfe, "ausserhalb": ausserhalb, "horcht": horcht(mr), "kontext": kontext(mr),
            "agenten": gespraech_agenten(mr),
            "todo": st.get("todo_id") if todo_offen(st.get("todo_id")) else None}


def neue_nachricht(von, text, gesendet=False, wer=None):
    m = {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:8], "von": von, "text": text, "zeit": jetzt(),
         "gesendet": jetzt() if gesendet else None}
    if wer:
        m["wer"] = wer
    return m


def gespraech_aktion(mr, d):
    """neu | antworten | aendern | loeschen | erledigt | oeffnen (Nutzer, von der Seite). Rückgabe (ok, text)."""
    aktion = d.get("aktion")
    ansicht = ansicht_lesen(d.get("ansicht"))
    text = str(d.get("text") or "").strip()
    with SPERRE:
        st = review_laden(mr)
        struktur = struktur_laden(st)
        if aktion == "neu":
            if ansicht and ansicht[0] == "commit":
                return False, NUR_LESEN
            if not text:
                return False, "leerer Kommentar"
            k = {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:10], "refs": (struktur or {}).get("refs"),
                 "erstellt": jetzt(), "path": None, "old_path": None, "a": None, "b": None,
                 "nachrichten": [neue_nachricht("ich", text)], "erledigt": None}
            if d.get("an"):
                k["an"] = str(d["an"])[:40]
            if d.get("datei") is not None:
                fehler, ort = zeile_aus_klick(struktur, d, ansicht)
                if fehler:
                    return False, fehler if quelle(mr).kann["review"] else fehler.replace("Der MR hat", "Das Projekt hat")
                k.update(ort)
                if ort["b"]:
                    t = inhalt(struktur["ordner"], struktur["refs"]["head_sha"], ort["path"]) or ""
                    zeilen = t.split("\n")
                    k["zeile_text"] = zeilen[ort["b"] - 1] if ort["b"] <= len(zeilen) else None
            st["kommentare"].append(k)
            review_speichern(mr, st)
            return True, ""
        k = next((k for k in faeden_von(st) if k["id"] == d.get("id")), None)
        if not k:
            return False, "Gespräch nicht gefunden – Seite neu laden"
        m = next((m for m in k["nachrichten"] if m["id"] == d.get("nid")), None) if d.get("nid") else None
        if d.get("nid") and (not m or m["von"] != "ich" or m.get("gesendet")):
            return False, "Nur eigene, noch nicht gesendete Nachrichten lassen sich ändern"
        if aktion == "antworten":
            if not text:
                return False, "leere Nachricht"
            k["nachrichten"].append(neue_nachricht("ich", text))
            k["erledigt"] = None
        elif aktion == "aendern":
            if not m or not text:
                return False, "leere Nachricht" if m else "Nachricht fehlt"
            m["text"] = text; m["zeit"] = jetzt()
        elif aktion == "loeschen":
            if m:
                k["nachrichten"].remove(m)
            if not m or not k["nachrichten"]:
                st["kommentare"].remove(k)
        elif aktion == "erledigt":
            k["erledigt"] = {"von": "ich", "zeit": jetzt()}
        elif aktion == "oeffnen":
            k["erledigt"] = None
        else:
            return False, "unbekannte Aktion"
        review_speichern(mr, st)
    return True, ""


# ---- Agent-Seite (CLI)

def alle_gespraeche():
    """Alle Gespräche (lokale Projekte und MRs) → Liste von Schlüsseln."""
    out = []
    for unter in ("lokal", "reviews"):
        for p in glob.glob(os.path.join(DATEN, unter, "*.json")):
            try:
                st = json.load(open(p, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            m = st.get("mr") or {}
            if m.get("lokal"):
                out.append({"lokal": m["lokal"]})
            elif m.get("iid") and any(k.get("nachrichten") is not None for k in st.get("kommentare") or []):
                out.append({"host": m["host"], "projekt": m["projekt"], "iid": m["iid"]})
    return out


_DATEIEN = {}


_LINK = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w-][\w.-]*\.[A-Za-z]\w{0,9})(?::(\d+)(?:-(\d+))?)?(?![\w/])")


def code_links(ordner, sha, texte, bevorzugt=()):
    """Code-Verweise in Nachrichten (pfad, pfad:zeile, pfad:von-bis, auch nur der Dateiname, wenn eindeutig – bei
    mehreren gewinnen die Dateien des Diffs) → [{t: Text im Original, path, zeile, bis}] für Links auf der Seite."""
    texte = [t for t in texte if t]
    if not texte or not sha:
        return []
    if (ordner, sha) not in _DATEIEN:
        if len(_DATEIEN) > 20:
            _DATEIEN.clear()
        alle = (git(ordner, "-c", "core.quotepath=false", "ls-tree", "-r", "--name-only", sha, check=False) or "").splitlines()
        namen = {}
        for p in alle:
            namen.setdefault(p.rsplit("/", 1)[-1], []).append(p)
        _DATEIEN[(ordner, sha)] = (alle, set(alle), namen)
    alle, menge, namen = _DATEIEN[(ordner, sha)]
    bevorzugt, out = set(bevorzugt), {}
    for text in texte:
        for m in _LINK.finditer(text):
            t, pfad = m.group(0), m.group(1)
            pfad = pfad[2:] if pfad.startswith("./") else pfad
            if t in out:
                continue
            if pfad in menge:
                p = pfad
            else:
                kand = [x for x in alle if x.endswith("/" + pfad)] if "/" in pfad else namen.get(pfad, [])
                if len(kand) > 1:
                    kand = [x for x in kand if x in bevorzugt] or kand
                if len(kand) != 1:
                    continue
                p = kand[0]
            z = int(m.group(2)) if m.group(2) else None
            out[t] = {"t": t, "path": p, "zeile": z, "bis": int(m.group(3)) if m.group(3) and z and int(m.group(3)) > z else None}
    return list(out.values())
