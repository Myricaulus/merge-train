"""Alles, was das lokale git fragt: Aufruf mit Protokoll, Diff zerlegen, Arbeitsstand, Repos finden, Dateiinhalte."""
import glob, hashlib, os, re, shutil, subprocess, threading, time
from datetime import datetime
from .einstellungen import ARBEITSSTAND, KONF, KONFIG_DATEI, ORDNER, PROJEKTE, PROJEKTE_LISTE, dateiname, projektname
from .waggon import Fehler, von_bis, zweige_gewaehlt

ANLASS = threading.local()  # wofür die Anfrage ist (Server: Pfad/Aktion, CLI: Befehl) – nur fürs Log


_LOG_SPERRE, _LOG_TAG = threading.Lock(), [None]


def anlass():
    return getattr(ANLASS, "name", None) or "-"


def aussen_log(quelle, wo, was, dauer, ergebnis):
    """Anfragen an die Quellen (lokales git, GitLab) protokollieren: ~/.cache/merge-train/aussen-<datum>.log, eine Datei
    je Tag, log_tage Tage aufbewahrt (0 = aus). Zum Erkennen, was langsam ist."""
    try:
        tage = int(KONF.get("log_tage", 7) or 0)
    except (TypeError, ValueError):
        tage = 7
    if tage <= 0 or not ORDNER:
        return
    from datetime import timedelta
    jetzt = datetime.now()
    zeile = (f"{jetzt:%H:%M:%S}.{jetzt.microsecond // 1000:03d} {dauer:7.3f}s {quelle:<6} {anlass():<32} "
             f"{wo}  {was}  {ergebnis}\n")
    try:
        with _LOG_SPERRE:
            os.makedirs(ORDNER, exist_ok=True)
            if _LOG_TAG[0] != jetzt.date():  # einmal am Tag: alte Dateien weg
                _LOG_TAG[0] = jetzt.date()
                grenze = f"aussen-{jetzt - timedelta(days=tage - 1):%Y-%m-%d}.log"
                for p in glob.glob(os.path.join(ORDNER, "aussen-*.log")):
                    if os.path.basename(p) < grenze:
                        os.remove(p)
            with open(os.path.join(ORDNER, f"aussen-{jetzt:%Y-%m-%d}.log"), "a", encoding="utf-8") as f:
                f.write(zeile)
    except OSError:
        pass


def git(ordner, *a, check=True, env=None, ok=(0,)):
    """git -C ordner …: stdout, None bei einem Exit-Code außerhalb ok (check: Ausnahme). ok=(0, 1) für diff --no-index."""
    t0 = time.time()
    r = subprocess.run(["git", "-C", ordner, *a], capture_output=True,
                       text=True, errors="replace", env=env)
    aussen_log("git", os.path.basename(str(ordner).rstrip("/")), "git " + " ".join(a)[:200], time.time() - t0,
               f"exit {r.returncode}" if r.returncode not in ok else f"ok {len(r.stdout)} B")
    if check and r.returncode not in ok:
        raise subprocess.CalledProcessError(r.returncode, a, r.stdout, r.stderr)
    return r.stdout if r.returncode in ok else None


def zerlegen(diff):
    """Unified-Diff in Dateien → Hunks → Zeilen zerlegen. fassung: Blobs und Modus aus den Kopfzeilen („index a..b
    100644“, „old/new mode“), mit --full-index ganz – gleich, solange die Datei vorher und nachher gleich ist."""
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
        elif h is None and z.startswith(("index ", "old mode ", "new mode ")):
            d["fassung"] = (d.get("fassung", "") + " " + z.split(" ", 1)[1]).strip()
        elif z.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)", z)
            h = {"a": int(m.group(1)), "b": int(m.group(2)), "kopf": m.group(3).strip(), "z": []}
            d["hunks"].append(h)
        elif h is not None and z[:1] in (" ", "+", "-"):
            h["z"].append((z[0], z[1:]))
            if z[0] == "+": d["plus"] += 1
            if z[0] == "-": d["minus"] += 1
    return dateien


def ist_repo(ordner):
    """Ordner ist ein Repo: .git ist ein Ordner oder (Worktree, Submodul) eine Datei."""
    return os.path.exists(os.path.join(ordner, ".git"))


