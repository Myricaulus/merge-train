"""merge-train agent …: die Befehle für den Agenten (feedback, antworten, horchen, kommentar, thread, zeigen, pruefen)."""
import argparse, hashlib, json, os, re, subprocess, sys, time
from datetime import datetime
from .einstellungen import ARBEITSSTAND, DATEN, INSTANZ, KONF, SKRIPT, ersetzen, jetzt, melden, projektname
from .waggon import Fehler, Waggon, von_bis
from .git import STAND_TEXT, git, inhalt, kurzpfad, projekt_ordner, stand_zu_gitlab
from .zeilen import bereich_anfang_vorwaerts, zeile_vorwaerts
from .diff_html import zeilenzahl
from .akte import (akte_bearbeiten, akte_datei, akte_lesen, faden_anhaengen, faden_finden, faden_status, faeden_von, kommentar_finden,
    kommentar_status, review_kommentare, struktur_laden)
from .gitlab import enc, geaenderte_dateien, glab, ist_mr_ref, mr_meta_holen, mr_ref, mr_vollstaendig, remote_info
from .hinweise import hinweis_dateien, hinweise_aufloesen, hinweise_lesen, ort_lesen, pfad_norm, see_also_aufloesen
from .seite import mr_seite
from .quellen import quelle
from .zuhoerer import SEITE_WEG_S, _prozess, agent_datei, agent_session, horcht_datei, prompt_merken, seite_datei, todo_offen
from .review import review_daten
from .gespraech import alle_gespraeche, neue_nachricht
from .prozess import im_browser

# Wer ruft an? Harnesses setzen Umgebungsvariablen: AI_AGENT (z. B. „claude-code_2-1-322_agent“, Konvention mehrerer
# Werkzeuge) oder eigene. Was davon nicht erkannt wird, stellt sich mit --als vor (oder MERGE_TRAIN_AGENT).
AI_AGENT_NAMEN = {"claude-code": "Claude", "claude": "Claude", "cursor": "Cursor", "gemini-cli": "Gemini",
                  "codex": "Codex", "github-copilot": "Copilot", "copilot": "Copilot"}
AGENT_UMGEBUNG = (("CLAUDECODE", "Claude"), ("CURSOR_AGENT", "Cursor"), ("GEMINI_CLI", "Gemini"),
                  ("CODEX_SANDBOX", "Codex"), ("OPENCODE", "opencode"))
VORSTELLEN = ('merge-train erkennt nicht, welcher Agent du bist – stell dich mit --als vor (Harness und Modell, '
              'z. B. --als "Copilot (Claude Sonnet 4.5)") oder setze MERGE_TRAIN_AGENT')


def agent_name(als=None, sonst=None):
    """Name des aufrufenden Agenten: --als, MERGE_TRAIN_AGENT, erkannt aus der Umgebung, sonst `sonst`. Ohne alles:
    Fehler (VORSTELLEN) – auf der Seite soll stehen, wer geschrieben hat, nicht „Agent“."""
    name = (als or os.environ.get("MERGE_TRAIN_AGENT") or "").strip()
    if not name:
        ai = (os.environ.get("AI_AGENT") or "").strip().lower()
        name = AI_AGENT_NAMEN.get(ai.split("_")[0], ai.split("_")[0]) if ai else ""
    name = name or next((n for var, n in AGENT_UMGEBUNG if os.environ.get(var)), "") or (sonst or "")
    if not name:
        raise Fehler(VORSTELLEN)
    return name[:40]


def gespraech_ziele(name=None):
    """Welche Gespräche meint der Agent? MR-Kennung/URL → dieses; Projekt → dessen lokales Gespräch;
    ohne Angabe: das aktuelle Repo (lokales Gespräch und alle MRs mit diesem Klon). Rückgabe: Liste von Schlüsseln."""
    if name:
        mr = None
        try:
            mr = Waggon.aus_id(name)
        except Fehler:
            if ist_mr_ref(name):
                mr = mr_ref(name, os.getcwd())
        if mr and not mr.lokal:
            treffer = [waggon for waggon in alle_gespraeche() if not waggon.lokal and waggon.projekt == mr.projekt
                       and waggon.iid == mr.iid and (not mr.host or waggon.host == mr.host)]
            return treffer[:1] or [mr]
    ordner = name or os.getcwd()
    if name and not os.path.isdir(ordner):
        ordner = projekt_ordner(name)
    wurzel = repo_wurzel(ordner)
    if not wurzel:
        raise Fehler(f"kein Git-Repo und kein MR: {name or os.getcwd()}")
    ziele = [Waggon(lokal=projektname(wurzel))] if KONF["lokal"] else []
    echt = os.path.realpath(wurzel)
    for waggon in alle_gespraeche():
        if not waggon.lokal:
            struktur = struktur_laden(akte_lesen(waggon))
            if struktur and os.path.realpath(struktur["ordner"]) == echt:
                ziele.append(waggon)
    if not ziele:
        raise Fehler(f"kein Gespräch zu {wurzel}")
    return ziele


