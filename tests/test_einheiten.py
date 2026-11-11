#!/usr/bin/env python3
"""Einzeltests für die Logik von merge-train – ohne Server und ohne glab, in unter einer Sekunde. Laufen gegen src/.

Aufruf:  python3 tests/test_einheiten.py      (vor tests/test_gitlab.py)

Für Zeilen-Arithmetik, Diff-Zerlegung und see_also legt der Test ein kleines Git-Repo im Temp-Ordner an. Akten liegen
im Temp-Ordner (XDG_DATA_HOME), GitLab ersetzt ein Fake für review.glab.
"""
import contextlib, glob, io, os, subprocess, sys, tempfile, threading, unittest

T = tempfile.mkdtemp(prefix="merge-train-einheiten-")
open(f"{T}/leer.toml", "w").close()
os.environ.update(MERGE_TRAIN_CONFIG=f"{T}/leer.toml", XDG_CACHE_HOME=f"{T}/cache", XDG_DATA_HOME=f"{T}/data",
                  XDG_CONFIG_HOME=f"{T}/config")  # nie die Einstellung oder Daten des Nutzers lesen
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from merge_train.waggon import Fehler, Waggon
from merge_train.git import zerlegen
from merge_train.zeilen import alt_zeile, im_diff, kontext_zeile, paare_und_hunks, zeile_vorwaerts, zurueck_diffs
from merge_train.akte import ausstehend, ist_sent, ist_staged, kommentar_status
from merge_train.hinweise import needle_zeilen, see_also_aufloesen
from merge_train.review import Schritt, abschluss_planen, entwuerfe_abgleichen, gitlab_reihenfolge, schritt_eintragen
from merge_train.einstellungen import DATEN, schluessel
from merge_train.akte import akte_bearbeiten, akte_datei, akte_lesen, aktion_ausfuehren, faeden_von, kommentar_anhaengen
from merge_train.gespraech import gespraech_aktion
from merge_train.server import Anfrage, bearbeiten
from merge_train import review


def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, check=True).stdout


REPO = f"{T}/repo"
ALT = [f"z{i}" for i in range(1, 21)]
# Stand B gegenüber A: Zeile 3 geändert, nach Zeile 10 eine eingefügt, Zeile 15 gelöscht (20 Zeilen bleiben 20)
NEU = ALT[:2] + ["z3 neu"] + ALT[3:10] + ["eingefügt"] + ALT[10:14] + ALT[15:]


def repo_anlegen():
    os.makedirs(REPO)
    git("init", "-q", "-b", "main"); git("config", "user.email", "t@t"); git("config", "user.name", "t")
    schreib = lambda p, t: open(f"{REPO}/{p}", "w", encoding="utf-8").write(t)
    schreib("a.txt", "\n".join(ALT) + "\n"); schreib("bleibt.txt", "x\n"); schreib("weg.txt", "w1\nw2\n")
    schreib("alt name.txt", "\n".join(f"u{i}" for i in range(30)) + "\n")
    git("add", "-A"); git("commit", "-qm", "A")
    a = git("rev-parse", "HEAD").strip()
    schreib("a.txt", "\n".join(NEU) + "\n")
    os.remove(f"{REPO}/weg.txt")
    schreib("Ümlaut mit leer.txt", "neu\n")
    open(f"{REPO}/bild.bin", "wb").write(bytes(range(256)))
    git("mv", "alt name.txt", "neuer name.txt")
    git("add", "-A"); git("commit", "-qm", "B")
    b = git("rev-parse", "HEAD").strip()
    git("rm", "-q", "a.txt"); git("commit", "-qm", "C")
    return a, b, git("rev-parse", "HEAD").strip()


A, B, C = repo_anlegen()
DIFF = zerlegen(git("-c", "core.quotepath=false", "diff", "--no-color", "--no-ext-diff", "-M", "-U3", A, B))


def datei(name):
    d = next(d for d in DIFF if d["neu"] == name)
    paare, hunks = paare_und_hunks(d)
    return dict(d, paare=paare, hunks=hunks, bn=len(NEU))


class Zerlegen(unittest.TestCase):
    def test_status_und_namen(self):
        akte = {d["neu"]: d["status"] for d in DIFF}
        self.assertEqual(akte["a.txt"], "geändert")
        self.assertEqual(akte["weg.txt"], "gelöscht")
        self.assertEqual(akte["Ümlaut mit leer.txt"], "neu")
        self.assertEqual(akte["neuer name.txt"], "umbenannt")
        self.assertEqual(next(d for d in DIFF if d["neu"] == "neuer name.txt")["alt"], "alt name.txt")

    def test_binaer(self):
        d = next(d for d in DIFF if d["neu"] == "bild.bin")
        self.assertTrue(d["binaer"])
        self.assertEqual(d["hunks"], [])

    def test_zaehler(self):
        d = next(d for d in DIFF if d["neu"] == "a.txt")
        self.assertEqual((d["plus"], d["minus"]), (2, 2))