def projekt_ordner(name):
    """Projektname → Ordner (unter einem Eintrag von projekte oder ein dort genanntes Repo)."""
    for p in PROJEKTE_LISTE:
        if os.path.isdir(os.path.join(p, name)) and not ist_repo(p):
            return os.path.join(p, name)
        if os.path.basename(p.rstrip("/")) == name and ist_repo(p):
            return p
    return os.path.join(PROJEKTE, name)


def branch_von(wurzel):
    """Branch, zu dem die Fäden eines lokalen Projekts gehören: bis, bei bis = "arbeitsstand" der ausgecheckte Branch
    (losgelöster HEAD: "HEAD")."""
    bis = von_bis(projektname(wurzel))[1]
    if bis != ARBEITSSTAND:
        return bis
    return (git(wurzel, "symbolic-ref", "--short", "-q", "HEAD", check=False) or "").strip() or "HEAD"


_ARBEIT = {}


def eigener_commit_env(index):
    """Umgebung für eigene Commit-Objekte (Arbeitsstand, stand_mit): eigener Index, feste Namen und Daten – gleicher
    Inhalt ergibt denselben sha, die Seite bleibt im Cache."""
    return dict(os.environ, GIT_INDEX_FILE=index, GIT_AUTHOR_NAME="merge-train", GIT_AUTHOR_EMAIL="merge-train@localhost",
                GIT_COMMITTER_NAME="merge-train", GIT_COMMITTER_EMAIL="merge-train@localhost",
                GIT_AUTHOR_DATE="2000-01-01T00:00:00+0000", GIT_COMMITTER_DATE="2000-01-01T00:00:00+0000")


def stand_mit(wurzel, head, fassungen, text):
    """Commit-Objekt mit dem Baum von head, in dem jede Datei aus fassungen {pfad: commit} so steht wie in jenem Commit
    (None oder dort nicht vorhanden: fehlt) – z. B. die Basis eines Myrling-Laufs, dessen Dateien je eine eigene
    Vergleichsbasis haben. Elternteil head, kein Ref; ändert sich nichts: head."""
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        env = eigener_commit_env(os.path.join(t, "index"))
        git(wurzel, "read-tree", head, env=env)
        for pfad, sha in fassungen.items():
            eintrag = (git(wurzel, "ls-tree", "-z", sha, "--", pfad, check=False) or "").split("\0")[0] if sha else ""
            if eintrag:  # „100755 blob <sha>\t<pfad>“: Modus mitnehmen, sonst zeigt der Diff eine Rechte-Änderung
                modus, _, blob = eintrag.split("\t", 1)[0].split(" ")
                git(wurzel, "update-index", "--add", "--cacheinfo", f"{modus},{blob},{pfad}", env=env)
            else:
                git(wurzel, "update-index", "--force-remove", "--", pfad, env=env)
        baum = git(wurzel, "write-tree", env=env).strip()
        if baum == git(wurzel, "rev-parse", head + "^{tree}").strip():
            return head
        return git(wurzel, "commit-tree", baum, "-p", head, "-m", text, env=env).strip()


def arbeitsstand(wurzel):
    """Das Arbeitsverzeichnis (geänderte, neue nicht ignorierte und gelöschte Dateien) als Commit-Objekt, ohne Index,
    Branch oder Dateien anzufassen: Kopie des Index, add -A, write-tree, commit-tree (eigener_commit_env). Ohne Änderungen: HEAD."""
    import tempfile
    head = git(wurzel, "rev-parse", "HEAD").strip()
    status = git(wurzel, "status", "--porcelain=v1", "-z", "--untracked-files=all", check=False,  # Index nicht auffrischen:
                 env=dict(os.environ, GIT_OPTIONAL_LOCKS="0")) or ""  # sonst meldet der Beobachter die eigene Prüfung
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
        env = eigener_commit_env(idx)
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
    """Stand für bis (Standard: bis des Projekts): Branch/Ref oder der Arbeitsstand."""
    bis = bis or von_bis(projektname(wurzel))[1]
    return arbeitsstand(wurzel) if bis == ARBEITSSTAND else git(wurzel, "rev-parse", bis).strip()