def zeit_kurz(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m. %H:%M")
    except (TypeError, ValueError):
        return "?"


def faden_nachbarn(k, review, ohne=None):
    """GitLab-Kommentare und Agent-Hinweise an der Zeile des Fadens (damit der Agent weiß, welchen er ändern soll),
    ohne den, an dem der Faden hängt (ohne: Name aus kommentar_beschreiben)."""
    if not review or not k.get("path"):
        return []
    da = lambda x: x.get("path") == k["path"] and ((k.get("b") and x.get("b") and (k.get("ab") or k["b"]) <= x["b"] <= k["b"]) or (not k.get("b") and k.get("a") and x.get("a") == k["a"]))
    out = []
    for x in review["kommentare"]:
        if da(x) and x["status"] != "loeschen":
            out.append(kommentar_beschreiben("k", x))
    for h in review["hinweise"]:
        if da(h) and h["status"] == "offen":
            out.append(kommentar_beschreiben("h", h))
    return [x for x in out if x[0] != ohne]


def kommentar_beschreiben(art, x):
    """(Name, Stufe, Text) eines GitLab-Kommentars für die Ausgabe: Review-Kommentar (art „k“, aus der Akte oder
    review_daten) oder Agent-Hinweis („h“)."""
    if art == "h":
        stufe = "draft" if x["status"] == "offen" else f'draft, {x["status"]}'
        return f'Agent-Hinweis h:{x["key"]}', f'{stufe}, {x["quelle"]} {x["finding"]}'.strip(), x["text"]
    st = x.get("status") or kommentar_status(x)
    return f'GitLab-Kommentar {x["id"]}', K_STATUS.get(st, st), x["text"]


def faden_ziel(waggon, zu, review=None):
    """Der GitLab-Kommentar, an dem ein Faden hängt (zu „k:<id>“ | „h:<key>“) → (art, eintrag) wie bei
    umformulieren_ziel_finden, oder None, wenn er weg ist. Ein übernommener Hinweis ist sein Review-Kommentar."""
    art, _, kid = str(zu or "").partition(":")
    akte = akte_lesen(waggon)
    if art == "k":
        k = kommentar_finden(akte, kid)
        return ("k", k) if k else None
    if art != "h":
        return None
    if review is None:
        try:
            review = review_daten(waggon)
        except Fehler:
            return None
    h = next((h for h in review["hinweise"] if h["key"] == kid), None)
    if h and h["status"] == "offen":
        return "h", h
    k = next((k for k in review_kommentare(akte) if k.get("hinweis") == kid), None)
    return ("k", k) if k else ("h", h) if h else None


K_STATUS = {"neu": "staged", "geaendert": "staged, Änderung an einem gesendeten", "uebertragen": "sent",
            "weg": "sent, in GitLab veröffentlicht"}  # Stufen siehe AGENTS.md


def faden_ausgeben(k, wurzel, head, kontext=3, review=None, waggon=None):
    """Ein Faden für den Agenten: Ort im aktuellen Stand, Code drumherum, der GitLab-Kommentar, an dem er hängt (zu),
    die übrigen GitLab-Kommentare/Hinweise dort, Verlauf."""
    von = (k.get("refs") or {}).get("head_sha") or head
    b = zeile_vorwaerts(wurzel, von, head, k["path"], k["b"]) if k.get("path") and k.get("b") else None
    ab = bereich_anfang_vorwaerts(wurzel, von, head, k.get("path"), k.get("ab"), b)
    ort = "allgemein" if not k.get("path") else \
        f'{k["path"]}:{ab}-{b}' if ab else f'{k["path"]}:{b}' if b else (f'{k["path"]} (alte Seite, Zeile {k["a"]})' if k.get("a") and not k.get("b")
                                      else f'{k["path"]} (Zeile {k["b"]} hat sich seit dem Kommentar geändert)')
    an = f'  · an {k["an"]}' if k.get("an") else ""
    out = [f'── [{k["id"]}] {ort}{an}' + (f'  · {faden_status(k)}' if faden_status(k) != "wartet" else "")]
    if k.get("path") and b:
        t = inhalt(wurzel, head, k["path"]) or ""
        zeilen = t.split("\n")
        for i in range(max(1, (ab or b) - kontext), min(len(zeilen), b + kontext) + 1):
            out.append(f'  {"→" if (ab or b) <= i <= b else " "} {i:5} │ {zeilen[i - 1]}')
    elif k.get("zeile_text"):
        out.append(f'      damals │ {k["zeile_text"]}')
    ziel = faden_ziel(waggon, k["zu"], review) if k.get("zu") and waggon else None
    if k.get("zu"):
        if ziel:
            name, status, text = kommentar_beschreiben(*ziel)
            out.append(f'    HÄNGT AN {name} ({status}) – der Wunsch gilt diesem Text:')
            out.append("      " + text.replace("\n", "\n      "))
        else:
            out.append("    hing an einem GitLab-Kommentar, den es nicht mehr gibt")
    for name, status, text in faden_nachbarn(k, review, ohne=ziel and kommentar_beschreiben(*ziel)[0]):
        out.append(f'    an dieser Zeile: {name} ({status}):')
        out.append("      " + text.replace("\n", "\n      "))
    for m in k["nachrichten"]:
        if m.get("gesendet") or m["von"] == "claude":
            wer = "Nutzer" if m["von"] == "ich" else (m.get("wer") or k.get("an") or "Claude")
            text = m["text"].replace("\n", "\n      ")
            out.append(f'    {wer} ({zeit_kurz(m["gesendet"] or m["zeit"])}): {text}')
    return "\n".join(out)


def am_mr(waggon):
    """Zusatz zu „(nichts offen)“: keine Fäden heißt nicht, dass am MR nichts kommentiert ist."""
    if not waggon.kann["review"]:
        return ""
    try:
        return f" · am MR: {kommentare_zahl(review_daten(waggon))} – merge-train agent kommentare {waggon.id}"
    except Fehler:
        return ""


def faeden_abholen(ziele, alle=False, markieren=True, weg=None, wer=None, vorschau=False):
    """Text mit allen Fäden des aktuellen Branches, die auf den Agenten warten (alle: auch beantwortete). Markiert
    Nachrichten als abgeholt und merkt sich den Text für die Seite (prompt_merken, weg: horchen | feedback). vorschau:
    Entwürfe zählen als gesendet, nichts wird gespeichert (prompt_vorschau)."""
    teile, gesamt, geholt = [], 0, []
    for waggon in ziele:
        wurzel, head = quelle(waggon).ort(waggon)
        branch = quelle(waggon).branch(waggon)
        with akte_bearbeiten(waggon, speichern=markieren and not vorschau) as akte:
            if vorschau:
                for k in faeden_von(akte, branch):
                    for m in k["nachrichten"]:
                        if m["von"] == "ich" and not m.get("gesendet"):
                            m["gesendet"] = jetzt()
            faeden = [k for k in faeden_von(akte, branch) if faden_status(k) != "entwurf" or any(m.get("gesendet") for m in k["nachrichten"])]
            zeigen = [k for k in faeden if alle or faden_status(k) == "wartet" or faden_ungelesen(k)]
            if markieren:
                for k in zeigen:
                    for m in k["nachrichten"]:
                        if m["von"] == "ich" and m.get("gesendet") and not m.get("abgeholt"):
                            m["abgeholt"] = jetzt()
        bis = von_bis(waggon.lokal)[1] if waggon.lokal else None
        wo = f"{branch}{' · Arbeitsstand' if bis == ARBEITSSTAND else ''} {head[:8]}" if waggon.lokal else f"MR {waggon.id} · Stand {head[:8]} · Klon {wurzel}"
        kopf = (f'merge-train · {waggon.name} · {wo} · {sum(1 for k in faeden if faden_status(k) == "wartet")} '
                f'Gespräch(e) warten auf Antwort' + (f', {len(faeden)} insgesamt' if alle else ""))
        if not zeigen:
            if len(ziele) == 1:
                teile.append(kopf + "\n(nichts offen)" + am_mr(waggon))
            continue
        gesamt += len(zeigen)
        geholt.append(waggon)
        review = None
        if waggon.kann["review"]:
            try:
                review = review_daten(waggon)
            except Fehler:
                pass
        teile += [kopf, ""] + [faden_ausgeben(k, wurzel, head, review=review, waggon=waggon) + "\n" for k in zeigen]
        teile.append("Code-Zeilen beziehen sich auf " + (("den Arbeitsstand (auch nicht Committetes); Wünsche dort umsetzen, "
                     "nicht committen." if bis == ARBEITSSTAND else f"den aktuellen Stand von {bis}.") if waggon.kann["committen"]
                     else f"den Stand {head[:8]} im Klon (nichts ändern, nur antworten).") + "\n")
    if gesamt:
        teile.append('Antworten: merge-train agent antworten <id> "Text"   (umgesetzt: --erledigt · Text von stdin: -)')
        if any(waggon.kann["review"] for waggon in ziele):
            teile.append('GitLab-Kommentar umformulieren: merge-train agent kommentar <h:key | Kommentar-id | Faden-id> "Text"')
            teile.append('Faden „HÄNGT AN“ einem Kommentar: merge-train agent kommentar <Faden-id> "Text" ändert genau diesen '
                         'und erledigt den Faden – keine Antwort im Faden, außer der Nutzer will etwas erklärt haben')
    text = "\n".join(teile) or "(nichts offen)"
    if markieren and weg and not vorschau:
        for waggon in geholt:
            prompt_merken(waggon, weg, text, wer)
    return text, gesamt


def ort_kurz(x):
    """Ort eines Kommentars, Hinweises oder einer Diskussion: pfad:zeile, pfad:-alt (gelöschte Zeile) oder allgemein."""
    if not x.get("path"):
        return "allgemein"
    return x["path"] + (f':{x["b"]}' if x.get("b") else f':-{x["a"]} (alt)' if x.get("a") else "")


def kommentare_teile(review):
    """Was am MR schon kommentiert ist: drafts (offene Agent-Hinweise), staged/sent Review-Kommentare und
    GitLab-Diskussionen (Stand des letzten „MR-Daten“) – je [(Kopf, Text)]."""
    drafts = [(f'{ort_kurz(h)} · {n} ({st})', t) for h in review["hinweise"] if h["status"] == "offen"
              for n, st, t in [kommentar_beschreiben("h", h)]]
    eigene = [(f'{ort_kurz(k)} · {n} ({st})' + (" – Antwort auf Diskussion " + str(k["antwort_auf"]) if k.get("antwort_auf") else ""), t)
              for k in review["kommentare"] if k["status"] != "loeschen" for n, st, t in [kommentar_beschreiben("k", k)]]
    disk = []
    for d in review["diskussionen"]:
        wer = f'eigener Kommentar {d["kommentar"]}' if d.get("kommentar") else "GitLab-Diskussion"
        verlauf = "\n".join(f'{m.get("wer") or ("du" if m["von"] == "ich" else "?")}'
                            f'{"" if m.get("gesendet") else " (Antwort, " + K_STATUS.get(m.get("stufe"), "staged") + ")"}: {m["text"]}'
                            for m in d["nachrichten"])
        disk.append((f'{ort_kurz(d)} · {wer} · Diskussion {d["diskussion"]} ({d["stand"]})', verlauf))
    return {"draft": drafts, "staged/sent": eigene, "GitLab-Diskussionen": disk}


def kommentare_zahl(review):
    """Kurz für Kopfzeilen: „1 draft, 2 staged/sent, 0 GitLab-Diskussionen“."""
    return ", ".join(f"{len(v)} {k}" for k, v in kommentare_teile(review).items())


def kommentare_ausgeben(ziele):
    """agent kommentare: alles, was an den MRs schon kommentiert ist, mit Ort, Stufe, id und Text (nur lesen)."""
    teile = []
    for waggon in ziele:
        if not waggon.kann["review"]:
            continue
        try:
            review = review_daten(waggon)
        except Fehler as e:
            teile.append(f"merge-train · {waggon.name} · Kommentare nicht lesbar: {e}"); continue
        gruppen = kommentare_teile(review)
        teile.append(f"merge-train · {waggon.name} · MR {waggon.id} · {kommentare_zahl(review)}")
        for name, eintraege in gruppen.items():
            if eintraege:
                teile.append(f"\n{name}:")
                teile += [f"  {kopf}\n    " + text.replace("\n", "\n    ") for kopf, text in eintraege]
        teile.append("")
    if not teile:
        return "(kein MR zu diesem Repo – merge-train agent kommentare <MR>)"
    teile.append('Umformulieren: merge-train agent kommentar <h:key | Kommentar-id> "Text" (legt bei staged/sent einen neuen '
                 'draft daneben an). GitLab-Diskussionen: Stand des letzten „↻ MR-Daten“.')
    return "\n".join(teile)


def umformulieren_ziel_finden(ziel, ziele=None):
    """Was meint der Agent? h:<key> → Agent-Hinweis (art "h"), sonst Kommentar-id ("k") oder Faden-id ("f"), Anfang
    genügt (ab 4 Zeichen). Rückgabe (waggon, art, eintrag); Fehler, wenn nichts oder mehreres passt."""
    ziel = ziel.strip()
    hkey = ziel[2:] if ziel.startswith("h:") else None
    passt = lambda i, z: i == z or (len(z) >= 4 and i.startswith(z))
    treffer = []
    for waggon in ziele or alle_gespraeche():
        if not waggon.kann["review"]:
            continue
        if hkey:
            try:
                review = review_daten(waggon)
            except Fehler:
                continue
            treffer += [(waggon, "h", h) for h in review["hinweise"] if passt(h["key"], hkey)]
        else:
            akte = akte_lesen(waggon)
            treffer += [(waggon, "k", k) for k in review_kommentare(akte) if passt(k["id"], ziel)]
            treffer += [(waggon, "f", k) for k in faeden_von(akte) if passt(k["id"], ziel)]
    if not treffer:
        raise Fehler(f"{ziel}: kein Agent-Hinweis, GitLab-Kommentar oder Faden in einem MR (merge-train agent feedback zeigt sie)")
    if len(treffer) > 1:
        raise Fehler(f"{ziel} ist nicht eindeutig: " + ", ".join((x.get("key") or x["id"]) for _, _, x in treffer))
    return treffer[0]


def kommentar_umformulieren(ziel, text, ziele=None, als=None):
    """GitLab-Kommentar für den Nutzer umformulieren (Regel aus AGENTS.md): ein draft (noch nicht übernommener
    Agent-Hinweis) wird in seiner JSON geändert; zu allem anderen (staged/sent, übernommener/verworfener Hinweis, Faden)
    kommt ein neuer draft daneben. Review-Kommentare (staged) legt nur der Nutzer an („übernehmen“). Ein Faden, der an
    einem Kommentar hängt (zu), meint diesen; danach ist der Faden erledigt und hängt am neuen bzw. geänderten draft.
    Rückgabe: Meldung."""
    text = (text or "").strip()
    if not text:
        raise Fehler("Kommentartext fehlt")
    waggon, art, x = umformulieren_ziel_finden(ziel, ziele)
    agent = agent_name(als, sonst=x.get("an") if art == "f" else None)
    faden = x if art == "f" and x.get("zu") else None
    if faden:
        z = faden_ziel(waggon, faden["zu"])
        if not z:
            raise Fehler(f'Der Kommentar, an dem [{faden["id"]}] hing, ist weg – im Faden nachfragen (agent antworten)')
        art, x = z
    if art == "h" and x["status"] == "offen":
        meldung, datei, nr = hinweis_text_aendern(x, text)
    else:
        meldung, datei, nr = draft_daneben(waggon, art, x, text, agent)
    return meldung + (faden_nach_kommentar(waggon, faden["id"], datei, nr, agent) if faden else "")


def faden_nach_kommentar(waggon, fid, datei, nr, agent):
    """Nach „agent kommentar <Faden-id>“: der Faden hängt jetzt am draft (Marker nr in datei; ein geänderter Text gibt
    dem Hinweis einen neuen key) und ist erledigt – es sei denn, der Nutzer hat inzwischen nachgelegt."""
    key = next((h["key"] for h in review_daten(waggon)["hinweise"] if h["json"] == datei and h["nr"] == nr), None)
    with akte_bearbeiten(waggon) as akte:
        k = faden_finden(akte, fid)
        if not k:
            return ""
        if key:
            k["zu"] = "h:" + key
        neu = faden_ungelesen(k)
        if neu:
            return f' · [{fid}] bleibt offen: {len(neu)} neue Nachricht(en) – merge-train agent feedback'
        k["erledigt"] = {"von": "claude", "zeit": jetzt(), "wer": agent}
    melden(f"{waggon.name}: {agent} hat den Kommentar geändert")
    return f" · [{fid}] erledigt"


def draft_daneben(waggon, art, x, text, agent=None):
    """Neuer draft (Agent-Hinweis) an der Stelle von x, in der Review-JSON des MR: die des ersetzten Hinweises, sonst
    die erste angemeldete. Rückgabe (Meldung, datei, nr des neuen Markers)."""
    akte = akte_lesen(waggon)
    struktur = struktur_laden(akte) or {}
    head = (struktur.get("refs") or {}).get("head_sha")
    path, b = x.get("path") or None, x.get("b")
    if path and b and art != "h" and head:  # Kommentar/Faden: Zeile auf den aktuellen MR-Stand umrechnen
        von = (x.get("refs") or {}).get("head_sha") or head
        b = zeile_vorwaerts(struktur.get("ordner"), von, head, path, b)
    m = {"text": text}
    if agent:
        m["agent"] = agent
    fid = x.get("finding")
    if fid:
        m["finding"] = fid
    m["title"] = "neu formuliert" + (f" (zu {fid})" if fid else "")
    if path and b:
        m.update(path=path, line=b)
    elif path:  # nur alte Seite oder Zeile seitdem geändert: als allgemeiner Hinweis mit Ort im Titel
        m["title"] += f" – {path}"
    if art == "k":
        m["ersetzt"] = f'Kommentar {x["id"]}'
    elif art == "h":
        m["ersetzt"] = f'Hinweis {x.get("finding") or x["key"]} ({x["status"]})'
    datei = x.get("json") if art == "h" else None
    if not datei and art == "k" and x.get("hinweis"):
        datei = next((h.get("json") for h in review_daten(waggon)["hinweise"] if h["key"] == x["hinweis"]), None)
    datei = datei or next(iter(hinweis_dateien(waggon, akte)), None)
    if not datei:
        raise Fehler("Zu diesem MR gibt es keine Review-JSON (Agent-Hinweise) – den neuen Text im Faden vorschlagen")
    daten = json.load(open(datei, encoding="utf-8-sig"))
    markers = daten if isinstance(daten, list) else daten.setdefault("markers", [])
    markers.append(m)
    ersetzen(datei, json.dumps(daten, indent=2, ensure_ascii=False) + "\n")
    ort = f"{path}:{b}" if path and b else "allgemein"
    return (f"neuer Agent-Hinweis (draft) bei {ort} in {kurzpfad(datei)} – der Nutzer übernimmt oder verwirft ihn; "
            "der bisherige Kommentar bleibt unverändert", datei, len(markers) - 1)


def faden_anlegen(ziele, text, ort=None, siehe=(), als=None):
    """Neuer Faden vom Agenten (erste Nachricht von ihm, gesendet): an pfad:zeile, pfad:von-bis oder allgemein (ort None). siehe: see_also-
    Einträge wie in der Review-JSON ("pfad:zeile-bis", {"path", "line", "end", "label", "diff"}). Rückgabe: (id, Meldung)."""
    text = (text or "").strip()
    if not text:
        raise Fehler("Text fehlt")
    als = agent_name(als)
    if len(ziele) > 1:
        lokal = [waggon for waggon in ziele if waggon.lokal]
        if not lokal:
            raise Fehler("mehrere MRs zu diesem Repo – mit -p den MR angeben: " + ", ".join(waggon.id for waggon in ziele))
        ziele = lokal[:1]
    waggon = ziele[0]
    wurzel, head = quelle(waggon).ort(waggon)
    k = {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:10], "branch": quelle(waggon).branch(waggon),
         "refs": {"head_sha": head}, "erstellt": jetzt(),
         "path": None, "old_path": None, "a": None, "b": None, "nachrichten": [], "erledigt": None, "vom_agenten": True,
         "an": als}
    if ort:
        path, z, e = ort_lesen(ort)
        path = pfad_norm(path)
        t = inhalt(wurzel, head, path)
        if t is None:
            raise Fehler(f"{path} gibt es im Stand {head[:8]} nicht")
        ab, b = (z, e) if e else (None, z)
        zeilen = t.split("\n")
        for z in (ab, b):
            if z and not 1 <= z <= zeilenzahl(t):
                raise Fehler(f"{path} hat keine Zeile {z} ({zeilenzahl(t)} Zeilen)")
        if ab and ab >= b:
            raise Fehler(f"Bereich {ab}-{b}: die erste Zeile muss vor der letzten liegen")
        k.update(path=path, b=b, zeile_text=zeilen[b - 1] if b else None)
        if ab:
            k["ab"] = ab
    sa = see_also_aufloesen(wurzel, head, list(siehe), None, k["path"])
    kaputt = [f'{s["path"] or "?"}: {s["problem"]}' for s in sa if s["problem"]]
    if kaputt:
        raise Fehler("siehe auch: " + "; ".join(kaputt))
    if siehe:
        k["see_also"] = list(siehe)
    k["nachrichten"].append(neue_nachricht("claude", text, gesendet=True, wer=als))
    with akte_bearbeiten(waggon) as akte:
        faden_anhaengen(akte, k)
    wo = f'{k["path"]}:{k.get("ab") or k["b"]}' + (f'-{k["b"]}' if k.get("ab") else "") if k["b"] else (k["path"] or "allgemein")
    melden(f"{waggon.name}: {als} hat einen Thread angelegt ({wo})")
    return k["id"], f'[{k["id"]}] Thread bei {wo} in {waggon.name} angelegt'


