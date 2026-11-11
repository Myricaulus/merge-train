"""Gespräch mit dem Agenten: Fäden an Zeilen, Nachrichten, Daten für die Seite."""
import glob, hashlib, json, os, re
from .einstellungen import DATEN, KONF, jetzt
from .waggon import Fehler, Waggon
from .git import git, inhalt
from .zeilen import alt_zeile, im_diff, zeile_vorwaerts
from .akte import (akte_lesen, aktion_ausfuehren, datei_index, eintrag_entfernen, faden_anhaengen, faden_finden, faden_status, faeden_von,
    struktur_laden)
from .hinweise import see_also_aufloesen
from .ansichten import ansicht_lesen
from .seite import ansicht_struktur
from .quellen import quelle
from .zuhoerer import horcht, kontext, todo_offen
from .review import NUR_LESEN, ansicht_zuordnen, review_daten, stand, zeile_aus_klick

# Im lokalen Projekt-Diff wird aus einem Kommentar ein Gesprächsfaden: der Nutzer schreibt (Entwurf), „Feedback senden“
# schickt alle Entwürfe ab, der Agent holt sie mit „merge-train agent feedback“ ab und antwortet mit „agent antworten“.
# Bei MRs genauso, für Kommentare, die „an <Agent>“ gespeichert werden; sie liegen als Fäden (mit „nachrichten“) in der
# Review-Datei des MR und gehen nie nach GitLab. Felder eines Fadens: siehe akte.py.
# Wer zuhört: „agent horchen“ legt <akte>.horcht an (pid, Name). Hört niemand zu, startet „Feedback senden“ den
# Agenten aus [agenten] bzw. feedback_befehl – oder legt einen todo-Eintrag an („Session starten“ öffnet ihn).


def wagen_daten(waggon, ansicht=None):
    """Alles, was die Seite über ihren Waggon braucht: Gespräch immer, Review (Kommentare, Hinweise) je nach Quelle."""
    gespraech = gespraech_daten(waggon, ansicht)
    if not gespraech.get("ok"):
        return gespraech
    review = review_daten(waggon, ansicht) if waggon.kann["review"] else \
        {"ok": True, "kommentare": [], "hinweise": [], "quellen": [], "ausstehend": 0, "ausserhalb": 0, "web_url": ""}
    akte = akte_lesen(waggon)
    return dict(review, faeden=gespraech["kommentare"], g_ausstehend=gespraech["ausstehend"], horcht=gespraech["horcht"], kontext=gespraech["kontext"], todo=gespraech["todo"],
                agenten=gespraech["agenten"], kann=waggon.kann, stand=stand(waggon, akte), ausserhalb=review["ausserhalb"] + gespraech["ausserhalb"])


def gespraech_agenten(waggon):
    """Namen, an die man im GitLab-Modus fragen kann: eingerichtete [agenten] und wer gerade zuhört."""
    namen = list(KONF.get("agenten") or {})
    if waggon.kann["committen"] and "Claude" not in namen:  # lokal ist Claude immer da (todo / feedback_befehl)
        namen.insert(0, "Claude")
    wer = horcht(waggon)
    return namen + ([wer] if wer and wer not in namen else [])


def gespraech_daten(waggon, ansicht=None):
    """Wie review_daten, für ein Gespräch: Fäden auf den Stand der Seite umgerechnet."""
    akte = akte_lesen(waggon)
    struktur = struktur_laden(akte)
    if struktur is None:
        try:
            _, struktur = quelle(waggon).seite(waggon)
        except Fehler as e:
            return {"ok": False, "text": str(e)}
    head = struktur["refs"]["head_sha"]
    kommentare = []
    for k in faeden_von(akte):
        von = (k.get("refs") or {}).get("head_sha") or head
        b, unter = k.get("b"), None
        if k.get("path") and b:
            b = zeile_vorwaerts(struktur["ordner"], von, head, k["path"], b)
            if b is None:
                unter = f'Zeile {k["b"]} hat sich seit dem Kommentar geändert'
        i = datei_index(struktur, k.get("path"))
        f = struktur["dateien"][i] if i is not None else None
        a = alt_zeile(f, b) if f and b else (k.get("a") if not k.get("b") else None)
        zeile_im_diff = bool(f and (a or b) and im_diff(f, a, b))  # Kontextzeilen: unter dem Dateinamen, „aufklappen“
        if f and b and not zeile_im_diff and not unter:
            unter = f"Zeile {b} liegt außerhalb der Änderungen"
        kommentare.append({"id": k["id"], "text": k["nachrichten"][0]["text"] if k["nachrichten"] else "", "path": k.get("path"),
                    "a": a, "b": b, "datei": i, "im_diff": zeile_im_diff, "unter": unter if i is not None else None,
                    "problem": unter, "zeile_text": k.get("zeile_text"), "status": faden_status(k),
                    "nachrichten": k["nachrichten"], "erledigt": k.get("erledigt"), "an": k.get("an") or "Claude",
                    "vom_agenten": bool(k.get("vom_agenten")),
                    "see_also": see_also_aufloesen(struktur["ordner"], head, k.get("see_also"), None, k.get("path"))
                    if k.get("see_also") else [],
                    "links": code_links(struktur["ordner"], head, [m["text"] for m in k["nachrichten"]],
                                        [d["neu"] for d in struktur["dateien"]])})
    ausserhalb = 0
    if ansicht:
        ansicht_seite = ansicht_struktur(struktur, ansicht)
        vorher = len(kommentare)
        kommentare = ansicht_zuordnen(struktur, ansicht_seite, kommentare)
        ausserhalb = vorher - len(kommentare)
    entwuerfe = sum(1 for k in faeden_von(akte) for m in k["nachrichten"] if m["von"] == "ich" and not m.get("gesendet"))
    return {"ok": True, "kommentare": kommentare, "stand": stand(waggon, akte),
            "ausstehend": entwuerfe, "ausserhalb": ausserhalb, "horcht": horcht(waggon), "kontext": kontext(waggon),
            "agenten": gespraech_agenten(waggon),
            "todo": akte.get("todo_id") if todo_offen(akte.get("todo_id")) else None}


