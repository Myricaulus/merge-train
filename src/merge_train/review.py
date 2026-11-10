"""Review eines MRs: Kommentare anlegen und ändern (staged), Hinweise übernehmen, mit GitLab abgleichen und abschließen."""
import hashlib, os, re
from datetime import datetime
from .waggon import Fehler, Waggon
from .git import ANLASS, anlass, git, inhalt, zerlegen
from .syntax import darstellen, zeilen_tokens
from .zeilen import alt_zeile, diff_enden, im_diff, kontext_zeile, zurueck_diffs
from .diff_html import datei_tabelle
from .zustand import (ausstehend, datei_index, eintrag_entfernen, kommentar_anhaengen, kommentar_finden, kommentar_status, review_datei, review_kommentare,
    struktur_laden, zustand, zustand_lesen)
from .gitlab import alle, glab, mr_meta_holen, mr_pfad
from .hinweise import hinweis_dateien, hinweise_aufloesen, pfad_norm
from .ansichten import ansicht_lesen
from .seite import ansicht_struktur, mr_seite, projekt_zeiger
from .zuhoerer import horcht, kontext

def stand(mr, st):
    teile = [st.get("struktur") or ""]
    teile.append(horcht(mr) or "")  # „🎧 … hört zu“ soll sich auch ohne neue Nachricht aktualisieren
    k = kontext(mr)
    teile.append(str(k and k["prozent"]))  # Kontext-Füllstand im HUD
    for p in [review_datei(mr)] + ([] if mr.lokal else hinweis_dateien(mr, st)):
        try:
            s = os.stat(p); teile.append(f"{p}:{s.st_mtime_ns}:{s.st_size}")
        except OSError:
            teile.append(p + ":-")
    return hashlib.sha1("|".join(teile).encode()).hexdigest()[:16]


def gitlab_reihenfolge(st, kom, hinweise):
    """Reihenfolge der Box „GitLab-Kommentare“ = Sende-Reihenfolge bei „Review abschließen“: ids der Kommentare und keys
    der offenen Hinweise. Vom Nutzer sortiert (st["reihenfolge"]), Neues an seiner Stelle nach Datei und Zeile."""
    nat = lambda x: (x["datei"] if x.get("datei") is not None else -1, x.get("b") or x.get("a") or 0)
    eintraege = sorted([(x["id"], x) for x in kom if x["status"] != "loeschen"] +
                       [(h["key"], h) for h in hinweise if h["status"] == "offen"], key=lambda e: nat(e[1]))
    da = dict(eintraege)
    out = [i for i in st.get("reihenfolge") or [] if i in da]
    gesetzt = set(out)
    for i, x in eintraege:
        if i not in gesetzt:
            out.insert(next((j for j, o in enumerate(out) if nat(da[o]) > nat(x)), len(out)), i)
    return out


def review_daten(mr, ansicht=None):
    st = zustand_lesen(mr)
    struktur = struktur_laden(st)
    if struktur is None:
        _, struktur, mr = mr_seite(mr)
        st = zustand_lesen(mr)
    hinweise, quellen = hinweise_aufloesen(mr, st, struktur)
    kom = []
    for k in review_kommentare(st):
        i = datei_index(struktur, k.get("path"))
        f = struktur["dateien"][i] if i is not None else None
        kom.append({"id": k["id"], "text": k["text"], "path": k.get("path"), "a": k.get("a"), "b": k.get("b"),
                    "datei": i, "im_diff": bool(f and (k.get("a") or k.get("b")) and im_diff(f, k.get("a"), k.get("b"))),
                    "finding": k.get("finding"), "hinweis": k.get("hinweis"), "status": kommentar_status(k)})
    reihenfolge = gitlab_reihenfolge(st, kom, hinweise)  # im ganzen MR, vor dem Übertragen in eine Ansicht
    ausserhalb = 0
    if ansicht:  # Zeilen in die Ansicht übertragen; Einträge in anderen Dateien zählen nur
        ans_st = ansicht_struktur(struktur, ansicht)
        vorher = len(kom) + sum(1 for h in hinweise if h["status"] == "offen")
        kom = ansicht_zuordnen(struktur, ans_st, kom)
        hinweise = ansicht_zuordnen(struktur, ans_st, hinweise)
        ausserhalb = vorher - len(kom) - sum(1 for h in hinweise if h["status"] == "offen")
    return {"ok": True, "kommentare": kom, "hinweise": hinweise, "quellen": quellen, "stand": stand(mr, st),
            "web_url": st["mr"].get("web_url", ""), "ausstehend": ausstehend(st), "ausserhalb": ausserhalb,
            "reihenfolge": reihenfolge}