def hinweis_text_aendern(h, text):
    """text eines Markers in der Review-JSON ersetzen, Formatierung der Datei möglichst erhalten."""
    pfad, nr = h["json"], h["nr"]
    roh = open(pfad, encoding="utf-8-sig").read()
    daten = json.loads(roh)
    markers = daten if isinstance(daten, list) else daten["markers"]
    alt = markers[nr].get("text")
    neu_roh = None
    if isinstance(alt, str):
        for enc in {json.dumps(alt, ensure_ascii=False), json.dumps(alt)}:
            if roh.count(enc) == 1:
                neu_roh = roh.replace(enc, json.dumps(text, ensure_ascii=False)); break
    if neu_roh is None:
        markers[nr]["text"] = text
        neu_roh = json.dumps(daten, indent=2, ensure_ascii=False) + "\n"
    try:
        json.loads(neu_roh)
    except ValueError as e:
        raise Fehler(f"{pfad}: geänderte JSON wäre ungültig ({e}) – nichts geschrieben")
    ersetzen(pfad, neu_roh)
    return f'Agent-Hinweis (draft) {h["finding"] or h["key"]} geändert (text in {kurzpfad(pfad)})', pfad, nr


def faden_ungelesen(k):
    """Gesendete Nachrichten des Nutzers, die der Agent noch nicht abgeholt hat (auch nach einer Antwort nachgeschoben)."""
    return [m for m in k["nachrichten"] if m["von"] == "ich" and m.get("gesendet") and not m.get("abgeholt")]


