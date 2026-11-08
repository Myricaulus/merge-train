# Agent-Hinweise in merge-train anzeigen (für den jira-review-Skill)

Dieser Abschnitt ist zum Übernehmen in `~/.claude/skills/jira-review/SKILL.md` gedacht.
Das JSON-Format bleibt, wie es ist (`tasks/<KEY>-review-markers.json`, wie im jira-review-Skill beschrieben).
merge-train liest die Datei nur, schreibt sie nie und lädt sie neu, sobald sie sich ändert.

---

## Review in merge-train anzeigen

Nach dem Schreiben bzw. Aktualisieren von `tasks/<KEY>-review-markers.json` (Repo-Root als Arbeitsordner):

```sh
merge-train agent pruefen tasks/<KEY>-review-markers.json
```

Die Ausgabe zeigt pro Eintrag, auf welche Zeile des aktuellen MR-Stands der Eintrag fällt:

| Ausgabe | Bedeutung | Was tun |
|---|---|---|
| `im Diff` | Zeile liegt im Diff, wird ein Zeilen-Kommentar | nichts |
| `Zeile außerhalb des Diffs → …` | Datei ist da, Zeile aber nicht im Diff | ok, wird allgemeiner MR-Kommentar mit Link auf die Zeile |
| `Datei nicht im Diff → …` | Datei gehört nicht zum MR | ok, wie oben |
| `FEHLT: needle nicht gefunden` | needle passt auf keine Zeile im **MR-Stand** (nicht im lokalen Checkout!) | needle korrigieren |
| `FEHLT: Datei nicht im MR-Stand` | Pfad gibt es im MR-Stand nicht | `path` prüfen (relativ zum Repo-Root, `/` als Trenner) |
| `(needle passt N×)` | needle trifft mehrere Zeilen | gewollt? Sonst needle genauer oder mit `=` |

Exit-Code 1, sobald etwas `FEHLT`; Exit-Code 2, wenn die Datei nicht lesbar ist oder kein MR zugeordnet werden kann.

Wenn alles passt, die Datei beim MR anmelden und den MR öffnen:

```sh
merge-train agent zeigen tasks/<KEY>-review-markers.json
```

(`--nicht-oeffnen` gibt nur die URL aus.)

### Zuordnung zum Merge-Request

In dieser Reihenfolge:

1. `--mr <URL | !42 | gruppe/projekt!42>` auf der Kommandozeile
2. optionales Feld `"mr"` auf oberster Ebene der JSON (MR-URL), z. B.
   `"mr": "https://gitlab.example.com/gruppe/projekt/-/merge_requests/42"`
3. sonst der offene MR, dessen Quell-Branch gleich `"branch"` ist (Projekt aus `git remote get-url origin`)

Wenn es zum Branch mehrere offene MRs gibt oder der Branch anders heißt: Feld `"mr"` setzen.

### Optionale Zusatzfelder

Alles optional, ältere Dateien bleiben gültig:

- oben: `"mr"` (siehe oben)
- pro Marker: `"line"` (Zahl, Zeile im MR-Stand). Damit wird die Zeile direkt genommen statt per `needle` gesucht.
  Nur nehmen, wenn ein needle nicht eindeutig zu machen ist.
- pro Marker: `"problem"` (deutsche Kurzfassung), `"decision"`, `"status"`, `"placement"`. Diese Felder werden in merge-train
  unter „Details“ angezeigt, `status` zusätzlich als Etikett.

### Was der Nutzer in merge-train damit macht

- Hinweise erscheinen an der Zeile im Diff (lila Rand) bzw. oben unter „Review“, wenn sie außerhalb des Diffs liegen.
- „übernehmen“ / „anpassen & übernehmen“ macht daraus einen eigenen Review-Kommentar, „verwerfen“ blendet ihn aus.
- „Review abschließen → GitLab“ legt alle Kommentare als **Entwürfe** (Draft-Notes, wie „Review starten“) im MR an.
  Veröffentlicht wird erst in GitLab von Hand.

Deshalb:

- `text` bleibt der fertige englische Kommentar für GitLab, beginnend mit der Finding-ID.
- Die Code-Marker (`mark_review.py`) braucht es für die Anzeige in merge-train nicht. Sie schaden aber auch nicht,
  denn merge-train entfernt einen gesetzten Marker (`// <tag> …`) vor dem needle-Vergleich.
- Beim Review-Update die JSON wie bisher komplett neu schreiben und danach wieder `merge-train agent pruefen …` aufrufen.
  Die offene Seite aktualisiert sich von selbst. Schon übernommene Kommentare bleiben im Tool erhalten.
  Ändert sich `text` eines Eintrags, erscheint er als neuer Hinweis.
