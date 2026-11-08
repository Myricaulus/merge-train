# ---------------------------------------------------------------- MR-Zug (MRs zum Review)
# Die Liste kommt aus dem Cache. GitLab wird nur im Güterbahnhof („↻ MRs“) gefragt.

MR_LISTE = os.path.join(ORDNER, "mrliste.json")

def mr_liste():
    try:
        d = json.load(open(MR_LISTE, encoding="utf-8"))
        return d.get("items") or [], d.get("zeit")
    except (OSError, ValueError):
        return [], None

def mr_liste_holen():
    """Offene MRs, bei denen ich Reviewer bin (bzw. mr_liste), aus GitLab holen und merken."""
    art = KONF["mr_liste"]
    if art == "keine":
        return [], None
    host = KONF["gitlab_host"]
    ich = glab(host, "user")["username"]
    param = {"reviewer": "reviewer_username", "assignee": "assignee_username", "author": "author_username"}.get(art, "reviewer_username")
    roh = glab(host, f"merge_requests?scope=all&state=opened&{param}={enc(ich)}&per_page=50") or []
    items = [{"web_url": it.get("web_url", ""), "title": it.get("title", ""), "changes_count": it.get("changes_count")}
             for it in roh if URL_MR.search(it.get("web_url", ""))]
    zeit = datetime.now().strftime("%d.%m. %H:%M")
    ersetzen(MR_LISTE, json.dumps({"items": items, "zeit": zeit}, ensure_ascii=False))
    return items, zeit

def mr_wagen(akt=None):
    items, _ = mr_liste()
    wagen, gesehen = [], set()
    def wagen_fuer(mr, titel, aenderungen):
        st = review_laden(mr)
        n = sum(1 for k in st["kommentare"] if not k.get("geloescht"))
        fertig = bool(st.get("abgeschlossen")) and not ausstehend(st)
        kurz = mr["projekt"].rsplit("/", 1)[-1]
        return {"p": mr_id(mr), "name": f'!{mr["iid"]} {kurz}', "titel": f'{mr["projekt"]}!{mr["iid"]}: {titel}',
                "zeile2": titel, "datei": "/mr/" + mr_id(mr), "plus": 0, "minus": 0, "dateien": aenderungen or 0,
                "commits": 0, "todos": [], "status": "fertig" if fertig else "offen",
                "marke": "✓ in GitLab" if fertig else (f"● {n} Komm." if n else "● offen")}
    for it in items:
        try:
            mr = mr_ref(it.get("web_url", ""))
        except GitLabFehler:
            continue
        gesehen.add(mr_id(mr))
        wagen.append(wagen_fuer(mr, it.get("title", ""), it.get("changes_count")))
    if akt and akt not in gesehen and not str(akt).startswith("projekt:"):
        try:
            mr = mr_aus_id(akt)
            wagen.insert(0, wagen_fuer(mr, review_laden(mr)["mr"].get("titel", ""), 0))
        except GitLabFehler:
            pass
    return wagen

def startseite(text="", sid=""):
    """Start (GitLab-Modus): Güterbahnhof und Zug, dazu ein Feld zum Öffnen eines MR."""
    daten = json.dumps({"modus": "gitlab", "id": sid, "projekt": sid, "sha": "", "k": schluessel(), "dateien": 0})
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8">{ICON}<title>merge-train</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}{CSS_REVIEW}.uebersicht{{max-width:900px;margin:30px auto;padding:0 16px}}
.uebersicht input{{width:100%;font:14px ui-monospace,monospace;padding:6px 8px;border:1px solid var(--rand);border-radius:6px;background:var(--bg);color:var(--fg)}}</style></head>
<body class="gl"><header id="kopf">{gleise_html(True)}<div class="zeile"><span id="meldung"></span><button id="fertig" hidden></button></div></header>
<main class="uebersicht">{f'<p class="warn">{html.escape(text)}</p>' if text else ""}<p class="sub">MR im Zug wählen. Neue MRs holt „↻ MRs“ im Güterbahnhof.</p>
<form action="/mr-oeffnen"><p><label>MR öffnen (URL oder gruppe/projekt!42):<br><input name="u" autofocus placeholder="https://gitlab…/-/merge_requests/42"></label></p></form>
</main><script>const MR={daten};const ds=[],ls=[];function kh(){{}}{JS_ZUG}{JS_BAHNHOF}</script></body></html>"""
