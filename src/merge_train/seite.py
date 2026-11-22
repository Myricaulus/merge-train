"""Die Seiten bauen: Diff-Seite eines Projekts, MRs bzw. Myrling-Laufs, Güterbahnhof mit Zug, Startseite."""
import hashlib, html, json, os, re, shlex, shutil
import urllib.parse
from .einstellungen import ARBEITSSTAND, KONF, ORDNER, SKRIPT, dateiname, ersetzen, projektname, schluessel
from .waggon import Waggon, fertig_moeglich, von_bis
from .git import INHALT, bis_sha, blobs, diff_basis, git, git_commits, inhalt, kurzpfad, STAND_TEXT, stand_zu_gitlab, wip_name, wip_sha, zerlegen
from .syntax import vorab_lexen
from .zeilen import paare_und_hunks
from .web import BAHNHOF_BILD, CSS, CSS_REVIEW, ICON, JS, JS_START
from .diff_html import datei_html, spaeter_grund, zeilenzahl
from .akte import STRUKTUR, akte_bearbeiten, akte_lesen
from .gitlab import MetaFehlt, mr_lokal
from .ansichten import ansicht_aufloesen, ansicht_html

def commits_html(commits, knoepfe=None):
    """commits: Liste (kurz-sha, zeit, betreff, rumpf[, sha]). knoepfe(i, commit) → HTML hinter dem Betreff."""
    def nachricht(b):
        b = re.sub(r"\n*Co-Authored-By:.*", "", b, flags=re.I).strip()
        return f'<div class="nachricht">{html.escape(b)}</div>' if b else ""
    return "".join(f'<div class="commit"><code>{html.escape(c[0])}</code> <b>{html.escape(c[2])}</b> '
                   f'<span class="sub">{html.escape(c[1])}</span>{knoepfe(i, c) if knoepfe else ""}{nachricht(c[3])}</div>'
                   for i, c in enumerate(commits)) or '<div class="sub">keine Commits</div>'


def dateiliste_html(dateien):
    fl, letzter = [], None
    for n, d in enumerate(dateien):
        ordner, name = os.path.split(d["neu"])
        if ordner != letzter:
            fl.append(f'<div class="sub" style="padding:6px 10px 0">{html.escape(ordner or "/")}</div>'); letzter = ordner
        fl.append(f'<a href="#d{n}" title="{html.escape(d["neu"])}"><span class="zahl"><span class="kz"></span><span class="p">+{d["plus"]}</span> '
                  f'<span class="m">−{d["minus"]}</span></span>{html.escape(name)}'
                  f'{" <span class=sub>(" + d["status"] + ")</span>" if d["status"] != "geändert" else ""}</a>')
    return fl


def mr_seite(mr, ansicht=None):
    """MR-Seite aus dem lokalen Klon (im Cache je Stand). Rückgabe (html-pfad, struktur, mr). Keine GitLab-Anfrage."""
    akte = akte_lesen(mr)
    meta = akte.get("meta")
    if not meta:
        raise MetaFehlt(f'Für {mr.projekt}!{mr.iid} gibt es noch keine MR-Daten – „merge-train agent zeigen …“ '
                        "(jira-review) oder im Güterbahnhof „MR-Daten holen“")
    ordner, refs = mr_lokal(mr, meta)
    # Cache-Schlüssel nur aus dem, was die Seite zeigt: der Abrufzeitpunkt (_zeit) steht nur in der Warnung bei
    # abweichendem Stand – sonst würde jedes „MR-Daten holen“ die ganze Seite neu bauen; dazu der Stand der Meldung
    # (ein Push aus dem Terminal ändert ihn, ohne dass sich Kopf oder MR-Daten ändern)
    gl_head = (meta.get("diff_refs") or {}).get("head_sha")
    stand = stand_zu_gitlab(ordner, meta.get("source_branch") or "", refs["head_sha"], gl_head)
    mh = hashlib.sha1(json.dumps({**{k: v for k, v in meta.items() if k != "_zeit" or stand}, "_stand": stand},
                                 sort_keys=True).encode()).hexdigest()[:6]
    praefix = os.path.join(MR_ORDNER, f'{mr.dateiname}-{refs["head_sha"][:12]}-{refs["base_sha"][:12]}-{mh}')
    pfad, struktur = seite_bauen(mr.id, ordner, refs, praefix,
                                 lambda *a: mr_html(mr, meta, *a), ansicht)
    if not ansicht:
        with akte_bearbeiten(mr) as s:  # Kommentare, Hinweise und Gespräch beziehen sich immer auf den ganzen MR
            s["struktur"] = praefix_json(praefix)
    return pfad, struktur, mr


