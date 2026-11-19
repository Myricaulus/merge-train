"""Review eines MRs: Kommentare anlegen und ändern (staged), Hinweise übernehmen, mit GitLab abgleichen und abschließen."""
import hashlib, os, re, tempfile, threading
from .waggon import Fehler, Ungueltig, Waggon
from .einstellungen import KONF, jetzt
from .git import ANLASS, anlass, branch_auschecken, git, inhalt, zerlegen
from .syntax import darstellen, zeilen_tokens
from .zeilen import alt_zeile, diff_enden, im_diff, kontext_zeile, zeile_vorwaerts, zurueck_diffs
from .diff_html import datei_tabelle
from .akte import (akte_bearbeiten, akte_datei, akte_lesen, aktion_ausfuehren, ausstehend, datei_index, diskussion_abgehakt,
    diskussion_stand, hinweis_stand, in_gitlab, kommentar_stand,
    diskussionen_stand, eintrag_entfernen, kommentar_anhaengen, notizen_von_anderen,
    kommentar_finden, kommentar_status, review_kommentare, struktur_laden)
from .gitlab import GitLabFehler, alle, glab, mr_lokal, mr_meta_holen, mr_pfad
from .hinweise import hinweis_dateien, hinweise_aufloesen, pfad_norm
from .ansichten import ansicht_lesen
from .seite import ansicht_struktur, mr_seite, projekt_zeiger
from .zuhoerer import horcht, kontext
from collections import Counter
from dataclasses import dataclass

def stand(waggon, akte):
    teile = [akte.get("struktur") or ""]
    teile.append(horcht(waggon) or "")  # „🎧 … hört zu“ soll sich auch ohne neue Nachricht aktualisieren
    k = kontext(waggon)
    teile.append(str(k and k["prozent"]))  # Kontext-Füllstand im HUD
    for p in [akte_datei(waggon)] + (hinweis_dateien(waggon, akte) if waggon.ist_mr else []):
        try:
            s = os.stat(p); teile.append(f"{p}:{s.st_mtime_ns}:{s.st_size}")
        except OSError:
            teile.append(p + ":-")
    return hashlib.sha1("|".join(teile).encode()).hexdigest()[:16]


def gitlab_reihenfolge(akte, kommentare, hinweise):
    """Reihenfolge der Box „GitLab-Kommentare“ = Sende-Reihenfolge bei „Review abschließen“: ids der Kommentare und keys
    der offenen Hinweise. Vom Nutzer sortiert (st["reihenfolge"]), Neues an seiner Stelle nach Datei und Zeile."""
    nat = lambda x: (x["datei"] if x.get("datei") is not None else -1, x.get("b") or x.get("a") or 0)
    eintraege = sorted([(x["id"], x) for x in kommentare if x["status"] != "loeschen"] +
                       [(h["key"], h) for h in hinweise if h["status"] == "offen"], key=lambda e: nat(e[1]))
    da = dict(eintraege)
    out = [i for i in akte.get("reihenfolge") or [] if i in da]
    gesetzt = set(out)
    for i, x in eintraege:
        if i not in gesetzt:
            out.insert(next((j for j, o in enumerate(out) if nat(da[o]) > nat(x)), len(out)), i)
    return out


def kommentare_fuer_seite(akte, struktur):
    """Review-Kommentare, wie die Seite sie braucht: Datei-Index, im Diff, Stufe."""
    out = []
    for k in review_kommentare(akte):
        if k.get("gitlab_weg") and k.get("gitlab_diskussion"):
            continue  # veröffentlicht: steht als Thread in diskussionen_fuer_seite
        i = datei_index(struktur, k.get("path"))
        f = struktur["dateien"][i] if i is not None else None
        out.append({"id": k["id"], "text": k["text"], "path": k.get("path"), "a": k.get("a"), "b": k.get("b"),
                    "datei": i, "im_diff": bool(f and (k.get("a") or k.get("b")) and im_diff(f, k.get("a"), k.get("b"))),
                    "finding": k.get("finding"), "agent": k.get("agent"), "hinweis": k.get("hinweis"), "status": kommentar_status(k),
                    "antwort_auf": k.get("antwort_auf"), **dict(zip(("stand", "wer"), kommentar_stand(k)))})
    return out


def diskussionen_fuer_seite(akte, struktur):
    """Alle GitLab-Diskussionen als Threads für die Seite, in der Form der Gesprächsfäden (gespraech_daten) mit
    ziel "gitlab": eigene veröffentlichte Kommentare wie die anderer, Nachrichten (von ich | andere; eigene
    Antwort-Entwürfe ungesendet mit ihrer Stufe), Stand (entwurf | wartet | antwort | erledigt), Ort auf den Stand der
    Seite umgerechnet. Bei eigenen gilt der Ort des Kommentars (allgemein gesendete stehen so an ihrer Zeile)."""
    eigene = {(k.get("gitlab_diskussion") or {}).get("id"): k for k in review_kommentare(akte) if k.get("gitlab_weg")}
    head, ordner, web = struktur["refs"]["head_sha"], struktur["ordner"], akte["mr"].get("web_url") or ""
    ich_id = akte.get("ich_id")
    out = []
    for d in akte.get("diskussionen") or []:
        k = eigene.get(d["id"])
        ort = k if k else d
        von = ((k.get("refs") or {}).get("head_sha") if k else d.get("head_sha")) or head
        b, unter = ort.get("b"), None
        if ort.get("path") and b:
            b = zeile_vorwaerts(ordner, von, head, ort["path"], b)
            if b is None:
                unter = f'Zeile {ort["b"]} hat sich seit dem Kommentar geändert'
        i = datei_index(struktur, ort.get("path"))
        f = struktur["dateien"][i] if i is not None else None
        a = ort.get("a") if not ort.get("b") else (alt_zeile(f, b) if f and b else None)
        drin = bool(f and (a or b) and im_diff(f, a, b))
        if f and b and not drin and not unter:
            unter = f"Zeile {b} liegt außerhalb der Änderungen"
        von = lambda wer_id: "ich" if wer_id == ich_id else "andere"
        nachrichten = [{"id": d.get("note_id"), "von": "ich" if k else von(d.get("wer_id")), "wer": d["wer"],
                        "text": k["text"] if k else d["text"], "zeit": d["zeit"], "gesendet": d["zeit"]}]
        nachrichten += [{"id": x.get("id"), "von": von(x.get("wer_id")), "wer": x.get("wer"), "text": x.get("text"),
                         "zeit": x.get("zeit"), "gesendet": x.get("zeit")} for x in d.get("antworten") or []]
        entwuerfe = [{"id": e["id"], "von": "ich", "text": e["text"], "zeit": e.get("erstellt"), "gesendet": None,
                      "stufe": kommentar_status(e)} for e in review_kommentare(akte)
                     if e.get("antwort_auf") == d["id"] and kommentar_status(e) not in ("weg", "loeschen")]
        erledigt, abgehakt = d.get("erledigt"), diskussion_abgehakt(akte, d)
        stand_, wer = diskussion_stand(akte, d)
        out.append({"id": "gl:" + str(d["id"]), "ziel": "gitlab", "diskussion": d["id"], "kommentar": k["id"] if k else None,
                    "finding": k.get("finding") if k else None, "agent": k.get("agent") if k else None, "text": nachrichten[0]["text"], "path": ort.get("path"),
                    "a": a, "b": b, "datei": i, "im_diff": drin, "unter": unter if i is not None else None, "problem": unter,
                    "stand": stand_, "wer": wer, "loesbar": d.get("loesbar"), "nachrichten": nachrichten + entwuerfe, "links": [],
                    "erledigt": dict(erledigt, von=von(erledigt.get("wer_id"))) if erledigt else None, "abgehakt": abgehakt,
                    "url": f'{web}#note_{d["note_id"]}' if web and d.get("note_id") else web})
    return out


