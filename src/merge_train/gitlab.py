"""GitLab über glab: MR-Verweise lesen, Metadaten und Liste der MRs holen, lokale Klone finden."""
import json, os, re, shlex, subprocess, time
import urllib.parse
from datetime import datetime
from .einstellungen import KONF, ORDNER, SPERRE, ersetzen
from .git import aussen_log, git, kurzpfad, ref_sha
from .zustand import review_laden, review_speichern

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
    t0 = time.time()
    try:
        r = subprocess.run(argv, input=eingabe, capture_output=True, text=True, encoding="utf-8",
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


# Die Liste kommt aus dem Cache. GitLab wird nur im Güterbahnhof („↻ MRs“) gefragt.

MR_LISTE = os.path.join(ORDNER, "mrliste.json")


def mr_liste():
    try:
        d = json.load(open(MR_LISTE, encoding="utf-8"))
        return d.get("items") or [], d.get("zeit")
    except (OSError, ValueError):
        return [], None


def mr_liste_holen():
    """Offene MRs, bei denen ich Reviewer bin (bzw. mr_liste), aus GitLab holen und merken."""
    art = KONF["mr_liste"]
    if art == "keine":
        return [], None
    host = KONF["gitlab_host"]
    ich = glab(host, "user")["username"]
    param = {"reviewer": "reviewer_username", "assignee": "assignee_username", "author": "author_username"}.get(art, "reviewer_username")
    roh = glab(host, f"merge_requests?scope=all&state=opened&{param}={enc(ich)}&per_page=50") or []
    items = [{"web_url": it.get("web_url", ""), "title": it.get("title", ""), "changes_count": it.get("changes_count")}
             for it in roh if URL_MR.search(it.get("web_url", ""))]
    zeit = datetime.now().strftime("%d.%m. %H:%M")
    ersetzen(MR_LISTE, json.dumps({"items": items, "zeit": zeit}, ensure_ascii=False))
    return items, zeit


def geaenderte_dateien(mr, von, bis):
    """Pfade (alt und neu), die sich zwischen von und bis geändert haben (lokaler Klon)."""
    for o in lokale_klone(mr):
        out = git(o, "-c", "core.quotepath=false", "diff", "--name-status", "-M", von, bis, check=False)
        if out is not None:
            return {p for z in out.splitlines() for p in z.split("\t")[1:]}
    raise GitLabFehler(f"Commit {von} ist im lokalen Klon nicht bekannt (git fetch)")