def mr_html(mr, meta, dateien, commits, texte, struktur):
    slug = mr.id
    head = struktur["refs"]["head_sha"]
    ans = struktur.get("ansicht")
    web = meta.get("web_url") or ""
    autor = (meta.get("author") or {}).get("name", "")
    beschr = (meta.get("description") or "").strip()
    cl = (f'<div class="commit"><b>Beschreibung</b><div class="nachricht">{html.escape(beschr)}</div></div>' if beschr else "") \
        + commits_html(commits, commit_knoepfe(f"/mr/{slug}", commits, ans))
    leer = '<div class="leer">Keine Änderungen in diesem Merge-Request.</div>' if not dateien else ""
    lesen = bool(ans and ans["art"] == "commit")
    daten = seiten_daten(slug, head, len(dateien), ans, projekt=slug, web_url=web)
    klick = ("nur lesen" if lesen else "Klick auf Zeilennummer (rechts): Kommentar" if ans
             else "Klick auf Zeilennummer: Kommentar")
    hilfe = (f'<div class="hilfe">{klick}<br><kbd>n</kbd> nächster MR · '
             '<kbd>←</kbd>/<kbd>→</kbd> Datei<br><kbd>i</kbd> inline · <kbd>z</kbd> zu/auf · <kbd>c</kbd> Commits</div>')
    ah = ansicht_html(f"/mr/{slug}", "ganzer MR", ans) if ans else ""
    abw = stand_html(struktur["ordner"], meta, head)
    titel = f'{mr.projekt}!{mr.iid}'
    entwurf = '<span class="badge">Draft</span> ' if meta.get("draft") or meta.get("work_in_progress") else ""
    return diff_seite(titel=f'!{mr.iid} {html.escape(meta.get("title") or "")}', sid=slug, lesen=lesen, daten=daten,
                      head=head, dateien=dateien, texte=texte, commits=commits, h1=f'{entwurf}{html.escape(meta.get("title") or "")}',
                      commits_titel="Beschreibung &amp; Commits", commits_liste=cl, nach_commits=abw + ah,
                      nach_h1=f'\n<a class="gl-link" href="{html.escape(web)}" target="_blank" rel="noopener">{html.escape(titel)} ↗</a>',
                      sub_vor=f'{html.escape(meta.get("source_branch") or "")} → {html.escape(meta.get("target_branch") or "")} · {html.escape(autor)} ·\n',
                      nach_sub=f'\n<span class="sub quelle-ok" title="Diff und Inhalte aus dem lokalen Klon">· lokal: {html.escape(kurzpfad(struktur["ordner"]))}</span>',
                      hilfe=hilfe, leer=leer)


# Knopf in der Meldung je Stand (stand_zu_gitlab): data-g = Aktion in api/gitlab, data-frage = erst bestätigen
STAND_KNOPF = {
    "origin_voraus": '<button data-g="aktualisieren" data-meldung="hole origin …" title="git fetch, Quell-Branch '
                     'vorspulen (ausgecheckt samt Submodulen)">⇣ lokal aktualisieren</button>',
    "gepusht": '<button data-g="mrdaten" title="GitLab-Stand dieses MR neu holen">↻ MR-Daten</button>',
    "lokal_voraus": '<button data-g="pushen" data-meldung="pushe …" title="git push origin {b} (nur vorspulen)">'
                    '⇡ pushen</button>',
    "umgeschrieben": '<button data-g="pushen" data-meldung="pushe …" data-frage="{b} mit Force-Push überschreiben? '
                     'Nur, wenn origin noch auf {gl} steht (--force-with-lease)." title="git push '
                     '--force-with-lease={b}:{gl} origin {b}">⇡ force-push (with lease)</button>'}


