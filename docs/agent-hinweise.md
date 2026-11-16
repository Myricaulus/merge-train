# Agent-Hinweise in merge-train (für den mr-review-Skill)

Ein Review-Agent schreibt seine Findings nach `tasks/<KEY>-review-markers.json`. merge-train zeigt sie als Hinweise
an ihren Zeilen im MR-Diff. Im Code selbst wird nichts markiert. merge-train liest die Datei nur, schreibt sie nie und
lädt sie neu, sobald sie sich ändert. Wie ein Review-Agent damit arbeitet (Ablauf, gute Kommentartexte), steht im
Skill [`skill/mr-review/SKILL.md`](../skill/mr-review/SKILL.md). Dieses Dokument ist die Referenz für Format und
Ausgaben; der Skill verweist hierher statt sie zu wiederholen.

## Ablauf

Diff, Dateien und Commits kommen nur aus dem lokalen Klon: Stand = Quell-Branch des MR (lokaler Branch, sonst
`origin/…`), Basis = gemeinsamer Vorgänger mit dem Ziel-Branch. Der Branch muss also vorher aktuell sein (fetch,
fast-forward). `pruefen` und `zeigen` holen dabei einmal die MR-Daten aus GitLab (Titel, Beschreibung, Branches, Stand)
und legen sie für die Seite ab – die Seite selbst fragt GitLab nicht.

Nach dem Schreiben bzw. Aktualisieren der Datei (Repo-Root als Arbeitsordner):

```sh
merge-train agent pruefen tasks/<KEY>-review-markers.json
merge-train agent zeigen  tasks/<KEY>-review-markers.json    # Datei beim MR anmelden und MR öffnen (--nicht-oeffnen: nur URL)
```

Erste Zeilen der Ausgabe: MR und Stand, dann `Quelle: lokal (…)`, ggf. `Achtung: GitLab steht auf …, der lokale Branch auf …`.
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
3 = kein lokaler Klon/Branch zum MR, oder der lokale Branch steht nicht auf dem GitLab-Stand (fetch / fast-forward).

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
{"key": "KEY", "agent": "Copilot (Claude Sonnet 4.5)", "branch": "feature/key-…", "reviewed_commit": "1a2b3c4d", "reviewed_at": "2026-11-09",
 "notes": "Themen außerhalb der Story",
 "markers": [
   {"finding": "#3", "title": "Stichpunkte zum Thema", "path": "src/A.cs", "needle": "public void Foo(", "text": "English comment for GitLab",
    "problem": "deutsche Kurzfassung", "decision": "…", "status": "…",
    "see_also": ["src/B.cs:120", {"path": "src/C.cs", "needle": "Foo(", "label": "Aufrufer"},
                 {"path": "src/AKopie.cs", "diff": true, "label": "Kopie"}],
    "rationale": "Belege", "resolved_when": "woran man den Fix erkennt"},
   {"finding": "#7", "text": "General remark (no path → general MR comment)"}]}