def faden_antworten(fid, text, erledigt=False, als=None, ziele=None):
    """Antwort auf Faden fid (Anfang genügt) – gesucht in ziele, sonst in allen Gesprächen."""
    treffer = []
    for waggon in ziele or alle_gespraeche():
        akte = akte_lesen(waggon)
        treffer += [(waggon, k["id"]) for k in faeden_von(akte) if k["id"] == fid or (len(fid) >= 4 and k["id"].startswith(fid))]
    if not treffer:
        raise Fehler(f"Gespräch {fid} gibt es nicht (merge-train agent feedback --alle)")
    if len(treffer) > 1:
        raise Fehler(f"{fid} ist nicht eindeutig: " + ", ".join(t[1] for t in treffer))
    waggon, kid = treffer[0]
    with akte_bearbeiten(waggon) as akte:
        k = faden_finden(akte, kid)
        if not k:
            raise Fehler(f"Gespräch {kid} wurde inzwischen gelöscht")
        neu = faden_ungelesen(k)
        if neu:  # der Nutzer hat inzwischen nachgelegt: nicht blind abhaken
            raise Fehler(f'In [{k["id"]}] gibt es {len(neu)} neue Nachricht(en), die du noch nicht gelesen hast – '
                               f'erst „merge-train agent feedback“, dann antworten:\n' +
                               "\n".join(f'    Nutzer ({zeit_kurz(m["gesendet"])}): {m["text"]}' for m in neu))
        wer = agent_name(als, sonst=k.get("an"))
        if text:
            k["nachrichten"].append(neue_nachricht("claude", text, gesendet=True, wer=wer))
        if erledigt:
            k["erledigt"] = {"von": "claude", "zeit": jetzt(), "wer": wer}
        rest = sum(1 for x in faeden_von(akte, quelle(waggon).branch(waggon)) if faden_status(x) == "wartet")
        tid = akte.get("todo_id")
    melden(f"{waggon.name}: {wer} hat geantwortet" + (" (erledigt)" if erledigt else ""))
    if not rest and todo_offen(tid):
        subprocess.run(["todo", "erledigt", tid, "-n", "Alle Fragen/Feedback in merge-train beantwortet"], capture_output=True)
    return k["id"], rest


