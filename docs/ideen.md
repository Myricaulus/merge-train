# Ideen für später

Noch nicht entschieden, nur geparkt.

## Beobachten als Bildschirmschoner

Zu `merge-train --beobachten`: zum Zuschauen und Entspannen, während ein Agent oder ein eigener Refactor läuft.

- ~~**Rahmen um das Neue**~~ (erledigt, `web/beobachten.js`, `api/neu`): Nach dem Neuladen wegen einer Änderung bekommen
  die Zeilen, die sich seit dem zuletzt angezeigten Stand geändert haben, einen Rahmen; die Seite scrollt sanft hin. Er
  bleibt bis zur nächsten Änderung. Offen: Stellen in eingeklapptem Kontext oder in nachzuladenden Dateien bekommen keinen
  Rahmen (die Zeilen sind nicht auf der Seite), und eine zurückgenommene Änderung (wieder auf HEAD-Stand) zeigt nichts.
- **Rest schrumpft**: Nur die gerahmten Stellen mit etwas Kontext bleiben groß, der übrige Code schrumpft zügig zusammen
  (zusammengeklappt oder klein skaliert).
- **Weiche Bewegungen** (nice to have): Rahmen gleitet zur neuen Stelle, Schrumpfen/Aufziehen animiert statt Sprung.
  Sanftes Scrollen gibt es schon. Für weiche Übergänge eher nicht neu laden, sondern die Seite per fetch tauschen.

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