```

- `agent` (oben, optional auch je Eintrag): wer die Hinweise geschrieben hat, Harness und Modell, z. B.
  `"Copilot (Claude Sonnet 4.5)"`. Steht auf der Seite am Hinweis („🤖 Copilot (…) #3“) und am übernommenen Kommentar.
  Fehlt das Feld, gilt der Agent, der `pruefen`/`zeigen` aufruft (erkannt aus der Umgebung oder `--als`). Ist keiner
  erkennbar, meldet `pruefen` „Achtung: die JSON nennt kein „agent““.
- `title`: ein paar deutsche Stichpunkte zum Thema für die Kommentarliste links. Ohne `title` zeigt die Liste den Textanfang.
- `text` ist der fertige englische GitLab-Kommentar, ohne Finding-ID (die steht in `finding` und ist nur lokal).
  Querverweise per Datei- oder Klassenname ohne Zeile, die genaue Stelle gehört in `see_also`. Ändert sich `text`, erscheint der
  Eintrag als neuer Hinweis. Schon übernommene Kommentare bleiben erhalten.
- `needle`: Text auf der Zeile im MR-Stand. Mit `=` am Anfang muss er die ganze Zeile treffen. Alternativ `line` (Zahl),
  nur wenn ein needle nicht eindeutig zu machen ist.
- `see_also`: Verweise auf anderen Code (`"pfad"`, `"pfad:zeile"`, `"pfad:von-bis"` oder
  `{"path", "line" | "needle", "end", "label"}`; `end` = letzte Zeile eines Bereichs). merge-train zeigt sie als Links.
  Ein Klick öffnet den Code im Popup, Zeile bzw. Bereich hervorgehoben: liegt die Datei im Diff, deren Diff (aufklappbar),
  sonst den Dateiinhalt.
  Mit `"diff": true` wird daraus ein Dateivergleich (Link mit ⇄): Das Popup zeigt die Datei des Hinweises (`path` des
  Markers) und die verlinkte Datei nebeneinander, Unterschiede markiert, mit ↑/↓ von Unterschied zu Unterschied. Mit
  `"diff": "pfad"` wird stattdessen gegen diese Datei verglichen. Gedacht für Kopien („nahezu identisch zu …“).
  Bereichsvergleich für Code, der nur stellenweise wiederholt wird: `"diff": "pfad:von-bis"` vergleicht nur diesen
  Bereich, und mit `line`/`needle` + `end` am Eintrag nur dessen Bereich, z. B.
  `{"path": "Alt.cs", "line": 27, "end": 62, "diff": "Neu.cs:28-62", "label": "gleiche Prüfungen"}`. Die
  Zeilennummern im Popup bleiben die der Dateien. Ohne Bereich wird wie bisher die ganze Datei verglichen.
  Zeilenangaben (nicht `needle`) beziehen sich auf `reviewed_commit`: Hat sich der Branch seitdem bewegt, rechnet
  merge-train sie auf den MR-Stand um. Ist im Bereich selbst etwas geändert worden, zeigt die Seite ⚠ am Link und
  `pruefen` meldet „siehe auch …: Achtung: …“ (kein Fehler, Exit-Code unverändert).
  Die Verweise gehören **nicht** zum GitLab-Kommentar.
- `problem`, `decision`, `status` und weitere Felder erscheinen unter „Details“, `status` zusätzlich als Etikett.
- Oben optional `"mr": "<MR-URL>"`.

### Zuordnung zum Merge-Request

1. `--mr <URL | !42 | gruppe/projekt!42>` auf der Kommandozeile
2. sonst Feld `"mr"` auf oberster Ebene der JSON
3. sonst der offene MR, dessen Quell-Branch gleich `"branch"` ist

Das Projekt (für `!42` und die Suche nach dem Branch) kommt aus `git remote get-url origin` des Repos, in dem der Agent
arbeitet (cwd), sonst aus dem Repo, in dem die JSON liegt. Sind das zwei verschiedene Repos, sucht `pruefen` den Branch
in beiden. Haben beide einen offenen MR zu dem Branch, bricht es mit „mehrere offene MRs“ ab, statt einen zu raten.
Gibt es zum Branch mehrere offene MRs oder heißt der Branch anders: Feld `"mr"` setzen.

**Repo ohne eigenes `tasks/`** (z. B. ein Submodul-Repo wie server-components): Die JSON kommt nach `tasks/` des Repos, in
dem die Story geführt wird. Darin steht `"mr": "gruppe/projekt!17"` bzw. die MR-URL, und `pruefen`/`zeigen` laufen aus
dem Klon des MR-Repos. Der Klon gilt dann als lokaler Klon des MR.

## Was der Nutzer in merge-train damit macht

- Hinweise stehen an ihrer Zeile im Diff (lila Rand). Liegt die Zeile außerhalb des Diffs, stehen sie oben unter „Review“.
  Ein Klick auf den Ort klappt den Kontext auf und springt hin. Liegt die Datei nicht im Diff, öffnet sich ein Popup.
- Ausgeblendete Zeilen zwischen den Hunks lassen sich nachladen (▼ 20 / ▲ 20 / alle). An diesen Zeilen kann man auch kommentieren.
- „übernehmen“ / „anpassen & übernehmen“ macht aus einem Hinweis einen eigenen Review-Kommentar, „verwerfen“ blendet ihn aus.
- In den Commit-Ansichten („nur dieser“ / „seit diesem“ in der Commit-Liste) stehen die Hinweise an der zurückgerechneten
  Zeile, sonst unter dem Dateinamen. „nur dieser“ ist nur zum Lesen da.
- „Review abschließen → GitLab“ legt alle Kommentare als **Entwürfe** (Draft-Notes) im MR an.
  Veröffentlicht wird erst in GitLab von Hand.