def faeden_horchen(ziele, timeout=0, als=None):
    """Warten, bis neue (noch nicht abgeholte) Nachrichten da sind, dann ausgeben. Rückgabe (text, anzahl)."""
    import atexit, signal, time
    dateien = [horcht_datei(waggon) for waggon in ziele]
    for d in dateien:
        ersetzen(d, f"{os.getpid()} {jetzt()} {als}\n")
    sid, sess = os.environ.get("CLAUDE_CODE_SESSION_ID"), agent_session(os.getpid())
    if sid and sess and re.fullmatch(r"[\w-]+", sid):
        for waggon in ziele:
            ersetzen(agent_datei(waggon), f"{sess} {sid} {als}\n")
    def weg(*_):
        for d in dateien:
            try:
                if open(d).read().split()[0] == str(os.getpid()):
                    os.remove(d)
            except (OSError, IndexError):
                pass
    atexit.register(weg)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(0))
    ende = time.time() + timeout if timeout else None
    pfade = [akte_datei(waggon) for waggon in ziele]
    zuletzt = None
    session = agent_session(os.getpid())  # endet die Agenten-Session, hört auch horchen auf
    start, gesehen = time.time(), False
    seiten = [seite_datei(waggon) for waggon in ziele]
    while not ende or time.time() < ende:
        if session and _prozess(session) is None:
            return "merge-train: Agenten-Session beendet – horchen hört auf", 0
        zuletzt_da = max([os.path.getmtime(p) for p in seiten if os.path.exists(p)] or [0])
        gesehen = gesehen or zuletzt_da > start  # erst zählen, wenn die Seite nach dem Start offen war
        if gesehen and time.time() - zuletzt_da > SEITE_WEG_S:
            return (f"merge-train: Seite geschlossen (seit {SEITE_WEG_S} s kein Lebenszeichen) – horchen hört auf. "
                    "Neu horchen, wenn der Nutzer weitermachen will.", 0)
        m = []
        for p in pfade:
            try:
                m.append(os.stat(p).st_mtime_ns)
            except OSError:
                m.append(None)
        if m != zuletzt:
            zuletzt = m
            neu = []
            for waggon in ziele:
                akte = akte_lesen(waggon)
                if any(n["von"] == "ich" and n.get("gesendet") and not n.get("abgeholt")
                       for k in faeden_von(akte, quelle(waggon).branch(waggon)) for n in k["nachrichten"]):
                    neu.append(waggon)
            if neu:
                return faeden_abholen(neu, weg="horchen", wer=als)
        time.sleep(1)
    return "merge-train: keine neuen Nachrichten (Zeit abgelaufen)", 0


def repo_wurzel(ordner):
    """Oberster Ordner des Git-Repos, in dem ordner liegt, sonst None."""
    return (git(ordner, "rev-parse", "--show-toplevel", check=False) or "").strip() or None if os.path.isdir(ordner) else None


