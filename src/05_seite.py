# ---------------------------------------------------------------- Seite (Diff aus dem lokalen Git – GitLab-MR und lokales Projekt)
# Beide Modi bauen ihre Seite gleich: Diff, Commits und Inhalte aus dem Klon, Kontext und große Dateien nachladbar,
# Commit-Ansichten. Sie unterscheiden sich nur im Kopf (MR-Daten/Kommentare bzw. „fertig“).

MR_ORDNER = os.path.join(ORDNER, "mr")
LOKAL_ORDNER = os.path.join(ORDNER, "lokal")
VERSION = str(int(os.path.getmtime(os.path.realpath(__file__))))

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

def praefix_json(praefix, ans=None):
    return praefix + (f'-{ans["art"]}{ans["sha"][:12]}' if ans else "") + f"-{VERSION}.json"

def seite_bauen(sid, ordner, refs, praefix, html_fn, ansicht=None):
    """Seite für base..head (bzw. eine Commit-Ansicht) bauen, im Cache je Stand. html_fn(dateien, commits, texte, struktur).
    Rückgabe (html-pfad, struktur)."""
    ans = ansicht_aufloesen(ordner, refs, *ansicht) if ansicht else None
    stamm = praefix_json(praefix, ans)[:-5]
    if os.path.exists(stamm + ".html") and os.path.exists(stamm + ".json"):
        if stamm + ".json" not in STRUKTUR:
            STRUKTUR[stamm + ".json"] = json.load(open(stamm + ".json", encoding="utf-8"))
        return stamm + ".html", STRUKTUR[stamm + ".json"]
    von, bis = (ans["von"], ans["bis"]) if ans else (refs["base_sha"], refs["head_sha"])
    dateien = zerlegen(git(ordner, "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff",
                           "-M", "-U3", von, bis))
    commits = git_commits(ordner, refs["base_sha"], refs["head_sha"])
    def benoetigt(d):
        if d["binaer"] or not d["hunks"]:
            return None, None
        return (f'{von}:{d["alt"]}' if d["status"] != "neu" else None,
                f'{bis}:{d["neu"]}' if d["status"] != "gelöscht" else None)
    for spec, text in blobs(ordner, [s for d in dateien for s in benoetigt(d) if s]).items():
        sha, _, pfad = spec.partition(":")
        INHALT[(ordner, sha, pfad)] = text
    def texte(d):
        a, b = benoetigt(d)
        if a is None and b is None:
            return None, None
        return (inhalt(ordner, *a.split(":", 1)) or "" if a else "", inhalt(ordner, *b.split(":", 1)) or "" if b else "")
    tx = [texte(d) for d in dateien]
    vorab_lexen([(t, d[k]) for d, (a, b) in zip(dateien, tx) if d["hunks"] and not spaeter_grund(d)
                 for t, k in ((a if d["minus"] else None, "alt"), (b, "neu")) if t])
    struktur = {"id": sid, "refs": refs, "ordner": ordner, "praefix": praefix, "ansicht": ans, "dateien": []}
    for d, (_, neu_text) in zip(dateien, tx):
        paare, hunks = paare_und_hunks(d)
        struktur["dateien"].append({"alt": d["alt"], "neu": d["neu"], "status": d["status"],
                                    "paare": paare, "hunks": hunks, "bn": zeilenzahl(neu_text) or None})
    ersetzen(stamm + ".html", html_fn(dateien, commits, tx, struktur))
    ersetzen(stamm + ".json", json.dumps(struktur, ensure_ascii=False))
    STRUKTUR[stamm + ".json"] = struktur
    return stamm + ".html", struktur

def seiten_daten(sid, head, n, ans, **mehr):
    """const MR = … für die Seite."""
    return json.dumps(dict(mehr, id=sid, sha=head, k=schluessel(), dateien=n,
                           ansicht=f'{ans["art"]}:{ans["sha"]}' if ans else "",
                           lesen=bool(ans and ans["art"] == "commit")), ensure_ascii=False)

def commit_knoepfe(url, commits, ans):
    """Je Commit „nur dieser“ / „seit diesem“ (beim letzten Commit nur „nur dieser“)."""
    def knoepfe(i, c):
        sha = c[4] if len(c) > 4 else ""
        if not sha:
            return ""
        akt = ans["art"] if ans and ans["sha"] == sha else None
        out = (f'<a class="ck{" akt" if akt == "commit" else ""}" href="{html.escape(url)}?commit={sha}" '
               f'title="nur die Änderungen dieses Commits (nur lesen)">nur dieser</a>')
        if i < len(commits) - 1:
            out += (f'<a class="ck{" akt" if akt == "seit" else ""}" href="{html.escape(url)}?seit={sha}" '
                    f'title="alle Änderungen nach diesem Commit bis zum aktuellen Stand">seit diesem</a>')
        return f'<span class="cks">{out}</span>'
    return knoepfe

