#!/usr/bin/env python3
"""Einzeltests für die Logik von merge-train – ohne Server und ohne glab, in unter einer Sekunde. Laufen gegen src/.

Aufruf:  python3 tests/test_einheiten.py [Klasse …]     (vor tests/test_gitlab.py; welche Klassen wann: ./testen)

Für Zeilen-Arithmetik, Diff-Zerlegung und see_also legt der Test ein kleines Git-Repo im Temp-Ordner an. Akten liegen
im Temp-Ordner (XDG_DATA_HOME), GitLab ersetzt ein Fake für review.glab.
"""
from pathlib import Path
import contextlib, glob, io, os, subprocess, sys, tempfile, threading, unittest, urllib.parse

T = tempfile.mkdtemp(prefix="merge-train-einheiten-")
open(f"{T}/leer.toml", "w").close()
os.environ.update(MERGE_TRAIN_CONFIG=f"{T}/leer.toml", XDG_CACHE_HOME=f"{T}/cache", XDG_DATA_HOME=f"{T}/data",
                  XDG_CONFIG_HOME=f"{T}/config")  # nie die Einstellung oder Daten des Nutzers lesen
os.makedirs(f"{T}/bin")
for _p in ("notify-send", "todo"):  # keine Desktop-Meldungen, keine todo-Einträge des Nutzers
    open(f"{T}/bin/{_p}", "w").write("#!/bin/sh\nexit 1\n" if _p == "todo" else "#!/bin/sh\n"); os.chmod(f"{T}/bin/{_p}", 0o755)
os.environ.update(PATH=f"{T}/bin:" + os.environ["PATH"], TODO_DIR=f"{T}/todo")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from merge_train.waggon import Fehler, Waggon
from merge_train.git import branch_aktualisieren, branch_pushen, origin_voraus, stand_zu_gitlab, zerlegen
from merge_train.zeilen import (alt_zeile, bereich_anfang_vorwaerts, bereich_vorwaerts, im_diff, kontext_zeile, paare_und_hunks, zeile_vorwaerts,
                                zurueck_diffs)
from merge_train.akte import ausstehend, ist_sent, ist_staged, kommentar_status
from merge_train.hinweise import needle_zeilen, see_also_aufloesen
from merge_train.review import (Schritt, abschluss_planen, entwuerfe_abgleichen, gitlab_reihenfolge, schritt_eintragen,
                                vergleich_daten)