def stand_html(ordner, meta, head):
    """Meldung über den Diffs, wenn der lokale Quell-Branch nicht auf dem zuletzt geholten GitLab-Stand steht: rot,
    wenn lokal etwas fehlt oder auseinandergelaufen ist; sonst (lokal weiter, schon gepusht) als Hinweis."""
    gl, branch = (meta.get("diff_refs") or {}).get("head_sha"), meta.get("source_branch") or ""
    art = stand_zu_gitlab(ordner, branch, head, gl)
    if not art:
        return ""
    e = html.escape
    knopf = STAND_KNOPF.get(art, "").format(b=e(branch), gl=e(gl[:8]))
    klasse = "warn" if art in ("origin_voraus", "abweichend") else "warn lokal"
    return (f'<div class="{klasse}">GitLab stand beim letzten Holen ({e(meta.get("_zeit") or "?")}) auf {e(gl[:8])}, '
            f'lokal ist {e(head[:8])}: {e(STAND_TEXT[art])}. {knopf}</div>')


def leitstand_html():
    """Knöpfe im Leitstand: je eingeschalteter Quelle."""
    from .quellen import MYRLING  # quellen braucht seite
    knoepfe = ""
    wo = [t for t, an in (("lokalen Änderungen", KONF["lokal"]), ("Läufen des Myrlings", MYRLING.an())) if an]
    if wo:  # lädt die Seite neu: lokal ist dann alles frisch, zug.js holt die Läufe neu
        knoepfe += f'<button data-l="neu" title="Nach neuen {" und ".join(wo)} schauen">↻ Änderungen</button>'
    if KONF["gitlab"]:
        fehlt = not shutil.which((shlex.split(KONF["glab"]) or ["glab"])[0])
        def knopf(aktion, text, titel):  # ohne glab ausgegraut: der Bahnhof steht, aber es fährt nichts
            if fehlt:
                return f'<button data-g="{aktion}" disabled title="glab fehlt ({html.escape(KONF["glab"])}) – siehe README">{text}</button>'
            return f'<button data-g="{aktion}" title="{titel}">{text}</button>'
        knoepfe += (knopf("mrliste", "↻ MRs", "MRs, bei denen ich Reviewer bin, aus GitLab holen")
                    + knopf("mrdaten", "↻ MR-Daten", "Titel, Beschreibung, Branches und GitLab-Stand dieses MR neu holen"))
    return knoepfe


def gleise_html():
    """Kopf: der Güterbahnhof über die ganze Breite. Kulisse (bahnhof.webp), davor Verladegebäude und Förderband
    (zeichnet zeichnungen.js in #anlage, weil das Band bis zur Bildschirmmitte reicht) und der Zug. Im Leitstand die Knöpfe
    der eingeschalteten Quellen: lokal nach neuen Änderungen schauen, GitLab nur auf Knopfdruck fragen."""
    titel = "Güterbahnhof" + (": GitLab wird nur hier (und beim Abschließen) gefragt" if KONF["gitlab"] else "")
    return (f'<div class="gleise szene" style="--bild:url(data:image/webp;base64,{BAHNHOF_BILD})">'
            '<svg id="anlage" aria-hidden="true"></svg>'
            f'<div id="bahnhof" title="{titel}"><div class="bh-knoepfe">{leitstand_html()}</div><span id="bhzeit"></span></div>'
            '<div id="zug"></div></div>')


# Beide Modi bauen ihre Seite gleich: Diff, Commits und Inhalte aus dem Klon, Kontext und große Dateien nachladbar,
# Commit-Ansichten. Sie unterscheiden sich nur im Kopf (MR-Daten/Kommentare bzw. „fertig“).

MR_ORDNER = os.path.join(ORDNER, "mr")


LOKAL_ORDNER = os.path.join(ORDNER, "lokal")


# Stand des Skripts und der Einstellung (Leitstand-Knöpfe, Agenten): ändert sich eins, werden Seiten neu gebaut
VERSION = str(int(os.path.getmtime(SKRIPT))) + "-" + \
    hashlib.sha1(json.dumps(KONF, sort_keys=True, default=str).encode()).hexdigest()[:6]


def praefix_json(praefix, ans=None):
    return praefix + (f'-{ans["art"]}{ans["sha"][:12]}' if ans else "") + f"-{VERSION}.json"


