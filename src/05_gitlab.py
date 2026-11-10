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
    if mr.get("lokal"):
        return "projekt:" + mr["lokal"]
    return f'{mr["host"]}/{mr["projekt"]}/{mr["iid"]}'

def mr_aus_id(s):
    """Seiten-Kennung → Ref. „projekt:name“ = lokales Projekt ({"lokal": name}), sonst GitLab-MR."""
    if str(s).startswith("projekt:"):
        name = str(s)[8:]
        if not name or any(t in ("", ".", "..") for t in name.split("/")):
            raise GitLabFehler(f"ungültige Projekt-Kennung: {s}")
        return {"lokal": name}
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

# MR-Daten (Titel, Beschreibung, Branches …) kommen aus dem Cache im Review-Stand. GitLab wird nur auf
# Anforderung gefragt: CLI (merge-train <MR>, agent pruefen/zeigen – also vom jira-review), Güterbahnhof, Abschließen.
META_FELDER = ("title", "description", "web_url", "source_branch", "target_branch", "draft", "work_in_progress",
               "diff_refs", "sha", "iid")

class MetaFehlt(GitLabFehler):
    pass

def mr_meta_holen(mr):
    """MR-Daten aus GitLab holen und merken. Rückgabe (mr kanonisch, meta)."""
    roh = glab(mr["host"], mr_pfad(mr))
    mr = mr_normalisieren(roh, mr)
    meta = {k: roh.get(k) for k in META_FELDER}
    meta["author"] = {"name": (roh.get("author") or {}).get("name", "")}
    meta["_zeit"] = datetime.now().strftime("%d.%m. %H:%M")
    with SPERRE:
        st = review_laden(mr)
        st["meta"] = meta
        st["mr"] = dict(mr, web_url=meta.get("web_url") or "", titel=meta.get("title") or "",
                        source_branch=meta.get("source_branch") or "", target_branch=meta.get("target_branch") or "")
        review_speichern(mr, st)
    return mr, meta

def ref_sha(ordner, name, remote_zuerst=False):
    for r in ([f"refs/remotes/origin/{name}", f"refs/heads/{name}"] if remote_zuerst
              else [f"refs/heads/{name}", f"refs/remotes/origin/{name}"]):
        s = (git(ordner, "rev-parse", "--verify", "-q", r + "^{commit}", check=False) or "").strip()
        if s:
            return s
    return None

def mr_lokal(mr, meta):
    """Lokaler Klon und Stand: Kopf = Quell-Branch (lokal, sonst origin), Basis = merge-base mit dem Ziel-Branch
    (bzw. die Basis aus GitLab, wenn GitLab beim letzten Holen auf demselben Stand war). Rückgabe (ordner, refs)."""
    quelle, ziel = meta.get("source_branch") or "", meta.get("target_branch") or ""
    gl = meta.get("diff_refs") or {}
    gruende = []
    for o in dict.fromkeys(os.path.realpath(k) for k in lokale_klone(mr)):
        head, tgt = ref_sha(o, quelle), ref_sha(o, ziel, remote_zuerst=True)
        if not head or not tgt:
            gruende.append(f"{kurzpfad(o)}: Branch {quelle if not head else ziel} fehlt (git fetch)"); continue
        if gl.get("head_sha") == head and gl.get("base_sha") and \
           git(o, "cat-file", "-e", gl["base_sha"] + "^{commit}", check=False) is not None:
            return o, {"base_sha": gl["base_sha"], "start_sha": gl.get("start_sha") or tgt, "head_sha": head}
        base = (git(o, "merge-base", tgt, head, check=False) or "").strip()
        if not base:
            gruende.append(f"{kurzpfad(o)}: kein gemeinsamer Vorgänger von {ziel} und {quelle}"); continue
        return o, {"base_sha": base, "start_sha": tgt, "head_sha": head}
    raise GitLabFehler("kein lokaler Klon für " + f'{mr["projekt"]}!{mr["iid"]}: '
                       + ("; ".join(gruende) or "unter [repos] eintragen oder „merge-train agent zeigen“ im Repo aufrufen"))

def mr_seite(mr, ansicht=None):
    """MR-Seite aus dem lokalen Klon (im Cache je Stand). Rückgabe (html-pfad, struktur, mr). Keine GitLab-Anfrage."""
    st = review_laden(mr)
    meta = st.get("meta")
    if not meta:
        raise MetaFehlt(f'Für {mr["projekt"]}!{mr["iid"]} gibt es noch keine MR-Daten – „merge-train agent zeigen …“ '
                        "(jira-review) oder im Güterbahnhof „MR-Daten holen“")
    ordner, refs = mr_lokal(mr, meta)
    mh = hashlib.sha1(json.dumps(meta, sort_keys=True).encode()).hexdigest()[:6]
    praefix = os.path.join(MR_ORDNER, f'{mr_datei(mr)}-{refs["head_sha"][:12]}-{refs["base_sha"][:12]}-{mh}')
    pfad, struktur = seite_bauen(mr_id(mr), ordner, refs, praefix,
                                 lambda *a: mr_html(mr, meta, *a), ansicht)
    if not ansicht:
        with SPERRE:  # Kommentare, Hinweise und Gespräch beziehen sich immer auf den ganzen MR
            for m in (mr, gk(mr)):
                s = review_laden(m)
                if s.get("struktur") != praefix_json(praefix):
                    s["struktur"] = praefix_json(praefix)
                    review_speichern(m, s)
    return pfad, struktur, mr

