# ---------------------------------------------------------------- Agent-Hinweise (review-markers.json)

HINWEIS_FELDER = {"finding", "title", "path", "needle", "text", "rationale", "resolved_when", "line", "see_also"}

def pfad_norm(p):
    p = str(p or "").strip().replace("\\", "/")
    return p[2:] if p.startswith("./") else p

def see_also_aufloesen(mr, head, eintraege, tag):
    """see_also: Liste aus "pfad", "pfad:zeile" oder {"path", "line"|"needle", "label"} → Zeilen im MR-Stand.
    Nur für merge-train (Links/Popup), nie Teil des GitLab-Kommentars."""
    if isinstance(eintraege, (str, dict)):
        eintraege = [eintraege]
    out = []
    for e in eintraege if isinstance(eintraege, list) else []:
        if isinstance(e, str):
            m = re.fullmatch(r"(.+?)(?::(\d+))?", e.strip())
            e = {"path": m.group(1), "line": int(m.group(2)) if m.group(2) else None} if m else {}
        if not isinstance(e, dict):
            continue
        path, zeile, problem = pfad_norm(e.get("path")), None, None
        if isinstance(e.get("line"), int) and e["line"] > 0:
            zeile = e["line"]
        if not path:
            problem = "kein Pfad"
        elif head:
            t = inhalt(mr, head, path)
            if t is None:
                problem = "Datei nicht im MR-Stand"
            elif zeile and zeile > zeilenzahl(t):
                problem = f"Zeile {zeile} gibt es nicht ({zeilenzahl(t)} Zeilen)"
            elif not zeile and e.get("needle"):
                z = needle_zeilen(t, str(e["needle"]), tag)
                zeile = z[0] if z else None
                problem = None if z else "needle nicht gefunden"
        out.append({"path": path, "zeile": zeile, "label": e.get("label"), "problem": problem})
    return out
_HW_CACHE = {}

def hinweise_lesen(pfad):
    """Hinweis-Datei lesen und vereinheitlichen (auch Altformat: nur das markers-Array)."""
    st = os.stat(pfad)
    k = (pfad, st.st_mtime_ns, st.st_size)
    if k in _HW_CACHE:
        return _HW_CACHE[k]
    daten = json.load(open(pfad, encoding="utf-8-sig"))
    if isinstance(daten, list):
        daten = {"markers": daten}
    if not isinstance(daten, dict) or not isinstance(daten.get("markers", []), list):
        raise ValueError("erwartet ein Objekt mit „markers“-Liste (oder nur die Liste)")
    for i, m in enumerate(daten.get("markers") or []):
        if not isinstance(m, dict):
            raise ValueError(f"markers[{i}] ist kein Objekt")
        if not str(m.get("text") or "").strip():
            raise ValueError(f"markers[{i}]: „text“ fehlt")
    daten.setdefault("markers", [])
    _HW_CACHE[k] = daten
    return daten

def hinweis_passt(pfad, info):
    try:
        h = hinweise_lesen(pfad)
    except (OSError, ValueError):
        return False
    if h.get("mr"):
        try:
            ref = mr_ref(h["mr"], os.path.dirname(pfad))
        except GitLabFehler:
            return False
        return ref["iid"] == info.get("iid") and (ref["projekt"] or "").lower() == (info.get("projekt") or "").lower()
    return bool(h.get("branch")) and h["branch"] == info.get("source_branch")

def hinweis_dateien(mr, st):
    dateien = [p for p in st["hinweis_dateien"] if os.path.exists(p)]
    for muster in KONF["hinweise"]:
        for p in sorted(glob.glob(os.path.expanduser(muster))):
            p = os.path.abspath(p)
            if p not in dateien and hinweis_passt(p, st["mr"]):
                dateien.append(p)
    return dateien