def dateien_html(dateien, texte):
    return "".join(datei_html(n, d, *texte[n], luecken=True, spaeter=spaeter_grund(d)) for n, d in enumerate(dateien))

# ---- lokales Projekt (VON … BIS, z. B. reviewed … claude)

def projekt_zeiger(projekt):
    return os.path.join(LOKAL_ORDNER, dateiname(projekt) + ".zeiger")

def projekt_seite(wurzel, von=None, bis=None, ansicht=None):
    """Seite eines lokalen Projekts (BIS gegen VON ab dem gemeinsamen Vorgänger). Rückgabe (html-pfad, struktur)."""
    von, bis = von or VON, bis or BIS
    projekt = projektname(wurzel)
    head = git(wurzel, "rev-parse", bis).strip()
    refs = {"base_sha": git(wurzel, "merge-base", von, bis).strip(), "start_sha": git(wurzel, "rev-parse", von).strip(),
            "head_sha": head}
    praefix = os.path.join(LOKAL_ORDNER, f'{dateiname(projekt)[:-5]}-{von}-{bis}-{head[:12]}-{refs["base_sha"][:12]}'
                           .replace("/", "_"))
    pfad, struktur = seite_bauen("projekt:" + projekt, wurzel, refs, praefix,
                                 lambda *a: projekt_html(projekt, von, bis, *a), ansicht)
    if not ansicht:
        ersetzen(projekt_zeiger(projekt), praefix_json(praefix))
    return pfad, struktur

def projekt_html(projekt, von, bis, dateien, commits, texte, struktur):
    head = struktur["refs"]["head_sha"]
    ans = struktur.get("ansicht")
    plus = sum(d["plus"] for d in dateien); minus = sum(d["minus"] for d in dateien)
    todos = sorted(set(re.findall(r"todo:([\w.-]+)", " ".join(c[2] + " " + c[3] for c in commits))))
    url = "/" + dateiname(projekt)
    cl = commits_html(commits, commit_knoepfe(url, commits, ans))
    td = ('<div class="todos">todos: ' + "".join(f"<code>{html.escape(t)}</code>" for t in todos) + "</div>"
          if todos else "")
    leer = f'<div class="leer">Keine Unterschiede – {html.escape(von)} ist auf dem Stand von {html.escape(bis)}.</div>' \
        if not dateien else ""
    lesen = bool(ans and ans["art"] == "commit")
    daten = seiten_daten("projekt:" + projekt, head, len(dateien), ans, projekt=projekt)
    hilfe = ('<div class="hilfe"><kbd>Enter</kbd> fertig · <kbd>n</kbd> nächstes Projekt<br>'
             '<kbd>←</kbd>/<kbd>→</kbd> Datei · <kbd>i</kbd> inline<br><kbd>z</kbd> zu/auf · <kbd>c</kbd> Commits</div>')
    ah = ansicht_html(url, "ganzes Projekt", ans) if ans else ""
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">{ICON}
<meta name="viewport" content="width=device-width,initial-scale=1"><title>MR {html.escape(projekt)}</title>
<style>{CSS}{CSS_REVIEW}</style><script src="/zug.js"></script></head><body>
<header id="kopf">{gleise_html(False)}<div class="zeile"><h1>{html.escape(projekt)}: {html.escape(bis)} → {html.escape(von)}</h1>
<span class="sub">{len(commits)} Commit(s) · {len(dateien)} Datei(en) · <span class="p">+{plus}</span> <span class="m">−{minus}</span> · Stand {html.escape(head[:8])}</span>
<span id="meldung"></span><button id="fertig"{" hidden" if lesen else ""} title="{html.escape(von)} auf diesen Stand setzen und zum nächsten Projekt">fertig ✓</button></div>
<details id="commits"><summary>Commits</summary><div class="liste">{cl}</div>{td}</details>{ah}</header>
<div class="rahmen"><aside class="seite"><div class="box">{hilfe}</div><nav id="liste"><h2>Dateien ({len(dateien)})</h2>{"".join(dateiliste_html(dateien))}</nav></aside>
<main>{leer}{dateien_html(dateien, texte)}</main></div>
<script>const MR={daten};{JS}{JS_ZUG}{JS_DIFF}</script></body></html>"""
