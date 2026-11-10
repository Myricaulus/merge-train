# Umbau von merge-train: übrige Schritte

Arbeitsplan für den Umbau auf dem Branch `fable`, für die nächste Session (Mensch oder Agent). Die Schritte 1–6 sind
erledigt, 7–8 stehen aus. Nach dem Umbau fliegt diese Datei wieder raus (bzw. das Bleibende wandert nach README/AGENTS.md).

## Ziel

Die Anwendung ist in wenigen Tagen gewachsen. Der Umbau soll sie fit für künftige Änderungen machen: nicht zu Ende
gedachte Muster schließen, den Code auf das Nötige vereinfachen, für Menschen lesbarer machen. **Am Verhalten ändert
sich nichts.** Jeder Schritt ist für sich lauffähig, getestet und ein eigener Commit.

## Regeln für die Arbeit

- **Nur im Worktree `/home/wsl/workspaces/merge-train-fable` (Branch `fable`) arbeiten.** Im Hauptstand
  `/home/wsl/workspaces/merge-train` (Branch `claude`) nichts ändern: dort läuft der Server des Nutzers (Port 8771) und
  startet bei jeder Änderung am gebauten Skript neu. Die Bash-Shell springt nach jedem Aufruf in den Hauptstand zurück,
  deshalb jeden Befehl mit `cd /home/wsl/workspaces/merge-train-fable && …` beginnen.
- Branches `reviewed` und `main` nicht anfassen. Nicht pushen. Commits auf `fable` gehören zum Vorgehen.
- **Nach jedem Schritt committen und stoppen.** Der Nutzer prüft dann seine Usage und kompaktiert selbst. Sparsam
  arbeiten: Tests einmal je Stand laufen lassen, keine Subagenten.
- Nicht `pkill -f "merge-train --server"`: das trifft auch den Server des Nutzers.
- Begriffe draft/staged/sent wie in AGENTS.md. Der Agent legt nie Review-Kommentare an.
- Namen: zu kurze Namen maßvoll ausschreiben („muss kein Roman werden“). `st` für den geladenen Zustand und `k` für
  einen Kommentar in kurzen Schleifen sind in Ordnung, `kom`, `rv`, `gs` und Ähnliches in längeren Funktionen nicht.
- Kein neues Framework (FastAPI, Flask o. ä.): merge-train bleibt ein Skript ohne Abhängigkeiten außer der
  Standardbibliothek (pygments optional, `glab` für GitLab).
- Ändert `claude` sich während des Umbaus, vor dem nächsten Schritt `git merge claude` im Worktree. Änderungen an
  `src/web/*` und Tests mergen von selbst. Python-Änderungen aus `src/NN_*.py` gibt es auf `fable` nicht mehr: dort den
  Diff von `claude` ansehen und von Hand ins passende Modul übertragen (so geschehen in `eaa1ce2`).

## Prüfen nach jeder Änderung

```sh
cd /home/wsl/workspaces/merge-train-fable
./bauen                                                                  # src/ → merge-train (Python-Zip)
MERGE_TRAIN_CONFIG=/nonexistent python3 werkzeug/namen_pruefen.py merge-train   # vergessene Imports
python3 tests/test_gitlab.py                                             # Ende-zu-Ende, ~13 s, Port 8799; „alles ok“
```

- `werkzeug/imports_richten.py` schreibt die Import-Zeilen aller Module neu, nach dem, was sie wirklich benutzen, und
  meldet `RÜCKWÄRTS a → b`, wenn ein Modul eines nutzt, das in der Reihenfolge später kommt. Nach dem Verschieben von
  Funktionen einfach laufen lassen. Neue Module dort in `REIHENFOLGE` und in `src/merge_train/__init__.py` eintragen.
  Namen müssen paketweit eindeutig sein (das Werkzeug bricht sonst ab).
- `namen_pruefen.py` findet Namen, die eine Funktion lädt, die es im Modul aber nicht gibt. Die Tests treffen nicht
  jeden Pfad, dieses Werkzeug schon.