class Zeilen(unittest.TestCase):
    f = datei("a.txt")

    def test_alt_zeile(self):
        self.assertIsNone(alt_zeile(self.f, 3))    # geändert: neue Fassung hat keine alte Zeile
        self.assertIsNone(alt_zeile(self.f, 11))   # eingefügt
        self.assertEqual(alt_zeile(self.f, 12), 11)  # nach der Einfügung: eins verschoben
        self.assertEqual(alt_zeile(self.f, 7), 7)    # zwischen den Hunks (Kontext)
        self.assertEqual(alt_zeile(self.f, 20), 20)  # hinter allem: +1 −1 gleicht sich aus
        self.assertEqual(alt_zeile(self.f, 15), 14)  # z14: Einfügung davor
        self.assertEqual(alt_zeile(self.f, 16), 16)  # z16: Einfügung und Löschung davor gleichen sich aus

    def test_im_diff(self):
        self.assertTrue(im_diff(self.f, None, 11))   # eingefügt
        self.assertTrue(im_diff(self.f, 3, None))    # alte Fassung der geänderten Zeile
        self.assertTrue(im_diff(self.f, 15, None))   # gelöscht
        self.assertTrue(im_diff(self.f, 11, 12))     # Kontext im Hunk
        self.assertFalse(im_diff(self.f, None, 7))
        self.assertFalse(im_diff(self.f, 11, 13))    # falsches Paar

    def test_kontext_zeile(self):
        self.assertTrue(kontext_zeile(self.f, 7, 7))
        self.assertFalse(kontext_zeile(self.f, 6, 7))
        self.assertFalse(kontext_zeile(self.f, 11, 12))  # steht im Hunk, ist kein nachgeladener Kontext
        self.assertFalse(kontext_zeile(self.f, 21, 21))  # hinter dem Dateiende

    def test_zeile_vorwaerts(self):
        v = lambda b, bis=B: zeile_vorwaerts(REPO, A, bis, "a.txt", b)
        self.assertEqual(v(11), 12)     # Faden unter der Einfügung wandert mit
        self.assertEqual(v(10), 10)     # darüber bleibt er
        self.assertIsNone(v(3))         # an der geänderten Zeile: seitdem geändert
        self.assertIsNone(v(15))        # gelöscht
        self.assertEqual(v(14), 15)     # unter der Einfügung, über der Löschung
        self.assertEqual(v(16), 16)     # unter beiden
        self.assertEqual(v(7), 7)
        self.assertIsNone(v(5, C))      # Datei gelöscht
        self.assertEqual(zeile_vorwaerts(REPO, A, A, "a.txt", 3), 3)
        self.assertEqual(zeile_vorwaerts(REPO, A, B, "bleibt.txt", 1), 1)  # Datei unverändert

    def test_zurueck_diffs(self):
        r = zurueck_diffs(REPO, A, B, ["a.txt", "bleibt.txt"])
        self.assertEqual(set(r), {"a.txt"})  # unveränderte fehlen
        self.assertEqual(r["a.txt"]["status"], "geändert")
        self.assertIn([None, 11], r["a.txt"]["paare"])
        self.assertEqual(zurueck_diffs(REPO, A, B, []), {})


def kommentar(**k):
    return dict({"id": "k1", "text": "Text", "path": "a.txt", "b": 5}, **k)


class Stufen(unittest.TestCase):
    def test_kommentar_status(self):
        self.assertEqual(kommentar_status(kommentar()), "neu")
        self.assertEqual(kommentar_status(kommentar(gitlab_id=1, gitlab_text="Text")), "uebertragen")
        self.assertEqual(kommentar_status(kommentar(gitlab_id=1, gitlab_text="alt")), "geaendert")
        self.assertEqual(kommentar_status(kommentar(gitlab_id=1, gitlab_text="Text", gitlab_weg=True)), "weg")
        self.assertEqual(kommentar_status(kommentar(gitlab_id=1, geloescht=True)), "loeschen")
        self.assertEqual(kommentar_status(kommentar(geloescht=True, gitlab_weg=True)), "loeschen")  # löschen geht vor

    def test_staged_sent(self):
        for k, staged in [(kommentar(), True), (kommentar(gitlab_id=1, gitlab_text="alt"), True),
                          (kommentar(gitlab_id=1, geloescht=True), True), (kommentar(gitlab_id=1, gitlab_text="Text"), False),
                          (kommentar(gitlab_id=1, gitlab_text="Text", gitlab_weg=True), False)]:
            self.assertEqual(ist_staged(k), staged, k)
            self.assertEqual(ist_sent(k), not staged, k)

    def test_ausstehend_ohne_faeden(self):
        akte = {"kommentare": [kommentar(), kommentar(id="k2", gitlab_id=1, gitlab_text="Text"),
                             {"id": "f1", "nachrichten": [], "text": "x"}]}
        self.assertEqual(ausstehend(akte), 1)


