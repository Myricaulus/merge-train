"""GitLab über glab: MR-Verweise lesen, Metadaten und Liste der MRs holen, lokale Klone finden."""
import json, os, re, shlex, subprocess, time
import urllib.parse
from datetime import datetime
from .einstellungen import KONF, ORDNER, ersetzen
from .waggon import Fehler, Waggon
from .git import arbeitsstand, aussen_log, git, git_oder_fehler, kurzpfad, ref_sha
from .akte import akte_bearbeiten, akte_lesen

class GitLabFehler(Fehler):
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
    t0 = time.time()
    try:
        r = subprocess.run(argv, input=eingabe or "", capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=90)
    except FileNotFoundError:
        raise GitLabFehler(f"glab nicht gefunden ({KONF['glab']}) – installieren und „glab auth login“ ausführen")
    except subprocess.TimeoutExpired:
        aussen_log("gitlab", host or "-", f"{methode} {pfad}", time.time() - t0, "Zeitüberschreitung")
        raise GitLabFehler(f"glab api {pfad}: Zeitüberschreitung")
    aussen_log("gitlab", host or "-", f"{methode} {pfad}", time.time() - t0,
               f"Fehler: {(r.stderr or r.stdout).strip()[:120]}" if r.returncode else f"ok {len(r.stdout)} B")
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
    raise Fehler(f"kein GitLab-Remote „origin“ in {ordner}")


def ist_mr_ref(s):
    return bool(URL_MR.search(s) or re.fullmatch(r"!\d+", s) or re.fullmatch(r"[\w.\-/]+!\d+", s))


def mr_ref(s, ordner=None):
    """MR-URL, '!42' (Projekt aus git-Remote von ordner) oder 'gruppe/projekt!42' → Waggon."""
    s = str(s).strip()
    m = URL_MR.search(s)
    if m:
        return Waggon(host=m.group(1), projekt=m.group(2), iid=int(m.group(3)))
    m = re.fullmatch(r"([\w.\-/]+)!(\d+)", s)
    if m:
        host = KONF["gitlab_host"]
        if not host and ordner:
            try:
                host = remote_info(ordner)[0]
            except Fehler:
                pass
        return Waggon(host=host, projekt=m.group(1), iid=int(m.group(2)))
    m = re.fullmatch(r"!?(\d+)", s)
    if m:
        host, projekt = remote_info(ordner or os.getcwd())
        return Waggon(host=host, projekt=projekt, iid=int(m.group(1)))
    raise Fehler(f"kein Merge-Request erkannt: {s}")


def mr_vollstaendig(mr):
    """Ohne Host (glab-Standardhost): Host und kanonischen Pfad aus der API holen."""
    if mr.host:
        return mr
    return mr_normalisieren(glab("", mr_pfad(mr)), mr)


def mr_pfad(mr):
    return f'projects/{enc(mr.projekt)}/merge_requests/{mr.iid}'


def mr_normalisieren(meta, mr):
    """Kanonischen Projektpfad aus web_url übernehmen (Umbenennungen, Groß/klein)."""
    m = URL_MR.search(meta.get("web_url") or "")
    return Waggon(host=mr.host or m.group(1), projekt=m.group(2), iid=int(m.group(3))) if m else mr


def lokale_klone(mr):
    """Klone des MR-Projekts: [repos], der gemerkte Klon aus der Akte, dann gefundene unter klon_ordner."""
    out = []
    for schl in (mr.projekt, f'{mr.host}/{mr.projekt}'):
        if schl in KONF["repos"]:
            out.append(os.path.expanduser(KONF["repos"][schl]))
    k = akte_lesen(mr).get("klon")
    if k:
        out.append(k)
    out += klon_suchen(mr.projekt)
    return [o for o in out if os.path.isdir(o)]


_REMOTE = {}  # Kandidat aus klon_ordner → Projektpfad seines origin ("" ohne GitLab-Remote), je Serverlauf


def klon_suchen(projekt):
    """Unter jedem Eintrag von klon_ordner: <ordner>/<letzter Teil des Projektpfads> bzw. <ordner>/<ganzer Pfad>,
    sofern dessen origin auf genau dieses Projekt zeigt (Groß/klein egal)."""
    ordner = KONF["klon_ordner"]
    out = []
    for d in ordner if isinstance(ordner, list) else [ordner]:
        for kandidat in dict.fromkeys(os.path.join(os.path.expanduser(d), t) for t in (projekt.rsplit("/", 1)[-1], projekt)):
            if not os.path.exists(os.path.join(kandidat, ".git")):
                continue
            if kandidat not in _REMOTE:
                try:
                    _REMOTE[kandidat] = remote_info(kandidat)[1]
                except Fehler:
                    _REMOTE[kandidat] = ""
            if _REMOTE[kandidat].lower() == projekt.lower():
                out.append(kandidat)
    return out