def seite_bauen(sid, ordner, refs, praefix, html_fn, ansicht=None, commits=None):
    """Seite für base..head (bzw. eine Commit-Ansicht) bauen, im Cache je Stand. html_fn(dateien, commits, texte, struktur).
    commits: die Liste unter „Commits“, Standard base..head. Rückgabe (html-pfad, struktur)."""
    ans = ansicht_aufloesen(ordner, refs, *ansicht) if ansicht else None
    stamm = praefix_json(praefix, ans)[:-5]
    if os.path.exists(stamm + ".html") and os.path.exists(stamm + ".json"):
        if stamm + ".json" not in STRUKTUR:
            STRUKTUR[stamm + ".json"] = json.load(open(stamm + ".json", encoding="utf-8"))
        return stamm + ".html", STRUKTUR[stamm + ".json"]
    von, bis = (ans["von"], ans["bis"]) if ans else (refs["base_sha"], refs["head_sha"])
    dateien = zerlegen(git(ordner, "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff",
                           "-M", "-U3", von, bis))
    if commits is None:
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
    """const MR = … für die Seite (kann: was der Waggon kann, siehe Quellen)."""
    from .quellen import extern_von  # quellen braucht seite
    waggon = Waggon.aus_id(sid)
    return json.dumps(dict(mehr, id=sid, sha=head, k=schluessel(), dateien=n, kann=waggon.kann, version=VERSION,
                           ich=KONF["ich_symbol"], extern=extern_von(waggon),
                           beobachten=bool(KONF["beobachten"]), ansicht=f'{ans["art"]}:{ans["sha"]}' if ans else "",
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


# ---- lokales Projekt (von … bis des Projekts, z. B. reviewed … claude)

def projekt_zeiger(projekt):
    return os.path.join(LOKAL_ORDNER, dateiname(projekt) + ".zeiger")


def projekt_seite(wurzel, ansicht=None):
    """Seite eines lokalen Projekts (bis gegen von ab dem gemeinsamen Vorgänger bzw. dem Teilstand <von>-wip: diff_basis).
    Rückgabe (html-pfad, struktur)."""
    projekt = projektname(wurzel)
    von, bis = von_bis(projekt)
    waggon = Waggon(lokal=projekt)
    head = bis_sha(wurzel, bis)
    refs = {"base_sha": diff_basis(wurzel, von, head), "start_sha": git(wurzel, "rev-parse", von).strip(),
            "head_sha": head, "ziel": von}
    praefix = os.path.join(LOKAL_ORDNER, f'{waggon.dateiname}-{von}-{bis}-{head[:12]}-{refs["base_sha"][:12]}'
                           .replace("/", "_"))
    pfad, struktur = seite_bauen(waggon.id, wurzel, refs, praefix,
                                 lambda *a: projekt_html(projekt, von, bis, *a, wip=bool(wip_sha(wurzel, von))), ansicht)
    if not ansicht:
        ersetzen(projekt_zeiger(projekt), praefix_json(praefix))
        with akte_bearbeiten(waggon) as akte:  # Gespräch: Kommentare beziehen sich auf den ganzen Diff
            akte["struktur"] = praefix_json(praefix)
    return pfad, struktur


def stand_name(wurzel, bis, head):
    """Titel für bis: beim Arbeitsstand „Arbeitsstand <branch>“ (nicht Committetes dabei) bzw. „HEAD <branch>“ (sauber)."""
    if bis != ARBEITSSTAND:
        return bis
    branch = (git(wurzel, "symbolic-ref", "--short", "-q", "HEAD", check=False) or "").strip() or "(detached)"
    sauber = head == (git(wurzel, "rev-parse", "HEAD", check=False) or "").strip()
    return f"{'HEAD' if sauber else 'Arbeitsstand'} {branch}"


def projekt_html(projekt, von, bis, dateien, commits, texte, struktur, wip=False):
    head = struktur["refs"]["head_sha"]
    ans = struktur.get("ansicht")
    todos = sorted(set(re.findall(r"todo:([\w.-]+)", " ".join(c[2] + " " + c[3] for c in commits))))
    url = "/" + dateiname(projekt)
    cl = commits_html(commits, commit_knoepfe(url, commits, ans))
    td = ('<div class="todos">todos: ' + "".join(f"<code>{html.escape(t)}</code>" for t in todos) + "</div>"
          if todos else "")
    leer = f'<div class="leer">Keine Unterschiede – {html.escape(von)} ist auf dem Stand von {html.escape(bis)}.</div>' \
        if not dateien else ""
    lesen = bool(ans and ans["art"] == "commit")
    daten = seiten_daten(Waggon(lokal=projekt).id, head, len(dateien), ans, projekt=projekt)
    klick = "nur lesen" if lesen else "Klick auf Zeilennummer: Frage/Kommentar an Claude"
    fertig_kbd = "<kbd>Enter</kbd> fertig · " if fertig_moeglich(projekt) else ""
    hilfe = (f'<div class="hilfe">{klick}<br>{fertig_kbd}<kbd>n</kbd> nächstes Projekt<br>'
             '<kbd>←</kbd>/<kbd>→</kbd> Datei · <kbd>i</kbd> inline<br><kbd>z</kbd> zu/auf · <kbd>c</kbd> Commits</div>')
    ah = ansicht_html(url, "ganzes Projekt", ans) if ans else ""
    return diff_seite(titel=f"MR {html.escape(projekt)}", sid=Waggon(lokal=projekt).id, lesen=lesen, daten=daten, head=head,
                      dateien=dateien, texte=texte, commits=commits,
                      h1=f"{html.escape(projekt)}: {html.escape(stand_name(struktur['ordner'], bis, head))} → {html.escape(wip_name(von) if wip else von)}",
                      fertig_titel=f"{html.escape(von)} auf diesen Stand setzen und zum nächsten Projekt",
                      commits_titel="Commits", commits_liste=cl, unter_commits=td, nach_commits=ah, hilfe=hilfe, leer=leer)


def diff_seite(*, titel, sid, lesen, daten, head, dateien, texte, commits, h1, commits_titel, commits_liste, fertig_titel="",
               nach_h1="", sub_vor="", nach_sub="", unter_commits="", nach_commits="", hilfe="", leer=""):
    """Die eine Diff-Seite für alle Quellen: Güterbahnhof im Kopf, Titelzeile, Commits, Seitenleiste mit Kommentaren und
    Dateiliste, Diff. Die Knöpfe richten sich danach, was der Waggon kann (Quelle), die Titelzeile liefert die Quelle."""
    kann = Waggon.aus_id(sid).kann
    plus = sum(d["plus"] for d in dateien); minus = sum(d["minus"] for d in dateien)
    knoepfe = ('<button id="feedback" hidden disabled title="Entwürfe (Fragen/Wünsche) an den Agenten schicken – bleiben privat">'
               'An Agent senden</button>\n'
               '<button id="prompt" hidden title="Was ging an den Agenten? Die zuletzt zugestellten Prompts (horchen, Start). '
               'Dort lässt sich einschalten, dass „An Agent senden“ den Prompt vorher zeigt">📨</button>\n'
               '<button id="starten" hidden title="Konsole mit dem Agenten im Klon öffnen (todo los)">▶ Session starten</button>\n'
               '<button id="abmelden" hidden title="Zuhören beenden: die Session bekommt davon nichts mit (kein Request). '
               'Wieder zuhören: der Session „hör zu“ sagen">🎧 ✕</button>')
    if kann["fertig"]:
        knoepfe += f'\n<button id="fertig"{" hidden" if lesen else ""} title="{fertig_titel}">fertig ✓</button>'
    if kann["review"]:
        knoepfe += (f'\n<button id="abschliessen"{" hidden" if lesen else ""} title="Kommentare als Entwürfe („Review starten“) '
                    'in den MR übertragen – veröffentlicht wird erst in GitLab">Review abschließen → GitLab</button>')
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">{ICON}
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{titel}</title>
<style>{CSS}{CSS_REVIEW}</style><script src="/zug.js?akt={urllib.parse.quote(sid)}"></script></head><body class="diffseite">
<header id="kopf">{gleise_html()}<div class="zeile"><h1>{h1}</h1>{nach_h1}
<span class="sub">{sub_vor}{len(commits)} Commit(s) · {len(dateien)} Datei(en) · <span class="p">+{plus}</span> <span class="m">−{minus}</span> · Stand {html.escape(head[:8])}</span>{nach_sub}
<span id="rvstand" class="sub"></span><span id="meldung"></span>
<span class="kopfknoepfe">{knoepfe}</span></div>
<details id="commits"><summary>{commits_titel}</summary><div class="liste">{commits_liste}</div>{unter_commits}</details>{nach_commits}</header>
<div class="rahmen"><aside class="seite"><div class="box">{hilfe}<details id="kliste" class="kliste" open hidden><summary>GitLab-Kommentare</summary><div></div></details><details id="kliste-gl" class="kliste" open hidden><summary>GitLab-Diskussionen</summary><div></div></details><details id="kliste-ki" class="kliste" open hidden><summary>KI-Threads</summary><div></div></details></div>
<nav id="liste"><h2>Dateien ({len(dateien)})</h2>{"".join(dateiliste_html(dateien))}</nav></aside>
<main>{leer}{dateien_html(dateien, texte)}</main></div>
<script>const MR={daten};{JS}</script></body></html>"""


def ansicht_struktur(haupt, ansicht):
    """Struktur der Ansichts-Seite zur Hauptseite (erzeugt sie bei Bedarf)."""
    from .quellen import quelle  # quellen braucht seite
    p = praefix_json(haupt["praefix"], {"art": ansicht[0], "sha": ansicht[1]})
    if p not in STRUKTUR:
        if not os.path.exists(p):
            waggon = Waggon.aus_id(haupt["id"])
            return quelle(waggon).seite(waggon, ansicht=ansicht)[1]
        STRUKTUR[p] = json.load(open(p, encoding="utf-8"))
    return STRUKTUR[p]


# ---- Lauf des Myrlings (Skript und Begleitdateien, jede gegen ihre zuletzt angesehene Fassung)

MYRLING_ORDNER = os.path.join(ORDNER, "myrling")


# Lauf-Stand aus --anstehend → Text im Kopf der Seite und Marke am Waggon
LAUF_STAND = {"neu": ("neu", "noch nie angesehen"), "geaendert": ("geändert", "seit der zuletzt angesehenen Fassung geändert"),
              "abgelehnt": ("✗ abgelehnt", "diese Fassung ist abgelehnt"),
              "gesehen": ("gesehen", "wie zuletzt angesehen, aber weder geprüft noch erfolgreich gelaufen")}


def myrling_seite(waggon, ansicht=None):
    """Seite eines Myrling-Laufs: Diff von der Basis (jede Datei auf ihrer zuletzt angesehenen Fassung, lauf_ort) zum
    jetzigen Commit, Commits = die, die eine der Dateien seit ihrer Basis geändert haben. Fragt den Befehl der Quelle,
    wenn seine Liste älter als ein paar Sekunden ist. Rückgabe (html-pfad, struktur)."""
    from .myrling import lauf_ort, lauf_von
    lauf = lauf_von(waggon.myrling)
    wurzel, basis, head, fehlen = lauf_ort(lauf)
    refs = {"base_sha": basis, "start_sha": basis, "head_sha": head}
    kopf = {k: lauf[k] for k in ("fp", "stand", "braucht", "abgelehnt")}
    mh = hashlib.sha1(json.dumps([kopf, fehlen], sort_keys=True).encode()).hexdigest()[:6]
    praefix = os.path.join(MYRLING_ORDNER, f"{waggon.dateiname}-{head[:12]}-{basis[:12]}-{mh}")
    hier = [d for d in lauf["dateien"] if d["repo"] == wurzel]
    nur = set()
    for d in hier:  # neue Datei: die Commits, die sie angelegt und geändert haben (höchstens 20)
        bereich = [f'{d["basis"]}..{head}'] if d["basis"] else ["-n", "20", head]
        nur |= set((git(wurzel, "rev-list", *bereich, "--", d["pfad"], check=False) or "").split())
    pfad, struktur = seite_bauen(waggon.id, wurzel, refs, praefix, lambda *a: myrling_html(waggon, lauf, fehlen, *a),
                                 ansicht, commits=git_commits(wurzel, nur=nur))
    if not ansicht:
        with akte_bearbeiten(waggon) as akte:  # Gespräch: Kommentare beziehen sich auf den ganzen Lauf
            akte["struktur"] = praefix_json(praefix)
            akte["lauf"] = {"fp": lauf["fp"], "repo": wurzel}
    return pfad, struktur


def myrling_html(waggon, lauf, fehlen, dateien, commits, texte, struktur):
    e = html.escape
    head = struktur["refs"]["head_sha"]
    stand_kurz, stand_lang = LAUF_STAND.get(lauf["stand"], (lauf["stand"], lauf["stand"]))
    warn = ""
    if lauf["abgelehnt"]:
        warn += (f'<div class="warn">Abgelehnt am {e(str(lauf["abgelehnt"].get("am") or "?"))}: '
                 f'{e(str(lauf["abgelehnt"].get("grund") or "(ohne Begründung)"))}</div>')
    if fehlen:
        warn += ('<div class="warn">Fehlt im Diff (Begleitdateien aus anderen Repos zeigt der Waggon noch nicht): '
                 + ", ".join(f'<code title="{e(d["repo"])}">{e(kurzpfad(os.path.join(d["repo"], d["pfad"])))}</code>' for d in fehlen)
                 + "</div>")
    leer = (f'<div class="leer">Keine Unterschiede zur zuletzt angesehenen Fassung – {e(stand_lang)}.</div>'
            if not dateien else "")
    daten = seiten_daten(waggon.id, head, len(dateien), None, projekt=waggon.id, fp=lauf["fp"])
    hilfe = ('<div class="hilfe">Klick auf Zeilennummer: Frage an Claude<br><kbd>n</kbd> nächster Waggon<br>'
             '<kbd>←</kbd>/<kbd>→</kbd> Datei · <kbd>i</kbd> inline<br><kbd>z</kbd> zu/auf · <kbd>c</kbd> Commits</div>')
    braucht = f' · braucht {e(lauf["braucht"])}' if lauf["braucht"] else ""
    return diff_seite(titel=f'Lauf {e(waggon.myrling)}', sid=waggon.id, lesen=False, daten=daten, head=head,
                      dateien=dateien, texte=texte, commits=commits, h1=f'⛭ {e(waggon.myrling)}',
                      commits_titel="Commits seit der zuletzt angesehenen Fassung", commits_liste=commits_html(commits),
                      nach_commits=warn, hilfe=hilfe, leer=leer,
                      sub_vor=f'<span class="lauf-stand" title="{e(stand_lang)}">{e(stand_kurz)}</span>{braucht} · Myrling ·\n',
                      nach_sub=f'\n<span class="sub quelle-ok" title="Fingerabdruck {e(lauf["fp"])}">· {e(kurzpfad(struktur["ordner"]))} · fp {e(lauf["fp"][:8])}</span>')


def startseite(text="", sid=""):
    """Start: Güterbahnhof und der gemischte Zug, mit GitLab dazu ein Feld zum Öffnen eines MR."""
    daten = json.dumps({"id": sid, "projekt": sid, "sha": "", "k": schluessel(), "dateien": 0,
                        "kann": {"review": False, "fertig": False, "committen": False}})
    mr_feld = ('<p class="sub">Waggon im Zug wählen. Neue MRs holt „↻ MRs“ im Güterbahnhof.</p>'
               '<form action="/mr-oeffnen"><p><label>MR öffnen (URL oder gruppe/projekt!42):<br>'
               '<input name="u" autofocus placeholder="https://gitlab…/-/merge_requests/42"></label></p></form>'
               if KONF["gitlab"] else '<p class="sub">Waggon im Zug wählen.</p>')
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">{ICON}<title>merge-train</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}{CSS_REVIEW}.uebersicht{{max-width:900px;margin:30px auto;padding:0 16px}}
.uebersicht input{{width:100%;font:14px ui-monospace,monospace;padding:6px 8px;border:1px solid var(--rand);border-radius:6px;background:var(--bg);color:var(--fg)}}</style>
<script src="/zug.js?akt={urllib.parse.quote(sid)}"></script></head>
<body class="start"><header id="kopf">{gleise_html()}<div class="zeile"><span id="meldung"></span></div></header>
<main class="uebersicht">{f'<p class="warn">{html.escape(text)}</p>' if text else ""}{mr_feld}
</main><script>const MR={daten};{JS_START}</script></body></html>"""