class WaggonTest(unittest.TestCase):
    def test_kennung_hin_und_zurueck(self):
        for kennung in ("projekt:merge-train", "projekt:gruppe/sub", "gitlab.example.com/gruppe/demo/1",
                        "gitlab.example.com:8443/a/b/c/42"):
            self.assertEqual(Waggon.aus_id(kennung).id, kennung)
        w = Waggon.aus_id("h/gruppe/sub/projekt/7")
        self.assertEqual((w.host, w.projekt, w.iid), ("h", "gruppe/sub/projekt", 7))

    def test_ungueltig(self):
        for kennung in ("projekt:", "projekt:a/../b", "projekt:a//b", "h/p", "h/g/p/x", "h/../p/1", "h//p/1",
                        "h/g/p/", "ho st/g/p/1"):
            with self.assertRaises(Fehler, msg=kennung):
                Waggon.aus_id(kennung)

    def test_dict(self):
        for w in (Waggon(lokal="proj"), Waggon(host="h", projekt="g/p", iid=3)):
            self.assertEqual(Waggon.aus_dict(w.als_dict()), w)

    def test_dateiname(self):
        for w in (Waggon(host="gitlab.example.com:8443", projekt="g/p q", iid=3), Waggon(projekt="g/p", iid=1),
                  Waggon(lokal="a/b")):
            self.assertRegex(w.dateiname, r"^[\w.-]+$")
        self.assertNotEqual(Waggon(host="h", projekt="g/p", iid=1).dateiname, Waggon(host="h", projekt="g/p", iid=2).dateiname)

    def test_kann(self):
        self.assertTrue(Waggon(host="h", projekt="g/p", iid=1).kann["review"])
        self.assertFalse(Waggon(lokal="p").kann["review"])


