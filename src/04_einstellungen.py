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
PROJEKTE = os.path.expanduser(KONF["projekte"])
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
    p = PROJEKTE + "/"
    return os.path.relpath(wurzel, PROJEKTE) if wurzel.startswith(p) else os.path.basename(wurzel)

def dateiname(projekt):
    return projekt.replace("/", "_") + ".html"

def finde_repos():
    """Alle Repos unter PROJEKTE mit VON und BIS (auch eine Ebene tiefer, z. B. cachy-patch/*)."""
    out = []
    for e in sorted(os.listdir(PROJEKTE)):
        d = os.path.join(PROJEKTE, e)
        if not os.path.isdir(d): continue
        kandidaten = [d] if os.path.isdir(os.path.join(d, ".git")) else \
            [os.path.join(d, u) for u in sorted(os.listdir(d)) if os.path.isdir(os.path.join(d, u, ".git"))]
        for k in kandidaten:
            if git(k, "rev-parse", "--verify", "-q", VON, check=False) and \
               git(k, "rev-parse", "--verify", "-q", BIS, check=False):
                out.append(k)
    return out

def statistik(wurzel, von=None, bis=None):
    von, bis = von or VON, bis or BIS
    basis = git(wurzel, "merge-base", von, bis).strip()
    plus = minus = dateien = 0
    for z in git(wurzel, "diff", "--numstat", "--find-renames", basis, bis).splitlines():
        a, b, _ = z.split("\t", 2); dateien += 1
        if a != "-": plus += int(a); minus += int(b)
    log = git(wurzel, "log", "--format=%B", f"{von}..{bis}")
    return {"p": projektname(wurzel), "datei": dateiname(projektname(wurzel)), "plus": plus, "minus": minus,
            "dateien": dateien, "commits": int(git(wurzel, "rev-list", "--count", f"{von}..{bis}")),
            "todos": sorted(set(re.findall(r"todo:([\w.-]+)", log))), "status": "offen",
            "sha": git(wurzel, "rev-parse", bis).strip()}

def runde_laden():
    import json
    try:
        r = json.load(open(RUNDE))
    except (FileNotFoundError, ValueError):
        r = {}
    heute = datetime.now().strftime("%Y-%m-%d")
    return {p: w for p, w in r.items() if w.get("tag") == heute}

def zug_schreiben(stats):
    """zug.js: offene Projekte + heute fertig gewordene (sofern seitdem nichts Neues kam), absteigend nach Umfang."""
    import json
    fertig = runde_laden()
    wagen = [w for w in stats if w["dateien"]]  # offen ist, was jetzt noch Unterschiede hat
    offen = {w["p"] for w in wagen}
    wagen += [dict(w, status="fertig") for p, w in fertig.items() if p not in offen]
    wagen.sort(key=lambda w: -(w["plus"] + w["minus"]))
    ersetzen(os.path.join(ORDNER, "zug.js"), "window.MR_ZUG=" + json.dumps({"wagen": wagen}, ensure_ascii=False) + ";")
    return wagen

def commits_html(commits):
    """commits: Liste (kurz-sha, zeit, betreff, rumpf)."""
    def nachricht(b):
        b = re.sub(r"\n*Co-Authored-By:.*", "", b, flags=re.I).strip()
        return f'<div class="nachricht">{html.escape(b)}</div>' if b else ""
    return "".join(f'<div class="commit"><code>{html.escape(h)}</code> <b>{html.escape(s)}</b> '
                   f'<span class="sub">{html.escape(t)}</span>{nachricht(b)}</div>'
                   for h, t, s, b in commits) or '<div class="sub">keine Commits</div>'

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

