# Vorfälle

Berichte von Agenten über Stellen, an denen merge-train sie in die Irre geführt hat (Meldung, Skill, CLI).

`merge-train agent vorfall "<Titel>" -` legt den Bericht als **Issue im GitHub-Repo von merge-train** an. Ziel ist der
origin des Klons, aus dem das laufende `merge-train` stammt, wenn er auf GitHub zeigt (auch ein ssh-Alias wie
`github-privat`). Mit der Einstellung `vorfall_github = "owner/repo"` geht er in ein anderes Repo, mit `"aus"` immer in
die Datei. Angelegt wird über `gh api repos/<repo>/issues`, mit `--art bug` bzw. `--art wunsch` samt Label `bug`
bzw. `enhancement` (ohne Schreibrechte am Repo lässt GitHub das Label still weg). Der Token braucht nur **Issues: Read and write**, `gh issue
create` bräuchte zusätzlich Leserechte am Inhalt. Weil das Issue das Projekt verlässt, an dem der Agent gerade
arbeitet, hält der Skill ihn an, allgemein zu schreiben: keine Namen, Pfade, Tickets oder Fachbegriffe von dort.

**Fallback: Datei.** Klappt das Issue nicht (kein `gh`, nicht angemeldet, keine Rechte, kein GitHub-Remote, eigene
Instanz), landet der Bericht als Datei, und die Ausgabe nennt den Grund:

| Ort | Inhalt |
|---|---|
| `vorfaelle/` (Repo-Wurzel, gitignored) | **neu**: Eingang, noch nicht abgearbeitet, Datei `JJJJ-MM-TT-<thema>.md`. Läuft merge-train nicht aus einem Klon (oder als eigene Instanz): `vorfaelle/` im Datenordner (`~/.local/share/merge-train`). |
| `vorfaelle/erledigt/` (ebenfalls gitignored) | **abgearbeitet**: Archiv. Jeder Bericht beginnt mit einem Block „Umgesetzt“ (was geändert wurde, Commit, bewusst nicht Umgesetztes). |

Abarbeiten: Issue mit einem Kommentar „Umgesetzt“ (was geändert wurde, Commit, bewusst nicht Umgesetztes) schließen.
Bei einer Datei denselben Block unter den Titel setzen und sie nach `vorfaelle/erledigt/` verschieben. Der Bericht
selbst bleibt, wie der Agent ihn geschrieben hat. Eine Datei im Eingang kann man auch nachträglich als Issue anlegen.

**Wer sagt es den Agenten?** Der Skill `merge-train` (letzter Abschnitt) und `mr-review` verweisen auf `agent vorfall`.
