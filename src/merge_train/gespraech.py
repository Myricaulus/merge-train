"""Gespräch mit dem Agenten: Fäden an Zeilen, Nachrichten, Daten für die Seite."""
import glob, hashlib, json, os, re
from .einstellungen import DATEN, KONF, jetzt
from .waggon import ARTEN, Fehler, Waggon
from .git import git, inhalt
from .zeilen import alt_zeile, bereich_anfang_vorwaerts, im_diff, zeile_vorwaerts
from .akte import (akte_lesen, aktion_ausfuehren, andere_zweig_akten, datei_index, eintrag_entfernen, faden_anhaengen, faden_damals, faden_finden,
    faden_geaendert, faden_stand,
    faden_status, faeden_von, kommentar_finden)
from .hinweise import hinweise_aufloesen, see_also_aufloesen
from .ansichten import ansicht_lesen
from .seite import ansicht_struktur
from .quellen import quelle
from .zuhoerer import horcht, kontext, todo_offen
from .review import NUR_LESEN, ansicht_zuordnen, review_daten, seiten_struktur, stand, zeile_aus_klick

# Im lokalen Projekt-Diff wird aus einem Kommentar ein Gesprächsfaden: der Nutzer schreibt (Entwurf), „An Agent senden“
# schickt alle Entwürfe ab, der Agent holt sie mit „merge-train agent feedback“ ab und antwortet mit „agent antworten“.
# Bei MRs genauso, für Kommentare, die „an <Agent>“ gespeichert werden; sie liegen als Fäden (mit „nachrichten“) in der
# Review-Datei des MR und gehen nie nach GitLab. Felder eines Fadens: siehe akte.py.
# Wer zuhört: „agent horchen“ legt <akte>.horcht an (pid, Name). Hört niemand zu, startet „An Agent senden“ den
# Agenten aus [agenten] bzw. feedback_befehl – oder legt einen todo-Eintrag an („Session starten“ öffnet ihn).


def wagen_daten(waggon, ansicht=None, seite=None):
    """Alles, was die Seite (Schlüssel seite) über ihren Waggon braucht: Gespräch immer, Review (Kommentare, Hinweise)
    je nach Quelle."""
    gespraech = gespraech_daten(waggon, ansicht, seite)
    if not gespraech.get("ok"):
        return gespraech
    review = review_daten(waggon, ansicht, seite) if waggon.kann["review"] else \
        {"ok": True, "kommentare": [], "hinweise": [], "quellen": [], "ausstehend": 0, "ausserhalb": 0, "web_url": ""}
    akte = akte_lesen(waggon)
    return dict(review, faeden=gespraech["kommentare"], faeden_fremd=gespraech["fremd"], branch=gespraech["branch"],
                g_ausstehend=gespraech["ausstehend"], horcht=gespraech["horcht"], kontext=gespraech["kontext"], todo=gespraech["todo"],
                agenten=gespraech["agenten"], kann=waggon.kann, stand=stand(waggon, akte), ausserhalb=review["ausserhalb"] + gespraech["ausserhalb"])


def gespraech_agenten(waggon):
    """Namen, an die man fragen kann: Claude (immer, auch ohne Zuhörer: dann holt eine Session mit „agent feedback“
    ab, todo / feedback_befehl), eingerichtete [agenten] und wer gerade zuhört."""
    namen = list(KONF.get("agenten") or {})
    if "Claude" not in namen:
        namen.insert(0, "Claude")
    wer = horcht(waggon)
    return namen + ([wer] if wer and wer not in namen else [])