- Die Tests laden alle Namen aller Module in ein Wörterbuch (`alles_laden` in `tests/test_gitlab.py`) und rufen manche
  Funktionen direkt beim Namen auf. Wer eine Funktion umbenennt, muss sie dort mit umbenennen (`grep -n 'm\["' tests/`).
- JS hat keine Tests außer `node --check` (Teil von `test_gitlab.py`). Änderungen an der Seite im Browser prüfen: eigenen
  Server aus dem Worktree auf einem anderen Port starten (`port = …` in einer eigenen Konfig, `MERGE_TRAIN_CONFIG=…`),
  nie den auf 8771 benutzen. Zum Anschauen gibt es die chrome-devtools-MCP-Werkzeuge.

## Stand nach den Schritten 1–6

| Commit | Inhalt |
|---|---|
| `558ecc0` | Schritt 1: Datei-Modus ohne Server, `--von/--bis/--inline/--alle` und Durchreich-Hüllen entfernt |
| `bd6784b` | Schritt 2: echte Python-Module im Paket `src/merge_train/`, `./bauen` bündelt zum Python-Zip, Migration `alt_gespraech_uebernehmen` entfernt |
| `0c14fc2` | Kürzel ausgeschrieben: `g_…` → `faden_…`/`gespraech_…`, `rk` → `review_kommentare`, `k_status` → `kommentar_status` |
| `eaa1ce2` | Merge von `claude` (Kontext-Füllstand im HUD) |
| `a6f6a12` | Schritt 3: Typ `Waggon` (waggon.py), `Fehler` als Basis von `GitLabFehler`, Quellen entschlackt, kein Import-Zyklus mehr |
| Schritt 4 | Zustand kapseln: `with zustand(waggon) as st:`, `zustand_lesen`, `kommentar_finden`/`faden_finden`, `…_anhaengen`, `eintrag_entfernen`, `ist_staged`/`ist_sent`, Aufbau der Datei oben in `zustand.py` |
| Schritt 5 | Server als Routen-Tabelle (`@route`, `bearbeiten`, `Antwort`/`Anfrage`, `beobachten`), Aktions-Tabellen `AM_FADEN`, `KOMMENTAR_AKTIONEN`/`AM_KOMMENTAR` |
| Schritt 6 | Abschließen: `abschluss_planen` (rein) → `schritt_ausfuehren` (GitLab, ohne Sperre) → `schritt_eintragen` (je Schritt kurz unter der Sperre); `entwuerfe_abgleichen(st, vorhanden, eigene_texte)` rein, Texte vorher per `abgleich_vorbereiten`; Umformulieren: `umformulieren_ziel_finden` → `hinweis_text_aendern` / `draft_daneben` |

Aufbau (`src/merge_train/`, jedes Modul nutzt nur die davor, siehe `__init__.py`):

```
einstellungen  waggon  git  syntax  zeilen  web  diff_html  zustand  gitlab  hinweise  ansichten  seite
quellen  zuhoerer  review  gespraech  server  agent_cli  cli          (+ src/__main__.py, web/*.css|js|svg|webp)
```

Wichtige Bausteine:

- **`Waggon`** (`waggon.py`, `NamedTuple`): `Waggon(lokal="proj")` oder `Waggon(host, projekt, iid)`. Daran hängen
  `.id` (Kennung der Seite: `projekt:name` bzw. `host/gruppe/projekt/42`), `Waggon.aus_id(...)`, `.name`, `.url`,
  `.dateiname`, `.kann` (`review`/`fertig`/`committen`), `.als_dict()` / `Waggon.aus_dict()` (Feld `mr` der
  Zustandsdatei). Unveränderlich: ändern mit `waggon._replace(host=…)`. Variablen heißen `waggon`. In älterem Code
  heißt derselbe Wert noch oft `mr`, auch für lokale Projekte. Beim Anfassen in `waggon` umbenennen, wo er beides sein
  kann, `mr` nur behalten, wo es wirklich ein MR ist.