def diskussion_abhaken(akte, eingabe):
    """☑ abwarten / doch dran: nur in der Akte, GitLab bleibt offen. Abwarten gibt den Ball ohne Antwort ab (Stand
    wartet), bis ein anderer danach schreibt."""
    did = eingabe.get("diskussion")
    if not diskussion_finden(akte, did):
        return False, "Diskussion nicht gefunden – „↻ MR-Daten“"
    ab = akte.setdefault("diskussionen_abgehakt", {})
    if eingabe.get("aktion") == "abhaken":
        ab[str(did)] = jetzt()
    else:
        ab.pop(str(did), None)
    return True, ""


def diskussion_aufloesen(mr, eingabe):
    """✓ erledigt / wieder öffnen einer GitLab-Diskussion – gleich in GitLab (wie ein Faden gleich erledigt ist)."""
    did, zu = eingabe.get("diskussion"), eingabe.get("aktion") == "erledigen"
    if not diskussion_finden(akte_lesen(mr), did):
        return False, "Diskussion nicht gefunden – „↻ MR-Daten“"
    roh = glab(mr.host, f"{mr_pfad(mr)}/discussions/{did}?resolved={'true' if zu else 'false'}", "PUT")  # ohne Sperre
    neu = diskussion_kompakt(roh) if isinstance(roh, dict) else None
    with akte_bearbeiten(mr) as akte:
        d = diskussion_finden(akte, did)
        if d is not None:
            if neu:
                d.update(neu)
            else:
                d["erledigt"] = {"wer": "", "wer_id": akte.get("ich_id"), "zeit": jetzt(zone=True)} if zu else None
            for kopie in diskussion_kopien(akte, did):
                kopie["erledigt"] = d["erledigt"]
    return True, "in GitLab erledigt" if zu else "in GitLab wieder geöffnet"


def sende_reihenfolge(mr, akte):
    """id → Platz in der Box „GitLab-Kommentare“ (= Reihenfolge beim Senden). Ohne Struktur: leer."""
    struktur = struktur_laden(akte)
    if struktur is None:
        return {}
    hinweise, _ = hinweise_aufloesen(mr, akte, struktur)
    return {i: n for n, i in enumerate(gitlab_reihenfolge(akte, kommentare_fuer_seite(akte, struktur), hinweise))}


def review_daten(mr, ansicht=None):
    akte = akte_lesen(mr)
    struktur = struktur_laden(akte)
    if struktur is None:
        _, struktur, mr = mr_seite(mr)
        akte = akte_lesen(mr)
    hinweise, quellen = hinweise_aufloesen(mr, akte, struktur)
    for h in hinweise:
        h["stand"], h["wer"] = hinweis_stand(h)
    kommentare = kommentare_fuer_seite(akte, struktur)
    diskussionen = diskussionen_fuer_seite(akte, struktur)
    reihenfolge = gitlab_reihenfolge(akte, kommentare, hinweise)  # im ganzen MR, vor dem Übertragen in eine Ansicht
    ausserhalb = 0
    if ansicht:  # Zeilen in die Ansicht übertragen; Einträge in anderen Dateien zählen nur
        ansicht_seite = ansicht_struktur(struktur, ansicht)
        vorher = len(kommentare) + sum(1 for h in hinweise if h["status"] == "offen")
        kommentare = ansicht_zuordnen(struktur, ansicht_seite, kommentare)
        hinweise = ansicht_zuordnen(struktur, ansicht_seite, hinweise)
        diskussionen = ansicht_zuordnen(struktur, ansicht_seite, diskussionen)
        ausserhalb = vorher - len(kommentare) - sum(1 for h in hinweise if h["status"] == "offen")
    return {"ok": True, "kommentare": kommentare, "hinweise": hinweise, "diskussionen": diskussionen,
            "diskussionen_stand": diskussionen_stand(akte), "quellen": quellen, "stand": stand(mr, akte),
            "web_url": akte["mr"].get("web_url", ""), "ausstehend": ausstehend(akte), "ausserhalb": ausserhalb,
            "in_gitlab": in_gitlab(akte),
            "reihenfolge": reihenfolge}


def seiten_struktur(sid, ansicht=None):
    """Struktur der Seite: GitLab-MR („host/gruppe/projekt/42“), lokales Projekt („projekt:name“) oder Myrling-Lauf
    („myrling:skript“), ganz oder Ansicht."""
    waggon = Waggon.aus_id(sid)
    if waggon.lokal:
        try:
            p = open(projekt_zeiger(waggon.lokal), encoding="utf-8").read().strip()
        except OSError:
            return None
        struktur = struktur_laden({"struktur": p})
    else:
        struktur = struktur_laden(akte_lesen(waggon))
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


def zeilen_daten(struktur, pfad, von, bis, stand=None):
    """Zeilen von..bis (neue Seite: MR-Stand bzw. Stand der Ansicht; stand: ein anderer Commit, see_also "ref") als
    HTML – zum Nachladen von Kontext und fürs Popup."""
    head = stand or (diff_enden(struktur)[1] if struktur and struktur.get("refs") else None)
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