from merge_train.einstellungen import DATEN, schluessel
from merge_train.zuhoerer import transcript_stand
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

    def test_transcript_stand(self):
        import json
        pfad = os.path.join(T, "sitzung.jsonl")
        def dazu(*zeilen):
            with open(pfad, "a") as f:
                f.writelines(json.dumps(z) + "\n" for z in zeilen)
        u = lambda n: {"input_tokens": 1, "cache_creation_input_tokens": 0, "cache_read_input_tokens": n - 1}
        dazu({"type": "user", "message": {"content": "mach mal"}},
             {"type": "assistant", "message": {"stop_reason": "tool_use", "usage": u(250_000)}})
        st = transcript_stand(pfad)
        self.assertEqual((st.tokens, st.groesster, st.arbeitet), (250_000, 250_000, True))
        dazu({"type": "system", "subtype": "compact_boundary", "compactMetadata": {"preTokens": 300_000, "postTokens": 12_000}},
             {"type": "assistant", "message": {"stop_reason": "end_turn", "usage": u(40_000)}},
             {"type": "ai-title"})  # Metadaten danach ändern nichts
        st = transcript_stand(pfad)
        self.assertEqual((st.tokens, st.groesster, st.arbeitet), (40_000, 300_000, False))
        dazu({"type": "user", "message": {"content": [{"type": "text", "text": "noch was"}]}})
        self.assertTrue(transcript_stand(pfad).arbeitet)
        dazu({"type": "user", "message": {"content": [{"type": "text", "text": "[Request interrupted by user]"}]}},
             {"type": "assistant", "isSidechain": True, "message": {"stop_reason": "tool_use"}})  # Subagent zählt nicht
        self.assertFalse(transcript_stand(pfad).arbeitet)
        with open(pfad, "a") as f:
            f.write('{"type": "user", "message": {"content": "halbe Zei')  # noch nicht fertig geschrieben
        self.assertFalse(transcript_stand(pfad).arbeitet)

    def test_bereich_vorwaerts(self):
        v = lambda z, e=None: bereich_vorwaerts(REPO, A, B, "a.txt", z, e)
        self.assertEqual(v(5, 7), (5, 7, False))     # über allen Änderungen
        self.assertEqual(v(11, 13), (12, 14, False))  # unter der Einfügung: nur verschoben
        self.assertEqual(v(11), (12, None, False))
        self.assertEqual(v(9, 12), (9, 13, True))    # Einfügung im Bereich
        self.assertEqual(v(14, 16), (15, 16, True))  # Zeile 15 im Bereich gelöscht
        self.assertEqual(v(3), (3, None, True))      # geändert
        self.assertEqual(bereich_vorwaerts(REPO, A, C, "a.txt", 5, 7), (5, 7, True))  # Datei weg

    def test_bereich_wandert_mit(self):
        v = lambda ab, b_neu: bereich_anfang_vorwaerts(REPO, A, B, "a.txt", ab, b_neu)
        self.assertEqual(v(9, 15), 9)   # 9–14 → 9–15: die Einfügung liegt im Bereich
        self.assertEqual(v(11, 15), 12)  # ganz unter der Einfügung
        self.assertIsNone(v(3, 10))     # Anfang geändert: nur noch die letzte Zeile
        self.assertIsNone(v(None, 10))  # kein Bereich
        self.assertIsNone(v(12, 12))    # Anfang nicht mehr vor dem Ende

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

    def test_see_also_seit_review(self):
        """Zeilen beziehen sich auf reviewed_commit: verschoben → umgerechnet, im Bereich geändert → Warnung."""
        r = see_also_aufloesen(REPO, B, ["a.txt:11-13", "a.txt:9-12", {"path": "a.txt", "needle": "z12"},
                                         {"path": "a.txt", "line": 11, "end": 13, "diff": "a.txt:3-4"}], "", seit=A[:8])
        kurz = [(x["zeile"], x["bis"], x["warnung"]) for x in r]
        self.assertEqual(kurz[0], (12, 14, None))
        self.assertEqual(kurz[1], (9, 13, f"Bereich seit dem Review ({A[:8]}) geändert"))
        self.assertEqual(kurz[2], (13, None, None))  # needle: schon im neuen Stand gesucht, nichts umzurechnen
        self.assertEqual((r[3]["vergleich"], r[3]["vzeile"], r[3]["vbis"]), ("a.txt", 3, 4))
        self.assertEqual(r[3]["warnung"], f"diff a.txt: Bereich seit dem Review ({A[:8]}) geändert")
        self.assertEqual(see_also_aufloesen(REPO, B, ["a.txt:11"], "", seit=B)[0]["zeile"], 11)  # gleicher Stand
        self.assertIn("nicht im Klon", see_also_aufloesen(REPO, B, ["a.txt:11"], "", seit="deadbeef")[0]["warnung"])

    def test_see_also_ref(self):
        """"ref": Datei aus einem anderen Stand (Ziel, Basis, Ref); needle nur auf dem Ziel → Vorschlag."""
        r = see_also_aufloesen(REPO, B, [{"path": "weg.txt", "line": 2, "ref": A}, {"path": "weg.txt", "needle": "w2", "ref": "ziel"},
                                         {"path": "a.txt", "needle": "z15"}, {"path": "a.txt", "ref": "basis"},
                                         {"path": "a.txt", "ref": "gibtsnicht"}, {"path": "weg.txt", "ref": "ziel", "diff": True},
                                         {"path": "neuer name.txt", "ref": "ziel"}],
                               "", eigene="a.txt", ziel=A)
        kurz = [(x["zeile"], x.get("ref"), x.get("sha"), x["problem"]) for x in r]
        self.assertEqual(kurz[0], (2, A, A, None))
        self.assertEqual(kurz[1], (2, A, A, None))
        self.assertEqual(kurz[2][3], f'needle nicht gefunden – steht aber auf {A}: "ref": "ziel" angeben')
        self.assertEqual(kurz[3][1:], ("Basis", A, None))
        self.assertEqual(kurz[4], (None, None, None, "Stand gibtsnicht nicht im Klon"))
        self.assertEqual((r[5]["vergleich"], r[5]["sha"], r[5]["problem"]), ("a.txt", A, None))  # MR-Stand ⇄ Ziel
        self.assertEqual(kurz[6][3], f"Datei nicht auf {A}")
        self.assertEqual(see_also_aufloesen(REPO, B, [{"path": "a.txt", "ref": "ziel"}], "")[0]["problem"], "kein Zielbranch bekannt")
        st = {"ordner": REPO, "refs": {"base_sha": A, "head_sha": B}}
        self.assertEqual(review.zeilen_daten(st, "weg.txt", 1, 9, A)["n"], 2)
        self.assertFalse(review.zeilen_daten(st, "weg.txt", 1, 9)["ok"])
        v = vergleich_daten(st, "a.txt", "a.txt", stand_b=A)
        self.assertEqual((v["ok"], v["plus"], v["minus"]), (True, 2, 2))

    def test_see_also_submodul(self):
        """Dateien in Submodulen: aus dem Submodul-Repo im Stand laut Gitlink; fehlt der Stand, sagt das die Meldung."""
        sub, haupt = f"{T}/sm-sub", f"{T}/sm-haupt"
        g = lambda o, *a: subprocess.run(["git", "-C", o, "-c", "user.email=t@t", "-c", "user.name=t", "-c", "protocol.file.allow=always", *a],
                                         capture_output=True, text=True, check=True).stdout
        os.makedirs(f"{sub}/lib"); os.makedirs(haupt)
        g(sub, "init", "-q"); Path(f"{sub}/lib/x.txt").write_text("eins\nzwei\n"); g(sub, "add", "-A"); g(sub, "commit", "-qm", "x")
        g(haupt, "init", "-q"); g(haupt, "submodule", "add", "-q", sub, "ext/sub"); g(haupt, "commit", "-qm", "s")
        h = g(haupt, "rev-parse", "HEAD").strip()
        r = see_also_aufloesen(haupt, h, ["ext/sub/lib/x.txt:2", {"path": "ext/sub/lib/x.txt", "needle": "eins"}, "ext/sub/fehlt.txt"], "")
        self.assertEqual([(x["zeile"], x["problem"]) for x in r[:2]], [(2, None), (1, None)])
        self.assertIn("ext/sub: Datei nicht im Submodul", r[2]["problem"])
        g(f"{haupt}/ext/sub", "commit", "-q", "--allow-empty", "-m", "y"); g(haupt, "commit", "-qam", "s2")
        neu = g(f"{haupt}/ext/sub", "rev-parse", "HEAD").strip()
        g(f"{haupt}/ext/sub", "reset", "-q", "--hard", "HEAD~1"); g(f"{haupt}/ext/sub", "reflog", "expire", "--expire=now", "--all")
        g(f"{haupt}/ext/sub", "gc", "-q", "--prune=now")
        r = see_also_aufloesen(haupt, g(haupt, "rev-parse", "HEAD").strip(), ["ext/sub/lib/x.txt"], "")
        self.assertEqual(r[0]["problem"], f"Stand {neu[:8]} des Submoduls ext/sub nicht im Klon (git -C ext/sub fetch)")

    def test_siehe_eintrag_ref(self):
        from merge_train.agent_cli import siehe_eintrag
        self.assertEqual(siehe_eintrag("a.txt:3-5@ziel|L"), {"path": "a.txt", "line": 3, "end": 5, "ref": "ziel", "label": "L"})
        self.assertEqual(siehe_eintrag("a.txt@origin/main"), {"path": "a.txt", "ref": "origin/main"})
        self.assertEqual(siehe_eintrag("node_modules/@types/x.d.ts:2"), {"path": "node_modules/@types/x.d.ts", "line": 2})

    def test_vergleich_bereiche(self):
        st = {"ordner": REPO, "refs": {"base_sha": A, "head_sha": B}}
        r = vergleich_daten(st, "a.txt", "a.txt", (2, 4), (12, 14))
        self.assertTrue(r["ok"])
        self.assertEqual((r["a"], r["b"], r["plus"], r["minus"]), ([2, 4], [12, 14], 3, 3))
        self.assertIn('<td class="n">2</td>', r["html"])   # Nummern der Datei, nicht des Ausschnitts
        self.assertIn('<td class="n">14</td>', r["html"])
        self.assertIn("Bereiche sind gleich", vergleich_daten(st, "a.txt", "a.txt", (5, 7), (5, 7))["html"])
        ganz = vergleich_daten(st, "a.txt", "bleibt.txt")
        self.assertEqual((ganz["a"], ganz["b"], ganz["plus"], ganz["minus"]), (None, None, 1, 20))


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

    def test_stand_und_neue_antworten(self):
        from merge_train.akte import diskussionen_stand
        n = self.note
        akte = {"mr": {}, "kommentare": []}
        disk = [{"id": "x", "notes": [n(30, 5, "Frage vom Reviewer", resolved=False)]},
                {"id": "s", "notes": [n(31, 5, "added 1 commit", system=True)]}]  # Systemnotiz: keine Diskussion
        review.diskussionen_abgleichen(akte, disk, 1)
        self.assertEqual([d["id"] for d in akte["diskussionen"]], ["x"])
        self.assertEqual(diskussionen_stand(akte), self.zahl(dran=1))
        disk[0]["notes"] = [n(30, 5, "Frage vom Reviewer", resolved=True, von="R"), n(32, 1, "meine Antwort", resolved=True),
                            n(33, 5, "danke", resolved=True)]
        self.assertEqual(review.diskussionen_abgleichen(akte, disk, 1), (1, 1))  # nur Beiträge anderer zählen
        self.assertEqual(diskussionen_stand(akte), self.zahl(erledigt=1))

    @staticmethod
    def zahl(**k):
        return dict(dict.fromkeys(("entwurf", "dran", "gitlab_entwurf", "wartet", "erledigt"), 0), **k)

    def test_staende(self):
        """(stand, wer) je Eintragsart – das Konzept „Stände der Listen“ (docs/funktionen.md)."""
        from merge_train.akte import diskussion_stand, faden_stand, hinweis_stand, kommentar_stand
        n = self.note
        akte = {"mr": {}, "kommentare": []}
        disk = [{"id": "x", "notes": [n(60, 5, "Frage", resolved=False)]},
                {"id": "m", "notes": [n(61, 1, "meine Frage", resolved=False)]},
                {"id": "z", "notes": [n(62, 5, "zu", resolved=True, von="R")]},
                {"id": "i", "notes": [n(63, 5, "von mir zu", resolved=True, von="ich")]}]
        review.diskussionen_abgleichen(akte, disk, 1)
        akte["diskussionen"][3]["erledigt"]["wer_id"] = 1
        st = {d["id"]: diskussion_stand(akte, d) for d in akte["diskussionen"]}
        self.assertEqual(st, {"x": ("dran", "extern"), "m": ("wartet", "du"), "z": ("erledigt", "extern"),
                              "i": ("erledigt", "du")})
        akte["kommentare"].append({"id": "a", "text": "Antwort", "antwort_auf": "x"})
        self.assertEqual(diskussion_stand(akte, akte["diskussionen"][0]), ("entwurf", "du"))
        akte["kommentare"][0].update(gitlab_id=7, gitlab_text="Antwort")
        self.assertEqual(diskussion_stand(akte, akte["diskussionen"][0]), ("gitlab_entwurf", "du"))
        self.assertEqual([kommentar_stand(k) for k in ({"text": "t"}, {"text": "t", "gitlab_id": 1, "gitlab_text": "t"},
                                                       {"text": "t2", "gitlab_id": 1, "gitlab_text": "t"},
                                                       {"text": "t", "gitlab_id": 1, "gitlab_weg": True})],
                         [("entwurf", "du"), ("gitlab_entwurf", "du"), ("entwurf", "du"), ("wartet", "du")])
        self.assertEqual((hinweis_stand({"status": "offen"}), hinweis_stand({"status": "verworfen"})),
                         (("dran", "agent"), ("erledigt", "du")))
        m = lambda von, gesendet=True: {"von": von, "text": "t", "gesendet": "z" if gesendet else None}
        self.assertEqual([faden_stand(k) for k in ({"nachrichten": [m("ich", False)]}, {"nachrichten": [m("ich")]},
                                                   {"nachrichten": [m("ich"), m("claude")]},
                                                   {"nachrichten": [m("ich")], "erledigt": {"von": "claude"}},
                                                   {"nachrichten": [m("ich")], "erledigt": {"von": "ich"}})],
                         [("entwurf", "du"), ("wartet", "du"), ("dran", "agent"), ("erledigt", "agent"), ("erledigt", "du")])

    def test_abwarten(self):
        from merge_train.akte import diskussion_abgehakt, diskussionen_stand
        n = self.note
        akte = {"mr": {}, "kommentare": []}
        disk = [{"id": "x", "notes": [n(40, 5, "Frage", resolved=False)]}]
        review.diskussionen_abgleichen(akte, disk, 1)
        d = akte["diskussionen"][0]
        self.assertEqual(review.diskussion_abhaken(akte, {"aktion": "abhaken", "diskussion": "x"}), (True, ""))
        self.assertTrue(diskussion_abgehakt(akte, d))
        self.assertEqual(diskussionen_stand(akte)["wartet"], 1)  # abwarten: Ball abgegeben, die anderen sind dran
        self.assertFalse(d.get("erledigt"))  # in GitLab bleibt sie offen
        akte["diskussionen_abgehakt"]["x"] = "2026-11-11T08:30:00+00:00"
        disk[0]["notes"].append(dict(n(41, 1, "meine Antwort", resolved=False), created_at="2026-11-11T09:00:00Z"))
        review.diskussionen_abgleichen(akte, disk, 1)
        self.assertTrue(diskussion_abgehakt(akte, akte["diskussionen"][0]))  # eigene Antwort: wartet weiter
        disk[0]["notes"].append(dict(n(42, 5, "doch noch was", resolved=False), created_at="2026-11-11T09:10:00Z"))
        review.diskussionen_abgleichen(akte, disk, 1)
        self.assertIsNone(diskussion_abgehakt(akte, akte["diskussionen"][0]))  # anderer schreibt danach: wieder dran
        self.assertEqual(diskussionen_stand(akte)["dran"], 1)
        review.diskussion_abhaken(akte, {"aktion": "aufhaken", "diskussion": "x"})
        self.assertEqual(akte["diskussionen_abgehakt"], {})

    def test_waggon_fertig(self):
        """Waggon fertig (grüner Rahmen), sobald in keiner Diskussion mehr du dran bist; vorher „● n dran“."""
        from merge_train.quellen import mr_wagen
        n = self.note
        mr = Waggon(host="gitlab.example", projekt="g/fertig", iid=3)
        wagen = lambda: next(w for w in mr_wagen(mr.id) if w["p"] == mr.id)
        with akte_bearbeiten(mr) as akte:
            review.diskussionen_abgleichen(akte, [{"id": "x", "notes": [n(50, 5, "Frage", resolved=False)]},
                                                  {"id": "y", "notes": [n(51, 5, "Noch eine", resolved=False)]}], 1)
        self.assertEqual((wagen()["status"], wagen()["marke"]), ("offen", "● 2 dran"))
        with akte_bearbeiten(mr) as akte:
            review.diskussion_abhaken(akte, {"aktion": "abhaken", "diskussion": "x"})
        self.assertEqual((wagen()["status"], wagen()["marke"]), ("offen", "● 1 dran"))
        self.assertIn("1 wartet auf andere", wagen()["titel"])
        with akte_bearbeiten(mr) as akte:
            review.diskussion_abhaken(akte, {"aktion": "abhaken", "diskussion": "y"})
        self.assertEqual((wagen()["status"], wagen()["marke"]), ("fertig", "✓ erledigt"))


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


