"""merge-train agent …: die Befehle für den Agenten (feedback, antworten, horchen, kommentar, thread, zeigen, pruefen)."""
import argparse, hashlib, json, os, re, subprocess, sys, time
from datetime import datetime
from .einstellungen import ARBEITSSTAND, BIS, KONF, SPERRE, ersetzen, jetzt, melden, projektname
from .git import git, inhalt, kurzpfad, projekt_ordner
from .zeilen import zeile_vorwaerts
from .diff_html import zeilenzahl
from .zustand import faeden_von, faden_status, review_datei, review_laden, review_speichern, review_kommentare, struktur_laden
from .gitlab import (GitLabFehler, enc, geaenderte_dateien, glab, ist_mr_ref, mr_aus_id, mr_id, mr_meta_holen,
    mr_ref, mr_vollstaendig, remote_info)
from .hinweise import hinweis_dateien, hinweise_aufloesen, hinweise_lesen, pfad_norm, see_also_aufloesen
from .seite import mr_seite
from .quellen import quelle
from .zuhoerer import SEITE_WEG_S, _prozess, agent_session, horcht_datei, seite_datei, todo_offen
from .review import review_daten
from .gespraech import alle_gespraeche, neue_nachricht
from .server import im_browser

def gespraech_ziele(name=None):
    """Welche Gespräche meint der Agent? MR-Kennung/URL → dieses; Projekt → dessen lokales Gespräch;
    ohne Angabe: das aktuelle Repo (lokales Gespräch und alle MRs mit diesem Klon). Rückgabe: Liste von Schlüsseln."""
    if name:
        mr = None
        try:
            mr = mr_aus_id(name)
        except GitLabFehler:
            if ist_mr_ref(name):
                mr = mr_ref(name, os.getcwd())
        if mr and not mr.get("lokal"):
            treffer = [g for g in alle_gespraeche() if not g.get("lokal") and g["projekt"] == mr["projekt"]
                       and g["iid"] == mr["iid"] and (not mr["host"] or g["host"] == mr["host"])]
            return treffer[:1] or [mr]
    ordner = name or os.getcwd()
    if name and not os.path.isdir(ordner):
        ordner = projekt_ordner(name)
    wurzel = (git(ordner, "rev-parse", "--show-toplevel", check=False) or "").strip() if os.path.isdir(ordner) else ""
    if not wurzel:
        raise GitLabFehler(f"kein Git-Repo und kein MR: {name or os.getcwd()}")
    ziele = [{"lokal": projektname(wurzel)}] if KONF["lokal"] else []
    echt = os.path.realpath(wurzel)
    for g in alle_gespraeche():
        if not g.get("lokal"):
            with SPERRE:
                struktur = struktur_laden(review_laden(g))
            if struktur and os.path.realpath(struktur["ordner"]) == echt:
                ziele.append(g)
    if not ziele:
        raise GitLabFehler(f"kein Gespräch zu {wurzel}")
    return ziele