def vergleich_daten(struktur, a, b, bereich_a=None, bereich_b=None, stand_b=None):
    """Zwei Dateien des MR-Stands gegeneinander (see_also mit "diff") nebeneinander als Tabelle: ganz oder nur je ein
    Bereich (von, bis); die Zeilennummern bleiben die der Dateien. stand_b: b aus diesem Commit (see_also "ref")."""
    head = diff_enden(struktur)[1] if struktur and struktur.get("refs") else None
    if not head:
        return {"ok": False, "text": "MR-Stand unbekannt – Seite neu laden"}
    a, b = pfad_norm(a), pfad_norm(b)
    ta, tb = inhalt(struktur["ordner"], head, a), inhalt(struktur["ordner"], stand_b or head, b)
    for p, t, s in ((a, ta, head), (b, tb, stand_b or head)):
        if t is None:
            return {"ok": False, "text": f"{p} gibt es im Stand {s[:8]} nicht"}
    teile = []
    for t, bereich in ((ta, bereich_a), (tb, bereich_b)):
        zeilen = t.splitlines(keepends=True)
        von, bis = bereich if bereich and bereich[0] else (1, len(zeilen))
        von = max(1, min(von, len(zeilen) or 1)); bis = max(von, min(bis or von, len(zeilen)))
        teile.append((von, bis, "".join(zeilen[von - 1:bis])))
    with tempfile.TemporaryDirectory() as tmp:
        pa, pb = os.path.join(tmp, "a"), os.path.join(tmp, "b")
        for pfad, (_, _, text) in ((pa, teile[0]), (pb, teile[1])):
            with open(pfad, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        roh = git(struktur["ordner"], "diff", "--no-index", "--no-color", "--no-ext-diff", "-U1000000", pa, pb,
                  check=False, ok=(0, 1))
    dateien = zerlegen(roh or "")
    teil = bereich_a or bereich_b
    d = dateien[0] if dateien else {"hunks": [], "binaer": False, "plus": 0, "minus": 0,
                                    "leer": f"beide {'Bereiche' if teil else 'Dateien'} sind gleich"}
    for h in d["hunks"]:  # Nummern der Ausschnitte → Nummern in den Dateien
        h["a"] += teile[0][0] - 1; h["b"] += teile[1][0] - 1
    d.update(alt=a, neu=b)
    return {"ok": True, "sha": head, "plus": d["plus"], "minus": d["minus"], "html": datei_tabelle(d, ta, tb),
            "a": [teile[0][0], teile[0][1]] if bereich_a else None, "b": [teile[1][0], teile[1][1]] if bereich_b else None}


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


def kommentar_neu(waggon, akte, eingabe, ansicht):
    """Neuer Review-Kommentar (staged): aus einem übernommenen Hinweis (draft), an der geklickten Zeile oder allgemein."""
    struktur = struktur_laden(akte)
    text = str(eingabe.get("text") or "").strip()
    k = {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:10], "refs": (struktur or {}).get("refs"),
         "erstellt": jetzt()}
    if eingabe.get("hinweis"):
        h = next((h for h in hinweise_aufloesen(waggon, akte, struktur)[0] if h["key"] == eingabe["hinweis"]), None)
        if not h:
            return False, "Hinweis nicht mehr vorhanden – Seite neu laden."
        if ansicht and h["path"] and not h["b"]:
            return False, "Der Hinweis lässt sich hier keiner Zeile zuordnen – im ganzen MR übernehmen."
        i = h["datei"]
        k.update(text=text or h["text"], path=h["path"] or None, a=h["a"], b=h["b"], finding=h["finding"],
                 agent=h.get("agent"), hinweis=h["key"], old_path=struktur["dateien"][i]["alt"] if i is not None else h["path"])
    elif eingabe.get("datei") is not None:
        fehler, ort = zeile_aus_klick(struktur, eingabe, ansicht)
        if fehler:
            return False, fehler
        k.update(text=text, **ort)
    else:
        k.update(text=text, path=None, a=None, b=None)
    if not k["text"]:
        return False, "leerer Kommentar"
    if k.get("hinweis"):
        akte["hinweise"][k["hinweis"]] = "uebernommen"
        akte["reihenfolge"] = [k["id"] if x == k["hinweis"] else x for x in akte.get("reihenfolge") or []]  # Platz behalten
    kommentar_anhaengen(akte, k)
    return True, ""


def kommentare_sortieren(mr, akte, eingabe, ansicht):
    """Box „GitLab-Kommentare“ umsortiert (bestimmt die Sende-Reihenfolge)."""
    ids = eingabe.get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        return False, "Reihenfolge ungültig"
    akte["reihenfolge"] = ids
    return True, ""


# Aktionen an einem bestehenden Kommentar: (st, kommentar, d) → (ok, text)

def kommentar_aendern(akte, k, eingabe):
    text = str(eingabe.get("text") or "").strip()
    if not text:
        return False, "leerer Kommentar"
    k["text"] = text
    return True, ""


def kommentar_loeschen(akte, k, eingabe):
    """Schon in GitLab: dort beim Abschließen löschen (staged „loeschen“), sonst gleich weg."""
    if k.get("hinweis"):
        akte["hinweise"][k["hinweis"]] = "verworfen"
    if k.get("gitlab_id") and not k.get("gitlab_weg"):
        k["geloescht"] = True
    else:
        eintrag_entfernen(akte, k)
    return True, ""


def kommentar_wiederherstellen(akte, k, eingabe):
    k.pop("geloescht", None)
    return True, ""


def antwort_entwurf(mr, akte, eingabe, ansicht):
    """Antwort auf eine GitLab-Diskussion als lokaler Entwurf (staged): „Review abschließen“ legt sie als Draft-Note mit
    in_reply_to_discussion_id an. Ort wie die Diskussion (nur für die Liste und die Reihenfolge)."""
    text = str(eingabe.get("text") or "").strip()
    d = diskussion_finden(akte, eingabe.get("diskussion"))
    if not d:
        return False, "Diskussion nicht gefunden – „↻ MR-Daten“"
    if not text:
        return False, "leere Antwort"
    kommentar_anhaengen(akte, {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:10], "erstellt": jetzt(),
                               "text": text, "antwort_auf": d["id"], "path": d.get("path"), "a": d.get("a"), "b": d.get("b")})
    return True, ""


def diskussion_kopien(akte, did):
    """Die Kopien der Diskussion did an den eigenen Kommentaren (gitlab_diskussion): ändert sich die Diskussion,
    ändern sie sich mit."""
    return [k["gitlab_diskussion"] for k in review_kommentare(akte) if (k.get("gitlab_diskussion") or {}).get("id") == did]