class Abschliessen(unittest.TestCase):
    def test_planen(self):
        akte = {"kommentare": [
            kommentar(id="neu", text="ganz neu"),
            kommentar(id="da", text="schon in GitLab"),              # Entwurf dort, nur nicht gemerkt
            kommentar(id="geaendert", text="neu", gitlab_id=11, gitlab_text="alt"),
            kommentar(id="gleich", text="x", gitlab_id=12, gitlab_text="x"),
            kommentar(id="loeschen", gitlab_id=13, geloescht=True),
            kommentar(id="entfernen", gitlab_id=99, geloescht=True),  # in GitLab schon weg
            kommentar(id="veroeffentlicht", gitlab_id=98, gitlab_text="Text", gitlab_weg=True),
            {"id": "faden", "text": "privat", "nachrichten": []}]}
        vorhanden = {11: {"id": 11}, 12: {"id": 12}, 13: {"id": 13},
                     20: {"id": 20, "note": "**[`a.txt:5`](link)**\n\nschon in GitLab"}}
        s = abschluss_planen(akte, vorhanden, {"loeschen": 0, "neu": 1})
        self.assertEqual([(x.id, x.art) for x in s],
                         [("loeschen", "loeschen"), ("neu", "anlegen"), ("da", "uebernehmen"), ("geaendert", "aendern"),
                          ("entfernen", "entfernen")])
        da = next(x for x in s if x.id == "da")
        self.assertEqual((da.gitlab_id, da.gitlab_art), (20, "allgemein"))
        self.assertEqual(next(x for x in s if x.id == "neu").kommentar["text"], "ganz neu")

    def test_ein_entwurf_nur_einmal_uebernommen(self):
        akte = {"kommentare": [kommentar(id="a", text="gleich"), kommentar(id="b", text="gleich")]}
        s = abschluss_planen(akte, {5: {"id": 5, "note": "gleich", "position": {"new_line": 5}}}, {})
        self.assertEqual([x.art for x in s], ["uebernehmen", "anlegen"])
        self.assertEqual(s[0].gitlab_art, "position")

    def test_eintragen(self):
        akte = {"kommentare": [kommentar(id="k", text="getippt, während gesendet wurde")]}
        ok = schritt_eintragen(akte, Schritt("anlegen", "k", "a.txt:5", "gesendet"), 7, "position")
        self.assertTrue(ok)
        self.assertEqual(kommentar_status(akte["kommentare"][0]), "geaendert")  # nichts still überschrieben
        self.assertFalse(schritt_eintragen(akte, Schritt("anlegen", "weg", "allgemein", "x"), 8, "mr"))

    def test_eintragen_loeschen(self):
        akte = {"kommentare": [kommentar(id="weg", gitlab_id=1, geloescht=True),
                             kommentar(id="zurueck", gitlab_id=2, gitlab_text="Text")]}  # währenddessen wiederhergestellt
        schritt_eintragen(akte, Schritt("loeschen", "weg", "a.txt:5", "Text", 1), None, None)
        schritt_eintragen(akte, Schritt("loeschen", "zurueck", "a.txt:5", "Text", 2), None, None)
        self.assertEqual([k["id"] for k in akte["kommentare"]], ["zurueck"])
        self.assertEqual(kommentar_status(akte["kommentare"][0]), "neu")

    def test_abgleich(self):
        akte = {"kommentare": [kommentar(id="pub", text="veröffentlicht", gitlab_id=1, gitlab_text="veröffentlicht"),
                             kommentar(id="verw", text="verworfen", gitlab_id=2, gitlab_text="verworfen"),
                             kommentar(id="da", gitlab_id=3, gitlab_text="Text")]}
        self.assertEqual(entwuerfe_abgleichen(akte, {3: {}}, None), (0, 0))  # nichts geholt: nichts ändern
        self.assertEqual(kommentar_status(akte["kommentare"][1]), "uebertragen")
        self.assertEqual(entwuerfe_abgleichen(akte, {3: {}}, ["**[`a.txt:5`](l)**\n\nveröffentlicht"]), (1, 1))
        self.assertEqual([kommentar_status(k) for k in akte["kommentare"]], ["weg", "neu", "uebertragen"])

    def test_reihenfolge(self):
        kom = [{"id": "k1", "datei": 0, "b": 5, "status": "neu"}, {"id": "k2", "datei": 1, "b": 1, "status": "neu"},
               {"id": "k3", "datei": 0, "b": 1, "status": "loeschen"}]
        hinweise = [{"key": "h1", "datei": 0, "b": 9, "status": "offen"}, {"key": "h2", "datei": None, "status": "offen"},
                    {"key": "h3", "datei": 0, "b": 2, "status": "verworfen"}]
        self.assertEqual(gitlab_reihenfolge({}, kom, hinweise), ["h2", "k1", "h1", "k2"])  # allgemein zuerst, dann Datei/Zeile
        # vom Nutzer sortiert bleibt, Unbekanntes fällt weg; Neues vor dem ersten, der natürlich später kommt
        self.assertEqual(gitlab_reihenfolge({"reihenfolge": ["k2", "weg", "k1"]}, kom, hinweise), ["h2", "h1", "k2", "k1"])


class Hinweise(unittest.TestCase):
    TEXT = "void Foo() {\n  Foo();  // TODO REVIEW X-1\n  Bar(Foo);\n}"

    def test_needle(self):
        self.assertEqual(needle_zeilen(self.TEXT, "Foo(", ""), [1, 2])
        self.assertEqual(needle_zeilen(self.TEXT, "=Foo();", "TODO REVIEW X-1"), [2])  # Tag-Kommentar abgeschnitten
        self.assertEqual(needle_zeilen(self.TEXT, "=Foo();", ""), [])
        self.assertEqual(needle_zeilen(self.TEXT, "=  }  ", ""), [4])  # = vergleicht ohne Leerraum am Rand
        self.assertEqual(needle_zeilen(self.TEXT, "GibtEsNicht", ""), [])

    def test_see_also(self):
        r = see_also_aufloesen(REPO, B, ["a.txt:5", "a.txt:5-7", "./a.txt", {"path": "a.txt", "needle": "eingefügt", "label": "L"},
                                         {"path": "a.txt", "diff": True}, "fehlt.txt", "a.txt:99",
                                         {"path": "a.txt", "needle": "GibtEsNicht"}, {"path": "a.txt", "diff": "fehlt.txt"}],
                               "", eigene="bleibt.txt")
        kurz = [(x["path"], x["zeile"], x["bis"], x["problem"]) for x in r]
        self.assertEqual(kurz[:4], [("a.txt", 5, None, None), ("a.txt", 5, 7, None), ("a.txt", None, None, None),
                                    ("a.txt", 11, None, None)])
        self.assertEqual(r[3]["label"], "L")
        self.assertEqual(r[4]["vergleich"], "bleibt.txt")
        self.assertEqual([x["problem"] for x in r[5:]], ["Datei nicht im MR-Stand", "Zeile 99 gibt es nicht (20 Zeilen)",
                                                         "needle nicht gefunden", "diff: fehlt.txt nicht im MR-Stand"])
        self.assertEqual(see_also_aufloesen(REPO, B, {"path": "a.txt", "diff": True}, "")[0]["problem"],
                         "diff: Hinweis hat keine eigene Datei – Pfad angeben")