- **Quellen** (`quellen.py`): `LOKAL`, `GITLAB`, `quelle(waggon)`. Sie wissen `an()`, `ort()` (Klon und Stand),
  `seite()`, `wagen()`, `prompt()`. `schluessel_von(kennung)` prüft zusätzlich, ob die Quelle eingeschaltet ist.
- **Zustand** (`zustand.py`): eine JSON je Waggon (`review_datei/laden/speichern`), globale `SPERRE` (RLock, in
  `einstellungen.py`). `kommentare` enthält Review-Kommentare und Gesprächsfäden gemischt: Fäden haben `nachrichten`
  (`review_kommentare(st)` und `faeden_von(st)` trennen sie). Die Seiten-Struktur liegt als Zeiger `st["struktur"]`
  auf eine Cache-JSON (`struktur_laden`).
- **Fehler** (`waggon.py`): `Fehler` = Meldung für Nutzer/Agent; `GitLabFehler(Fehler)` nur für glab-Probleme,
  `MetaFehlt(GitLabFehler)` für fehlende MR-Daten.

---

## Schritt 4: Zustand kapseln

**Problem.** Laden, Sperren und Speichern sind über das ganze Paket verstreut: 30 Blöcke `with SPERRE:`, 40 Aufrufe von
`review_laden`, 19 von `review_speichern` (davon 11 bzw. 5 allein in `agent_cli.py`). Jede Stelle muss selbst daran
denken, unter der Sperre zu laden **und** zu speichern. Wer nur liest, sperrt manchmal und manchmal nicht. Dazu liegen
Review-Kommentare und Gesprächsfäden gemischt in `st["kommentare"]` und werden überall per `nachrichten is None`
auseinandergehalten.

**Ziel.**

1. Ein Kontextmanager in `zustand.py`:

   ```python
   @contextmanager
   def zustand(waggon, speichern=True):
       """Zustand des Waggons laden, unter der Sperre halten, am Ende speichern (nur wenn geändert)."""
       with SPERRE:
           st = review_laden(waggon)
           vorher = json.dumps(st, sort_keys=True)
           yield st
           if speichern and json.dumps(st, sort_keys=True) != vorher:
               review_speichern(waggon, st)
   ```

   und für reines Lesen `zustand_lesen(waggon)` (lädt unter der Sperre, gibt eine Kopie zurück). Danach jedes Muster
   `with SPERRE: st = review_laden(x) … review_speichern(x, st)` durch `with zustand(x) as st:` ersetzen. Vorsicht bei
   Funktionen, die **innerhalb** der Sperre GitLab fragen (`abschliessen`, `entwuerfe_abgleichen`). Das bleibt erst mal
   so (siehe Schritt 6), nur die Form ändert sich. Frühe `return`s im Block speichern jetzt automatisch, wenn sich etwas
   geändert hat. Jede Stelle prüfen, ob das gewollt ist; wo nicht, `speichern=False` oder die Änderung erst nach der
   Prüfung machen.
2. `review_laden`/`review_speichern` werden dann nur noch in `zustand.py` selbst und in `zustand()` aufgerufen. Mit
   `grep -n "review_laden\|review_speichern" src/merge_train/*.py` prüfen.
3. **Kommentare und Fäden trennen**, aber nur in der API, nicht im Dateiformat (alte Dateien sollen weiter gehen, eine
   Migration lohnt nicht): `review_kommentare(st)` und `faeden_von(st)` bleiben die einzigen Zugriffe. Dazu
   `faden_finden(st, id)` und `kommentar_finden(st, id)` statt der vielen `next((k for k in st["kommentare"] if …))`.
   Neue Einträge über `kommentar_anhaengen(st, k)` / `faden_anhaengen(st, k)`.