def gespraech_daten(waggon, ansicht=None, seite=None):
    """Wie review_daten, für ein Gespräch: Fäden des aktuellen Branches auf den Stand der Seite (Schlüssel seite)
    umgerechnet, dazu (fremd) die Fäden anderer Branches – nur zum Lesen, ohne Ort im Diff."""
    akte = akte_lesen(waggon)
    struktur = seiten_struktur(waggon, seite, akte=akte)
    if struktur is None and seite:
        return {"ok": False, "text": "Seite unbekannt – neu laden"}
    if struktur is None:
        try:
            _, struktur = quelle(waggon).seite(waggon)
        except Fehler as e:
            return {"ok": False, "text": str(e)}
    head = struktur["refs"]["head_sha"]
    branch = quelle(waggon).branch(waggon)
    kommentare = []
    for k in faeden_von(akte, branch):
        von = (k.get("refs") or {}).get("head_sha") or head
        b, unter = k.get("b"), None
        if k.get("path") and b:
            b = zeile_vorwaerts(struktur["ordner"], von, head, k["path"], b)
            if b is None:
                unter = faden_geaendert(k)
        ab = bereich_anfang_vorwaerts(struktur["ordner"], von, head, k.get("path"), k.get("ab"), b) if k.get("path") else None
        i = datei_index(struktur, k.get("path"))
        f = struktur["dateien"][i] if i is not None else None
        a = alt_zeile(f, b) if f and b else (k.get("a") if not k.get("b") else None)
        zeile_im_diff = bool(f and (a or b) and im_diff(f, a, b))  # Kontextzeilen: unter dem Dateinamen, „aufklappen“
        if f and b and not zeile_im_diff and not unter:
            unter = f"Zeile {b} liegt außerhalb der Änderungen"
        kommentare.append({"id": k["id"], "text": k["nachrichten"][0]["text"] if k["nachrichten"] else "", "path": k.get("path"),
                    "a": a, "b": b, "ab": ab, "datei": i, "im_diff": zeile_im_diff, "unter": unter if i is not None else None,
                    "problem": unter, "damals": damals_text(k), "status": faden_status(k),
                    **dict(zip(("stand", "wer"), faden_stand(k))),
                    "nachrichten": k["nachrichten"], "erledigt": k.get("erledigt"), "an": k.get("an") or "Claude",
                    "vom_agenten": bool(k.get("vom_agenten")), "zu": k.get("zu"),
                    "see_also": see_also_aufloesen(struktur["ordner"], head, k.get("see_also"), None, k.get("path"),
                                                  ziel=struktur["refs"].get("ziel"))
                    if k.get("see_also") else [],
                    "links": code_links(struktur["ordner"], head, [m["text"] for m in k["nachrichten"]],
                                        [d["neu"] for d in struktur["dateien"]])})
    ausserhalb = 0
    if ansicht:
        ansicht_seite = ansicht_struktur(struktur, ansicht)
        vorher = len(kommentare)
        kommentare = ansicht_zuordnen(struktur, ansicht_seite, kommentare)
        ausserhalb = vorher - len(kommentare)
    fremd = {k["id"]: k for k in faeden_von(akte) if k.get("branch") != branch}
    for p in andere_zweig_akten(waggon):  # lokal: die Akten der anderen Branches (eine Akte je Branch)
        for k in faeden_von(akte_lesen(waggon, pfad=p)):
            if k.get("branch") != branch:
                fremd.setdefault(k["id"], k)
    fremd = [faden_fremd(k) for k in fremd.values()]
    entwuerfe = sum(1 for k in faeden_von(akte, branch) for m in k["nachrichten"] if m["von"] == "ich" and not m.get("gesendet"))
    return {"ok": True, "kommentare": kommentare, "fremd": fremd, "branch": branch, "stand": stand(waggon, akte),
            "ausstehend": entwuerfe, "ausserhalb": ausserhalb, "horcht": horcht(waggon), "kontext": kontext(waggon),
            "agenten": gespraech_agenten(waggon),
            "todo": akte.get("todo_id") if todo_offen(akte.get("todo_id")) else None}


def damals_text(k):
    """„Zeilen 61–86: <Code der Zeile 61>“ für die Seite (unter „damals“), None ohne gemerkten Code."""
    ort, text = faden_damals(k)
    return f"{ort}: {text.strip()}" if text and text.strip() else None


def faden_fremd(k):
    """Faden eines anderen Branches für die Seite: Ort nur als Text (Zeilen gehören zu jenem Stand), nur lesen."""
    return {"id": k["id"], "text": k["nachrichten"][0]["text"] if k["nachrichten"] else "", "path": k.get("path"),
            "a": k.get("a"), "b": k.get("b"), "datei": None, "im_diff": False, "unter": None, "problem": None,
            "status": faden_status(k),
            **dict(zip(("stand", "wer"), faden_stand(k))), "nachrichten": k["nachrichten"],
            "erledigt": k.get("erledigt"), "an": k.get("an") or "Claude", "vom_agenten": bool(k.get("vom_agenten")),
            "zu": k.get("zu"), "see_also": [], "links": [], "lesen": True, "fremd": k.get("branch") or "ohne Branch"}


def neue_nachricht(von, text, gesendet=False, wer=None):
    m = {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:8], "von": von, "text": text, "zeit": jetzt(),
         "gesendet": jetzt() if gesendet else None}
    if wer:
        m["wer"] = wer
    return m


