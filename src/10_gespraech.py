# ---------------------------------------------------------------- Gespräch (Fragen und Feedback an den Agenten)
# Im lokalen Projekt-Diff wird aus einem Kommentar ein Gesprächsfaden: der Nutzer schreibt (Entwurf), „Feedback senden“
# schickt alle Entwürfe ab, der Agent holt sie mit „merge-train agent feedback“ ab und antwortet mit „agent antworten“.
# Im GitLab-Modus genauso, aber nur für Kommentare, die „an <Agent>“ gespeichert werden; sie liegen getrennt vom Review
# (DATEN/gespraech/<mr>.json) und gehen nie nach GitLab. Gesprächs-Schlüssel g: {"lokal": projekt} oder gk(mr).
# Zustand: gleiche Form wie bei MRs (kommentare mit path/a/b, refs des Stands beim Schreiben), je Faden
# „nachrichten“: [{id, von: ich|claude, wer, text, zeit, gesendet, abgeholt}], „erledigt“: {von, zeit} oder None, „an“.
# Wer zuhört: „agent horchen“ legt <zustand>.horcht an (pid, Name). Hört niemand zu, startet „Feedback senden“ den
# Agenten aus [agenten] bzw. feedback_befehl – oder legt einen todo-Eintrag an („Session starten“ öffnet ihn).

def jetzt():
    return datetime.now().isoformat(timespec="seconds")

def g_status(k):
    """entwurf (ungesendete eigene Nachricht) | wartet (auf den Agenten) | antwort (Agent hat zuletzt geschrieben) | erledigt"""
    n = k.get("nachrichten") or []
    if any(m["von"] == "ich" and not m.get("gesendet") for m in n):
        return "entwurf"
    if k.get("erledigt"):
        return "erledigt"
    gesendet = [m for m in n if m.get("gesendet")]
    return "antwort" if gesendet and gesendet[-1]["von"] == "claude" else "wartet"

def g_faeden(st):
    return [k for k in st["kommentare"] if k.get("nachrichten") is not None and not k.get("archiv")]

_VORWAERTS = {}

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

def g_wurzel(projekt):
    return next((r for r in finde_repos() if projektname(r) == projekt), None)

def gk(mr):
    """Gesprächs-Schlüssel: lokales Projekt bleibt, ein MR bekommt seine eigene Gesprächsdatei."""
    if mr.get("lokal"):
        return {"lokal": mr["lokal"]}
    return {"gespraech": True, "host": mr["host"], "projekt": mr["projekt"], "iid": mr["iid"]}

def g_mr(g):
    return {"host": g["host"], "projekt": g["projekt"], "iid": g["iid"]}

def g_name(g):
    return g["lokal"] if g.get("lokal") else f'{g["projekt"]}!{g["iid"]}'

def g_ort(g):
    """(ordner, head) des Stands, auf den sich die Zeilen beziehen: lokal der Branch BIS, beim MR der Stand der Seite."""
    if g.get("lokal"):
        wurzel = g_wurzel(g["lokal"])
        if not wurzel:
            raise GitLabFehler(f'Projekt {g["lokal"]} nicht gefunden')
        head = (git(wurzel, "rev-parse", "--verify", "-q", BIS, check=False) or "").strip()
        if not head:
            raise GitLabFehler(f"Branch {BIS} fehlt in {wurzel}")
        return wurzel, head
    with SPERRE:
        struktur = struktur_laden(review_laden(g))
    if struktur is None:
        _, struktur, _ = mr_seite(g_mr(g))
    return struktur["ordner"], struktur["refs"]["head_sha"]

def g_agenten(g):
    """Namen, an die man im GitLab-Modus fragen kann: eingerichtete [agenten] und wer gerade zuhört."""
    namen = list(KONF.get("agenten") or {})
    wer = horcht(g)
    return namen + ([wer] if wer and wer not in namen else [])