def seiten_struktur(sid, ansicht=None):
    """Struktur der Seite: GitLab-MR („host/gruppe/projekt/42“) oder lokales Projekt („projekt:name“), ganz oder Ansicht."""
    waggon = Waggon.aus_id(sid)
    if waggon.lokal:
        try:
            p = open(projekt_zeiger(waggon.lokal), encoding="utf-8").read().strip()
        except OSError:
            return None
        struktur = struktur_laden({"struktur": p})
    else:
        struktur = struktur_laden(zustand_lesen(waggon))
    if ansicht and struktur:
        struktur = ansicht_struktur(struktur, ansicht)
    return struktur


def datei_nachladen(struktur, i):
    """Diff einer zunächst ausgelassenen (großen/generierten) Datei."""
    try:
        if i < 0:
            raise IndexError
        f = struktur["dateien"][i]
    except (TypeError, IndexError):
        return {"ok": False, "text": "unbekannte Datei – Seite neu laden"}
    von, bis = diff_enden(struktur)
    out = git(struktur["ordner"], "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "-M", "-U3",
              von, bis, "--", *dict.fromkeys([f["alt"], f["neu"]]), check=False)
    d = next((x for x in zerlegen(out or "") if x["neu"] == f["neu"]), None)
    if d is None:
        return {"ok": False, "text": "Diff nicht gefunden"}
    alt = inhalt(struktur["ordner"], von, d["alt"]) or "" if d["status"] != "neu" else ""
    neu = inhalt(struktur["ordner"], bis, d["neu"]) or "" if d["status"] != "gelöscht" else ""
    return {"ok": True, "html": datei_tabelle(d, alt, neu, luecken=True)}


_TOKENS = {}


def zeilen_daten(struktur, pfad, von, bis):
    """Zeilen von..bis (neue Seite: MR-Stand bzw. Stand der Ansicht) als HTML – zum Nachladen von Kontext und fürs Popup."""
    head = diff_enden(struktur)[1] if struktur and struktur.get("refs") else None
    if not head:
        return {"ok": False, "text": "MR-Stand unbekannt – Seite neu laden"}
    pfad = pfad_norm(pfad)
    text = inhalt(struktur["ordner"], head, pfad)
    if text is None:
        return {"ok": False, "text": f"{pfad} gibt es im Stand {head[:8]} nicht"}
    zeilen = text.replace("\r\n", "\n").split("\n")
    if zeilen and zeilen[-1] == "":
        zeilen.pop()
    k = (struktur["ordner"], head, pfad)
    if k not in _TOKENS:
        if len(_TOKENS) > 40:
            _TOKENS.clear()
        _TOKENS[k] = zeilen_tokens(text, pfad)
    toks = _TOKENS[k]
    von = max(1, von); bis = min(len(zeilen), bis, von + 4999)
    return {"ok": True, "n": len(zeilen), "von": von, "bis": bis, "sha": head,
            "zeilen": [darstellen(toks[i - 1] if toks and i <= len(toks) else None, zeilen[i - 1], [], "")
                       for i in range(von, bis + 1)]}


def vergleich_daten(struktur, a, b):
    """Zwei Dateien des MR-Stands gegeneinander (see_also mit "diff"): ganze Dateien nebeneinander als Tabelle."""
    head = diff_enden(struktur)[1] if struktur and struktur.get("refs") else None
    if not head:
        return {"ok": False, "text": "MR-Stand unbekannt – Seite neu laden"}
    a, b = pfad_norm(a), pfad_norm(b)
    ta, tb = inhalt(struktur["ordner"], head, a), inhalt(struktur["ordner"], head, b)
    for p, t in ((a, ta), (b, tb)):
        if t is None:
            return {"ok": False, "text": f"{p} gibt es im Stand {head[:8]} nicht"}
    roh = git(struktur["ordner"], "diff", "--no-color", "--no-ext-diff", "-U1000000", f"{head}:{a}", f"{head}:{b}", check=False)
    dateien = zerlegen(roh or "")
    d = dateien[0] if dateien else {"hunks": [], "binaer": False, "plus": 0, "minus": 0, "leer": "beide Dateien sind gleich"}
    d.update(alt=a, neu=b)
    return {"ok": True, "sha": head, "plus": d["plus"], "minus": d["minus"], "html": datei_tabelle(d, ta, tb)}


