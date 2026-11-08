# ---------------------------------------------------------------- GitLab (über glab)

class GitLabFehler(Exception):
    pass

def enc(t):
    return urllib.parse.quote(str(t), safe="")

def glab(host, pfad, methode="GET", daten=None, roh=False):
    """glab api aufrufen. daten → JSON-Body. Rückgabe: geparstes JSON (bzw. Text bei roh)."""
    argv = shlex.split(KONF["glab"]) + ["api"]
    if host:
        argv += ["--hostname", host]
    if methode != "GET":
        argv += ["--method", methode]
    eingabe = None
    if daten is not None:
        argv += ["--header", "Content-Type: application/json", "--input", "-"]
        eingabe = json.dumps(daten)
    argv.append(pfad)
    try:
        r = subprocess.run(argv, input=eingabe, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=90)
    except FileNotFoundError:
        raise GitLabFehler(f"glab nicht gefunden ({KONF['glab']}) – installieren und „glab auth login“ ausführen")
    except subprocess.TimeoutExpired:
        raise GitLabFehler(f"glab api {pfad}: Zeitüberschreitung")
    if r.returncode:
        raise GitLabFehler(f"glab api {methode} {pfad.split('?')[0]}: {(r.stderr or r.stdout).strip()[:500]}")
    if roh:
        return r.stdout
    return json.loads(r.stdout) if r.stdout.strip() else None

def alle(host, pfad, max_seiten=50):
    """Paginierte Liste vollständig holen."""
    out, sep = [], "&" if "?" in pfad else "?"
    for s in range(1, max_seiten + 1):
        teil = glab(host, f"{pfad}{sep}per_page=100&page={s}")
        if not isinstance(teil, list):
            return out or teil
        out += teil
        if len(teil) < 100:
            break
    return out

URL_MR = re.compile(r"https?://([^/\s]+)/(.+?)/-/merge_requests/(\d+)")

def remote_info(ordner):
    """(host, projektpfad) aus dem origin-Remote eines Klons."""
    url = (git(ordner, "remote", "get-url", "origin", check=False) or "").strip()
    for rx in (r"^ssh://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+?)(?:\.git)?/?$",
               r"^https?://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?/?$",
               r"^[\w.-]+@([^:]+):(.+?)(?:\.git)?/?$"):
        m = re.match(rx, url)
        if m:
            return KONF["gitlab_host"] or m.group(1), m.group(2)
    raise GitLabFehler(f"kein GitLab-Remote „origin“ in {ordner}")

def ist_mr_ref(s):
    return bool(URL_MR.search(s) or re.fullmatch(r"!\d+", s) or re.fullmatch(r"[\w.\-/]+!\d+", s))

def mr_ref(s, ordner=None):
    """MR-URL, '!42' (Projekt aus git-Remote von ordner) oder 'gruppe/projekt!42' → {host, projekt, iid}."""
    s = str(s).strip()
    m = URL_MR.search(s)
    if m:
        return {"host": m.group(1), "projekt": m.group(2), "iid": int(m.group(3))}
    m = re.fullmatch(r"([\w.\-/]+)!(\d+)", s)
    if m:
        host = KONF["gitlab_host"]
        if not host and ordner:
            try:
                host = remote_info(ordner)[0]
            except GitLabFehler:
                pass
        return {"host": host, "projekt": m.group(1), "iid": int(m.group(2))}
    m = re.fullmatch(r"!?(\d+)", s)
    if m:
        host, projekt = remote_info(ordner or os.getcwd())
        return {"host": host, "projekt": projekt, "iid": int(m.group(1))}
    raise GitLabFehler(f"kein Merge-Request erkannt: {s}")

def mr_vollstaendig(mr):
    """Ohne Host (glab-Standardhost): Host und kanonischen Pfad aus der API holen."""
    if mr["host"]:
        return mr
    return mr_normalisieren(glab("", mr_pfad(mr)), mr)

def mr_id(mr):
    return f'{mr["host"]}/{mr["projekt"]}/{mr["iid"]}'