def wip_name(von):
    """Branch des Teilstands (Teilabgabe, abhaken.teil_abgeben): <von>-wip."""
    return von + "-wip"


def wip_sha(wurzel, von):
    """sha des Teilstands <von>-wip, None ohne Teilstand."""
    r = git(wurzel, "rev-parse", "--verify", "-q", wip_name(von) + "^{commit}", check=False)
    return r.strip() if r else None


def diff_basis(wurzel, von, bis):
    """Basis des Diffs eines lokalen Projekts (bis = sha): der Teilstand <von>-wip, sonst der gemeinsame Vorgänger."""
    return wip_sha(wurzel, von) or git(wurzel, "merge-base", von, bis).strip()


def ohne_basis(wurzel, von=None, bis=None):
    """True, wenn von und bis (Standard: die des Projekts) keinen gemeinsamen Vorgänger und keinen Teilstand haben,
    z. B. nach einem Rebase ab der Wurzel, solange von noch auf der alten Historie steht: diff_basis ginge nicht."""
    if not (von and bis):
        von, bis = von_bis(projektname(wurzel))
    return not wip_sha(wurzel, von) and git(wurzel, "merge-base", von, "HEAD" if bis == ARBEITSSTAND else bis,
                                            check=False) is None


def fehlende_zweige(wurzel, von=None, bis=None):
    """Welche von von/bis (Standard: die des Projekts) es im Klon nicht gibt."""
    if not (von and bis):
        von, bis = von_bis(projektname(wurzel))
    return [b for b, ref in ((von, von), (bis, "HEAD" if bis == ARBEITSSTAND else bis))
            if not git(wurzel, "rev-parse", "--verify", "-q", ref + "^{commit}", check=False)]


def finde_repos(alle=False):
    """Alle Repos aus projekte (Ordner: auch eine Ebene tiefer, z. B. cachy-patch/*; oder direkt ein Repo), in denen es
    von und bis des Projekts gibt. alle: auch die, denen ein Branch fehlt, sofern ausdrücklich gemeint (direkt unter
    projekte genannt oder mit eigenen Zweigen in der Einstellung bzw. auf der Seite) – zum Einstellen im Zug."""
    out, kandidaten = [], []
    for wo in PROJEKTE_LISTE:
        if ist_repo(wo):  # direkt ein Repo
            kandidaten.append((wo, True)); continue
        for e in sorted(os.listdir(wo)) if os.path.isdir(wo) else []:
            d = os.path.join(wo, e)
            if not os.path.isdir(d): continue
            kandidaten += [(d, False)] if ist_repo(d) else \
                [(os.path.join(d, u), False) for u in sorted(os.listdir(d)) if ist_repo(os.path.join(d, u))]
    for k, genannt in kandidaten:
        if not fehlende_zweige(k):
            out.append(k)
        elif alle:
            p = projektname(k)
            if genannt or p in (KONF.get("zweige") or {}) or zweige_gewaehlt(p):
                out.append(k)
    return out


def statistik(wurzel, von=None, bis=None):
    von, bis = von or von_bis(projektname(wurzel))[0], bis_sha(wurzel, bis)
    basis = diff_basis(wurzel, von, bis)
    plus = minus = dateien = 0
    for z in git(wurzel, "diff", "--numstat", "--find-renames", basis, bis).splitlines():
        a, b, _ = z.split("\t", 2); dateien += 1
        if a != "-": plus += int(a); minus += int(b)
    log = git(wurzel, "log", "--format=%B", f"{von}..{bis}")
    return {"p": projektname(wurzel), "datei": dateiname(projektname(wurzel)), "plus": plus, "minus": minus,
            "dateien": dateien, "commits": int(git(wurzel, "rev-list", "--count", f"{von}..{bis}")),
            "todos": sorted(set(re.findall(r"todo:([\w.-]+)", log))), "status": "offen",
            "sha": bis}


def kurzpfad(p):
    h = os.path.expanduser("~")
    return "~" + p[len(h):] if p and (p == h or p.startswith(h + os.sep)) else p


