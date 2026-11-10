# Ideen für später

Noch nicht entschieden, nur geparkt.

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