def diskussion_finden(akte, did):
    return next((d for d in akte.get("diskussionen") or [] if d.get("id") == did), None) if did else None


def antwort_senden(mr, eingabe):
    """„sofort senden“: Antwort gleich als Kommentar in die GitLab-Diskussion (ohne lokalen und GitLab-Entwurf), dann in
    die Akte. Rückgabe (ok, text)."""
    text = str(eingabe.get("text") or "").strip()
    did = eingabe.get("diskussion")
    if not diskussion_finden(akte_lesen(mr), did):
        return False, "Diskussion nicht gefunden – „↻ MR-Daten“"
    if not text:
        return False, "leere Antwort"
    note = glab(mr.host, f"{mr_pfad(mr)}/discussions/{did}/notes", "POST", {"body": text}) or {}  # GitLab, ohne Sperre
    antwort = {"id": note.get("id"), "wer": (note.get("author") or {}).get("name") or "",
               "wer_id": (note.get("author") or {}).get("id"), "text": note.get("body") or text,
               "zeit": note.get("created_at") or jetzt(zone=True)}
    with akte_bearbeiten(mr) as akte:
        d = diskussion_finden(akte, did)
        for x in ([d] if d is not None else []) + diskussion_kopien(akte, did):
            x.setdefault("antworten", []).append(antwort)
    return True, "Antwort in GitLab veröffentlicht"


KOMMENTAR_AKTIONEN = {"neu": kommentar_neu, "reihenfolge": kommentare_sortieren, "antworten": antwort_entwurf}
AM_KOMMENTAR = {"aendern": kommentar_aendern, "loeschen": kommentar_loeschen, "wiederherstellen": kommentar_wiederherstellen}


def kommentar_aktion(mr, eingabe):
    """Aktion des Nutzers von der Seite: aus KOMMENTAR_AKTIONEN oder AM_KOMMENTAR (mit „id“). Rückgabe (ok, text)."""
    aktion = eingabe.get("aktion")
    ansicht = ansicht_lesen(eingabe.get("ansicht"))
    if ansicht and ansicht[0] == "commit":
        return False, NUR_LESEN
    if aktion == "antworten" and eingabe.get("sofort"):
        return antwort_senden(mr, eingabe)
    if aktion in ("erledigen", "wiedereroeffnen"):
        return diskussion_aufloesen(mr, eingabe)
    if aktion in ("abhaken", "aufhaken"):
        return aktion_ausfuehren(mr, lambda akte: diskussion_abhaken(akte, eingabe))
    if aktion in KOMMENTAR_AKTIONEN:
        return aktion_ausfuehren(mr, lambda akte: KOMMENTAR_AKTIONEN[aktion](mr, akte, eingabe, ansicht))
    if aktion not in AM_KOMMENTAR:
        return False, "unbekannte Aktion"
    def am_kommentar(akte):
        k = kommentar_finden(akte, eingabe.get("id"))
        return AM_KOMMENTAR[aktion](akte, k, eingabe) if k else (False, "Kommentar nicht gefunden")
    return aktion_ausfuehren(mr, am_kommentar)


def hinweis_verwerfen(akte, key):
    akte["hinweise"][key] = "verworfen"
    return True, ""


def hinweis_zurueck(akte, key):
    akte["hinweise"].pop(key, None)
    return True, ""


AM_HINWEIS = {"verwerfen": hinweis_verwerfen, "zurueck": hinweis_zurueck}


def hinweis_aktion(mr, eingabe):
    """Agent-Hinweis (draft) verwerfen oder zurückholen. Übernehmen ist „neu“ in KOMMENTAR_AKTIONEN."""
    ansicht = ansicht_lesen(eingabe.get("ansicht"))
    if ansicht and ansicht[0] == "commit":
        return False, NUR_LESEN
    aktion = AM_HINWEIS.get(eingabe.get("aktion"))
    if not aktion:
        return False, "unbekannte Aktion"
    return aktion_ausfuehren(mr, lambda akte: aktion(akte, str(eingabe.get("key") or "")))


def entwurf_anlegen(mr, k, head, proj_url):
    """Draft-Note anlegen: an der Zeile, sonst (oder wenn GitLab ablehnt) als allgemeiner Kommentar mit Link."""
    host, mr_api = mr.host, mr_pfad(mr)
    refs = k.get("refs") or {}
    if k.get("antwort_auf"):  # Antwort auf eine Diskussion: Ort hat die Diskussion
        return glab(host, f"{mr_api}/draft_notes", "POST", {"note": k["text"], "in_reply_to_discussion_id": k["antwort_auf"]}), "antwort"
    if k.get("path") and (k.get("a") or k.get("b")) and refs.get("head_sha"):
        pos = {"position_type": "text", "base_sha": refs.get("base_sha"), "start_sha": refs.get("start_sha"),
               "head_sha": refs["head_sha"], "old_path": k.get("old_path") or k["path"], "new_path": k["path"]}
        if k.get("a"): pos["old_line"] = k["a"]
        if k.get("b"): pos["new_line"] = k["b"]
        try:
            return glab(host, f"{mr_api}/draft_notes", "POST", {"note": k["text"], "position": pos}), "position"
        except Fehler as e:
            fehler = str(e)
            if re.search(r"\b(401|403|404)\b", fehler):
                raise
    text = k["text"]
    if k.get("path"):
        zeile = k.get("b") or k.get("a")
        ref = refs.get("head_sha") or head
        ort = f'{k["path"]}:{zeile}' if zeile else k["path"]
        link = f'{proj_url}/-/blob/{ref}/{k["path"]}' + (f"#L{zeile}" if zeile else "")
        text = f"**[`{ort}`]({link})**\n\n{text}"
    return glab(host, f"{mr_api}/draft_notes", "POST", {"note": text}), "allgemein" if k.get("path") else "mr"


_ICH = {}  # GitLab-Benutzer-id je Host


def fehlende_entwuerfe(akte, vorhanden):
    """Gesendete Kommentare, deren Draft-Note in GitLab fehlt (auch schon als „weg“ markierte: früher galt jeder
    fehlende Entwurf als veröffentlicht)."""
    return [k for k in review_kommentare(akte) if k.get("gitlab_id") and not k.get("geloescht") and k["gitlab_id"] not in vorhanden]