def g_daten(mr, ansicht=None):
    """Wie review_daten, für ein Gespräch: Fäden auf den Stand der Seite umgerechnet."""
    with SPERRE:
        st = review_laden(mr)
    struktur = struktur_laden(st)
    if struktur is None:
        if mr.get("lokal"):
            wurzel = g_wurzel(mr["lokal"])
            if not wurzel:
                return {"ok": False, "text": f'Projekt {mr["lokal"]} nicht gefunden'}
            _, struktur = projekt_seite(wurzel)
        else:
            _, struktur, _ = mr_seite(g_mr(mr))
    head = struktur["refs"]["head_sha"]
    kom = []
    for k in g_faeden(st):
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
                    "problem": unter, "zeile_text": k.get("zeile_text"), "status": g_status(k),
                    "nachrichten": k["nachrichten"], "erledigt": k.get("erledigt"), "an": k.get("an") or "Claude"})
    ausserhalb = 0
    if ansicht:
        ans_st = ansicht_struktur(struktur, ansicht)
        vorher = len(kom)
        kom = ansicht_zuordnen(struktur, ans_st, kom)
        ausserhalb = vorher - len(kom)
    entwuerfe = sum(1 for k in g_faeden(st) for m in k["nachrichten"] if m["von"] == "ich" and not m.get("gesendet"))
    return {"ok": True, "lokal": True, "kommentare": kom, "hinweise": [], "quellen": [], "stand": stand(mr, st),
            "ausstehend": entwuerfe, "ausserhalb": ausserhalb, "horcht": horcht(mr), "agenten": g_agenten(mr),
            "todo": st.get("todo_id") if todo_offen(st.get("todo_id")) else None}

def g_nachricht(von, text, gesendet=False, wer=None):
    m = {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:8], "von": von, "text": text, "zeit": jetzt(),
         "gesendet": jetzt() if gesendet else None}
    if wer:
        m["wer"] = wer
    return m

def g_aktion(mr, d):
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
                 "nachrichten": [g_nachricht("ich", text)], "erledigt": None}
            if d.get("an"):
                k["an"] = str(d["an"])[:40]
            if d.get("datei") is not None:
                fehler, ort = zeile_aus_klick(struktur, d, ansicht)
                if fehler:
                    return False, fehler.replace("Der MR hat", "Das Projekt hat") if mr.get("lokal") else fehler
                k.update(ort)
                if ort["b"]:
                    t = inhalt(struktur["ordner"], struktur["refs"]["head_sha"], ort["path"]) or ""
                    zeilen = t.split("\n")
                    k["zeile_text"] = zeilen[ort["b"] - 1] if ort["b"] <= len(zeilen) else None
            st["kommentare"].append(k)
            review_speichern(mr, st)
            return True, ""
        k = next((k for k in g_faeden(st) if k["id"] == d.get("id")), None)
        if not k:
            return False, "Gespräch nicht gefunden – Seite neu laden"
        m = next((m for m in k["nachrichten"] if m["id"] == d.get("nid")), None) if d.get("nid") else None
        if d.get("nid") and (not m or m["von"] != "ich" or m.get("gesendet")):
            return False, "Nur eigene, noch nicht gesendete Nachrichten lassen sich ändern"
        if aktion == "antworten":
            if not text:
                return False, "leere Nachricht"
            k["nachrichten"].append(g_nachricht("ich", text))
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

# ---- Wer bekommt das Feedback?

def horcht_datei(g):
    return review_datei(g)[:-5] + ".horcht"

def horcht(g):
    """Name der Session, die gerade mit „agent horchen“ zuhört (Standard „Claude“), sonst None."""
    try:
        teile = open(horcht_datei(g)).read().split()
        os.kill(int(teile[0]), 0)
        return " ".join(teile[2:]) or "Claude"
    except (OSError, ValueError, IndexError):
        return None

def todo_offen(tid):
    if not tid:
        return False
    basis = os.environ.get("TODO_DIR") or os.path.expanduser("~/todo")
    return os.path.exists(os.path.join(basis, "offen", tid + ".md"))

def g_prompt(g, wurzel=""):
    if g.get("lokal"):
        projekt = g["lokal"]
        return (f"In merge-train liegen Fragen bzw. Feedback des Nutzers zum Code von {projekt} (Diff {BIS} gegen {VON}). "
                f"Hol sie mit `merge-train agent feedback` ab. Fragen beantworten, Änderungswünsche auf {BIS} umsetzen und "
                f"committen; zu jedem Faden mit `merge-train agent antworten <id> \"…\"` antworten (umgesetzt: --erledigt). "
                f"Danach mit `merge-train agent horchen` im Hintergrund auf weitere Nachrichten warten.")
    z = mr_id(g_mr(g))
    return (f"In merge-train liegen Fragen des Nutzers zum Merge-Request {g_name(g)} (lokaler Klon: {wurzel}). "
            f"Hol sie mit `merge-train agent feedback {z}` ab. Beantworte sie anhand des Codes im Klon; den MR nicht "
            f"ändern, nichts committen oder pushen. Zu jedem Faden mit `merge-train agent antworten <id> \"…\"` antworten. "
            f"Danach mit `merge-train agent horchen {z}` (im Hintergrund, nach jeder Ausgabe neu) auf weitere Fragen warten.")

