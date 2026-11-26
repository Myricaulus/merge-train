# Funktionen von merge-train (Code-Glossar für Agenten)

Wozu: gegen Duplikation. Vor einer Änderung hier nachsehen, ob es die Funktion oder einen Baustein schon gibt, und dann
diesen erweitern statt daneben etwas Zweites zu bauen. Je Funktion: Zweck in einer Zeile, **Achsen** (wo Varianten
dazukommen), **Ort** im Code, **Erweitern**. Wie sie sich verhält, steht im Docstring der genannten Funktion, oben im
Modul und im README. Welches Wort was meint: [glossar.md](glossar.md).

Beim Ändern mitpflegen: neue Funktion = neuer Eintrag, neue Variante = ein Wort in ihrer Achse. Keine Einzelheiten zum
Verhalten hier, die gehören in den Docstring.

## Funktionen

### 1. Mehrere Quellen für Waggons
Lokale Branches, Läufe des Myrlings und GitLab-MRs, alle in einem Zug.
- Achsen: Quelle (lokal, Myrling, GitLab; geplant GitHub), Waggon-Art.
- Ort: `quellen.py` (Basis `Quelle`, `Lokal`, `Myrling`, `GitLab`, `quelle(waggon)`), `waggon.py` (Basis `Art`,
  `LokalArt`, `MyrlingArt`, `MrArt` in `ARTEN`), `gitlab.py`, `myrling.py` (Vertrag oben im Modul), `cli.py`.
- Bausteine: `von_bis(projekt)` für von/bis eines lokalen Projekts, `stand_oder_fehlt` bei fehlendem Branch oder
  Vorgänger, `lauf_ort` (Basis je Datei eines Laufs), Waggon-Karte `projekt_einstellung`/`projekt_einstellen`.
- Erweitern: neue Quelle = Unterklasse von `Quelle` plus eine von `Art` (mit `logo`), keine eigene Seite, keine
  `if lokal`-Ketten.

### 2. Fähigkeiten je Waggon (`kann`)
`review`, `fertig`, `committen`.
- Ort: `Art.kann` (`waggon.py`), in JS `App.kann`.
- Erweitern: Verhalten, das nur manche Waggons haben, als weitere Fähigkeit.

### 3. Vergleichs-Modi (was gegen was)
- Achsen: lokal, Arbeitsstand, MR, Myrling, Beobachten (16).
- Ort: `einstellungen.py` (`VON`, `BIS`, `ARBEITSSTAND`), `git.py` (`arbeitsstand`, `stand_mit`), `Quelle.ort`.

### 4. Diff-Seite (gemeinsam für alle Quellen)
Diff aus dem lokalen Git, Dateiliste, Kontext nachladen, Datei abhaken und filtern, Boxen unter ihrer Zeile.
- Achsen: Dateiart (generiert/groß), Darstellung (nebeneinander/inline), Filter.
- Ort: `seite.py`, `diff_html.py`, `syntax.py`, `web/diff.js`, `web/navigation.js` (`dateienFiltern`, Sprung zu einer
  Datei `zuDatei`, nach dem Abhaken `naechsteOffene`); abhaken: `abhaken.py`, `App.wagenFuellen`; Boxen: `einfuegen` (`web/review.js`); Routen `api/zeilen`, `api/datei`,
  `api/abgehakt`.
- Bausteine: Jede Seite nennt den Schlüssel ihrer Struktur (`MR.seite`, `seiten_schluessel`); der Server rechnet
  gegen genau diese (`seiten_struktur`, `struktur_der_seite`), die CLI gegen die zuletzt gebaute (`akte.struktur`).
  Ob eine Seite noch aktuell ist: `seite_veraltet` (`beobachter.py`). Einrichtung je Datei (Inline-Tabelle, Knöpfe
  der Lücken, Haken): `App.jedeDatei`, für neue bzw. neu gefüllte Dateien `App.dateiEinrichten`; neuer Diff im DOM:
  `App.dateienNeu` (dieselben Arrays `App.dateien`/`App.dateiLinks`). Neuer Stand ohne Neuladen: `App.neuHolen`
  (`web/tausch.js`, sonst `location.reload`), Route `api/diff` aus den Teilen der Seite (`teil`, `seiten_teile`),
  Schlüssel je Datei `datei_schluessel` (`diff_html.py`), Rahmen `App.einrahmen` (`web/beobachten.js`, `neue_zeilen`).