def ich(host):
    """Meine GitLab-Benutzer-id (ändert sich nicht, kostet aber eine eigene Anfrage)."""
    if host not in _ICH:
        _ICH[host] = (glab(host, "user") or {}).get("id")
    return _ICH[host]


def eigene_kommentartexte(mr):
    """Texte meiner (nicht System-)Kommentare im MR – um veröffentlichte Entwürfe zu erkennen. GitLab-Anfragen."""
    host, mr_api = mr.host, mr_pfad(mr)
    ich(host)
    return [n.get("body") or "" for n in alle(host, f"{mr_api}/notes") if (n.get("author") or {}).get("id") == _ICH[host] and not n.get("system")]


def abgleich_vorbereiten(mr, vorhanden):
    """Was entwuerfe_abgleichen braucht, ohne Sperre geholt: eigene Kommentartexte, nur wenn Entwürfe fehlen (sonst None)."""
    return eigene_kommentartexte(mr) if fehlende_entwuerfe(akte_lesen(mr), vorhanden) else None


def entwuerfe_abgleichen(akte, vorhanden, eigene_texte):
    """Reine Funktion. Gesendete Kommentare, deren Draft-Note in GitLab fehlt: als Kommentar veröffentlicht → bleibt sent
    („weg“); sonst in GitLab verworfen (z. B. ganzes Review verworfen) → wieder staged, „Review abschließen“ sendet ihn neu.
    eigene_texte None = nicht geholt (es fehlte nichts): dann nichts tun. Rückgabe (veröffentlicht, verworfen)."""
    if eigene_texte is None:
        return 0, 0
    veroeffentlicht = verworfen = 0
    for k in fehlende_entwuerfe(akte, vorhanden):
        if any((k.get("gitlab_text") or k["text"]) in t for t in eigene_texte):  # „allgemein“: Text steht hinter dem Link
            veroeffentlicht += not k.get("gitlab_weg")
            k["gitlab_weg"] = True
        else:
            for f in ("gitlab_id", "gitlab_text", "gitlab_art", "gitlab_weg"):
                k.pop(f, None)
            verworfen += 1
    return veroeffentlicht, verworfen


def diskussion_auswerten(d):
    """GitLab-Diskussion → (note_id des ersten Kommentars, erledigt {wer, zeit} | None, Antworten ohne Systemnotizen)."""
    notes = d.get("notes") or []
    erste = notes[0] if notes else {}
    loesbar = [n for n in notes if n.get("resolvable")]
    erledigt = None
    if loesbar and all(n.get("resolved") for n in loesbar):
        von = next((n for n in loesbar if n.get("resolved_by")), loesbar[-1])
        erledigt = {"wer": (von.get("resolved_by") or {}).get("name") or "", "wer_id": (von.get("resolved_by") or {}).get("id"),
                    "zeit": von.get("resolved_at")}
    antworten = [{"id": n.get("id"), "wer": (n.get("author") or {}).get("name") or "",
                  "wer_id": (n.get("author") or {}).get("id"), "text": n.get("body") or "", "zeit": n.get("created_at")}
                 for n in notes[1:] if not n.get("system")]
    return erste.get("id"), erledigt, antworten


def diskussion_kompakt(d):
    """GitLab-Diskussion → Eintrag für akte["diskussionen"] (None bei Systemnotizen wie „added 1 commit“)."""
    notes = d.get("notes") or []
    if not notes or notes[0].get("system"):
        return None
    erste, pos = notes[0], notes[0].get("position") or {}
    note_id, erledigt, antworten = diskussion_auswerten(d)
    return {"id": d.get("id"), "note_id": note_id, "wer": (erste.get("author") or {}).get("name") or "",
            "wer_id": (erste.get("author") or {}).get("id"), "text": erste.get("body") or "", "zeit": erste.get("created_at"),
            "path": pos.get("new_path") or pos.get("old_path"), "old_path": pos.get("old_path"),
            "a": pos.get("old_line"), "b": pos.get("new_line"), "head_sha": pos.get("head_sha"),
            "loesbar": any(n.get("resolvable") for n in notes), "erledigt": erledigt, "antworten": antworten}


def diskussionen_abgleichen(akte, diskussionen, ich_id):
    """Reine Funktion. Alle Diskussionen des MR merken (akte["diskussionen"], auch die anderer) und veröffentlichte
    Kommentare mit ihrer verbinden (gemerkte id, sonst: erster Kommentar von mir mit dem gesendeten Text), dort Antworten
    und Erledigt-Status eintragen. Rückgabe (neue Beiträge anderer, neu erledigte Diskussionen) seit dem letzten Abruf."""
    vorher = akte.get("diskussionen")
    bekannt_ids = {i for i, _ in notizen_von_anderen(akte, ich_id)} if vorher is not None else None
    vorher_erledigt = {d["id"] for d in vorher or [] if d.get("erledigt")}
    akte["diskussionen"] = [x for x in map(diskussion_kompakt, diskussionen) if x]
    akte["ich_id"] = ich_id
    nach_id = {d.get("id"): d for d in diskussionen}
    vergeben = {k["gitlab_diskussion"]["id"] for k in review_kommentare(akte) if k.get("gitlab_diskussion")}
    neu_antworten = neu_erledigt = 0
    for k in review_kommentare(akte):
        if not k.get("gitlab_weg") or k.get("antwort_auf"):  # Antworten stehen in ihrer Diskussion
            continue
        alt = k.get("gitlab_diskussion") or {}
        d = nach_id.get(alt.get("id"))
        if d is None:
            text = k.get("gitlab_text") or k["text"]
            d = next((d for d in diskussionen if d.get("id") not in vergeben and d.get("notes")
                      and not d["notes"][0].get("system") and (d["notes"][0].get("author") or {}).get("id") == ich_id
                      and text in (d["notes"][0].get("body") or "")), None)
        if d is None:
            continue
        vergeben.add(d["id"])
        note_id, erledigt, antworten = diskussion_auswerten(d)
        if bekannt_ids is None:  # erster Abruf aller Diskussionen: neu ist, was am Kommentar noch nicht stand
            bekannt = {a["id"] for a in alt.get("antworten") or []}
            neu_antworten += sum(1 for a in antworten if a["id"] not in bekannt)
            neu_erledigt += bool(erledigt and not alt.get("erledigt"))
        k["gitlab_diskussion"] = {"id": d["id"], "note_id": note_id, "erledigt": erledigt, "antworten": antworten}
    if bekannt_ids is not None:
        neu_antworten = sum(1 for i, _ in notizen_von_anderen(akte, ich_id) if i not in bekannt_ids)
        neu_erledigt = sum(1 for d in akte["diskussionen"] if d.get("erledigt") and d["id"] not in vorher_erledigt)
    return neu_antworten, neu_erledigt


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