def benachrichtigen(g, wurzel, n, namen=("Claude",)):
    """Nach „Feedback senden“: Session, die zuhört → nichts weiter; sonst Agent aus [agenten], feedback_befehl oder
    todo-Eintrag. Rückgabe (text für die Seite, todo_id oder None)."""
    wer = horcht(g)
    if wer:
        return f"an die Session übergeben, die zuhört ({wer})", None
    projekt = g_name(g)
    prompt = g_prompt(g, wurzel)
    agenten = KONF.get("agenten") or {}
    befehle = [(nm, agenten[nm]) for nm in namen if nm in agenten]
    if not befehle and KONF.get("feedback_befehl"):
        befehle = [("Claude", KONF["feedback_befehl"])]
    if befehle:
        gestartet = []
        for nm, befehl in befehle:
            argv = [a.format(ordner=wurzel, projekt=projekt, prompt=prompt) for a in shlex.split(befehl)]
            try:
                subprocess.Popen(argv, cwd=wurzel, start_new_session=True, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                gestartet.append(nm)
            except OSError as e:
                return f"{nm} startet nicht: {e}", None
        return " und ".join(gestartet) + " gestartet", None
    if not shutil.which("todo"):
        return f"Keine Session hört zu – in einer Agent-Session „merge-train agent feedback{'' if g.get('lokal') else ' ' + mr_id(g_mr(g))}“ sagen", None
    with SPERRE:
        tid = review_laden(g).get("todo_id")
    zeile = f"{n} neue Nachricht(en) um {datetime.now().strftime('%H:%M')}"
    if todo_offen(tid):
        subprocess.run(["todo", "notiz", tid, zeile, "--von", "merge-train"], capture_output=True)
    else:
        r = subprocess.run(["todo", "neu", f"merge-train: Fragen/Feedback zu {projekt}", "-p", wurzel,
                            "--von", "merge-train", "-n", "Aus merge-train „Feedback senden“. " + zeile, "--prompt", prompt],
                           capture_output=True, text=True)
        tid = (r.stdout.strip().splitlines() or [""])[-1].strip() if r.returncode == 0 else None
        if not tid:
            return f"todo-Eintrag ließ sich nicht anlegen: {(r.stderr or r.stdout).strip()[:200]}", None
        with SPERRE:
            st = review_laden(g); st["todo_id"] = tid; review_speichern(g, st)
    subprocess.run(["todo", "heute", tid, "-t", f"Fragen/Feedback aus merge-train ({zeile})"], capture_output=True)
    return "Keine Session hört zu – als todo eingetragen (Panel), „▶ Session starten“ öffnet sie", tid

def feedback_senden(g):
    """Alle Entwürfe abschicken. Rückgabe (ok, text, todo_id)."""
    try:
        wurzel, _ = g_ort(g)
    except GitLabFehler as e:
        return False, str(e), None
    with SPERRE:
        st = review_laden(g)
        n, namen = 0, []
        for k in g_faeden(st):
            for m in k["nachrichten"]:
                if m["von"] == "ich" and not m.get("gesendet"):
                    m["gesendet"] = jetzt(); n += 1
                    if (k.get("an") or "Claude") not in namen:
                        namen.append(k.get("an") or "Claude")
        if not n:
            return False, "Keine Entwürfe zum Senden", None
        review_speichern(g, st)
    text, tid = benachrichtigen(g, wurzel, n, namen)
    return True, f"{n} Nachricht(en) gesendet · {text}", tid

def session_starten(g):
    with SPERRE:
        tid = review_laden(g).get("todo_id")
    if not todo_offen(tid):
        return False, "Kein offener todo-Eintrag"
    r = subprocess.run(["todo", "los", tid], capture_output=True, text=True)
    return (True, "Konsole geöffnet – Enter startet Claude") if r.returncode == 0 else \
        (False, f"todo los: {(r.stderr or r.stdout).strip()[:200]}")

# ---- Agent-Seite (CLI)

def g_alle():
    """Alle Gespräche (lokale Projekte und MRs) → Liste von Schlüsseln."""
    out = []
    for unter in ("lokal", "gespraech"):
        for p in glob.glob(os.path.join(DATEN, unter, "*.json")):
            try:
                m = json.load(open(p, encoding="utf-8")).get("mr") or {}
            except (OSError, ValueError):
                continue
            if m.get("lokal") or m.get("gespraech"):
                out.append(gk(m) if m.get("lokal") else m)
    return out

def g_ziele(name=None):
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
            treffer = [g for g in g_alle() if g.get("gespraech") and g["projekt"] == mr["projekt"]
                       and g["iid"] == mr["iid"] and (not mr["host"] or g["host"] == mr["host"])]
            return treffer[:1] or [gk(mr)]
    ordner = name or os.getcwd()
    if name and not os.path.isdir(ordner):
        ordner = os.path.join(PROJEKTE, name)
    wurzel = (git(ordner, "rev-parse", "--show-toplevel", check=False) or "").strip() if os.path.isdir(ordner) else ""
    if not wurzel:
        raise GitLabFehler(f"kein Git-Repo und kein MR: {name or os.getcwd()}")
    ziele = [{"lokal": projektname(wurzel)}] if KONF["lokal"] else []
    echt = os.path.realpath(wurzel)
    for g in g_alle():
        if g.get("gespraech"):
            with SPERRE:
                struktur = struktur_laden(review_laden(g))
            if struktur and os.path.realpath(struktur["ordner"]) == echt:
                ziele.append(g)
    if not ziele:
        raise GitLabFehler(f"kein Gespräch zu {wurzel}")
    return ziele

def g_zeit(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m. %H:%M")
    except (TypeError, ValueError):
        return "?"

def g_ausgeben(k, wurzel, head, kontext=3):
    """Ein Faden für den Agenten: Ort im aktuellen Stand, Code drumherum, Verlauf."""
    von = (k.get("refs") or {}).get("head_sha") or head
    b = zeile_vorwaerts(wurzel, von, head, k["path"], k["b"]) if k.get("path") and k.get("b") else None
    ort = "allgemein" if not k.get("path") else \
        f'{k["path"]}:{b}' if b else (f'{k["path"]} (alte Seite, Zeile {k["a"]})' if k.get("a") and not k.get("b")
                                      else f'{k["path"]} (Zeile {k["b"]} hat sich seit dem Kommentar geändert)')
    an = f'  · an {k["an"]}' if k.get("an") else ""
    out = [f'── [{k["id"]}] {ort}{an}' + (f'  · {g_status(k)}' if g_status(k) != "wartet" else "")]
    if k.get("path") and b:
        t = inhalt(wurzel, head, k["path"]) or ""
        zeilen = t.split("\n")
        for i in range(max(1, b - kontext), min(len(zeilen), b + kontext) + 1):
            out.append(f'  {"→" if i == b else " "} {i:5} │ {zeilen[i - 1]}')
    elif k.get("zeile_text"):
        out.append(f'      damals │ {k["zeile_text"]}')
    for m in k["nachrichten"]:
        if m.get("gesendet") or m["von"] == "claude":
            wer = "Nutzer" if m["von"] == "ich" else (m.get("wer") or k.get("an") or "Claude")
            text = m["text"].replace("\n", "\n      ")
            out.append(f'    {wer} ({g_zeit(m["gesendet"] or m["zeit"])}): {text}')
    return "\n".join(out)

def g_abholen(ziele, alle=False, markieren=True):
    """Text mit allen Fäden, die auf den Agenten warten (alle: auch beantwortete). Markiert Nachrichten als abgeholt."""
    teile, gesamt = [], 0
    for g in ziele:
        wurzel, head = g_ort(g)
        with SPERRE:
            st = review_laden(g)
            faeden = [k for k in g_faeden(st) if g_status(k) != "entwurf" or any(m.get("gesendet") for m in k["nachrichten"])]
            zeigen = [k for k in faeden if alle or g_status(k) == "wartet" or g_ungelesen(k)]
            if markieren:
                for k in zeigen:
                    for m in k["nachrichten"]:
                        if m["von"] == "ich" and m.get("gesendet") and not m.get("abgeholt"):
                            m["abgeholt"] = jetzt()
                if zeigen:
                    review_speichern(g, st)
        wo = f"{BIS} {head[:8]}" if g.get("lokal") else f"MR {mr_id(g_mr(g))} · Stand {head[:8]} · Klon {wurzel}"
        kopf = (f'merge-train · {g_name(g)} · {wo} · {sum(1 for k in faeden if g_status(k) == "wartet")} '
                f'Gespräch(e) warten auf Antwort' + (f', {len(faeden)} insgesamt' if alle else ""))
        if not zeigen:
            if len(ziele) == 1:
                teile.append(kopf + "\n(nichts offen)")
            continue
        gesamt += len(zeigen)
        teile += [kopf, ""] + [g_ausgeben(k, wurzel, head) + "\n" for k in zeigen]
        teile.append("Code-Zeilen beziehen sich auf " + (f"den aktuellen Stand von {BIS}." if g.get("lokal")
                     else f"den MR-Stand {head[:8]} im Klon (den MR nicht ändern, nur antworten).") + "\n")
    if gesamt:
        teile.append('Antworten: merge-train agent antworten <id> "Text"   (umgesetzt: --erledigt · Text von stdin: -)')
    return "\n".join(teile) or "(nichts offen)", gesamt

def g_ungelesen(k):
    """Gesendete Nachrichten des Nutzers, die der Agent noch nicht abgeholt hat (auch nach einer Antwort nachgeschoben)."""
    return [m for m in k["nachrichten"] if m["von"] == "ich" and m.get("gesendet") and not m.get("abgeholt")]

def g_antworten(fid, text, erledigt=False, als=None, ziele=None):
    """Antwort auf Faden fid (Anfang genügt) – gesucht in ziele, sonst in allen Gesprächen."""
    treffer = []
    for g in ziele or g_alle():
        with SPERRE:
            st = review_laden(g)
        treffer += [(g, k["id"]) for k in g_faeden(st) if k["id"] == fid or (len(fid) >= 4 and k["id"].startswith(fid))]
    if not treffer:
        raise GitLabFehler(f"Gespräch {fid} gibt es nicht (merge-train agent feedback --alle)")
    if len(treffer) > 1:
        raise GitLabFehler(f"{fid} ist nicht eindeutig: " + ", ".join(t[1] for t in treffer))
    g, kid = treffer[0]
    with SPERRE:
        st = review_laden(g)
        k = next(k for k in g_faeden(st) if k["id"] == kid)
        neu = g_ungelesen(k)
        if neu:  # der Nutzer hat inzwischen nachgelegt: nicht blind abhaken
            raise GitLabFehler(f'In [{k["id"]}] gibt es {len(neu)} neue Nachricht(en), die du noch nicht gelesen hast – '
                               f'erst „merge-train agent feedback“, dann antworten:\n' +
                               "\n".join(f'    Nutzer ({g_zeit(m["gesendet"])}): {m["text"]}' for m in neu))
        wer = als or k.get("an") or None
        if text:
            k["nachrichten"].append(g_nachricht("claude", text, gesendet=True, wer=wer))
        if erledigt:
            k["erledigt"] = {"von": "claude", "zeit": jetzt(), "wer": wer}
        review_speichern(g, st)
        rest = sum(1 for x in g_faeden(st) if g_status(x) == "wartet")
        tid = st.get("todo_id")
    melden(f"{g_name(g)}: {wer or 'Claude'} hat geantwortet" + (" (erledigt)" if erledigt else ""))
    if not rest and todo_offen(tid):
        subprocess.run(["todo", "erledigt", tid, "-n", "Alle Fragen/Feedback in merge-train beantwortet"], capture_output=True)
    return k["id"], rest

def g_horchen(ziele, timeout=0, als=None):
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
    while not ende or time.time() < ende:
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
                       for k in g_faeden(st) for n in k["nachrichten"]):
                    neu.append(g)
            if neu:
                return g_abholen(neu)
        time.sleep(1)
    return "merge-train: keine neuen Nachrichten (Zeit abgelaufen)", 0

def g_archivieren(projekt):
    """Nach „fertig“: erledigte Fäden aus der Ansicht nehmen (bleiben in der Datei)."""
    mr = {"lokal": projekt}
    with SPERRE:
        st = review_laden(mr)
        n = 0
        for k in g_faeden(st):
            if g_status(k) == "erledigt":
                k["archiv"] = jetzt(); n += 1
        if n:
            review_speichern(mr, st)

def g_zahlen(projekt):
    """Für den Zug: (offene Fäden, Fäden mit neuer Antwort)."""
    try:
        st = review_laden({"lokal": projekt})
    except Exception:
        return 0, 0
    f = g_faeden(st)
    return sum(1 for k in f if g_status(k) != "erledigt"), sum(1 for k in f if g_status(k) == "antwort")