- Erweitern: Filtergruppen (etwa FE/BE) als weitere Zeilen im Filtermenü.

### 5. Ansichten eines Waggons
`alles`, `commit:<sha>`, `seit:<sha>`.
- Ort: `ansichten.py`, `ansicht_zuordnen` (`review.py`), `web/diff.js`.
- Erweitern: eine neue Sicht auf denselben Vergleich ist eine weitere Ansicht.

### 6. Zeilen umrechnen (alt ↔ neu, Stand ↔ Stand)
Grundlage für mitwandernde Fäden, Commit-Ansichten, fremde Diskussionen.
- Ort: `zeilen.py`.
- Erweitern: jede „gehört diese Zeile noch hierher?“-Frage geht über diese Funktionen.

### 7. Code-Verweise und Popup
`pfad:zeile`, Bereiche, Siehe-auch und Vergleiche (⇄) öffnen ein Popup. Steht dort ein Faden außerhalb der
Änderungen, springen sie zu ihm und klappen den Kontext auf (`ortZeigen`, `springen`, `zeileZeigen` in `web/diff.js`).
- Achsen: Verweisart, Herkunft (Hinweis, Nachricht, Thread), Stand (`stand_waehlen`, `@ref`), Repo (Hauptrepo, Submodul).
- Ort: `hinweise.py` (`ort_lesen`, `see_also_aufloesen`, `stand_waehlen`), `code_links` (`gespraech.py`),
  `vergleich_daten`/`zeilen_daten` (`review.py`), `inhalt`/`fehlt_grund` (`git.py`), `web/diff.js`;
  Routen `api/zeilen`, `api/vergleich`.
- Erweitern: Dateien aus einem anderen Repo (etwa Begleitdateien eines Laufs) über `inhalt` anschließen.

### 8. Gespräch mit Agenten (Fäden)
Fäden an Zeile, Bereich, GitLab-Kommentar oder allgemein; Agent holt ab, antwortet, legt eigene Threads an.
- Achsen: Quelle (`kann.committen`, `Quelle.prompt`; beim eigenen MR laut `eigener_mr` darf der Agent umsetzen), Agent,
  Faden-Aktion, Ort.
- Ort: `gespraech.py`, `agent_cli.py` (`status_ausgeben`, `feedback`, `antworten`, `thread`, `agent_name`), Route
  `api/gespraech`, `web/review.js`; Faden an Kommentar: `faden_zu`/`faden_ziel`, nach neuem Text eines drafts
  `faeden_umhaengen` (der key hängt am Text).
- Erweitern: neue Einrichtungs-Prüfung für `status` = Zeile in `einrichtung_teile`; neuer Harness in
  `AGENT_UMGEBUNG`; Befehlsübersicht in `completions/merge-train.fish` mitpflegen.

### 9. Wer hört zu / Agent benachrichtigen
- Achsen: Zustellweg (horchen, todo, eigener Befehl), Agent, Tätigkeit, Ende.
- Ort: `zuhoerer.py` (`zustellweg`, `benachrichtigen`, `prompt_merken`, `kontext`), `entwuerfe_senden` (`akte.py`),
  `horchen` (`agent_cli.py`), `web/hud.js`, `hoererZeichen` (`web/zug.js`).
- Erweitern: ein neuer Zustellweg kommt in `benachrichtigen`, nicht in die Seite.

### 10. GitLab-Review
Kommentare schreiben, „Review abschließen“, Urteil.
- Achsen: Senden (direkt veröffentlichen, nur Entwürfe), Urteil.
- Ort: `review.py` (`abschluss_planen`, `schritt_ausfuehren`, `URTEILE`, `urteil_senden`), Routen `api/kommentar`,
  `api/abschliessen`; `glab`/`ich` (`gitlab.py`).