def mit_gitlab_abgleichen(mr, vorhanden, danach=None):
    """Gesendete Kommentare mit den Entwürfen in GitLab abgleichen: eigene Kommentartexte ohne Sperre holen, dann
    gesperrt eintragen. danach(akte) läuft in derselben Sperre (abschliessen plant dort).
    Rückgabe (veröffentlicht, verworfen, Ergebnis von danach)."""
    eigene_texte = abgleich_vorbereiten(mr, vorhanden)  # GitLab, ohne Sperre
    with akte_bearbeiten(mr) as akte:
        veroeffentlicht, verworfen = entwuerfe_abgleichen(akte, vorhanden, eigene_texte)
        return veroeffentlicht, verworfen, danach(akte) if danach else None


def mr_gitlab_holen(mr):
    """Alles aus GitLab für einen MR, ohne die Seite zu bauen: MR-Daten, Entwürfe (gesendete Kommentare abgleichen) und
    Diskussionen. Rückgabe: Meldungsteile (Liste), leer, wenn nichts Neues."""
    _, vorhanden = meta_und_entwuerfe(mr)
    if isinstance(vorhanden, Fehler):
        raise vorhanden
    veroeffentlicht, verworfen, _ = mit_gitlab_abgleichen(mr, vorhanden)
    teile = []
    if verworfen:
        teile.append(f"{verworfen} Entwurf/Entwürfe in GitLab verworfen – wieder lokal, „Review abschließen“ sendet sie neu")
    if veroeffentlicht:
        teile.append(f"{veroeffentlicht} in GitLab veröffentlicht")
    try:  # GitLab, ohne Sperre
        diskussionen, ich_id = alle(mr.host, f"{mr_pfad(mr)}/discussions"), ich(mr.host)
    except Fehler as e:
        return teile + [f"Diskussionen nicht abrufbar: {e}"]
    with akte_bearbeiten(mr) as akte:
        neu_antworten, neu_erledigt = diskussionen_abgleichen(akte, diskussionen if isinstance(diskussionen, list) else [], ich_id)
    if neu_antworten:
        teile.append(f"{neu_antworten} neue Antwort(en)")
    if neu_erledigt:
        teile.append(f"{neu_erledigt} in GitLab erledigt")
    return teile


_AUSCHECKEN = threading.Lock()


def mr_auschecken(mr):
    """Erster Besuch der MR-Seite (mr_auschecken = true): den Quell-Branch im lokalen Klon auschecken, wenn der Stand
    sauber ist (branch_auschecken). Einmal je MR (akte „ausgecheckt“) – wechselst du danach selbst zurück, bleibt es
    so. Ging es nicht (offene Änderungen …), beim nächsten Besuch wieder. Die Seite hängt nicht davon ab (sie liest die
    Branch-Refs, nicht HEAD), muss also nicht neu laden. Rückgabe: Text für die Glocke oder ""."""
    if not KONF["mr_auschecken"] or akte_lesen(mr).get("ausgecheckt"):
        return ""
    with _AUSCHECKEN:
        akte = akte_lesen(mr)
        if akte.get("ausgecheckt") or not akte.get("meta"):
            return ""
        try:
            ordner, _ = mr_lokal(mr, akte["meta"])
        except Fehler:
            return ""
        erledigt, text = branch_auschecken(ordner, akte["meta"].get("source_branch") or "")
        if erledigt:
            with akte_bearbeiten(mr) as a:
                a["ausgecheckt"] = jetzt()
        return text


def mr_daten_holen(mr):
    """Güterbahnhof „MR-Daten“ (auf der Seite des MR): mr_gitlab_holen, Seite gleich bauen."""
    vorher = akte_lesen(mr).get("struktur")
    teile = mr_gitlab_holen(mr)
    try:  # neu laden muss der Browser nur, wenn sich die Seite geändert hat
        mr_seite(mr)
        neu_laden = akte_lesen(mr).get("struktur") != vorher
    except Fehler:
        neu_laden = True
    text = " · ".join(["MR-Daten geholt"] + teile)
    return {"ok": True, "text": text, "neu_laden": neu_laden}


# ---- Review abschließen: planen (rein) → ausführen (GitLab, ohne Sperre) → je Schritt eintragen (kurz gesperrt)

def kommentar_ort(k):
    zeile = k.get("b") or k.get("a")
    return (k.get("path") or "allgemein") + (f":{zeile}" if zeile else "")


@dataclass
class Schritt:
    """Ein Schritt von „Review abschließen“. art:
      loeschen     Entwurf in GitLab löschen, dann lokal entfernen
      entfernen    zu löschen, aber in GitLab schon weg: nur lokal entfernen
      aendern      Text des Entwurfs in GitLab ersetzen
      uebernehmen  gleicher Entwurf ist schon in GitLab (z. B. Abbruch zwischen Anlegen und Speichern): nur merken
      anlegen      neuen Entwurf anlegen (kommentar: Kopie des Kommentars)"""
    art: str
    id: str             # Kommentar
    ort: str            # für Meldungen: pfad:zeile bzw. „allgemein“
    text: str           # Text, der gesendet wird
    gitlab_id: object = None
    gitlab_art: str = None  # bei uebernehmen: position | allgemein | mr
    kommentar: dict = None  # bei anlegen


def schritt_fuer(k, art, **mehr):
    return Schritt(art, k["id"], kommentar_ort(k), k["text"], **{"gitlab_id": k.get("gitlab_id"), **mehr})


def abschluss_planen(akte, vorhanden, platz):
    """Reine Funktion: was „Review abschließen“ in GitLab tun muss, als Liste von Schritten in der Reihenfolge der Box
    „GitLab-Kommentare“ (platz: id → Platz). Gesprächsfäden bleiben privat."""
    schritte = []
    vergeben = {k.get("gitlab_id") for k in review_kommentare(akte) if k.get("gitlab_id")}
    for k in sorted(review_kommentare(akte), key=lambda k: platz.get(k["id"], len(platz))):
        if k.get("geloescht"):
            schritte.append(schritt_fuer(k, "loeschen" if k.get("gitlab_id") in vorhanden else "entfernen"))
        elif k.get("gitlab_weg") or k.get("gitlab_id") and k["text"] == k.get("gitlab_text"):
            continue  # veröffentlicht bzw. unverändert in GitLab
        elif k.get("gitlab_id"):
            schritte.append(schritt_fuer(k, "aendern"))
        else:
            da = next((d for i, d in vorhanden.items() if i not in vergeben and
                       ((d.get("note") or "") == k["text"] or (d.get("note") or "").endswith("\n\n" + k["text"]))), None)
            if da:
                vergeben.add(da["id"])
                schritte.append(schritt_fuer(k, "uebernehmen", gitlab_id=da["id"], gitlab_art="position" if da.get("position")
                                    else ("allgemein" if k.get("path") else "mr")))
            else:
                schritte.append(schritt_fuer(k, "anlegen", kommentar=dict(k)))
    return schritte