# ---- Akte: Speichern, Ablehnen, kaputte Datei, Sperre

def frische_akte(name):
    w = Waggon(lokal=name)
    for p in [akte_datei(w)] + glob.glob(akte_datei(w) + ".kaputt-*"):
        os.remove(p) if os.path.exists(p) else None
    return w


class AkteTest(unittest.TestCase):
    def test_speichert_nur_bei_aenderung(self):
        w = frische_akte("speichern")
        with akte_bearbeiten(w):
            pass
        self.assertFalse(os.path.exists(akte_datei(w)))  # nichts geändert: keine Datei
        with akte_bearbeiten(w) as akte:
            akte["x"] = 1
        self.assertEqual(akte_lesen(w)["x"], 1)
        with akte_bearbeiten(w, speichern=False) as akte:
            akte["x"] = 2
        self.assertEqual(akte_lesen(w)["x"], 1)
        with self.assertRaises(KeyError):
            with akte_bearbeiten(w) as akte:
                akte["x"] = 3
                raise KeyError
        self.assertEqual(akte_lesen(w)["x"], 1)  # Ausnahme: nicht gespeichert

    def test_abgelehnte_aktion_speichert_nichts(self):
        w = frische_akte("ablehnen")
        def halb(akte):
            akte["x"] = "halb geändert"
            return False, "abgelehnt"
        self.assertEqual(aktion_ausfuehren(w, halb), (False, "abgelehnt"))
        self.assertNotIn("x", akte_lesen(w))
        def ganz(akte):
            akte["x"] = "ganz"
            return True, "gut"
        self.assertEqual(aktion_ausfuehren(w, ganz), (True, "gut"))
        self.assertEqual(akte_lesen(w)["x"], "ganz")

    def test_kaputte_datei_wird_beiseitegelegt(self):
        w = frische_akte("kaputt")
        os.makedirs(os.path.dirname(akte_datei(w)), exist_ok=True)
        with open(akte_datei(w), "w") as f:
            f.write("{kaputt")
        self.assertEqual(akte_lesen(w)["kommentare"], [])  # nur lesen: liegen lassen
        with open(akte_datei(w)) as f:
            self.assertEqual(f.read(), "{kaputt")
        with contextlib.redirect_stderr(io.StringIO()) as meldung, akte_bearbeiten(w) as akte:
            akte["x"] = 1
        self.assertIn("ist kaputt", meldung.getvalue())
        beiseite = glob.glob(akte_datei(w) + ".kaputt-*")
        self.assertEqual(len(beiseite), 1)
        with open(beiseite[0]) as f:
            self.assertEqual(f.read(), "{kaputt")
        self.assertEqual(akte_lesen(w)["x"], 1)

    def test_sperre_gilt_auch_fuer_andere_prozesse(self):
        w = frische_akte("sperre")
        versuch = "import fcntl, sys; fcntl.flock(open(sys.argv[1], 'a'), fcntl.LOCK_EX | fcntl.LOCK_NB)"
        anderer = lambda: subprocess.run([sys.executable, "-c", versuch, os.path.join(DATEN, ".sperre")],
                                         capture_output=True).returncode
        with akte_bearbeiten(w):
            with akte_bearbeiten(w):  # verschachtelt im selben Thread: keine Selbstblockade
                pass
            self.assertNotEqual(anderer(), 0)
        self.assertEqual(anderer(), 0)


# ---- Server: bearbeiten() und Routen (ohne HTTP)

