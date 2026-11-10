# Hinweise für Agenten

## Branches

| Branch | Stand | Wer setzt ihn |
|---|---|---|
| `claude` | neuer Stand vom Agenten | Agent: hier committen (und pushen, wenn gewünscht) |
| `reviewed` | vom Nutzer gereviewter Stand | Nutzer, per merge-train „fertig“ – Agent fasst ihn nicht an |
| `main` | deployter Stand (GitHub-Standard-Branch, holt der WSL-Rechner per `git pull`) | Nutzer: `git push origin reviewed:main` – Agent nur auf ausdrückliche Bitte |

Dass die drei Branches gerade auf denselben Commit zeigen, heißt nur, dass alles gereviewt und deployt ist.
Nicht als Hinweis lesen, dass `reviewed` und `main` dasselbe wären.

## Begriffe: Stufen eines GitLab-Kommentars

Nur für die Entwicklung (Doku, Code-Kommentare, Skill, Ausgaben von `merge-train agent`). Die Seite behält ihre Labels.

| Stufe | Bedeutung | Seite | Code |
|---|---|---|---|
| **draft** | Agent-Hinweis aus der Review-JSON, noch nicht übernommen. Darf noch geändert werden (auch vom Agenten). | lila Hinweis, „übernehmen“ | Hinweis-Status `offen` |
| **staged** | übernommen bzw. selbst geschrieben, wird mit „Review abschließen“ gesendet | „Entwurf (lokal)“, „geändert – wird aktualisiert“, „wird in GitLab gelöscht“ | `k_status`: `neu`, `geaendert`, `loeschen` |
| **sent** | als Draft-Note in GitLab bzw. dort veröffentlicht (in GitLab verworfene werden wieder staged) | „in GitLab (Entwurf)“, „in GitLab veröffentlicht“ | `k_status`: `uebertragen`, `weg` |

**staged entsteht nur durch den Nutzer**: Klick auf „übernehmen“ (oder ein selbst geschriebener Kommentar). Der Agent legt
nie Review-Kommentare an. Er ändert nur drafts und legt sonst einen neuen draft daneben an (`merge-train agent kommentar`,
als Marker in der Review-JSON des MR).
Achtung: GitLab nennt auch sent-Kommentare „draft notes“; „draft“ meint hier immer den Agent-Hinweis.

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