def zeile_aus_klick(struktur, d, ansicht):
    """Klick auf eine Zeilennummer (datei, a, b, sha der Seite) → (fehler, {path, old_path, a, b}) im MR-Stand."""
    if not struktur or d.get("sha") != struktur["refs"].get("head_sha"):
        return "Der MR hat inzwischen einen neuen Stand – bitte Seite neu laden.", None
    seite = ansicht_struktur(struktur, ansicht) if ansicht else struktur
    try:
        f = seite["dateien"][int(d["datei"])]
    except (ValueError, IndexError, TypeError):
        return "unbekannte Datei", None
    a = int(d["a"]) if d.get("a") is not None else None
    b = int(d["b"]) if d.get("b") is not None else None
    if (a is None and b is None) or not (im_diff(f, a, b) or kontext_zeile(f, a, b)):
        return "Zeile nicht im Diff", None
    if ansicht:  # „seit“: rechts ist der MR-Stand → Zeile im MR-Diff bestimmen
        i = datei_index(struktur, f["neu"])
        if b is None or i is None:
            return "Hier nur auf der rechten Seite (MR-Stand) kommentierbar", None
        f = struktur["dateien"][i]
        a = alt_zeile(f, b)
        if not (im_diff(f, a, b) or kontext_zeile(f, a, b)):
            return "Zeile lässt sich im MR nicht zuordnen", None
    return None, {"path": f["neu"], "old_path": f["alt"], "a": a, "b": b}


NUR_LESEN = "Diese Ansicht ist nur zum Lesen – Kommentare im ganzen MR oder in „seit diesem“ bearbeiten."


def kommentar_neu(mr, st, d, ansicht):
    """Neuer Review-Kommentar (staged): aus einem übernommenen Hinweis (draft), an der geklickten Zeile oder allgemein."""
    struktur = struktur_laden(st)
    text = str(d.get("text") or "").strip()
    k = {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:10], "refs": (struktur or {}).get("refs"),
         "erstellt": datetime.now().isoformat(timespec="seconds")}
    if d.get("hinweis"):
        h = next((h for h in hinweise_aufloesen(mr, st, struktur)[0] if h["key"] == d["hinweis"]), None)
        if not h:
            return False, "Hinweis nicht mehr vorhanden – Seite neu laden."
        if ansicht and h["path"] and not h["b"]:
            return False, "Der Hinweis lässt sich hier keiner Zeile zuordnen – im ganzen MR übernehmen."
        i = h["datei"]
        k.update(text=text or h["text"], path=h["path"] or None, a=h["a"], b=h["b"], finding=h["finding"],
                 hinweis=h["key"], old_path=struktur["dateien"][i]["alt"] if i is not None else h["path"])
    elif d.get("datei") is not None:
        fehler, ort = zeile_aus_klick(struktur, d, ansicht)
        if fehler:
            return False, fehler
        k.update(text=text, **ort)
    else:
        k.update(text=text, path=None, a=None, b=None)
    if not k["text"]:
        return False, "leerer Kommentar"
    if k.get("hinweis"):  # erst nach allen Prüfungen ändern: frühe returns speichern sonst mit
        st["hinweise"][k["hinweis"]] = "uebernommen"
        st["reihenfolge"] = [k["id"] if x == k["hinweis"] else x for x in st.get("reihenfolge") or []]  # Platz behalten
    kommentar_anhaengen(st, k)
    return True, ""


def kommentare_sortieren(mr, st, d, ansicht):
    """Box „GitLab-Kommentare“ umsortiert (bestimmt die Sende-Reihenfolge)."""
    ids = d.get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return False, "Reihenfolge ungültig"
    st["reihenfolge"] = ids
    return True, ""


# Aktionen an einem bestehenden Kommentar: (st, kommentar, d) → (ok, text)

def kommentar_aendern(st, k, d):
    text = str(d.get("text") or "").strip()
    if not text:
        return False, "leerer Kommentar"
    k["text"] = text
    return True, ""


