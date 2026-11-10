# ---------------------------------------------------------------- Einstellungen

def _xdg(var, std):
    return os.environ.get(var) or os.path.expanduser(std)

KONFIG_DATEI = os.environ.get("MERGE_TRAIN_CONFIG") or \
    os.path.join(_xdg("XDG_CONFIG_HOME", "~/.config"), "merge-train", "config.toml")
STANDARD = {
    "lokal": True,            # lokaler Projekt-Diff (von/bis-Branches aller Repos unter projekte)
    "projekte": "~/Projects",
    "von": "reviewed", "bis": "claude",
    "gitlab": True,           # GitLab-MRs über glab
    "gitlab_host": "",        # leer: Host aus MR-URL bzw. git-Remote, sonst glab-Standard
    "glab": "glab",
    "mr_liste": "reviewer",   # Zug im GitLab-Modus: reviewer | assignee | author | keine
    "hinweise": [],           # Globs für Agent-Hinweis-Dateien, z. B. "~/src/*/tasks/*-review-markers.json"
    "repos": {},              # "gruppe/projekt" = "~/pfad/zum/klon" (schneller als Dateien über die API)
    "browser": "",            # leer: xdg-open, sonst wslview/explorer.exe; unter WSL z. B. "wslview"
    "port": 8771,
    "feedback_befehl": "",    # lokaler Modus: Befehl, wenn keine Session zuhört (sonst todo-Eintrag)
    "agenten": {},            # Gespräch auch im GitLab-Modus: Name = Startbefehl, z. B. copilot = "… copilot -i {prompt}"
    "log_tage": 7,            # Log der Anfragen an die Quellen (git, GitLab): ~/.cache/merge-train/aussen-<datum>.log; 0 = aus
}

def _toml_einfach(text):
    """Notbehelf ohne tomllib (Python < 3.11): key = wert und [abschnitt], Werte wie in Python."""
    import ast
    out, akt = {}, None
    for z in text.splitlines():
        z = z.strip()
        if not z or z.startswith("#"):
            continue
        m = re.fullmatch(r"\[([\w.-]+)\]", z)
        if m:
            akt = out.setdefault(m.group(1), {}); continue
        k, _, v = z.partition("=")
        v = re.sub(r"\s+#[^\"']*$", "", v.strip())
        v = re.sub(r"\btrue\b", "True", re.sub(r"\bfalse\b", "False", v))
        (akt if akt is not None else out)[k.strip().strip('"')] = ast.literal_eval(v)
    return out

def konfig_laden():
    k = dict(STANDARD)
    try:
        text = open(KONFIG_DATEI, encoding="utf-8").read()
    except FileNotFoundError:
        return k
    try:
        import tomllib
        k.update(tomllib.loads(text))
    except ImportError:
        k.update(_toml_einfach(text))
    except Exception as e:
        sys.exit(f"merge-train: {KONFIG_DATEI} fehlerhaft: {e}")
    return k

KONF = konfig_laden()
ORDNER = os.path.join(_xdg("XDG_CACHE_HOME", "~/.cache"), "merge-train")
DATEN = os.path.join(_xdg("XDG_DATA_HOME", "~/.local/share"), "merge-train")
# projekte: Ordner mit Repos (auch eine Ebene tiefer) oder einzelne Repos – ein Eintrag oder eine Liste
PROJEKTE_LISTE = [os.path.expanduser(p) for p in (KONF["projekte"] if isinstance(KONF["projekte"], list) else [KONF["projekte"]])]
PROJEKTE = PROJEKTE_LISTE[0] if PROJEKTE_LISTE else os.path.expanduser("~")
VON, BIS = KONF["von"], KONF["bis"]
RUNDE = os.path.join(ORDNER, "runde.json")
SCHLUESSEL = os.path.join(ORDNER, "schluessel")
SPERRE = threading.RLock()

def ersetzen(ziel, inhalt):
    """Atomar schreiben (eigene Temp-Datei je Aufruf, damit parallele Abrufe sich nicht stören)."""
    import tempfile
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(ziel), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(inhalt)
    os.chmod(tmp, 0o644)
    os.replace(tmp, ziel)

