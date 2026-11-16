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
| **staged** | übernommen bzw. selbst geschrieben, wird mit „Review abschließen“ gesendet | „Entwurf (lokal)“, „geändert – wird aktualisiert“, „wird in GitLab gelöscht“ | `kommentar_status`: `neu`, `geaendert`, `loeschen` |
| **sent** | als Draft-Note in GitLab bzw. dort veröffentlicht – mit „direkt veröffentlichen“ (Standard) gleich beim Abschließen (in GitLab verworfene werden wieder staged) | „in GitLab (Entwurf)“, „in GitLab veröffentlicht“ | `kommentar_status`: `uebertragen`, `weg` |

**staged entsteht nur durch den Nutzer**: Klick auf „übernehmen“ (oder ein selbst geschriebener Kommentar). Der Agent legt
nie Review-Kommentare an. Er ändert nur drafts und legt sonst einen neuen draft daneben an (`merge-train agent kommentar`,
als Marker in der Review-JSON des MR).
Achtung: GitLab nennt auch sent-Kommentare „draft notes“; „draft“ meint hier immer den Agent-Hinweis.
Davon getrennt zeigt die Seite je Eintrag, wer dran ist (`stand`) und wer zuletzt gehandelt hat (`wer`), siehe
„Stände der Listen“ in [`docs/funktionen.md`](docs/funktionen.md).

## Funktionen und DRY

Vor jeder Änderung in [`docs/funktionen.md`](docs/funktionen.md) nachsehen, ob es die Funktion oder einen passenden
Baustein schon gibt. Wenn ja, diesen erweitern statt daneben etwas Neues zu bauen: DRY bleiben. Fällt bei einer
geplanten Änderung schon bestehende Duplikation im Code auf, sie gleich mit beseitigen, sofern sie zur geplanten
Änderung passt (gleiche Stelle, gleicher Baustein). Sonst nur benennen. Die Datei beim Ändern mitpflegen: neue
Funktion = neuer Eintrag, neue Variante = ein Wort in ihrer Achse.

## Code

Änderungen nur in `src/` (Python-Module in `src/merge_train/`, `src/merge_train/web/*.css|js`), danach `./bauen`. `merge-train` ist das gebaute
Ergebnis: nicht eingecheckt, nie direkt bearbeiten. Die Tests bauen zuerst.

## Tests

**Keine eigenen Testläufe: ändern → committen.** Der pre-commit-Hook ruft `./testen` auf, das nur prüft, was die
Änderungen betreffen. Der pre-push-Hook (auch `git push .` von „fertig“) ruft `./testen --push` auf: Stände, die noch
nicht voll getestet sind, laufen voll. Ein Commit, der scheitert (Exit ≠ 0), zeigt die
Fehler: beheben, wieder committen. Nicht `--no-verify`. Den Auto-Neustart und das Neuladen der Seite nicht prüfen, die
sieht der Nutzer im HUD. Eigene Läufe nur auf Anfrage oder beim Arbeiten an den Tests selbst
(`./testen --liste` zeigt die Auswahl, `python3 tests/test_gitlab.py <teil>` einen Teil).

Neues Modul in `src/merge_train/`: in `MODUL_TEILE` in `testen` eintragen. Die Einzeltests rufen Funktionen beim Namen auf,
`test_gitlab.py` über `alles_laden` auch: beim Umbenennen mitziehen. `biome lint src/merge_train/web` nicht direkt
aufrufen (`App` und `MR` sind Globale aus dem Bündel), sondern `./pruefen`. Den Server des Nutzers (Port 8771) nur mit
`merge-train --stopp` beenden, eine eigene Instanz mit `merge-train --beobachten --stopp [ordner]`.

## Gespräch im lokalen Modus

Der Nutzer stellt Fragen und Wünsche zum Code direkt in merge-train (siehe README, „Gespräch mit Claude“).
Abholen mit `merge-train agent feedback`, antworten mit `merge-train agent antworten <id> "…"` (`--erledigt`, wenn
umgesetzt). Soll die Session zuhören: `merge-train agent horchen` im Hintergrund starten und nach jeder Ausgabe neu starten.

## Vorfälle

Neue Berichte legen Agenten mit `merge-train agent vorfall` in `vorfaelle/` ab (gitignored), abgearbeitete mit dem Block „Umgesetzt“ in `docs/vorfaelle/`
(siehe [`docs/vorfaelle/README.md`](docs/vorfaelle/README.md)).