def kommentar_loeschen(st, k, d):
    """Schon in GitLab: dort beim Abschließen löschen (staged „loeschen“), sonst gleich weg."""
    if k.get("hinweis"):
        st["hinweise"][k["hinweis"]] = "verworfen"
    if k.get("gitlab_id") and not k.get("gitlab_weg"):
        k["geloescht"] = True
    else:
        eintrag_entfernen(st, k)
    return True, ""


def kommentar_wiederherstellen(st, k, d):
    k.pop("geloescht", None)
    return True, ""


KOMMENTAR_AKTIONEN = {"neu": kommentar_neu, "reihenfolge": kommentare_sortieren}
AM_KOMMENTAR = {"aendern": kommentar_aendern, "loeschen": kommentar_loeschen, "wiederherstellen": kommentar_wiederherstellen}


def kommentar_aktion(mr, d):
    """Aktion des Nutzers von der Seite: aus KOMMENTAR_AKTIONEN oder AM_KOMMENTAR (mit „id“). Rückgabe (ok, text)."""
    aktion = d.get("aktion")
    ansicht = ansicht_lesen(d.get("ansicht"))
    if ansicht and ansicht[0] == "commit":
        return False, NUR_LESEN
    if aktion not in KOMMENTAR_AKTIONEN and aktion not in AM_KOMMENTAR:
        return False, "unbekannte Aktion"
    with zustand(mr) as st:
        if aktion in KOMMENTAR_AKTIONEN:
            return KOMMENTAR_AKTIONEN[aktion](mr, st, d, ansicht)
        k = kommentar_finden(st, d.get("id"))
        if not k:
            return False, "Kommentar nicht gefunden"
        return AM_KOMMENTAR[aktion](st, k, d)


def hinweis_aktion(mr, d):
    ansicht = ansicht_lesen(d.get("ansicht"))
    if ansicht and ansicht[0] == "commit":
        return False, NUR_LESEN
    with zustand(mr) as st:
        key = str(d.get("key") or "")
        if d.get("aktion") == "verwerfen":
            st["hinweise"][key] = "verworfen"
        elif d.get("aktion") == "zurueck":
            st["hinweise"].pop(key, None)
        else:
            return False, "unbekannte Aktion"
    return True, ""


def entwurf_anlegen(mr, k, head, proj_url):
    """Draft-Note anlegen: an der Zeile, sonst (oder wenn GitLab ablehnt) als allgemeiner Kommentar mit Link."""
    host, P = mr.host, mr_pfad(mr)
    refs = k.get("refs") or {}
    if k.get("path") and (k.get("a") or k.get("b")) and refs.get("head_sha"):
        pos = {"position_type": "text", "base_sha": refs.get("base_sha"), "start_sha": refs.get("start_sha"),
               "head_sha": refs["head_sha"], "old_path": k.get("old_path") or k["path"], "new_path": k["path"]}
        if k.get("a"): pos["old_line"] = k["a"]
        if k.get("b"): pos["new_line"] = k["b"]
        try:
            return glab(host, f"{P}/draft_notes", "POST", {"note": k["text"], "position": pos}), "position"
        except Fehler as e:
            fehler = str(e)
            if re.search(r"\b(401|403|404)\b", fehler):
                raise
    text = k["text"]
    if k.get("path"):
        z = k.get("b") or k.get("a")
        ref = refs.get("head_sha") or head
        ort = f'{k["path"]}:{z}' if z else k["path"]
        link = f'{proj_url}/-/blob/{ref}/{k["path"]}' + (f"#L{z}" if z else "")
        text = f"**[`{ort}`]({link})**\n\n{text}"
    return glab(host, f"{P}/draft_notes", "POST", {"note": text}), "allgemein" if k.get("path") else "mr"


_ICH = {}  # GitLab-Benutzer-id je Host


def fehlende_entwuerfe(st, vorhanden):
    """Gesendete Kommentare, deren Draft-Note in GitLab fehlt (auch schon als „weg“ markierte: früher galt jeder
    fehlende Entwurf als veröffentlicht)."""
    return [k for k in review_kommentare(st) if k.get("gitlab_id") and not k.get("geloescht") and k["gitlab_id"] not in vorhanden]


def eigene_kommentartexte(mr):
    """Texte meiner (nicht System-)Kommentare im MR – um veröffentlichte Entwürfe zu erkennen. GitLab-Anfragen."""
    host, P = mr.host, mr_pfad(mr)
    if host not in _ICH:  # ändert sich nicht, kostet aber eine eigene Anfrage
        _ICH[host] = (glab(host, "user") or {}).get("id")
    return [n.get("body") or "" for n in alle(host, f"{P}/notes") if (n.get("author") or {}).get("id") == _ICH[host] and not n.get("system")]