# MR-Daten (Titel, Beschreibung, Branches …) kommen aus dem Cache im Review-Stand. GitLab wird nur auf
# Anforderung gefragt: CLI (merge-train <MR>, agent pruefen/zeigen – also vom jira-review), Güterbahnhof, Abschließen.
META_FELDER = ("title", "description", "web_url", "source_branch", "target_branch", "draft", "work_in_progress",
               "diff_refs", "sha", "iid", "state")


class MetaFehlt(GitLabFehler):
    pass


def mr_meta_holen(mr):
    """MR-Daten aus GitLab holen und merken. Rückgabe (mr kanonisch, meta)."""
    roh = glab(mr.host, mr_pfad(mr))
    mr = mr_normalisieren(roh, mr)
    meta = {k: roh.get(k) for k in META_FELDER}
    autor = roh.get("author") or {}
    meta["author"] = {"name": autor.get("name", ""), "id": autor.get("id")}  # id: eigener MR? (quellen.eigener_mr)
    meta["_zeit"] = datetime.now().strftime("%d.%m. %H:%M")
    with akte_bearbeiten(mr) as akte:
        akte["meta"] = meta
        akte["mr"] = dict(mr.als_dict(), web_url=meta.get("web_url") or "", titel=meta.get("title") or "",
                        source_branch=meta.get("source_branch") or "", target_branch=meta.get("target_branch") or "")
    return mr, meta


def gitlab_klon(ordner):
    """(host, projekt), wenn origin des Klons ein GitLab-Projekt sein kann, sonst None – ohne GitLab zu fragen. GitHub
    zählt nicht (remote_info nimmt jeden Remote, mit gitlab_host als Host)."""
    url = (git(ordner, "remote", "get-url", "origin", check=False) or "").strip()
    if not url or "github.com" in url:
        return None
    try:
        return remote_info(ordner)
    except Fehler:
        return None


def mrs_zum_branch(host, projekt, branch):
    """Offene MRs mit diesem Quell-Branch, aus GitLab: [Waggon]."""
    out = []
    for it in glab(host, f"projects/{enc(projekt)}/merge_requests?state=opened&source_branch={enc(branch)}") or []:
        try:
            out.append(mr_ref(it.get("web_url", "")))
        except Fehler:
            pass
    return out


def mr_anlegen(host, projekt, quelle, ziel, titel, beschreibung, ordner):
    """MR in GitLab anlegen (docs/ein-waggon.md, Schritt 2), seine MR-Daten holen und den Klon merken: so findet ihn
    eigene_mrs, und der lokale Waggon geht im MR auf. Der Branch muss schon auf origin sein. Rückgabe: Waggon."""
    roh = glab(host, f"projects/{enc(projekt)}/merge_requests", "POST",
               {"source_branch": quelle, "target_branch": ziel, "title": titel, "description": beschreibung})
    return mr_uebernehmen(mr_ref((roh or {}).get("web_url", "")), ordner)


def mr_uebernehmen(mr, ordner):
    """MR-Daten holen und ordner als seinen Klon merken (eigene_mrs findet ihn dann). Rückgabe: Waggon (kanonisch)."""
    mr, _ = mr_meta_holen(mr)
    with akte_bearbeiten(mr) as akte:
        akte["klon"] = ordner
    return mr


_GEHOLT = set()  # (klon, quelle, ziel), für die mr_lokal schon einmal origin geholt hat (je Serverlauf)