def mr_aus_id(s):
    teile = str(s).split("/")
    if len(teile) < 3 or not teile[-1].isdigit() or not re.fullmatch(r"[\w.:-]*", teile[0]) \
       or any(t in ("", ".", "..") for t in teile[1:-1]):
        raise GitLabFehler(f"ungültige MR-Kennung: {s}")
    return {"host": teile[0], "projekt": "/".join(teile[1:-1]), "iid": int(teile[-1])}

def mr_datei(mr):
    return re.sub(r"[^\w.-]", "_", f'{mr["host"] or "gitlab"}_{mr["projekt"]}_{mr["iid"]}')

def mr_pfad(mr):
    return f'projects/{enc(mr["projekt"])}/merge_requests/{mr["iid"]}'

def mr_normalisieren(meta, mr):
    """Kanonischen Projektpfad aus web_url übernehmen (Umbenennungen, Groß/klein)."""
    m = URL_MR.search(meta.get("web_url") or "")
    return {"host": mr["host"] or m.group(1), "projekt": m.group(2), "iid": int(m.group(3))} if m else mr

def mr_diffs(host, P):
    try:
        return alle(host, f"{P}/diffs")
    except GitLabFehler as e:
        if "404" not in str(e):
            raise
        return (glab(host, f"{P}/changes") or {}).get("changes", [])  # GitLab < 15.7

INHALT = {}

def inhalt(mr, sha, pfad):
    """Dateiinhalt an einem Stand: erst lokaler Klon (falls bekannt), sonst über die API. None = gibt es nicht."""
    k = (mr_id(mr), sha, pfad)
    if k in INHALT:
        return INHALT[k]
    text = None
    for ordner in lokale_klone(mr):
        text = git(ordner, "show", f"{sha}:{pfad}", check=False)
        if text is not None:
            break
    if text is None:
        try:
            text = glab(mr["host"], f'projects/{enc(mr["projekt"])}/repository/files/{enc(pfad)}/raw?ref={sha}', roh=True)
        except GitLabFehler:
            text = None
    if len(INHALT) > 3000:
        INHALT.clear()
    INHALT[k] = text
    return text

def lokale_klone(mr):
    out = []
    for schl in (mr["projekt"], f'{mr["host"]}/{mr["projekt"]}'):
        if schl in KONF["repos"]:
            out.append(os.path.expanduser(KONF["repos"][schl]))
    k = review_laden(mr).get("klon")
    if k:
        out.append(k)
    return [o for o in out if os.path.isdir(o)]

def kurzpfad(p):
    h = os.path.expanduser("~")
    return "~" + p[len(h):] if p and (p == h or p.startswith(h + os.sep)) else p

def lokal_pruefen(mr, refs, branch):
    """Ist ein lokaler Klon genau auf dem MR-Stand (Branch, Commit, keine lokalen Änderungen)?
    Rückgabe (ordner, grund): ordner = nutzbarer Klon, sonst grund (None = kein Klon eingetragen)."""
    klone, head = lokale_klone(mr), refs.get("head_sha")
    if not klone:
        return None, None
    if not head or not refs.get("base_sha"):
        return None, "MR-Stand unbekannt"
    gruende = []
    for o in dict.fromkeys(os.path.realpath(k) for k in klone):
        k = kurzpfad(o)
        akt = (git(o, "rev-parse", "HEAD", check=False) or "").strip()
        zweig = (git(o, "rev-parse", "--abbrev-ref", "HEAD", check=False) or "").strip()
        if akt != head or (branch and zweig != branch):
            gruende.append(f"{k} steht auf {zweig or '?'} {akt[:8]}, der MR auf {branch or '?'} {head[:8]}")
            continue
        geaendert = [z for z in (git(o, "status", "--porcelain", "--untracked-files=no",
                                     "--ignore-submodules=dirty", check=False) or "").splitlines() if z.strip()]
        if geaendert:
            gruende.append(f"{k}: {len(geaendert)} Datei(en) mit lokalen Änderungen (git status)")
            continue
        if git(o, "cat-file", "-e", refs["base_sha"] + "^{commit}", check=False) is None:
            gruende.append(f"{k}: Basis-Commit {refs['base_sha'][:8]} fehlt lokal (git fetch)")
            continue
        return o, None
    return None, "; ".join(gruende)