def mr_fuer_hinweise(pfad, daten, ref=None, cwd=None):
    """Zu welchem MR gehört die Hinweis-Datei? --mr, sonst Feld „mr“, sonst der offene MR des Branches. Das Projekt
    (für „!42“ und die Branch-Suche) kommt aus dem Repo, in dem der Agent arbeitet (cwd), sonst aus dem Repo der Datei
    – sie liegt z. B. im tasks/ eines anderen Repos. Sind es zwei Repos, wird in beiden gesucht; hat jedes einen MR zum
    Branch, ist das ein Fehler (--mr). Rückgabe (mr, ordner): ordner = das Repo, dessen origin zum MR passt."""
    kandidaten = list(dict.fromkeys(r for r in (repo_wurzel(cwd or os.getcwd()), repo_wurzel(os.path.dirname(pfad))) if r))
    if not kandidaten:
        kandidaten = [os.path.dirname(pfad)]
    projekte = {}
    for o in kandidaten:
        try:
            projekte[o] = remote_info(o)
        except Fehler:
            pass
    ref = ref or daten.get("mr")
    if ref:
        mr = mr_vollstaendig(mr_ref(str(ref), next(iter(projekte), kandidaten[0])))
    else:
        branch = daten.get("branch")
        if not branch:
            raise Fehler("kein MR zuzuordnen: --mr angeben oder „branch“/„mr“ in die JSON schreiben")
        if not projekte:
            raise Fehler(f"kein GitLab-Remote „origin“ in {', '.join(kurzpfad(o) for o in kandidaten)} – --mr angeben")
        treffer, fehler = [], []
        for host, projekt in dict.fromkeys(projekte.values()):
            try:
                lst = glab(host, f"projects/{enc(projekt)}/merge_requests?state=opened&source_branch={enc(branch)}")
            except Fehler as e:  # z. B. ein cwd mit GitHub-Remote: das andere Repo kann trotzdem passen
                fehler.append(f"{projekt}: {e}"); continue
            treffer += [m._replace(host=m.host or host) for m in (mr_ref(x["web_url"]) for x in lst or [])]
        if not treffer:
            gesucht = ", ".join(p for _, p in dict.fromkeys(projekte.values()))
            raise Fehler(f"kein offener MR für Branch {branch} in {gesucht}"
                         + "".join(f"\n  Abfrage gescheitert – {f}" for f in fehler) + "\n--mr angeben")
        treffer = list(dict.fromkeys(treffer))
        if len(treffer) > 1:
            raise Fehler(f"mehrere offene MRs für Branch {branch}: {', '.join(f'{m.projekt}!{m.iid}' for m in treffer)} "
                         "– --mr angeben oder „mr“ in die JSON schreiben")
        mr = treffer[0]
    ordner = next((o for o, (_, p) in projekte.items() if p.lower() == (mr.projekt or "").lower()), kandidaten[0])
    return mr, ordner


def vorfall_ordner():
    """Eingang für Vorfälle: vorfaelle/ im merge-train-Klon, aus dem das laufende Skript stammt (gitignored; auch bei
    anderen Nutzern, die merge-train von GitHub auschecken), sonst – nicht aus einem Klon gestartet, eigene Instanz –
    vorfaelle/ im Datenordner. MERGE_TRAIN_VORFAELLE überschreibt beides (Tests)."""
    if os.environ.get("MERGE_TRAIN_VORFAELLE"):
        return os.environ["MERGE_TRAIN_VORFAELLE"]
    klon = repo_wurzel(os.path.dirname(SKRIPT))
    if klon and not INSTANZ and os.path.isdir(os.path.join(klon, "skill", "merge-train")):
        return os.path.join(klon, "vorfaelle")
    return os.path.join(DATEN, "vorfaelle")


def vorfall_ablegen(titel, text, agent, wo):
    """Bericht als vorfaelle/JJJJ-MM-TT-<thema>.md ablegen (nie überschreiben). Rückgabe: Pfad."""
    ordner = vorfall_ordner()
    os.makedirs(ordner, exist_ok=True)
    thema = re.sub(r"[^a-z0-9äöüß]+", "-", titel.lower()).strip("-")[:60] or "vorfall"
    tag = datetime.now().strftime("%Y-%m-%d")
    pfad, n = os.path.join(ordner, f"{tag}-{thema}.md"), 2
    while os.path.exists(pfad):
        pfad, n = os.path.join(ordner, f"{tag}-{thema}-{n}.md"), n + 1
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(f"# {titel.strip()}\n\nDatum: {tag} · Agent: {agent} · Repo: {wo}\n\n{text.strip()}\n")
    return pfad


def befehl_vorfall(o):
    wo = repo_wurzel(os.getcwd())
    pfad = vorfall_ablegen(o.titel, text_von(o), agent_name(o.als, sonst="unbekannt"), kurzpfad(wo) if wo else os.getcwd())
    print(f"Vorfall abgelegt: {pfad}\nDem Nutzer in einem Satz sagen, dass es ihn gibt.")
    return 0


