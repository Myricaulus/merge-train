"""Datei abhaken und die Füllung des Waggons daraus (Güterbahnhof, Schritt 3).
Akte „abgehakt“: {pfad: Stand der Datei in bis}. Der Stand ist der Blob, bei gelöschten Dateien „weg:<alter Pfad>“.
Ändert ein neuer Stand eine abgehakte Datei, passt der Stand nicht mehr, und der Haken fällt weg.
Akte „fuellung“: {anteil, fertig, dateien}, zuletzt berechnet. Der Zug zeigt sie, ohne den Diff neu zu rechnen."""
from .akte import akte_bearbeiten
from .git import git
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
    """Nach „fertig“: alles gesehen, die Haken gelten nicht mehr."""
    akte.pop("abgehakt", None)
    akte.pop("fuellung", None)