def blobs(ordner, specs):
    """Viele Dateiinhalte („rev:pfad“) mit einem git-cat-file-Aufruf. None = gibt es nicht."""
    specs = [s for s in dict.fromkeys(specs) if "\n" not in s]
    if not specs:
        return {}
    r = subprocess.run(["git", "-C", ordner, "cat-file", "--batch"], input=("\n".join(specs) + "\n").encode(),
                       capture_output=True)
    out, pos, daten = {}, 0, r.stdout
    for s in specs:
        nl = daten.find(b"\n", pos)
        if nl < 0:
            break
        kopf = daten[pos:nl].decode(errors="replace").split(); pos = nl + 1
        if len(kopf) != 3 or not kopf[2].isdigit():
            out[s] = None; continue
        n = int(kopf[2])
        out[s] = daten[pos:pos + n].decode("utf-8", errors="replace") if kopf[1] == "blob" else None
        pos += n + 1
    return out

def paare_und_hunks(d):
    """Je Diffzeile [alt, neu] (None = gibt es auf der Seite nicht) und Hunk-Grenzen [a, b, alen, blen]."""
    paare, hunks = [], []
    for h in d["hunks"]:
        a, b = h["a"], h["b"]
        al = sum(1 for t, _ in h["z"] if t != "+"); bl = sum(1 for t, _ in h["z"] if t != "-")
        hunks.append([h["a"], h["b"], al, bl])
        for t, _ in h["z"]:
            if t == " ": paare.append([a, b]); a += 1; b += 1
            elif t == "-": paare.append([a, None]); a += 1
            else: paare.append([None, b]); b += 1
    return paare, hunks

def alt_zeile(f, n):
    """Zeile n (neu) → Zeile im alten Stand; None bei hinzugefügter Zeile."""
    for a, b in f["paare"]:
        if b == n:
            return a
    delta = 0
    for a0, b0, al, bl in f["hunks"]:
        if b0 + bl <= n:
            delta += bl - al
    return n - delta

def im_diff(f, a, b):
    if b is not None:
        return any(p[1] == b and (a is None or p[0] == a) for p in f["paare"])
    return any(p[0] == a and p[1] is None for p in f["paare"])

def kontext_zeile(f, a, b):
    """Unveränderte Zeile außerhalb der Hunks (nachgeladener Kontext)?"""
    return (a is not None and b is not None and 0 < b <= (f.get("bn") or 0)
            and not any(p[1] == b for p in f["paare"]) and alt_zeile(f, b) == a)

def api_commit(c):
    msg = (c.get("message") or "").split("\n", 1)
    zeit = c.get("authored_date") or c.get("created_at") or ""
    try:
        zeit = datetime.fromisoformat(zeit.replace("Z", "+00:00")[:25]).astimezone().strftime("%d.%m. %H:%M")
    except ValueError:
        zeit = zeit[:16]
    return (c.get("short_id", ""), zeit, c.get("title") or msg[0], msg[1] if len(msg) > 1 else "")

MR_ORDNER = os.path.join(ORDNER, "mr")
VERSION = str(int(os.path.getmtime(os.path.realpath(__file__))))

