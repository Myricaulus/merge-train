# ---------------------------------------------------------------- CLI für Agenten

def mr_fuer_hinweise(pfad, daten, ref=None):
    """Zu welchem MR gehört die Hinweis-Datei? --mr, sonst Feld „mr“, sonst offener MR des Branches."""
    ordner = (git(os.path.dirname(pfad), "rev-parse", "--show-toplevel", check=False) or "").strip() \
        or os.path.dirname(pfad)
    ref = ref or daten.get("mr")
    if ref:
        mr = mr_vollstaendig(mr_ref(str(ref), ordner))
    else:
        branch = daten.get("branch")
        if not branch:
            raise GitLabFehler("kein MR zuzuordnen: --mr angeben oder „branch“/„mr“ in die JSON schreiben")
        host, projekt = remote_info(ordner)
        lst = glab(host, f"projects/{enc(projekt)}/merge_requests?state=opened&source_branch={enc(branch)}")
        if not lst:
            raise GitLabFehler(f"kein offener MR für Branch {branch} in {projekt} – --mr angeben")
        mr = mr_ref(lst[0]["web_url"])
        mr["host"] = mr["host"] or host
    return mr, ordner

def agent_main(argv):
    ap = argparse.ArgumentParser(prog="merge-train agent",
                                 description="Agent-Hinweise (tasks/<KEY>-review-markers.json) einem GitLab-MR zuordnen und anzeigen")
    sub = ap.add_subparsers(dest="befehl")
    for name, hilfe in (("zeigen", "Datei beim MR anmelden, Zuordnung ausgeben und den MR im Browser öffnen"),
                        ("pruefen", "nur prüfen: auf welche Zeilen des MR-Stands die Hinweise fallen (Exit 1 bei Problemen)")):
        p = sub.add_parser(name, help=hilfe, description=hilfe)
        p.add_argument("datei", help="Hinweis-Datei (JSON)")
        p.add_argument("--mr", help="MR-URL, '!42' oder gruppe/projekt!42 (sonst Feld „mr“ oder der offene MR zu „branch“)")
        p.add_argument("--seit", nargs="?", const="", metavar="COMMIT",
                       help="Review-Update: Stand der Einträge seit COMMIT (ohne Wert: reviewed_commit der JSON)")
        if name == "zeigen":
            p.add_argument("--nicht-oeffnen", action="store_true", help="Browser nicht öffnen, nur URL ausgeben")
    o = ap.parse_args(argv)
    if not o.befehl:
        ap.print_help(); return 2
    pfad = os.path.abspath(o.datei)
    try:
        daten = hinweise_lesen(pfad)
    except (OSError, ValueError) as e:
        print(f"merge-train: {o.datei} nicht lesbar: {e}", file=sys.stderr); return 2
    try:
        mr, ordner = mr_fuer_hinweise(pfad, daten, o.mr)
        with SPERRE:  # Repo der Hinweis-Datei als lokalen Klon merken (vor dem Seitenaufbau)
            st = review_laden(mr)
            try:
                if remote_info(ordner)[1].lower() == (mr["projekt"] or "").lower() and st.get("klon") != ordner:
                    st["klon"] = ordner; review_speichern(mr, st)
            except GitLabFehler:
                pass
        mr, meta = mr_meta_holen(mr)  # die einzige GitLab-Anfrage: aktuelle MR-Daten für die Seite merken
    except GitLabFehler as e:
        print(f"merge-train: {e}", file=sys.stderr); return 2
    try:
        _, struktur, mr = mr_seite(mr)
    except GitLabFehler as e:
        print(f"merge-train: {e}", file=sys.stderr); return 3
    with SPERRE:
        st = review_laden(mr)
        if o.befehl == "zeigen" and pfad not in st["hinweis_dateien"]:
            st["hinweis_dateien"].append(pfad)
            review_speichern(mr, st)
    head = struktur["refs"].get("head_sha") or ""
    geaendert, seit = None, None
    if o.seit is not None:
        seit = o.seit or str(daten.get("reviewed_commit") or "")
        if not seit:
            print("merge-train: --seit ohne Commit und kein reviewed_commit in der JSON", file=sys.stderr); return 2
        try:
            geaendert = geaenderte_dateien(mr, seit, head)
        except GitLabFehler as e:
            print(f"merge-train: {e}", file=sys.stderr); return 2
    hinweise, _ = hinweise_aufloesen(mr, st, struktur, nur=[pfad])
    print(f'{mr["projekt"]}!{mr["iid"]} · Stand {head[:8]} · {len(daten["markers"])} Einträge')
    print(f'Quelle: lokal ({kurzpfad(struktur["ordner"])})')
    gl_head = (meta.get("diff_refs") or {}).get("head_sha") or ""
    abweichend = gl_head and gl_head != head
    if abweichend:
        print(f"Achtung: GitLab steht auf {gl_head[:8]}, der lokale Branch auf {head[:8]} – Branch aktualisieren")
    if geaendert is not None:
        print(f"seit {seit}: {len(geaendert)} Datei(en) geändert")
    schlecht = 0
    for h in hinweise:
        ort = f'{h["path"]}:{h["zeile"]}' if h["zeile"] else (h["path"] or "-")
        fehlt = not h["zeile"] and h["path"]
        if geaendert is not None and h["path"]:
            if h["problem"] == "Datei nicht im MR-Stand":
                zustand = "WEG: Datei gibt es nicht mehr → Diff gegen resolved_when prüfen"
            elif fehlt:
                zustand = f'GEÄNDERT: {h["problem"]} → Diff gegen resolved_when prüfen'
            else:
                zustand = "offen* (Datei geändert)" if h["path"] in geaendert else "offen (Datei unverändert)"
            fehlt = False
        elif not h["path"]:
            zustand = "allgemeiner MR-Kommentar"
        elif h["im_diff"]:
            zustand = "im Diff"
        elif h["zeile"]:
            zustand = f'{h["problem"]} → wird allgemeiner Kommentar mit Link'
        else:
            zustand = f'FEHLT: {h["problem"]}'
        schlecht += bool(fehlt)
        if h["mehrfach"]:
            zustand += f' (needle passt {h["mehrfach"]}×)'
        if h["status"] != "offen":
            zustand += f' [{h["status"]}]'
        print(f'{h["finding"]:<5} {ort:<60} {zustand}')
        for s in h["see_also"]:
            if s["problem"]:
                print(f'{"":<5}   siehe auch {s["path"] or "-"}: FEHLT: {s["problem"]}'); schlecht += 1
    if o.befehl == "zeigen":
        im_browser("/mr/" + mr_id(mr), nur_url=o.nicht_oeffnen)
    if schlecht:
        return 1
    return 3 if abweichend else 0

