"""Aufruf von der Kommandozeile."""
import argparse, os, sys
from .einstellungen import ARBEITSSTAND, BIS, KONF, KONFIG_DATEI, VON, dateiname, projektname
from .waggon import Fehler, von_bis
from .git import ANLASS, fehlende_zweige, finde_repos, git, projekt_ordner, statistik
from .gitlab import ist_mr_ref, mr_meta_holen, mr_ref, mr_vollstaendig
from .quellen import LOKAL
from .prozess import im_browser, server, server_stoppen
from .instanz import beobachten_starten, zur_instanz
from .agent_cli import agent_main

def main():
    ANLASS.name = ("cli " + " ".join(sys.argv[1:3]))[:32]
    if len(sys.argv) > 1 and sys.argv[1] in ("agent", "status"):  # „merge-train status“ = „merge-train agent status“
        zur_instanz(sys.argv[1:])  # läuft für dieses Repo eine --beobachten-Instanz: dort weiter
        sys.exit(agent_main(sys.argv[2:] if sys.argv[1] == "agent" else sys.argv[1:]))
    ap = argparse.ArgumentParser(prog="merge-train", description=f"merge-train: Merge-Requests {BIS} → {VON} aller Projekte, GitLab-MRs reviewen "
                                             "(„merge-train agent -h“ für Agent-Hinweise)")
    ap.add_argument("ordner", nargs="?", help="nur dieses Projekt (Ordner oder Name unter ~/Projects), oder ein GitLab-MR "
                                              "(URL, '!42', gruppe/projekt!42); ohne: der ganze Zug, beginnend beim größten")
    ap.add_argument("--mrs", action="store_true", help="GitLab-MRs zum Review (Reviewer = ich) zeigen")
    ap.add_argument("--nur-datei", action="store_true", help="nur die URL ausgeben, nicht öffnen")
    ap.add_argument("--stopp", action="store_true", help="den Server (Port aus der Einstellung) beenden; "
                                                         "mit --beobachten den dieses Repos")
    ap.add_argument("--beobachten", action="store_true",
                    help="Arbeitsverzeichnis (auch nicht Committetes) gegen HEAD bzw. --von live beobachten: eigene Instanz "
                         "mit freiem Port, Seite lädt bei Änderungen neu, endet mit dem Tab")
    ap.add_argument("--von", help="nur mit --beobachten: Vergleichsstand (Standard HEAD)")
    ap.add_argument("--server", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--projekte", action="store_true", help=argparse.SUPPRESS)  # für die Shell-Vervollständigung
    o = ap.parse_args()
    if o.server:
        return server()
    if o.von and not o.beobachten:
        ap.error("--von gibt es nur mit --beobachten (sonst: von in der Einstellung)")
    if o.stopp:
        if o.beobachten:
            zur_instanz(["--stopp"], o.ordner, immer=True)
            print("merge-train: keine --beobachten-Instanz für dieses Repo"); return
        sys.exit(server_stoppen())
    if o.beobachten:
        return beobachten_starten(o.ordner, o.von, o.nur_datei)
    if o.projekte:
        if not KONF["lokal"]:
            return
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(8) as ex:
            akte = list(ex.map(statistik, finde_repos()))
        akte.sort(key=lambda w: (not w["dateien"], -(w["plus"] + w["minus"])))
        for w in akte:
            print(f'{w["p"]}\t+{w["plus"]} −{w["minus"]} · {w["dateien"]} Datei(en)' if w["dateien"] else f'{w["p"]}\taktuell')
        return
    if o.ordner and ist_mr_ref(o.ordner) and not os.path.exists(o.ordner):
        if not KONF["gitlab"]:
            sys.exit("merge-train: GitLab ist abgeschaltet (gitlab = false in der Einstellung)")
        try:  # Aufruf von Hand: MR-Daten einmal holen, die Seite selbst fragt GitLab nicht
            mr, _ = mr_meta_holen(mr_vollstaendig(mr_ref(o.ordner, os.getcwd())))
        except Fehler as e:
            sys.exit(f"merge-train: {e}")
        return im_browser("/mr/" + mr.id, o.nur_datei)
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
        if not os.path.isdir(ordner):  # im Projektordner ist „merge-train“ auch die gebaute Datei
            ordner = projekt_ordner(o.ordner)
        wurzel = (git(ordner, "rev-parse", "--show-toplevel", check=False) or "").strip() or None
        if o.ordner and not wurzel:
            sys.exit(f"merge-train: kein Git-Repo: {o.ordner}")
    if wurzel and fehlende_zweige(wurzel):
        von, bis = von_bis(projektname(wurzel))
        sys.exit(f"merge-train: Branch {' und '.join(fehlende_zweige(wurzel))} fehlt in {wurzel} (von = {von}, bis = {bis}; "
                 "im Zug den Waggon aufklappen oder [zweige] in der Einstellung)")
    if wurzel:  # der Server baut die Seite beim Abruf (und danach die übrigen offenen im Hintergrund)
        return im_browser("/" + dateiname(projektname(wurzel)), o.nur_datei)
    offen = [w for w in LOKAL.wagen() if w["status"] == "offen"]
    if not offen:
        print("merge-train: nichts zu prüfen – überall ist bis auf dem Stand von von"); return
    return im_browser(offen[0]["datei"], o.nur_datei)
