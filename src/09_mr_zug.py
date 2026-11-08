# ---------------------------------------------------------------- MR-Zug (MRs zum Review)

_MR_LISTE = {"t": 0, "items": [], "fehler": None}

def mr_liste(neu=False):
    import time
    art = KONF["mr_liste"]
    if art == "keine" or not KONF["gitlab"]:
        return [], None
    if not neu and time.time() - _MR_LISTE["t"] < 60:
        return _MR_LISTE["items"], _MR_LISTE["fehler"]
    host = KONF["gitlab_host"]
    try:
        ich = glab(host, "user")["username"]
        param = {"reviewer": "reviewer_username", "assignee": "assignee_username", "author": "author_username"}.get(art, "reviewer_username")
        items, fehler = glab(host, f"merge_requests?scope=all&state=opened&{param}={enc(ich)}&per_page=50") or [], None
    except (GitLabFehler, KeyError, TypeError) as e:
        items, fehler = [], str(e)
    _MR_LISTE.update(t=time.time(), items=items, fehler=fehler)
    return items, fehler

def mr_wagen(akt=None):
    items, _ = mr_liste()
    wagen, gesehen = [], set()
    def wagen_fuer(mr, titel, aenderungen):
        st = review_laden(mr)
        n = sum(1 for k in st["kommentare"] if not k.get("geloescht"))
        fertig = bool(st.get("abgeschlossen")) and not ausstehend(st)
        kurz = mr["projekt"].rsplit("/", 1)[-1]
        return {"p": mr_id(mr), "name": f'!{mr["iid"]} {kurz}', "titel": f'{mr["projekt"]}!{mr["iid"]}: {titel}',
                "zeile2": titel, "datei": "/mr/" + mr_id(mr), "plus": 0, "minus": 0, "dateien": aenderungen,
                "commits": 0, "todos": [], "status": "fertig" if fertig else "offen",
                "marke": "✓ in GitLab" if fertig else (f"● {n} Komm." if n else "● offen")}
    for it in items:
        try:
            mr = mr_ref(it.get("web_url", ""))
        except GitLabFehler:
            continue
        gesehen.add(mr_id(mr))
        wagen.append(wagen_fuer(mr, it.get("title", ""), it.get("changes_count") or 0))
    if akt and akt not in gesehen:
        try:
            mr = mr_aus_id(akt)
            wagen.insert(0, wagen_fuer(mr, review_laden(mr)["mr"].get("titel", ""), 0))
        except GitLabFehler:
            pass
    return wagen

def mr_uebersicht():
    items, fehler = mr_liste(neu=True)
    zeilen = "".join(
        f'<li><a href="/mr/{html.escape(mr_id(mr_ref(it["web_url"])))}"><b>{html.escape(it.get("references", {}).get("full") or "")}</b> '
        f'{html.escape(it.get("title", ""))}</a> <span class="sub">{html.escape((it.get("author") or {}).get("name", ""))}</span></li>'
        for it in items if URL_MR.search(it.get("web_url", "")))
    art = {"reviewer": "bei denen du Reviewer bist", "assignee": "die dir zugewiesen sind",
           "author": "die du erstellt hast"}.get(KONF["mr_liste"], "")
    liste = (f"<ul>{zeilen}</ul>" if zeilen else f'<p class="sub">Keine offenen Merge-Requests {art}.</p>') \
        if KONF["mr_liste"] != "keine" else ""
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>merge-train: Merge-Requests</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>{CSS}{CSS_REVIEW}.uebersicht{{max-width:900px;margin:40px auto;padding:0 16px}} .uebersicht li{{margin:6px 0}}
.uebersicht input{{width:100%;font:14px ui-monospace,monospace;padding:6px 8px;border:1px solid var(--rand);border-radius:6px;background:var(--bg);color:var(--fg)}}</style></head>
<body><main class="uebersicht"><h1>Merge-Requests {art}</h1>
{f'<p class="warn">GitLab nicht erreichbar: {html.escape(fehler)}</p>' if fehler else ""}{liste}
<form action="/mr-oeffnen"><p><label>MR öffnen (URL oder gruppe/projekt!42):<br><input name="u" autofocus placeholder="https://gitlab…/-/merge_requests/42"></label></p></form>
</main></body></html>"""

