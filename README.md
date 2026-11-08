# merge-train

Merge-Requests im Browser ansehen, so wie der „Changes“-Reiter in GitLab, nur schneller. Zwei Modi:

- **Lokaler Projekt-Diff**: Für alle Repos unter `~/Projects` wird `claude` gegen `reviewed` verglichen. Jedes Projekt ist ein Waggon im Zug.
  „fertig“ setzt `reviewed` auf den gesehenen Stand.
- **GitLab-MR-Review** (über `glab`): Diff eines MR mit eigenen Kommentaren und Agent-Hinweisen.
  „Review abschließen“ legt die Kommentare als **Entwürfe** im MR an. Veröffentlicht wird danach in GitLab.

Ein einzelnes Python-Skript, ohne Abhängigkeiten außer `git` (Syntaxfarben mit `pygments`, GitLab mit `glab`).
Ein kleiner Server auf `127.0.0.1:8771` liefert die Seiten aus und beendet sich nach einer Stunde ohne Anfrage.

## Aufruf

```sh
merge-train                     # lokaler Zug (bei lokal = false: Liste der MRs zum Review)
merge-train myproj              # nur dieses Projekt
merge-train https://gitlab.example.com/gruppe/projekt/-/merge_requests/42
merge-train '!42'               # MR 42 des Projekts im aktuellen Ordner (git remote origin)
merge-train gruppe/projekt!42
merge-train --mrs               # MRs, bei denen ich Reviewer bin
merge-train agent pruefen tasks/PROJ-824-review-markers.json   # siehe docs/agent-hinweise.md
merge-train agent zeigen  tasks/PROJ-824-review-markers.json
```

In bash `'!42'` in Anführungszeichen setzen, sonst greift die History-Expansion.

## GitLab-Review

- **Kommentar schreiben**: Auf eine Zeilennummer klicken (links = alte Zeile, rechts = neue). Speichern mit Strg+Enter, abbrechen mit Esc.
  Allgemeine Kommentare über „＋ allgemeiner Kommentar“.
- **Agent-Hinweise** (lila) stehen an ihrer Zeile. Liegt die Zeile außerhalb des Diffs, stehen sie oben unter „Review“.
  Mit „übernehmen“ oder „anpassen & übernehmen“ werden sie zu einem eigenen Kommentar, „verwerfen“ blendet sie aus.
- **Kommentare** lassen sich bearbeiten und löschen. Das Etikett zeigt den Stand: *Entwurf (lokal)*, *in GitLab (Entwurf)*,
  *geändert* oder *wird in GitLab gelöscht*.
- **Review abschließen → GitLab** legt neue Kommentare als Draft-Notes an, aktualisiert geänderte und löscht entfernte.
  Nichts wird veröffentlicht: In GitLab steht dann „Pending comments“, dort prüfen und das Review abschicken.
  Mehrfaches Abschließen erzeugt keine Duplikate. Einen schon veröffentlichten Kommentar fasst das Tool nicht mehr an.
- Kommentare zu Zeilen außerhalb des Diffs versucht das Tool zuerst als Zeilen-Kommentar. Lehnt GitLab das ab, wird daraus
  ein allgemeiner Kommentar mit Link auf `datei:zeile`.

Der Review-Stand liegt in `~/.local/share/merge-train/reviews/`, der Seiten-Cache in `~/.cache/merge-train/`.

## Einstellungen

`~/.config/merge-train/config.toml`, Vorlage: [`config.example.toml`](config.example.toml). Die wichtigsten Einträge:

| Schlüssel | Standard | Wofür |
|---|---|---|
| `lokal` | `true` | lokaler Projekt-Diff an/aus |
| `gitlab` | `true` | GitLab-Modus an/aus |
| `gitlab_host` | leer | Host, wenn ihn weder URL noch Remote liefern |
| `mr_liste` | `reviewer` | welche MRs der Zug zeigt |
| `hinweise` | `[]` | Globs für Agent-Hinweis-Dateien (automatische Zuordnung über `branch`) |
| `repos` | `{}` | lokale Klone, damit Dateien nicht über die API geholt werden müssen |
| `browser` | leer | Browser-Befehl, unter WSL z. B. `wslview` |

Wird das Skript oder die Einstellungsdatei geändert, startet der Server mit dem neuen Stand neu.

## Auf einen anderen Rechner übertragen (z. B. WSL, nur GitLab)

```sh
git clone git@github.com:Myricaulus/merge-train.git ~/merge-train
~/merge-train/install.sh --nur-gitlab
```

`install.sh` verlinkt `~/.local/bin/merge-train`, legt die Einstellungen mit `lokal = false` an (unter WSL mit `browser = "wslview"`,
wenn vorhanden) und prüft `pygments` und `glab`. Danach:

1. `glab auth login --hostname <gitlab-host>`. Beim Arbeits-GitLab zusätzlich `gitlab_host` eintragen.
2. In `~/.config/merge-train/config.toml` die Einträge `hinweise` (z. B. `"~/workspaces/projekt/tasks/*-review-markers.json"`)
   und `repos` setzen.
3. Unter WSL: `sudo apt install wslu python3-pygments` (`wslview` öffnet den Windows-Browser). Der Server hört auf `127.0.0.1`,
   und WSL2 reicht `localhost` an Windows durch. Klappt das nicht, in `%UserProfile%\.wslconfig` `localhostForwarding=true` setzen.
4. Den Abschnitt aus [`docs/agent-hinweise.md`](docs/agent-hinweise.md) in den jira-review-Skill übernehmen.

Python ≥ 3.8 genügt. Ohne `tomllib` (vor 3.11) liest ein einfacher Ersatzparser die Einstellungen.
Er versteht nur `schlüssel = wert`, `[abschnitt]` und einzeilige Listen.

## Tests

```sh
python3 tests/test_gitlab.py      # GitLab-Modus komplett, mit tests/fake-glab statt GitLab
```

`tests/fake-glab` spielt `glab api` gegen ein lokales Git-Repo nach: MR, Diffs, Commits, Dateien und Draft-Notes.
Mit `--behalten` bleibt der Testordner liegen.