class RoutenTest(unittest.TestCase):
    def frage(self, methode, pfad, **daten):
        return bearbeiten(Anfrage(methode, pfad, "", daten, None))

    def test_ping_und_unbekannt(self):
        self.assertEqual((self.frage("GET", "ping").status, self.frage("GET", "ping").inhalt), (200, "merge-train"))
        self.assertEqual(self.frage("GET", "gibt/es/nicht").status, 404)
        self.assertEqual(self.frage("POST", "api/gibtsnicht").status, 404)

    def test_falscher_schluessel(self):
        for methode, pfad in (("GET", "api/review"), ("POST", "api/kommentar")):
            a = self.frage(methode, pfad, mr="projekt:x", k="falsch")
            self.assertEqual(a.status, 403)
            self.assertTrue(a.typ.startswith("application/json"), pfad)

    def test_fehler_nach_art(self):
        a = self.frage("POST", "api/kommentar", k=schluessel(), mr="kaputt")  # ungültige Kennung
        self.assertEqual((a.status, a.typ.split(";")[0]), (400, "application/json"))
        a = self.frage("POST", "api/gespraech", k=schluessel(), mr="projekt:x", aktion="gibtsnicht")
        self.assertEqual(a.status, 400)
        self.assertIn("unbekannte Aktion", a.inhalt)

    def test_dict_wird_json(self):
        a = self.frage("POST", "tschuess", k=schluessel())
        self.assertEqual((a.status, a.inhalt), (200, '{"ok": true}'))


# ---- Gesprächsfäden: Aktionen von der Seite

class FadenAktionenTest(unittest.TestCase):
    def test_ablauf(self):
        w = frische_akte("faeden")
        aktion = lambda **e: gespraech_aktion(w, e)
        self.assertEqual(aktion(aktion="neu", text="Warum?"), (True, ""))
        faden = lambda: faeden_von(akte_lesen(w))[0] if faeden_von(akte_lesen(w)) else None
        fid, nid = faden()["id"], faden()["nachrichten"][0]["id"]
        self.assertEqual(aktion(aktion="erledigt", id=fid)[0], True)
        self.assertEqual(faden()["erledigt"]["von"], "ich")
        self.assertTrue(aktion(aktion="antworten", id=fid, text="Doch noch was")[0])
        self.assertIsNone(faden()["erledigt"])  # Antwort öffnet wieder
        self.assertEqual(aktion(aktion="aendern", id=fid, nid=nid, text=""), (False, "leere Nachricht"))
        self.assertEqual(faden()["nachrichten"][0]["text"], "Warum?")
        with akte_bearbeiten(w) as akte:  # Antwort des Agenten: gesendet, nicht vom Nutzer
            faeden_von(akte)[0]["nachrichten"].append({"id": "c1", "von": "claude", "text": "Darum", "gesendet": "x"})
        self.assertFalse(aktion(aktion="aendern", id=fid, nid="c1", text="anders")[0])
        self.assertFalse(aktion(aktion="gibtsnicht", id=fid)[0])
        aktion(aktion="loeschen", id=fid)  # ohne Nachricht: ganzer Faden
        self.assertIsNone(faden())


class FadenBranchTest(unittest.TestCase):
    """Fäden gehören zum Branch, auf dem sie entstanden; andere Branches sehen sie nur (lesend)."""
    def test_lokal(self):
        from unittest import mock
        from merge_train.quellen import LOKAL
        w = frische_akte("branches")
        with mock.patch.object(LOKAL, "branch", lambda waggon: "feature/a"):
            self.assertTrue(gespraech_aktion(w, {"aktion": "neu", "text": "auf a"})[0])
        k = faeden_von(akte_lesen(w))[0]
        self.assertEqual(k["branch"], "feature/a")
        self.assertEqual([x["id"] for x in faeden_von(akte_lesen(w), "feature/a")], [k["id"]])
        self.assertEqual(faeden_von(akte_lesen(w), "feature/b"), [])
        with mock.patch.object(LOKAL, "branch", lambda waggon: "feature/b"):
            ok, text = gespraech_aktion(w, {"aktion": "erledigt", "id": k["id"]})
        self.assertFalse(ok)
        self.assertIn("feature/a", text)
        self.assertIsNone(faeden_von(akte_lesen(w))[0]["erledigt"])

    def test_mr_alte_faeden_zum_quell_branch(self):
        w = Waggon(host="h", projekt="g/p", iid=7)
        with akte_bearbeiten(w) as akte:
            akte["mr"]["source_branch"] = "feature/x"
            akte["kommentare"].append({"id": "alt", "nachrichten": []})
            akte["kommentare"].append({"id": "kom", "text": "Review"})
        akte = akte_lesen(w)
        self.assertEqual([k["id"] for k in faeden_von(akte, "feature/x")], ["alt"])
        self.assertNotIn("branch", akte["kommentare"][1])  # Review-Kommentare bleiben ohne


