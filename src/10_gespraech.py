# ---------------------------------------------------------------- Gespräch (lokaler Modus: Fragen und Feedback an den Agenten)
# Im lokalen Projekt-Diff wird aus einem Kommentar ein Gesprächsfaden: der Nutzer schreibt (Entwurf), „Feedback senden“
# schickt alle Entwürfe ab, der Agent holt sie mit „merge-train agent feedback“ ab und antwortet mit „agent antworten“.
# Zustand: DATEN/lokal/<projekt>.json, gleiche Form wie bei MRs (kommentare mit path/a/b, refs des Stands beim Schreiben),
# je Faden „nachrichten“: [{id, von: ich|claude, text, zeit, gesendet, abgeholt}], „erledigt“: {von, zeit} oder None.
# Wer zuhört: „agent horchen“ legt DATEN/lokal/<projekt>.horcht an (pid). Hört niemand zu, legt „Feedback senden“
# einen todo-Eintrag an (Panel pulsiert, „Session starten“ öffnet ihn mit todo los) – oder ruft feedback_befehl auf.

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

def g_daten(mr, ansicht=None):
    """Wie review_daten, für ein lokales Projekt: Fäden auf den Stand der Seite umgerechnet."""
    with SPERRE:
        st = review_laden(mr)
    struktur = struktur_laden(st)
    if struktur is None:
        wurzel = g_wurzel(mr["lokal"])
        if not wurzel:
            return {"ok": False, "text": f'Projekt {mr["lokal"]} nicht gefunden'}
        _, struktur = projekt_seite(wurzel)
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
                    "nachrichten": k["nachrichten"], "erledigt": k.get("erledigt")})
    ausserhalb = 0
    if ansicht:
        ans_st = ansicht_struktur(struktur, ansicht)
        vorher = len(kom)
        kom = ansicht_zuordnen(struktur, ans_st, kom)
        ausserhalb = vorher - len(kom)
    entwuerfe = sum(1 for k in g_faeden(st) for m in k["nachrichten"] if m["von"] == "ich" and not m.get("gesendet"))
    return {"ok": True, "lokal": True, "kommentare": kom, "hinweise": [], "quellen": [], "stand": stand(mr, st),
            "ausstehend": entwuerfe, "ausserhalb": ausserhalb, "horcht": horcht(mr["lokal"]) is not None,
            "todo": st.get("todo_id") if todo_offen(st.get("todo_id")) else None}

def g_nachricht(von, text, gesendet=False):
    return {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:8], "von": von, "text": text, "zeit": jetzt(),
            "gesendet": jetzt() if gesendet else None}

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
            if d.get("datei") is not None:
                fehler, ort = zeile_aus_klick(struktur, d, ansicht)
                if fehler:
                    return False, fehler.replace("Der MR hat", "Das Projekt hat")
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

def horcht_datei(projekt):
    return os.path.join(DATEN, "lokal", dateiname(projekt)[:-5] + ".horcht")

def horcht(projekt):
    """pid der Session, die gerade mit „agent horchen“ zuhört, sonst None."""
    try:
        pid = int(open(horcht_datei(projekt)).read().split()[0])
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError, IndexError):
        return None

def todo_offen(tid):
    if not tid:
        return False
    basis = os.environ.get("TODO_DIR") or os.path.expanduser("~/todo")
    return os.path.exists(os.path.join(basis, "offen", tid + ".md"))

def g_prompt(projekt):
    return (f"In merge-train liegen Fragen bzw. Feedback des Nutzers zum Code von {projekt} (Diff {BIS} gegen {VON}). "
            f"Hol sie mit `merge-train agent feedback` ab. Fragen beantworten, Änderungswünsche auf {BIS} umsetzen und "
            f"committen; zu jedem Faden mit `merge-train agent antworten <id> \"…\"` antworten (umgesetzt: --erledigt). "
            f"Danach mit `merge-train agent horchen` im Hintergrund auf weitere Nachrichten warten.")