4. **Stufen als benannte Funktionen** neben `kommentar_status`: `ist_staged(k)`, `ist_sent(k)` (Begriffe aus AGENTS.md)
   statt `kommentar_status(k) in ("neu", "geaendert", "loeschen")` an mehreren Stellen (`ausstehend`, `agent_cli.K_STATUS`,
   `review.py`). Die Werte von `kommentar_status` bleiben, weil die Seite (review.js `STATUS`) sie kennt.
5. Kommentar oben in `zustand.py` mit dem Aufbau der Datei (Felder `mr`, `meta`, `kommentare`, `hinweise`,
   `hinweis_dateien`, `struktur`, `todo_id`, `abgeschlossen`, Felder eines Kommentars und eines Fadens). Ein Teil davon
   steht heute als Kommentarblock oben in `gespraech.py`, dorthin verschieben und ergänzen.

**Fertig, wenn** kein Modul außer `zustand.py` mehr `SPERRE` zusammen mit `review_laden` benutzt, Tests und
`namen_pruefen` grün sind. Commit: „Zustand kapseln: with zustand(waggon) …“.

**Erledigt**, mit zwei Abweichungen vom Plan:
- `zustand_lesen` sperrt **nicht**: `ersetzen()` schreibt atomar, Lesende sehen immer eine ganze Datei. Mit Sperre
  hätte jedes `api/stand` gewartet, solange `abschliessen` unter der Sperre GitLab fragt.
- `abschliessen` ruft innerhalb von `with zustand(mr)` weiter `review_speichern` nach jedem Kommentar (vergebene
  `gitlab_id`s überstehen einen Abbruch). Fällt mit Schritt 6 weg; dann ist `review.py` der letzte Nutzer außerhalb
  von `zustand.py` gewesen.
- Nebenbei: in `kommentar_aktion` wird ein Hinweis erst nach der Prüfung auf leeren Text als „übernommen“ markiert
  (sonst hätte das automatische Speichern beim frühen `return` den Hinweis ohne Kommentar übernommen). Lokale
  Variablen `zustand` in `agent_main`/`_prozess` heißen jetzt `befund`/`prozess_zustand`.

## Offen: aussagekräftigere Namen (Hinweis des Nutzers)

„zustand“ ist sehr allgemein – Zustand wovon? Gemeint ist die Review-/Gesprächsdatei eines Waggons. Bei Gelegenheit
(eigener Commit, rein mechanisch) Modul und Funktionen nach dem benennen, was sie halten, z. B. `waggon_datei` /
`with waggon_daten(waggon) as daten:`; dasselbe Maß an andere allgemeine Namen anlegen (`st`, `d`, `r`, `rv`).

## Schritt 5: Server als Routen-Tabelle

**Problem.** `server.py` besteht im Kern aus einer Funktion `server()` (~220 Zeilen) mit einer inneren Klasse `H`,
deren `get()` und `post()` lange `if pfad == …`-Ketten sind (17 Zweige). Schlüssel prüfen (`k`), Waggon aus der Anfrage
holen (`schluessel_von(d.get("mr"))`), Ansicht lesen (`ansicht_lesen`) und Fehler in JSON verwandeln
(`except Fehler` → 400, sonst 500) wiederholen sich je Zweig leicht anders. `/api/gespraech` reicht eine `aktion`
weiter, die `gespraech_aktion` wieder mit `if aktion == …` verteilt; dasselbe gilt für `kommentar_aktion` in
`review.py` (neu/reihenfolge/aendern/loeschen/wiederherstellen).

**Ziel.**

1. Handler als Funktionen auf Modulebene, registriert per Dekorator:

   ```python
   ROUTEN = {}  # (methode, pfad) → (funktion, braucht)

   def route(methode, pfad, *, schluessel=True, waggon=False, ansicht=False, quelle_an=None):
       def eintragen(f):
           ROUTEN[(methode, pfad)] = (f, dict(schluessel=schluessel, waggon=waggon, ansicht=ansicht, quelle_an=quelle_an))
           return f
       return eintragen

   @route("POST", "/api/kommentar", waggon=True, ansicht=True)
   def api_kommentar(anfrage, waggon, ansicht): ...
   ```

   Die eine Stelle im Handler, die `ROUTEN` nachschlägt, erledigt Schlüssel, Waggon (`schluessel_von`), Ansicht,
   „Quelle eingeschaltet?“ (`GITLAB.an()`/`LOKAL.an()`) und die Fehlerbehandlung **einmal**. Antworten als Rückgabewert
   (`dict` → JSON, `(status, text, typ)` für Seiten), nicht mehr `self.json_senden` in jeder Funktion.