def needle_zeilen(text, needle, tag):
    rx = re.compile(r"\s*(//|<!--) " + re.escape(tag) + r"(?![0-9A-Za-z]).*$") if tag else None
    out = []
    for nr, z in enumerate(text.split("\n"), 1):
        if rx:
            z = rx.sub("", z)
        if (z.strip() == needle[1:].strip()) if needle.startswith("=") else (needle in z):
            out.append(nr)
    return out

def hinweise_aufloesen(mr, st, struktur, nur=None):
    """Hinweise aller Dateien auf Zeilen des MR-Stands abbilden. Rückgabe (hinweise, quellen)."""
    hinweise, quellen = [], []
    head = (struktur or {}).get("refs", {}).get("head_sha")
    for pfad in (nur if nur is not None else hinweis_dateien(mr, st)):
        try:
            h = hinweise_lesen(pfad)
        except (OSError, ValueError) as e:
            quellen.append({"datei": pfad, "fehler": f"nicht lesbar: {e}", "anzahl": 0}); continue
        tag = str(h.get("tag") or "")
        name = h.get("key") or os.path.basename(pfad)
        quellen.append({"datei": pfad, "key": h.get("key"), "notes": h.get("notes"), "anzahl": len(h["markers"]),
                        "reviewed_commit": h.get("reviewed_commit"), "reviewed_at": h.get("reviewed_at"),
                        "failing_tests": h.get("failing_tests"),
                        "alt": bool(head and h.get("reviewed_commit") and not head.startswith(str(h["reviewed_commit"])))})
        for m in h["markers"]:
            text = str(m.get("text") or "").strip()
            fid = str(m.get("finding") or (re.match(r"(#\d+|K\d+)\b", text) or [""])[0])  # ID nur noch lokal, nicht mehr im Text nötig
            path = pfad_norm(m.get("path"))
            needle = str(m.get("needle") or "")
            basis = {"finding": fid, "text": text, "rationale": m.get("rationale"), "resolved_when": m.get("resolved_when"),
                     "extra": {k: v for k, v in m.items() if k not in HINWEIS_FELDER}, "path": path, "quelle": name,
                     "see_also": see_also_aufloesen(mr, head, m.get("see_also"), tag),
                     "title": str(m.get("title") or "").strip() or None}
            zeilen, problem = [], None
            if not path:
                pass  # allgemeiner Hinweis zum MR
            elif isinstance(m.get("line"), int) and m["line"] > 0:
                zeilen = [m["line"]]
            elif not head:
                problem = "MR-Stand unbekannt"
            else:
                t = inhalt(mr, head, path)
                if t is None:
                    problem = "Datei nicht im MR-Stand"
                elif not needle:
                    problem = "kein needle"
                else:
                    zeilen = needle_zeilen(t, needle, tag)
                    if not zeilen:
                        problem = "needle nicht gefunden"
            i = datei_index(struktur, path)
            f = struktur["dateien"][i] if i is not None else None
            for j, z in enumerate(zeilen or [None]):
                key = hashlib.sha1(f"{name}|{fid}|{path}|{needle}|{text}|{j}".encode()).hexdigest()[:12]
                a = alt_zeile(f, z) if f and z else None
                imd = bool(f and z and im_diff(f, a, z))
                pr = problem or (None if imd else ("Zeile außerhalb des Diffs" if f else "Datei nicht im Diff") if z else None)
                hinweise.append(dict(basis, key=key, zeile=z, datei=i, a=a, b=z, im_diff=imd, problem=pr,
                                     mehrfach=len(zeilen) if len(zeilen) > 1 else None,
                                     status=st["hinweise"].get(key, "offen")))
    return hinweise, quellen

def stand(mr, st):
    teile = [st.get("struktur") or ""]
    for p in [review_datei(mr)] + hinweis_dateien(mr, st):
        try:
            s = os.stat(p); teile.append(f"{p}:{s.st_mtime_ns}:{s.st_size}")
        except OSError:
            teile.append(p + ":-")
    return hashlib.sha1("|".join(teile).encode()).hexdigest()[:16]

