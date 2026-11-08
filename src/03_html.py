# ---------------------------------------------------------------- HTML

def hunk_zeilen(h, ta_tok, tb_tok):
    """Zeilen paaren: (typ, nr_a, html_a, nr_b, html_b)."""
    def tok(tabelle, nr):
        return tabelle[nr - 1] if tabelle and 0 < nr <= len(tabelle) else None
    rows, a, b, i, z = [], h["a"], h["b"], 0, h["z"]
    while i < len(z):
        if z[i][0] == " ":
            t = z[i][1]
            rows.append(("ctx", a, darstellen(tok(ta_tok, a), t, [], ""),
                         b, darstellen(tok(tb_tok, b), t, [], "")))
            a += 1; b += 1; i += 1
            continue
        weg, dazu = [], []
        while i < len(z) and z[i][0] == "-": weg.append(z[i][1]); i += 1
        while i < len(z) and z[i][0] == "+": dazu.append(z[i][1]); i += 1
        for k in range(max(len(weg), len(dazu))):
            ta = weg[k] if k < len(weg) else None
            tb = dazu[k] if k < len(dazu) else None
            ba, bb = intraline(ta, tb) if ta is not None and tb is not None else ([], [])
            ha = darstellen(tok(ta_tok, a), ta, ba, "del") if ta is not None else None
            hb = darstellen(tok(tb_tok, b), tb, bb, "ins") if tb is not None else None
            rows.append(("chg", a if ta is not None else None, ha, b if tb is not None else None, hb))
            if ta is not None: a += 1
            if tb is not None: b += 1
    return rows

def zeilenzahl(text):
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)

def luecken_von(d, bn):
    """Ausgeblendete Bereiche der neuen Seite: {hunk-index: (von, bis, delta)}, -1 = nach dem letzten Hunk.
    delta = alte Zeile − neue Zeile (zwischen Hunks konstant)."""
    if d["status"] in ("neu", "gelöscht") or not d["hunks"] or not bn:
        return {}
    out, ea, eb = {}, 1, 1
    for i, h in enumerate(d["hunks"]):
        if h["b"] > eb:
            out[i] = (eb, h["b"] - 1, h["a"] - h["b"])
        ea = h["a"] + sum(1 for t, _ in h["z"] if t != "+")
        eb = h["b"] + sum(1 for t, _ in h["z"] if t != "-")
    if bn >= eb:
        out[-1] = (eb, bn, ea - eb)
    return out

def luecke_tr(von, bis, delta, sbs):
    return (f'<tr class="lu" data-von="{von}" data-bis="{bis}" data-d="{delta}"><td class="n"></td>'
            f'<td colspan="{3 if sbs else 2}" class="lu-k">⋯ {bis - von + 1} Zeile(n)</td></tr>')

GENERIERT = re.compile(r"(\.Designer\.cs|ModelSnapshot\.cs|\.min\.(js|css)|\.snap|(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock))$")
SPAETER_ZEILEN, SPAETER_BYTES = 3000, 300_000

def spaeter_grund(d):
    """Große oder generierte Datei: Diff erst auf Klick laden (wie „collapsed“ in GitLab). None = sofort zeigen."""
    if not d["hunks"] or d["binaer"]:
        return None
    if GENERIERT.search(d["neu"]):
        return "generierte Datei"
    zeilen = sum(len(h["z"]) for h in d["hunks"])
    groesse = sum(len(t) for h in d["hunks"] for _, t in h["z"])
    if zeilen > SPAETER_ZEILEN or groesse > SPAETER_BYTES:
        return f"großer Diff ({zeilen} Zeilen, {groesse // 1024} KB)"
    return None

def datei_tabelle(d, alt_text, neu_text, luecken=False):
    """Diff einer Datei als Tabelle (nebeneinander). Die Inline-Ansicht baut der Browser daraus (JS inlBauen)."""
    if d["binaer"]:
        return '<div class="leer">Binärdatei</div>'
    if not d["hunks"]:
        return f'<div class="leer">{html.escape(d.get("leer") or "keine Inhaltsänderung")}</div>'
    lu = luecken_von(d, zeilenzahl(neu_text)) if luecken else {}
    ta_tok = zeilen_tokens(alt_text, d["alt"])
    tb_tok = zeilen_tokens(neu_text, d["neu"])
    sbs = []
    for hi, h in enumerate(d["hunks"]):
        if hi in lu:
            sbs.append(luecke_tr(*lu[hi], True))
        hk = html.escape(f'@@ -{h["a"]} +{h["b"]} @@ {h["kopf"]}')
        sbs.append(f'<tr class="hk"><td></td><td colspan="3">{hk}</td></tr>')
        for typ, na, ha, nb, hb in hunk_zeilen(h, ta_tok, tb_tok):
            if typ == "ctx":
                sbs.append(f'<tr data-a="{na}" data-b="{nb}"><td class="n">{na}</td><td class="c">{ha}</td><td class="n">{nb}</td><td class="c">{hb}</td></tr>')
                continue
            la = f'<td class="n">{na}</td><td class="c weg">{ha}</td>' if ha is not None else '<td class="n"></td><td class="c nix"></td>'
            lb = f'<td class="n">{nb}</td><td class="c dazu">{hb}</td>' if hb is not None else '<td class="n"></td><td class="c nix"></td>'
            attr = (f' data-a="{na}"' if ha is not None else "") + (f' data-b="{nb}"' if hb is not None else "")
            sbs.append(f"<tr{attr}>{la}{lb}</tr>")
    if -1 in lu:
        sbs.append(luecke_tr(*lu[-1], True))
    cs = '<colgroup><col class="cn"><col><col class="cn"><col></colgroup>'
    return f'<table class="sbs">{cs}{"".join(sbs)}</table>'

def datei_html(n, d, alt_text, neu_text, luecken=False, spaeter=None):
    name = d["neu"] if d["alt"] == d["neu"] else f'{d["alt"]} → {d["neu"]}'
    kopf = (f'<summary><span class="st st-{d["status"]}">{d["status"]}</span> '
            f'<b>{html.escape(name)}</b> <span class="p">+{d["plus"]}</span> '
            f'<span class="m">−{d["minus"]}</span></summary>')
    # content-visibility (CSS): nur sichtbare Dateien werden gerendert; geschätzte Höhe hält Scrollbalken/Sprünge stabil
    hoehe = 40 if spaeter or not d["hunks"] else 40 + 21 * (sum(len(h["z"]) for h in d["hunks"]) + 2 * len(d["hunks"]))
    auf = (f'<details open class="datei" id="d{n}" data-pfad="{html.escape(d["neu"])}" '
           f'style="contain-intrinsic-size:auto {hoehe}px">{kopf}')
    if spaeter:
        return (f'{auf}<div class="leer spaet">{html.escape(spaeter)} – '
                f'<button class="laden">Diff laden</button></div></details>')
    return f'{auf}{datei_tabelle(d, alt_text, neu_text, luecken)}</details>'

CSS = r"""@einbetten web/basis.css@"""

JS = r"""@einbetten web/basis.js@"""

JS_ZUG = r"""@einbetten web/zug.js@"""

