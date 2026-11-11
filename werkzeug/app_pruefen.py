#!/usr/bin/env python3
"""Prüft, wie die Seiten-Skripte über das globale App zusammenhängen (läuft in ./pruefen, ohne Biome und ohne Node).

Jede Datei in src/merge_train/web/*.js steckt in einer eigenen Funktion und sieht die anderen nur über App. Geprüft wird
je Seite das Bündel in der Reihenfolge aus web.py (JS_DATEIEN, JS_START_DATEIEN):

  - Jedes gelesene App.x wird von irgendeiner Datei bereitgestellt (App.x = …, Object.assign(App, {…}), app.js).
  - Was eine Datei beim Laden aus App herausnimmt (const {x} = App), stellt eine früher geladene Datei bereit.
    Was später kommt, nur beim Aufruf lesen (App.x).
  - Was zwei Dateien setzen (toasts.js ersetzt melden), nimmt niemand beim Laden heraus: man bekäme die alte Fassung.
  - Der Kopfkommentar jeder Datei stimmt: „Braucht von App: …“ nennt genau, was sie liest, „Stellt bereit: …“
    (samt „Ersetzt: …“) genau, was sie setzt. Andere Wörter im Kommentar stören nicht, nur Namen, die es in App gibt.

Aufruf: python3 werkzeug/app_pruefen.py   Exit 1 bei Befunden.
"""
import ast, os, re, sys

HIER = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
WEB = os.path.join(HIER, "src", "merge_train", "web")


def buendel():
    baum = ast.parse(open(os.path.join(HIER, "src", "merge_train", "web.py"), encoding="utf-8").read())
    listen = {z.targets[0].id: ast.literal_eval(z.value) for z in baum.body
              if isinstance(z, ast.Assign) and isinstance(z.targets[0], ast.Name) and z.targets[0].id.endswith("_DATEIEN")}
    return {"Diff-Seite": listen["JS_DATEIEN"], "Startseite": listen["JS_START_DATEIEN"]}


def ohne_kommentare(text):
    return re.sub(r"(^|\s)//[^\n]*", r"\1", text)


def kopf(text):
    """Kommentarzeilen vor dem ersten Code, als ein Text."""
    zeilen = []
    for z in text.split("\n"):
        if not z.startswith("//"):
            break
        zeilen.append(z[2:].strip())
    return " ".join(zeilen)


def namen_in(text):
    return {m.group(1) for m in re.finditer(r"(?<![\w.])([A-Za-z_]\w*)(?!\w|\.\w)", text)}


def bereitgestellt(name, code):
    out = {m.group(1) for m in re.finditer(r"\bApp\.(\w+)\s*=(?!=)", code)}
    for m in re.finditer(r"Object\.assign\(\s*App\s*,\s*\{([^}]*)\}", code):
        out |= {e.split(":")[0].strip() for e in m.group(1).split(",") if e.strip()}
    if name == "app.js":  # Schlüssel des Objekts selbst
        literal = re.search(r"const App = \{\n(.*?)\n\};", code, re.S)
        out |= {m.group(1) for m in re.finditer(r"^  (\w+)\s*[:(]", literal.group(1) if literal else "", re.M)}
    return out


def beim_laden(code):
    """Namen, die die Datei beim Laden aus App herausnimmt: const {a, b: c} = App."""
    out = set()
    for m in re.finditer(r"\{([^{}]*)\}\s*=\s*App\b(?!\.)", code):
        out |= {e.split(":")[0].strip() for e in m.group(1).split(",") if e.strip()}
    return out


def beim_aufruf(code):
    return {m.group(1) for m in re.finditer(r"\bApp\.(\w+)\b(?!\s*=(?!=))", code)}


def teil(kopftext, anfang, enden):
    i = kopftext.find(anfang)
    if i < 0:
        return None
    rest = kopftext[i + len(anfang):]
    stopp = min([rest.find(e) for e in enden if rest.find(e) >= 0] or [len(rest)])
    return rest[:stopp]


def main():
    seiten = buendel()
    dateien = sorted({f for d in seiten.values() for f in d})
    code = {f: ohne_kommentare(open(os.path.join(WEB, f), encoding="utf-8").read()) for f in dateien}
    kopftext = {f: kopf(open(os.path.join(WEB, f), encoding="utf-8").read()) for f in dateien}
    setzt = {f: bereitgestellt(f, code[f]) for f in dateien}
    laden = {f: beim_laden(code[f]) for f in dateien}
    aufruf = {f: beim_aufruf(code[f]) - setzt[f] for f in dateien}
    alle = set().union(*setzt.values())
    befunde = []

    for f in dateien:
        for n in sorted((laden[f] | aufruf[f]) - alle):
            befunde.append(f"{f}: liest App.{n}, das keine Datei setzt")
    for seite, reihe in seiten.items():
        for i, f in enumerate(reihe):
            frueher = set().union(*(setzt[g] for g in reihe[:i]))
            for n in sorted(laden[f] - frueher):
                spaeter = [g for g in reihe[i + 1:] if n in setzt[g]]
                if n in alle:
                    befunde.append(f"{f} ({seite}): nimmt {n} beim Laden aus App, gesetzt erst "
                                   f"{'in ' + ', '.join(spaeter) if spaeter else 'auf einer anderen Seite'} – App.{n} beim Aufruf lesen")
    mehrfach = {n for n in alle if sum(n in setzt[f] for f in dateien) > 1}
    for f in dateien:
        for n in sorted(laden[f] & mehrfach):
            befunde.append(f"{f}: nimmt {n} beim Laden aus App, aber {n} wird später ersetzt – App.{n} beim Aufruf lesen")

    for f in dateien:
        k = kopftext[f]
        braucht = teil(k, "Braucht von App:", ["Stellt bereit:", "Ersetzt:"])
        stellt = (teil(k, "Stellt bereit:", ["Ersetzt:", "Braucht von App:"]) or "") + " " + \
                 (teil(k, "Ersetzt:", ["Stellt bereit:", "Braucht von App:"]) or "")
        if braucht is None and f != "app.js":
            befunde.append(f"{f}: Kopfkommentar ohne „Braucht von App:“")
            continue
        gelesen = laden[f] | aufruf[f]
        genannt = namen_in(braucht or "") & alle
        for n in sorted(gelesen - genannt):
            befunde.append(f"{f}: liest App.{n}, im Kopf fehlt es unter „Braucht von App“")
        for n in sorted(genannt - gelesen):
            befunde.append(f"{f}: Kopf nennt {n} unter „Braucht von App“, die Datei liest es nicht")
        if f == "app.js":
            continue
        genannt = namen_in(stellt) & alle
        for n in sorted(setzt[f] - genannt):
            befunde.append(f"{f}: setzt App.{n}, im Kopf fehlt es unter „Stellt bereit“")
        for n in sorted(genannt - setzt[f]):
            befunde.append(f"{f}: Kopf nennt {n} unter „Stellt bereit“, die Datei setzt es nicht")

    for b in befunde:
        print("src/merge_train/web/" + b)
    if befunde:
        sys.exit(f"\n{len(befunde)} Befund(e) zu App")
    print(f"App: {len(alle)} Namen, {len(dateien)} Dateien, Kopfkommentare und Ladereihenfolge stimmen")


if __name__ == "__main__":
    main()
