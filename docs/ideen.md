# Ideen für später

Noch nicht entschieden, nur geparkt.

## Beobachten als Bildschirmschoner

Zu `merge-train --beobachten`: zum Zuschauen und Entspannen, während ein Agent oder ein eigener Refactor läuft.

- ~~**Rahmen um das Neue**~~ (erledigt, `web/beobachten.js`, `api/neu`): Nach dem Neuladen wegen einer Änderung bekommen
  die Zeilen, die sich seit dem zuletzt angezeigten Stand geändert haben, einen Rahmen; die Seite scrollt sanft hin. Er
  bleibt bis zur nächsten Änderung. Offen: Stellen in eingeklapptem Kontext oder in nachzuladenden Dateien bekommen keinen
  Rahmen (die Zeilen sind nicht auf der Seite), und eine zurückgenommene Änderung (wieder auf HEAD-Stand) zeigt nichts.
- **Haufen aus Chunk-Boxen** (statt „Rest schrumpft“): Jede neue Änderung seit der letzten Aktualisierung bekommt eine
  eigene kleine Box im Dateibereich.
  - **Box**: wie die bisherigen Datei-Boxen, aber sehr kompakt (schmale Titelzeile mit Datei und Zeile, kaum Rand). Inhalt:
    der Chunk mit 3 Zeilen Kontext, die geänderten Zeilen bzw. einzelnen Hunks darin hervorgehoben. Sehr große Chunks
    scrollen in der Box, damit sie eine Höchstgröße nicht überschreitet.
  - **Glühen**: Der Rahmen einer neuen Box glüht wie heißes Metall (weiß-gelb → orange → rot). Mit jeder weiteren
    Aktualisierung kühlt er etwas ab, bis er eisengrau ist (oder eine Farbe, die zum Hintergrund passt).
  - **Im Grunde viele kleine Popups** (wie das „Siehe auch“-Popup in `diff.js`, nur ohne Abdunkeln und mehrere zugleich):
    - **Platz**: zufällig im Dateibereich, Größe nach Inhalt (bis zur Höchstgröße). Kein Raster, kein Ausweichen – sie
      dürfen sich überlappen, neue landen obenauf. 16, mindestens 9 sollen locker Platz haben.
    - **Schief hingeworfen**: Jede Box, die noch nie im Spotlight war, liegt leicht gedreht, zufällig zwischen 10° und
      20° nach links oder rechts (also nie zwischen −10° und +10°). Eine Box, die einmal im Spotlight war, liegt danach
      für immer gerade – so sieht man, was man schon angeschaut hat. (`transform: rotate()`, das Geraderücken als Übergang.)
    - **An der Titelzeile verschiebbar**, sonst bleiben sie liegen, wo sie gelandet sind.
    - **Spotlight**: Doppelklick auf die Titelzeile macht daraus ein Fenster mit 60 % des Viewports in der Mitte. Klick
      daneben macht es wieder klein (an seinen alten Platz).
    - **Rausfliegen nach einer Regel**: die ältesten (über der Höchstzahl) und veraltete (ihre Stelle hat sich seitdem
      wieder geändert oder ist nicht mehr im Diff).
    - **Während Spotlight** landen neue Boxen am Rand, damit man sieht, dass es im Hintergrund weitergeht.
  - Weiche Bewegungen (Landen, Abkühlen, Rausfliegen, Spotlight auf/zu) mit CSS-Übergängen. Dafür nicht mehr neu laden:
    Die Seite holt die neuen Chunks per fetch und baut nur die Boxen dazu.
  - Früher angedacht und verworfen (zu viel Tüftelei): Haufen, der alte Boxen aus dem Viewport drückt, Box unter der Maus
    bleibt stehen, Boxen einer Datei beieinander, dahinter liegende rutschen beim Spotlight hervor.
  - Bausteine: `neue_zeilen` (`beobachter.py`, `git diff -U0 alt neu`) liefert schon die Bereiche; für die Boxen bräuchte es
    dieselben Hunks mit `-U3` samt Syntaxfarben (wie `api/zeilen`). Was beim Ende des Bildschirmschoners passiert (zurück
    zum normalen Diff, z. B. per Taste), ist noch offen.

## Weitere geparkte Punkte

- **Aussagekräftigere Namen**: „zustand“ ist zu allgemein – Zustand wovon? Gemeint ist die Review-/Gesprächsdatei eines
  Waggons. Rein mechanisch umbenennen (z. B. `with waggon_daten(waggon) as daten:`), dasselbe Maß an andere allgemeine
  Namen anlegen (`st`, `d`, `r`, `rv`).

- **Branch wechseln aus merge-train**, wenn mehrere MRs anstehen. Müsste jira-review vorher übernehmen (testen,
  bauen), braucht noch Überlegung im Detail.
- **Eigene MRs**, die andere reviewen, im Zug zeigen und deren Kommentare per Güterbahnhof nachladen.
- **main-Merges** aus „seit diesem“ und aus der Ansicht eines Merge-Commits herausrechnen
  (`git merge-tree --write-tree` mit der aktuellen Basis).
- **Erstes Laden in frischem Browser** (~2 s Layout, nur unter WSL; unter Linux 0,5 s), siehe [performance.md](performance.md).
- **Sichtung für MyrSpace** (vorgemerkt, Richtung entschieden): merge-train wird fester Teil der Sichtung einer
  sudo-Anfrage und später des Einlasses einer Myrte. Der Myrling liefert den Unterschied aus seinem Lauf-Repo
  (`anfrage/<n>` gegen `main`) über den sicheren Kanal, merge-train zeigt ihn mit markierten Sonderzeichen und meldet
  „gesehen“ mit dem Lauf-Hash des Gezeigten zurück, entschieden wird am Handy. Bei Myrten nur den Unterschied zum
  letzten eigenen Befund sichten. Grundlage: MyrSpace `ausweise/FORMATE.md` 7.5, 7.6, `UseCases.md` U32, U4G, U4H;
  Begriffe: [glossar.md](glossar.md), Abschnitt 10.