def schluessel():
    os.makedirs(ORDNER, exist_ok=True)
    try:
        return open(SCHLUESSEL).read().strip()
    except FileNotFoundError:
        import secrets
        k = secrets.token_hex(16)
        try:
            fd = os.open(SCHLUESSEL, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return open(SCHLUESSEL).read().strip()
        os.write(fd, k.encode()); os.close(fd)
        return k

def projektname(wurzel):
    for p in PROJEKTE_LISTE:
        if wurzel.startswith(p.rstrip("/") + "/"):
            return os.path.relpath(wurzel, p)
    return os.path.basename(wurzel)

def projekt_ordner(name):
    """Projektname → Ordner (unter einem Eintrag von projekte oder ein dort genanntes Repo)."""
    for p in PROJEKTE_LISTE:
        if os.path.isdir(os.path.join(p, name)) and not os.path.isdir(os.path.join(p, ".git")):
            return os.path.join(p, name)
        if os.path.basename(p.rstrip("/")) == name and os.path.isdir(os.path.join(p, ".git")):
            return p
    return os.path.join(PROJEKTE, name)

def dateiname(projekt):
    return projekt.replace("/", "_") + ".html"

ARBEITSSTAND = "arbeitsstand"  # bis = Arbeitsverzeichnis (auch nicht committet), z. B. von = "origin/main"
_ARBEIT = {}

def arbeitsstand(wurzel):
    """Das Arbeitsverzeichnis (geänderte, neue nicht ignorierte und gelöschte Dateien) als Commit-Objekt, ohne Index,
    Branch oder Dateien anzufassen: Kopie des Index, add -A, write-tree, commit-tree mit festen Daten – gleicher Inhalt
    ergibt denselben sha (die Seite bleibt im Cache). Ohne Änderungen: HEAD."""
    import tempfile
    head = git(wurzel, "rev-parse", "HEAD").strip()
    status = git(wurzel, "status", "--porcelain=v1", "-z", "--untracked-files=all", check=False) or ""
    if not status:
        return head
    merkmal = [head, status]
    for e in status.split("\0"):  # Inhalt kann sich ändern, ohne dass sich der Status ändert: mtime/Größe mitnehmen
        if len(e) > 3:
            try:
                s = os.stat(os.path.join(wurzel, e[3:])); merkmal.append(f"{s.st_mtime_ns}:{s.st_size}")
            except OSError:
                merkmal.append("-")
    k = (wurzel, hashlib.sha1("|".join(merkmal).encode()).hexdigest())
    if k in _ARBEIT:
        return _ARBEIT[k]
    with tempfile.TemporaryDirectory() as t:
        idx = os.path.join(t, "index")
        echt = git(wurzel, "rev-parse", "--path-format=absolute", "--git-path", "index", check=False)
        if echt and os.path.exists(echt.strip()):
            shutil.copyfile(echt.strip(), idx)  # mit Stat-Cache: nur geänderte Dateien werden neu gelesen
        env = dict(os.environ, GIT_INDEX_FILE=idx, GIT_AUTHOR_NAME="merge-train", GIT_AUTHOR_EMAIL="merge-train@localhost",
                   GIT_COMMITTER_NAME="merge-train", GIT_COMMITTER_EMAIL="merge-train@localhost",
                   GIT_AUTHOR_DATE="2000-01-01T00:00:00+0000", GIT_COMMITTER_DATE="2000-01-01T00:00:00+0000")
        if not os.path.exists(idx):
            git(wurzel, "read-tree", "HEAD", env=env)
        git(wurzel, "add", "-A", env=env)
        baum = git(wurzel, "write-tree", env=env).strip()
        sha = head if baum == git(wurzel, "rev-parse", "HEAD^{tree}").strip() else \
            git(wurzel, "commit-tree", baum, "-p", head, "-m", "Arbeitsstand (nicht committet)", env=env).strip()
    if len(_ARBEIT) > 200:
        _ARBEIT.clear()
    _ARBEIT[k] = sha
    return sha

def bis_sha(wurzel, bis=None):
    """Stand für bis: Branch/Ref oder der Arbeitsstand."""
    bis = bis or BIS
    return arbeitsstand(wurzel) if bis == ARBEITSSTAND else git(wurzel, "rev-parse", bis).strip()

def finde_repos():
    """Alle Repos aus projekte (Ordner: auch eine Ebene tiefer, z. B. cachy-patch/*; oder direkt ein Repo) mit VON und BIS."""
    out, kandidaten = [], []
    for wo in PROJEKTE_LISTE:
        if os.path.isdir(os.path.join(wo, ".git")):  # direkt ein Repo
            kandidaten.append(wo); continue
        for e in sorted(os.listdir(wo)) if os.path.isdir(wo) else []:
            d = os.path.join(wo, e)
            if not os.path.isdir(d): continue
            kandidaten += [d] if os.path.isdir(os.path.join(d, ".git")) else \
                [os.path.join(d, u) for u in sorted(os.listdir(d)) if os.path.isdir(os.path.join(d, u, ".git"))]
    for k in kandidaten:
        if git(k, "rev-parse", "--verify", "-q", VON, check=False) and \
           git(k, "rev-parse", "--verify", "-q", "HEAD" if BIS == ARBEITSSTAND else BIS, check=False):
            out.append(k)
    return out

def statistik(wurzel, von=None, bis=None):
    von, bis = von or VON, bis_sha(wurzel, bis)
    basis = git(wurzel, "merge-base", von, bis).strip()
    plus = minus = dateien = 0
    for z in git(wurzel, "diff", "--numstat", "--find-renames", basis, bis).splitlines():
        a, b, _ = z.split("\t", 2); dateien += 1
        if a != "-": plus += int(a); minus += int(b)
    log = git(wurzel, "log", "--format=%B", f"{von}..{bis}")
    return {"p": projektname(wurzel), "datei": dateiname(projektname(wurzel)), "plus": plus, "minus": minus,
            "dateien": dateien, "commits": int(git(wurzel, "rev-list", "--count", f"{von}..{bis}")),
            "todos": sorted(set(re.findall(r"todo:([\w.-]+)", log))), "status": "offen",
            "sha": bis}

def runde_laden():
    import json
    try:
        r = json.load(open(RUNDE))
    except (FileNotFoundError, ValueError):
        r = {}
    heute = datetime.now().strftime("%Y-%m-%d")
    return {p: w for p, w in r.items() if w.get("tag") == heute}

def lokal_wagen(stats):
    """Lokale Waggons: offene Projekte + heute fertig gewordene (sofern seitdem nichts Neues kam), absteigend nach Umfang."""
    fertig = runde_laden()
    wagen = [w for w in stats if w["dateien"]]  # offen ist, was jetzt noch Unterschiede hat
    offen = {w["p"] for w in wagen}
    wagen += [dict(w, status="fertig") for p, w in fertig.items() if p not in offen]
    wagen.sort(key=lambda w: -(w["plus"] + w["minus"]))
    for w in wagen:  # Gespräch: offene Fäden / neue Antworten des Agenten
        w["gs"], w["gs_neu"] = g_zahlen({"lokal": w["p"]})
        w["datei"] = "/" + dateiname(w["p"])
    return wagen

def commits_html(commits, knoepfe=None):
    """commits: Liste (kurz-sha, zeit, betreff, rumpf[, sha]). knoepfe(i, commit) → HTML hinter dem Betreff."""
    def nachricht(b):
        b = re.sub(r"\n*Co-Authored-By:.*", "", b, flags=re.I).strip()
        return f'<div class="nachricht">{html.escape(b)}</div>' if b else ""
    return "".join(f'<div class="commit"><code>{html.escape(c[0])}</code> <b>{html.escape(c[2])}</b> '
                   f'<span class="sub">{html.escape(c[1])}</span>{knoepfe(i, c) if knoepfe else ""}{nachricht(c[3])}</div>'
                   for i, c in enumerate(commits)) or '<div class="sub">keine Commits</div>'

def dateiliste_html(dateien):
    fl, letzter = [], None
    for n, d in enumerate(dateien):
        ordner, name = os.path.split(d["neu"])
        if ordner != letzter:
            fl.append(f'<div class="sub" style="padding:6px 10px 0">{html.escape(ordner or "/")}</div>'); letzter = ordner
        fl.append(f'<a href="#d{n}" title="{html.escape(d["neu"])}"><span class="zahl"><span class="kz"></span><span class="p">+{d["plus"]}</span> '
                  f'<span class="m">−{d["minus"]}</span></span>{html.escape(name)}'
                  f'{" <span class=sub>(" + d["status"] + ")</span>" if d["status"] != "geändert" else ""}</a>')
    return fl

def alles_erzeugen(von, bis, inline):
    from concurrent.futures import ThreadPoolExecutor
    schluessel()  # einmal vorab anlegen, sonst Wettlauf zwischen den Threads
    repos = finde_repos()
    with ThreadPoolExecutor(8) as ex:
        stats = list(ex.map(lambda r: statistik(r, von, bis), repos))
    wagen = lokal_wagen(stats)
    offen = {w["p"] for w in wagen if w["status"] == "offen"}
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda r: projekt_seite(r, von, bis),
                    [r for r in repos if projektname(r) in offen]))
    return repos, wagen