def schreiben(pfad, text):
    with open(pfad, "w") as f:
        f.write(text)


def lesen(pfad):
    with open(pfad) as f:
        return f.read()


class AgentArgsTest(unittest.TestCase):
    def test_optionen_hinten(self):
        """Vorfall 2026-11-13: antworten <id> --erledigt "Text" – Optionen auch hinter den Positionsargumenten."""
        from merge_train.agent_cli import agent_args
        _, o = agent_args(["antworten", "abc", "--erledigt", "Text"])
        self.assertEqual((o.befehl, o.id, o.erledigt, o.text), ("antworten", "abc", True, "Text"))


    def test_vorfall(self):
        """agent vorfall: Bericht im Eingang, Name aus dem Titel, nie überschreiben."""
        from unittest import mock
        from merge_train.agent_cli import vorfall_ablegen
        ordner = tempfile.mkdtemp(dir=T)
        with mock.patch.dict(os.environ, {"MERGE_TRAIN_VORFAELLE": ordner}):
            a = vorfall_ablegen("Prüfen: falsches Projekt!", "Text", "Claude", "~/x")
            b = vorfall_ablegen("Prüfen: falsches Projekt!", "Text", "Claude", "~/x")
        self.assertTrue(os.path.basename(a).endswith("-prüfen-falsches-projekt.md"))
        self.assertTrue(b.endswith("-2.md"))
        self.assertIn("Agent: Claude · Repo: ~/x", lesen(a))

    def test_vorfall_issue(self):
        """agent vorfall: Issue über gh api nur mit vorfall_github, ohne Repo-Pfad; scheitert gh oder fehlt die Einstellung →
        Datei mit Grund und dem Befehl zum Einreichen."""
        import json
        from unittest import mock
        from merge_train import agent_cli
        from merge_train.einstellungen import KONF
        ordner, bin_ = tempfile.mkdtemp(dir=T), tempfile.mkdtemp(dir=T)
        gh = os.path.join(bin_, "gh")
        with open(gh, "w") as f:
            f.write(f'#!/bin/sh\necho "$@" > {bin_}/args\ncat > {bin_}/ein\n'
                    f'[ -e {bin_}/kaputt ] && {{ echo "HTTP 403: Resource not accessible" >&2; exit 1; }}\n'
                    'echo https://github.com/o/r/issues/7\n')
        os.chmod(gh, 0o755)
        _, o = agent_cli.agent_args(["vorfall", "Titel", "Bericht", "--als", "Claude", "--art", "wunsch"])
        def lauf():
            aus = io.StringIO()
            with contextlib.redirect_stdout(aus):
                agent_cli.befehl_vorfall(o)
            return aus.getvalue()
        with mock.patch.dict(os.environ, {"MERGE_TRAIN_VORFAELLE": ordner}), \
             mock.patch.dict(KONF, {"vorfall_github": "o/r", "gh": gh}):
            self.assertIn("als GitHub-Issue angelegt: https://github.com/o/r/issues/7", lauf())
            self.assertIn("repos/o/r/issues", lesen(os.path.join(bin_, "args")))
            daten = json.loads(lesen(os.path.join(bin_, "ein")))
            self.assertEqual(daten["title"], "Titel")
            self.assertIn("Agent: Claude", daten["body"])
            self.assertNotIn("Repo:", daten["body"])
            self.assertEqual(daten["labels"], ["enhancement"])
            self.assertEqual(os.listdir(ordner), [])
            open(os.path.join(bin_, "kaputt"), "w").close()
            aus = lauf()
            self.assertIn("kein Issue: HTTP 403", aus)
            self.assertEqual(len(os.listdir(ordner)), 1)
            self.assertIn("· Art: Wunsch", lesen(os.path.join(ordner, os.listdir(ordner)[0])))
            self.assertIn("gh issue create -R Myricaulus/merge-train --title Titel --body-file ", aus)
            self.assertIn("nicht selbst einreichen", aus)
            for wert in ("aus", ""):  # leer: nie das origin des Klons (Issue #9)
                KONF["vorfall_github"] = wert
                self.assertIsNone(agent_cli.vorfall_github())
                self.assertIn("kein Issue: vorfall_github nicht gesetzt", lauf())

    def test_faeden_teile(self):
        """status: Hinweise oben, Liste unten (Agenten kürzen mit head, Issue #8); ab LANGE_LISTE der Weg zu allen."""
        from merge_train.agent_cli import LANGE_LISTE, faeden_teile
        ks = [{"id": f"f{i}", "path": None, "erledigt": None,
               "nachrichten": [{"von": "claude", "wer": "Claude", "text": "x", "gesendet": "2026"}]} for i in range(LANGE_LISTE + 1)]
        hinweise, liste = faeden_teile(ks, "merge-train agent feedback")
        self.assertEqual(hinweise, [f"{LANGE_LISTE + 1} offene Fäden, Liste ganz unten – alle mit Text und Code: "
                                    "merge-train agent feedback --alle"])
        self.assertEqual(liste[1], f"Offene Fäden ({LANGE_LISTE + 1}):")
        self.assertEqual(len(liste), LANGE_LISTE + 3)  # nicht gekürzt
        self.assertEqual(faeden_teile(ks[:LANGE_LISTE], "x")[0], [])
        self.assertEqual(faeden_teile([], "x"), ([], []))

    def test_vorfall_todo(self):
        """agent vorfall: gibt es todo, wird es ein Eintrag im merge-train-Klon (vor GitHub und Datei)."""
        from unittest import mock
        from merge_train import agent_cli
        bin_, klon = tempfile.mkdtemp(dir=T), tempfile.mkdtemp(dir=T)
        with open(f"{bin_}/todo", "w") as f:
            f.write(f'#!/bin/sh\nprintf "%s\\n" "$@" > {bin_}/args\necho t9\n')
        os.chmod(f"{bin_}/todo", 0o755)
        _, o = agent_cli.agent_args(["vorfall", "Titel", "Bericht", "--als", "Claude", "--art", "bug"])
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"PATH": f"{bin_}:" + os.environ["PATH"]}), \
             mock.patch.object(agent_cli, "eigener_klon", return_value=klon), \
             mock.patch.object(agent_cli, "vorfall_issue", side_effect=AssertionError("kein Issue, wenn todo klappt")), \
             contextlib.redirect_stdout(aus):
            agent_cli.befehl_vorfall(o)
        self.assertIn("als todo-Eintrag im Projekt merge-train angelegt: t9", aus.getvalue())
        args = lesen(f"{bin_}/args").splitlines()
        self.assertEqual(args[:6], ["neu", "merge-train Bug: Titel", "-p", klon, "--prio", "3"])
        self.assertEqual(args[args.index("-n") + 1], "Bericht")
        with mock.patch.object(agent_cli, "eigener_klon", return_value=None):  # gebaut außerhalb eines Klons
            self.assertEqual(agent_cli.vorfall_todo("T", "B", "Claude"), (None, "kein merge-train-Klon"))
        self.assertIsNone(agent_cli.vorfall_todo("T", "B", "Claude")[0])  # Ersatz-todo der Tests scheitert → GitHub