def mr_seite(mr, meta=None, inline=False):
    """MR-Seite (im Cache je Stand) erzeugen. Rückgabe (html-pfad, struktur, mr)."""
    from concurrent.futures import ThreadPoolExecutor
    meta = meta or glab(mr["host"], mr_pfad(mr))
    mr = mr_normalisieren(meta, mr)
    host, P = mr["host"], mr_pfad(mr)
    refs = meta.get("diff_refs") or {}
    head = refs.get("head_sha") or meta.get("sha") or "leer"
    lokal, grund = lokal_pruefen(mr, refs, meta.get("source_branch", ""))
    quelle = "lokal" if lokal else "api" + (hashlib.sha1(grund.encode()).hexdigest()[:6] if grund else "")
    stamm = os.path.join(MR_ORDNER, f"{mr_datei(mr)}-{head[:12]}-{quelle}-{VERSION}")
    if os.path.exists(stamm + ".html") and os.path.exists(stamm + ".json"):
        struktur = json.load(open(stamm + ".json", encoding="utf-8"))
    else:
        if lokal:
            dateien = zerlegen(git(lokal, "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff",
                                   "-M", "-U3", refs["base_sha"], head))
        else:
            dateien = []
            for e in (mr_diffs(host, P) if refs.get("head_sha") else []):
                kopf = "diff --git a/x b/x\n" + ("new file mode\n" if e.get("new_file") else "") + \
                       ("deleted file mode\n" if e.get("deleted_file") else "") + \
                       ("rename from x\n" if e.get("renamed_file") else "")
                d = zerlegen(kopf + (e.get("diff") or ""))[0]
                d["alt"], d["neu"] = e.get("old_path") or e.get("new_path"), e.get("new_path") or e.get("old_path")
                if not d["hunks"] and (e.get("too_large") or e.get("collapsed")):
                    d["leer"] = "GitLab liefert für diese Datei keinen Diff (zu groß) – lokalen Klon auf den MR-Stand bringen"
                    d["ohne_diff"] = True
                dateien.append(d)
        commits = [api_commit(c) for c in reversed(alle(host, f"{P}/commits"))]
        def benoetigt(d):
            if d["binaer"] or not d["hunks"]:
                return None, None
            return (f'{refs["base_sha"]}:{d["alt"]}' if d["status"] != "neu" else None,
                    f'{head}:{d["neu"]}' if d["status"] != "gelöscht" else None)
        if lokal:  # alle Inhalte auf einmal in den Cache
            for spec, text in blobs(lokal, [s for d in dateien for s in benoetigt(d) if s]).items():
                sha, _, pfad = spec.partition(":")
                INHALT[(mr_id(mr), sha, pfad)] = text
        def texte(d):
            a, b = benoetigt(d)
            if a is None and b is None:
                return None, None
            return (inhalt(mr, *a.split(":", 1)) if a else "", inhalt(mr, *b.split(":", 1)) if b else "")
        with ThreadPoolExecutor(8) as ex:
            tx = list(ex.map(texte, dateien))
        struktur = {"mr": mr, "refs": {k: refs.get(k) for k in ("base_sha", "start_sha", "head_sha")},
                    "web_url": meta.get("web_url", ""), "quelle": "lokal" if lokal else "api",
                    "ordner": lokal, "grund": grund, "dateien": []}
        for d, (_, neu_text) in zip(dateien, tx):
            paare, hunks = paare_und_hunks(d)
            struktur["dateien"].append({"alt": d["alt"], "neu": d["neu"], "status": d["status"],
                                        "paare": paare, "hunks": hunks, "bn": zeilenzahl(neu_text) or None})
        ersetzen(stamm + ".html", mr_html(mr, meta, dateien, commits, tx, head, struktur))
        ersetzen(stamm + ".json", json.dumps(struktur, ensure_ascii=False))
    with SPERRE:
        st = review_laden(mr)
        st["mr"] = dict(mr, web_url=meta.get("web_url", ""), titel=meta.get("title", ""),
                        source_branch=meta.get("source_branch", ""), target_branch=meta.get("target_branch", ""))
        st["struktur"] = stamm + ".json"
        review_speichern(mr, st)
    return stamm + ".html", struktur, mr