def oeffnen(ziel):
    """Im Browser öffnen: browser aus der Einstellung, sonst xdg-open / wslview / explorer.exe (WSL)."""
    if KONF["browser"]:
        argv = shlex.split(KONF["browser"])
    else:
        prog = next((p for p in ("xdg-open", "wslview", "explorer.exe") if shutil.which(p)), None)
        if not prog:
            print(f"merge-train: kein Browser-Befehl gefunden – {ziel} bitte selbst öffnen (browser = … in der Einstellung)")
            return
        argv = [prog]
    subprocess.Popen(argv + [ziel], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def melden(text):
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-a", "merge-train", "-i", "vcs-merge-request", "merge-train", text], check=False)

def fertig(projekt, sha, k):
    """VON auf den gesehenen Stand setzen. Rückgabe (ok, text)."""
    import json
    if k != schluessel():
        return False, "Abgelehnt: falscher Schlüssel."
    repos = {projektname(r): r for r in finde_repos()}
    if projekt not in repos:
        return False, f"Unbekanntes Projekt: {projekt}"
    wurzel = repos[projekt]
    if not re.fullmatch(r"[0-9a-f]{40}", sha or "") or git(wurzel, "cat-file", "-t", sha, check=False) != "commit\n":
        return False, "Abgelehnt: unbekannter Stand."
    if not LOKAL.kann["fertig"]:
        return False, f"„fertig“ geht nur mit lokalen Branches (von = {VON}, bis = {BIS})."
    if git(wurzel, "merge-base", "--is-ancestor", VON, sha, check=False) is None:
        return False, f"{projekt}: {VON} ist nicht Vorgänger des gesehenen Stands – nichts geändert."
    st = statistik(wurzel, VON, sha)
    log = git(wurzel, "log", "--format=%B", f"{VON}..{sha}")
    schliesst = sorted(set(re.findall(r"closes\s+todo:([\w.-]+)", log, flags=re.I)))
    git(wurzel, "branch", "-f", VON, sha)
    g_archivieren({"lokal": projekt})
    with SPERRE:
        r = runde_laden()
        r[projekt] = dict(st, p=projekt, datei=dateiname(projekt), status="fertig", tag=datetime.now().strftime("%Y-%m-%d"))
        with open(RUNDE, "w") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    erledigt = []
    for t in schliesst:
        ok = subprocess.run(["todo", "erledigt", t, "-n", f"Merge-Request {projekt} angenommen ({sha[:8]})"],
                            cwd=wurzel, capture_output=True).returncode == 0
        erledigt.append(t + ("" if ok else " (Fehler)"))
    rest = git(wurzel, "rev-list", "--count", f"{sha}..{BIS}").strip()
    text = (f"{projekt}: {VON} → {sha[:8]}" + (f"\ntodos erledigt: {', '.join(erledigt)}" if erledigt else "")
            + (f"\nAchtung: {BIS} hat {rest} neuere Commit(s)" if rest != "0" else ""))
    melden(text)
    return True, text