def mr_html(mr, meta, dateien, commits, texte, struktur):
    slug = mr_id(mr)
    head = struktur["refs"]["head_sha"]
    ans = struktur.get("ansicht")
    web = meta.get("web_url") or ""
    autor = (meta.get("author") or {}).get("name", "")
    beschr = (meta.get("description") or "").strip()
    cl = (f'<div class="commit"><b>Beschreibung</b><div class="nachricht">{html.escape(beschr)}</div></div>' if beschr else "") \
        + commits_html(commits, commit_knoepfe(f"/mr/{slug}", commits, ans))
    leer = '<div class="leer">Keine Änderungen in diesem Merge-Request.</div>' if not dateien else ""
    lesen = bool(ans and ans["art"] == "commit")
    daten = seiten_daten(slug, head, len(dateien), ans, modus="gitlab", projekt=slug, web_url=web)
    klick = ("nur lesen" if lesen else "Klick auf Zeilennummer (rechts): Kommentar" if ans
             else "Klick auf Zeilennummer: Kommentar")
    hilfe = (f'<div class="hilfe">{klick}<br><kbd>n</kbd> nächster MR · '
             '<kbd>←</kbd>/<kbd>→</kbd> Datei<br><kbd>i</kbd> inline · <kbd>z</kbd> zu/auf · <kbd>c</kbd> Commits</div>')
    ah = ansicht_html(f"/mr/{slug}", "ganzer MR", ans) if ans else ""
    gl_head = (meta.get("diff_refs") or {}).get("head_sha")
    abw = (f'<div class="warn">GitLab stand beim letzten Holen ({html.escape(meta.get("_zeit") or "?")}) auf '
           f'{html.escape(gl_head[:8])}, lokal ist {html.escape(head[:8])} – Branch aktualisieren oder MR-Daten holen.</div>'
           if gl_head and gl_head != head else "")
    titel = f'{mr["projekt"]}!{mr["iid"]}'
    entwurf = '<span class="badge">Draft</span> ' if meta.get("draft") or meta.get("work_in_progress") else ""
    knoepfe = ('<button id="feedback" hidden disabled title="Fragen an den Agenten abschicken (gehen nicht nach GitLab)">Fragen senden</button>\n'
               '<button id="starten" hidden title="Konsole mit dem Agenten im Klon öffnen (todo los)">▶ Session starten</button>\n'
               f'<button id="fertig"{" hidden" if lesen else ""} title="Kommentare als Entwürfe („Review starten“) in den MR '
               'übertragen – veröffentlicht wird erst in GitLab">Review abschließen → GitLab</button>')
    return diff_seite(titel=f'!{mr["iid"]} {html.escape(meta.get("title") or "")}', gitlab=True, daten=daten, head=head,
                      dateien=dateien, texte=texte, commits=commits, h1=f'{entwurf}{html.escape(meta.get("title") or "")}',
                      knoepfe=knoepfe, commits_titel="Beschreibung &amp; Commits", commits_liste=cl, nach_commits=abw + ah,
                      nach_h1=f'\n<a class="gl-link" href="{html.escape(web)}" target="_blank" rel="noopener">{html.escape(titel)} ↗</a>',
                      sub_vor=f'{html.escape(meta.get("source_branch") or "")} → {html.escape(meta.get("target_branch") or "")} · {html.escape(autor)} ·\n',
                      nach_sub=f'\n<span class="sub quelle-ok" title="Diff und Inhalte aus dem lokalen Klon">· lokal: {html.escape(kurzpfad(struktur["ordner"]))}</span>',
                      hilfe=hilfe, leer=leer)

def gleise_html(gitlab):
    """Kopf: der Güterbahnhof über die ganze Breite. Kulisse (bahnhof.webp), davor Verladegebäude und Förderband
    (zeichnet zug.js in #anlage, weil das Band bis zur Bildschirmmitte reicht) und der Zug. Die Knöpfe sitzen im
    Leitstand des Gebäudes: GitLab nur auf Knopfdruck, lokal schauen sie nach neuen Änderungen."""
    if gitlab:
        fehlt = not shutil.which((shlex.split(KONF["glab"]) or ["glab"])[0])
        def knopf(g, text, titel):  # ohne glab ausgegraut: der Bahnhof steht, aber es fährt nichts
            if fehlt:
                return f'<button data-g="{g}" disabled title="glab fehlt ({html.escape(KONF["glab"])}) – siehe README">{text}</button>'
            return f'<button data-g="{g}" title="{titel}">{text}</button>'
        knoepfe = (knopf("mrliste", "↻ MRs", "MRs, bei denen ich Reviewer bin, aus GitLab holen")
                   + knopf("mrdaten", "↻ MR-Daten", "Titel, Beschreibung, Branches und GitLab-Stand dieses MR neu holen"))
        titel = "Güterbahnhof: GitLab wird nur hier (und beim Abschließen) gefragt"
    else:
        knoepfe = '<button data-l="neu" title="Nach neuen lokalen Änderungen schauen">↻ Änderungen</button>'
        titel = "Güterbahnhof"
    return (f'<div class="gleise szene" style="--bild:url(data:image/webp;base64,{BAHNHOF_BILD})">'
            '<svg id="anlage" aria-hidden="true"></svg>'
            f'<div id="bahnhof" title="{titel}"><div class="bh-knoepfe">{knoepfe}</div><span id="bhzeit"></span></div>'
            '<div id="zug"></div></div>')

BAHNHOF_BILD = r"""@einbetten web/bahnhof.webp@"""
