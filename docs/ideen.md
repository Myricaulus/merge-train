# Ideen für später

Noch nicht entschieden, nur geparkt.

## Kommentare im lokalen Modus (Feedback an den Agenten)

Im lokalen Projekt-Diff (`claude` gegen `reviewed`) wie im GitLab-Modus auf eine Zeilennummer klicken und kommentieren,
damit der Agent das Feedback zu seinem Code bekommt.

Seit dem gemeinsamen Seitenaufbau ist das meiste schon da: Zeilenzuordnung, Kontext-Zeilen, Commit-Ansichten,
Kommentarliste und Kästen (`review.js`). Was fehlen würde:

- **Speicherort**: Review-Stand je Projekt, z. B. `~/.local/share/merge-train/lokal/<projekt>.json`, gleiches Format
  wie bei MRs (`kommentare` mit `path`, `a`, `b`, `text`, Stand `head_sha`).
- **Übergabe an den Agenten** statt „Review abschließen → GitLab“, zum Beispiel:
  - `merge-train agent feedback <projekt>`: gibt die offenen Kommentare aus (Datei, Zeile, Zeilentext als needle, Text),
    der Agent arbeitet sie ab.
  - oder eine Datei im Repo (`tasks/feedback.json` im Format der review-markers, dann zeigt merge-train die Antworten
    des Agenten gleich als Hinweise an).
- **Erledigt-Abgleich**: Nach neuen Commits auf `claude` wie beim Review-Update (`--seit`) zeigen, welche Kommentare
  sich erledigt haben (Zeile weg/geändert). Offen: Soll „fertig“ gesperrt sein, solange Kommentare offen sind?
- Kommentare zum Stand in einer „seit diesem“-Ansicht gehen schon heute über die MR-Zeilen. Lokal genauso.

## Weitere geparkte Punkte

- **Branch wechseln aus merge-train**, wenn mehrere MRs anstehen. Müsste jira-review vorher übernehmen (testen,
  bauen), braucht noch Überlegung im Detail.
- **Eigene MRs**, die andere reviewen, im Zug zeigen und deren Kommentare per Güterbahnhof nachladen.
- **main-Merges** aus „seit diesem“ und aus der Ansicht eines Merge-Commits herausrechnen
  (`git merge-tree --write-tree` mit der aktuellen Basis).
- **Erstes Laden in frischem Browser** (~2 s Layout), siehe [performance.md](performance.md).