2. Präfix-Routen (`mr/<kennung>`, `<projekt>.html`) bleiben als kleine Liste von `(regex, funktion)`. Weiterleitungen
   (Kennung kanonisch machen) dort.
3. `server()` behält nur Aufbau: Port binden, `syntax.SERVER_SOCKET` setzen, Wächter-Thread (Neustart bei neuer mtime
   von `SKRIPT`/`KONFIG_DATEI` per `os.execv`), Leerlauf-Ende, Vorbau im Hintergrund. Die Wächter-Logik als eigene
   Funktion `beobachten(...)`.
4. Aktionen: `gespraech_aktion` und `kommentar_aktion` in eine Tabelle `{aktion: funktion}` je Modul zerlegen
   (`faden_neu`, `faden_antworten_nutzer`, `faden_aendern`, …; `kommentar_neu`, `kommentar_aendern`, …). Die Route
   schlägt nach und gibt bei unbekannter Aktion 400 zurück. Die Seite schickt weiter `{"aktion": …}`, am JS ändert sich
   nichts.
5. Die Origin-Prüfung (`herkunft`) und der Schlüssel bleiben genau so streng: jede POST-Route braucht den Schlüssel,
   GET-Routen mit Daten (`api/review`, `api/stand`, `api/zeilen`, …) auch. Beim Umbau Route für Route vergleichen, ob
   vorher ein Schlüssel nötig war, und es in der Tabelle sichtbar machen (`schluessel=False` nur bei `ping`, Favicon,
   Seiten).

**Fertig, wenn** `get()`/`post()` je unter ~30 Zeilen sind, keine Route mehr selbst Schlüssel oder Fehler behandelt und
die Tests grün sind. Die Tests sprechen den Server über HTTP an und decken die meisten Routen ab. Danach einmal mit
eigenem Server im Browser durchklicken (Projekt-Seite, MR-Seite, Kommentar anlegen, Faden, fertig). Commit:
„Server: Routen-Tabelle …“.

**Erledigt.** `get()` 9, `post()` 13 Zeilen. Statt im Browser: alter (Schritt 4) und neuer Server auf demselben
Testzustand, ~45 Anfragen (alle Routen, Fehler- und Randfälle) verglichen – Status, Typ, Weiterleitung, Rumpf gleich bis
auf zwei bewusste Fälle: POST auf unbekannten Pfad mit falschem Schlüssel → 404 statt 403 (erst Route, dann Schlüssel);
unbekannte Aktion an einem Kommentar meldet „unbekannte Aktion“ statt vorher „Kommentar nicht gefunden“. Fehlerformat
bleibt je Methode: GET Text (502/500), POST JSON. `zug.js`/`api/zug` waren und sind ohne Schlüssel (in der Tabelle
sichtbar: `mit_schluessel=False`).

## Schritt 6: Lange Abläufe in Planen und Ausführen zerlegen

**Problem.** `abschliessen` (`review.py`, ~70 Zeilen) und `kommentar_umformulieren` (`agent_cli.py`, ~70 Zeilen)
mischen Entscheidung und Wirkung. `abschliessen` prüft den Stand, holt Entwürfe und Kommentare aus GitLab, entscheidet
je Kommentar (löschen/ändern/neu/übernehmen) und ruft dabei sofort `glab` auf, **unter `SPERRE`**. Das hält alle
anderen Anfragen an, solange GitLab antwortet, und lässt sich nicht testen, ohne GitLab nachzubauen. Ähnlich
`entwuerfe_abgleichen` und `meta_und_entwuerfe`.

