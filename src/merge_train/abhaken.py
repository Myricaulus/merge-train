"""Datei abhaken und die Füllung des Waggons daraus (Güterbahnhof, Schritt 3).
Akte „abgehakt“: {pfad: Stand der Datei in bis}. Der Stand ist der Blob, bei gelöschten Dateien „weg:<alter Pfad>“.
Ändert ein neuer Stand eine abgehakte Datei, passt der Stand nicht mehr, und der Haken fällt weg.
Akte „fuellung“: {anteil, fertig, dateien}, zuletzt berechnet. Der Zug zeigt sie, ohne den Diff neu zu rechnen.
Teilabgabe (lokal): die abgehakten Dateien in der Fassung aus bis als Commit auf <von>-wip (teil_abgeben)."""
import os, tempfile
from .akte import akte_bearbeiten
from .git import git, wip_name, wip_sha
from .waggon import Ungueltig

MINDEST = 20  # jede Datei zählt mit mindestens so vielen Zeilen (auch binäre und reine Umbenennungen)


def datei_staende(struktur):
    """{pfad: Stand} aller Dateien des Diffs der Seite (ganzer Waggon, keine Ansicht)."""
    pfade = [f["neu"] for f in struktur["dateien"] if f["status"] != "gelöscht"]
    blob = {}
    if pfade:
        for z in git(struktur["ordner"], "ls-tree", "-z", struktur["refs"]["head_sha"], "--", *pfade).split("\0"):
            kopf, _, pfad = z.partition("\t")
            if pfad:
                blob[pfad] = kopf.split()[2]
    return {f["neu"]: blob.get(f["neu"]) or "weg:" + f["alt"] for f in struktur["dateien"]}


def datei_gewicht(f):
    """Zeilen (+ und −) einer Datei der Struktur, mindestens MINDEST."""
    return max(MINDEST, sum(1 for a, b in f["paare"] if a is None or b is None))


def fuellung_rechnen(akte, struktur, staende):
    """Gültige Haken behalten, Füllung neu rechnen. Rückgabe die abgehakten Pfade."""
    ab = {p: s for p, s in (akte.get("abgehakt") or {}).items() if staende.get(p) == s}
    gesamt = sum(datei_gewicht(f) for f in struktur["dateien"])
    voll = sum(datei_gewicht(f) for f in struktur["dateien"] if f["neu"] in ab)
    akte["abgehakt"] = ab
    akte["fuellung"] = {"anteil": round(voll / gesamt, 3) if gesamt else 0, "fertig": len(ab),
                        "dateien": len(struktur["dateien"])}
    return sorted(ab)


def abhaken(waggon, struktur, pfad=None, an=True):
    """Datei abhaken (an) bzw. den Haken entfernen. Ohne pfad nur nachrechnen (Seite geladen, neuer Stand).
    Rückgabe {abgehakt, fuellung}."""
    staende = datei_staende(struktur)
    if pfad is not None and pfad not in staende:
        raise Ungueltig(f"Datei nicht im Diff: {pfad}")
    with akte_bearbeiten(waggon) as akte:
        if pfad is not None:
            ab = akte.setdefault("abgehakt", {})
            if an:
                ab[pfad] = staende[pfad]
            else:
                ab.pop(pfad, None)
        fertig = fuellung_rechnen(akte, struktur, staende)
        return {"ok": True, "abgehakt": fertig, "fuellung": akte["fuellung"]}


def haken_weg(akte):
    """Nach „fertig“ bzw. „abgeben“: die Dateien sind aus dem Diff, die Haken gelten nicht mehr."""
    akte.pop("abgehakt", None)
    akte.pop("fuellung", None)


def teil_abgeben(struktur, von, pfade):
    """Die Dateien pfade (abgehakt) in der Fassung aus head_sha als Commit auf <von>-wip (Parent: <von>-wip bzw. von).
    Per Plumbing mit eigenem Index: Arbeitsverzeichnis, Index und HEAD bleiben unberührt.
    Rückgabe (sha des Commits, True wenn sein Baum gleich dem von head_sha ist)."""
    ordner, head = struktur["ordner"], struktur["refs"]["head_sha"]
    eltern = wip_sha(ordner, von) or git(ordner, "rev-parse", von + "^{commit}").strip()
    alle = {p for f in struktur["dateien"] if f["neu"] in pfade for p in (f["alt"], f["neu"])}
    da = {}
    for z in git(ordner, "ls-tree", "-z", head, "--", *alle).split("\0") if alle else ():
        kopf, _, pfad = z.partition("\t")
        if pfad:
            modus, _, blob = kopf.split()
            da[pfad] = f"{modus},{blob},{pfad}"
    with tempfile.TemporaryDirectory() as t:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(t, "index"))
        git(ordner, "read-tree", eltern, env=env)
        weg = sorted(alle - set(da))
        if weg:
            git(ordner, "update-index", "--force-remove", "--", *weg, env=env)
        if da:
            git(ordner, "update-index", "--add", *(a for k in sorted(da) for a in ("--cacheinfo", da[k])), env=env)
        baum = git(ordner, "write-tree", env=env).strip()
    n = len(pfade)
    text = f"merge-train: Teilabgabe ({n} Datei{'' if n == 1 else 'en'})\n\n" + "\n".join(sorted(pfade))
    sha = git(ordner, "commit-tree", baum, "-p", eltern, "-m", text).strip()
    git(ordner, "update-ref", "refs/heads/" + wip_name(von), sha)
    return sha, baum == git(ordner, "rev-parse", head + "^{tree}").strip()