def benachrichtigen(projekt, wurzel, n):
    """Nach „Feedback senden“: Session, die zuhört → nichts weiter; sonst feedback_befehl oder todo-Eintrag.
    Rückgabe (text für die Seite, todo_id oder None)."""
    if horcht(projekt):
        return "an die Claude-Session übergeben, die zuhört", None
    prompt = g_prompt(projekt)
    if KONF.get("feedback_befehl"):
        argv = [a.format(ordner=wurzel, projekt=projekt, prompt=prompt) for a in shlex.split(KONF["feedback_befehl"])]
        try:
            subprocess.Popen(argv, cwd=wurzel, start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "Claude-Session gestartet (feedback_befehl)", None
        except OSError as e:
            return f"feedback_befehl startet nicht: {e}", None
    if not shutil.which("todo"):
        return "Keine Session hört zu – in einer Claude-Session im Projekt „merge-train agent feedback“ sagen", None
    with SPERRE:
        st = review_laden({"lokal": projekt})
        tid = st.get("todo_id")
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
            st = review_laden({"lokal": projekt}); st["todo_id"] = tid; review_speichern({"lokal": projekt}, st)
    subprocess.run(["todo", "heute", tid, "-t", f"Fragen/Feedback aus merge-train ({zeile})"], capture_output=True)
    return "Keine Session hört zu – als todo eingetragen (Panel), „▶ Session starten“ öffnet sie", tid

def feedback_senden(mr):
    """Alle Entwürfe abschicken. Rückgabe (ok, text, todo_id)."""
    projekt = mr["lokal"]
    wurzel = g_wurzel(projekt)
    if not wurzel:
        return False, f"Projekt {projekt} nicht gefunden", None
    with SPERRE:
        st = review_laden(mr)
        n = 0
        for k in g_faeden(st):
            for m in k["nachrichten"]:
                if m["von"] == "ich" and not m.get("gesendet"):
                    m["gesendet"] = jetzt(); n += 1
        if not n:
            return False, "Keine Entwürfe zum Senden", None
        review_speichern(mr, st)
    text, tid = benachrichtigen(projekt, wurzel, n)
    return True, f"{n} Nachricht(en) gesendet · {text}", tid

def session_starten(mr):
    with SPERRE:
        tid = review_laden(mr).get("todo_id")
    if not todo_offen(tid):
        return False, "Kein offener todo-Eintrag"
    r = subprocess.run(["todo", "los", tid], capture_output=True, text=True)
    return (True, "Konsole geöffnet – Enter startet Claude") if r.returncode == 0 else \
        (False, f"todo los: {(r.stderr or r.stdout).strip()[:200]}")

# ---- Agent-Seite (CLI)

def g_projekt(name=None):
    """Projektname aus Argument oder aktuellem Ordner → (projekt, wurzel)."""
    ordner = name or os.getcwd()
    if name and not os.path.isdir(ordner):
        ordner = os.path.join(PROJEKTE, name)
    wurzel = (git(ordner, "rev-parse", "--show-toplevel", check=False) or "").strip() if os.path.isdir(ordner) else ""
    if not wurzel:
        raise GitLabFehler(f"kein Git-Repo: {name or os.getcwd()}")
    return projektname(wurzel), wurzel

def g_zeit(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m. %H:%M")
    except (TypeError, ValueError):
        return "?"

def g_ausgeben(k, wurzel, head, kontext=3):
    """Ein Faden für den Agenten: Ort im aktuellen Stand, Code drumherum, Verlauf."""
    von = (k.get("refs") or {}).get("head_sha") or head
    b = zeile_vorwaerts(wurzel, von, head, k["path"], k["b"]) if k.get("path") and k.get("b") else None
    ort = "allgemein (ganzes Projekt)" if not k.get("path") else \
        f'{k["path"]}:{b}' if b else (f'{k["path"]} (alte Seite, Zeile {k["a"]})' if k.get("a") and not k.get("b")
                                      else f'{k["path"]} (Zeile {k["b"]} hat sich seit dem Kommentar geändert)')
    out = [f'── [{k["id"]}] {ort}' + (f'  · {g_status(k)}' if g_status(k) != "wartet" else "")]
    if k.get("path") and b:
        t = inhalt(wurzel, head, k["path"]) or ""
        zeilen = t.split("\n")
        for i in range(max(1, b - kontext), min(len(zeilen), b + kontext) + 1):
            out.append(f'  {"→" if i == b else " "} {i:5} │ {zeilen[i - 1]}')
    elif k.get("zeile_text"):
        out.append(f'      damals │ {k["zeile_text"]}')
    for m in k["nachrichten"]:
        if m.get("gesendet") or m["von"] == "claude":
            wer = "Nutzer" if m["von"] == "ich" else "Claude"
            text = m["text"].replace("\n", "\n      ")
            out.append(f'    {wer} ({g_zeit(m["gesendet"] or m["zeit"])}): {text}')
    return "\n".join(out)

def g_abholen(projekt, wurzel, alle=False, markieren=True):
    """Text mit allen Fäden, die auf den Agenten warten (alle: auch beantwortete). Markiert Nachrichten als abgeholt."""
    mr = {"lokal": projekt}
    head = (git(wurzel, "rev-parse", "--verify", "-q", BIS, check=False) or "").strip()
    if not head:
        raise GitLabFehler(f"Branch {BIS} fehlt in {wurzel}")
    with SPERRE:
        st = review_laden(mr)
        faeden = [k for k in g_faeden(st) if g_status(k) != "entwurf" or any(m.get("gesendet") for m in k["nachrichten"])]
        zeigen = [k for k in faeden if alle or g_status(k) == "wartet" or g_ungelesen(k)]
        if markieren:
            for k in zeigen:
                for m in k["nachrichten"]:
                    if m["von"] == "ich" and m.get("gesendet") and not m.get("abgeholt"):
                        m["abgeholt"] = jetzt()
            if zeigen:
                review_speichern(mr, st)
    kopf = (f'merge-train · {projekt} · {BIS} {head[:8]} · {sum(1 for k in faeden if g_status(k) == "wartet")} '
            f'Gespräch(e) warten auf Antwort' + (f', {len(faeden)} insgesamt' if alle else ""))
    if not zeigen:
        return kopf + "\n(nichts offen)", 0
    teile = [kopf, ""] + [g_ausgeben(k, wurzel, head) + "\n" for k in zeigen]
    teile.append('Antworten: merge-train agent antworten <id> "Text"   (umgesetzt: --erledigt · Text von stdin: -)\n'
                 'Code-Zeilen beziehen sich auf den aktuellen Stand von ' + BIS + '.')
    return "\n".join(teile), len(zeigen)

def g_ungelesen(k):
    """Gesendete Nachrichten des Nutzers, die der Agent noch nicht abgeholt hat (auch nach einer Antwort nachgeschoben)."""
    return [m for m in k["nachrichten"] if m["von"] == "ich" and m.get("gesendet") and not m.get("abgeholt")]

def g_antworten(projekt, fid, text, erledigt=False):
    mr = {"lokal": projekt}
    with SPERRE:
        st = review_laden(mr)
        k = next((k for k in g_faeden(st) if k["id"] == fid or (len(fid) >= 4 and k["id"].startswith(fid))), None)
        if not k:
            raise GitLabFehler(f"Gespräch {fid} gibt es in {projekt} nicht (merge-train agent feedback --alle)")
        neu = g_ungelesen(k)
        if neu:  # der Nutzer hat inzwischen nachgelegt: nicht blind abhaken
            raise GitLabFehler(f'In [{k["id"]}] gibt es {len(neu)} neue Nachricht(en), die du noch nicht gelesen hast – '
                               f'erst „merge-train agent feedback“, dann antworten:\n' +
                               "\n".join(f'    Nutzer ({g_zeit(m["gesendet"])}): {m["text"]}' for m in neu))
        if text:
            k["nachrichten"].append(g_nachricht("claude", text, gesendet=True))
        if erledigt:
            k["erledigt"] = {"von": "claude", "zeit": jetzt()}
        review_speichern(mr, st)
        rest = sum(1 for x in g_faeden(st) if g_status(x) == "wartet")
        tid = st.get("todo_id")
    melden(f"{projekt}: Claude hat geantwortet" + (" (erledigt)" if erledigt else ""))
    if not rest and todo_offen(tid):
        subprocess.run(["todo", "erledigt", tid, "-n", "Alle Fragen/Feedback in merge-train beantwortet"], capture_output=True)
    return k["id"], rest

def g_horchen(projekt, wurzel, timeout=0):
    """Warten, bis neue (noch nicht abgeholte) Nachrichten da sind, dann ausgeben. Rückgabe (text, anzahl)."""
    import atexit, signal, time
    datei = horcht_datei(projekt)
    ersetzen(datei, f"{os.getpid()} {jetzt()}\n")
    def weg(*_):
        try:
            if open(datei).read().split()[0] == str(os.getpid()):
                os.remove(datei)
        except (OSError, IndexError):
            pass
    atexit.register(weg)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(0))
    ende = time.time() + timeout if timeout else None
    pfad = review_datei({"lokal": projekt})
    zuletzt = None
    while not ende or time.time() < ende:
        try:
            m = os.stat(pfad).st_mtime_ns
        except OSError:
            m = None
        if m != zuletzt:
            zuletzt = m
            with SPERRE:
                st = review_laden({"lokal": projekt})
            if any(n["von"] == "ich" and n.get("gesendet") and not n.get("abgeholt")
                   for k in g_faeden(st) for n in k["nachrichten"]):
                return g_abholen(projekt, wurzel)
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