def mr_lokal(mr, meta):
    """Lokaler Klon und Stand: Kopf = Quell-Branch (lokal, sonst origin), Basis = merge-base mit dem Ziel-Branch
    (bzw. die Basis aus GitLab, wenn GitLab beim letzten Holen auf demselben Stand war). Fehlt ein Branch, wird origin
    einmal geholt (git fetch, ändert nichts am Arbeitsverzeichnis). Rückgabe (ordner, refs)."""
    quelle, ziel = meta.get("source_branch") or "", meta.get("target_branch") or ""
    gl = meta.get("diff_refs") or {}
    gruende = []
    for o in dict.fromkeys(os.path.realpath(k) for k in lokale_klone(mr)):
        head, tgt = ref_sha(o, quelle), ref_sha(o, ziel, remote_zuerst=True)
        if (not head or not tgt) and (o, quelle, ziel) not in _GEHOLT:
            _GEHOLT.add((o, quelle, ziel))
            try:
                git_oder_fehler(o, "fetch", "-q", "origin")
            except Fehler as e:
                gruende.append(str(e)); continue
            head, tgt = ref_sha(o, quelle), ref_sha(o, ziel, remote_zuerst=True)
        if not head or not tgt:
            gruende.append(f"{kurzpfad(o)}: Branch {quelle if not head else ziel} fehlt (auch nach git fetch)"); continue
        zref = f"origin/{ziel}" if git(o, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{ziel}", check=False) else ziel  # wie tgt; see_also "ref": "ziel"
        if gl.get("head_sha") == head and gl.get("base_sha") and \
           git(o, "cat-file", "-e", gl["base_sha"] + "^{commit}", check=False) is not None:
            return o, {"base_sha": gl["base_sha"], "start_sha": gl.get("start_sha") or tgt, "head_sha": head, "ziel": zref}
        base = (git(o, "merge-base", tgt, head, check=False) or "").strip()
        if not base:
            gruende.append(f"{kurzpfad(o)}: kein gemeinsamer Vorgänger von {ziel} und {quelle}"); continue
        return o, {"base_sha": base, "start_sha": tgt, "head_sha": head, "ziel": zref}
    raise Fehler("kein lokaler Klon für " + f'{mr.projekt}!{mr.iid}: '
                       + ("; ".join(gruende) or "unter [repos] eintragen, klon_ordner setzen oder „merge-train agent zeigen“ im Repo aufrufen"))


# Die Liste kommt aus dem Cache. GitLab wird nur im Güterbahnhof („↻ MRs“) gefragt.

MR_LISTE = os.path.join(ORDNER, "mrliste.json")


_ICH = {}  # GitLab-Benutzer-id je Host


def ich(host):
    """Meine GitLab-Benutzer-id (ändert sich nicht, kostet aber eine eigene Anfrage)."""
    if host not in _ICH:
        _ICH[host] = (glab(host, "user") or {}).get("id")
    return _ICH[host]


def eigener_mr(w):
    """Bin ich Autor und nicht Reviewer dieses MR? Dann ist sein Quell-Branch meine Entwicklung: der Agent setzt Wünsche
    um und committet (docs/ein-waggon.md). Laut gemerkter MR-Liste (Rollen), sonst Autor der MR-Daten gegen meinen
    GitLab-Benutzer."""
    ende = f"/{w.projekt}/-/merge_requests/{w.iid}".lower()
    rollen = [r for it in mr_liste()[0] if it.get("web_url", "").lower().endswith(ende) for r in it.get("rollen") or []]
    if rollen:
        return "author" in rollen and "reviewer" not in rollen
    autor = ((akte_lesen(w).get("meta") or {}).get("author") or {}).get("id")
    try:
        return bool(autor) and autor == ich(w.host)
    except GitLabFehler:
        return False


def ausgecheckt(ordner):
    """Der im Klon ausgecheckte Branch (None bei losgelöstem HEAD)."""
    return (git(ordner, "symbolic-ref", "--short", "-q", "HEAD", check=False) or "").strip() or None


def eigener_arbeitsstand(mr, ordner, meta, refs):
    """Eigener MR, dessen Quell-Branch im Klon ausgecheckt ist: Kopf ist der Arbeitsstand (auch nicht Committetes,
    docs/ein-waggon.md); refs.commit_sha = letzter Commit des Branches, refs.arbeitsstand = True. Sonst refs."""
    quelle = meta.get("source_branch")
    if not quelle or ausgecheckt(ordner) != quelle or not eigener_mr(mr):
        return refs
    return dict(refs, head_sha=arbeitsstand(ordner), commit_sha=refs["head_sha"], arbeitsstand=True)


def mr_liste():
    try:
        d = json.load(open(MR_LISTE, encoding="utf-8"))
        return d.get("items") or [], d.get("zeit")
    except (OSError, ValueError):
        return [], None


ROLLEN = {"reviewer": "reviewer_username", "assignee": "assignee_username", "author": "author_username"}


def mr_liste_holen():
    """Offene MRs, bei denen ich Reviewer bzw. Autor bin (mr_liste, mehrere mit Komma), aus GitLab holen und merken.
    Jeder MR einmal, mit seinen Rollen."""
    arten = [a.strip() for a in str(KONF["mr_liste"]).split(",") if a.strip() in ROLLEN]
    if not arten:
        return [], None
    host = KONF["gitlab_host"]
    ich = glab(host, "user")["username"]
    items = {}
    for art in arten:
        roh = glab(host, f"merge_requests?scope=all&state=opened&{ROLLEN[art]}={enc(ich)}&per_page=50") or []
        for it in roh:
            url = it.get("web_url", "")
            if URL_MR.search(url):
                x = items.setdefault(url, {"web_url": url, "title": it.get("title", ""),
                                           "changes_count": it.get("changes_count"), "rollen": []})
                x["rollen"].append(art)
    items = list(items.values())
    zeit = datetime.now().strftime("%d.%m. %H:%M")
    ersetzen(MR_LISTE, json.dumps({"items": items, "zeit": zeit}, ensure_ascii=False))
    return items, zeit


def geaenderte_dateien(mr, von, bis):
    """Pfade (alt und neu), die sich zwischen von und bis geändert haben (lokaler Klon)."""
    for o in lokale_klone(mr):
        out = git(o, "-c", "core.quotepath=false", "diff", "--name-status", "-M", von, bis, check=False)
        if out is not None:
            return {p for z in out.splitlines() for p in z.split("\t")[1:]}
    raise Fehler(f"Commit {von} ist im lokalen Klon nicht bekannt (git fetch)")
