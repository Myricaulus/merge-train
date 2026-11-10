# ---------------------------------------------------------------- Gespräch (Fragen und Feedback an den Agenten)
# Im lokalen Projekt-Diff wird aus einem Kommentar ein Gesprächsfaden: der Nutzer schreibt (Entwurf), „Feedback senden“
# schickt alle Entwürfe ab, der Agent holt sie mit „merge-train agent feedback“ ab und antwortet mit „agent antworten“.
# Bei MRs genauso, für Kommentare, die „an <Agent>“ gespeichert werden; sie liegen als Fäden (mit „nachrichten“) in der
# Review-Datei des MR und gehen nie nach GitLab. Schlüssel g wie bei den Quellen: {"lokal": projekt} oder der MR.
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

def g_agenten(g):
    """Namen, an die man im GitLab-Modus fragen kann: eingerichtete [agenten] und wer gerade zuhört."""
    namen = list(KONF.get("agenten") or {})
    if quelle(g).kann["committen"] and "Claude" not in namen:  # lokal ist Claude immer da (todo / feedback_befehl)
        namen.insert(0, "Claude")
    wer = horcht(g)
    return namen + ([wer] if wer and wer not in namen else [])

def g_daten(mr, ansicht=None):
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
    return {"ok": True, "kommentare": kom, "stand": stand(mr, st),
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
                    return False, fehler if quelle(mr).kann["review"] else fehler.replace("Der MR hat", "Das Projekt hat")
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

# Was zwischen „agent horchen“ und der Agenten-Session (claude, copilot …) liegen darf. systemd/init: dorthin wandern
# verwaiste Prozesse, wenn die Session weg ist – dann hört niemand mehr zu.
_ZWISCHEN = {"sh", "bash", "zsh", "fish", "dash", "ksh", "python", "python3", "timeout", "env", "nohup", "setsid", "script"}
_WAISENHAUS = {"systemd", "init", "launchd"}

def _proc(pid):
    """(name, ppid) aus /proc, None wenn es den Prozess nicht (mehr) gibt."""
    try:
        stat = open(f"/proc/{pid}/stat").read()
    except OSError:
        return None
    zustand, ppid = stat[stat.rindex(")") + 2:].split()[:2]
    return None if zustand == "Z" else (stat[stat.index("(") + 1:stat.rindex(")")], int(ppid))  # Zombie: schon beendet

def agent_session(pid):
    """Die Agenten-Session über pid: der nächste Vorfahr, der keine Shell/Python ist. None = verwaist (Session weg).
    Ohne /proc (kein Linux/WSL) lässt sich das nicht prüfen: dann gilt pid selbst."""
    if not os.path.isdir("/proc/self"):
        return pid
    p = pid
    for _ in range(30):
        info = _proc(p)
        if info is None:
            return None
        name, ppid = info
        if p != pid and name not in _ZWISCHEN:
            return None if name in _WAISENHAUS or name.startswith(("Relay(", "SessionLeader")) else p
        if ppid <= 1:
            return None
        p = ppid
    return None

SEITE_WEG_S = int(os.environ.get("MERGE_TRAIN_SEITE_WEG_S") or 30)

def seite_datei(g):
    return review_datei(g)[:-5] + ".seite"

def seite_lebt(g):
    """Lebenszeichen einer offenen Seite (fragt alle 4 s nach dem Stand) – horchen hört auf, wenn keins mehr kommt."""
    p = seite_datei(g)
    try:
        os.utime(p)
    except FileNotFoundError:
        ersetzen(p, "")

def horcht(g):
    """Name der Session, die gerade mit „agent horchen“ zuhört (Standard „Claude“), sonst None. Zählt nur, solange über
    dem horchen-Prozess noch eine Agenten-Session lebt (sonst ist es ein Überbleibsel einer beendeten Session)."""
    try:
        teile = open(horcht_datei(g)).read().split()
        pid = int(teile[0])
        os.kill(pid, 0)
    except (OSError, ValueError, IndexError):
        return None
    if agent_session(pid) is None:
        return None
    return " ".join(teile[2:]) or "Claude"

def todo_offen(tid):
    if not tid:
        return False
    basis = os.environ.get("TODO_DIR") or os.path.expanduser("~/todo")
    return os.path.exists(os.path.join(basis, "offen", tid + ".md"))

def benachrichtigen(g, wurzel, n, namen=("Claude",)):
    """Nach „Feedback senden“: Session, die zuhört → nichts weiter; sonst Agent aus [agenten], feedback_befehl oder
    todo-Eintrag. Rückgabe (text für die Seite, todo_id oder None)."""
    wer = horcht(g)
    if wer:
        return f"an die Session übergeben, die zuhört ({wer})", None
    projekt = quelle(g).name_von(g)
    prompt = quelle(g).prompt(g, wurzel)
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
        return f"Keine Session hört zu – in einer Agent-Session „merge-train agent feedback {mr_id(g)}“ sagen", None
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
        wurzel, _ = quelle(g).ort(g)
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
            treffer = [g for g in g_alle() if not g.get("lokal") and g["projekt"] == mr["projekt"]
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
    for g in g_alle():
        if not g.get("lokal"):
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

def g_nachbarn(k, rv):
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

def g_ausgeben(k, wurzel, head, kontext=3, rv=None):
    """Ein Faden für den Agenten: Ort im aktuellen Stand, Code drumherum, GitLab-Kommentare/Hinweise dort, Verlauf."""
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
    for name, status, text in g_nachbarn(k, rv):
        out.append(f'    an dieser Zeile: {name} ({status}):')
        out.append("      " + text.replace("\n", "\n      "))
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
        wurzel, head = quelle(g).ort(g)
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
        wo = f"{BIS} {head[:8]}" if g.get("lokal") else f"MR {mr_id(g)} · Stand {head[:8]} · Klon {wurzel}"
        kopf = (f'merge-train · {quelle(g).name_von(g)} · {wo} · {sum(1 for k in faeden if g_status(k) == "wartet")} '
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
        teile += [kopf, ""] + [g_ausgeben(k, wurzel, head, rv=rv) + "\n" for k in zeigen]
        teile.append("Code-Zeilen beziehen sich auf " + (("den Arbeitsstand (auch nicht Committetes); Wünsche dort umsetzen, "
                     "nicht committen." if BIS == ARBEITSSTAND else f"den aktuellen Stand von {BIS}.") if quelle(g).kann["committen"]
                     else f"den Stand {head[:8]} im Klon (nichts ändern, nur antworten).") + "\n")
    if gesamt:
        teile.append('Antworten: merge-train agent antworten <id> "Text"   (umgesetzt: --erledigt · Text von stdin: -)')
        if any(quelle(g).kann["review"] for g in ziele):
            teile.append('GitLab-Kommentar umformulieren: merge-train agent kommentar <h:key | Kommentar-id | Faden-id> "Text"')
    return "\n".join(teile) or "(nichts offen)", gesamt

def g_kommentar(ziel, text, ziele=None):
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
    for g in ziele or g_alle():
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
            treffer += [(g, "k", k) for k in rk(st) if passt(k["id"], ziel)]
            treffer += [(g, "f", k) for k in g_faeden(st) if passt(k["id"], ziel)]
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
    melden(f"{quelle(g).name_von(g)}: {wer or 'Claude'} hat geantwortet" + (" (erledigt)" if erledigt else ""))
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
    session = agent_session(os.getpid())  # endet die Agenten-Session, hört auch horchen auf
    start, gesehen = time.time(), False
    seiten = [seite_datei(g) for g in ziele]
    while not ende or time.time() < ende:
        if session and _proc(session) is None:
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
                       for k in g_faeden(st) for n in k["nachrichten"]):
                    neu.append(g)
            if neu:
                return g_abholen(neu)
        time.sleep(1)
    return "merge-train: keine neuen Nachrichten (Zeit abgelaufen)", 0

def g_archivieren(mr):
    """Nach „fertig“: erledigte Fäden aus der Ansicht nehmen (bleiben in der Datei)."""
    with SPERRE:
        st = review_laden(mr)
        n = 0
        for k in g_faeden(st):
            if g_status(k) == "erledigt":
                k["archiv"] = jetzt(); n += 1
        if n:
            review_speichern(mr, st)

def g_zahlen(g):
    """Für den Zug: (offene Fäden, Fäden mit neuer Antwort)."""
    try:
        st = review_laden(g)
    except Exception:
        return 0, 0
    f = g_faeden(st)
    return sum(1 for k in f if g_status(k) != "erledigt"), sum(1 for k in f if g_status(k) == "antwort")