**Ziel.**

1. `abschliessen` in drei Teile:
   - `abschluss_planen(st, vorhanden, gitlab_kommentare, reihenfolge) → [Schritt]`: reine Funktion ohne I/O. Ein
     Schritt ist z. B. `("loeschen", k_id, gitlab_id)`, `("aendern", k_id, gitlab_id, text)`,
     `("anlegen", k_id, position)`, `("uebernehmen", k_id, gitlab_id)` (vorhandener Entwurf mit gleichem Text).
   - `abschluss_ausfuehren(waggon, schritte) → [Ergebnis]`: ruft `glab`, **ohne Sperre**.
   - Ergebnisse unter `with zustand(waggon) as st:` zurückschreiben (gitlab_id, gitlab_text setzen, Gelöschtes
     entfernen). Dabei Kommentare, die sich inzwischen geändert haben (Nutzer hat während des Sendens getippt), nicht
     überschreiben: Text vor dem Senden merken und vergleichen.
   - Die Rückmeldung (`z["neu"]`, `z["weg"]`, …) aus den Ergebnissen zählen.
2. `kommentar_umformulieren` genauso: erst `ziel_finden(ziel, ziele) → (waggon, art, eintrag)` (draft per `h:<key>`,
   staged/sent-Kommentar, Faden), dann je Art eine kleine Funktion. Die Regel „draft ändern, sonst neuen draft
   daneben“ (AGENTS.md) steht dann an einer Stelle.
3. `entwuerfe_abgleichen` (in GitLab verworfene Entwürfe werden wieder staged) als reine Funktion auf `(st, vorhanden)`.
4. Wo es sich anbietet, dasselbe für `faden_anlegen` (Ort prüfen ↔ anlegen) und `fertig` in `quellen.py`
   (Prüfungen ↔ Branch setzen, Runde schreiben, todos erledigen).

**Fertig, wenn** keine `glab`-Anfrage mehr unter `SPERRE` läuft (`grep -n "glab(" review.py` und jeweils den
umgebenden Block prüfen), die Planungsfunktionen ohne GitLab aufrufbar sind und die Tests grün sind. Die Tests haben
mit `tests/fake-glab` gute Abdeckung fürs Abschließen (Entwürfe anlegen/ändern/löschen, `FAKE_GLAB_FEHLER_POSITION`).
Commit: „Abschließen und Umformulieren: planen, dann ausführen …“.

**Erledigt.** Keine GitLab-Anfrage mehr unter der Sperre (per AST geprüft: kein `glab`/`alle`/… in einem
`with zustand(…)`). `review_laden`/`review_speichern` gibt es nur noch in `zustand.py`. Nebenläufigkeit beim Senden:
`gitlab_text` ist der gesendete Text (tippt der Nutzer währenddessen, ist der Kommentar danach „geaendert“); ein
währenddessen wiederhergestellter Kommentar wird wieder „neu“; ein währenddessen gelöschter bekommt seinen gerade
angelegten Entwurf in GitLab wieder gelöscht. Diese Fälle in Schritt 8 als Einzeltests von `schritt_eintragen` abdecken.
`faden_anlegen` (prüft schon vor dem Anlegen) und `fertig` (sperrt nur die Runden-Datei) blieben, wie sie sind.

## Schritt 7: JavaScript lesbar machen