def zeit_kurz(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m. %H:%M")
    except (TypeError, ValueError):
        return "?"


def faden_nachbarn(k, rv):
    """GitLab-Kommentare und Agent-Hinweise an der Zeile des Fadens (damit der Agent weiß, welchen er ändern soll)."""
    if not rv or not k.get("path"):
        return []
    da = lambda x: x.get("path") == k["path"] and ((k.get("b") and x.get("b") == k["b"]) or (not k.get("b") and k.get("a") and x.get("a") == k["a"]))
    out = []
    for x in rv["kommentare"]:
        if da(x) and x["status"] != "loeschen":
            out.append((f'GitLab-Kommentar {x["id"]}', K_STATUS.get(x["status"], x["status"]), x["text"]))
    for h in rv["hinweise"]:
        if da(h) and h["status"] == "offen":
            out.append((f'Agent-Hinweis h:{h["key"]}', f'draft, {h["quelle"]} {h["finding"]}'.strip(), h["text"]))
    return out


K_STATUS = {"neu": "staged", "geaendert": "staged, Änderung an einem gesendeten", "uebertragen": "sent",
            "weg": "sent, in GitLab veröffentlicht"}  # Stufen siehe AGENTS.md


def faden_ausgeben(k, wurzel, head, kontext=3, rv=None):
    """Ein Faden für den Agenten: Ort im aktuellen Stand, Code drumherum, GitLab-Kommentare/Hinweise dort, Verlauf."""
    von = (k.get("refs") or {}).get("head_sha") or head
    b = zeile_vorwaerts(wurzel, von, head, k["path"], k["b"]) if k.get("path") and k.get("b") else None
    ort = "allgemein" if not k.get("path") else \
        f'{k["path"]}:{b}' if b else (f'{k["path"]} (alte Seite, Zeile {k["a"]})' if k.get("a") and not k.get("b")
                                      else f'{k["path"]} (Zeile {k["b"]} hat sich seit dem Kommentar geändert)')
    an = f'  · an {k["an"]}' if k.get("an") else ""
    out = [f'── [{k["id"]}] {ort}{an}' + (f'  · {faden_status(k)}' if faden_status(k) != "wartet" else "")]
    if k.get("path") and b:
        t = inhalt(wurzel, head, k["path"]) or ""
        zeilen = t.split("\n")
        for i in range(max(1, b - kontext), min(len(zeilen), b + kontext) + 1):
            out.append(f'  {"→" if i == b else " "} {i:5} │ {zeilen[i - 1]}')
    elif k.get("zeile_text"):
        out.append(f'      damals │ {k["zeile_text"]}')
    for name, status, text in faden_nachbarn(k, rv):
        out.append(f'    an dieser Zeile: {name} ({status}):')
        out.append("      " + text.replace("\n", "\n      "))
    for m in k["nachrichten"]:
        if m.get("gesendet") or m["von"] == "claude":
            wer = "Nutzer" if m["von"] == "ich" else (m.get("wer") or k.get("an") or "Claude")
            text = m["text"].replace("\n", "\n      ")
            out.append(f'    {wer} ({zeit_kurz(m["gesendet"] or m["zeit"])}): {text}')
    return "\n".join(out)


def faeden_abholen(ziele, alle=False, markieren=True):
    """Text mit allen Fäden, die auf den Agenten warten (alle: auch beantwortete). Markiert Nachrichten als abgeholt."""
    teile, gesamt = [], 0
    for g in ziele:
        wurzel, head = quelle(g).ort(g)
        with SPERRE:
            st = review_laden(g)
            faeden = [k for k in faeden_von(st) if faden_status(k) != "entwurf" or any(m.get("gesendet") for m in k["nachrichten"])]
            zeigen = [k for k in faeden if alle or faden_status(k) == "wartet" or faden_ungelesen(k)]
            if markieren:
                for k in zeigen:
                    for m in k["nachrichten"]:
                        if m["von"] == "ich" and m.get("gesendet") and not m.get("abgeholt"):
                            m["abgeholt"] = jetzt()
                if zeigen:
                    review_speichern(g, st)
        wo = f"{BIS} {head[:8]}" if g.get("lokal") else f"MR {mr_id(g)} · Stand {head[:8]} · Klon {wurzel}"
        kopf = (f'merge-train · {quelle(g).name_von(g)} · {wo} · {sum(1 for k in faeden if faden_status(k) == "wartet")} '
                f'Gespräch(e) warten auf Antwort' + (f', {len(faeden)} insgesamt' if alle else ""))
        if not zeigen:
            if len(ziele) == 1:
                teile.append(kopf + "\n(nichts offen)")
            continue
        gesamt += len(zeigen)
        rv = None
        if quelle(g).kann["review"]:
            try:
                rv = review_daten(g)
            except GitLabFehler:
                pass
        teile += [kopf, ""] + [faden_ausgeben(k, wurzel, head, rv=rv) + "\n" for k in zeigen]
        teile.append("Code-Zeilen beziehen sich auf " + (("den Arbeitsstand (auch nicht Committetes); Wünsche dort umsetzen, "
                     "nicht committen." if BIS == ARBEITSSTAND else f"den aktuellen Stand von {BIS}.") if quelle(g).kann["committen"]
                     else f"den Stand {head[:8]} im Klon (nichts ändern, nur antworten).") + "\n")
    if gesamt:
        teile.append('Antworten: merge-train agent antworten <id> "Text"   (umgesetzt: --erledigt · Text von stdin: -)')
        if any(quelle(g).kann["review"] for g in ziele):
            teile.append('GitLab-Kommentar umformulieren: merge-train agent kommentar <h:key | Kommentar-id | Faden-id> "Text"')
    return "\n".join(teile) or "(nichts offen)", gesamt


def kommentar_umformulieren(ziel, text, ziele=None):
    """GitLab-Kommentar für den Nutzer umformulieren. h:<key> eines drafts (noch nicht übernommener Agent-Hinweis): dessen
    text in seiner JSON ändern. Sonst (staged/sent, übernommener/verworfener Hinweis, Faden): neuer draft an derselben
    Stelle. Review-Kommentare (staged) legt nur der Nutzer an („übernehmen“). Rückgabe: Meldung."""
    text = (text or "").strip()
    if not text:
        raise GitLabFehler("Kommentartext fehlt")
    ziel = ziel.strip()
    hkey = ziel[2:] if ziel.startswith("h:") else None
    passt = lambda i, z: i == z or (len(z) >= 4 and i.startswith(z))
    treffer = []
    for g in ziele or alle_gespraeche():
        if not quelle(g).kann["review"]:
            continue
        with SPERRE:
            st = review_laden(g)
        if hkey:
            try:
                rv = review_daten(g)
            except GitLabFehler:
                continue
            treffer += [(g, "h", h) for h in rv["hinweise"] if passt(h["key"], hkey)]
        else:
            treffer += [(g, "k", k) for k in review_kommentare(st) if passt(k["id"], ziel)]
            treffer += [(g, "f", k) for k in faeden_von(st) if passt(k["id"], ziel)]
    if not treffer:
        raise GitLabFehler(f"{ziel}: kein Agent-Hinweis, GitLab-Kommentar oder Faden in einem MR (merge-train agent feedback zeigt sie)")
    if len(treffer) > 1:
        raise GitLabFehler(f"{ziel} ist nicht eindeutig: " + ", ".join((x.get("key") or x["id"]) for _, _, x in treffer))
    g, art, x = treffer[0]
    if art == "h" and x["status"] == "offen":
        return hinweis_text_aendern(x, text)
    # staged/sent oder ein Faden: neuer draft (Agent-Hinweis) an derselben Stelle. staged wird ein Kommentar nur,
    # wenn der Nutzer auf „übernehmen“ klickt – der Agent legt nie selbst Review-Kommentare an.
    with SPERRE:
        st = review_laden(g)
        struktur = struktur_laden(st) or {}
    head = (struktur.get("refs") or {}).get("head_sha")
    path, b = x.get("path") or None, x.get("b")
    if path and b and art != "h" and head:  # Kommentar/Faden: Zeile auf den aktuellen MR-Stand umrechnen
        von = (x.get("refs") or {}).get("head_sha") or head
        b = zeile_vorwaerts(struktur.get("ordner"), von, head, path, b)
    m = {"text": text}
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
    # in die Review-JSON des MR: die des ersetzten Hinweises, sonst die erste
    datei = x.get("json") if art == "h" else None
    with SPERRE:
        st = review_laden(g)
    if not datei and art == "k" and x.get("hinweis"):
        datei = next((h.get("json") for h in review_daten(g)["hinweise"] if h["key"] == x["hinweis"]), None)
    datei = datei or next(iter(hinweis_dateien(g, st)), None)
    if not datei:
        raise GitLabFehler("Zu diesem MR gibt es keine Review-JSON (Agent-Hinweise) – den neuen Text im Faden vorschlagen")
    daten = json.load(open(datei, encoding="utf-8-sig"))
    (daten if isinstance(daten, list) else daten.setdefault("markers", [])).append(m)
    ersetzen(datei, json.dumps(daten, indent=2, ensure_ascii=False) + "\n")
    ort = f"{path}:{b}" if path and b else "allgemein"
    return (f"neuer Agent-Hinweis (draft) bei {ort} in {kurzpfad(datei)} – der Nutzer übernimmt oder verwirft ihn; "
            "der bisherige Kommentar bleibt unverändert")


def faden_anlegen(ziele, text, ort=None, siehe=(), als=None):
    """Neuer Faden vom Agenten (erste Nachricht von ihm, gesendet): an pfad:zeile oder allgemein (ort None). siehe: see_also-
    Einträge wie in der Review-JSON ("pfad:zeile-bis", {"path", "line", "end", "label", "diff"}). Rückgabe: (id, Meldung)."""
    text = (text or "").strip()
    if not text:
        raise GitLabFehler("Text fehlt")
    if len(ziele) > 1:
        lokal = [g for g in ziele if g.get("lokal")]
        if not lokal:
            raise GitLabFehler("mehrere MRs zu diesem Repo – mit -p den MR angeben: " + ", ".join(mr_id(g) for g in ziele))
        ziele = lokal[:1]
    g = ziele[0]
    wurzel, head = quelle(g).ort(g)
    k = {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:10], "refs": {"head_sha": head}, "erstellt": jetzt(),
         "path": None, "old_path": None, "a": None, "b": None, "nachrichten": [], "erledigt": None, "vom_agenten": True}
    if als:
        k["an"] = als
    if ort:
        m = re.fullmatch(r"(.+?)(?::(\d+))?", ort.strip())
        path = pfad_norm(m.group(1))
        t = inhalt(wurzel, head, path)
        if t is None:
            raise GitLabFehler(f"{path} gibt es im Stand {head[:8]} nicht")
        b = int(m.group(2)) if m.group(2) else None
        zeilen = t.split("\n")
        if b and not 1 <= b <= zeilenzahl(t):
            raise GitLabFehler(f"{path} hat keine Zeile {b} ({zeilenzahl(t)} Zeilen)")
        k.update(path=path, b=b, zeile_text=zeilen[b - 1] if b else None)
    sa = see_also_aufloesen(wurzel, head, list(siehe), None, k["path"])
    kaputt = [f'{s["path"] or "?"}: {s["problem"]}' for s in sa if s["problem"]]
    if kaputt:
        raise GitLabFehler("siehe auch: " + "; ".join(kaputt))
    if siehe:
        k["see_also"] = list(siehe)
    k["nachrichten"].append(neue_nachricht("claude", text, gesendet=True, wer=als))
    with SPERRE:
        st = review_laden(g)
        st["kommentare"].append(k)
        review_speichern(g, st)
    wo = f'{k["path"]}:{k["b"]}' if k["b"] else (k["path"] or "allgemein")
    melden(f"{quelle(g).name_von(g)}: {als or 'Claude'} hat einen Thread angelegt ({wo})")
    return k["id"], f'[{k["id"]}] Thread bei {wo} in {quelle(g).name_von(g)} angelegt'


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
        raise GitLabFehler(f"{pfad}: geänderte JSON wäre ungültig ({e}) – nichts geschrieben")
    ersetzen(pfad, neu_roh)
    return f'Agent-Hinweis (draft) {h["finding"] or h["key"]} geändert (text in {kurzpfad(pfad)})'


