# Funktionen von merge-train (Glossar für Agenten)

Wozu: Vor einer neuen Änderung hier nachsehen, ob es das Gesuchte als Funktion oder Baustein schon gibt. Wenn ja, dieses
erweitern (neue Variante, neuer Fall), statt daneben etwas Zweites zu bauen. Jede Funktion nennt ihre **Achsen** (wo
Varianten dazukommen) und ihren **Ort** im Code. Wie sie sich im Einzelnen verhält, steht im Docstring der genannten
Funktion, oben im Modul, im README und in `docs/`.

Beim Ändern mitpflegen: Eine neue Funktion bekommt hier einen Eintrag, eine neue Variante nur ein Wort in ihrer Achse.

## Grundbegriffe

- **Waggon**: ein Vergleich Quelle → Ziel in einem lokalen Klon (lokales Projekt, MR oder Lauf des Myrlings). Schlüssel für alles andere:
  Seite, Akte, Fäden, Zug. `waggon.py`
- **Quelle**: woher Waggons kommen. `quellen.py`
- **Akte**: die JSON-Datei je Waggon mit Kommentaren, Fäden und Hinweis-Status. `akte.py`
- **draft / staged / sent**: Stufen eines GitLab-Kommentars, siehe AGENTS.md.
- **Stand / wer**: wer bei einem Eintrag der Listen jetzt dran ist und wer zuletzt gehandelt hat, siehe
  [Stände der Listen](#stände-der-listen-wer-ist-dran).

## Funktionen

### 1. Mehrere Quellen für Waggons
Lokale Branches (`bis` gegen `von` in jedem Repo unter `projekte`), Läufe des Myrlings und GitLab-MRs, einzeln
abschaltbar, alle in einem Zug.
- Achsen: Quelle (lokal, Myrling, GitLab; geplant GitHub). Je Quelle (Basis `Quelle`): `an`, `ort`, `ziel`, `seite`,
  `branch`, `wagen`, `prompt`, `stand_kurz`/`zeilen_stand` (Kopf von feedback), `waggon_von`, dazu `titel` und `logo`
  (Datei in `web/`, Route `logo/<name>.svg`; Pflicht für jede Quelle mit Einträgen von außen). Je Waggon-Art (Basis
  `Art`): Kennung, Seite, Dateiname, Akten-Ordner, `kann`.
- Ort: `quellen.py` (`Lokal`, `Myrling`, `GitLab`, `quelle(waggon)`), `waggon.py` (`LokalArt`, `MyrlingArt`, `MrArt`
  in `ARTEN`, `Waggon.art`), `gitlab.py` (glab), `myrling.py` (Befehl des Myrlings, Vertrag oben im Modul), `cli.py`
  (MR-Verweise).
- Erweitern: eine neue Quelle ist eine Unterklasse von `Quelle` plus eine von `Art`, keine eigene Seite und keine
  `if lokal`-Ketten.
- von/bis eines lokalen Projekts nur über `von_bis(projekt)` (`waggon.py`). Fehlt ein Branch oder ein gemeinsamer
  Vorgänger: `stand_oder_fehlt` (`fehlende_zweige`, `ohne_basis`).
- Myrling: ein Waggon je Skript, das auf eine Prüfung wartet (`myrling_befehl`). Jede Datei steht gegen ihre eigene
  Basis: `lauf_ort` baut daraus einen Basis-Commit (`stand_mit`), damit Diff, Kontext und Fäden wie bei den anderen
  Quellen laufen. Die Liste holt `zug.js` im Hintergrund (`im_hintergrund_holen`). Begleitdateien aus anderen Repos
  („Fehlt im Diff“): siehe 7, `inhalt`. Attrappe: `tests/fake-nas-lauf`.
- Waggon-Karte („▾“ am lokalen Waggon): `projekt_einstellung`/`projekt_einstellen` (`quellen.py`), Route
  `api/projekt`, `karteOeffnen` (`web/zug.js`). Erweitern: weitere Projekt-Einstellungen dort und in der Akte.

### 2. Fähigkeiten je Waggon (`kann`)
`review` (Kommentare nach GitLab), `fertig` (Ziel-Branch setzen), `committen` (Agent darf umsetzen statt nur antworten).
- Achsen: Fähigkeit.
- Ort: `Art.kann` (`waggon.py`), in JS `App.kann`.
- Erweitern: Verhalten, das nur manche Waggons haben, als weitere Fähigkeit, nicht über `if lokal` an vielen Stellen.

### 3. Vergleichs-Modi (was gegen was)
lokal (`bis` gegen `von`, Standard `claude` → `reviewed`), Arbeitsstand (`bis = "arbeitsstand"`, auch nicht Committetes),
MR (Quell-Branch gegen den gemeinsamen Vorgänger mit dem Ziel), Myrling (jede Datei gegen ihre zuletzt angesehene
Fassung), Beobachten (siehe 16).
- Achsen: `von`/`bis` in der Einstellung, Quelle.
- Ort: `einstellungen.py` (`VON`, `BIS`, `ARBEITSSTAND`), `git.py` (`arbeitsstand`, `stand_mit`, `eigener_commit_env`),
  `Quelle.ort`.

### 4. Diff-Seite (gemeinsam für alle Quellen)
Diff immer aus dem lokalen Git (nie aus der GitLab-API), Syntaxfarben, geänderte Wörter, nebeneinander oder inline,
Dateiliste, Tasten (j/k, i, z, c), Kontext nachladen (auch dort kommentierbar), große und generierte Dateien erst auf
Klick.
- Datei abhaken (je Stand der Datei, daraus die Füllung des Waggons): `abhaken.py` (`abhaken`, `datei_staende`,
  `haken_weg`, `MINDEST`), Route `api/abgehakt`, `alle_wagen`, `App.wagenFuellen` (`zug.js`).
- Dateien filtern (abgehakte, je Endung): `dateienFiltern`, `ausgefiltert`, `App.aufdecken` (`web/navigation.js`).
  Erweitern: Gruppen (etwa FE/BE nach Endungen) als weitere Zeilen im Menü.
- Boxen (Kommentare, Hinweise, Fäden) unter ihrer Zeile: `einfuegen`, `feldMitnehmen` (`web/review.js`).
- Achsen: Dateiart (generiert/groß), Darstellung (nebeneinander/inline).
- Ort: `seite.py`, `diff_html.py`, `syntax.py`, `web/navigation.js`, `web/diff.js`; Routen `api/zeilen`, `api/datei`.

### 5. Ansichten eines Waggons
`alles` (Standard), `commit:<sha>` (nur lesen), `seit:<sha>` (rechts kommentierbar). Kommentare, Hinweise und Fäden
gehören zum ganzen Vergleich und werden in die Ansicht umgerechnet.
- Achsen: Ansicht.
- Ort: `ansichten.py`, `ansicht_zuordnen` (`review.py`), `nurLesen`/`seitAnsicht` in `web/diff.js`.
- Erweitern: eine neue Sicht auf denselben Vergleich (z. B. ohne main-Merges) ist eine weitere Ansicht.

### 6. Zeilen umrechnen (alt ↔ neu, Stand ↔ Stand)
Darauf beruhen: Fäden wandern nach neuen Commits mit, Kommentare in Commit-Ansichten, fremde GitLab-Diskussionen.
- Ort: `zeilen.py` (`alt_zeile`, `im_diff`, `zeile_vorwaerts`, `bereich_vorwaerts`, `bereich_anfang_vorwaerts`,
  `paare_und_hunks`).
- Erweitern: Jede neue „gehört diese Zeile noch hierher?“-Frage geht über diese Funktionen.

### 7. Code-Verweise und Popup
`pfad`, `pfad:zeile`, `pfad:von-bis`, Siehe-auch und Dateivergleiche (⇄) öffnen ein Popup: Diff der Datei, wenn sie im
Diff liegt, sonst den Inhalt. Zeilen der Agent-Hinweise werden von `reviewed_commit` auf den MR-Stand umgerechnet,
Änderungen im Bereich als `warnung` (⚠).
- Achsen: Verweisart (Zeile, Bereich, needle, Vergleich, Bereichsvergleich), Herkunft (Agent-Hinweis, Nachricht, Thread
  des Agenten), Stand (MR-Stand, `"ref"`/`@ref`: Zielbranch, Merge-Basis, beliebiger Ref – `stand_waehlen`, Ziel aus
  `refs["ziel"]` bzw. `Quelle.ziel`), Repo (Hauptrepo, Submodul).
- Dateien aus einem anderen Stand oder Submodul: `inhalt` (`submodul_stelle`), `fehlt_grund` (`git.py`). Erweitern:
  Begleitdateien eines Myrling-Laufs aus einem Repo, das kein Submodul ist, hier anschließen statt daneben bauen.
- Ort: `ort_lesen`, `ort_mitziehen`, `see_also_aufloesen`, `stand_waehlen`, `needle_anderswo` (`hinweise.py`),
  `code_links` (`gespraech.py`), `vergleich_daten`, `zeilen_daten` (`review.py`, beide mit anderem Stand),
  `popup`/`sieheAuch`/`ortLink`/`vergleich` in `web/diff.js`; Routen `api/zeilen` (`sha`), `api/vergleich` (`b_sha`).

### 8. Gespräch mit Agenten (Fäden an Zeilen)
Fragen und Wünsche an einer Zeile, einem Bereich, einem GitLab-Kommentar oder allgemein; erst Entwurf, dann „senden“.
Der Agent holt ab, antwortet und legt eigene Threads an (mit Siehe-auch und Vergleich). Fäden gehören zum Branch.
- Modi: lokal (Agent darf umsetzen) und MR (privat, nie nach GitLab, nur antworten). Claude ist immer fragbar
  (`gespraech_agenten`), weitere Agenten über `[agenten]`.
- Ort eines Fadens: Bereich ab–b (`bereich_anfang_vorwaerts`, `bereichMarkieren` in `web/review.js`); GitLab-Kommentar
  (`zu` = `k:<id>` | `h:<key>`: `faden_zu`, `faden_ziel`, `faden_nach_kommentar`; `angehaengt`, `zuSchluessel`).
- Wer schreibt: `agent_name` (`agent_cli.py`, Umgebung `AGENT_UMGEBUNG`, sonst `VORSTELLEN`). Neue Harnesses dort.
- Einstieg des Agenten: `merge-train status` (`status_ausgeben`): Entwicklung oder Review (`review_ziel`,
  `eigener_mr`, `status_review`); ganz oben, was an der Einrichtung nicht stimmt (`einrichtung_teile`: `konfig_maengel`,
  `fehlende_zweige`, `fehlende_hooks`/`HOOKS`). Erweitern: eine neue Prüfung ist eine Zeile in `einrichtung_teile`.
  `thread` und `antworten` nehmen `--siehe`/`--vergleich` (`siehe_eintrag`); Faden-Zeilen: `faden_zeile`.
- Achsen: Quelle (über `kann.committen` und `Quelle.prompt`), Agent, Faden-Aktion, Ort (Zeile, Bereich,
  GitLab-Kommentar, allgemein).
- Befehlsübersicht für Agenten: `completions/merge-train.fish` (eine Zeile je Befehl, der Skill verweist darauf).
- Ort: `gespraech.py`, `agent_cli.py` (`status`, `feedback`, `antworten`, `thread`), Route `api/gespraech`, `web/review.js`.

### 9. Wer hört zu / Agent benachrichtigen
Eine Session wartet mit `agent horchen`; sonst startet „senden“ einen Befehl (`[agenten]`, `feedback_befehl`) oder legt
einen todo-Eintrag an (`zustellweg`). HUD und Waggondach zeigen, wer zuhört, was er tut und den Kontext-Füllstand.
„📨“ zeigt, was zuletzt beim Agenten ankam, auf Wunsch vor dem Senden eine Vorschau. Zuhören kann still enden
(`horchen_still`).
- Achsen: Zustellweg (horchen, todo, eigener Befehl), Agent, Tätigkeit (hoert, arbeitet), Prompt (vorher, zuletzt),
  Ende (Nachricht, Session weg, Zeit, still).
- Ort: `zuhoerer.py` (`zuhoerer`, `horcht`, `agent_sitzung`, `transcript_stand`, `zustellweg`, `benachrichtigen`,
  `prompt_merken`, `prompt_vorschau`, `zuhoerer_abmelden`), `entwuerfe_senden` (`akte.py`), `agent_cli.py` (`horchen`,
  `faeden_abholen`, Ziele aus `alle_gespraeche(leere=True)`), Route `api/gespraech` (`vorschau`, `prompt`,
  `abmelden`), `web/hud.js`, `web/zug.js` (`hoererZeichen`), `promptDialog` (`web/review.js`).
- Erweitern: ein neuer Zustellweg kommt in `benachrichtigen`/`feedback_senden`, nicht in die Seite.

### 10. GitLab-Review
Eigene Kommentare an Zeilen oder allgemein, bearbeiten, löschen, Reihenfolge. „Review abschließen“ gleicht mit
GitLab ab (Draft-Notes anlegen, aktualisieren, löschen, ohne Duplikate), veröffentlicht sie auf Wunsch gleich
(`draft_notes/bulk_publish`, danach `mr_gitlab_holen`) und setzt zuletzt das Urteil (genehmigen, ändern lassen).
- Achsen: Senden (direkt veröffentlichen, nur Entwürfe); Urteil (kommentieren, genehmigen, ändern lassen).
- Ort: `review.py` (planen: `abschluss_planen`, ausführen: `schritt_ausfuehren`, `URTEILE`/`urteil_senden`), Routen
  `api/kommentar`, `api/abschliessen`.
- Erweitern: neue Arten von Übertragung als weiterer `Schritt`, nicht als eigener Ablauf.

### 11. Agent-Hinweise (drafts)
Ein Review-Agent schreibt `tasks/<KEY>-review-markers.json`; merge-train zeigt die Einträge an ihrer Zeile (needle,
`=`, `line`). Übernehmen, anpassen & übernehmen, verwerfen. `agent pruefen` (auch `--seit`), `agent zeigen`,
`agent kommentar` (draft ändern bzw. neuen daneben), `agent kommentare` (lesen, `kommentare_teile`).
- Wer: Feld `agent` der JSON bzw. des Markers, sonst Akte `hinweis_agenten`; geht beim Übernehmen in den Kommentar mit.
- Achsen: Marker-Feld, Prüf-Ergebnis, Zuordnung zum MR (`mr_fuer_hinweise`).
- Ort: `hinweise.py`, `agent_cli.py`, `hinweis_aktion` (`review.py`), Route `api/hinweis`. Format: `docs/agent-hinweise.md`.

### 12. GitLab-Diskussionen lesen und beantworten
Antworten und Erledigt-Status an eigenen Kommentaren, fremde Diskussionen lesend an der Zeile und in einer Liste.
Antworten sofort oder als lokaler Entwurf, „☑ abwarten“ (Ball ohne Antwort abgeben, nur in der Akte), „✓ erledigt“
gleich in GitLab. Stand: `diskussion_stand`.
- Ort: `diskussionen_abgleichen`, `antwort_entwurf`, `antwort_senden`, `diskussion_abhaken`, `diskussion_aufloesen`,
  `diskussion_kopien` (`review.py`), `diskussion_abgehakt` (`akte.py`), `fadenKnoepfe`/`fadenErledigen`/`GITLAB_AKTIONEN`
  (`web/review.js`).
- Liste links: siehe Baustein „Liste links über den Dateien“.

### 13. GitLab nur auf Knopfdruck (Cache)
Seiten fragen GitLab nie selbst. Geholt wird nur über die Knöpfe im Güterbahnhof („↻ MRs“, „↻ MR-Daten“), beim
Abschließen und von `agent pruefen|zeigen` bzw. `merge-train <MR>`. Weicht der Klon vom GitLab-Stand ab, bietet die
Seite den passenden Knopf an (aktualisieren, pushen, force-push mit Lease). Beim ersten Besuch checkt merge-train den
Quell-Branch im Klon aus, wenn der Stand sauber ist.
- Achsen: Stand zu GitLab (`STAND_TEXT`), Klon (`[repos]`, Akte `klon`, `klon_ordner`).
- Ort: `gitlab.py` (`lokale_klone`, `klon_suchen`, `mr_lokal`), `stand_zu_gitlab`, `branch_aktualisieren`,
  `branch_pushen`, `branch_auschecken` (`git.py`), `STAND_KNOPF`/`stand_html` (`seite.py`), `branch_aktion`,
  `im_hintergrund` (`server.py`), `mr_gitlab_holen`/`mr_daten_holen`/`mr_auschecken` (`review.py`), Route
  `api/gitlab`, `api/stand` (`seite`, `meldung`), `neuLaden` (`web/review.js`), `web/bahnhof.js`.
- Erweitern: neue GitLab-Daten an einen bestehenden Holen-Knopf hängen, keinen eigenen Abruf beim Laden der Seite.

### 14. Zug und Güterbahnhof
Kopf jeder Seite: ein Wagen je Waggon (aus allen Quellen), Füllstand, Marken („💬 n neu“, „● n dran“), Wechsel per
Klick oder n/Enter, „fertig ✓“ für lokale Waggons, Abfahrt. Leitstand-Knöpfe je Quelle. Welche MRs: `mr_liste`.
- Achsen: Quelle, Marke am Wagen, Knopf im Leitstand.
- Ort: `alle_wagen`/`wagen_fuer`, `wagen_eintrag`, `faeden_marke`, `faeden_text` (`quellen.py`), `seite.py`,
  `web/zug.js`, `web/bahnhof.js`, `web/zeichnungen.js`; Spec und Ausbauschritte: `docs/gueterbahnhof.md`.

### 15. „fertig“ / „abgeben“ (lokal)
„fertig“ setzt `von` auf den gesehenen Stand (`git push .`: nur Fast-Forward, der pre-push-Hook des Repos läuft) und
räumt erledigte Fäden weg. Ist erst ein Teil der Dateien abgehakt, gibt „abgeben“ diese als Commit auf den Teilstand
`<von>-wip` ab, ohne Arbeitsverzeichnis, Index oder HEAD anzufassen; der Diff läuft danach ab dem Teilstand.
- Ort: `fertig_moeglich` (`waggon.py`), Route `fertig` (`server.py`, `teil` = abgeben), `fertig`, `abgeben`,
  `abgabe_pruefen`, `runde_eintragen` (`quellen.py`), `teil_abgeben` (`abhaken.py`), `wip_name`, `wip_sha`,
  `diff_basis` (`git.py`, auch für `statistik` und `projekt_seite`).

### 16. Beobachten (Arbeitsstand live)
`merge-train --beobachten [ordner] [--von REF]`: eigene Instanz mit eigenem Port und Daten, inotify, lädt bei
echter Änderung neu, rahmt Neues ein, endet beim Schließen des Tabs. `agent …` aus dem Repo landet bei der Instanz.
- Ort: `instanz.py` (Kommandozeile), `beobachter.py` (Server), `web/beobachten.js`, Route `api/neu`.
- Ideen zum Ausbau: `docs/ideen.md`.

### 17. Stellwerk (HUD) und Meldungen
LED für den Server, Stand von merge-train, Zähler, ✎ bei einem offenen Eingabefeld (`hudFeld`), wer zuhört,
Kontext-Füllstand; Toasts und 🔔 mit den letzten 50. Auch auf der Startseite (ohne Zähler und 🔔).
- Ort: `web/hud.js`, `web/toasts.js`, `kontext` (`zuhoerer.py`), Route `api/hud`.
- Erweitern: neue Statusanzeigen ins HUD, neue Meldungen über `App.melden`, keine eigenen Banner.

### 18. Server und Prozess
Kleiner Server auf `127.0.0.1:8771`, Routen-Tabelle mit gemeinsamer Fehler- und Waggon-Behandlung, Seite fragt alle
4 s nach, Neustart bei neuem Stand von Skript oder Einstellung, Ende nach Leerlauf oder `--stopp`.
- Ort: `server.py` (`@route`, `bearbeiten`), `prozess.py`.
- Erweitern: eine neue Aktion der Seite ist eine Route mit `waggon=`/`struktur=`; Änderungen an der Akte nur über
  `akte_bearbeiten`/`aktion_ausfuehren`.

### 19. Kommandozeile
`merge-train [projekt | MR-Verweis | --mrs | --stopp | --beobachten]`, `merge-train status` (= `agent status`) und
`merge-train agent …` (`status`, `pruefen`, `zeigen`, `feedback`, `antworten`, `horchen`, `kommentar`, `kommentare`,
`thread`, `vorfall`). MR-Verweise: URL, `!42`, `gruppe/projekt!42`.
- `agent vorfall` nimmt den ersten Weg, der klappt: `vorfall_todo` (`eigener_klon`), `vorfall_issue`
  (`vorfall_github`), `vorfall_ablegen` (`vorfall_ordner`); Ablauf: `docs/vorfaelle/README.md`.
- Ort: `cli.py`, `agent_cli.py`, MR-Verweise in `gitlab.py` (`mr_ref`, `ist_mr_ref`). Agenten-Doku:
  `skill/merge-train/SKILL.md`.

### 20. Einstellungen und Installation
`~/.config/merge-train/config.toml` (Vorlage `config.example.toml`), Ersatzparser ohne `tomllib`, Log der
Anfragen an git und GitLab (`log_tage`). Installation: README, Abschnitt „Installation“.
- Ort: `einstellungen.py`, `install.idem.sh`.
- Erweitern: neue Schalter in `einstellungen.py` mit Standard, dazu Zeile in der README-Tabelle und in
  `config.example.toml`.

### 21. Tests (Mini-CI)
`./testen` wählt nach den geänderten Dateien aus (pre-commit; `--push` als pre-push, `--voll` im Takt `voll_faellig`
und für jeden noch nicht voll getesteten Stand, Merkzettel `.git/merge-train-getestet`; Einzelheiten oben in `testen`).
Teile: `./pruefen` (JS/CSS), Smoke, Klassen von `tests/test_einheiten.py`, Teile von `tests/test_gitlab.py`, nur mit
`--voll` die UI-Tests `tests/test_ui.py` (headless Chromium, `Pipe` aus `perf/cdp_messung.py`, Server und Test-Repo aus
`werkzeug/seiten_vergleich.py`).
- Achsen: Auswahl (Diff gegen HEAD, `--seit`, `--voll`, `--liste`, `--push`).
- Ort: `testen`, `MODUL_TEILE` darin, `TEILE` in `tests/test_gitlab.py` und `tests/test_ui.py`.
- Erweitern: neues Modul in `MODUL_TEILE` eintragen (fehlt es, laufen alle Teile); neuer Teil in `TEILE`, `ALLE_TEILE`
  und `main()` von `test_gitlab.py`. Tests rufen nie das echte `todo`/`notify-send` (Ersatz in `bin/` des Testordners).

## Stände der Listen (wer ist dran)

Gilt für jeden Eintrag, der einen Gesprächs- oder Sendestand hat: die drei Listen links („GitLab-Kommentare“,
„GitLab-Diskussionen“, „KI-Threads“), das Badge der Thread-Box, die Marke am Waggon. Eine neue Liste, Eintragsart oder
Quelle (z. B. GitHub) ordnet sich hier ein, statt eigene Zustände und Zeichen zu erfinden.

Jeder Eintrag hat zwei Achsen, beide vom Server berechnet:

**`stand`: wer jetzt dran ist.** Bestimmt Zeichen und Farbe (Klasse `s-<stand>`), Filter, Waggon „fertig“.

| id | Zeichen | Bedeutung |
|---|---|---|
| `entwurf` | orange ○ | von dir, noch nicht gesendet |
| `dran` | lila ● | du bist dran: dir wurde etwas hingelegt (Antwort, Hinweis, neue Nachricht) |
| `gitlab_entwurf` | orange ➜ | liegt als Entwurf in der Quelle, dort abschicken (nur ohne „direkt veröffentlichen“) |
| `wartet` | blauer ○ | die anderen sind dran |
| `erledigt` | grüner ✓ | abgeschlossen (nur dann wird die Thread-Box grau) |

**`wer`: wer zuletzt gehandelt hat.** Das Symbol links vom Stand.

| id | Symbol | Bedeutung |
|---|---|---|
| `du` | Einstellung `ich_symbol` (Standard 🤓) | du |
| `agent` | 🤖 | ein Agent (Claude-Antwort, Agent-Hinweis, Thread mit `--erledigt` geschlossen) |
| `extern` | Logo der Quelle (`Quelle.logo`) | von außen aus der Quelle; ob ein Mensch schrieb, weiß man nicht sicher |

**Gültige Kombinationen**

| Eintrag | entwurf | dran | gitlab_entwurf | wartet | erledigt |
|---|---|---|---|---|---|
| KI-Thread (`faden_stand`) | du: Frage nicht gesendet | agent: hat geantwortet bzw. Thread eröffnet | – | du: gesendet | du / agent |
| GitLab-Diskussion (`diskussion_stand`) | du: Antwort lokal | extern: zuletzt geschrieben | du: Antwort als Entwurf in GitLab | du: zuletzt geschrieben oder „☑ abwarten“ | du / extern: in GitLab aufgelöst |
| Review-Kommentar (`kommentar_stand`) | du: neu oder geändert | – | du: Draft-Note in GitLab | du: veröffentlicht, bis „MR-Daten“ ihn als Diskussion holt | – |
| Agent-Hinweis (`hinweis_stand`) | – | agent: noch nicht übernommen | – | – | du: übernommen/verworfen (nicht in der Liste) |

**Regeln**
- Vorrang bei einer Diskussion: eigener Entwurf (lokal, dann in GitLab) vor erledigt, vor wartet, vor dran.
- Aus `dran` kommt man durch Antworten, „☑ abwarten“ (Ball ohne Antwort abgeben) oder Erledigen. Schreibt danach
  jemand von außen, ist man wieder `dran`.
- Waggon „fertig“ (grüner Rahmen): kein `entwurf`, kein `dran`, kein `gitlab_entwurf` mehr. `wartet` hält nicht auf.
  Die Marke „● n dran“ zählt die Diskussionen, in denen du dran bist.
- Klick auf das Zeichen in der Liste nur, wo es eine Aktion gibt: erledigen (KI-Thread lokal, lösbare Diskussion gleich
  in GitLab), nicht lösbare Diskussion in `dran` abwarten.
- Filterknöpfe je Liste nur für die Stände, die dort vorkommen können (`LISTEN_STATI`), auch bei 0.

**Ort**: `STAENDE`, `WER`, `faden_stand`, `diskussion_stand`, `kommentar_stand`, `hinweis_stand`, `diskussionen_stand`
(Zählung für den Waggon) in `akte.py`; Zeichen und Texte `App.STAENDE`, `App.werZeichen` (`web/review.js`); Listen
`LISTEN_STATI`, `standZeichen`, `standKnopf` (`web/diff.js`); Quelle-Logo `extern_von` (`quellen.py`).
- Erweitern: eine neue Eintragsart bekommt eine `*_stand`-Funktion in `akte.py`, die nur diese ids liefert; eine neue
  Quelle ein `logo`. Ein neuer Stand nur, wenn „wer ist dran“ ihn nicht ausdrücken kann.

## Querschnitt: Bausteine, die man wiederverwendet statt neu schreibt

| Bedarf | Baustein |
|---|---|
| Daten je Waggon speichern | Akte: `akte_bearbeiten`, `akte_lesen` (`akte.py`) |
| git aufrufen | `git()` (`git.py`), protokolliert mit Anlass |
| Zeitstempel | `jetzt()` (`einstellungen.py`), `jetzt(zone=True)` neben Zeiten aus GitLab |
| GitLab aufrufen | `gitlab.py` (glab), nur auf Knopfdruck |
| Zeile zwischen Ständen zuordnen | `zeilen.py` |
| Code-Stelle verlinken | `pfad:zeile` im Text bzw. `see_also`, Popup aus `web/diff.js` |
| Liste links über den Dateien | `kommentarListe`, `kasten` (`web/diff.js`); Stände nach [Stände der Listen](#stände-der-listen-wer-ist-dran), je Liste in `LISTEN_STATI`, Filter je Waggon im Browser (`ausgeblendet`). Neue Liste = neuer Eintrag in `LISTEN_STATI` |
| Stand eines Eintrags anzeigen | `stand`/`wer` vom Server, `App.STAENDE`, `App.werZeichen` – nie eigene Zustände |
| Meldung an den Nutzer | `App.melden` (Toasts), auf Python-Seite `Fehler` |
| Langer Ablauf mit GitLab | planen und ausführen getrennt (wie `abschluss_planen`/`schritt_ausfuehren`) |
| Agent soll etwas tun | `Quelle.prompt` und `benachrichtigen` (`zuhoerer.py`) |
| Gemeinsames im JS | nur über `App`, Kopfkommentar „braucht/stellt bereit“ pflegen |