def abgleich_vorbereiten(mr, vorhanden):
    """Was entwuerfe_abgleichen braucht, ohne Sperre geholt: eigene Kommentartexte, nur wenn Entwürfe fehlen (sonst None)."""
    return eigene_kommentartexte(mr) if fehlende_entwuerfe(zustand_lesen(mr), vorhanden) else None


def entwuerfe_abgleichen(st, vorhanden, eigene_texte):
    """Reine Funktion. Gesendete Kommentare, deren Draft-Note in GitLab fehlt: als Kommentar veröffentlicht → bleibt sent
    („weg“); sonst in GitLab verworfen (z. B. ganzes Review verworfen) → wieder staged, „Review abschließen“ sendet ihn neu.
    eigene_texte None = nicht geholt (es fehlte nichts): dann nichts tun. Rückgabe (veröffentlicht, verworfen)."""
    if eigene_texte is None:
        return 0, 0
    pub = verw = 0
    for k in fehlende_entwuerfe(st, vorhanden):
        if any((k.get("gitlab_text") or k["text"]) in t for t in eigene_texte):  # „allgemein“: Text steht hinter dem Link
            pub += not k.get("gitlab_weg")
            k["gitlab_weg"] = True
        else:
            for f in ("gitlab_id", "gitlab_text", "gitlab_art", "gitlab_weg"):
                k.pop(f, None)
            verw += 1
    return pub, verw


def meta_und_entwuerfe(mr):
    """MR-Daten und Draft-Notes gleichzeitig holen (zwei unabhängige GitLab-Anfragen).
    Rückgabe (meta, {id: draft} | Fehler)."""
    from concurrent.futures import ThreadPoolExecutor
    name = anlass()
    def mit(f, *a):  # Anlass fürs Log in den Thread mitnehmen
        ANLASS.name = name
        return f(*a)
    with ThreadPoolExecutor(2) as ex:
        f_meta = ex.submit(mit, mr_meta_holen, mr)
        f_ent = ex.submit(mit, alle, mr.host, f"{mr_pfad(mr)}/draft_notes")
        try:
            ent = {d.get("id"): d for d in f_ent.result()}
        except Fehler as e:
            ent = e
        return f_meta.result()[1], ent


# ---- Review abschließen: planen (rein) → ausführen (GitLab, ohne Sperre) → je Schritt eintragen (kurz unter der Sperre)

def kommentar_ort(k):
    z = k.get("b") or k.get("a")
    return (k.get("path") or "allgemein") + (f":{z}" if z else "")


def abschluss_planen(st, vorhanden, pos):
    """Reine Funktion: was „Review abschließen“ in GitLab tun muss, in der Reihenfolge der Box „GitLab-Kommentare“
    (pos: id → Platz). Schritte {art, id, ort, gitlab_id, text, …}, art:
      loeschen     Entwurf in GitLab löschen, dann lokal entfernen
      entfernen    zu löschen, aber in GitLab schon weg: nur lokal entfernen
      aendern      Text des Entwurfs in GitLab ersetzen
      uebernehmen  gleicher Entwurf ist schon in GitLab (z. B. Abbruch zwischen Anlegen und Speichern): nur merken
      anlegen      neuen Entwurf anlegen (kommentar: Kopie des Kommentars)"""
    schritte = []
    vergeben = {k.get("gitlab_id") for k in review_kommentare(st) if k.get("gitlab_id")}
    for k in sorted(review_kommentare(st), key=lambda k: pos.get(k["id"], len(pos))):  # Gesprächsfäden bleiben privat
        s = {"id": k["id"], "ort": kommentar_ort(k), "gitlab_id": k.get("gitlab_id"), "text": k["text"]}
        if k.get("geloescht"):
            s["art"] = "loeschen" if k.get("gitlab_id") in vorhanden else "entfernen"
        elif k.get("gitlab_weg"):
            continue
        elif k.get("gitlab_id"):
            if k["text"] == k.get("gitlab_text"):
                continue
            s["art"] = "aendern"
        else:
            da = next((d for i, d in vorhanden.items() if i not in vergeben and
                       ((d.get("note") or "") == k["text"] or (d.get("note") or "").endswith("\n\n" + k["text"]))), None)
            if da:
                s.update(art="uebernehmen", gitlab_id=da["id"],
                         gitlab_art="position" if da.get("position") else ("allgemein" if k.get("path") else "mr"))
                vergeben.add(da["id"])
            else:
                s.update(art="anlegen", kommentar=dict(k))
        schritte.append(s)
    return schritte


