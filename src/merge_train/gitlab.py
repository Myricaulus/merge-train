"""GitLab über glab: MR-Verweise lesen, MR-Daten (in die Akte des Quell-Branches) und die Liste der MRs holen. Ein MR
ist eine Schicht auf seinem Branch (docs/branch-waggon.md): MrRef nennt ihn für GitLab, der Waggon ist der Branch."""
import glob, json, os, re, shlex, subprocess, time
import urllib.parse
from datetime import datetime
from typing import NamedTuple, Optional
from .einstellungen import DATEN, KONF, ORDNER, ersetzen
from .waggon import ABKUERZUNGEN, Fehler, Waggon
from .git import aussen_log, git, origin_teile
from .akte import ZWEIGE, _json_lesen, akte_archivieren, akte_bearbeiten, akte_lesen, akten_vereinigen, zweig_akten

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


class MrRef(NamedTuple):
    """Ein MR, wie GitLab ihn nennt (für die API). Der Waggon dazu ist sein Quell-Branch (mr_waggon)."""
    host: Optional[str]  # None = Standardhost von glab
    projekt: str         # gruppe/projekt
    iid: int

    @property
    def id(self):
        """Kennung „host/gruppe/projekt/42“ (alte Waggon-Kennung, Abkürzung für den Branch)."""
        return f"{self.host}/{self.projekt}/{self.iid}"

    @property
    def name(self):
        return f"{self.projekt}!{self.iid}"

    @property
    def url(self):
        """Seite: leitet auf den Branch weiter, fehlen die MR-Daten, bietet sie „MR-Daten holen“ an."""
        return "/mr/" + self.id


def mr_aus_kennung(kennung):
    """„host/gruppe/projekt/42“ → MrRef, sonst None."""
    teile = str(kennung).split("/")
    if len(teile) < 3 or not teile[-1].isdigit() or not re.fullmatch(r"[\w.:-]*", teile[0]) \
       or any(t in ("", ".", "..") for t in teile[1:-1]):
        return None
    return MrRef(teile[0] or None, "/".join(teile[1:-1]), int(teile[-1]))


def mr_von(akte):
    """MR der Schicht einer Akte (Feld „gitlab“), None ohne."""
    g = akte.get("gitlab") or {}
    return MrRef(g.get("host"), g["projekt"], int(g["iid"])) if g.get("projekt") and g.get("iid") else None


def mr_index():
    """Alle Branches mit MR-Schicht: {(gruppe/projekt klein, iid): (host, Waggon)}."""
    from urllib.parse import unquote
    out = {}
    for ordner in glob.glob(os.path.join(DATEN, ZWEIGE, "*")):
        for _, pfad in zweig_akten(unquote(os.path.basename(ordner))):
            akte = _json_lesen(pfad) or {}
            g = akte.get("gitlab") or {}
            if g.get("projekt") and g.get("iid") and akte.get("mr"):
                out[(g["projekt"].lower(), int(g["iid"]))] = (g.get("host"), Waggon.aus_dict(akte["mr"]))
    return out


def mr_waggon(mr, index=None):
    """Der Branch, dessen Akte diesen MR trägt, None, solange seine MR-Daten nicht geholt sind."""
    host, w = (mr_index() if index is None else index).get((mr.projekt.lower(), mr.iid), (None, None))
    return w if w and (not mr.host or not host or host == mr.host) else None


def _als_mr(kennung):
    """Abkürzung (waggon.ABKUERZUNGEN): MR-Kennung, MR-URL oder gruppe/projekt!42 → sein Branch."""
    mr = mr_aus_kennung(kennung)
    if not mr and (URL_MR.search(kennung) or re.fullmatch(r"[\w.\-/]+!\d+", kennung)):
        mr = mr_ref(kennung)
    return mr and mr_waggon(mr)


ABKUERZUNGEN.append(_als_mr)


def remote_info(ordner):
    """(host, projektpfad) aus dem origin-Remote eines Klons (host: gitlab_host, wenn gesetzt)."""
    teile = origin_teile(ordner)
    if not teile:
        raise Fehler(f"kein GitLab-Remote „origin“ in {ordner}")
    return KONF["gitlab_host"] or teile[0], teile[1]


