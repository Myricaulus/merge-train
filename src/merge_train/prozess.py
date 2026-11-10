"""Der Server als Prozess: im Hintergrund starten, bewachen (Leerlauf, --stopp, Tab zu, neuer Stand), beenden."""
import json, os, subprocess, sys, threading, time
import urllib.parse
from .einstellungen import KONF, KONFIG_DATEI, ORDNER, SKRIPT, oeffnen, schluessel
from .server import ABSCHIED_S, Handler, PORT, _ABSCHIED, _LAUFEND, _LETZTE_ANFRAGE, _STOPP
from http.server import ThreadingHTTPServer
from . import syntax

LEERLAUF_S = int(KONF["leerlauf"])


def server_laeuft(port=None):
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port or PORT}/ping", timeout=0.5) as r:
            return r.read() == b"merge-train"
    except OSError:
        return False


def server_sicherstellen():
    if server_laeuft():
        return True
    log = open(os.path.join(ORDNER, "server.log"), "a")
    subprocess.Popen([sys.executable, SKRIPT, "--server"], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=log, stderr=log)
    for _ in range(40):
        time.sleep(0.1)
        if server_laeuft():
            return True
    return False


def dateizeiten(pfade):
    out = []
    for p in pfade:
        try: out.append(os.path.getmtime(p))
        except OSError: out.append(None)
    return out


def server_bewachen(srv, beobachtet):
    """Bis LEERLAUF_S ohne Anfrage, „merge-train --stopp“, Tab zu (--beobachten) oder bis Skript/Einstellung sich ändern;
    dann laufende Aktionen (z. B. „Review abschließen“) fertig werden lassen und den Server anhalten.
    Rückgabe: True = mit neuem Stand neu starten."""
    anfang, neu = dateizeiten(beobachtet), False
    while time.time() - _LETZTE_ANFRAGE[0] < LEERLAUF_S:
        if _STOPP.wait(2):
            break
        abschied = _ABSCHIED[0]
        if abschied is not None and _LETZTE_ANFRAGE[0] <= abschied and time.time() - abschied > ABSCHIED_S:
            break
        jetzt = dateizeiten(beobachtet)
        if jetzt[0] is None:  # Skript umbenannt/gelöscht: beenden
            break
        if jetzt != anfang:
            neu = True; break
    bis = time.time() + 600
    while _LAUFEND[0] > 0 and time.time() < bis:
        time.sleep(0.2)
    srv.shutdown()
    return neu


def server():
    """Liefert ~/.cache/merge-train auf 127.0.0.1 aus, erzeugt Seiten beim Abruf frisch, nimmt „fertig“
    und die Review-Aktionen an. Beendet sich nach LEERLAUF_S ohne Anfrage oder auf „merge-train --stopp“, startet neu bei
    neuem Skript/neuer Einstellung."""
    schluessel()
    _LETZTE_ANFRAGE[0] = time.time()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    syntax.SERVER_SOCKET = srv.socket
    beobachtet = [SKRIPT, KONFIG_DATEI]
    neu = []
    threading.Thread(target=lambda: neu.append(server_bewachen(srv, beobachtet)), daemon=True).start()
    srv.serve_forever()
    srv.server_close()
    if neu and neu[0]:
        os.execv(sys.executable, [sys.executable, beobachtet[0], "--server"])


def server_stoppen():
    """merge-train --stopp: den Server auf PORT beenden (laufende Aktionen werden noch fertig). Rückgabe: Exit-Code."""
    import urllib.request
    if not server_laeuft():
        print(f"merge-train: kein Server auf Port {PORT}"); return 0
    anfrage = urllib.request.Request(f"http://127.0.0.1:{PORT}/stopp", method="POST",
                                     data=json.dumps({"k": schluessel()}).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(anfrage, timeout=5).read()
    except OSError as e:
        print(f"merge-train: Server auf Port {PORT} lehnt ab: {e}", file=sys.stderr); return 1
    for _ in range(100):
        if not server_laeuft():
            print(f"merge-train: Server auf Port {PORT} beendet"); return 0
        time.sleep(0.1)
    print(f"merge-train: Server auf Port {PORT} beendet sich, sobald laufende Aktionen fertig sind"); return 0


def im_browser(pfad, nur_url=False):
    if not server_sicherstellen():
        sys.exit(f"merge-train: Server startet nicht – siehe {os.path.join(ORDNER, 'server.log')}")
    url = f"http://127.0.0.1:{PORT}{pfad}"
    print(url)
    if not nur_url:
        oeffnen(url)