def agent_parser():
    ap = argparse.ArgumentParser(prog="merge-train agent",
                                 description="Agent-Hinweise (tasks/<KEY>-review-markers.json) einem GitLab-MR zuordnen und anzeigen; "
                                             "Gespräch mit dem Nutzer (feedback, antworten, horchen) – lokal und zu MRs")
    sub = ap.add_subparsers(dest="befehl")
    for name, hilfe in (("zeigen", "Datei beim MR anmelden, Zuordnung ausgeben und den MR im Browser öffnen"),
                        ("pruefen", "nur prüfen: auf welche Zeilen des MR-Stands die Hinweise fallen (Exit 1 bei Problemen)")):
        p = sub.add_parser(name, help=hilfe, description=hilfe)
        p.add_argument("datei", help="Hinweis-Datei (JSON)")
        p.set_defaults(aufruf=befehl_hinweise)
        p.add_argument("--mr", help="MR-URL, '!42' oder gruppe/projekt!42 (sonst Feld „mr“ oder der offene MR zu „branch“)")
        p.add_argument("--seit", nargs="?", const="", metavar="COMMIT",
                       help="Review-Update: Stand der Einträge seit COMMIT (ohne Wert: reviewed_commit der JSON)")
        p.add_argument("--als", help="wer die Hinweise geschrieben hat, wenn die JSON kein „agent“ nennt "
                                     "(Standard: aus der Umgebung erkannt)")
        if name == "zeigen":
            p.add_argument("--nicht-oeffnen", action="store_true", help="Browser nicht öffnen, nur URL ausgeben")
    gespraech = "Gespräch (Fragen/Feedback des Nutzers aus merge-train, lokal oder zu einem MR): "
    p = sub.add_parser("feedback", help="Gespräch: Fragen/Feedback des Nutzers abholen",
                       description=gespraech + "Fäden ausgeben, die auf eine Antwort warten (markiert sie als abgeholt)")
    p.add_argument("projekt", nargs="?", help="Projektordner, Name unter ~/Projects oder MR (Kennung/URL/gruppe/projekt!42); "
                                              "Standard: aktuelles Repo samt seinen MRs")
    p.add_argument("--alle", action="store_true", help="auch beantwortete Fäden zeigen")
    p.set_defaults(aufruf=befehl_feedback)
    p = sub.add_parser("antworten", help="Gespräch: auf einen Faden antworten",
                       description=gespraech + "auf einen Faden antworten; der Nutzer sieht die Antwort sofort in merge-train")
    p.add_argument("id", help="id des Fadens (aus „agent feedback“, Anfang genügt)")
    p.add_argument("text", nargs="?", default="", help="Antwort (Markdown-artig, mehrzeilig erlaubt); - = von stdin")
    p.add_argument("--erledigt", action="store_true", help="Faden als erledigt markieren (z. B. Wunsch umgesetzt)")
    p.add_argument("-p", "--projekt", help="Projekt oder MR (Standard: Faden in allen Gesprächen suchen)")
    p.add_argument("--als", help="Name, unter dem die Antwort erscheint (Standard: aus der Umgebung erkannt, sonst der gefragte Agent)")
    p.set_defaults(aufruf=befehl_antworten)
    p = sub.add_parser("kommentare", help="GitLab-Kommentare eines MR lesen (draft, staged/sent, Diskussionen)",
                       description="Alles, was am MR schon kommentiert ist: drafts (Agent-Hinweise), staged/sent "
                                   "Review-Kommentare und GitLab-Diskussionen, je mit Ort, Stufe, id und Text. Nur lesen, "
                                   "fragt GitLab nicht. Vor eigenen Anmerkungen aufrufen, damit nichts doppelt entsteht.")
    p.add_argument("projekt", nargs="?", help="MR (Kennung/URL/gruppe/projekt!42) oder Projektordner; Standard: die MRs des aktuellen Repos")
    p.set_defaults(aufruf=lambda o: print(kommentare_ausgeben(gespraech_ziele(o.projekt))) or 0)
    p = sub.add_parser("kommentar", help="GitLab-Kommentar umformulieren (draft ändern, sonst neuer draft)",
                       description="GitLab-Kommentar für den Nutzer umformulieren: h:<key> eines drafts (noch nicht übernommener "
                                   "Agent-Hinweis) ändert dessen text in der JSON; eine Kommentar-id (staged/sent) oder Faden-id legt "
                                   "einen neuen draft an derselben Stelle an (der alte bleibt). staged wird ein Kommentar nur, "
                                   "wenn der Nutzer ihn übernimmt. "
                                   "IDs zeigt „agent feedback“; Stufen siehe AGENTS.md.")
    p.add_argument("ziel", help="h:<key> (draft), Kommentar-id oder Faden-id (Anfang genügt)")
    p.add_argument("text", help="neuer Kommentartext; - = von stdin")
    p.add_argument("-p", "--projekt", help="MR (Standard: in allen MRs suchen)")
    p.add_argument("--als", help="wer den draft schreibt (Standard: aus der Umgebung erkannt, sonst Pflicht)")
    p.set_defaults(aufruf=befehl_kommentar)
    p = sub.add_parser("thread", help="Gespräch: neuen Thread anlegen (Hinweis, offene Frage, Zusammenfassung)",
                       description=gespraech + "Neuer Thread vom Agenten, an einer Code-Zeile oder allgemein (ohne --ort, z. B. die "
                                   "Zusammenfassung am Ende). Datei- und pfad:zeile-Angaben im Text werden auf der Seite zu "
                                   "Links. Antworten des Nutzers kommen wie sonst über feedback/horchen.")
    p.add_argument("text", help="Text (mehrzeilig erlaubt); - = von stdin")
    p.add_argument("--ort", metavar="PFAD[:ZEILE[-BIS]]",
                   help="Zeile oder Bereich im aktuellen Stand (lokal: Arbeitsstand bzw. Branch, MR: Klon); einmal je Thread")
    p.add_argument("--siehe", action="append", default=[], metavar="PFAD[:ZEILE[-BIS]][|LABEL]",
                   help="Siehe-auch-Link (mehrfach möglich)")
    p.add_argument("--vergleich", action="append", nargs=2, default=[], metavar=("A[:VON-BIS]", "B[:VON-BIS][|LABEL]"),
                   help="zwei Dateien (bzw. mit VON-BIS nur diese Bereiche) nebeneinander vergleichen (Popup); mehrfach möglich")
    p.add_argument("-p", "--projekt", help="Projekt oder MR (Standard: aktuelles Repo, lokal vor MR)")
    p.add_argument("--als", help="Name, unter dem der Thread erscheint (Standard: aus der Umgebung erkannt, sonst Pflicht)")
    p.set_defaults(aufruf=befehl_thread)
    p = sub.add_parser("vorfall", help="Bericht ablegen, wo merge-train in die Irre geführt hat (Meldung, Skill, CLI)",
                       description="Vorfall für die Entwicklung von merge-train ablegen: Situation, was passiert ist, "
                                   "Einordnung, Workaround, Wunsch. Landet im Eingang vorfaelle/ des merge-train-Klons "
                                   "(gitignored), siehe docs/vorfaelle/README.md dort.")
    p.add_argument("titel", help="kurzer Titel, z. B. „pruefen wählt bei fremdem Repo das falsche Projekt“")
    p.add_argument("text", help="Bericht (Markdown); - = von stdin")
    p.add_argument("--als", help="wer berichtet (Standard: aus der Umgebung erkannt)")
    p.set_defaults(aufruf=befehl_vorfall)
    p = sub.add_parser("horchen", help="Gespräch: auf neue Nachrichten warten",
                       description=gespraech + "warten, bis der Nutzer „An Agent senden“ drückt, dann wie „feedback“ ausgeben "
                                        "und beenden (im Hintergrund laufen lassen, danach neu starten)")
    p.add_argument("projekt", nargs="?", help="Projektordner, Name oder MR (Standard: aktuelles Repo samt seinen MRs)")
    p.add_argument("--als", help="Name, der auf der Seite als Zuhörer erscheint (Standard: aus der Umgebung erkannt, "
                                 "z. B. Claude in Claude Code; sonst Pflicht, z. B. \"Copilot (Claude Sonnet 4.5)\")")
    p.add_argument("--timeout", type=int, default=0, metavar="S", help="nach S Sekunden aufgeben (Exit 1)")
    p.set_defaults(aufruf=befehl_horchen)
    return ap


def befehl_feedback(o):
    print(faeden_abholen(gespraech_ziele(o.projekt), alle=o.alle, weg="feedback")[0]); return 0


def befehl_horchen(o):
    text, n = faeden_horchen(gespraech_ziele(o.projekt), o.timeout, agent_name(o.als))
    print(text); return 0 if n else 1


def text_von(o):
    """Text aus dem Argument, „-“ = von stdin."""
    return sys.stdin.read().strip() if o.text == "-" else o.text.strip()


def siehe_eintrag(angabe, diff=None):
    """--siehe/--vergleich „pfad[:zeile[-bis]][|label]“ → see_also-Eintrag wie in den Hinweis-Dateien."""
    angabe, _, label = angabe.partition("|")
    pfad, zeile, bis = ort_lesen(angabe)
    eintrag = {"path": pfad}
    if zeile:
        eintrag["line"] = zeile
    if bis:
        eintrag["end"] = bis
    if label.strip():
        eintrag["label"] = label.strip()
    if diff:
        eintrag["diff"] = diff.strip()
    return eintrag