def review_daten(mr):
    with SPERRE:
        st = review_laden(mr)
    struktur = struktur_laden(st)
    if struktur is None:
        _, struktur, mr = mr_seite(mr)
        st = review_laden(mr)
    hinweise, quellen = hinweise_aufloesen(mr, st, struktur)
    kom = []
    for k in st["kommentare"]:
        i = datei_index(struktur, k.get("path"))
        f = struktur["dateien"][i] if i is not None else None
        kom.append({"id": k["id"], "text": k["text"], "path": k.get("path"), "a": k.get("a"), "b": k.get("b"),
                    "datei": i, "im_diff": bool(f and (k.get("a") or k.get("b")) and im_diff(f, k.get("a"), k.get("b"))),
                    "finding": k.get("finding"), "hinweis": k.get("hinweis"), "status": k_status(k)})
    return {"ok": True, "kommentare": kom, "hinweise": hinweise, "quellen": quellen, "stand": stand(mr, st),
            "web_url": st["mr"].get("web_url", ""), "ausstehend": ausstehend(st)}

def datei_nachladen(mr, i):
    """Diff einer zunächst ausgelassenen (großen/generierten) Datei – nur im lokalen Modus."""
    with SPERRE:
        st = review_laden(mr)
    struktur = struktur_laden(st)
    try:
        if i < 0:
            raise IndexError
        f = struktur["dateien"][i]
    except (TypeError, IndexError):
        return {"ok": False, "text": "unbekannte Datei – Seite neu laden"}
    if struktur.get("quelle") != "lokal" or not struktur.get("ordner"):
        return {"ok": False, "text": "nur im lokalen Modus möglich"}
    refs = struktur["refs"]
    out = git(struktur["ordner"], "-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "-M", "-U3",
              refs["base_sha"], refs["head_sha"], "--", *dict.fromkeys([f["alt"], f["neu"]]), check=False)
    d = next((x for x in zerlegen(out or "") if x["neu"] == f["neu"]), None)
    if d is None:
        return {"ok": False, "text": "Diff nicht gefunden"}
    alt = inhalt(mr, refs["base_sha"], d["alt"]) if d["status"] != "neu" else ""
    neu = inhalt(mr, refs["head_sha"], d["neu"]) if d["status"] != "gelöscht" else ""
    return {"ok": True, "html": datei_tabelle(d, alt, neu, luecken=True)}

_TOKENS = {}

def zeilen_daten(mr, pfad, von, bis):
    """Zeilen von..bis (neue Seite, MR-Stand) als HTML – zum Nachladen von Kontext und fürs Popup."""
    with SPERRE:
        st = review_laden(mr)
    struktur = struktur_laden(st)
    head = ((struktur or {}).get("refs") or {}).get("head_sha")
    if not head:
        return {"ok": False, "text": "MR-Stand unbekannt – Seite neu laden"}
    pfad = pfad_norm(pfad)
    text = inhalt(mr, head, pfad)
    if text is None:
        return {"ok": False, "text": f"{pfad} gibt es im MR-Stand {head[:8]} nicht"}
    zeilen = text.replace("\r\n", "\n").split("\n")
    if zeilen and zeilen[-1] == "":
        zeilen.pop()
    k = (mr_id(mr), head, pfad)
    if k not in _TOKENS:
        if len(_TOKENS) > 40:
            _TOKENS.clear()
        _TOKENS[k] = zeilen_tokens(text, pfad)
    toks = _TOKENS[k]
    von = max(1, von); bis = min(len(zeilen), bis, von + 4999)
    return {"ok": True, "n": len(zeilen), "von": von, "bis": bis, "sha": head,
            "zeilen": [darstellen(toks[i - 1] if toks and i <= len(toks) else None, zeilen[i - 1], [], "")
                       for i in range(von, bis + 1)]}

