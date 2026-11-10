"""Ansichten eines Waggons: alles, ein einzelner Commit (commit:<sha>) oder alles seit einem Commit (seit:<sha>)."""
import html, re
from .waggon import Fehler
from .git import git

# Kommentare und Hinweise gehören immer zum ganzen MR (Zeilen im MR-Stand). Eine Ansicht zeigt sie nur an:
# „seit“ hat rechts den MR-Stand, dort lässt sich alles direkt zuordnen und auch kommentieren.
# „commit“ zeigt den Stand nach dem Commit, Zeilen werden über den Diff Commit → MR-Stand zurückgerechnet. Nur lesen.

LEERER_BAUM = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def ansicht_lesen(s):
    """'commit:<sha>' / 'seit:<sha>' → (art, sha), sonst None."""
    m = re.fullmatch(r"(commit|seit):([0-9a-f]{7,40})", str(s or ""))
    return (m.group(1), m.group(2)) if m else None


def ansicht_aufloesen(ordner, refs, art, sha):
    """Commit prüfen (muss zum MR gehören) → {art, sha, von, bis, titel, kurz, anzahl, merge}."""
    voll = (git(ordner, "rev-parse", "--verify", "-q", sha + "^{commit}", check=False) or "").strip()
    if not voll:
        raise Fehler(f"Commit {sha[:12]} gibt es im lokalen Klon nicht")
    im_mr = (git(ordner, "rev-list", f'{refs["base_sha"]}..{refs["head_sha"]}', check=False) or "").split()
    if voll not in im_mr:
        raise Fehler(f"Commit {sha[:12]} gehört nicht zu diesem MR")
    titel = (git(ordner, "log", "-1", "--format=%s", voll, check=False) or "").strip()
    eltern = (git(ordner, "rev-list", "--parents", "-n1", voll, check=False) or "").split()[1:]
    if art == "commit":
        von, bis, anzahl = (eltern[0] if eltern else LEERER_BAUM), voll, 1
    else:
        von, bis, anzahl = voll, refs["head_sha"], im_mr.index(voll)  # rev-list: neueste zuerst
    return {"art": art, "sha": voll, "von": von, "bis": bis, "titel": titel, "kurz": voll[:8],
            "anzahl": anzahl, "merge": len(eltern) > 1}


def ansicht_html(url, zurueck_text, ans):
    zurueck = f'<a href="{html.escape(url)}">{html.escape(zurueck_text)}</a>'
    t = f'<code>{html.escape(ans["kurz"])}</code> „{html.escape(ans["titel"])}“'
    if ans["art"] == "commit":
        merge = " · Merge-Commit: Diff gegen den ersten Vorgänger" if ans["merge"] else ""
        text = (f'Nur Commit {t}{merge} · <b>nur lesen</b>: Kommentare und Hinweise stehen an ihrer Zeile, '
                f'wenn sie sich zuordnen lassen, sonst unter dem Dateinamen')
    else:
        text = (f'Änderungen seit {t} ({ans["anzahl"]} Commit(s) danach)'
                + (" · kommentieren rechts (MR-Stand)" if not url.endswith(".html") else ""))
    return f'<div id="ansicht" class="ansicht">{text} · {zurueck}</div>'