def befehl_thread(o):
    siehe = [siehe_eintrag(x) for x in o.siehe] + [siehe_eintrag(b, a) for a, b in o.vergleich]
    print(faden_anlegen(gespraech_ziele(o.projekt), text_von(o), o.ort, siehe, o.als)[1]); return 0


def befehl_kommentar(o):
    print(kommentar_umformulieren(o.ziel, text_von(o), gespraech_ziele(o.projekt) if o.projekt else None, o.als)); return 0


def befehl_antworten(o):
    text = text_von(o)
    if not text and not o.erledigt:
        print("merge-train: Antworttext fehlt", file=sys.stderr); return 2
    fid, rest = faden_antworten(o.id, text, o.erledigt, o.als, gespraech_ziele(o.projekt) if o.projekt else None)
    print(f"[{fid}] beantwortet" + (" und erledigt" if o.erledigt else "")
          + (f" · {rest} weitere(r) wartet/warten noch" if rest else " · nichts mehr offen"))
    return 0


def hinweis_befund(h, geaendert):
    """Zeile der Ausgabe von „agent zeigen/pruefen“ für einen Hinweis → (befund, fehlt: zählt als Problem)."""
    fehlt = bool(not h["zeile"] and h["path"])
    if geaendert is not None and h["path"]:  # --seit
        if h["problem"] == "Datei nicht im MR-Stand":
            befund = "WEG: Datei gibt es nicht mehr → Diff gegen resolved_when prüfen"
        elif fehlt:
            befund = f'GEÄNDERT: {h["problem"]} → Diff gegen resolved_when prüfen'
        else:
            befund = "offen* (Datei geändert)" if h["path"] in geaendert else "offen (Datei unverändert)"
        fehlt = False
    elif not h["path"]:
        befund = "allgemeiner MR-Kommentar"
    elif h["im_diff"]:
        befund = "im Diff"
    elif h["zeile"]:
        befund = f'{h["problem"]} → wird allgemeiner Kommentar mit Link'
    else:
        befund = f'FEHLT: {h["problem"]}'
    if h["mehrfach"]:
        befund += f' (needle passt {h["mehrfach"]}×)'
    if h["status"] != "offen":
        befund += f' [{h["status"]}]'
    return befund, fehlt


def befehl_hinweise(o):
    """agent zeigen / agent pruefen: Hinweis-Datei einem MR zuordnen und die Zuordnung ausgeben."""
    pfad = os.path.abspath(o.datei)
    try:
        daten = hinweise_lesen(pfad)
    except (OSError, ValueError) as e:
        print(f"merge-train: {o.datei} nicht lesbar: {e}", file=sys.stderr); return 2
    try:
        mr, ordner = mr_fuer_hinweise(pfad, daten, o.mr)
        try:
            klon = remote_info(ordner)[1].lower() == (mr.projekt or "").lower()
        except Fehler:
            klon = False
        if klon:
            with akte_bearbeiten(mr) as akte:  # Repo der Hinweis-Datei als lokalen Klon merken (vor dem Seitenaufbau)
                akte["klon"] = ordner
        mr, meta = mr_meta_holen(mr)  # die einzige GitLab-Anfrage: aktuelle MR-Daten für die Seite merken
    except Fehler as e:
        print(f"merge-train: {e}", file=sys.stderr); return 2
    try:
        _, struktur, mr = mr_seite(mr)
    except Fehler as e:
        print(f"merge-train: {e}", file=sys.stderr); return 3
    vorstellen = None
    try:
        agent = str(daten.get("agent") or "").strip() or agent_name(o.als)
    except Fehler:
        agent, vorstellen = None, "Achtung: die JSON nennt kein „agent“ – auf der Seite steht dann nur „Agent“. " \
            "Feld \"agent\" (Harness und Modell) eintragen oder --als angeben."
    with akte_bearbeiten(mr) as akte:
        if o.befehl == "zeigen" and pfad not in akte["hinweis_dateien"]:
            akte["hinweis_dateien"].append(pfad)
        if agent and not daten.get("agent"):
            akte.setdefault("hinweis_agenten", {})[pfad] = agent
    head = struktur["refs"].get("head_sha") or ""
    geaendert, seit = None, None
    if o.seit is not None:
        seit = o.seit or str(daten.get("reviewed_commit") or "")
        if not seit:
            print("merge-train: --seit ohne Commit und kein reviewed_commit in der JSON", file=sys.stderr); return 2
        try:
            geaendert = geaenderte_dateien(mr, seit, head)
        except Fehler as e:
            print(f"merge-train: {e}", file=sys.stderr); return 2
    hinweise, _ = hinweise_aufloesen(mr, akte, struktur, nur=[pfad])
    print(f'{mr.projekt}!{mr.iid} · Stand {head[:8]} · {len(daten["markers"])} Einträge')
    print(f'Quelle: lokal ({kurzpfad(struktur["ordner"])})')
    gl_head = (meta.get("diff_refs") or {}).get("head_sha") or ""
    abweichend = stand_zu_gitlab(struktur["ordner"], meta.get("source_branch") or "", head, gl_head)
    if abweichend:
        print(f"Achtung: GitLab steht auf {gl_head[:8]}, der lokale Branch auf {head[:8]} – {STAND_TEXT[abweichend]}")
    if vorstellen:
        print(vorstellen)
    if geaendert is not None:
        print(f"seit {seit}: {len(geaendert)} Datei(en) geändert")
    schlecht = 0
    for h in hinweise:
        ort = f'{h["path"]}:{h["zeile"]}' if h["zeile"] else (h["path"] or "-")
        befund, fehlt = hinweis_befund(h, geaendert)
        schlecht += fehlt
        print(f'{h["finding"]:<5} {ort:<60} {befund}')
        for s in h["see_also"]:
            if s["problem"]:
                print(f'{"":<5}   siehe auch {s["path"] or "-"}: FEHLT: {s["problem"]}'); schlecht += 1
            elif s["warnung"]:
                print(f'{"":<5}   siehe auch {s["path"]}: Achtung: {s["warnung"]}')
    if o.befehl == "zeigen":
        im_browser("/mr/" + mr.id, nur_url=o.nicht_oeffnen)
    if schlecht:
        return 1
    return 3 if abweichend else 0


def agent_args(argv):
    """argv → (Parser, Namespace). Optionen gehen auch hinter den Positionsargumenten (antworten <id> --erledigt "…")."""
    ap = agent_parser()
    sub = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction))
    if argv and argv[0] in sub.choices:
        return ap, sub.choices[argv[0]].parse_intermixed_args(argv[1:], argparse.Namespace(befehl=argv[0]))
    return ap, ap.parse_args(argv)


def agent_main(argv):
    ap, o = agent_args(argv)
    if not o.befehl:
        ap.print_help(); return 2
    if o.aufruf is befehl_hinweise:  # meldet seine Fehler selbst (Exit 2 bzw. 3)
        return befehl_hinweise(o)
    try:
        return o.aufruf(o)
    except Fehler as e:
        print(f"merge-train: {e}", file=sys.stderr); return 2