def kommentar_aktion(mr, d):
    """neu | aendern | loeschen | wiederherstellen. Rückgabe (ok, text)."""
    aktion = d.get("aktion")
    with SPERRE:
        st = review_laden(mr)
        struktur = struktur_laden(st)
        if aktion == "neu":
            text = str(d.get("text") or "").strip()
            k = {"id": hashlib.sha1(os.urandom(16)).hexdigest()[:10], "refs": (struktur or {}).get("refs"),
                 "erstellt": datetime.now().isoformat(timespec="seconds")}
            if d.get("hinweis"):
                h = next((h for h in hinweise_aufloesen(mr, st, struktur)[0] if h["key"] == d["hinweis"]), None)
                if not h:
                    return False, "Hinweis nicht mehr vorhanden – Seite neu laden."
                i = h["datei"]
                k.update(text=text or h["text"], path=h["path"] or None, a=h["a"], b=h["b"], finding=h["finding"],
                         hinweis=h["key"], old_path=struktur["dateien"][i]["alt"] if i is not None else h["path"])
                st["hinweise"][h["key"]] = "uebernommen"
            elif d.get("datei") is not None:
                if not struktur or d.get("sha") != struktur["refs"].get("head_sha"):
                    return False, "Der MR hat inzwischen einen neuen Stand – bitte Seite neu laden."
                try:
                    f = struktur["dateien"][int(d["datei"])]
                except (ValueError, IndexError):
                    return False, "unbekannte Datei"
                a = int(d["a"]) if d.get("a") is not None else None
                b = int(d["b"]) if d.get("b") is not None else None
                if (a is None and b is None) or not (im_diff(f, a, b) or kontext_zeile(f, a, b)):
                    return False, "Zeile nicht im Diff"
                k.update(text=text, path=f["neu"], old_path=f["alt"], a=a, b=b)
            else:
                k.update(text=text, path=None, a=None, b=None)
            if not k["text"]:
                return False, "leerer Kommentar"
            st["kommentare"].append(k)
        else:
            k = next((k for k in st["kommentare"] if k["id"] == d.get("id")), None)
            if not k:
                return False, "Kommentar nicht gefunden"
            if aktion == "aendern":
                text = str(d.get("text") or "").strip()
                if not text:
                    return False, "leerer Kommentar"
                k["text"] = text
            elif aktion == "loeschen":
                if k.get("hinweis"):
                    st["hinweise"][k["hinweis"]] = "verworfen"
                if k.get("gitlab_id") and not k.get("gitlab_weg"):
                    k["geloescht"] = True  # Entwurf in GitLab wird beim Abschließen gelöscht
                else:
                    st["kommentare"].remove(k)
            elif aktion == "wiederherstellen":
                k.pop("geloescht", None)
            else:
                return False, "unbekannte Aktion"
        review_speichern(mr, st)
    return True, ""

def hinweis_aktion(mr, d):
    with SPERRE:
        st = review_laden(mr)
        key = str(d.get("key") or "")
        if d.get("aktion") == "verwerfen":
            st["hinweise"][key] = "verworfen"
        elif d.get("aktion") == "zurueck":
            st["hinweise"].pop(key, None)
        else:
            return False, "unbekannte Aktion"
        review_speichern(mr, st)
    return True, ""

def entwurf_anlegen(mr, k, head, proj_url):
    """Draft-Note anlegen: an der Zeile, sonst (oder wenn GitLab ablehnt) als allgemeiner Kommentar mit Link."""
    host, P = mr["host"], mr_pfad(mr)
    refs = k.get("refs") or {}
    if k.get("path") and (k.get("a") or k.get("b")) and refs.get("head_sha"):
        pos = {"position_type": "text", "base_sha": refs.get("base_sha"), "start_sha": refs.get("start_sha"),
               "head_sha": refs["head_sha"], "old_path": k.get("old_path") or k["path"], "new_path": k["path"]}
        if k.get("a"): pos["old_line"] = k["a"]
        if k.get("b"): pos["new_line"] = k["b"]
        try:
            return glab(host, f"{P}/draft_notes", "POST", {"note": k["text"], "position": pos}), "position"
        except GitLabFehler as e:
            fehler = str(e)
            if re.search(r"\b(401|403|404)\b", fehler):
                raise
    text = k["text"]
    if k.get("path"):
        z = k.get("b") or k.get("a")
        ref = refs.get("head_sha") or head
        ort = f'{k["path"]}:{z}' if z else k["path"]
        link = f'{proj_url}/-/blob/{ref}/{k["path"]}' + (f"#L{z}" if z else "")
        text = f"**[`{ort}`]({link})**\n\n{text}"
    return glab(host, f"{P}/draft_notes", "POST", {"note": text}), "allgemein" if k.get("path") else "mr"