def schritt_ausfuehren(mr, s, head, proj_url):
    """Einen Schritt in GitLab ausführen (ohne Sperre). Rückgabe: (gitlab_id, gitlab_art) des Entwurfs bzw. (None, None)."""
    entwurf = f"{mr_pfad(mr)}/draft_notes/{s.gitlab_id}"
    if s.art == "loeschen":
        glab(mr.host, entwurf, "DELETE")
    elif s.art == "aendern":
        glab(mr.host, entwurf, "PUT", {"note": s.text})
    elif s.art == "anlegen":
        antwort, gitlab_art = entwurf_anlegen(mr, s.kommentar, head, proj_url)
        return (antwort or {}).get("id"), gitlab_art
    elif s.art == "uebernehmen":
        return s.gitlab_id, s.gitlab_art
    return None, None


GITLAB_FELDER = ("gitlab_id", "gitlab_text", "gitlab_art", "gitlab_weg")


def schritt_eintragen(akte, s, gitlab_id, gitlab_art):
    """Ergebnis eines Schritts in die Akte. gitlab_text = der gesendete Text: hat der Nutzer währenddessen getippt,
    ist der Kommentar danach „geaendert“ (staged) statt still überschrieben. Rückgabe False: Kommentar inzwischen weg."""
    k = kommentar_finden(akte, s.id)
    if k is None:
        return False
    if s.art in ("loeschen", "entfernen"):
        if k.get("geloescht"):
            eintrag_entfernen(akte, k)
        else:  # währenddessen wiederhergestellt: in GitLab ist er weg, also wieder neu
            for f in GITLAB_FELDER:
                k.pop(f, None)
    elif s.art == "aendern":
        k["gitlab_text"] = s.text
    elif s.art in ("anlegen", "uebernehmen"):
        k.update(gitlab_id=gitlab_id, gitlab_text=s.text, gitlab_art=gitlab_art)
    else:
        raise ValueError(f"unbekannte Art {s.art}")
    return True


def abschluss_meldung(gezaehlt, veroeffentlicht, verworfen, fehler, direkt=False, urteil="kommentieren"):
    """Text nach „Review abschließen“. gezaehlt: Counter über die ausgeführten Arten, dazu „allgemein“, bei direkt
    „publiziert“ (1 = alle Entwürfe in GitLab veröffentlicht) und „urteil“ (1 = Urteil in GitLab gesetzt)."""
    teile = []
    if gezaehlt["anlegen"]:
        teile.append(f'{gezaehlt["anlegen"]} neu' +
                     (f' ({gezaehlt["allgemein"]} als allgemeiner Kommentar mit Link)' if gezaehlt["allgemein"] else ""))
    if gezaehlt["aendern"]: teile.append(f'{gezaehlt["aendern"]} aktualisiert')
    if gezaehlt["uebernehmen"]: teile.append(f'{gezaehlt["uebernehmen"]} waren schon da (nicht doppelt angelegt)')
    if gezaehlt["loeschen"]: teile.append(f'{gezaehlt["loeschen"]} gelöscht')
    if direkt and gezaehlt["publiziert"]:
        text = "In GitLab veröffentlicht" + (": " + ", ".join(teile) if teile else "") + "."
    else:
        text = ("Entwürfe in GitLab: " + ", ".join(teile) + ". Jetzt in GitLab prüfen und dort das Review abschicken."
                if teile else "" if urteil != "kommentieren" else "Nichts zu übertragen – alles ist schon als Entwurf in GitLab.")
    if gezaehlt["urteil"]:
        text = URTEILE[urteil] + (" · " + text if text else ".")
    if verworfen:
        text += f" {verworfen} davon waren in GitLab verworfen und wurden neu angelegt."
    if veroeffentlicht:
        text += f" {veroeffentlicht} Entwurf/Entwürfe sind in GitLab schon veröffentlicht."
    if fehler:
        text = "Fehler: " + " | ".join(fehler) + (" – Rest: " + text if teile else "")
    return text


URTEILE = {"kommentieren": "", "genehmigen": "In GitLab genehmigt", "aendern": "In GitLab Änderungen angefordert"}


def urteil_senden(mr, urteil):
    """Urteil des Reviews in GitLab setzen: genehmigen (REST approve) oder Änderungen anfordern (GraphQL
    mergeRequestRequestChanges – REST kennt das nicht). kommentieren setzt nichts."""
    if urteil == "genehmigen":
        glab(mr.host, f"{mr_pfad(mr)}/approve", "POST")
    elif urteil == "aendern":
        r = glab(mr.host, "graphql", "POST", {
            "query": "mutation($p: ID!, $i: String!) { mergeRequestRequestChanges(input: {projectPath: $p, iid: $i}) "
                     "{ errors } }", "variables": {"p": mr.projekt, "i": str(mr.iid)}}) or {}
        fehler = [e.get("message", str(e)) for e in r.get("errors") or []] + \
            list(((r.get("data") or {}).get("mergeRequestRequestChanges") or {}).get("errors") or [])
        if fehler:
            raise GitLabFehler("; ".join(fehler))


_ABSCHLUSS_LAEUFT, _ABSCHLUSS_SPERRE = set(), threading.Lock()  # Waggons, deren „Review abschließen“ gerade läuft
LAEUFT_SCHON = "„Review abschließen“ läuft für diesen MR schon (anderer Tab?) – danach die Seite neu laden."


