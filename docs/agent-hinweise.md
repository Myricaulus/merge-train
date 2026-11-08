# Agent-Hinweise in merge-train (für den jira-review-Skill)

Ein Review-Agent schreibt seine Findings nach `tasks/<KEY>-review-markers.json`. merge-train zeigt sie als Hinweise
an ihren Zeilen im MR-Diff. Im Code selbst wird nichts markiert. merge-train liest die Datei nur, schreibt sie nie und
lädt sie neu, sobald sie sich ändert. Wie der Skill damit arbeitet, steht in `~/.claude/skills/jira-review/SKILL.md`
(Abschnitt „Review JSON and merge-train“).

## Ablauf

Der Klon muss auf dem Quell-Branch des MR stehen, genau auf dem MR-Stand und ohne lokale Änderungen
(`git status --untracked-files=no` leer). Dann kommen Diff und Dateien aus dem Klon. Das ist schneller und vollständig,
denn GitLab liefert bei großen MRs für viele Dateien keinen Diff. Passt der Klon nicht, nimmt merge-train die GitLab-API
und nennt den Grund.

Nach dem Schreiben bzw. Aktualisieren der Datei (Repo-Root als Arbeitsordner):

```sh
merge-train agent pruefen tasks/<KEY>-review-markers.json
merge-train agent zeigen  tasks/<KEY>-review-markers.json    # Datei beim MR anmelden und MR öffnen (--nicht-oeffnen: nur URL)
```

Erste Zeilen der Ausgabe: MR und Stand, dann `Quelle: lokal (…)` oder `Quelle: GitLab-API – lokal nicht möglich: …`.
Danach eine Zeile pro Eintrag:

| Ausgabe | Bedeutung | Was tun |
|---|---|---|
| `im Diff` | Zeile liegt im Diff, wird ein Zeilen-Kommentar | nichts |
| `Zeile außerhalb des Diffs → …` | Datei ist im Diff, die Zeile nicht | ok. In merge-train lässt sich der Kontext aufklappen. In GitLab wird es zuerst als Zeilen-Kommentar versucht, sonst wird ein allgemeiner Kommentar mit Link daraus |
| `Datei nicht im Diff → …` | Datei gehört nicht zum MR | ok, allgemeiner Kommentar mit Link |
| `allgemeiner MR-Kommentar` | Eintrag ohne `path` | ok |
| `FEHLT: needle nicht gefunden` | needle passt auf keine Zeile im MR-Stand | needle korrigieren |
| `FEHLT: Datei nicht im MR-Stand` | Pfad gibt es im MR-Stand nicht | `path` prüfen (relativ zum Repo-Root, `/` als Trenner) |
| `siehe auch …: FEHLT: …` | ein `see_also`-Eintrag passt nicht | Pfad/needle/Zeile korrigieren |
| `(needle passt N×)` | needle trifft mehrere Zeilen | gewollt? Sonst needle genauer oder mit `=` |

Exit-Code: 0 = alles passt, 1 = etwas `FEHLT`, 2 = Datei nicht lesbar oder kein MR zuzuordnen,
3 = alles gefunden, aber der lokale Klon passt nicht (Diff kam über die API).

### Review-Update: `--seit`

```sh
merge-train agent pruefen tasks/<KEY>-review-markers.json --seit          # seit reviewed_commit der JSON
merge-train agent pruefen tasks/<KEY>-review-markers.json --seit 1a2b3c4d # seit einem anderen Commit
```

| Ausgabe | Bedeutung |
|---|---|
| `WEG` | Datei gibt es nicht mehr → Diff gegen `resolved_when` prüfen |
| `GEÄNDERT` | needle nicht mehr gefunden → Diff gegen `resolved_when` prüfen |
| `offen*` | Zeile noch da, Datei aber geändert → Fix steckt evtl. woanders in der Datei |
| `offen` | Datei unverändert |

Mit `--seit` sind weggefallene needles kein Fehler (Exit 1 nur bei kaputten `see_also`-Einträgen).

## Format

```json
{"key": "KEY", "branch": "feature/key-…", "reviewed_commit": "1a2b3c4d", "reviewed_at": "2026-11-09",
 "notes": "Themen außerhalb der Story",
 "markers": [
   {"finding": "#3", "title": "Stichpunkte zum Thema", "path": "src/A.cs", "needle": "public void Foo(", "text": "#3 English comment for GitLab",
    "problem": "deutsche Kurzfassung", "decision": "…", "status": "…",
    "see_also": ["src/B.cs:120", {"path": "src/C.cs", "needle": "Foo(", "label": "Aufrufer"}],
    "rationale": "Belege", "resolved_when": "woran man den Fix erkennt"},
   {"finding": "#7", "text": "#7 General remark (no path → general MR comment)"}]}
```

- `title`: ein paar deutsche Stichpunkte zum Thema für die Kommentarliste links. Ohne `title` zeigt die Liste den Textanfang.
- `text` ist der fertige englische GitLab-Kommentar und beginnt mit der Finding-ID. Ändert sich `text`, erscheint der
  Eintrag als neuer Hinweis. Schon übernommene Kommentare bleiben erhalten.
- `needle`: Text auf der Zeile im MR-Stand. Mit `=` am Anfang muss er die ganze Zeile treffen. Alternativ `line` (Zahl),
  nur wenn ein needle nicht eindeutig zu machen ist.
- `see_also`: Verweise auf anderen Code (`"pfad"`, `"pfad:zeile"` oder `{"path", "line" | "needle", "label"}`).
  merge-train zeigt sie als Links. Ein Klick öffnet den Code im Popup (nachladbar, mit Link nach GitLab).
  Die Verweise gehören **nicht** zum GitLab-Kommentar.
- `problem`, `decision`, `status` und weitere Felder erscheinen unter „Details“, `status` zusätzlich als Etikett.
- Oben optional `"mr": "<MR-URL>"`.

### Zuordnung zum Merge-Request

1. `--mr <URL | !42 | gruppe/projekt!42>` auf der Kommandozeile
2. sonst Feld `"mr"` auf oberster Ebene der JSON
3. sonst der offene MR, dessen Quell-Branch gleich `"branch"` ist (Projekt aus `git remote get-url origin`)

Gibt es zum Branch mehrere offene MRs oder heißt der Branch anders: Feld `"mr"` setzen.

## Was der Nutzer in merge-train damit macht

- Hinweise stehen an ihrer Zeile im Diff (lila Rand). Liegt die Zeile außerhalb des Diffs, stehen sie oben unter „Review“.
  Ein Klick auf den Ort klappt den Kontext auf und springt hin. Liegt die Datei nicht im Diff, öffnet sich ein Popup.
- Ausgeblendete Zeilen zwischen den Hunks lassen sich nachladen (▼ 20 / ▲ 20 / alle). An diesen Zeilen kann man auch kommentieren.
- „übernehmen“ / „anpassen & übernehmen“ macht aus einem Hinweis einen eigenen Review-Kommentar, „verwerfen“ blendet ihn aus.
- „Review abschließen → GitLab“ legt alle Kommentare als **Entwürfe** (Draft-Notes) im MR an.
  Veröffentlicht wird erst in GitLab von Hand.
