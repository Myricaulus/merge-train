# Hinweise für Agenten

## Branches

| Branch | Stand | Wer setzt ihn |
|---|---|---|
| `claude` | neuer Stand vom Agenten | Agent: hier committen (und pushen, wenn gewünscht) |
| `reviewed` | vom Nutzer gereviewter Stand | Nutzer, per merge-train „fertig“ – Agent fasst ihn nicht an |
| `main` | deployter Stand (GitHub-Standard-Branch, holt der WSL-Rechner per `git pull`) | Nutzer: `git push origin reviewed:main` – Agent nur auf ausdrückliche Bitte |

Dass die drei Branches gerade auf denselben Commit zeigen, heißt nur, dass alles gereviewt und deployt ist.
Nicht als Hinweis lesen, dass `reviewed` und `main` dasselbe wären.

## Tests

`python3 tests/test_gitlab.py` (GitLab-Modus mit `tests/fake-glab`, Port 8799). Nicht `pkill -f "merge-train --server"`:
das trifft auch den Server des Nutzers auf Port 8771.