class DiskussionenTest(unittest.TestCase):
    """„MR-Daten“: Antworten und Erledigt-Status veröffentlichter Kommentare aus den GitLab-Diskussionen."""
    @staticmethod
    def note(i, wer, text, system=False, resolved=None, von=None):
        n = {"id": i, "author": {"id": wer, "name": f"N{wer}"}, "body": text, "system": system, "created_at": "2026-11-11T08:00:00Z"}
        if resolved is not None:
            n.update(resolvable=True, resolved=resolved, resolved_by={"name": von} if von else None, resolved_at="2026-11-11T09:00:00Z")
        return n

    def test_abgleich(self):
        n = self.note
        akte = {"mr": {}, "kommentare": [
            {"id": "a", "text": "Erster", "gitlab_text": "Erster", "gitlab_id": 1, "gitlab_weg": True},
            {"id": "b", "text": "Zweiter", "gitlab_text": "Zweiter", "gitlab_id": 2, "gitlab_weg": True},
            {"id": "c", "text": "Entwurf", "gitlab_id": 3}]}  # noch nicht veröffentlicht: bleibt ohne
        disk = [{"id": "d0", "notes": [n(9, 5, "Erster", resolved=False)]},  # gleicher Text, aber nicht von mir
                {"id": "d1", "notes": [n(10, 1, "Erster", resolved=True), n(11, 5, "changed this line", system=True),
                                       n(12, 5, "Done", resolved=True, von="Necmettin")]},
                {"id": "d2", "notes": [n(20, 1, "Zweiter", resolved=False), n(21, 5, "Agreed", resolved=False)]}]
        self.assertEqual(review.diskussionen_abgleichen(akte, disk, 1), (2, 1))
        a, b, c = akte["kommentare"]
        self.assertEqual((a["gitlab_diskussion"]["id"], a["gitlab_diskussion"]["note_id"]), ("d1", 10))
        self.assertEqual(a["gitlab_diskussion"]["erledigt"]["wer"], "Necmettin")
        self.assertEqual([x["text"] for x in a["gitlab_diskussion"]["antworten"]], ["Done"])
        self.assertIsNone(b["gitlab_diskussion"]["erledigt"])
        self.assertNotIn("gitlab_diskussion", c)
        a["text"] = a["gitlab_text"] = "in GitLab umformuliert"  # gemerkte id gilt weiter, auch ohne passenden Text
        self.assertEqual(review.diskussionen_abgleichen(akte, disk, 1), (0, 0))
        self.assertEqual(a["gitlab_diskussion"]["id"], "d1")

    def test_neu_und_stand(self):
        from merge_train.akte import diskussionen_stand
        n = self.note
        akte = {"mr": {}, "kommentare": []}
        disk = [{"id": "x", "notes": [n(30, 5, "Frage vom Reviewer", resolved=False)]},
                {"id": "s", "notes": [n(31, 5, "added 1 commit", system=True)]}]  # Systemnotiz: keine Diskussion
        review.diskussionen_abgleichen(akte, disk, 1)
        self.assertEqual([d["id"] for d in akte["diskussionen"]], ["x"])
        self.assertEqual(diskussionen_stand(akte), {"offen": 1, "erledigt": 0, "neu": 1})
        akte["diskussionen_gesehen"] = 30  # Seite geöffnet
        self.assertEqual(diskussionen_stand(akte)["neu"], 0)
        disk[0]["notes"] = [n(30, 5, "Frage vom Reviewer", resolved=True, von="R"), n(32, 1, "meine Antwort", resolved=True),
                            n(33, 5, "danke", resolved=True)]
        self.assertEqual(review.diskussionen_abgleichen(akte, disk, 1), (1, 1))  # nur Beiträge anderer zählen
        self.assertEqual(diskussionen_stand(akte), {"offen": 0, "erledigt": 1, "neu": 1})


# ---- Review abschließen als Ganzes, gegen ein GitLab-Fake

class GitLabFake:
    """Ersatz für review.glab: zählt Aufrufe, vergibt ids, „kaputt“ im Text → Fehler; bremse hält POSTs an."""
    def __init__(self):
        self.aufrufe, self.naechste, self.bremse, self.beim_anlegen, self.entwuerfe = [], 100, None, None, {}

    def __call__(self, host, pfad, methode="GET", daten=None, roh=False):
        self.aufrufe.append((methode, pfad, (daten or {}).get("note")))
        if self.bremse:
            self.bremse.wait(5)
        if "kaputt" in ((daten or {}).get("note") or ""):
            raise Fehler("glab api POST draft_notes: 500 kaputt")
        if methode == "POST":
            if self.beim_anlegen:
                self.beim_anlegen(daten)
            self.naechste += 1
            self.entwuerfe[self.naechste] = {"id": self.naechste, "note": daten["note"]}
            return {"id": self.naechste}
        if methode == "DELETE":
            self.entwuerfe.pop(int(pfad.rsplit("/", 1)[1]), None)
        return {}