def abschliessen(mr):
    """Kommentare als Entwürfe (Draft-Notes) in den MR übertragen – nicht veröffentlichen."""
    host, P = mr["host"], mr_pfad(mr)
    with SPERRE:
        st = review_laden(mr)
        web = st["mr"].get("web_url", "")
        proj_url = web.split("/-/merge_requests/")[0]
        head = ((struktur_laden(st) or {}).get("refs") or {}).get("head_sha")
        try:
            vorhanden = {d.get("id") for d in alle(host, f"{P}/draft_notes")}
        except GitLabFehler as e:
            return False, f"Entwürfe nicht abrufbar: {e}", web
        z = {"neu": 0, "allg": 0, "akt": 0, "weg": 0, "verschwunden": 0}
        fehler = []
        for k in list(st["kommentare"]):
            try:
                if k.get("geloescht"):
                    if k.get("gitlab_id") in vorhanden:
                        glab(host, f'{P}/draft_notes/{k["gitlab_id"]}', "DELETE"); z["weg"] += 1
                    st["kommentare"].remove(k)
                elif k.get("gitlab_weg"):
                    pass
                elif k.get("gitlab_id"):
                    if k["gitlab_id"] not in vorhanden:
                        k["gitlab_weg"] = True; z["verschwunden"] += 1  # in GitLab veröffentlicht oder gelöscht
                    elif k["text"] != k.get("gitlab_text"):
                        glab(host, f'{P}/draft_notes/{k["gitlab_id"]}', "PUT", {"note": k["text"]})
                        k["gitlab_text"] = k["text"]; z["akt"] += 1
                else:
                    r, art = entwurf_anlegen(mr, k, head, proj_url)
                    k.update(gitlab_id=(r or {}).get("id"), gitlab_text=k["text"], gitlab_art=art)
                    z["neu"] += 1; z["allg"] += art == "allgemein"
            except GitLabFehler as e:
                fehler.append(f'{k.get("path") or "allgemein"}{":" + str(k.get("b") or k.get("a")) if k.get("b") or k.get("a") else ""}: {e}')
            review_speichern(mr, st)
        if not fehler:
            st["abgeschlossen"] = datetime.now().isoformat(timespec="seconds")
            review_speichern(mr, st)
    teile = []
    if z["neu"]: teile.append(f'{z["neu"]} neu' + (f' ({z["allg"]} als allgemeiner Kommentar mit Link)' if z["allg"] else ""))
    if z["akt"]: teile.append(f'{z["akt"]} aktualisiert')
    if z["weg"]: teile.append(f'{z["weg"]} gelöscht')
    text = ("Entwürfe in GitLab: " + ", ".join(teile) + ". Jetzt in GitLab prüfen und dort das Review abschicken."
            if teile else "Nichts zu übertragen – alles ist schon als Entwurf in GitLab.")
    if z["verschwunden"]:
        text += f' {z["verschwunden"]} Entwurf/Entwürfe gibt es in GitLab nicht mehr (veröffentlicht oder dort gelöscht).'
    if fehler:
        text = "Fehler: " + " | ".join(fehler) + (" – Rest: " + text if teile else "")
    return not fehler, text, web