def faden_ungelesen(k):
    """Gesendete Nachrichten des Nutzers, die der Agent noch nicht abgeholt hat (auch nach einer Antwort nachgeschoben)."""
    return [m for m in k["nachrichten"] if m["von"] == "ich" and m.get("gesendet") and not m.get("abgeholt")]


def faden_antworten(fid, text, erledigt=False, als=None, ziele=None):
    """Antwort auf Faden fid (Anfang genügt) – gesucht in ziele, sonst in allen Gesprächen."""
    treffer = []
    for g in ziele or alle_gespraeche():
        with SPERRE:
            st = review_laden(g)
        treffer += [(g, k["id"]) for k in faeden_von(st) if k["id"] == fid or (len(fid) >= 4 and k["id"].startswith(fid))]
    if not treffer:
        raise GitLabFehler(f"Gespräch {fid} gibt es nicht (merge-train agent feedback --alle)")
    if len(treffer) > 1:
        raise GitLabFehler(f"{fid} ist nicht eindeutig: " + ", ".join(t[1] for t in treffer))
    g, kid = treffer[0]
    with SPERRE:
        st = review_laden(g)
        k = next(k for k in faeden_von(st) if k["id"] == kid)
        neu = faden_ungelesen(k)
        if neu:  # der Nutzer hat inzwischen nachgelegt: nicht blind abhaken
            raise GitLabFehler(f'In [{k["id"]}] gibt es {len(neu)} neue Nachricht(en), die du noch nicht gelesen hast – '
                               f'erst „merge-train agent feedback“, dann antworten:\n' +
                               "\n".join(f'    Nutzer ({zeit_kurz(m["gesendet"])}): {m["text"]}' for m in neu))
        wer = als or k.get("an") or None
        if text:
            k["nachrichten"].append(neue_nachricht("claude", text, gesendet=True, wer=wer))
        if erledigt:
            k["erledigt"] = {"von": "claude", "zeit": jetzt(), "wer": wer}
        review_speichern(g, st)
        rest = sum(1 for x in faeden_von(st) if faden_status(x) == "wartet")
        tid = st.get("todo_id")
    melden(f"{quelle(g).name_von(g)}: {wer or 'Claude'} hat geantwortet" + (" (erledigt)" if erledigt else ""))
    if not rest and todo_offen(tid):
        subprocess.run(["todo", "erledigt", tid, "-n", "Alle Fragen/Feedback in merge-train beantwortet"], capture_output=True)
    return k["id"], rest


