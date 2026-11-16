# Funktionen von merge-train (Glossar für Agenten)

Wozu: Vor einer neuen Änderung hier nachsehen, ob es das Gesuchte als Funktion oder Baustein schon gibt. Wenn ja, dieses
erweitern (neue Variante, neuer Fall), statt daneben etwas Zweites zu bauen. Jede Funktion nennt ihre **Achsen** (wo
Varianten dazukommen) und ihren **Ort** im Code. Einzelheiten stehen im README, in `docs/` und oben in jedem Modul.

Beim Ändern mitpflegen: Eine neue Funktion bekommt hier einen Eintrag, eine neue Variante nur ein Wort in ihrer Achse.

## Grundbegriffe

- **Waggon**: ein Vergleich Quelle → Ziel in einem lokalen Klon (lokales Projekt oder MR). Schlüssel für alles andere:
  Seite, Akte, Fäden, Zug. `waggon.py`
- **Quelle**: woher Waggons kommen. `quellen.py`
- **Akte**: die JSON-Datei je Waggon mit Kommentaren, Fäden und Hinweis-Status. `akte.py`
- **draft / staged / sent**: Stufen eines GitLab-Kommentars, siehe AGENTS.md.
- **Stand / wer**: wer bei einem Eintrag der Listen jetzt dran ist und wer zuletzt gehandelt hat, siehe
  [Stände der Listen](#stände-der-listen-wer-ist-dran).

## Funktionen

### 1. Mehrere Quellen für Waggons
Lokale Branches (`bis` gegen `von` in jedem Repo unter `projekte`) und GitLab-MRs. Einzeln an- und abschaltbar, beide
zusammen in einem Zug.
- Achsen: Quelle (lokal, GitLab; geplant GitHub). Je Quelle: `an`, `ort`, `seite`, `branch`, `wagen`, `prompt`, dazu
  `titel` und `logo` (Datei in `web/`, Route `logo/<name>.svg`): das Symbol für „wer = extern“, Pflicht für jede
  Quelle mit Einträgen von außen.
- Ort: `quellen.py` (Klassen `Lokal`, `GitLab`), `gitlab.py` (glab), `cli.py` (MR-Verweise).
- Erweitern: eine neue Quelle ist eine neue Klasse in `quellen.py` plus eine Waggon-Art, keine eigene Seite.
- von/bis eines lokalen Projekts nur über `von_bis(projekt)` (`waggon.py`): auf der Seite gewählt (Akte `zweige`) vor
  `[zweige.<projekt>]` vor `von`/`bis`. Fehlt ein Branch: `fehlende_zweige` (`git.py`), Waggon „⚠ fehlt“
  (`stand_oder_fehlt`), nur für ausdrücklich gemeinte Repos (`finde_repos(alle=True)`).
- Waggon-Karte („▾“ am lokalen Waggon): Projektinfos, von/bis wählen. `projekt_einstellung`/`projekt_einstellen`
  (`quellen.py`), Route `api/projekt`, `karteOeffnen` in `web/zug.js`. Erweitern: weitere Projekt-Einstellungen dort
  und in der Akte, keine eigene Seite.

### 2. Fähigkeiten je Waggon (`kann`)
Was ein Waggon darf, bestimmt seine Quelle: `review` (Kommentare nach GitLab), `fertig` (Ziel-Branch setzen),
`committen` (Agent darf umsetzen statt nur antworten).
- Achsen: Fähigkeit.
- Ort: `Waggon.kann` (`waggon.py`), in JS `App.kann`.
- Erweitern: Neues Verhalten, das nur manche Waggons haben, als weitere Fähigkeit hier eintragen, nicht über
  `if lokal` an vielen Stellen.

### 3. Vergleichs-Modi (was gegen was)
- lokal: Branch `bis` gegen `von` (Standard `claude` → `reviewed`)
- Arbeitsstand: `bis = "arbeitsstand"`, auch nicht Committetes, ohne Index oder Branch anzufassen
- MR: Quell-Branch gegen den gemeinsamen Vorgänger mit dem Ziel-Branch
- Beobachten: eigene Instanz je Repo/Worktree, live (siehe 16)
- Achsen: `von`/`bis` in der Einstellung, Quelle.
- Ort: `einstellungen.py` (`VON`, `BIS`, `ARBEITSSTAND`), `git.py` (`arbeitsstand`), `Quelle.ort`.

### 4. Diff-Seite (gemeinsam für alle Quellen)
Eine Seite für jeden Waggon: Diff immer aus dem lokalen Git (nie aus der GitLab-API), Syntaxfarben, geänderte Wörter
hervorgehoben, nebeneinander oder inline, Dateiliste, Tasten (j/k, i, z, c), Datei abhaken.
- Datei abhaken: ☐ im Dateikopf, klappt zu und streicht in der Liste durch. Der Haken gilt je Stand der Datei
  (Blob in bis), ein neuer Stand nimmt ihn weg. Gespeichert in der Akte (`abgehakt`), daraus die Füllung des
  Waggons (`fuellung`: Zeilen der abgehakten Dateien / alle, je Datei mindestens `MINDEST`), im Zug als Schüttgut im
  Kasten. „fertig“ und „abgeben“ (Abschnitt 15) räumen die Haken weg.
  Ort: `abhaken.py` (`abhaken`, `datei_staende`, `haken_weg`), Route `api/abgehakt` (GET beim Laden, POST je
  Haken), `web/diff.js`, `alle_wagen` (Füllung je Waggon), `App.wagenFuellen` (`zug.js`).
- Dateien filtern: im Titel der Dateiliste das Häkchen „abgehakte“ (eingeblendet klappen sie auf) und das Klappmenü
  „Filter ▾“ mit einem Häkchen je Endung (mit Anzahl); Ausgefiltertes verschwindet aus Liste und Diff (`ausgefiltert`),
  je Waggon im Browser (`filter:dateien:<id>`); j/k und die
  aktive Datei überspringen Ausgefiltertes, ein Sprung zu einer ausgefilterten Datei zeigt sie (`App.aufdecken`).
  Ort: `dateienFiltern` (`web/navigation.js`), nach dem Abhaken aus `hakenSetzen` (`web/diff.js`).
  Erweitern: Gruppen (etwa FE/BE nach Endungen) als weitere Zeilen im Menü.
- Kontext zwischen Hunks nachladen (▼ 20 / ▲ 20 / alle), auch dort kommentierbar.
- Boxen (Kommentare, Hinweise, Fäden) unter ihrer Zeile: inline über die ganze Breite, nebeneinander auf der Seite ihres
  Orts (neue Zeile rechts, nur alte links), `einfuegen` (`web/review.js`). Eine Box mit offenem Eingabefeld zeichnet
  `zeichnen` nicht neu; `feldMitnehmen` verschiebt sie beim Umschalten (i) samt Text in die sichtbare Tabelle. Neue,
  leere Felder gehen bei einem Klick außerhalb ihres Rahmens zu.
- Große und generierte Dateien erst auf Klick, automatisch, wenn ein Kommentar darin liegt.
- Achsen: Dateiart (generiert/groß), Darstellung (nebeneinander/inline).
- Ort: `seite.py`, `diff_html.py`, `syntax.py`, `web/navigation.js`, `web/diff.js`; Routen `api/zeilen`, `api/datei`.

### 5. Ansichten eines Waggons
`alles` (Standard), `commit:<sha>` (nur dieser Commit, nur lesen), `seit:<sha>` (alles seit dem Commit, rechts
kommentierbar). Kommentare, Hinweise und Fäden gehören immer zum ganzen Vergleich und werden in die Ansicht
umgerechnet; wo das nicht geht, stehen sie unter dem Dateinamen mit Grund.
- Achsen: Ansicht.
- Ort: `ansichten.py`, `ansicht_zuordnen` (`review.py`), `nurLesen`/`seitAnsicht` in `web/diff.js`.
- Erweitern: eine neue Sicht auf denselben Vergleich (z. B. ohne main-Merges) ist eine weitere Ansicht.

### 6. Zeilen umrechnen (alt ↔ neu, Stand ↔ Stand)
Ordnet Zeilen zwischen alter und neuer Seite eines Diffs und zwischen zwei Ständen zu. Darauf beruhen: Fäden wandern
nach neuen Commits mit, Kommentare in Commit-Ansichten, fremde GitLab-Diskussionen auf dem Stand der Seite.
- Ort: `zeilen.py` (`alt_zeile`, `im_diff`, `zeile_vorwaerts`, `bereich_vorwaerts`, `paare_und_hunks`).
- Erweitern: Jede neue „gehört diese Zeile noch hierher?“-Frage geht über diese Funktionen.

### 7. Code-Verweise und Popup
`pfad`, `pfad:zeile`, `pfad:von-bis`, Siehe-auch-Einträge und Dateivergleiche (⇄) öffnen ein Popup: Diff der Datei,
wenn sie im Diff liegt, sonst den Inhalt. Dateivergleich zeigt zwei Dateien nebeneinander, ganz oder je einen Bereich.
Zeilenangaben der Agent-Hinweise werden von `reviewed_commit` auf den MR-Stand umgerechnet, Änderungen im Bereich als
`warnung` (⚠) gemeldet.
- Achsen: Verweisart (Zeile, Bereich, needle, Vergleich, Bereichsvergleich), Herkunft (Agent-Hinweis, Nachricht, Thread
  des Agenten).
- Ort: `ort_lesen`, `ort_mitziehen`, `see_also_aufloesen` (`hinweise.py`), `code_links` (`gespraech.py`),
  `vergleich_daten` (`review.py`), `popup`/`sieheAuch`/`ortLink`/`vergleich` in `web/diff.js`; Route `api/vergleich`.

### 8. Gespräch mit Agenten (Fäden an Zeilen)
Fragen und Wünsche an einer Zeile oder allgemein; erst Entwurf, dann „senden“; Antworten, erledigen, wieder öffnen.
Agent holt ab, antwortet und legt eigene Threads an (mit Siehe-auch und Vergleich).
- Modi: lokal (Agent darf umsetzen und committen bzw. im Arbeitsstand ändern) und MR (privat, nie nach GitLab, nur
  antworten). Claude ist immer fragbar (auch im MR ohne Zuhörer, `gespraech_agenten`), weitere Agenten (Copilot …) über `[agenten]`.
- Fäden gehören zum Branch; andere Branches nur lesend einblendbar.
- Ort eines Fadens: eine Zeile oder ein Bereich ab–b der neuen Seite (Umschalt-Klick, `thread --ort pfad:von-bis`); der
  Anfang wandert mit `bereich_anfang_vorwaerts` (`zeilen.py`) mit, markiert von `bereichMarkieren` (`web/review.js`).
- Ort eines Fadens auch: ein GitLab-Kommentar (`zu` = `k:<id>` | `h:<key>`, „💬 an Agent“ an Kommentar/Hinweis): der
  Faden steht in dessen Box (`angehaengt`, `zuSchluessel` in `web/review.js`), Ort aus `faden_zu` (`gespraech.py`);
  `feedback` zeigt den Kommentar als Ziel (`faden_ziel`), `agent kommentar <Faden-id>` ändert ihn und erledigt den Faden
  (`faden_nach_kommentar`, `agent_cli.py`).
- Wer schreibt: `agent_name` (`agent_cli.py`): `--als`, `MERGE_TRAIN_AGENT`, erkannt aus der Umgebung (`AI_AGENT`,
  `AGENT_UMGEBUNG`), sonst Fehler (`VORSTELLEN`). Neue Harnesses dort eintragen.
- Achsen: Quelle (über `kann.committen` und `Quelle.prompt`), Agent, Faden-Aktion, Ort (Zeile, Bereich, GitLab-Kommentar, allgemein).
- Ort: `gespraech.py`, `agent_cli.py` (`feedback`, `antworten`, `thread`), Route `api/gespraech`, `web/review.js`.

### 9. Wer hört zu / Agent benachrichtigen
Eine Session wartet mit `agent horchen`; sonst startet „senden“ einen Befehl: `todo`-Eintrag, `feedback_befehl` oder
der Startbefehl aus `[agenten]`. Zeigt im HUD, wer horcht (`horcht`), auf dem Waggondach, wer zuhört und was er tut (`zuhoerer`:
hoert, arbeitet = letzte Nachricht im Transcript ist keine fertige Antwort; wartet sie im Terminal, nichts), und den
Kontext-Füllstand der Claude-Session (Fenster 1M, sobald sie je über 200k lag; beides aus `transcript_stand`).
Die Emojis wechselt ein Takt in `zug.js` (`hoererZeichen`), der Zug fragt `api/zuhoerer` alle 5 s.
Welchen Weg „senden“ nimmt, entscheidet `zustellweg`. Was beim Agenten ankam (Ausgabe von horchen/feedback,
Startprompt), merkt sich `prompt_merken` in `<akte>.prompt` (die letzten 5, nicht in der Akte). „📨“ zeigt das, mit
„vor dem Senden zeigen“ (`localStorage.promptVorher`) zeigt „senden“ erst `prompt_vorschau` (horchen: `faeden_abholen`
mit `vorschau`, Entwürfe als gesendet, nichts gespeichert; davor der Startprompt, wenn „senden“ startet oder ein todo
anlegt) – auch ohne Agent. „📨“ zeigt davor, was gesendet, aber noch nicht abgeholt ist. Dialog: `promptDialog`
(`web/review.js`).
- Achsen: Zustellweg (horchen, todo, eigener Befehl), Agent, Tätigkeit (hoert, arbeitet), Prompt (vorher, zuletzt).
- Ort: `zuhoerer.py` (`zuhoerer`, `agent_sitzung`, `zustellweg`, `prompt_merken`), `agent_cli.py` (`horchen`),
  Route `api/gespraech` (`vorschau`, `prompt`), `web/hud.js`, `web/zug.js`, `web/review.js`.
- Erweitern: ein neuer Zustellweg kommt in `benachrichtigen`/`feedback_senden`, nicht in die Seite.

### 10. GitLab-Review
Eigene Kommentare an Zeilen oder allgemein, bearbeiten, löschen, Reihenfolge (sortieren, ⤒/⤓). „Review abschließen“
gleicht mit GitLab ab und legt Draft-Notes an, aktualisiert oder löscht sie, ohne Duplikate. Mit „☑ direkt
veröffentlichen“ (Standard, im Browser gemerkt) danach `draft_notes/bulk_publish` und gleich `mr_gitlab_holen`: die
Kommentare stehen dann als Diskussionen da. Ohne: sie bleiben Entwürfe in GitLab (Stand `gitlab_entwurf`). Zeilen
außerhalb des Diffs: erst Zeilen-Kommentar, sonst allgemeiner mit Link. Zuletzt setzt das Urteil (Split-Knopf „▾“,
`URTEILE`/`urteil_senden`) „genehmigen“ (REST `approve`) bzw. „ändern lassen“ (GraphQL `mergeRequestRequestChanges`);
mit Urteil geht Abschließen auch ohne Kommentare, das Urteil gilt nur für ein Abschließen.
- Achsen: Senden (direkt veröffentlichen, nur Entwürfe); Urteil (kommentieren, genehmigen, ändern lassen).
- Ort: `review.py` (planen: `abschluss_planen`, ausführen: `schritt_ausfuehren`), Routen `api/kommentar`,
  `api/abschliessen`.
- Erweitern: neue Arten von Übertragung als weiterer `Schritt`, nicht als eigener Ablauf.

### 11. Agent-Hinweise (drafts)
Ein Review-Agent schreibt `tasks/<KEY>-review-markers.json`; merge-train zeigt die Einträge an ihrer Zeile (needle,
`=`, `line`), mit Details, Status und Siehe-auch. Übernehmen, anpassen & übernehmen, verwerfen. `agent pruefen`
(auch `--seit` für Review-Updates), `agent zeigen`, `agent kommentar` (draft ändern bzw. neuen daneben), `agent
kommentare` (lesen: drafts, staged/sent, GitLab-Diskussionen; `kommentare_teile`, auch für den Zusatz „am MR: …“ zu
„(nichts offen)“ in `feedback`).
- Wer: Feld `agent` der JSON bzw. des Markers, sonst der Agent von `pruefen`/`zeigen` (Akte `hinweis_agenten`); geht
  beim Übernehmen in den Kommentar mit.
- Achsen: Marker-Feld, Prüf-Ergebnis, Zuordnung zum MR (`--mr`, Feld `mr`, Branch; Projekt aus cwd und Repo der
  JSON: `mr_fuer_hinweise`).
- Ort: `hinweise.py`, `agent_cli.py`, `hinweis_aktion` (`review.py`), Route `api/hinweis`. Format: `docs/agent-hinweise.md`.

### 12. GitLab-Diskussionen lesen und beantworten
Holt Diskussionen zu MRs: Antworten und Erledigt-Status an eigenen Kommentaren, fremde Diskussionen nur lesend an der
Zeile und in einer Liste. „↩ antworten“: sofort senden oder als lokaler Entwurf, den „Review abschließen“ als
Draft-Antwort anlegt. „☑ abwarten“ (`abhaken`, nur in der Akte) gibt den Ball ohne Antwort ab, bis ein anderer
danach schreibt; „✓ in GitLab erledigt“ (`erledigen`) löst die Diskussion gleich in GitLab auf, wie ein KI-Thread
erledigt wird – auch per Klick auf das Zeichen in der Liste (`fadenErledigen`). Stand: `diskussion_stand`.
- Ort: `diskussionen_abgleichen`, `antwort_entwurf`, `antwort_senden`, `diskussion_abhaken`, `diskussion_aufloesen`
  (`review.py`), `diskussion_abgehakt` (`akte.py`), `fadenKnoepfe`/`GITLAB_AKTIONEN` (`web/review.js`).
- Liste links: siehe Baustein „Liste links über den Dateien“.

### 13. GitLab nur auf Knopfdruck (Cache)
Seiten fragen GitLab nie selbst. Geholt wird nur über die Knöpfe im Güterbahnhof („↻ MRs“, „↻ MR-Daten“), beim
Abschließen und von `agent pruefen|zeigen` bzw. `merge-train <MR>`. Abweichender GitLab-Stand wird angezeigt, je nach
`stand_zu_gitlab` (`git.py`, Texte `STAND_TEXT`, Knöpfe `STAND_KNOPF`/`stand_html` in `seite.py`): ist origin weiter,
zieht „⇣ lokal aktualisieren“ den Klon nach (`branch_aktualisieren`, Aktion `aktualisieren`); ist lokal weiter, pusht
„⇡ pushen“, nach einem Rebase (lokal stand der Branch laut reflog auf dem GitLab-Stand) „⇡ force-push (with lease)“
mit Lease auf den zuletzt geholten GitLab-Stand (`branch_pushen`, Aktion `pushen`, erst bestätigen); danach bzw. nach
einem Push aus dem Terminal „gepusht“ mit „↻ MR-Daten“; auseinandergelaufen ohne Rebase: nur die Meldung. Beide
Aktionen holen danach die MR-Daten (`mr_daten_holen`). Eine im Hintergrund neu gebaute MR-Seite (`api/stand` liefert `seite`)
lädt offene Tabs neu (`neuLaden` in `web/review.js`). Den Klon liefert `lokale_klone` (`[repos]`, Akte `klon`, sonst
`klon_suchen`: `<klon_ordner>/<projekt>`, wenn origin passt). Fehlt im Klon ein Branch des MR, holt `mr_lokal` origin einmal je Serverlauf. Beim ersten Besuch eines MR checkt `mr_auschecken` (`review.py`,
im Hintergrund über `im_hintergrund` im Server) den Quell-Branch im Klon aus, wenn der Stand sauber ist
(`branch_auschecken` in `git.py`; Einstellung `mr_auschecken`, einmal je MR: Akte `ausgecheckt`). Die Seite liest die
Branch-Refs, nicht HEAD, und lädt deshalb nicht neu; die Meldung kommt über `api/stand` (`meldung`) in die Glocke.
- Ort: `gitlab.py`, `mr_gitlab_holen`/`mr_daten_holen` (`review.py`), Route `api/gitlab`, `web/bahnhof.js`.
- Erweitern: neue GitLab-Daten an einen bestehenden Holen-Knopf hängen, keinen eigenen Abruf beim Laden der Seite.

### 14. Zug und Güterbahnhof
Kopf jeder Seite: ein Wagen je Waggon (gemischt aus allen Quellen), Füllstand, Marken („💬 n neu“, „● n dran“ –
ein eigenes „ungesehen“ gibt es nicht, ein neuer Beitrag anderer macht die Diskussion „dran“), Wechsel per Klick oder n/Enter, „fertig ✓“ für lokale Waggons, Abfahrt. Leitstand-Knöpfe je Quelle.
Welche MRs: `mr_liste` (reviewer, author, assignee).
- Achsen: Quelle, Marke am Wagen, Knopf im Leitstand.
- Ort: `alle_wagen`/`wagen_fuer` (`quellen.py`), `seite.py`, `web/zug.js`, `web/bahnhof.js`, `web/zeichnungen.js`;
  Spec und Ausbauschritte: `docs/gueterbahnhof.md`.

### 15. „fertig“ / „abgeben“ (lokal)
Setzt `von` auf den gesehenen Stand (`git push . <sha>:<von>`: nur Fast-Forward, der pre-push-Hook des Repos läuft,
bei merge-train selbst `./testen --push`, bis ~20 s; die Seite zeigt dann „⏳ prüft …“, ein Fehlschlag ändert nichts
und meldet die Ausgabe des Hooks), warnt bei offenen Fäden oder ungesendeten Entwürfen, räumt erledigte Fäden weg.
Nicht bei `origin/…` oder Arbeitsstand. Ist erst ein Teil der Dateien abgehakt, heißt der Knopf „abgeben“: die
abgehakten Dateien (Fassung aus bis) kommen per Plumbing als Commit auf den Teilstand `<von>-wip` (Arbeitsverzeichnis,
Index und HEAD bleiben), der Diff läuft danach ab dem Teilstand (`diff_basis`). Hat der Teilstand den Baum von bis,
ist es „fertig“ (der Teilstand wird gelöscht). Abgegeben zählt für die Abfahrt (RUNDE `abgegeben`, Waggon mit
gestricheltem grünem Rahmen).
- Ort: `fertig_moeglich` (`waggon.py`), Route `fertig` (`server.py`, `teil` = abgeben), `fertig`, `abgeben`,
  `abgabe_pruefen`, `runde_eintragen` (`quellen.py`), `teil_abgeben` (`abhaken.py`), `wip_name`, `wip_sha`,
  `diff_basis` (`git.py`, auch für `statistik` und `projekt_seite`).

### 16. Beobachten (Arbeitsstand live)
`merge-train --beobachten [ordner] [--von REF]`: eigene Instanz mit eigenem Port und Daten, inotify, lädt bei
echter Änderung neu, rahmt Neues ein, endet beim Schließen des Tabs. `agent …` aus dem Repo landet bei der Instanz.
- Ort: `instanz.py` (Kommandozeile), `beobachter.py` (Server), `web/beobachten.js`, Route `api/neu`.
- Ideen zum Ausbau: `docs/ideen.md`.

### 17. Stellwerk (HUD) und Meldungen
LED für den Server, Stand von merge-train, Zähler, dahinter ✎ bei einem offenen Eingabefeld (hält Neuladen auf,
Klick springt hin: `hudFeld`), wer zuhört, Kontext-Füllstand; Toasts und 🔔 mit den letzten 50.
Auch auf der Startseite (Güterbahnhof, auch mit Fehler): HUD ohne Zähler und 🔔; Server, Zuhörer und Meldungen aus `api/hud`.
- Ort: `web/hud.js`, `web/toasts.js`, `kontext` (`zuhoerer.py`), Route `api/hud`.
- Erweitern: neue Statusanzeigen ins HUD, neue Meldungen über `App.melden`, keine eigenen Banner.

### 18. Server und Prozess
Kleiner Server auf `127.0.0.1:8771`, Routen-Tabelle mit gemeinsamer Fehler- und Waggon-Behandlung, Seite fragt alle
4 s nach, Neustart bei neuem Stand von Skript oder Einstellung, Ende nach Leerlauf oder `--stopp`.
- Ort: `server.py` (`@route`, `bearbeiten`), `prozess.py`.
- Erweitern: eine neue Aktion der Seite ist eine Route mit `waggon=`/`struktur=`; Änderungen an der Akte nur über
  `akte_bearbeiten`/`aktion_ausfuehren`.

### 19. Kommandozeile
`merge-train [projekt | MR-Verweis | --mrs | --stopp | --beobachten]` und `merge-train agent …` (`pruefen`, `zeigen`,
`feedback`, `antworten`, `horchen`, `kommentar`, `kommentare`, `thread`, `vorfall`). MR-Verweise: URL, `!42`,
`gruppe/projekt!42`. `agent vorfall` legt einen Bericht im Eingang ab (`vorfall_ordner`: `vorfaelle/` im Klon des
laufenden Skripts, sonst im Datenordner; Ablauf: `docs/vorfaelle/README.md`).
- Ort: `cli.py`, `agent_cli.py`, MR-Verweise in `gitlab.py` (`mr_ref`, `ist_mr_ref`). Agenten-Doku:
  `skill/merge-train/SKILL.md`.

### 20. Einstellungen und Installation
`~/.config/merge-train/config.toml` (Vorlage `config.example.toml`), Ersatzparser ohne `tomllib`, Log der
Anfragen an git und GitLab (`log_tage`). Installation: README, Abschnitt „Installation“.
- Ort: `einstellungen.py`, `install.idem.sh`.
- Erweitern: neue Schalter in `einstellungen.py` mit Standard, dazu Zeile in der README-Tabelle und in
  `config.example.toml`.

### 21. Tests (Mini-CI)
`./testen` wählt nach den geänderten Dateien aus: `./pruefen` (JS/CSS), Smoke (Bau nach `tests/bau/`, Import aller
Module), Klassen von `tests/test_einheiten.py` (automatisch aus den Imports der Testdatei und von `src/`), Teile von
`tests/test_gitlab.py` (`gitlab`, `lokal`, `horchen`, `arbeitsstand`, `gemischt`). Läuft als pre-commit-Hook, `--push`
als pre-push-Hook: jeder gepushte Stand, dessen Tree-ID nicht im Merkzettel
`.git/merge-train-getestet` steht, läuft `--voll`, genau dieser Stand (sonst im Temp-Worktree); ein grünes `--voll` auf
sauberem Stand trägt ein. Takt im pre-commit (`voll_faellig`, `.git/merge-train-takt`): erster Commit des Tages
`--voll`, danach erst wieder nach 2 h und 5 Commits (was später kommt). Nur `--voll` (pre-push, Takt): UI-Tests `tests/test_ui.py` (`senden`, `vorschau`, `zuletzt`) im
headless Chromium über die DevTools-Pipe (`Pipe` aus `perf/cdp_messung.py`, Server und Test-Repo aus
`werkzeug/seiten_vergleich.py`). Achsen: Auswahl (Diff gegen HEAD, `--seit`, `--voll`, `--liste`, `--push`).
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
| GitLab aufrufen | `gitlab.py` (glab), nur auf Knopfdruck |
| Zeile zwischen Ständen zuordnen | `zeilen.py` |
| Code-Stelle verlinken | `pfad:zeile` im Text bzw. `see_also`, Popup aus `web/diff.js` |
| Liste links über den Dateien | `kommentarListe`, `kasten` (`web/diff.js`); Stände nach [Stände der Listen](#stände-der-listen-wer-ist-dran), je Liste in `LISTEN_STATI`, Filter je Waggon im Browser (`ausgeblendet`). Neue Liste = neuer Eintrag in `LISTEN_STATI` |
| Stand eines Eintrags anzeigen | `stand`/`wer` vom Server, `App.STAENDE`, `App.werZeichen` – nie eigene Zustände |
| Meldung an den Nutzer | `App.melden` (Toasts), auf Python-Seite `Fehler` |
| Langer Ablauf mit GitLab | planen und ausführen getrennt (wie `abschluss_planen`/`schritt_ausfuehren`) |
| Agent soll etwas tun | `Quelle.prompt` und `benachrichtigen` (`zuhoerer.py`) |
| Gemeinsames im JS | nur über `App`, Kopfkommentar „braucht/stellt bereit“ pflegen |