def ist_mr_ref(s):
    return bool(URL_MR.search(s) or re.fullmatch(r"!\d+", s) or re.fullmatch(r"[\w.\-/]+!\d+", s))


def mr_ref(s, ordner=None):
    """MR-URL, '!42' (Projekt aus git-Remote von ordner) oder 'gruppe/projekt!42' → MrRef."""
    s = str(s).strip()
    m = URL_MR.search(s)
    if m:
        return MrRef(m.group(1), m.group(2), int(m.group(3)))
    m = re.fullmatch(r"([\w.\-/]+)!(\d+)", s)
    if m:
        host = KONF["gitlab_host"]
        if not host and ordner:
            try:
                host = remote_info(ordner)[0]
            except Fehler:
                pass
        return MrRef(host or None, m.group(1), int(m.group(2)))
    m = re.fullmatch(r"!?(\d+)", s)
    if m:
        host, projekt = remote_info(ordner or os.getcwd())
        return MrRef(host, projekt, int(m.group(1)))
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
    return MrRef(mr.host or m.group(1), m.group(2), int(m.group(3))) if m else mr


# MR-Daten (Titel, Beschreibung, Branches …) kommen aus dem Cache im Review-Stand. GitLab wird nur auf
# Anforderung gefragt: CLI (merge-train <MR>, agent pruefen/zeigen – also vom jira-review), Güterbahnhof, Abschließen.
META_FELDER = ("title", "description", "web_url", "source_branch", "target_branch", "draft", "work_in_progress",
               "diff_refs", "sha", "iid", "state")


class MetaFehlt(GitLabFehler):
    pass


# Felder der MR-Schicht in der Akte eines Branches: ein neuer MR für denselben Branch fängt sie neu an (die alten gehen
# mit der ganzen Akte als Kopie nach archiv/), die Fäden bleiben.
SCHICHT_FELDER = ("gitlab", "meta", "diskussionen", "diskussionen_abgehakt", "ich_id", "abgeschlossen", "reihenfolge",
                  "hinweise", "hinweis_dateien", "hinweis_agenten", "ausgecheckt", "auscheck_grund")


def alte_mr_akte(mr):
    """reviews/<mr>.json von vor Schritt 5 (MR-Akte ohne MR-Daten, akten_migrieren ließ sie liegen)."""
    return os.path.join(DATEN, "reviews", re.sub(r"[^\w.-]", "_", f"{mr.host or 'gitlab'}_{mr.projekt}_{mr.iid}") + ".json")


def mr_meta_holen(mr):
    """MR-Daten aus GitLab holen und in die Akte des Quell-Branches schreiben: das schaltet dort die MR-Schicht frei
    (Feld „gitlab“). Rückgabe (Waggon des Branches, meta)."""
    roh = glab(mr.host, mr_pfad(mr))
    mr = mr_normalisieren(roh, mr)
    meta = {k: roh.get(k) for k in META_FELDER}
    autor = roh.get("author") or {}
    meta["author"] = {"name": autor.get("name", ""), "id": autor.get("id")}  # id: eigener MR? (eigener_mr)
    meta["_zeit"] = datetime.now().strftime("%d.%m. %H:%M")
    if not meta.get("source_branch"):
        raise GitLabFehler(f"{mr.name}: GitLab nennt keinen Quell-Branch")
    w = Waggon(repo=mr.projekt.lower(), branch=meta["source_branch"])
    with akte_bearbeiten(w) as akte:
        alt = mr_von(akte)
        if alt and alt.iid != mr.iid:  # neuer MR für denselben Branch: die alte Schicht ins Archiv
            akte_archivieren(w, akte, f"mr{alt.iid}")
            for f in SCHICHT_FELDER:
                akte.pop(f, None)
            akte["kommentare"] = [k for k in akte["kommentare"] if k.get("nachrichten") is not None]
        frueher = alte_mr_akte(mr)
        if os.path.exists(frueher):
            akten_vereinigen(akte, _json_lesen(frueher) or {})
        akte["meta"] = meta
        akte["gitlab"] = {"host": mr.host, "projekt": mr.projekt, "iid": mr.iid, "web_url": meta.get("web_url") or "",
                          "titel": meta.get("title") or "", "source_branch": meta["source_branch"],
                          "target_branch": meta.get("target_branch") or ""}
    if os.path.exists(frueher):
        os.remove(frueher)
    return w, meta


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
    """Offene MRs mit diesem Quell-Branch, aus GitLab: [MrRef]."""
    out = []
    for it in glab(host, f"projects/{enc(projekt)}/merge_requests?state=opened&source_branch={enc(branch)}") or []:
        try:
            out.append(mr_ref(it.get("web_url", "")))
        except Fehler:
            pass
    return out