def faden_zu(waggon, akte, struktur, zu):
    """Ort eines Fadens, der an einem GitLab-Kommentar hängt (zu = „k:<Kommentar-id>“ oder „h:<Hinweis-key>“): der Ort
    des Kommentars bzw. des Hinweises. Rückgabe (fehler, felder für den Faden)."""
    art, _, kid = str(zu).partition(":")
    if art == "k":
        x = kommentar_finden(akte, kid)
        if not x:
            return "Kommentar nicht mehr vorhanden – Seite neu laden", None
        return None, {"zu": zu, "refs": x.get("refs") or (struktur or {}).get("refs"), "path": x.get("path"),
                      "old_path": x.get("old_path"), "a": x.get("a"), "b": x.get("b")}
    if art == "h" and waggon.kann["review"]:
        h = next((h for h in hinweise_aufloesen(waggon, akte, struktur)[0] if h["key"] == kid), None)
        if not h:
            return "Hinweis nicht mehr vorhanden – Seite neu laden", None
        return None, {"zu": zu, "path": h["path"] or None, "old_path": h["path"] or None, "a": h["a"], "b": h["b"]}
    return "zu: k:<Kommentar-id> oder h:<Hinweis-key>", None


def faden_neu(waggon, akte, eingabe, text, ansicht):
    """Neuer Faden des Nutzers (Entwurf), an der geklickten Zeile, an einem GitLab-Kommentar (zu) oder allgemein."""
    if ansicht and ansicht[0] == "commit":
        return False, NUR_LESEN
    if not text:
        return False, "leerer Kommentar"
    struktur = seiten_struktur(waggon, eingabe.get("seite"), akte=akte)
    if struktur is None and eingabe.get("seite"):
        return False, "Seite unbekannt – neu laden"
    k = {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:10], "branch": quelle(waggon).branch(waggon),
         "refs": (struktur or {}).get("refs"), "erstellt": jetzt(), "path": None, "old_path": None, "a": None, "b": None,
         "nachrichten": [neue_nachricht("ich", text)], "erledigt": None}
    if eingabe.get("an"):
        k["an"] = str(eingabe["an"])[:40]
    if eingabe.get("zu"):
        fehler, felder = faden_zu(waggon, akte, struktur, eingabe["zu"])
        if fehler:
            return False, fehler
        k.update(felder)
    elif eingabe.get("datei") is not None:
        fehler, ort = zeile_aus_klick(struktur, eingabe, ansicht)
        if fehler:
            return False, fehler if waggon.kann["review"] else fehler.replace("Der MR hat", "Das Projekt hat")
        k.update(ort)
        if eingabe.get("ab") is not None and ort["b"]:  # Bereich ab–b (Umschalt-Klick auf eine zweite Zeile)
            try:
                ab = int(eingabe["ab"])
            except (TypeError, ValueError):
                return False, "Bereich: ab ist keine Zeile"
            if not 1 <= ab < ort["b"]:
                return False, f"Bereich: ab {ab} muss vor Zeile {ort['b']} liegen"
            k["ab"] = ab
    if k["b"]:
        sha = (k.get("refs") or {}).get("head_sha") or struktur["refs"]["head_sha"]
        zeilen = (inhalt(struktur["ordner"], sha, k["path"]) or "").split("\n")
        k["zeile_text"] = zeilen[k["b"] - 1] if k["b"] <= len(zeilen) else None
        if k.get("ab"):
            k["ab_text"] = zeilen[k["ab"] - 1]
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
        if k.get("branch") != branch:
            return False, f'Das Gespräch gehört zu {k.get("branch") or "keinem Branch"} – hier nur zum Lesen'
        nid = eingabe.get("nid")
        m = next((m for m in k["nachrichten"] if m["id"] == nid), None) if nid else None
        if nid and (not m or m["von"] != "ich" or m.get("gesendet")):
            return False, "Nur eigene, noch nicht gesendete Nachrichten lassen sich ändern"
        return AM_FADEN[aktion](akte, k, m, text)
    branch = quelle(waggon).branch(waggon)
    return aktion_ausfuehren(waggon, am_faden)


# ---- Agent-Seite (CLI)

def alle_gespraeche(leere=False):
    """Alle Gespräche (lokale Projekte, Myrling-Läufe und MRs) → Liste von Schlüsseln. MRs und Myrling-Läufe nur mit
    Faden, außer leere: auch die noch ohne (horchen im Klon muss sie schon belauschen, bevor dort die erste Frage steht)."""
    out = []
    for art in ARTEN:
        for p in glob.glob(os.path.join(DATEN, art.ordner, "*.json")):
            try:
                akte = json.load(open(p, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            m = akte.get("mr") or {}
            if m.get("lokal") or (m.get("iid") or m.get("myrling")) and (leere or any(k.get("nachrichten") is not None for k in akte.get("kommentare") or [])):
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