- Erweitern: neue Art der Übertragung als weiterer `Schritt`.

### 11. Agent-Hinweise (drafts)
Review-JSON eines Agenten, an ihrer Zeile übernehmen oder verwerfen.
- Achsen: Marker-Feld, Prüf-Ergebnis, Zuordnung zum MR (`mr_fuer_hinweise`).
- Ort: `hinweise.py`, `agent_cli.py` (`pruefen`, `zeigen`, `kommentar`, `kommentare`), `hinweis_aktion` (`review.py`),
  Route `api/hinweis`. Format: `docs/agent-hinweise.md`.

### 12. GitLab-Diskussionen
Lesen, antworten, abwarten, erledigen.
- Ort: `review.py` (`diskussionen_abgleichen`, `antwort_senden`, `diskussion_aufloesen`), `diskussion_abgehakt`
  (`akte.py`), `fadenKnoepfe` (`web/review.js`).

### 13. GitLab nur auf Knopfdruck
Seiten fragen GitLab nie selbst; Abgleich des Klons mit dem GitLab-Stand.
- Achsen: Stand zu GitLab (`STAND_TEXT`), Klon.
- Ort: `gitlab.py` (`klon_suchen`, `mr_lokal`), `git.py` (`stand_zu_gitlab`, `branch_aktualisieren`, `branch_pushen`,
  `branch_auschecken`), `review.py` (`mr_gitlab_holen`, `mr_daten_holen`), `im_hintergrund` (`server.py`),
  Route `api/gitlab`, `web/bahnhof.js`.
- Erweitern: neue GitLab-Daten an einen bestehenden Holen-Knopf hängen, keinen Abruf beim Laden der Seite.

### 14. Zug und Güterbahnhof
- Achsen: Quelle, Marke am Wagen, Knopf im Leitstand.
- Ort: `quellen.py` (`alle_wagen`, `wagen_eintrag`, `faeden_marke`), `seite.py`, `web/zug.js`, `web/bahnhof.js`,
  `web/zeichnungen.js`; Spec: `docs/gueterbahnhof.md`.

### 15. „fertig“ / „abgeben“ (lokal)
- Ort: `fertig_moeglich` (`waggon.py`), Route `fertig` (`server.py`), `fertig`, `abgeben`, `runde_eintragen`
  (`quellen.py`), `teil_abgeben` (`abhaken.py`), `wip_name`, `diff_basis` (`git.py`).

### 16. Beobachten (Arbeitsstand live)
- Ort: `instanz.py`, `beobachter.py` (der Watcher gilt für jede lokale Seite: `repo_bewegt`), `web/beobachten.js`.
  Ideen: `docs/ideen.md`.

### 17. Stellwerk (HUD) und Meldungen
- Ort: `web/hud.js`, `web/toasts.js`, Route `api/hud`.
- Erweitern: neue Anzeigen ins HUD, Meldungen über `App.melden`, keine eigenen Banner.

### 18. Server und Prozess
- Ort: `server.py` (`@route`, `bearbeiten`), `prozess.py`.
- Bausteine: `server_sicherstellen` startet den Server ohne Browser (Aufrufe, nach denen der Nutzer gleich auf die
  Seite sieht: `server_wecken` in `agent thread`/`feedback`/`horchen`).
- Erweitern: neue Aktion der Seite = Route mit `waggon=`/`struktur=` (Struktur der Seite aus `anfrage.seite`); Akte nur
  über `akte_bearbeiten`/`aktion_ausfuehren`.

### 19. Kommandozeile
- Ort: `cli.py`, `agent_cli.py`, MR-Verweise in `gitlab.py` (`mr_ref`); `agent vorfall`: `vorfall_todo`,
  `vorfall_issue`, `vorfall_ablegen`. Doku für Agenten: `skill/merge-train/SKILL.md`.

### 20. Einstellungen und Installation
- Ort: `einstellungen.py`, `install.idem.sh`.
- Erweitern: neuer Schalter in `einstellungen.py` mit Standard, dazu Zeile in der README-Tabelle und in
  `config.example.toml`.