def mr_anlegen(host, projekt, quelle, ziel, titel, beschreibung, ordner):
    """MR in GitLab anlegen (docs/ein-waggon.md, Schritt 2) und seine MR-Daten holen: Der Branch bekommt seine
    MR-Schicht. Der Branch muss schon auf origin sein. Rückgabe: Waggon des Branches."""
    roh = glab(host, f"projects/{enc(projekt)}/merge_requests", "POST",
               {"source_branch": quelle, "target_branch": ziel, "title": titel, "description": beschreibung})
    return mr_uebernehmen(mr_ref((roh or {}).get("web_url", "")), ordner)


def mr_uebernehmen(mr, ordner):
    """MR-Daten holen und ordner als Klon merken (falls er sonst nicht zu finden ist). Rückgabe: Waggon des Branches."""
    w, _ = mr_meta_holen(mr)
    with akte_bearbeiten(w) as akte:
        akte["klon"] = ordner
    return w


# Die Liste kommt aus dem Cache. GitLab wird nur im Güterbahnhof („↻ MRs“) gefragt.

MR_LISTE = os.path.join(ORDNER, "mrliste.json")


_ICH = {}  # GitLab-Benutzer-id je Host


def ich(host):
    """Meine GitLab-Benutzer-id (ändert sich nicht, kostet aber eine eigene Anfrage)."""
    if host not in _ICH:
        _ICH[host] = (glab(host, "user") or {}).get("id")
    return _ICH[host]


def eigener_mr(w, akte=None):
    """Hat der Branch einen MR, bei dem ich Autor und nicht Reviewer bin? Dann ist er meine Entwicklung: der Agent setzt
    Wünsche um und committet (docs/ein-waggon.md). Laut gemerkter MR-Liste (Rollen), sonst Autor der MR-Daten gegen
    meinen GitLab-Benutzer. False ohne MR."""
    akte = akte or akte_lesen(w)
    mr = mr_von(akte)
    if not mr:
        return False
    ende = f"/{mr.projekt}/-/merge_requests/{mr.iid}".lower()
    rollen = [r for it in mr_liste()[0] if it.get("web_url", "").lower().endswith(ende) for r in it.get("rollen") or []]
    if rollen:
        return "author" in rollen and "reviewer" not in rollen
    autor = ((akte.get("meta") or {}).get("author") or {}).get("id")
    try:
        return bool(autor) and autor == ich(mr.host)
    except GitLabFehler:
        return False


def ausgecheckt(ordner):
    """Der im Klon ausgecheckte Branch (None bei losgelöstem HEAD)."""
    return (git(ordner, "symbolic-ref", "--short", "-q", "HEAD", check=False) or "").strip() or None


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


def geaenderte_dateien(klone, von, bis):
    """Pfade (alt und neu), die sich zwischen von und bis geändert haben (im ersten Klon, der beide kennt)."""
    for o in klone:
        out = git(o, "-c", "core.quotepath=false", "diff", "--name-status", "-M", von, bis, check=False)
        if out is not None:
            return {p for z in out.splitlines() for p in z.split("\t")[1:]}
    raise Fehler(f"Commit {von} ist im lokalen Klon nicht bekannt (git fetch)")