class EinrichtungTest(unittest.TestCase):
    """merge-train status meldet eine fehlerhafte Einrichtung: Einstellung, fehlende Branches, Git-Hooks des Klons."""
    def test_konfig_maengel(self):
        from unittest import mock
        from merge_train.einstellungen import KONF, konfig_maengel
        with mock.patch.dict(KONF, {"lokall": True, "port": "8771", "lokal": 1, "kontext_schwellen": [1, 2, 3, 4]}):
            m = konfig_maengel()
        self.assertTrue(any("„lokall“" in x and "unbekannt" in x for x in m), m)
        self.assertTrue(any("„port“" in x for x in m) and any("„lokal“" in x for x in m), m)
        self.assertFalse(any("kontext_schwellen" in x for x in m), m)
        with mock.patch.dict(KONF, {"log_tage": True}):  # bool ist in Python ein int – trotzdem falsch
            self.assertTrue(any("„log_tage“" in x for x in konfig_maengel()))

    def test_hooks_und_zweige(self):
        from unittest import mock
        from merge_train import agent_cli
        w = tempfile.mkdtemp(dir=T)
        subprocess.run(["git", "init", "-q", "-b", "claude", w], check=True)
        subprocess.run(["git", "-C", w, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "a"], check=True)
        for name in agent_cli.HOOKS:
            if name != "pre-push":
                schreiben(f"{w}/.git/hooks/{name}", f"#!/bin/sh\n# {agent_cli.HOOKS[name]} (von install.idem.sh)\n")
        self.assertEqual(agent_cli.fehlende_hooks(w), ["pre-push"])
        with mock.patch.object(agent_cli, "konfig_maengel", return_value=[]):
            with mock.patch.object(agent_cli, "eigener_klon", return_value=w):
                teile = "\n".join(agent_cli.einrichtung_teile(w))
                self.assertIn("Git-Hooks fehlen: pre-push – Commits und Pushes laufen ungetestet", teile)
                self.assertIn("Branch reviewed fehlt im Klon", teile)
                self.assertNotIn("Branch claude", teile)
                self.assertNotIn("Branch", "\n".join(agent_cli.einrichtung_teile(w, zweige=False)))
            with mock.patch.object(agent_cli, "eigener_klon", return_value=None):  # anderes Repo: Hooks gehen es nichts an
                self.assertNotIn("Hooks", "\n".join(agent_cli.einrichtung_teile(w)))
            schreiben(f"{w}/.git/hooks/pre-push", "#!/bin/sh\n# merge-train: testen\n")
            subprocess.run(["git", "-C", w, "branch", "reviewed"], check=True)
            with mock.patch.object(agent_cli, "eigener_klon", return_value=w):
                self.assertEqual(agent_cli.einrichtung_teile(w), [])


