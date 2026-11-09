# Hinweise für Agenten

## Branches

| Branch | Stand | Wer setzt ihn |
|---|---|---|
| `claude` | neuer Stand vom Agenten | Agent: hier committen (und pushen, wenn gewünscht) |
| `reviewed` | vom Nutzer gereviewter Stand | Nutzer, per merge-train „fertig“ – Agent fasst ihn nicht an |
| `main` | deployter Stand (GitHub-Standard-Branch, holt der WSL-Rechner per `git pull`) | Nutzer: `git push origin reviewed:main` – Agent nur auf ausdrückliche Bitte |

Dass die drei Branches gerade auf denselben Commit zeigen, heißt nur, dass alles gereviewt und deployt ist.
Nicht als Hinweis lesen, dass `reviewed` und `main` dasselbe wären.

## Code

Änderungen nur in `src/` (Python-Teile, `src/web/*.css|js`), danach `./bauen`. `merge-train` ist das gebaute
Ergebnis: nicht eingecheckt, nie direkt bearbeiten. Die Tests bauen zuerst.

## Tests

`python3 tests/test_gitlab.py` (GitLab-Modus mit `tests/fake-glab`, Port 8799). Nicht `pkill -f "merge-train --server"`:
das trifft auch den Server des Nutzers auf Port 8771.

## Gespräch im lokalen Modus

Der Nutzer stellt Fragen und Wünsche zum Code direkt in merge-train (siehe README, „Gespräch mit Claude“).
Abholen mit `merge-train agent feedback`, antworten mit `merge-train agent antworten <id> "…"` (`--erledigt`, wenn
umgesetzt). Soll die Session zuhören: `merge-train agent horchen` im Hintergrund starten und nach jeder Ausgabe neu starten.