def quelle_html(struktur, dateien):
    if struktur.get("quelle") == "lokal":
        return f'<span class="sub quelle-ok" title="Diff und Inhalte aus dem lokalen Klon">· lokal: {html.escape(kurzpfad(struktur["ordner"]))}</span>'
    ohne = sum(1 for d in dateien if d.get("ohne_diff"))
    grund = struktur.get("grund") or "kein lokaler Klon unter [repos] eingetragen"
    teile = ["Diff über die GitLab-API" + (f": <b>{ohne} Datei(en) ohne Diff</b>" if ohne else "") + "."]
    teile.append(f"Lokal nicht möglich – {html.escape(grund)}.")
    return f'<div id="quelle" class="warn">{" ".join(teile)}</div>'

def mr_html(mr, meta, dateien, commits, texte, head, struktur):
    slug = mr_id(mr)
    qh = quelle_html(struktur, dateien)
    band = qh if qh.startswith("<div") else ""
    lokal = struktur.get("quelle") == "lokal"  # nur lokal lassen sich Dateien einzeln nachladen
    plus = sum(d["plus"] for d in dateien); minus = sum(d["minus"] for d in dateien)
    web = meta.get("web_url", "")
    autor = (meta.get("author") or {}).get("name", "")
    beschr = (meta.get("description") or "").strip()
    cl = (f'<div class="commit"><b>Beschreibung</b><div class="nachricht">{html.escape(beschr)}</div></div>' if beschr else "") \
        + commits_html(commits)
    fl = dateiliste_html(dateien)
    leer = '<div class="leer">Keine Änderungen in diesem Merge-Request (oder GitLab berechnet den Diff noch).</div>' \
        if not dateien else ""
    daten = json.dumps({"modus": "gitlab", "projekt": slug, "id": slug, "sha": head, "k": schluessel(),
                        "dateien": len(dateien), "web_url": web})
    hilfe = ('<div class="hilfe">Klick auf Zeilennummer: Kommentar<br><kbd>n</kbd> nächster MR · '
             '<kbd>←</kbd>/<kbd>→</kbd> Datei<br><kbd>i</kbd> inline · <kbd>z</kbd> zu/auf · <kbd>c</kbd> Commits</div>')
    titel = f'{mr["projekt"]}!{mr["iid"]}'
    entwurf = '<span class="badge">Draft</span> ' if meta.get("draft") or meta.get("work_in_progress") else ""
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>!{mr["iid"]} {html.escape(meta.get("title", ""))}</title>
<style>{CSS}{CSS_REVIEW}</style></head><body class="gl">
<header id="kopf"><div id="zug"></div><div class="zeile"><h1>{entwurf}{html.escape(meta.get("title", ""))}</h1>
<a class="gl-link" href="{html.escape(web)}" target="_blank" rel="noopener">{html.escape(titel)} ↗</a>
<span class="sub">{html.escape(meta.get("source_branch", ""))} → {html.escape(meta.get("target_branch", ""))} · {html.escape(autor)} ·
{len(commits)} Commit(s) · {len(dateien)} Datei(en) · <span class="p">+{plus}</span> <span class="m">−{minus}</span> · Stand {html.escape(head[:8])}</span>{"" if band else qh}
<span id="rvstand" class="sub"></span><span id="meldung"></span>
<button id="fertig" title="Kommentare als Entwürfe („Review starten“) in den MR übertragen – veröffentlicht wird erst in GitLab">Review abschließen → GitLab</button></div>
<details id="commits"><summary>Beschreibung &amp; Commits</summary><div class="liste">{cl}</div></details>{band}</header>
<div class="rahmen"><aside class="seite"><div class="box">{hilfe}<details id="kliste" open><summary>Kommentare</summary><div></div></details></div>
<nav id="liste"><h2>Dateien ({len(dateien)})</h2>{"".join(fl)}</nav></aside>
<main>{leer}{"".join(datei_html(n, d, *texte[n], luecken=True, spaeter=lokal and spaeter_grund(d)) for n, d in enumerate(dateien))}</main></div>
<script>const MR={daten};{JS}{JS_ZUG}{JS_REVIEW}</script></body></html>"""