**Problem.** `src/merge_train/web/*.js` (~580 Zeilen, `review.js` 237, `diff.js` 154, `zug.js` 129, `basis.js` 37,
`bahnhof.js` 20) ist sehr dicht geschrieben: mehrere Statements je Zeile (Zeilen bis über 300 Zeichen), Namen mit ein
bis drei Buchstaben (`ds`, `ls`, `kh`, `RV`, `FD`, `GA`, `RVW`, `AG`, `qs`, `el`, `sst`, `fb`), und viele Globale über
Dateigrenzen hinweg. Alle Dateien landen hintereinander in einem `<script>`, die Reihenfolge ist `JS`, `JS_ZUG`,
`JS_DIFF`, `JS_REVIEW`, `JS_BAHNHOF` (siehe `seite.py` und den `node --check` im Test). Beispiele für Kopplung:
`meld` wird in `zug.js` definiert und in `review.js` benutzt. Die Startseite braucht Attrappen
`const ds=[],ls=[];function kh(){}`, weil `basis.js` sie erwartet. Meldungen werden zu Toasts, indem `review.js` per
`MutationObserver` den Text von `#meldung` beobachtet (Zeile ~227).

**Ziel** (Verhalten und Aussehen unverändert):

1. Formatierung: ein Statement je Zeile, Einrückung mit 2 Leerzeichen, Zeilen ≤ 120 Zeichen. Das ist mechanisch und
   kommt **zuerst als eigener Commit**, damit die inhaltlichen Änderungen danach lesbar im Diff stehen. Kein
   Build-Werkzeug einführen. Wenn ein Formatierer hilft (z. B. `npx prettier` einmalig), nur lokal benutzen, nicht
   ins Repo.
2. Namen ausschreiben: `ds` → `dateien`, `ls` → `links`/`listenEintraege` (je nach Bedeutung, erst nachsehen), `kh` →
   `kopfHoehe`, `RV` → `review`, `FD()` → `faeden()`, `GA()` → `gespraechAusstehend()`, `RVW` → `mitReview`, `AG()` →
   `agenten()`, `fb` → `feedbackKnopf` usw. **Die Felder der Server-Antworten (`MR`, `kann`, `g_ausstehend`, …) nicht
   umbenennen**, sonst muss Python mit. Wenn doch, dann in beiden zugleich.
3. Ein Objekt `App` (in `basis.js`) für das, was Dateien teilen: `App.melden(text, art)`, `App.review`, `App.waggon`
   (= `MR`), `App.kann`. Dateien greifen nur über `App` aufeinander zu. Die Startseite setzt die Teile, die sie nicht
   hat, gar nicht, und die Nutzer prüfen `if (App.dateien)`. Keine Attrappen mehr.
4. `melden()` ruft die Toasts direkt auf, der `MutationObserver` entfällt. Alle Stellen, die `meld.textContent = …`
   setzen, auf `App.melden(…)` umstellen (`grep -n "meld\." src/merge_train/web/*.js`).
5. HUD und Toasts aus `review.js` in eigene Dateien `hud.js` und `toasts.js`, die Lok/Zug-Zeichnung aus `zug.js` nach
   `lok.js`. Neue Dateien in `web.py` laden und in die Liste der Skripte der Seite (`seite.py`) und des Tests
   (`node --check`) eintragen.
6. Je Datei oben ein Kommentar: wofür, was sie von `App` braucht, was sie bereitstellt.

**Prüfen:** `node --check` (im Test) reicht nicht. Eigenen Server aus dem Worktree auf einem anderen Port starten und im
Browser durchgehen: Startseite (Zug, Güterbahnhof, HUD, Toasts), Projekt-Seite (Dateien j/k, i inline, z, c, Kontext
aufklappen, Faden anlegen, Feedback senden, fertig), MR-Seite mit `tests/fake-glab` (Kommentar, Hinweis übernehmen,
Reihenfolge ziehen, Abschließen), Commit-Ansicht. Auf Konsolenfehler achten. Am besten vor dem Umbau Screenshots
machen und danach vergleichen. Commits: „JS: Formatierung“, dann „JS: Namen, App-Objekt, Dateien aufgeteilt“.

## Schritt 8: Einzeltests für die Logik

**Problem.** Es gibt nur den Ende-zu-Ende-Test `tests/test_gitlab.py` (~800 Zeilen, ~163 Prüfungen, 13 s). Er ist
wertvoll, sagt bei einem Fehler aber selten, wo es liegt, und deckt die Rechenlogik nur in wenigen Fällen ab.