def schritt_ausfuehren(mr, s, head, proj_url):
    """Einen Schritt in GitLab ausführen (ohne Sperre). Rückgabe: Ergebnis-Felder (gitlab_id, gitlab_art)."""
    P = mr_pfad(mr)
    if s["art"] == "loeschen":
        glab(mr.host, f'{P}/draft_notes/{s["gitlab_id"]}', "DELETE")
    elif s["art"] == "aendern":
        glab(mr.host, f'{P}/draft_notes/{s["gitlab_id"]}', "PUT", {"note": s["text"]})
    elif s["art"] == "anlegen":
        r, art = entwurf_anlegen(mr, s["kommentar"], head, proj_url)
        return {"gitlab_id": (r or {}).get("id"), "gitlab_art": art}
    elif s["art"] == "uebernehmen":
        return {"gitlab_id": s["gitlab_id"], "gitlab_art": s["gitlab_art"]}
    return {}


def schritt_eintragen(st, s, ergebnis):
    """Ergebnis eines Schritts in den Zustand. gitlab_text = der gesendete Text: hat der Nutzer währenddessen getippt,
    ist der Kommentar danach „geaendert“ (staged) statt still überschrieben. Rückgabe False: Kommentar inzwischen weg."""
    k = kommentar_finden(st, s["id"])
    if k is None:
        return False
    if s["art"] in ("loeschen", "entfernen"):
        if k.get("geloescht"):
            eintrag_entfernen(st, k)
        else:  # währenddessen wiederhergestellt: in GitLab ist er weg, also wieder neu
            for f in ("gitlab_id", "gitlab_text", "gitlab_art", "gitlab_weg"):
                k.pop(f, None)
    elif s["art"] == "aendern":
        k["gitlab_text"] = s["text"]
    else:
        k.update(gitlab_id=ergebnis["gitlab_id"], gitlab_text=s["text"], gitlab_art=ergebnis["gitlab_art"])
    return True


