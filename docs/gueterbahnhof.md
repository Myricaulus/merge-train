# Güterbahnhof – Spec

Der Kopf jeder merge-train-Seite ist ein Umschlagbahnhof für Schüttgut. Der Zug zeigt auf einen Blick, wie viel
Review-Arbeit ansteht und wie viel erledigt ist: Jeder Wagen ist ein MR (lokal: ein Projekt) und wird beim
Abhaken der Dateien mit Schüttgut beladen.

## Stand (Schritt 1, erledigt)

Commits `321af08` … `eba8275` auf `claude`:

- **Kulisse:** `src/merge_train/web/bahnhof.webp` ist das myr-Panorama (7014×775). Die Seite bekommt es als Base64 (`web.py`), und
  `gleise_html` setzt es als `--bild` auf `.szene`. Es füllt die volle Breite, ist aber mindestens 2480 px breit
  (sonst seitlich abgeschnitten). Der Horizont liegt immer auf y=176 (`review.css`, `.szene`).
- **Nacht:** blaues Overlay über der Kulisse, die Fenster leuchten (`prefers-color-scheme: dark`).
- **Anlage:** `anlageZeichnen()` in `src/merge_train/web/zeichnungen.js` zeichnet sie in `#anlage`. Links steht das Verladegebäude: Bandturm
  mit dem Schild „MERGE-TRAIN“, verglaster Leitstand und ein Tor fürs Gleis bei x=28…156. Daraus läuft das
  Förderband als Fachwerkbrücke bis zur Bandmitte `cx` (Bildschirmmitte, mindestens 330), mit Bandkopf, Schurre
  und Strahl über dem Wagen. Dazu kommen Gleis, Schotter und Schwellen. Die Knöpfe sind HTML (`#bahnhof`) im
  Leitstand: GitLab „↻ MRs“ und „↻ MR-Daten“ (ohne glab ausgegraut), lokal „↻ Änderungen“ (lädt neu).
- **Band:** `.szene.laedt` bzw. `.laeuft` lässt es rütteln, das Schüttgut wandert und aus der Schurre rieselt
  es. `#laden` setzt `laedt` dauerhaft.
- **Scrollen:** Der Himmel (`--himmel: 96px`) rutscht weg, Leitstand, Band und Zug bleiben stehen. `kopfHoehe()`
  in `navigation.js` rechnet ihn heraus.
- **Zug:** Der aktuelle Wagen (sonst der letzte) steht unter dem Band, `#zug` scrollt mit Rand `cx` links und
  rechts. Die Wagen sind noch die alten weißen Kästen.

## Schritt 2: Schüttgutwagen

- Alle Wagen sind gleich groß und als offene Schüttgutwagen gezeichnet. Ein Ladezettel trägt Titel, +/− und die
  bisherige Marke (offen, fertig, 💬).
- Ein leerer Wagen hat einen dunklen, deutlich abgesetzten Innenraum, damit man den Füllgrad auf einen Blick
  sieht.
- Die Füllung ist Schüttgut im Stil der Kulisse. Häufchen obendrauf bei 25, 50 und 75 %.
- **Reihenfolge:** Vorne, direkt hinter der Lok, steht der Wagen, der beim ersten Öffnen standardmäßig kommt,
  also der größte. Damit ist die Reihenfolge umgekehrt zu heute. Die Lok (S 3/6) steht immer rechts davor, der
  vorderste bzw. aktuelle Wagen unter dem Bandende.

## Schritt 3: Füllung nach Zeilen

**Stand:** Abhaken und Füllung sind umgesetzt (`abhaken.py`, siehe `docs/funktionen.md`, Abschnitt 4), noch ohne
Band-Animation, Kriechen und Flammen. Abhaken ist ein ☐ im Dateikopf (Zuklappen allein zählt nicht), ein Haken lässt
sich wieder entfernen. Die Füllung steht in der Akte des Waggons. Gilt für lokale Waggons und MRs.

- Füllgrad = Zeilen (+ und −) der fertigen Dateien / Zeilen aller Dateien im MR. Jede Datei zählt mit einer
  Mindestportion.
- Datei abhaken: Die Gutschrift kommt sofort. Das Band rüttelt dabei (`.laeuft`), länger bei großen Dateien,
  aber gedeckelt. Am Wagen häuft es sich vorne bis zur Füllhöhe, und der Zug kriecht pro Befüllung ein Stück
  vor. Es fahren keine Objekte übers Band, ein Abbruch fällt also nicht auf.
- Nur das erste Abhaken zählt. Wieder aufklappen nimmt nichts weg.
- Bei `--seit` sind nur neue Dateien offen. Alte erledigte Dateien zählen weiter als voll: Füllgrad = alle
  Dateien minus die nicht fertigen.
- **Neuer Push ändert eine schon gereviewte Datei:** Ihre Menge verschwindet aus dem Wagen. Der Wagen steht
  kurz in Flammen mit Rauchwölkchen (nice to have), dann sinkt die Füllung.
- **Server:** Er speichert den Zustand jedes Wagens am Zug: Reihenfolge, Füllung pro Datei, erledigt. Bisher
  wird der Zug bei jedem Laden aus der MR-Liste berechnet. Ein Eintrag wird erst gelöscht, wenn der MR gemergt
  und ausrangiert ist. Ein MR, der gestern weggefahren ist und heute neue Änderungen bekommt, kommt teilgefüllt
  wieder.