def blobs(ordner, specs):
    """Viele Dateiinhalte („rev:pfad“) mit einem git-cat-file-Aufruf. None = gibt es nicht."""
    specs = [s for s in dict.fromkeys(specs) if "\n" not in s]
    if not specs:
        return {}
    t0 = time.time()
    r = subprocess.run(["git", "-C", ordner, "cat-file", "--batch"], input=("\n".join(specs) + "\n").encode(),
                       capture_output=True)
    aussen_log("git", os.path.basename(str(ordner).rstrip("/")), f"git cat-file --batch ({len(specs)} Dateien)",
               time.time() - t0, f"ok {len(r.stdout)} B")
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


def ref_sha(ordner, name, remote_zuerst=False):
    for r in ([f"refs/remotes/origin/{name}", f"refs/heads/{name}"] if remote_zuerst
              else [f"refs/heads/{name}", f"refs/remotes/origin/{name}"]):
        s = (git(ordner, "rev-parse", "--verify", "-q", r + "^{commit}", check=False) or "").strip()
        if s:
            return s
    return None


def git_oder_fehler(ordner, *a, rest=300):
    """git wie git(), ein Fehlschlag wird zum Fehler mit der Meldung von git (für die Seite, die letzten rest Zeichen)."""
    try:
        return git(ordner, *a)
    except subprocess.CalledProcessError as e:
        raise Fehler(f"git {a[0]} in {kurzpfad(ordner)}: {((e.stderr or '') + (e.output or '')).strip()[-rest:]}")


def origin_voraus(ordner, sha, ziel):
    """Ist ziel (z. B. der Stand in GitLab) ein Nachfolger von sha – oder lokal noch gar nicht da (erst holen)?"""
    if git(ordner, "cat-file", "-e", ziel + "^{commit}", check=False) is None:
        return True
    return git(ordner, "merge-base", "--is-ancestor", sha, ziel, check=False) is not None