def faeden_horchen(ziele, timeout=0, als=None):
    """Warten, bis neue (noch nicht abgeholte) Nachrichten da sind, dann ausgeben. Rückgabe (text, anzahl)."""
    import atexit, signal, time
    dateien = [horcht_datei(g) for g in ziele]
    for d in dateien:
        ersetzen(d, f"{os.getpid()} {jetzt()} {als or 'Claude'}\n")
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
    pfade = [review_datei(g) for g in ziele]
    zuletzt = None
    session = agent_session(os.getpid())  # endet die Agenten-Session, hört auch horchen auf
    start, gesehen = time.time(), False
    seiten = [seite_datei(g) for g in ziele]
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
            for g in ziele:
                with SPERRE:
                    st = review_laden(g)
                if any(n["von"] == "ich" and n.get("gesendet") and not n.get("abgeholt")
                       for k in faeden_von(st) for n in k["nachrichten"]):
                    neu.append(g)
            if neu:
                return faeden_abholen(neu)
        time.sleep(1)
    return "merge-train: keine neuen Nachrichten (Zeit abgelaufen)", 0


def mr_fuer_hinweise(pfad, daten, ref=None):
    """Zu welchem MR gehört die Hinweis-Datei? --mr, sonst Feld „mr“, sonst offener MR des Branches."""
    ordner = (git(os.path.dirname(pfad), "rev-parse", "--show-toplevel", check=False) or "").strip() \
        or os.path.dirname(pfad)
    ref = ref or daten.get("mr")
    if ref:
        mr = mr_vollstaendig(mr_ref(str(ref), ordner))
    else:
        branch = daten.get("branch")
        if not branch:
            raise GitLabFehler("kein MR zuzuordnen: --mr angeben oder „branch“/„mr“ in die JSON schreiben")
        host, projekt = remote_info(ordner)
        lst = glab(host, f"projects/{enc(projekt)}/merge_requests?state=opened&source_branch={enc(branch)}")
        if not lst:
            raise GitLabFehler(f"kein offener MR für Branch {branch} in {projekt} – --mr angeben")
        mr = mr_ref(lst[0]["web_url"])
        mr["host"] = mr["host"] or host
    return mr, ordner


