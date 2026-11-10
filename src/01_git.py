# ---------------------------------------------------------------- git

ANLASS = threading.local()  # wofür die Anfrage ist (Server: Pfad/Aktion, CLI: Befehl) – nur fürs Log
_LOG_SPERRE, _LOG_TAG = threading.Lock(), [None]

def anlass():
    return getattr(ANLASS, "name", None) or "-"

def aussen_log(quelle, wo, was, dauer, ergebnis):
    """Anfragen an die Quellen (lokales git, GitLab) protokollieren: ~/.cache/merge-train/aussen-<datum>.log, eine Datei
    je Tag, log_tage Tage aufbewahrt (0 = aus). Zum Erkennen, was langsam ist."""
    konf, ordner = globals().get("KONF") or {}, globals().get("ORDNER")
    try:
        tage = int(konf.get("log_tage", 7) or 0)
    except (TypeError, ValueError):
        tage = 7
    if tage <= 0 or not ordner:
        return
    from datetime import timedelta
    jetzt = datetime.now()
    zeile = (f"{jetzt:%H:%M:%S}.{jetzt.microsecond // 1000:03d} {dauer:7.3f}s {quelle:<6} {anlass():<32} "
             f"{wo}  {was}  {ergebnis}\n")
    try:
        with _LOG_SPERRE:
            os.makedirs(ordner, exist_ok=True)
            if _LOG_TAG[0] != jetzt.date():  # einmal am Tag: alte Dateien weg
                _LOG_TAG[0] = jetzt.date()
                grenze = f"aussen-{jetzt - timedelta(days=tage - 1):%Y-%m-%d}.log"
                for p in glob.glob(os.path.join(ordner, "aussen-*.log")):
                    if os.path.basename(p) < grenze:
                        os.remove(p)
            with open(os.path.join(ordner, f"aussen-{jetzt:%Y-%m-%d}.log"), "a", encoding="utf-8") as f:
                f.write(zeile)
    except OSError:
        pass

def git(ordner, *a, check=True):
    t0 = time.time()
    r = subprocess.run(["git", "-C", ordner, *a], capture_output=True,
                       text=True, errors="replace")
    aussen_log("git", os.path.basename(str(ordner).rstrip("/")), "git " + " ".join(a)[:200], time.time() - t0,
               f"exit {r.returncode}" if r.returncode else f"ok {len(r.stdout)} B")
    if check and r.returncode:
        raise subprocess.CalledProcessError(r.returncode, a, r.stdout, r.stderr)
    return r.stdout if r.returncode == 0 else None

def zerlegen(diff):
    """Unified-Diff in Dateien → Hunks → Zeilen zerlegen."""
    dateien, d, h = [], None, None
    for z in diff.splitlines():
        if z.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*) b/(.*)", z)
            d = {"alt": m.group(1), "neu": m.group(2), "hunks": [], "binaer": False,
                 "status": "geändert", "plus": 0, "minus": 0}
            dateien.append(d); h = None
        elif d is None:
            continue
        elif h is None and z.startswith("new file"): d["status"] = "neu"
        elif h is None and z.startswith("deleted file"): d["status"] = "gelöscht"
        elif h is None and z.startswith("rename from"): d["status"] = "umbenannt"
        elif h is None and z.startswith("Binary files"): d["binaer"] = True
        elif z.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)", z)
            h = {"a": int(m.group(1)), "b": int(m.group(2)), "kopf": m.group(3).strip(), "z": []}
            d["hunks"].append(h)
        elif h is not None and z[:1] in (" ", "+", "-"):
            h["z"].append((z[0], z[1:]))
            if z[0] == "+": d["plus"] += 1
            if z[0] == "-": d["minus"] += 1
    return dateien