def stand_zu_gitlab(ordner, branch, lokal, gl):
    """Wie steht der lokale Quell-Branch (lokal) zum zuletzt geholten GitLab-Stand (gl)? None, wenn gleich, sonst
    origin_voraus (erst holen), gepusht (origin/<branch> ist schon lokal, GitLab noch nicht neu geholt), lokal_voraus
    (neue Commits, noch nicht gepusht), umgeschrieben (lokal stand der Branch auf gl und wurde umgeschrieben, z. B.
    Rebase: Force-Push mit Lease) oder abweichend (auseinandergelaufen, ohne dass lokal auf gl stand)."""
    if not gl or gl == lokal:
        return None
    if origin_voraus(ordner, lokal, gl):
        return "origin_voraus"
    if (git(ordner, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{branch}^{{commit}}", check=False) or "").strip() == lokal:
        return "gepusht"
    if git(ordner, "merge-base", "--is-ancestor", gl, lokal, check=False) is not None:
        return "lokal_voraus"
    reflog = (git(ordner, "reflog", "show", "--format=%H", f"refs/heads/{branch}", "--", check=False) or "").split()
    return "umgeschrieben" if gl in reflog else "abweichend"


def branch_pushen(ordner, branch, gl):
    """Quell-Branch nach origin pushen: vorspulen bzw. – umgeschrieben – Force-Push mit Lease auf gl (den Stand, den
    GitLab zuletzt hatte; ist origin inzwischen woanders, lehnt git ab). Andere Stände: Fehler. Rückgabe: Text."""
    lokal = (git(ordner, "rev-parse", "--verify", "-q", f"refs/heads/{branch}^{{commit}}", check=False) or "").strip()
    art = stand_zu_gitlab(ordner, branch, lokal, gl) if lokal else None
    if art not in ("lokal_voraus", "umgeschrieben"):
        raise Fehler(f"{branch}: nichts zu pushen ({STAND_TEXT.get(art, 'gleich mit GitLab')})")
    lease = [f"--force-with-lease=refs/heads/{branch}:{gl}"] if art == "umgeschrieben" else []
    git_oder_fehler(ordner, "push", "-q", *lease, "origin", f"refs/heads/{branch}:refs/heads/{branch}")
    return f"{branch}: {gl[:8]} → {lokal[:8]} gepusht" + (" (force-with-lease)" if lease else "")


# Kurztext je Ergebnis von stand_zu_gitlab (Seite, agent zeigen/pruefen)
STAND_TEXT = {"origin_voraus": "GitLab ist weiter – Branch aktualisieren",
              "gepusht": "gepusht, GitLab noch nicht neu geholt – MR-Daten holen",
              "lokal_voraus": "lokal neue Commits, noch nicht gepusht",
              "umgeschrieben": "lokal umgeschrieben (z. B. Rebase), noch nicht gepusht – Force-Push mit Lease",
              "abweichend": "lokal und GitLab auseinandergelaufen – selbst zusammenführen"}


def branch_aktualisieren(ordner, branch):
    """origin holen und den lokalen Branch auf origin/<branch> nachziehen: vorspulen, oder – nach einem Force-Push –
    auf den neuen Stand setzen, wenn der lokale Branch keine eigenen Commits hat (stand auf dem alten origin).
    Ausgecheckt (auch in einem anderen Worktree) samt Arbeitsverzeichnis und Submodulen; dafür muss der Stand sauber
    sein (Submodul-Zeiger zählen nicht, die zieht submodule update mit). Rückgabe: Text."""
    remote = f"refs/remotes/origin/{branch}"
    def sha(ref):
        return (git(ordner, "rev-parse", "--verify", "-q", ref + "^{commit}", check=False) or "").strip()
    alt = sha(remote)
    git_oder_fehler(ordner, "fetch", "--recurse-submodules=on-demand", "origin")
    neu, lokal = sha(remote), sha(f"refs/heads/{branch}")
    if not neu:
        raise Fehler(f"origin/{branch} gibt es nicht")
    if not lokal or lokal == neu:
        return f"origin geholt, {branch} ist auf {neu[:8]}"
    vorspulen = git(ordner, "merge-base", "--is-ancestor", lokal, neu, check=False) is not None
    if not vorspulen and lokal != alt:
        raise Fehler(f"{branch} hat lokale Commits, die nicht auf origin sind – bitte selbst zusammenführen")
    baum = worktree_mit(ordner, branch)
    if not baum:
        git(ordner, "update-ref", f"refs/heads/{branch}", neu, lokal)
    else:
        sauber_oder_fehler(baum)
        git_oder_fehler(baum, *(["merge", "--ff-only", "-q"] if vorspulen else ["reset", "--keep", "-q"]), neu)
        git_oder_fehler(baum, "submodule", "update", "--init", "--recursive")
    return f"{branch}: {lokal[:8]} → {neu[:8]}" + ("" if vorspulen else " (neu gesetzt, origin wurde umgeschrieben)")


def worktree_mit(ordner, branch):
    """Worktree (auch der Hauptordner), in dem der Branch ausgecheckt ist, sonst None."""
    for block in (git(ordner, "worktree", "list", "--porcelain", check=False) or "").split("\n\n"):
        zeilen = dict(z.split(" ", 1) for z in block.splitlines() if " " in z)
        if zeilen.get("branch") == f"refs/heads/{branch}":
            return zeilen.get("worktree")
    return None


def sauber_oder_fehler(baum):
    """Fehler, wenn der Worktree nicht committete Änderungen hat (Submodul-Zeiger zählen nicht, unversionierte Dateien
    auch nicht – die schützt git selbst)."""
    offen = git(baum, "status", "--porcelain", "--untracked-files=no", "--ignore-submodules=all")
    if offen.strip():
        raise Fehler(f"{kurzpfad(baum)} hat nicht committete Änderungen:\n{offen.rstrip()}")


def branch_auschecken(ordner, branch):
    """Den Quell-Branch eines MR im Klon auschecken, wenn das gefahrlos geht: Stand sauber, HEAD auf einem Branch (kein
    Rebase, kein losgelöster HEAD), Branch nicht schon in einem anderen Worktree. Fehlt er lokal, entsteht er aus
    origin/<branch> (mit Tracking). Submodule ziehen mit. Rückgabe (erledigt, text): erledigt = nichts mehr zu tun
    (ausgecheckt oder schon da/anderswo), sonst text = warum nicht."""
    baum = worktree_mit(ordner, branch)
    if baum:
        return True, ("" if os.path.realpath(baum) == os.path.realpath(ordner) else f"{branch} ist in {kurzpfad(baum)} ausgecheckt")
    vorher = (git(ordner, "symbolic-ref", "-q", "--short", "HEAD", check=False) or "").strip()
    if not vorher:
        return False, f"{kurzpfad(ordner)}: HEAD steht auf keinem Branch (Rebase?) – {branch} nicht ausgecheckt"
    try:
        sauber_oder_fehler(ordner)
        lokal = git(ordner, "rev-parse", "--verify", "-q", f"refs/heads/{branch}", check=False) is not None
        git_oder_fehler(ordner, "switch", "-q", *([branch] if lokal else ["--track", "-c", branch, f"origin/{branch}"]))
        git_oder_fehler(ordner, "submodule", "update", "--init", "--recursive")
    except Fehler as e:
        return False, f"{branch} nicht ausgecheckt – {e}"
    return True, f"{kurzpfad(ordner)}: {vorher} → {branch} ausgecheckt"


INHALT = {}


def inhalt(ordner, sha, pfad):
    """Dateiinhalt an einem Stand aus dem lokalen Klon. None = gibt es nicht."""
    k = (ordner, sha, pfad)
    if k not in INHALT:
        if len(INHALT) > 3000:
            INHALT.clear()
        INHALT[k] = git(ordner, "show", f"{sha}:{pfad}", check=False)
        sub = INHALT[k] is None and submodul_stelle(ordner, sha, pfad)
        if sub and os.path.exists(os.path.join(sub[0], ".git")):
            INHALT[k] = inhalt(*sub)
    return INHALT[k]


def submodul_stelle(ordner, sha, pfad):
    """Liegt pfad im Stand sha unter einem Submodul (Gitlink): (Ordner des Submoduls im Klon, sein Commit laut sha,
    Pfad darin), sonst None. inhalt liest solche Dateien aus dem Submodul (auch verschachtelt)."""
    teile = pfad.split("/")
    for i in range(1, len(teile)):
        vorn = "/".join(teile[:i])
        m = re.match(r"\d+ (\w+) ([0-9a-f]+)\t", git(ordner, "ls-tree", sha, "--", vorn, check=False) or "")
        if not m or m.group(1) == "blob":
            return None
        if m.group(1) == "commit":
            return os.path.join(ordner, vorn), m.group(2), "/".join(teile[i:])
    return None


def fehlt_grund(ordner, sha, pfad, wo):
    """Warum inhalt(ordner, sha, pfad) nichts liefert, als Text für Seite und Agent; wo = „im MR-Stand“, „auf main“ …"""
    sub = submodul_stelle(ordner, sha, pfad)
    if not sub:
        return f"Datei nicht {wo}"
    name = os.path.relpath(sub[0], ordner)
    if not os.path.exists(os.path.join(sub[0], ".git")):
        return f"Submodul {name} nicht ausgecheckt (git submodule update --init {name})"
    if git(sub[0], "cat-file", "-e", sub[1] + "^{commit}", check=False) is None:
        return f"Stand {sub[1][:8]} des Submoduls {name} nicht im Klon (git -C {name} fetch)"
    return f"{name}: " + fehlt_grund(*sub, f"im Submodul (Stand {sub[1][:8]})")


def git_commits(ordner, von=None, bis=None, *, nur=None):
    """Commits von..bis, älteste zuerst: (kurz-sha, zeit, betreff, rumpf, sha). nur: genau diese Commits (shas, nach
    Datum), von/bis dann None."""
    auswahl = ["--no-walk=sorted", *sorted(nur)] if nur is not None else [f"{von}..{bis}"]
    if nur is not None and not nur:
        return []
    roh = git(ordner, "log", "--reverse", "--format=%h%x1f%ad%x1f%s%x1f%b%x1f%H%x1e",
              "--date=format:%d.%m. %H:%M", *auswahl, check=False) or ""
    return [tuple(c.strip("\n").split("\x1f")) for c in roh.split("\x1e") if c.strip()]


def projekt_wurzel(projekt):
    """Klon des lokalen Projekts mit diesem Namen (auch, wenn ihm gerade ein Branch fehlt)."""
    wurzel = next((r for r in finde_repos(alle=True) if projektname(r) == projekt), None)
    if not wurzel:
        raise Fehler(f"Projekt {projekt} nicht gefunden – den Ordner unter „projekte“ in {kurzpfad(KONFIG_DATEI)} "
                     "eintragen (greift ohne Neustart)")
    return wurzel