- **Teilabgabe (lokal, `<von>-wip`):** Ein großer Diff muss nicht auf einmal fertig werden. Klickt man auf
  „abgeben“, wenn erst ein Teil der Dateien abgehakt ist, schreibt merge-train die abgehakten Dateien in der
  Fassung aus `bis` als Commit auf `<von>-wip`, also z. B. `reviewed-wip`. Das geschieht per Plumbing, Arbeitsverzeichnis
  und Index bleiben unberührt. Die Seite zeigt danach `<von>-wip..bis`, also nur noch den Rest.
  Sobald `<von>-wip` denselben Baum hat wie `bis`, wird `von` auf `bis` gesetzt (wie bei „fertig“) und
  `<von>-wip` gelöscht.
- **„abgeben“ statt „fertig“:** Ein abgegebener Teilstand zählt für die Abfahrt, sonst fährt der Zug bei einem
  zu großen MR nie ab. Der Wagen bekommt dafür einen grünen, aber gestrichelten Rahmen. Ist der Zug abgefahren,
  wird der Wagen an diesem Tag nicht mehr angezeigt. Ist sein wip noch offen, kommt er aufs Rangiergleis
  (Schritt 6).

## Schritt 4: Rangieren

- Wird ein anderer MR gewählt (oder ist der vordere fertig), fährt der Zug vor oder zurück, bis der aktuelle
  Wagen unter dem Band steht. Lok und Wagen dürfen dabei aus dem Bild fahren.
- Das Band stoppt währenddessen. Die Gutschrift ist ohnehin schon passiert.
- Nach dem Ankuppeln ist die Reihenfolge fest. Der Zug wird nie umsortiert.

## Schritt 5: Köf, neue Wagen, Abfahrt

- **Rangierlok:** eine Köf. Sie kommt von links aus dem Tor des
  Verladegebäudes und schiebt neue Wagen hinten an. Untereinander sortiert sie sie außerhalb des Bildes, die
  größten zuerst.
- **Wann sie kommt:** beim ersten Start, bei F5 mit `#laden`, wenn der Server keine nicht abgegebenen Wagen
  kennt (Initialzustand oder Seite zuletzt leer geschlossen), und bei jedem neuen MR durch eine Aktualisierung.
  Lokal bringt sie alle auf einmal, und der Knopf schaut nach neuen lokalen Änderungen.
- **Nichts Neues:** Es passiert nichts, keine Leerfahrt.
- **Abfahrt:** Gereviewte Wagen bleiben voll am Zug, bis alle voll sind. Lokal gilt die bestehende Fertig-Regel,
  und zwar für alle Projekte. Bei GitLab müssen zusätzlich alle Kommentare aller Wagen abgegeben sein. Der Zug
  rollt dann rechts raus, und von links kommt eine neue S 3/6 ohne Wagen. Wer zu viele MRs hat, sieht es daran,
  dass der Zug nie abfährt.

## Schritt 6: Rangiergleis (Konzept, noch nicht umsetzen)

Eine zweite Ansicht neben dem Bahnhof. Dort stehen die gerade inaktiven Wagen: abgegebene wip-Wagen, Projekte
ohne Änderungen und Wagen, die man herausgenommen hat.

- **Hinweg:** Links oben, über dem Verladegebäude, zeigt ein Schild nach links, darauf der Knopf „Rangiergleis“.
  Ein Klick schwenkt die Seite zügig (etwa 1 s) nach links. Am besten schwenkt die Diff-Ansicht nach rechts
  hinaus und die Rangiergleis-Ansicht herein, mindestens aber der Kopf mit dem Zug. Das Hintergrundbild schwenkt
  dabei schneller (Parallaxe).
- **Auf dem Rangiergleis:**
  - Man kann die inaktiven Wagen ansehen, ihre Branches einstellen (wie mit der Waggon-Karte) und Wagen wieder
    aktiv schalten, z. B. einen abgegebenen wip-Wagen.
  - Links oben steht die Köf. Aktivierte Wagen werden an sie angehängt. Sie materialisieren sich in etwa 0,5 s,
    per Transparenz oder mit einem „Star-Trek-Beam“-Effekt. Ein ✕ wirft sie wieder hinaus.
- **Tafel rechts oben:** Sie zeigt die aktuelle Zuggröße im Bahnhof, symbolisch und nicht als Text. Reicht die
  Breite der Seite nicht, um den ganzen Zug darzustellen, erscheint eine Warnung.
- **Rückweg:** Rechts oben zeigt ein Schild nach rechts, darauf der Knopf „beladen“. Ein Klick lässt die Köf
  langsam losfahren, und das Bild schwenkt zurück zum Bahnhof. Kurz darauf kommt die Köf dort an und hängt die
  Wagen an. Ein aktivierter Wagen steht danach oben im Kopf.

## Bewusst nicht

- Kein Ton (Pfiff, Negativ-Ton): Dafür bräuchte es echte Samples, erst später.
- Kein Sonderfall für reduzierte Bewegung.
- Keine Wagen in verschiedenen Größen. Die Größe steht als +/− auf dem Ladezettel.

## Werkzeuge

- **Screenshots ohne Node:** Mit dem DevTools-Protokoll wie in `perf/cdp_messung.py` (`Pipe`), Breite per
  `Emulation.setDeviceMetricsOverride` und Dunkelmodus per `Emulation.setEmulatedMedia`
  (`prefers-color-scheme: dark`). Der Chromium-Schalter `--force-dark-mode` greift headless nicht.
- **Bildschirme des Nutzers:** 2560×1440 und 1920×1080.
- **Server auf 8771:** Er beendet sich nach einer Weile ohne Anfragen. Neu starten mit
  `setsid -f merge-train --server`, beenden mit `merge-train --stopp`.
