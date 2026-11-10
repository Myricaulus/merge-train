"""Alles, was das lokale git fragt: Aufruf mit Protokoll, Diff zerlegen, Arbeitsstand, Repos finden, Dateiinhalte."""
import glob, hashlib, os, re, shutil, subprocess, threading, time
from datetime import datetime
from .einstellungen import ARBEITSSTAND, BIS, KONF, ORDNER, PROJEKTE, PROJEKTE_LISTE, VON, dateiname, projektname
from .waggon import Fehler

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


def git(ordner, *a, check=True, env=None):
    t0 = time.time()
    r = subprocess.run(["git", "-C", ordner, *a], capture_output=True,
                       text=True, errors="replace", env=env)
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


def projekt_ordner(name):
    """Projektname → Ordner (unter einem Eintrag von projekte oder ein dort genanntes Repo)."""
    for p in PROJEKTE_LISTE:
        if os.path.isdir(os.path.join(p, name)) and not os.path.isdir(os.path.join(p, ".git")):
            return os.path.join(p, name)
        if os.path.basename(p.rstrip("/")) == name and os.path.isdir(os.path.join(p, ".git")):
            return p
    return os.path.join(PROJEKTE, name)


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


INHALT = {}


def inhalt(ordner, sha, pfad):
    """Dateiinhalt an einem Stand aus dem lokalen Klon. None = gibt es nicht."""
    k = (ordner, sha, pfad)
    if k not in INHALT:
        if len(INHALT) > 3000:
            INHALT.clear()
        INHALT[k] = git(ordner, "show", f"{sha}:{pfad}", check=False)
    return INHALT[k]


def git_commits(ordner, von, bis):
    """Commits von..bis, älteste zuerst: (kurz-sha, zeit, betreff, rumpf, sha)."""
    roh = git(ordner, "log", "--reverse", "--format=%h%x1f%ad%x1f%s%x1f%b%x1f%H%x1e",
              "--date=format:%d.%m. %H:%M", f"{von}..{bis}", check=False) or ""
    return [tuple(c.strip("\n").split("\x1f")) for c in roh.split("\x1e") if c.strip()]


def projekt_wurzel(projekt):
    """Klon des lokalen Projekts mit diesem Namen."""
    wurzel = next((r for r in finde_repos() if projektname(r) == projekt), None)
    if not wurzel:
        raise Fehler(f"Projekt {projekt} nicht gefunden")
    return wurzel