class AktualisierenTest(unittest.TestCase):
    """branch_aktualisieren: vorspulen, nach Force-Push neu setzen, eigene Commits und Änderungen schützen."""
    def setUp(self):
        self.d = tempfile.mkdtemp(dir=T)
        self.g("init", "-q", "--bare", "-b", "mr", "origin.git", ort=self.d)
        self.g("clone", "-q", "origin.git", "oben", ort=self.d)  # der Autor, der pusht
        self.oben = f"{self.d}/oben"
        self.commit(self.oben, "a")
        self.g("push", "-q", "origin", "HEAD:mr", ort=self.oben)
        self.g("clone", "-q", "-b", "mr", "origin.git", "klon", ort=self.d)
        self.klon = f"{self.d}/klon"

    def g(self, *a, ort=None):
        return subprocess.run(["git", "-C", ort, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                              capture_output=True, text=True, check=True).stdout.strip()

    def commit(self, ort, text):
        schreiben(f"{ort}/f", text + "\n")
        self.g("add", "f", ort=ort); self.g("commit", "-qm", text, ort=ort)
        return self.g("rev-parse", "HEAD", ort=ort)

    def test_vorspulen_ausgecheckt(self):
        neu = self.commit(self.oben, "b"); self.g("push", "-q", "origin", "HEAD:mr", ort=self.oben)
        self.assertTrue(origin_voraus(self.klon, self.g("rev-parse", "HEAD", ort=self.klon), neu))  # noch nicht geholt
        branch_aktualisieren(self.klon, "mr")
        self.assertEqual(self.g("rev-parse", "HEAD", ort=self.klon), neu)
        self.assertEqual(lesen(f"{self.klon}/f"), "b\n")
        self.assertFalse(origin_voraus(self.klon, neu, self.g("rev-parse", "HEAD~1", ort=self.klon)))

    def test_nicht_ausgecheckt(self):
        self.g("switch", "-q", "-c", "anders", ort=self.klon)
        neu = self.commit(self.oben, "b"); self.g("push", "-q", "origin", "HEAD:mr", ort=self.oben)
        branch_aktualisieren(self.klon, "mr")
        self.assertEqual(self.g("rev-parse", "mr", ort=self.klon), neu)
        self.assertEqual(lesen(f"{self.klon}/f"), "a\n")  # Arbeitsverzeichnis bleibt

    def test_force_push(self):
        self.g("reset", "-q", "--hard", "HEAD", ort=self.oben)
        schreiben(f"{self.oben}/f", "a2\n")
        self.g("commit", "-qam", "a2", "--amend", ort=self.oben)
        self.g("push", "-qf", "origin", "HEAD:mr", ort=self.oben)
        self.assertIn("umgeschrieben", branch_aktualisieren(self.klon, "mr"))
        self.assertEqual(lesen(f"{self.klon}/f"), "a2\n")

    def test_stand_und_pushen(self):
        """stand_zu_gitlab: lokal weiter → pushen; nach Rebase (reflog stand auf gl) → Force-Push mit Lease; danach
        gepusht, bis die MR-Daten neu geholt sind; ohne lokalen Stand auf gl: abweichend, kein Push."""
        gl = self.g("rev-parse", "HEAD", ort=self.klon)
        self.assertIsNone(stand_zu_gitlab(self.klon, "mr", gl, gl))
        neu = self.commit(self.klon, "b")
        self.assertEqual(stand_zu_gitlab(self.klon, "mr", neu, gl), "lokal_voraus")
        self.assertIn("gepusht", branch_pushen(self.klon, "mr", gl))
        self.assertEqual(stand_zu_gitlab(self.klon, "mr", neu, gl), "gepusht")
        self.g("commit", "-q", "--amend", "-m", "b2", ort=self.klon)  # „Rebase“: neu ersetzt
        neu2 = self.g("rev-parse", "HEAD", ort=self.klon)
        self.assertEqual(stand_zu_gitlab(self.klon, "mr", neu2, neu), "umgeschrieben")
        with self.assertRaises(Fehler):  # Lease: origin steht nicht auf dem angegebenen Stand
            branch_pushen(self.klon, "mr", gl)
        self.assertIn("force-with-lease", branch_pushen(self.klon, "mr", neu))
        self.assertEqual(self.g("rev-parse", "mr", ort=f"{self.d}/origin.git"), neu2)
        anders = self.commit(self.oben, "x"); self.g("push", "-qf", "origin", "HEAD:mr", ort=self.oben)
        self.g("fetch", "-q", ort=self.klon)
        self.assertEqual(stand_zu_gitlab(self.klon, "mr", neu2, anders), "abweichend")
        with self.assertRaises(Fehler):
            branch_pushen(self.klon, "mr", anders)

    def test_mr_fuer_hinweise(self):
        """Vorfall 2026-11-16: JSON im tasks/ eines anderen Repos – das Projekt kommt aus dem cwd, gesucht wird in
        beiden Repos; haben beide einen MR zum Branch, ist das ein Fehler statt des falschen MR."""
        from unittest import mock
        from merge_train import agent_cli
        self.g("remote", "set-url", "origin", "git@gitlab.example:gruppe/kern/server.git", ort=self.klon)
        self.g("init", "-q", f"{self.d}/projekt", ort=self.d)
        self.g("remote", "add", "origin", "git@gitlab.example:gruppe/projekt/quelle.git", ort=f"{self.d}/projekt")
        os.makedirs(f"{self.d}/projekt/tasks"); pfad = f"{self.d}/projekt/tasks/K-1-review-markers.json"
        mrs = {"gruppe/kern/server": 17}
        def glab(host, weg):
            projekt = urllib.parse.unquote(weg.split("/")[1])
            return [{"web_url": f"https://{host}/{projekt}/-/merge_requests/{mrs[projekt]}"}] if projekt in mrs else []
        with mock.patch.object(agent_cli, "glab", glab):
            mr, ordner = agent_cli.mr_fuer_hinweise(pfad, {"branch": "K-1"}, cwd=self.klon)
            self.assertEqual((mr.projekt, mr.iid, os.path.realpath(ordner)), ("gruppe/kern/server", 17, os.path.realpath(self.klon)))
            mr, _ = agent_cli.mr_fuer_hinweise(pfad, {"mr": "!3"}, cwd=self.klon)
            self.assertEqual((mr.projekt, mr.iid), ("gruppe/kern/server", 3))  # „!3“ im Projekt des cwd
            mrs["gruppe/projekt/quelle"] = 165
            with self.assertRaisesRegex(Fehler, "mehrere offene MRs.*server!17.*quelle!165"):
                agent_cli.mr_fuer_hinweise(pfad, {"branch": "K-1"}, cwd=self.klon)
            mr, ordner = agent_cli.mr_fuer_hinweise(pfad, {"branch": "K-1"}, cwd=f"{self.d}/projekt")
            self.assertEqual((mr.iid, os.path.realpath(ordner)), (165, os.path.realpath(f"{self.d}/projekt")))  # nur ein Repo

    def test_aktion(self):
        neu = self.commit(self.oben, "b"); self.g("push", "-q", "origin", "HEAD:mr", ort=self.oben)
        mr = Waggon(host="gitlab.example", projekt="g/akt", iid=7)
        with akte_bearbeiten(mr) as akte:
            akte.update(klon=self.klon, meta={"source_branch": "mr", "target_branch": "mr"})
        from merge_train.server import aktualisieren_aktion
        d = aktualisieren_aktion(Anfrage("POST", "api/gitlab", "", {"mr": mr.id}, None))
        self.assertTrue(d["ok"] and d["neu_laden"]); self.assertIn(neu[:8], d["text"])
        self.assertIn("MR-Daten", d["text"])  # danach geholt (hier ohne GitLab: gescheitert, aber gemeldet)

    def test_auschecken(self):
        """branch_auschecken: neuer Branch aus origin, schützt offene Änderungen; mr_auschecken nur einmal je MR."""
        from merge_train.git import branch_auschecken
        from merge_train.review import mr_auschecken
        self.g("switch", "-q", "-c", "feature", ort=self.oben); self.commit(self.oben, "f1")
        self.g("push", "-q", "origin", "feature", ort=self.oben); self.g("fetch", "-q", ort=self.klon)
        schreiben(f"{self.klon}/f", "lokal\n")
        ok, text = branch_auschecken(self.klon, "feature")
        self.assertFalse(ok); self.assertIn("nicht committete", text)
        self.g("checkout", "-q", "f", ort=self.klon)
        mr = Waggon(host="gitlab.example", projekt="g/aus", iid=8)
        with akte_bearbeiten(mr) as akte:
            akte.update(klon=self.klon, meta={"source_branch": "feature", "target_branch": "mr"})
        self.assertIn("mr → feature ausgecheckt", mr_auschecken(mr))
        self.assertEqual(self.g("rev-parse", "--abbrev-ref", "HEAD", ort=self.klon), "feature")
        self.assertEqual(self.g("rev-parse", "--abbrev-ref", "feature@{u}", ort=self.klon), "origin/feature")
        self.g("switch", "-q", "mr", ort=self.klon)  # selbst zurück: bleibt so
        self.assertEqual(mr_auschecken(mr), "")
        self.assertEqual(self.g("rev-parse", "--abbrev-ref", "HEAD", ort=self.klon), "mr")
        self.assertEqual(branch_auschecken(self.klon, "mr"), (True, ""))  # schon ausgecheckt

    def test_fehlender_branch_holt(self):
        """mr_lokal: Quell-Branch noch nicht geholt → einmal git fetch, dann geht es."""
        from merge_train.gitlab import mr_lokal
        self.g("switch", "-q", "-c", "spaet", ort=self.oben); neu = self.commit(self.oben, "s")
        self.g("push", "-q", "origin", "spaet", ort=self.oben)
        mr = Waggon(host="gitlab.example", projekt="g/spaet", iid=9)
        with akte_bearbeiten(mr) as akte:
            akte.update(klon=self.klon)
        _, refs = mr_lokal(mr, {"source_branch": "spaet", "target_branch": "mr"})
        self.assertEqual(refs["head_sha"], neu)

    def test_schuetzt_eigenes(self):
        self.commit(self.oben, "b"); self.g("push", "-q", "origin", "HEAD:mr", ort=self.oben)
        schreiben(f"{self.klon}/f", "lokal\n")
        with self.assertRaisesRegex(Fehler, "nicht committete"):
            branch_aktualisieren(self.klon, "mr")
        self.g("commit", "-qam", "eigen", ort=self.klon)
        with self.assertRaisesRegex(Fehler, "lokale Commits"):
            branch_aktualisieren(self.klon, "mr")


class ZweigeTest(unittest.TestCase):
    """von/bis je lokalem Projekt: Einstellung [zweige], auf der Seite gewählt (Akte), Waggon „fehlt“."""
    def test_von_bis(self):
        from merge_train import git as g, einstellungen as e, quellen as q
        from merge_train.waggon import von_bis, zweige_standard
        w = f"{tempfile.mkdtemp(dir=T)}/demo"
        sh = lambda *a: subprocess.run(["git", "-C", w, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                       capture_output=True, text=True, check=True).stdout
        os.makedirs(w); sh("init", "-q", "-b", "main"); schreiben(f"{w}/a", "1\n"); sh("add", "a"); sh("commit", "-qm", "a")
        sh("switch", "-qc", "x"); schreiben(f"{w}/a", "2\n"); sh("commit", "-qam", "b")
        alt = (g.PROJEKTE_LISTE[:], dict(e.KONF))
        try:
            g.PROJEKTE_LISTE[:] = e.PROJEKTE_LISTE[:] = [w]
            e.KONF.update(von="reviewed", bis="claude", zweige={})
            self.assertEqual(von_bis("demo"), ("reviewed", "claude"))
            self.assertEqual(g.finde_repos(), [])  # Branches fehlen
            self.assertEqual(g.finde_repos(alle=True), [w])  # direkt genannt: zum Einstellen im Zug
            self.assertEqual(q.stand_oder_fehlt(w)["status"], "fehlt")
            self.assertFalse(q.projekt_einstellen("demo", "gibtsnicht", "x")[0])
            self.assertTrue(q.projekt_einstellen("demo", "main", "x")[0])
            self.assertEqual(von_bis("demo"), ("main", "x"))
            self.assertEqual(g.finde_repos(), [w])
            self.assertEqual(q.stand_oder_fehlt(w)["commits"], 1)
            sh("switch", "-q", "--orphan", "neu"); schreiben(f"{w}/a", "3\n"); sh("add", "a"); sh("commit", "-qm", "c")
            self.assertTrue(q.projekt_einstellen("demo", "main", "neu")[0])  # ohne gemeinsamen Vorgänger (Rebase)
            self.assertEqual(q.stand_oder_fehlt(w)["marke"], "⚠ keine Basis")
            self.assertTrue(q.projekt_einstellung("demo")["ohne_basis"])
            self.assertTrue(q.projekt_einstellen("demo", "main", "x")[0]); sh("switch", "-q", "x"); sh("branch", "-qD", "neu")
            self.assertTrue(Waggon(lokal="demo").kann["fertig"])
            d = q.projekt_einstellung("demo")
            self.assertEqual((d["von"], d["bis"], d["gewaehlt"], sorted(d["lokal"])), ("main", "x", True, ["main", "x"]))
            self.assertTrue(q.projekt_einstellen("demo", "main", "arbeitsstand")[0])
            self.assertFalse(Waggon(lokal="demo").kann["fertig"])  # arbeitsstand: kein „fertig“
            e.KONF["zweige"] = {"demo": {"von": "main", "bis": "x"}}
            self.assertEqual(zweige_standard("demo"), ("main", "x"))
            self.assertTrue(q.projekt_einstellen("demo", "", "")[0])  # zurück zum Standard
            self.assertEqual(q.projekt_einstellung("demo")["gewaehlt"], False)
        finally:
            g.PROJEKTE_LISTE[:] = e.PROJEKTE_LISTE[:] = alt[0]
            e.KONF.clear(); e.KONF.update(alt[1])

    def test_abhaken(self):
        """Datei abhaken: Haken je Stand der Datei, Füllung nach Zeilen (mindestens MINDEST je Datei)."""
        from merge_train.abhaken import MINDEST, abhaken
        w = f"{tempfile.mkdtemp(dir=T)}/haken"
        sh = lambda *a: subprocess.run(["git", "-C", w, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                       capture_output=True, text=True, check=True).stdout
        os.makedirs(w); sh("init", "-q"); schreiben(f"{w}/a", "1\n"); sh("add", "a"); sh("commit", "-qm", "a")
        kopf = lambda: sh("rev-parse", "HEAD").strip()
        st = lambda: {"ordner": w, "refs": {"head_sha": kopf()}, "dateien": [
            {"alt": "a", "neu": "a", "status": "geändert", "paare": [[1, None]] * (3 * MINDEST)},
            {"alt": "b", "neu": "b", "status": "gelöscht", "paare": [[1, None]]}]}
        wg = frische_akte("haken-demo")
        self.assertEqual(abhaken(wg, st(), "a", True)["fuellung"], {"anteil": 0.75, "fertig": 1, "dateien": 2})
        self.assertEqual(abhaken(wg, st(), "b", True)["abgehakt"], ["a", "b"])
        with self.assertRaises(Fehler):
            abhaken(wg, st(), "gibtsnicht", True)
        schreiben(f"{w}/a", "2\n"); sh("commit", "-qam", "b")  # neuer Stand von a: Haken fällt weg
        r = abhaken(wg, st())
        self.assertEqual((r["abgehakt"], r["fuellung"]["anteil"]), (["b"], 0.25))
        self.assertEqual(abhaken(wg, st(), "b", False)["fuellung"]["anteil"], 0)
        self.assertEqual(akte_lesen(wg)["fuellung"]["fertig"], 0)

    def test_teilabgabe(self):
        """„abgeben“: abgehakte Dateien auf <von>-wip (Index und Arbeitsverzeichnis bleiben), Diff danach ab dem Teilstand;
        ist alles abgegeben, wird von auf bis gesetzt und der Teilstand gelöscht."""
        from merge_train import git as g, einstellungen as e, quellen as q
        from merge_train.abhaken import abhaken
        w = f"{tempfile.mkdtemp(dir=T)}/wipdemo"
        sh = lambda *a: subprocess.run(["git", "-C", w, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                       capture_output=True, text=True, check=True).stdout
        os.makedirs(w); sh("init", "-q", "-b", "reviewed")
        for n in "abc":
            schreiben(f"{w}/{n}", "1\n")
        sh("add", "."); sh("commit", "-qm", "basis"); sh("switch", "-qc", "claude")
        schreiben(f"{w}/a", "2\n"); sh("rm", "-q", "b"); schreiben(f"{w}/d", "neu\n"); sh("add", "."); sh("commit", "-qm", "x")
        schreiben(f"{w}/c", "ungesichert\n")  # Arbeitsverzeichnis: bleibt, wie es ist
        alt = (g.PROJEKTE_LISTE[:], dict(e.KONF))
        try:
            g.PROJEKTE_LISTE[:] = e.PROJEKTE_LISTE[:] = [w]
            e.KONF.update(von="reviewed", bis="claude", zweige={})
            wg = frische_akte("wipdemo")
            kopf = sh("rev-parse", "claude").strip()
            st = q.LOKAL.seite(wg)[1]
            self.assertEqual(sorted(f["neu"] for f in st["dateien"]), ["a", "b", "d"])
            self.assertFalse(q.abgeben("wipdemo", kopf, st)[0])  # nichts abgehakt
            abhaken(wg, st, "a"); abhaken(wg, st, "b")
            ok, text = q.abgeben("wipdemo", kopf, st)
            self.assertTrue(ok, text)
            self.assertEqual(sh("rev-parse", "reviewed"), sh("rev-parse", "claude~1"))  # von unverändert
            self.assertEqual(sh("show", "reviewed-wip:a"), "2\n")
            self.assertNotIn("b", sh("ls-tree", "--name-only", "reviewed-wip").split())
            self.assertEqual(sh("status", "--porcelain"), " M c\n")
            self.assertEqual(g.statistik(w)["dateien"], 1)
            wagen = q.lokal_wagen([g.statistik(w)])
            self.assertTrue(wagen[0]["abgegeben"])
            self.assertNotIn("abgehakt", akte_lesen(wg))
            st = q.LOKAL.seite(wg)[1]
            self.assertEqual([f["neu"] for f in st["dateien"]], ["d"])
            abhaken(wg, st, "d")
            ok, text = q.abgeben("wipdemo", kopf, st)  # alles abgegeben: wie fertig
            self.assertTrue(ok, text)
            self.assertEqual(sh("rev-parse", "reviewed"), sh("rev-parse", "claude"))
            self.assertEqual(sh("branch", "--list", "reviewed-wip"), "")
            self.assertEqual(q.lokal_wagen([g.statistik(w)])[0]["status"], "fertig")
        finally:
            g.PROJEKTE_LISTE[:] = e.PROJEKTE_LISTE[:] = alt[0]
            e.KONF.clear(); e.KONF.update(alt[1])

    def test_toml_ohne_tomllib(self):
        from merge_train.einstellungen import _toml_einfach
        d = _toml_einfach('lokal = true\n[zweige.merge-train]\nvon = "reviewed"\n[zweige."a/b"]\nbis = "x"\n[repos]\n"g/p" = "~/k"\n')
        self.assertEqual(d, {"lokal": True, "zweige": {"merge-train": {"von": "reviewed"}, "a/b": {"bis": "x"}}, "repos": {"g/p": "~/k"}})


class KlonSuchenTest(unittest.TestCase):
    """klon_ordner: <ordner>/<projekt> zählt nur, wenn origin auf genau dieses Projekt zeigt."""
    def test_finden(self):
        from merge_train import gitlab
        from merge_train.einstellungen import KONF
        d = tempfile.mkdtemp(dir=T)
        for name, url in (("metrics-client", "git@gitlab.example:Gruppe/Metrics-Client.git"),
                          ("fremd", "git@gitlab.example:andere/fremd.git")):
            subprocess.run(["git", "init", "-q", f"{d}/{name}"], check=True)
            subprocess.run(["git", "-C", f"{d}/{name}", "remote", "add", "origin", url], check=True)
        alt = KONF["klon_ordner"]
        try:
            KONF["klon_ordner"] = d  # ein Eintrag statt Liste geht auch
            self.assertEqual(gitlab.klon_suchen("gruppe/metrics-client"), [f"{d}/metrics-client"])
            self.assertEqual(gitlab.klon_suchen("gruppe/fremd"), [])  # gleicher Name, anderes Projekt
            self.assertEqual(gitlab.klon_suchen("gruppe/gibts-nicht"), [])
            mr = Waggon(host="gitlab.example", projekt="gruppe/metrics-client", iid=3)
            self.assertIn(f"{d}/metrics-client", gitlab.lokale_klone(mr))
        finally:
            KONF["klon_ordner"] = alt


if __name__ == "__main__":
    unittest.main(verbosity=1)
