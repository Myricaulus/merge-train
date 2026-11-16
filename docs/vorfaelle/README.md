# Vorfälle

Berichte von Agenten über Stellen, an denen merge-train sie in die Irre geführt hat (Meldung, Skill, CLI).

| Ort | Inhalt |
|---|---|
| `vorfaelle/` (Repo-Wurzel, gitignored) | **neu**: Eingang, noch nicht abgearbeitet. Agenten legen hier mit `merge-train agent vorfall "<Titel>" -` die Datei `JJJJ-MM-TT-<thema>.md` ab. |
| `vorfaelle/erledigt/` (ebenfalls gitignored) | **abgearbeitet**: Archiv. Jeder Bericht beginnt mit einem Block „Umgesetzt“ (was geändert wurde, Commit, bewusst nicht Umgesetztes). |

Abarbeiten: Bericht lesen, beheben, den Block „Umgesetzt“ unter den Titel setzen und die Datei nach `vorfaelle/erledigt/`
verschieben. Eingecheckt wird nur diese Beschreibung, die Berichte bleiben lokal.
Der Bericht selbst bleibt, wie der Agent ihn geschrieben hat.

**Wer sagt es den Agenten?** Der Skill `merge-train` (letzter Abschnitt) und `mr-review` verweisen auf
`agent vorfall`. Der Befehl findet den Eingang selbst: `vorfaelle/` im Klon, aus dem das laufende `merge-train` stammt.
Das klappt auch bei anderen Nutzern, die merge-train von GitHub auschecken. Läuft merge-train nicht aus einem Klon
(oder als eigene Instanz), landet der Bericht in `vorfaelle/` im Datenordner (`~/.local/share/merge-train`).

**Nicht selbst an merge-train entwickelt?** Dann ist der Eingang nur bei dir. Berichte, die merge-train selbst
betreffen, gern als Issue im GitHub-Repo von merge-train einreichen.
