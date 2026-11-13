# Prompt: jira-review-Skill um das Feld „agent“ ergänzen

Für eine Session auf dem WSL-Rechner, in dem Ordner, in dem `~/.claude/skills/jira-review/SKILL.md` liegt.
Voraussetzung: merge-train ist dort per `git pull` auf einem Stand mit dem Feld `agent` (siehe
`docs/agent-hinweise.md`, Abschnitt zur Review-JSON).

```
Passe den jira-review-Skill (~/.claude/skills/jira-review/SKILL.md) an den aktuellen merge-train an.
merge-train will wissen, welcher Agent eine Review-JSON geschrieben hat: oberstes Feld "agent" mit
"<Harness> (<Model>)", z. B. "Copilot (Claude Sonnet 4.5)" – immer derselbe Text, mit dem sich der Agent
auch bei merge-train-Befehlen über --als vorstellt. Das Format steht in docs/agent-hinweise.md im
merge-train-Repo, die Regeln zu --als in skill/merge-train/SKILL.md dort. Lies beides und ergänze den
Skill so, dass er "agent" in jede Review-JSON schreibt und bei merge-train agent pruefen/zeigen --als
übergibt, wenn merge-train ihn nicht aus der Umgebung erkennt. Prüfe außerdem, ob Copilot den
merge-train-Skill findet (install.sh verlinkt ihn nur nach ~/.claude/skills); wenn nicht, sag mir, wo er
für Copilot liegen müsste.
```
