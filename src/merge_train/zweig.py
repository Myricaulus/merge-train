"""Ein Branch als Waggon (docs/branch-waggon.md): welchen Branch ein Projekt-Ordner zeigt, aus welchem Klon ein Branch
gezeigt wird und welche Diff-Refs er hat – ohne MR gegen von des Projekts, mit MR-Schicht gegen das Ziel des MR."""
import os
from .einstellungen import ARBEITSSTAND, KONF, VON, projektname
from .waggon import ABKUERZUNGEN, Fehler, Waggon, von_bis
from .git import (arbeitsstand, branch_von, diff_basis, finde_repos, git, git_oder_fehler, haupt_klon, kurzpfad,
                  projekt_wurzel, ref_sha, repo_kennung, repo_klone)
from .akte import akte_lesen, struktur_laden
from .gitlab import ausgecheckt, eigener_mr, mr_von


def projekt_waggon(wurzel):
    """Der Branch, den ein Projekt-Ordner zeigt (branch_von: bis, beim Arbeitsstand der ausgecheckte)."""
    return Waggon(repo=repo_kennung(wurzel), branch=branch_von(wurzel))


def klon_waggon(wurzel):
    """Der Branch eines Klons: der seines Projekts (projekt_waggon), außerhalb von „projekte“ der ausgecheckte. None bei
    losgelöstem HEAD außerhalb eines Projekts."""
    echt = os.path.realpath(wurzel)
    if any(os.path.realpath(r) == echt for r in finde_repos(alle=True)):
        return projekt_waggon(wurzel)
    b = ausgecheckt(wurzel)
    return Waggon(repo=repo_kennung(wurzel), branch=b) if b else None


def _als_projekt(kennung):
    """Abkürzung (waggon.ABKUERZUNGEN): „projekt:<name>“ → der Branch, den das Projekt gerade zeigt."""
    if not kennung.startswith("projekt:"):
        return None
    try:
        return projekt_waggon(projekt_wurzel(kennung[len("projekt:"):]))
    except Fehler:
        return None


ABKUERZUNGEN.append(_als_projekt)


def gemerkte_klone(akte):
    """Klone, die eine Akte nennt: gemerkter Klon (agent zeigen, MR erstellen) und der der zuletzt gebauten Seite."""
    return [akte.get("klon"), (struktur_laden(akte) or {}).get("ordner")]


def projekt_von(w, akte=None):
    """Projekt (Ordner), dessen von/bis für den Branch gilt: das des Haupt-Klons, None ohne Klon."""
    k = haupt_klon(w.repo, gemerkte_klone(akte or akte_lesen(w)))
    return projektname(k) if k else None


_GEHOLT = set()  # (Klon, Branch), für die schon einmal origin geholt wurde (je Prozess)


def holen_einmal(klon, branch):
    """git fetch origin, einmal je Klon und Branch (ändert nichts am Arbeitsverzeichnis). True, wenn geholt."""
    if (klon, branch) in _GEHOLT:
        return False
    _GEHOLT.add((klon, branch))
    git_oder_fehler(klon, "fetch", "-q", "origin")
    return True


def branch_ort(w, akte=None, *, holen=True):
    """(Klon, ausgecheckt): aus welchem Klon der Branch gezeigt wird. Ist er im Haupt-Klon ausgecheckt, dieser
    (ausgecheckt = True: nur dort gibt es den Arbeitsstand); sonst der Haupt-Klon, wenn er den Branch hat (lokal oder
    origin/…), sonst der erste Klon oder Worktree mit dem Branch. Fehlt er überall, einmal git fetch im Haupt-Klon."""
    gemerkt = gemerkte_klone(akte or akte_lesen(w))
    haupt = haupt_klon(w.repo, gemerkt)
    if haupt and (ausgecheckt(haupt) == w.branch or w.branch == "HEAD" and not ausgecheckt(haupt)):
        return haupt, True
    klone = repo_klone(w.repo, gemerkt)
    for k in dict.fromkeys(([haupt] if haupt else []) + klone):
        if ref_sha(k, w.branch):
            return k, False
    if holen and haupt and holen_einmal(haupt, w.branch) and ref_sha(haupt, w.branch):
        return haupt, False
    raise Fehler(f"{w.name}: Branch {w.branch} in keinem Klon von {w.repo}" + (
        f" ({', '.join(kurzpfad(k) for k in klone)})" if klone else
        " – kein Klon bekannt: unter [repos] eintragen, klon_ordner setzen oder „merge-train agent zeigen“ im Repo aufrufen"))


def branch_refs(w, akte=None, *, holen=True):
    """(Klon, refs) des Branches. Mit MR-Schicht: Basis = merge-base mit dem Ziel des MR (bzw. die Basis aus GitLab,
    wenn GitLab beim letzten Holen auf demselben Stand war), Arbeitsstand nur als eigener MR. Ohne: gegen von des
    Projekts (Teilstand <von>-wip: diff_basis), Arbeitsstand bei bis = arbeitsstand. Den Arbeitsstand gibt es nur im
    Haupt-Klon (branch_ort); dann refs.arbeitsstand und refs.commit_sha (letzter Commit des Branches).
    holen=False: nur vorhandene Refs benutzen, etwa für den Zug."""
    akte = akte if akte is not None else akte_lesen(w)
    klon, aus = branch_ort(w, akte, holen=holen)
    commit = (git(klon, "rev-parse", "HEAD").strip() if w.branch == "HEAD" and aus else ref_sha(klon, w.branch))
    mr = mr_von(akte) if KONF["gitlab"] else None
    if mr:
        meta = akte.get("meta") or {}
        ziel = meta.get("target_branch") or ""
        tgt = ref_sha(klon, ziel, remote_zuerst=True)
        if not tgt and holen and holen_einmal(klon, ziel):
            tgt = ref_sha(klon, ziel, remote_zuerst=True)
        if not tgt:
            raise Fehler(f"{kurzpfad(klon)}: Ziel-Branch {ziel} fehlt" + (" (auch nach git fetch)" if holen else ""))
        zref = f"origin/{ziel}" if git(klon, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{ziel}", check=False) else ziel
        gl = meta.get("diff_refs") or {}
        if gl.get("head_sha") == commit and gl.get("base_sha") and \
           git(klon, "cat-file", "-e", gl["base_sha"] + "^{commit}", check=False) is not None:
            refs = {"base_sha": gl["base_sha"], "start_sha": gl.get("start_sha") or tgt, "head_sha": commit, "ziel": zref}
        else:
            base = (git(klon, "merge-base", tgt, commit, check=False) or "").strip()
            if not base:
                raise Fehler(f"{kurzpfad(klon)}: kein gemeinsamer Vorgänger von {ziel} und {w.branch}")
            refs = {"base_sha": base, "start_sha": tgt, "head_sha": commit, "ziel": zref}
        arbeit = aus and eigener_mr(w, akte)
    else:
        p = projekt_von(w, akte)
        von = von_bis(p)[0] if p else VON
        start = (git(klon, "rev-parse", "--verify", "-q", von + "^{commit}", check=False) or "").strip()
        if not start:
            raise Fehler(f"{w.name}: {von} fehlt in {kurzpfad(klon)}")
        arbeit = aus and (not p or von_bis(p)[1] == ARBEITSSTAND)
        head = arbeitsstand(klon) if arbeit else commit
        refs = {"base_sha": diff_basis(klon, von, head), "start_sha": start, "head_sha": head, "ziel": von}
    if arbeit:
        refs.update(head_sha=refs["head_sha"] if not mr else arbeitsstand(klon), commit_sha=commit, arbeitsstand=True)
    return klon, refs
