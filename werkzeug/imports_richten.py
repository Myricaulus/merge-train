"""Schreibt die Import-Zeilen aller Module in src/merge_train neu – nach dem, was sie wirklich benutzen – und meldet
Rückwärts-Abhängigkeiten (ein Modul nutzt eins, das in REIHENFOLGE später kommt). Aufruf aus der Repo-Wurzel:

  python3 werkzeug/imports_richten.py

Neues Modul: in REIHENFOLGE eintragen (und in src/merge_train/__init__.py). Namen müssen paketweit eindeutig sein.
"""
import ast, os, sys

P = "src/merge_train"
REIHENFOLGE = ["einstellungen", "waggon", "git", "syntax", "zeilen", "web", "diff_html", "akte", "beobachter", "gitlab", "hinweise",
               "ansichten", "seite", "quellen", "zuhoerer", "review", "gespraech", "server", "instanz", "agent_cli", "cli"]
STD = ["argparse", "fcntl", "base64", "difflib", "glob", "hashlib", "html", "json", "os", "pkgutil", "re", "shlex", "shutil",
       "subprocess", "sys", "threading", "time"]

vorhanden = sorted(f[:-3] for f in os.listdir(P) if f.endswith(".py") and f != "__init__.py")
assert sorted(REIHENFOLGE) == vorhanden, f"REIHENFOLGE passt nicht zu den Dateien: {vorhanden}"


def eigene_namen(k):
    if isinstance(k, (ast.FunctionDef, ast.ClassDef)):
        return [k.name]
    if isinstance(k, (ast.Assign, ast.AnnAssign)):
        ziele = k.targets if isinstance(k, ast.Assign) else [k.target]
        return [e.id for t in ziele for e in (t.elts if isinstance(t, ast.Tuple) else [t]) if isinstance(e, ast.Name)]
    if isinstance(k, ast.Try):
        return [n for x in k.body + [y for h in k.handlers for y in h.body] for n in eigene_namen(x)] + \
               [a.asname or a.name for x in k.body if isinstance(x, ast.ImportFrom) for a in x.names]
    return []


def ist_paket_import(k):
    return isinstance(k, ast.ImportFrom) and k.level == 1 and k.module


def ist_std_import(k):
    return isinstance(k, ast.Import) or (isinstance(k, ast.ImportFrom) and k.level == 0 and k.module == "datetime"
                                         and [a.name for a in k.names] == ["datetime"])


def freie_namen(k):
    eigene = set()
    if isinstance(k, (ast.FunctionDef, ast.ClassDef)):
        eigene = {x.id for x in ast.walk(k) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)} | \
                 {a.arg for a in ast.walk(k) if isinstance(a, ast.arg)}
    return {x.id for x in ast.walk(k) if isinstance(x, ast.Name)} - eigene


baeume, texte, wo = {}, {}, {}
for m in REIHENFOLGE:
    texte[m] = open(f"{P}/{m}.py", encoding="utf-8").read()
    baeume[m] = ast.parse(texte[m])
    for k in baeume[m].body:
        for n in eigene_namen(k):
            assert wo.get(n, m) == m, f"{n} doppelt: {wo[n]} und {m}"
            wo[n] = m

fehler = 0
for m in REIHENFOLGE:
    koerper = [k for k in baeume[m].body if not ist_paket_import(k) and not ist_std_import(k)]
    benutzt = set().union(*(freie_namen(k) for k in koerper)) if koerper else set()
    spaet = {a.name for k in baeume[m].body if isinstance(k, ast.ImportFrom) and k.level == 1 and not k.module
             for a in k.names}  # „from . import x“: absichtlich spät aufgelöst
    zeilen = []
    std = sorted(n for n in benutzt if n in STD)
    if std:
        zeilen.append("import " + ", ".join(std))
    if "urllib" in benutzt:
        zeilen.append("import urllib.parse")
    if "datetime" in benutzt and wo.get("datetime") != m:
        zeilen.append("from datetime import datetime")
    nach = {}
    for n in benutzt:
        if n in wo and wo[n] != m and wo[n] not in spaet:
            nach.setdefault(wo[n], []).append(n)
    for z in sorted(nach, key=REIHENFOLGE.index):
        if REIHENFOLGE.index(z) > REIHENFOLGE.index(m):
            print(f"RÜCKWÄRTS {m} → {z}: {' '.join(sorted(nach[z]))}")
            fehler += 1
        ns = sorted(nach[z])
        zeile = f"from .{z} import " + ", ".join(ns)
        if len(zeile) > 130:
            zeile = f"from .{z} import (" + ",\n    ".join(", ".join(ns[i:i + 8]) for i in range(0, len(ns), 8)) + ")"
        zeilen.append(zeile)
    alt = [k for k in baeume[m].body if ist_paket_import(k) or ist_std_import(k)]
    quell = texte[m].split("\n")
    if alt:
        erste = min(k.lineno for k in alt)
        weg = {i for k in alt for i in range(k.lineno, k.end_lineno + 1)}
        quell = [z for i, z in enumerate(quell, 1) if i not in weg]
        quell[erste - 1:erste - 1] = zeilen
    else:
        doc = baeume[m].body[0].end_lineno
        quell[doc:doc] = zeilen
    neu = "\n".join(quell)
    if neu != texte[m]:
        open(f"{P}/{m}.py", "w", encoding="utf-8").write(neu)
sys.exit(1 if fehler else 0)