def seite_schreiben(wurzel, von, bis, inline=False):
    import json
    basis = git(wurzel, "merge-base", von, bis).strip()
    sha = git(wurzel, "rev-parse", bis).strip()
    projekt = projektname(wurzel)
    roh = git(wurzel, "log", "--reverse", "--format=%h%x1f%ad%x1f%s%x1f%b%x1e",
              "--date=format:%d.%m. %H:%M", f"{von}..{bis}")
    commits = [c.strip("\n").split("\x1f") for c in roh.split("\x1e") if c.strip()]
    diff = git(wurzel, "diff", "--find-renames", "-U4", "--no-color", basis, bis)
    dateien = zerlegen(diff)
    plus = sum(d["plus"] for d in dateien); minus = sum(d["minus"] for d in dateien)
    todos = sorted(set(re.findall(r"todo:([\w.-]+)", roh)))
    cl = commits_html(commits)
    td = ('<div class="todos">todos: ' + "".join(f"<code>{html.escape(t)}</code>" for t in todos) + "</div>"
          if todos else "")
    fl = dateiliste_html(dateien)
    leer = f'<div class="leer">Keine Unterschiede – {VON} ist auf dem Stand von {BIS}.</div>' if not dateien else ""
    mr = json.dumps({"projekt": projekt, "sha": sha, "k": schluessel(), "dateien": len(dateien)})
    hilfe = ('<div class="hilfe"><kbd>Enter</kbd> fertig · <kbd>n</kbd> nächstes Projekt<br>'
             '<kbd>←</kbd>/<kbd>→</kbd> Datei · <kbd>i</kbd> inline<br><kbd>z</kbd> zu/auf · <kbd>c</kbd> Commits</div>')
    seite = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MR {html.escape(projekt)}</title>
<style>{CSS}</style><script src="zug.js"></script></head><body class="{'inline' if inline else ''}">
<header id="kopf"><div id="zug"></div><div class="zeile"><h1>{html.escape(projekt)}: {html.escape(bis)} → {html.escape(von)}</h1>
<span class="sub">{len(commits)} Commit(s) · {len(dateien)} Datei(en) · <span class="p">+{plus}</span> <span class="m">−{minus}</span> · erzeugt {datetime.now():%d.%m.%Y %H:%M}</span>
<span id="meldung"></span><button id="fertig" title="{html.escape(von)} auf diesen Stand setzen und zum nächsten Projekt">fertig ✓</button></div>
<details id="commits" open><summary>Commits</summary><div class="liste">{cl}</div>{td}</details></header>
<div class="rahmen"><aside class="seite"><div class="box">{hilfe}</div><nav id="liste"><h2>Dateien ({len(dateien)})</h2>{"".join(fl)}</nav></aside>
<main>{leer}{"".join(datei_html(n, d, *lokale_texte(wurzel, basis, bis, d)) for n, d in enumerate(dateien))}</main></div>
<script>const MR={mr};{JS}{JS_ZUG}</script></body></html>"""
    ziel = os.path.join(ORDNER, dateiname(projekt))
    ersetzen(ziel, seite)
    return ziel

def alles_erzeugen(von, bis, inline):
    from concurrent.futures import ThreadPoolExecutor
    schluessel()  # einmal vorab anlegen, sonst Wettlauf zwischen den Threads
    repos = finde_repos()
    with ThreadPoolExecutor(8) as ex:
        stats = list(ex.map(lambda r: statistik(r, von, bis), repos))
    wagen = zug_schreiben(stats)
    offen = {w["p"] for w in wagen if w["status"] == "offen"}
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(lambda r: seite_schreiben(r, von, bis, inline),
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
    if git(wurzel, "merge-base", "--is-ancestor", VON, sha, check=False) is None:
        return False, f"{projekt}: {VON} ist nicht Vorgänger des gesehenen Stands – nichts geändert."
    st = statistik(wurzel, VON, sha)
    log = git(wurzel, "log", "--format=%B", f"{VON}..{sha}")
    schliesst = sorted(set(re.findall(r"closes\s+todo:([\w.-]+)", log, flags=re.I)))
    git(wurzel, "branch", "-f", VON, sha)
    with SPERRE:
        r = runde_laden()
        r[projekt] = dict(st, p=projekt, datei=dateiname(projekt), status="fertig", tag=datetime.now().strftime("%Y-%m-%d"))
        with open(RUNDE, "w") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    zug_schreiben([statistik(w) for w in repos.values()])
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