def geaenderte_dateien(mr, von, bis):
    """Pfade (alt und neu), die sich zwischen von und bis geändert haben (lokaler Klon)."""
    for o in lokale_klone(mr):
        out = git(o, "-c", "core.quotepath=false", "diff", "--name-status", "-M", von, bis, check=False)
        if out is not None:
            return {p for z in out.splitlines() for p in z.split("\t")[1:]}
    raise GitLabFehler(f"Commit {von} ist im lokalen Klon nicht bekannt (git fetch)")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "agent":
        sys.exit(agent_main(sys.argv[2:]))
    ap = argparse.ArgumentParser(description=f"merge-train: Merge-Requests {BIS} → {VON} aller Projekte, GitLab-MRs reviewen "
                                             "(„merge-train agent -h“ für Agent-Hinweise)")
    ap.add_argument("ordner", nargs="?", help="nur dieses Projekt (Ordner oder Name unter ~/Projects), oder ein GitLab-MR "
                                              "(URL, '!42', gruppe/projekt!42); ohne: der ganze Zug, beginnend beim größten")
    ap.add_argument("--von", default=VON)
    ap.add_argument("--bis", default=BIS)
    ap.add_argument("--mrs", action="store_true", help="GitLab-MRs zum Review (Reviewer = ich) zeigen")
    ap.add_argument("--alle", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--inline", action="store_true", help="inline statt nebeneinander starten")
    ap.add_argument("--nur-datei", action="store_true", help="HTML erzeugen bzw. URL ausgeben, nicht öffnen")
    ap.add_argument("--server", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--projekte", action="store_true", help=argparse.SUPPRESS)  # für die Shell-Vervollständigung
    o = ap.parse_args()
    if o.server:
        return server()
    if o.projekte:
        if not KONF["lokal"]:
            return
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(8) as ex:
            st = list(ex.map(statistik, finde_repos()))
        st.sort(key=lambda w: (not w["dateien"], -(w["plus"] + w["minus"])))
        for w in st:
            print(f'{w["p"]}\t+{w["plus"]} −{w["minus"]} · {w["dateien"]} Datei(en)' if w["dateien"] else f'{w["p"]}\taktuell')
        return
    if o.ordner and ist_mr_ref(o.ordner) and not os.path.exists(o.ordner):
        if not KONF["gitlab"]:
            sys.exit("merge-train: GitLab ist abgeschaltet (gitlab = false in der Einstellung)")
        try:  # Aufruf von Hand: MR-Daten einmal holen, die Seite selbst fragt GitLab nicht
            mr, _ = mr_meta_holen(mr_vollstaendig(mr_ref(o.ordner, os.getcwd())))
        except GitLabFehler as e:
            sys.exit(f"merge-train: {e}")
        return im_browser("/mr/" + mr_id(mr), o.nur_datei)
    if o.mrs or (not o.ordner and not KONF["lokal"]):
        if not KONF["gitlab"]:
            sys.exit("merge-train: lokal und gitlab sind beide abgeschaltet – siehe " + KONFIG_DATEI)
        return im_browser("/mrs" if KONF["lokal"] else "/", o.nur_datei)
    if not KONF["lokal"]:
        sys.exit(f"merge-train: lokaler Projekt-Diff ist abgeschaltet (lokal = false in {KONFIG_DATEI}) – "
                 "MR-URL, '!42' oder --mrs angeben")
    wurzel = None
    if o.ordner:  # ohne Projekt: immer der ganze Zug
        ordner = o.ordner
        if o.ordner and not os.path.exists(ordner):
            ordner = os.path.join(PROJEKTE, o.ordner)
        wurzel = (git(ordner, "rev-parse", "--show-toplevel", check=False) or "").strip() or None
        if o.ordner and not wurzel:
            sys.exit(f"merge-train: kein Git-Repo: {o.ordner}")
    if wurzel and not all(git(wurzel, "rev-parse", "--verify", "-q", b, check=False) for b in (o.von, o.bis)):
        sys.exit(f"merge-train: Branch {o.von} oder {o.bis} fehlt in {wurzel}")
    repos, wagen = alles_erzeugen(o.von, o.bis, o.inline)
    if wurzel:
        ziel, _ = projekt_seite(wurzel, o.von, o.bis)
    else:
        offen = [w for w in wagen if w["status"] == "offen"]
        if not offen:
            print(f"merge-train: nichts zu prüfen – überall {VON} = {BIS}"); return
        ziel = next(projekt_seite(r)[0] for r in repos if projektname(r) == offen[0]["p"])
    if o.nur_datei or o.von != VON or o.bis != BIS or o.inline:
        print(ziel)
        if not o.nur_datei:
            oeffnen(ziel)
        return
    url = f"http://127.0.0.1:{PORT}/{dateiname(projektname(wurzel)) if wurzel else offen[0]['datei']}" \
        if server_sicherstellen() else ziel
    print(url)
    oeffnen(url)

if __name__ == "__main__":
    main()