def abschliessen(mr, direkt=False, urteil="kommentieren"):
    """Kommentare als Entwürfe (Draft-Notes) in den MR übertragen; direkt: danach alle meine Entwürfe des MR
    veröffentlichen (wie „Submit review“ in GitLab: eine Benachrichtigung); urteil (URTEILE): zuletzt genehmigen bzw.
    Änderungen anfordern – das geht auch ohne Kommentare. Rückgabe (ok, text, web_url).
    Je MR nur ein Lauf gleichzeitig: zwei Läufe planten denselben Stand und legten jeden Entwurf doppelt an."""
    with _ABSCHLUSS_SPERRE:
        if mr.id in _ABSCHLUSS_LAEUFT:
            return False, LAEUFT_SCHON, akte_lesen(mr)["mr"].get("web_url", "")
        _ABSCHLUSS_LAEUFT.add(mr.id)
    try:
        return abschluss_lauf(mr, direkt, urteil)
    finally:
        with _ABSCHLUSS_SPERRE:
            _ABSCHLUSS_LAEUFT.discard(mr.id)


def abschluss_lauf(mr, direkt=False, urteil="kommentieren"):
    if urteil not in URTEILE:
        raise Ungueltig(f"unbekanntes Urteil {urteil!r}")
    akte = akte_lesen(mr)
    head = ((struktur_laden(akte) or {}).get("refs") or {}).get("head_sha")
    web = akte["mr"].get("web_url", "")
    proj_url = web.split("/-/merge_requests/")[0]
    meta, vorhanden = meta_und_entwuerfe(mr)  # aktueller GitLab-Stand (Abschließen ist ohnehin eine GitLab-Aktion)
    gl_head = (meta.get("diff_refs") or {}).get("head_sha")
    if head and gl_head and gl_head != head:
        return (False, f"GitLab steht auf {gl_head[:8]}, die Seite auf {head[:8]} – erst den lokalen Stand aktualisieren "
                       "(jira-review: Branch und Kommentare), dann die Seite neu laden.", meta.get("web_url") or web)
    if isinstance(vorhanden, Fehler):
        return False, f"Entwürfe nicht abrufbar: {vorhanden}", web
    try:
        veroeffentlicht, verworfen, schritte = mit_gitlab_abgleichen(
            mr, vorhanden, lambda akte: abschluss_planen(akte, vorhanden, sende_reihenfolge(mr, akte)))
    except Fehler as e:
        return False, f"Kommentare des MR nicht abrufbar: {e}", web
    gezaehlt, fehler = Counter(), []
    for s in schritte:
        try:
            gitlab_id, gitlab_art = schritt_ausfuehren(mr, s, head, proj_url)
        except Fehler as e:
            fehler.append(f"{s.ort}: {e}")
            continue
        with akte_bearbeiten(mr) as akte:  # sofort eintragen: vergebene gitlab_ids überstehen einen Abbruch
            noch_da = schritt_eintragen(akte, s, gitlab_id, gitlab_art)
        if not noch_da and s.art == "anlegen" and gitlab_id:  # währenddessen gelöscht: nicht verwaisen lassen
            try:
                glab(mr.host, f"{mr_pfad(mr)}/draft_notes/{gitlab_id}", "DELETE")
            except Fehler:
                pass
            continue
        gezaehlt[s.art] += 1
        gezaehlt["allgemein"] += s.art == "anlegen" and gitlab_art == "allgemein"
    teile = []
    if not fehler and direkt and (schritte or vorhanden):
        try:
            glab(mr.host, f"{mr_pfad(mr)}/draft_notes/bulk_publish", "POST")
            gezaehlt["publiziert"] = 1
            teile = mr_gitlab_holen(mr)  # Entwürfe sind weg: als veröffentlicht erkennen, Diskussionen dazu holen
        except Fehler as e:
            fehler.append(f"Veröffentlichen: {e} – die Entwürfe liegen in GitLab")
    if not fehler and URTEILE[urteil]:
        try:
            urteil_senden(mr, urteil)
            gezaehlt["urteil"] = 1
        except Fehler as e:
            fehler.append(f"{URTEILE[urteil]}: nicht geklappt – {e}")
    if not fehler:
        with akte_bearbeiten(mr) as akte:
            akte["abgeschlossen"] = jetzt()
    text = abschluss_meldung(gezaehlt, veroeffentlicht, verworfen, fehler, direkt, urteil)
    return not fehler, " · ".join([text] + [t for t in teile if "veröffentlicht" not in t]), web


def ansicht_zuordnen(haupt, ansicht_seite, eintraege):
    """Kommentare/Hinweise (Zeilen im MR-Stand) in die Ansicht übertragen. Ändert die Einträge:
    datei/a/b/im_diff in Ansichts-Zeilen, „unter“ = Hinweistext, wenn sie unter dem Dateinamen stehen,
    „lesen“ = nicht änderbar, „mr_b“/„mr_a“ = Zeile im MR-Stand. Rückgabe: Einträge in Dateien der Ansicht."""
    ans = ansicht_seite["ansicht"]
    commit = ans["art"] == "commit"
    zurueck = zurueck_diffs(ansicht_seite["ordner"], ans["bis"], haupt["refs"]["head_sha"],
                            {x["path"] for x in eintraege if x.get("path")}) if commit else {}
    out = []
    for x in eintraege:
        x["mr_a"], x["mr_b"] = x.get("a"), x.get("b")
        x["lesen"] = commit
        if not x.get("path"):  # allgemein
            out.append(x); continue
        rueckweg = zurueck.get(x["path"])
        if rueckweg and rueckweg["status"] == "neu":
            continue  # Datei gab es nach dem Commit an diesem Pfad noch nicht
        i = datei_index(ansicht_seite, rueckweg["alt"] if rueckweg else x["path"])
        if i is None:
            continue  # Datei ist in dieser Ansicht nicht geändert
        f = ansicht_seite["dateien"][i]
        b, unter = x.get("b"), None
        if b and rueckweg:
            b = alt_zeile(rueckweg, b)  # Zeile im MR-Stand → Zeile nach dem Commit (None = später geändert)
            if b is None:
                unter = f'Zeile {x["mr_b"]} wurde nach diesem Commit noch geändert'
        elif not b:
            unter = ("Kommentar zur alten Seite des MR – hier nicht zuzuordnen" if x.get("a")
                     else x.get("problem") or "ohne Zeile")
            if not commit:
                x["lesen"] = True
        a = alt_zeile(f, b) if b else None
        zeile_im_diff = bool(b and im_diff(f, a, b))
        if b and not zeile_im_diff:
            unter = f"Zeile {b} liegt außerhalb der Änderungen" + (" dieses Commits" if commit else "")
        x.update(datei=i, a=a, b=b, im_diff=zeile_im_diff, unter=unter)
        if b and "problem" in x:
            x["problem"] = None
        out.append(x)
    return out