class AbschlussLaufTest(unittest.TestCase):
    def setUp(self):
        self.vorher = review.glab, review.meta_und_entwuerfe
        self.fake = review.glab = GitLabFake()
        review.meta_und_entwuerfe = lambda mr: ({}, dict(self.fake.entwuerfe))
        self.mr = Waggon(host="gitlab.example", projekt="g/" + self._testMethodName.replace("_", "-"), iid=1)
        if os.path.exists(akte_datei(self.mr)):
            os.remove(akte_datei(self.mr))

    def tearDown(self):
        review.glab, review.meta_und_entwuerfe = self.vorher

    def kommentare(self, *texte):
        with akte_bearbeiten(self.mr) as akte:
            for t in texte:
                kommentar_anhaengen(akte, {"id": t, "text": t, "path": None, "a": None, "b": None})

    def test_fehler_mitten_drin(self):
        self.kommentare("erster", "kaputt", "dritter")
        ok, text, _ = review.abschliessen(self.mr)
        self.assertFalse(ok)
        self.assertTrue(text.startswith("Fehler: allgemein: glab api POST draft_notes: 500 kaputt – Rest: Entwürfe in GitLab: 2 neu"), text)
        status = {k["id"]: kommentar_status(k) for k in akte_lesen(self.mr)["kommentare"]}
        self.assertEqual(status, {"erster": "uebertragen", "kaputt": "neu", "dritter": "uebertragen"})
        self.assertNotIn("abgeschlossen", akte_lesen(self.mr))

    def test_waehrenddessen_geloescht_wird_in_gitlab_wieder_entfernt(self):
        self.kommentare("bleibt", "geht")
        def nutzer_loescht(daten):
            if daten["note"] == "geht":
                with akte_bearbeiten(self.mr) as akte:
                    akte["kommentare"] = [k for k in akte["kommentare"] if k["id"] != "geht"]
        self.fake.beim_anlegen = nutzer_loescht
        ok, text, _ = review.abschliessen(self.mr)
        self.assertTrue(ok)
        self.assertIn(("DELETE", "projects/g%2Ftest-waehrenddessen-geloescht-wird-in-gitlab-wieder-entfernt/merge_requests/1/draft_notes/102", None),
                      self.fake.aufrufe)
        self.assertIn("1 neu", text)

    def test_nur_ein_lauf_je_mr(self):
        self.kommentare("langsam")
        self.fake.bremse = threading.Event()
        erster = threading.Thread(target=review.abschliessen, args=(self.mr,))
        erster.start()
        while not self.fake.aufrufe:
            erster.join(0.01)
        self.assertEqual(review.abschliessen(self.mr)[:2], (False, review.LAEUFT_SCHON))
        self.fake.bremse.set()
        erster.join()
        self.assertEqual(len([a for a in self.fake.aufrufe if a[0] == "POST"]), 1)
        self.assertEqual(review.abschliessen(self.mr)[0], True)  # danach wieder frei

    def test_entwurf_rueckfall_auf_allgemein(self):
        k = {"text": "Hier", "path": "a.txt", "old_path": "a.txt", "a": None, "b": 5, "refs": {"head_sha": "abc"}}
        def position_abgelehnt(host, pfad, methode="GET", daten=None, roh=False):
            if "position" in daten:
                raise Fehler("glab api POST draft_notes: 400 line_code ungültig")
            return {"id": 1, "note": daten["note"]}
        review.glab = position_abgelehnt
        antwort, art = review.entwurf_anlegen(self.mr, k, "abc", "https://gitlab.example/g/p")
        self.assertEqual(art, "allgemein")
        self.assertEqual(antwort["note"], "**[`a.txt:5`](https://gitlab.example/g/p/-/blob/abc/a.txt#L5)**\n\nHier")
        def verboten(host, pfad, methode="GET", daten=None, roh=False):
            raise Fehler("glab api POST draft_notes: 403 Forbidden")
        review.glab = verboten
        with self.assertRaises(Fehler):  # Rechte fehlen: nicht still als allgemeinen Kommentar senden
            review.entwurf_anlegen(self.mr, k, "abc", "https://gitlab.example/g/p")


if __name__ == "__main__":
    unittest.main(verbosity=1)