def neue_nachricht(von, text, gesendet=False, wer=None):
    m = {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:8], "von": von, "text": text, "zeit": jetzt(),
         "gesendet": jetzt() if gesendet else None}
    if wer:
        m["wer"] = wer
    return m


def faden_neu(waggon, akte, eingabe, text, ansicht):
    """Neuer Faden des Nutzers (Entwurf), an der geklickten Zeile oder allgemein."""
    if ansicht and ansicht[0] == "commit":
        return False, NUR_LESEN
    if not text:
        return False, "leerer Kommentar"
    struktur = struktur_laden(akte)
    k = {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:10], "refs": (struktur or {}).get("refs"),
         "erstellt": jetzt(), "path": None, "old_path": None, "a": None, "b": None,
         "nachrichten": [neue_nachricht("ich", text)], "erledigt": None}
    if eingabe.get("an"):
        k["an"] = str(eingabe["an"])[:40]
    if eingabe.get("datei") is not None:
        fehler, ort = zeile_aus_klick(struktur, eingabe, ansicht)
        if fehler:
            return False, fehler if waggon.kann["review"] else fehler.replace("Der MR hat", "Das Projekt hat")
        k.update(ort)
        if ort["b"]:
            t = inhalt(struktur["ordner"], struktur["refs"]["head_sha"], ort["path"]) or ""
            zeilen = t.split("\n")
            k["zeile_text"] = zeilen[ort["b"] - 1] if ort["b"] <= len(zeilen) else None
    faden_anhaengen(akte, k)
    return True, ""


# Aktionen an einem bestehenden Faden: (st, faden, nachricht | None, text) → (ok, text). Die Nachricht (nid) ist
# schon geprüft: eigene, noch nicht gesendete.

def faden_nutzer_antwortet(akte, k, m, text):
    if not text:
        return False, "leere Nachricht"
    k["nachrichten"].append(neue_nachricht("ich", text))
    k["erledigt"] = None
    return True, ""


def faden_nachricht_aendern(akte, k, m, text):
    if not m or not text:
        return False, "leere Nachricht" if m else "Nachricht fehlt"
    m["text"] = text; m["zeit"] = jetzt()
    return True, ""


def faden_nachricht_loeschen(akte, k, m, text):
    """Ohne Nachricht (oder wenn die letzte weg ist): den ganzen Faden."""
    if m:
        k["nachrichten"].remove(m)
    if not m or not k["nachrichten"]:
        eintrag_entfernen(akte, k)
    return True, ""


def faden_erledigen(akte, k, m, text):
    k["erledigt"] = {"von": "ich", "zeit": jetzt()}
    return True, ""


def faden_wieder_oeffnen(akte, k, m, text):
    k["erledigt"] = None
    return True, ""


AM_FADEN = {"antworten": faden_nutzer_antwortet, "aendern": faden_nachricht_aendern, "loeschen": faden_nachricht_loeschen,
            "erledigt": faden_erledigen, "oeffnen": faden_wieder_oeffnen}


FADEN_AKTIONEN = {"neu": faden_neu}


def gespraech_aktion(waggon, eingabe):
    """Aktion des Nutzers von der Seite: aus FADEN_AKTIONEN oder AM_FADEN (mit „id“, ggf. „nid“). Rückgabe (ok, text)."""
    aktion = eingabe.get("aktion")
    ansicht = ansicht_lesen(eingabe.get("ansicht"))
    text = str(eingabe.get("text") or "").strip()
    if aktion in FADEN_AKTIONEN:
        return aktion_ausfuehren(waggon, lambda akte: FADEN_AKTIONEN[aktion](waggon, akte, eingabe, text, ansicht))
    if aktion not in AM_FADEN:
        return False, "unbekannte Aktion"
    def am_faden(akte):
        k = faden_finden(akte, eingabe.get("id"))
        if not k:
            return False, "Gespräch nicht gefunden – Seite neu laden"
        nid = eingabe.get("nid")
        m = next((m for m in k["nachrichten"] if m["id"] == nid), None) if nid else None
        if nid and (not m or m["von"] != "ich" or m.get("gesendet")):
            return False, "Nur eigene, noch nicht gesendete Nachrichten lassen sich ändern"
        return AM_FADEN[aktion](akte, k, m, text)
    return aktion_ausfuehren(waggon, am_faden)


# ---- Agent-Seite (CLI)

def alle_gespraeche():
    """Alle Gespräche (lokale Projekte und MRs) → Liste von Schlüsseln."""
    out = []
    for unter in ("lokal", "reviews"):
        for p in glob.glob(os.path.join(DATEN, unter, "*.json")):
            try:
                akte = json.load(open(p, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            m = akte.get("mr") or {}
            if m.get("lokal") or m.get("iid") and any(k.get("nachrichten") is not None for k in akte.get("kommentare") or []):
                out.append(Waggon.aus_dict(m))
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
            zeile = int(m.group(2)) if m.group(2) else None
            out[t] = {"t": t, "path": p, "zeile": zeile, "bis": int(m.group(3)) if m.group(3) and zeile and int(m.group(3)) > zeile else None}
    return list(out.values())
