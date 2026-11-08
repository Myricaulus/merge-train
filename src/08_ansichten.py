# ---------------------------------------------------------------- Commit-Ansichten (nur dieser Commit / seit einem Commit)
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
        raise GitLabFehler(f"Commit {sha[:12]} gibt es im lokalen Klon nicht")
    im_mr = (git(ordner, "rev-list", f'{refs["base_sha"]}..{refs["head_sha"]}', check=False) or "").split()
    if voll not in im_mr:
        raise GitLabFehler(f"Commit {sha[:12]} gehört nicht zu diesem MR")
    titel = (git(ordner, "log", "-1", "--format=%s", voll, check=False) or "").strip()
    eltern = (git(ordner, "rev-list", "--parents", "-n1", voll, check=False) or "").split()[1:]
    if art == "commit":
        von, bis, anzahl = (eltern[0] if eltern else LEERER_BAUM), voll, 1
    else:
        von, bis, anzahl = voll, refs["head_sha"], im_mr.index(voll)  # rev-list: neueste zuerst
    return {"art": art, "sha": voll, "von": von, "bis": bis, "titel": titel, "kurz": voll[:8],
            "anzahl": anzahl, "merge": len(eltern) > 1}

def ansicht_html(slug, ans):
    zurueck = f'<a href="/mr/{html.escape(slug)}">ganzer MR</a>'
    t = f'<code>{html.escape(ans["kurz"])}</code> „{html.escape(ans["titel"])}“'
    if ans["art"] == "commit":
        merge = " · Merge-Commit: Diff gegen den ersten Vorgänger" if ans["merge"] else ""
        text = (f'Nur Commit {t}{merge} · <b>nur lesen</b>: Kommentare und Hinweise stehen an ihrer Zeile, '
                f'wenn sie sich zuordnen lassen, sonst unter dem Dateinamen')
    else:
        text = (f'Änderungen seit {t} ({ans["anzahl"]} Commit(s) danach) · kommentieren rechts (MR-Stand)')
    return f'<div id="ansicht" class="ansicht">{text} · {zurueck}</div>'

def diff_enden(struktur):
    """(von, bis) des Diffs einer Seite: Ansicht oder ganzer MR."""
    a = struktur.get("ansicht")
    return (a["von"], a["bis"]) if a else (struktur["refs"]["base_sha"], struktur["refs"]["head_sha"])

def ansicht_struktur(mr, haupt, ansicht):
    """Struktur der Ansichts-Seite (erzeugt sie bei Bedarf)."""
    p = seiten_stamm(mr, haupt["refs"]["head_sha"], "lokal", {"art": ansicht[0], "sha": ansicht[1]}) + ".json"
    if p not in STRUKTUR:
        if not os.path.exists(p):
            return mr_seite(mr, ansicht=ansicht)[1]
        STRUKTUR[p] = json.load(open(p, encoding="utf-8"))
    return STRUKTUR[p]

_ZURUECK = {}

def zurueck_diffs(ordner, bis, head, pfade):
    """Diff bis → head für die Pfade: {pfad im MR-Stand: datei (paare/hunks/alt)}; fehlt = seitdem unverändert."""
    k = (ordner, bis, head, tuple(sorted(pfade)))
    if k not in _ZURUECK:
        out = git(ordner, "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "-M", "-U3",
                  bis, head, "--", *sorted(pfade), check=False) if pfade else ""
        r = {}
        for d in zerlegen(out or ""):
            paare, hunks = paare_und_hunks(d)
            r[d["neu"]] = {"alt": d["alt"], "status": d["status"], "paare": paare, "hunks": hunks}
        if len(_ZURUECK) > 50:
            _ZURUECK.clear()
        _ZURUECK[k] = r
    return _ZURUECK[k]

def ansicht_zuordnen(haupt, ans_st, eintraege):
    """Kommentare/Hinweise (Zeilen im MR-Stand) in die Ansicht übertragen. Ändert die Einträge:
    datei/a/b/im_diff in Ansichts-Zeilen, „unter“ = Hinweistext, wenn sie unter dem Dateinamen stehen,
    „lesen“ = nicht änderbar, „mr_b“/„mr_a“ = Zeile im MR-Stand. Rückgabe: Einträge in Dateien der Ansicht."""
    ans = ans_st["ansicht"]
    commit = ans["art"] == "commit"
    zurueck = zurueck_diffs(ans_st["ordner"], ans["bis"], haupt["refs"]["head_sha"],
                            {x["path"] for x in eintraege if x.get("path")}) if commit else {}
    out = []
    for x in eintraege:
        x["mr_a"], x["mr_b"] = x.get("a"), x.get("b")
        x["lesen"] = commit
        if not x.get("path"):  # allgemein
            out.append(x); continue
        z = zurueck.get(x["path"])
        if z and z["status"] == "neu":
            continue  # Datei gab es nach dem Commit an diesem Pfad noch nicht
        i = datei_index(ans_st, z["alt"] if z else x["path"])
        if i is None:
            continue  # Datei ist in dieser Ansicht nicht geändert
        f = ans_st["dateien"][i]
        b, unter = x.get("b"), None
        if b and z:
            b = alt_zeile(z, b)  # Zeile im MR-Stand → Zeile nach dem Commit (None = später geändert)
            if b is None:
                unter = f'Zeile {x["mr_b"]} wurde nach diesem Commit noch geändert'
        elif not b:
            unter = ("Kommentar zur alten Seite des MR – hier nicht zuzuordnen" if x.get("a")
                     else x.get("problem") or "ohne Zeile")
            if not commit:
                x["lesen"] = True
        a = alt_zeile(f, b) if b else None
        imd = bool(b and im_diff(f, a, b))
        if b and not imd:
            unter = f"Zeile {b} liegt außerhalb der Änderungen" + (" dieses Commits" if commit else "")
        x.update(datei=i, a=a, b=b, im_diff=imd, unter=unter)
        if b and "problem" in x:
            x["problem"] = None
        out.append(x)
    return out