**Ziel:** `tests/test_einheiten.py` mit `unittest` (Standardbibliothek), ohne Server, ohne glab, in unter einer Sekunde:

1. **`zeilen.py`** (Zeilen-Arithmetik, der fehleranfälligste Teil): `paare_und_hunks`, `alt_zeile`, `im_diff`,
   `kontext_zeile`, `zeile_vorwaerts` (Faden bleibt bei Änderungen über/unter/an seiner Zeile an der richtigen Stelle),
   `zurueck_diffs`, `diff_enden`. Mit kleinen, von Hand geschriebenen Diffs: Zeile eingefügt, gelöscht, geändert,
   Datei neu/gelöscht/umbenannt, Kontext am Dateianfang/-ende.
2. **Stufen** (`zustand.py`): `kommentar_status` für alle Kombinationen, `ausstehend`, und nach Schritt 4 `ist_staged`/`ist_sent`.
3. **`Waggon`**: `aus_id` ↔ `.id` hin und zurück, ungültige Kennungen (`..`, leere Teile, fehlende iid) werfen
   `Fehler`, `aus_dict`/`als_dict`, `dateiname` ohne Sonderzeichen.
4. **Planen** (nach Schritt 6): `abschluss_planen` für neu/geändert/gelöscht/schon vorhanden, Reihenfolge wie in der
   Box „GitLab-Kommentare“ (`gitlab_reihenfolge` in `review.py`).
5. **Hinweise** (`hinweise.py`): `needle_zeilen` (needle mit `=` am Anfang = ganze Zeile, mehrfach vorhanden, fehlt),
   `see_also_aufloesen` (Formen `pfad:zeile`, `pfad:a-b`, `{path, needle}`, `{path, diff}`).
6. **`git.zerlegen`** (Diff-Ausgabe zerlegen) mit Binärdateien, Umbenennungen und Dateinamen mit Leerzeichen/Umlauten.

Laden wie im Ende-zu-Ende-Test (`sys.path.insert(0, "src")`, dann `from merge_train.zeilen import …`). Die Einzeltests
laufen gegen `src/`, nicht gegen das gebaute Zip. Vorher `MERGE_TRAIN_CONFIG` auf eine leere Datei setzen, damit nicht
die Konfig des Nutzers gelesen wird (die Module lesen sie beim Import). In AGENTS.md und README unter „Tests“
eintragen: `python3 tests/test_einheiten.py` (schnell, zuerst) und `python3 tests/test_gitlab.py`.

**Fertig, wenn** die Einzeltests die genannten Funktionen abdecken und beide Testdateien grün sind. Commit:
„Einzeltests für Zeilen, Stufen, Waggon, Hinweise …“.

---

## Danach

- `refactor.md` löschen. Bleibendes (Aufbau der Module, Werkzeuge, Prüfen im Browser) nach README „Entwicklung“ bzw.
  AGENTS.md übernehmen.
- README und `docs/*.md` auf veraltete Namen prüfen (`grep -rn "src/0\|src/1\|g_\|GitLabFehler" README.md docs skill`).
- Dem Nutzer melden. `fable` nach `claude` zu bringen entscheidet er (Merge oder Fast-Forward; danach auf dem
  WSL-Rechner einmal `./bauen`, der Symlink `~/.local/bin/merge-train` bleibt gleich).

## Bewusst nicht im Plan

- Kein Wechsel des Dateiformats der Zustands-JSON (keine Migration nötig, alte Dateien laufen weiter).
- Keine neuen Funktionen und keine Änderungen am Aussehen.
- Weitere lange Funktionen (`agent_main` ~170 Zeilen mit argparse-Unterbefehlen, `seite_bauen`, `hinweise_aufloesen`)
  nur anfassen, wenn ein Schritt sie ohnehin berührt. Ein naheliegender Nachfolger wäre, `agent_main` in je eine
  Funktion pro Unterbefehl zu teilen (`argparse` mit `set_defaults(aufruf=…)`).