def agent_main(argv):
    ap = argparse.ArgumentParser(prog="merge-train agent",
                                 description="Agent-Hinweise (tasks/<KEY>-review-markers.json) einem GitLab-MR zuordnen und anzeigen; "
                                             "Gespräch mit dem Nutzer (feedback, antworten, horchen) – lokal und zu MRs")
    sub = ap.add_subparsers(dest="befehl")
    for name, hilfe in (("zeigen", "Datei beim MR anmelden, Zuordnung ausgeben und den MR im Browser öffnen"),
                        ("pruefen", "nur prüfen: auf welche Zeilen des MR-Stands die Hinweise fallen (Exit 1 bei Problemen)")):
        p = sub.add_parser(name, help=hilfe, description=hilfe)
        p.add_argument("datei", help="Hinweis-Datei (JSON)")
        p.add_argument("--mr", help="MR-URL, '!42' oder gruppe/projekt!42 (sonst Feld „mr“ oder der offene MR zu „branch“)")
        p.add_argument("--seit", nargs="?", const="", metavar="COMMIT",
                       help="Review-Update: Stand der Einträge seit COMMIT (ohne Wert: reviewed_commit der JSON)")
        if name == "zeigen":
            p.add_argument("--nicht-oeffnen", action="store_true", help="Browser nicht öffnen, nur URL ausgeben")
    gs = "Gespräch (Fragen/Feedback des Nutzers aus merge-train, lokal oder zu einem MR): "
    p = sub.add_parser("feedback", help="Gespräch: Fragen/Feedback des Nutzers abholen",
                       description=gs + "Fäden ausgeben, die auf eine Antwort warten (markiert sie als abgeholt)")
    p.add_argument("projekt", nargs="?", help="Projektordner, Name unter ~/Projects oder MR (Kennung/URL/gruppe/projekt!42); "
                                              "Standard: aktuelles Repo samt seinen MRs")
    p.add_argument("--alle", action="store_true", help="auch beantwortete Fäden zeigen")
    p = sub.add_parser("antworten", help="Gespräch: auf einen Faden antworten",
                       description=gs + "auf einen Faden antworten; der Nutzer sieht die Antwort sofort in merge-train")
    p.add_argument("id", help="id des Fadens (aus „agent feedback“, Anfang genügt)")
    p.add_argument("text", nargs="?", default="", help="Antwort (Markdown-artig, mehrzeilig erlaubt); - = von stdin")
    p.add_argument("--erledigt", action="store_true", help="Faden als erledigt markieren (z. B. Wunsch umgesetzt)")
    p.add_argument("-p", "--projekt", help="Projekt oder MR (Standard: Faden in allen Gesprächen suchen)")
    p.add_argument("--als", help="Name, unter dem die Antwort erscheint (Standard: der gefragte Agent)")
    p = sub.add_parser("kommentar", help="GitLab-Kommentar umformulieren (draft ändern, sonst neuer draft)",
                       description="GitLab-Kommentar für den Nutzer umformulieren: h:<key> eines drafts (noch nicht übernommener "
                                   "Agent-Hinweis) ändert dessen text in der JSON; eine Kommentar-id (staged/sent) oder Faden-id legt "
                                   "einen neuen draft an derselben Stelle an (der alte bleibt). staged wird ein Kommentar nur, "
                                   "wenn der Nutzer ihn übernimmt. "
                                   "IDs zeigt „agent feedback“; Stufen siehe AGENTS.md.")
    p.add_argument("ziel", help="h:<key> (draft), Kommentar-id oder Faden-id (Anfang genügt)")
    p.add_argument("text", help="neuer Kommentartext; - = von stdin")
    p.add_argument("-p", "--projekt", help="MR (Standard: in allen MRs suchen)")
    p = sub.add_parser("thread", help="Gespräch: neuen Thread anlegen (Hinweis, offene Frage, Zusammenfassung)",
                       description=gs + "Neuer Thread vom Agenten, an einer Code-Zeile oder allgemein (ohne --ort, z. B. die "
                                   "Zusammenfassung am Ende). Datei- und pfad:zeile-Angaben im Text werden auf der Seite zu "
                                   "Links. Antworten des Nutzers kommen wie sonst über feedback/horchen.")
    p.add_argument("text", help="Text (mehrzeilig erlaubt); - = von stdin")
    p.add_argument("--ort", metavar="PFAD[:ZEILE]", help="Zeile im aktuellen Stand (lokal: Arbeitsstand bzw. Branch, MR: Klon)")
    p.add_argument("--siehe", action="append", default=[], metavar="PFAD[:ZEILE[-BIS]][|LABEL]",
                   help="Siehe-auch-Link (mehrfach möglich)")
    p.add_argument("--vergleich", action="append", nargs=2, default=[], metavar=("A", "B[|LABEL]"),
                   help="zwei Dateien nebeneinander vergleichen (Popup); mehrfach möglich")
    p.add_argument("-p", "--projekt", help="Projekt oder MR (Standard: aktuelles Repo, lokal vor MR)")
    p.add_argument("--als", help="Name, unter dem der Thread erscheint (Standard: Claude)")
    p = sub.add_parser("horchen", help="Gespräch: auf neue Nachrichten warten",
                       description=gs + "warten, bis der Nutzer „Feedback senden“ drückt, dann wie „feedback“ ausgeben "
                                        "und beenden (im Hintergrund laufen lassen, danach neu starten)")
    p.add_argument("projekt", nargs="?", help="Projektordner, Name oder MR (Standard: aktuelles Repo samt seinen MRs)")
    p.add_argument("--als", default="Claude", help="Name, der auf der Seite als Zuhörer erscheint (z. B. Copilot)")
    p.add_argument("--timeout", type=int, default=0, metavar="S", help="nach S Sekunden aufgeben (Exit 1)")
    o = ap.parse_args(argv)
    if not o.befehl:
        ap.print_help(); return 2
    if o.befehl in ("feedback", "antworten", "horchen", "kommentar", "thread"):
        try:
            if o.befehl == "feedback":
                text, _ = faeden_abholen(gespraech_ziele(o.projekt), alle=o.alle)
                print(text); return 0
            if o.befehl == "horchen":
                text, n = faeden_horchen(gespraech_ziele(o.projekt), o.timeout, o.als)
                print(text); return 0 if n else 1
            text = sys.stdin.read().strip() if o.text == "-" else o.text.strip()
            if o.befehl == "thread":
                def eintrag(x, diff=None):
                    x, _, label = x.partition("|")
                    m = re.fullmatch(r"(.+?)(?::(\d+)(?:-(\d+))?)?", x.strip())
                    e = {"path": m.group(1)}
                    if m.group(2):
                        e["line"] = int(m.group(2))
                    if m.group(3):
                        e["end"] = int(m.group(3))
                    if label.strip():
                        e["label"] = label.strip()
                    if diff:
                        e["diff"] = diff.strip()
                    return e
                siehe = [eintrag(x) for x in o.siehe] + [eintrag(b, a) for a, b in o.vergleich]
                print(faden_anlegen(gespraech_ziele(o.projekt), text, o.ort, siehe, o.als)[1]); return 0
            if o.befehl == "kommentar":
                print(kommentar_umformulieren(o.ziel, text, gespraech_ziele(o.projekt) if o.projekt else None)); return 0
            if not text and not o.erledigt:
                print("merge-train: Antworttext fehlt", file=sys.stderr); return 2
            fid, rest = faden_antworten(o.id, text, o.erledigt, o.als, gespraech_ziele(o.projekt) if o.projekt else None)
            print(f"[{fid}] beantwortet" + (" und erledigt" if o.erledigt else "")
                  + (f" · {rest} weitere(r) wartet/warten noch" if rest else " · nichts mehr offen"))
            return 0
        except GitLabFehler as e:
            print(f"merge-train: {e}", file=sys.stderr); return 2
    pfad = os.path.abspath(o.datei)
    try:
        daten = hinweise_lesen(pfad)
    except (OSError, ValueError) as e:
        print(f"merge-train: {o.datei} nicht lesbar: {e}", file=sys.stderr); return 2
    try:
        mr, ordner = mr_fuer_hinweise(pfad, daten, o.mr)
        with SPERRE:  # Repo der Hinweis-Datei als lokalen Klon merken (vor dem Seitenaufbau)
            st = review_laden(mr)
            try:
                if remote_info(ordner)[1].lower() == (mr["projekt"] or "").lower() and st.get("klon") != ordner:
                    st["klon"] = ordner; review_speichern(mr, st)
            except GitLabFehler:
                pass
        mr, meta = mr_meta_holen(mr)  # die einzige GitLab-Anfrage: aktuelle MR-Daten für die Seite merken
    except GitLabFehler as e:
        print(f"merge-train: {e}", file=sys.stderr); return 2
    try:
        _, struktur, mr = mr_seite(mr)
    except GitLabFehler as e:
        print(f"merge-train: {e}", file=sys.stderr); return 3
    with SPERRE:
        st = review_laden(mr)
        if o.befehl == "zeigen" and pfad not in st["hinweis_dateien"]:
            st["hinweis_dateien"].append(pfad)
            review_speichern(mr, st)
    head = struktur["refs"].get("head_sha") or ""
    geaendert, seit = None, None
    if o.seit is not None:
        seit = o.seit or str(daten.get("reviewed_commit") or "")
        if not seit:
            print("merge-train: --seit ohne Commit und kein reviewed_commit in der JSON", file=sys.stderr); return 2
        try:
            geaendert = geaenderte_dateien(mr, seit, head)
        except GitLabFehler as e:
            print(f"merge-train: {e}", file=sys.stderr); return 2
    hinweise, _ = hinweise_aufloesen(mr, st, struktur, nur=[pfad])
    print(f'{mr["projekt"]}!{mr["iid"]} · Stand {head[:8]} · {len(daten["markers"])} Einträge')
    print(f'Quelle: lokal ({kurzpfad(struktur["ordner"])})')
    gl_head = (meta.get("diff_refs") or {}).get("head_sha") or ""
    abweichend = gl_head and gl_head != head
    if abweichend:
        print(f"Achtung: GitLab steht auf {gl_head[:8]}, der lokale Branch auf {head[:8]} – Branch aktualisieren")
    if geaendert is not None:
        print(f"seit {seit}: {len(geaendert)} Datei(en) geändert")
    schlecht = 0
    for h in hinweise:
        ort = f'{h["path"]}:{h["zeile"]}' if h["zeile"] else (h["path"] or "-")
        fehlt = not h["zeile"] and h["path"]
        if geaendert is not None and h["path"]:
            if h["problem"] == "Datei nicht im MR-Stand":
                zustand = "WEG: Datei gibt es nicht mehr → Diff gegen resolved_when prüfen"
            elif fehlt:
                zustand = f'GEÄNDERT: {h["problem"]} → Diff gegen resolved_when prüfen'
            else:
                zustand = "offen* (Datei geändert)" if h["path"] in geaendert else "offen (Datei unverändert)"
            fehlt = False
        elif not h["path"]:
            zustand = "allgemeiner MR-Kommentar"
        elif h["im_diff"]:
            zustand = "im Diff"
        elif h["zeile"]:
            zustand = f'{h["problem"]} → wird allgemeiner Kommentar mit Link'
        else:
            zustand = f'FEHLT: {h["problem"]}'
        schlecht += bool(fehlt)
        if h["mehrfach"]:
            zustand += f' (needle passt {h["mehrfach"]}×)'
        if h["status"] != "offen":
            zustand += f' [{h["status"]}]'
        print(f'{h["finding"]:<5} {ort:<60} {zustand}')
        for s in h["see_also"]:
            if s["problem"]:
                print(f'{"":<5}   siehe auch {s["path"] or "-"}: FEHLT: {s["problem"]}'); schlecht += 1
    if o.befehl == "zeigen":
        im_browser("/mr/" + mr_id(mr), nur_url=o.nicht_oeffnen)
    if schlecht:
        return 1
    return 3 if abweichend else 0