### 21. Tests (Mini-CI)
`./testen` wählt nach den geänderten Dateien aus; Einzelheiten oben in `testen`.
- Achsen: Auswahl (`--seit`, `--voll`, `--liste`, `--push`), Teil.
- Ort: `testen` (`MODUL_TEILE`), `TEILE` in `tests/test_gitlab.py` und `tests/test_ui.py`.
- Erweitern: neues Modul in `MODUL_TEILE`; neuer Teil in `TEILE`, `ALLE_TEILE` und `main()` von `test_gitlab.py`.
  Tests rufen nie das echte `todo`/`notify-send`.

## Stände der Listen (wer ist dran)

Gilt für jeden Eintrag mit Gesprächs- oder Sendestand: die Listen links, das Badge der Thread-Box, die Marke am Waggon.
Eine neue Liste, Eintragsart oder Quelle ordnet sich hier ein, statt eigene Zustände und Zeichen zu erfinden. Beide
Achsen berechnet der Server.

**`stand`: wer jetzt dran ist** (Klasse `s-<stand>`, Filter, Waggon „fertig“)

| id | Zeichen | Bedeutung |
|---|---|---|
| `entwurf` | orange ○ | von dir, noch nicht gesendet |
| `dran` | lila ● | du bist dran |
| `gitlab_entwurf` | orange ➜ | liegt als Entwurf in der Quelle, dort abschicken |
| `wartet` | blauer ○ | die anderen sind dran |
| `erledigt` | grüner ✓ | abgeschlossen |

**`wer`: wer zuletzt gehandelt hat**: `du` (`ich_symbol`), `agent` (🤖), `extern` (Logo der Quelle, `Quelle.logo`).

**Je Eintragsart** eine Funktion, die nur diese ids liefert: `faden_stand`, `diskussion_stand`, `kommentar_stand`,
`hinweis_stand` (`akte.py`). Waggon „fertig“: kein `entwurf`, `dran` oder `gitlab_entwurf` mehr.

**Ort**: `STAENDE`, `WER`, `diskussionen_stand` (`akte.py`); `App.STAENDE`, `App.werZeichen` (`web/review.js`);
`LISTEN_STATI`, `standZeichen` (`web/diff.js`); `extern_von` (`quellen.py`).
- Erweitern: neue Eintragsart = neue `*_stand`-Funktion; neue Quelle = ein `logo`; ein neuer Stand nur, wenn „wer ist
  dran“ ihn nicht ausdrücken kann.

## Querschnitt: Bausteine, die man wiederverwendet statt neu schreibt

| Bedarf | Baustein |
|---|---|
| Daten je Waggon speichern | Akte: `akte_bearbeiten`, `akte_lesen` (`akte.py`) |
| git aufrufen | `git()` (`git.py`) |
| Zeitstempel | `jetzt()` (`einstellungen.py`) |
| GitLab aufrufen | `gitlab.py`, nur auf Knopfdruck |
| Zeile zwischen Ständen zuordnen | `zeilen.py` |
| Code-Stelle verlinken | `pfad:zeile` im Text bzw. `see_also`, Popup aus `web/diff.js` |
| Liste links über den Dateien | `kommentarListe`, `kasten` (`web/diff.js`), neue Liste = Eintrag in `LISTEN_STATI` |
| Stand eines Eintrags anzeigen | `stand`/`wer` vom Server, `App.STAENDE`, `App.werZeichen` |
| Meldung an den Nutzer | `App.melden`, auf Python-Seite `Fehler` |
| Seite auf den neuen Stand bringen | `App.neuHolen` (Tausch je Datei), nie `location.reload` – das nur bei neuer Version |
| Langer Ablauf mit GitLab | planen und ausführen getrennt (`abschluss_planen`/`schritt_ausfuehren`) |
| Agent soll etwas tun | `Quelle.prompt` und `benachrichtigen` (`zuhoerer.py`) |
| Gemeinsames im JS | nur über `App`, Kopfkommentar „braucht/stellt bereit“ pflegen |
