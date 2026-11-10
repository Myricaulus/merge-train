#!/usr/bin/env python3
"""Einzeltests für die Logik von merge-train – ohne Server und ohne glab, in unter einer Sekunde. Laufen gegen src/.

Aufruf:  python3 tests/test_einheiten.py      (vor tests/test_gitlab.py)

Für Zeilen-Arithmetik, Diff-Zerlegung und see_also legt der Test ein kleines Git-Repo im Temp-Ordner an.
"""
import os, subprocess, sys, tempfile, unittest

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
from merge_train.review import abschluss_planen, entwuerfe_abgleichen, gitlab_reihenfolge, schritt_eintragen


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
        self.assertEqual([(x["id"], x["art"]) for x in s],
                         [("loeschen", "loeschen"), ("neu", "anlegen"), ("da", "uebernehmen"), ("geaendert", "aendern"),
                          ("entfernen", "entfernen")])
        da = next(x for x in s if x["id"] == "da")
        self.assertEqual((da["gitlab_id"], da["gitlab_art"]), (20, "allgemein"))
        self.assertEqual(next(x for x in s if x["id"] == "neu")["kommentar"]["text"], "ganz neu")

    def test_ein_entwurf_nur_einmal_uebernommen(self):
        akte = {"kommentare": [kommentar(id="a", text="gleich"), kommentar(id="b", text="gleich")]}
        s = abschluss_planen(akte, {5: {"id": 5, "note": "gleich", "position": {"new_line": 5}}}, {})
        self.assertEqual([x["art"] for x in s], ["uebernehmen", "anlegen"])
        self.assertEqual(s[0]["gitlab_art"], "position")

    def test_eintragen(self):
        akte = {"kommentare": [kommentar(id="k", text="getippt, während gesendet wurde")]}
        ok = schritt_eintragen(akte, {"art": "anlegen", "id": "k", "text": "gesendet"}, {"gitlab_id": 7, "gitlab_art": "position"})
        self.assertTrue(ok)
        self.assertEqual(kommentar_status(akte["kommentare"][0]), "geaendert")  # nichts still überschrieben
        self.assertFalse(schritt_eintragen(akte, {"art": "anlegen", "id": "weg", "text": "x"}, {"gitlab_id": 8, "gitlab_art": "mr"}))

    def test_eintragen_loeschen(self):
        akte = {"kommentare": [kommentar(id="weg", gitlab_id=1, geloescht=True),
                             kommentar(id="zurueck", gitlab_id=2, gitlab_text="Text")]}  # währenddessen wiederhergestellt
        schritt_eintragen(akte, {"art": "loeschen", "id": "weg", "text": "Text"}, {})
        schritt_eintragen(akte, {"art": "loeschen", "id": "zurueck", "text": "Text"}, {})
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