def abschliessen(mr):
    """Kommentare als Entwürfe (Draft-Notes) in den MR übertragen – nicht veröffentlichen. Rückgabe (ok, text, web_url)."""
    head = ((struktur_laden(zustand_lesen(mr)) or {}).get("refs") or {}).get("head_sha")
    meta, vorhanden = meta_und_entwuerfe(mr)  # aktueller GitLab-Stand (Abschließen ist ohnehin eine GitLab-Aktion)
    gl_head = (meta.get("diff_refs") or {}).get("head_sha")
    if head and gl_head and gl_head != head:
        return (False, f"GitLab steht auf {gl_head[:8]}, die Seite auf {head[:8]} – erst den lokalen Stand aktualisieren "
                       "(jira-review: Branch und Kommentare), dann die Seite neu laden.", meta.get("web_url") or "")
    try:
        pos = {i: n for n, i in enumerate(review_daten(mr)["reihenfolge"])}  # wie in der Box „GitLab-Kommentare“
    except Fehler:
        pos = {}
    web = zustand_lesen(mr)["mr"].get("web_url", "")
    proj_url = web.split("/-/merge_requests/")[0]
    if isinstance(vorhanden, Fehler):
        return False, f"Entwürfe nicht abrufbar: {vorhanden}", web
    try:
        eigene_texte = abgleich_vorbereiten(mr, vorhanden)
    except Fehler as e:
        return False, f"Kommentare des MR nicht abrufbar: {e}", web
    z = {"neu": 0, "allg": 0, "akt": 0, "weg": 0, "wieder": 0}
    with zustand(mr) as st:
        z["veroeffentlicht"], z["verworfen"] = entwuerfe_abgleichen(st, vorhanden, eigene_texte)
        schritte = abschluss_planen(st, vorhanden, pos)
    fehler = []
    for s in schritte:
        try:
            ergebnis = schritt_ausfuehren(mr, s, head, proj_url)
        except Fehler as e:
            fehler.append(f'{s["ort"]}: {e}')
            continue
        with zustand(mr) as st:  # sofort eintragen: vergebene gitlab_ids überstehen einen Abbruch
            noch_da = schritt_eintragen(st, s, ergebnis)
        if not noch_da and s["art"] == "anlegen" and ergebnis.get("gitlab_id"):  # währenddessen gelöscht: nicht verwaisen lassen
            try:
                glab(mr.host, f'{mr_pfad(mr)}/draft_notes/{ergebnis["gitlab_id"]}', "DELETE")
            except Fehler:
                pass
            continue
        z["neu"] += s["art"] == "anlegen"; z["allg"] += s["art"] == "anlegen" and ergebnis["gitlab_art"] == "allgemein"
        z["akt"] += s["art"] == "aendern"; z["weg"] += s["art"] == "loeschen"; z["wieder"] += s["art"] == "uebernehmen"
    if not fehler:
        with zustand(mr) as st:
            st["abgeschlossen"] = datetime.now().isoformat(timespec="seconds")
    teile = []
    if z["neu"]: teile.append(f'{z["neu"]} neu' + (f' ({z["allg"]} als allgemeiner Kommentar mit Link)' if z["allg"] else ""))
    if z["akt"]: teile.append(f'{z["akt"]} aktualisiert')
    if z["wieder"]: teile.append(f'{z["wieder"]} waren schon da (nicht doppelt angelegt)')
    if z["weg"]: teile.append(f'{z["weg"]} gelöscht')
    text = ("Entwürfe in GitLab: " + ", ".join(teile) + ". Jetzt in GitLab prüfen und dort das Review abschicken."
            if teile else "Nichts zu übertragen – alles ist schon als Entwurf in GitLab.")
    if z["verworfen"]:
        text += f' {z["verworfen"]} davon waren in GitLab verworfen und wurden neu angelegt.'
    if z["veroeffentlicht"]:
        text += f' {z["veroeffentlicht"]} Entwurf/Entwürfe sind in GitLab schon veröffentlicht.'
    if fehler:
        text = "Fehler: " + " | ".join(fehler) + (" – Rest: " + text if teile else "")
    return not fehler, text, web


def ansicht_zuordnen(haupt, ans_st, eintraege):
    """Kommentare/Hinweise (Zeilen im MR-Stand) in die Ansicht übertragen. Ändert die Einträge:
    datei/a/b/im_diff in Ansichts-Zeilen, „unter“ = Hinweistext, wenn sie unter dem Dateinamen stehen,
    „lesen“ = nicht änderbar, „mr_b“/„mr_a“ = Zeile im MR-Stand. Rückgabe: Einträge in Dateien der Ansicht."""
    ans = ans_st["ansicht"]
    commit = ans["art"] == "commit"
    zurueck = zurueck_diffs(ans_st["ordner"], ans["bis"], haupt["refs"]["head_sha"],
                            {x["path"] for x in eintraege if x.get("path")}) if commit else {}
    out = []
    for x in eintraege:
        x["mr_a"], x["mr_b"] = x.get("a"), x.get("b")
        x["lesen"] = commit
        if not x.get("path"):  # allgemein
            out.append(x); continue
        z = zurueck.get(x["path"])
        if z and z["status"] == "neu":
            continue  # Datei gab es nach dem Commit an diesem Pfad noch nicht
        i = datei_index(ans_st, z["alt"] if z else x["path"])
        if i is None:
            continue  # Datei ist in dieser Ansicht nicht geändert
        f = ans_st["dateien"][i]
        b, unter = x.get("b"), None
        if b and z:
            b = alt_zeile(z, b)  # Zeile im MR-Stand → Zeile nach dem Commit (None = später geändert)
            if b is None:
                unter = f'Zeile {x["mr_b"]} wurde nach diesem Commit noch geändert'
        elif not b:
            unter = ("Kommentar zur alten Seite des MR – hier nicht zuzuordnen" if x.get("a")
                     else x.get("problem") or "ohne Zeile")
            if not commit:
                x["lesen"] = True
        a = alt_zeile(f, b) if b else None
        imd = bool(b and im_diff(f, a, b))
        if b and not imd:
            unter = f"Zeile {b} liegt außerhalb der Änderungen" + (" dieses Commits" if commit else "")
        x.update(datei=i, a=a, b=b, im_diff=imd, unter=unter)
        if b and "problem" in x:
            x["problem"] = None
        out.append(x)
    return out
