"""Aufruf von der Kommandozeile."""
import argparse, os, sys
from .einstellungen import ARBEITSSTAND, BIS, KONF, KONFIG_DATEI, VON, dateiname, projektname
from .git import ANLASS, finde_repos, git, projekt_ordner, statistik
from .gitlab import GitLabFehler, ist_mr_ref, mr_id, mr_meta_holen, mr_ref, mr_vollstaendig
from .quellen import LOKAL
from .server import im_browser, server
from .agent_cli import agent_main

def main():
    ANLASS.name = ("cli " + " ".join(sys.argv[1:3]))[:32]
    if len(sys.argv) > 1 and sys.argv[1] == "agent":
        sys.exit(agent_main(sys.argv[2:]))
    ap = argparse.ArgumentParser(prog="merge-train", description=f"merge-train: Merge-Requests {BIS} → {VON} aller Projekte, GitLab-MRs reviewen "
                                             "(„merge-train agent -h“ für Agent-Hinweise)")
    ap.add_argument("ordner", nargs="?", help="nur dieses Projekt (Ordner oder Name unter ~/Projects), oder ein GitLab-MR "
                                              "(URL, '!42', gruppe/projekt!42); ohne: der ganze Zug, beginnend beim größten")
    ap.add_argument("--mrs", action="store_true", help="GitLab-MRs zum Review (Reviewer = ich) zeigen")
    ap.add_argument("--nur-datei", action="store_true", help="nur die URL ausgeben, nicht öffnen")
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
        if not os.path.isdir(ordner):  # im Projektordner ist „merge-train“ auch die gebaute Datei
            ordner = projekt_ordner(o.ordner)
        wurzel = (git(ordner, "rev-parse", "--show-toplevel", check=False) or "").strip() or None
        if o.ordner and not wurzel:
            sys.exit(f"merge-train: kein Git-Repo: {o.ordner}")
    if wurzel and not all(git(wurzel, "rev-parse", "--verify", "-q", b, check=False)
                          for b in (VON, "HEAD" if BIS == ARBEITSSTAND else BIS)):
        sys.exit(f"merge-train: Branch {VON} oder {BIS} fehlt in {wurzel}")
    if wurzel:  # der Server baut die Seite beim Abruf (und danach die übrigen offenen im Hintergrund)
        return im_browser("/" + dateiname(projektname(wurzel)), o.nur_datei)
    offen = [w for w in LOKAL.wagen() if w["status"] == "offen"]
    if not offen:
        print(f"merge-train: nichts zu prüfen – überall {VON} = {BIS}"); return
    return im_browser(offen[0]["datei"], o.nur_datei)
