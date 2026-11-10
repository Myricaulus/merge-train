# merge-train

Merge-Requests im Browser ansehen, so wie der „Changes“-Reiter in GitLab, nur schneller. Jeder Waggon im Zug ist ein
Vergleich Quelle → Ziel in einem lokalen Klon. Die Waggons kommen aus zwei **Quellen** (einzeln an- und abschaltbar,
sind beide an, fahren sie im selben Zug):

- **lokal** (`lokal = true`): Für alle Repos unter `~/Projects` wird `claude` gegen `reviewed` verglichen.
  „fertig ✓“ setzt `reviewed` auf den gesehenen Stand. Fragen und Wünsche zum Code gehen per Klick auf die Zeilennummer
  an Claude, der sie auf `claude` umsetzen darf (siehe [Gespräch mit Claude](#gespräch-mit-claude-lokaler-modus)).
- **GitLab** (`gitlab = true`): ein MR mit eigenen Review-Kommentaren und Agent-Hinweisen. „Review abschließen“ legt
  die Kommentare als **Entwürfe** im MR an, veröffentlicht wird danach in GitLab. Dazu private Fragen an Agenten
  (siehe [Fragen an einen Agenten](#fragen-an-einen-agenten-gitlab-modus)), die nur antworten, nichts ändern.

Es gibt nur eine Seite: Kopf mit Güterbahnhof (Leitstand-Knöpfe aller eingeschalteten Quellen) und Zug, Diff aus dem
lokalen Git (Kontext nachladen, große Dateien auf Klick, Commit-Ansichten), Gespräch an den Zeilen. Was ein Waggon
zusätzlich kann (Review, „fertig“), bestimmt seine Quelle. GitLab wird nur auf Anforderung gefragt
(siehe [GitLab nur auf Knopfdruck](#gitlab-nur-auf-knopfdruck)). Eine weitere Quelle (z. B. GitHub-PRs) wäre eine
weitere Klasse in `src/09_quellen.py`.

Ein einzelnes Python-Skript, ohne Abhängigkeiten außer `git` (Syntaxfarben mit `pygments`, GitLab mit `glab`).
Gebaut wird es aus `src/` (siehe [Entwicklung](#entwicklung)).
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
merge-train agent pruefen tasks/PROJ-824-review-markers.json --seit   # Review-Update seit reviewed_commit
merge-train agent zeigen  tasks/PROJ-824-review-markers.json
merge-train agent feedback [projekt|MR]     # Agent: Fragen/Feedback abholen (lokal oder zu einem MR)
merge-train agent antworten <id> "…" [--erledigt]
merge-train agent horchen [projekt|MR] [--als Name]   # Agent: warten, bis „Feedback/Fragen senden“ gedrückt wird
```

In bash `'!42'` in Anführungszeichen setzen, sonst greift die History-Expansion.

## Gespräch mit Claude (lokaler Modus)

Fragen zum Code oder Änderungswünsche schreibt man direkt an die Zeile, wie ein Review-Kommentar:

1. **Klick auf eine Zeilennummer** (oder „＋ allgemeine Frage“): Die Nachricht ist zunächst ein **Entwurf**.
   Man kann mehrere sammeln, bearbeiten oder löschen.
2. **„Feedback senden“** schickt alle Entwürfe ab. ✓ heißt gesendet, ✓✓ heißt von Claude abgeholt.
3. Claude holt sie mit `merge-train agent feedback` ab (Ort im aktuellen Stand, Code drumherum, Verlauf), beantwortet
   Fragen bzw. setzt Wünsche auf `claude` um und antwortet je Faden mit `merge-train agent antworten <id> "…"`
   (`--erledigt`, wenn umgesetzt). Die Antwort erscheint sofort an der Zeile (die Seite fragt alle 4 s nach),
   dazu eine Desktop-Meldung. Im Zug zeigt der Waggon „💬 n neu“, der Tab-Titel „(n)“.
4. Mit **„↩ antworten“** geht das Gespräch weiter, „✓ erledigt“ schließt einen Faden.

Nach neuen Commits wandern die Fäden mit ihrer Zeile mit. Wurde die Zeile selbst geändert, steht der Faden unter dem
Dateinamen, mit dem damaligen Zeilentext. „fertig“ warnt bei offenen Fäden oder ungesendeten Entwürfen und räumt
erledigte Fäden weg. Offene bleiben für den nächsten Stand.

**Wer bekommt das Feedback?**

- **Eine Claude-Session hört zu**: Läuft in einer Session `merge-train agent horchen` (im Hintergrund), geht das
  Feedback direkt dorthin. Oben steht dann „🎧 Claude hört zu“. Dazu genügt es, der Session zu sagen: „hör auf merge-train“.
  In anderen Repos (z. B. dem Klon eines MR) kennt die Session das über den Claude-Skill `merge-train`
  (`skill/merge-train/SKILL.md`, von `install.sh` nach `~/.claude/skills` verlinkt).
- **Keine hört zu**: „Feedback senden“ legt einen `todo`-Eintrag im Projekt an (mit Startprompt), und das Panel pulsiert.
  „▶ Session starten“ auf der Seite öffnet ihn mit `todo los` (Konsole im Projekt, Enter startet Claude).
  Weitere Nachrichten hängen sich als Notiz an denselben Eintrag. Sind alle Fäden beantwortet, hakt merge-train ihn ab.
- **Eigener Befehl**: `feedback_befehl` in der Einstellung startet stattdessen etwas Eigenes, z. B.
  `feedback_befehl = "konsole --workdir {ordner} -e claude {prompt}"` (Platzhalter `{ordner}`, `{projekt}`, `{prompt}`).

Der Zustand liegt in `~/.local/share/merge-train/lokal/<projekt>.json`.

## GitLab-Review

- **Quelle**: Diff, Dateien und Commits kommen immer aus dem lokalen Klon (`[repos]` oder Repo der Hinweis-Datei):
  Stand = Quell-Branch des MR (lokal, sonst `origin/…`), Basis = gemeinsamer Vorgänger mit dem Ziel-Branch.
  Welcher Branch ausgecheckt ist und lokale Änderungen spielen keine Rolle. Stand GitLab beim letzten Holen woanders,
  sagt das ein Hinweis oben. Die GitLab-API für Diffs wird nicht mehr benutzt.
- **Kontext**: Ausgeblendete Zeilen zwischen den Hunks lassen sich nachladen (▼ 20 / ▲ 20 / alle). Auch dort kann man kommentieren.
  Generierte Dateien (`*.Designer.cs`, `*ModelSnapshot.cs`, Lockfiles …) und sehr große Diffs werden erst auf Klick geladen,
  automatisch, sobald ein Kommentar oder Hinweis darin liegt.
- **Stellwerk** (HUD) rechts im Güterbahnhof, auf Stelzen über dem Gleis: LED (grün: Server läuft, rot: nicht erreichbar,
  gelb: neuer Server, die Seite lädt gleich neu), Stand von merge-train (letzter Commit mit Zeit, `*` = Änderungen in
  `src/` noch nicht committet), wer zuhört, Zahl der Kommentare, Hinweise und KI-Threads (offen = nicht erledigt; in der
  Liste „KI-Threads“ schließt ein Klick auf ○ einen Thread). Meldungen des Servers erscheinen als Toasts (10 s, wegklickbar), die letzten 50 unter 🔔 unten rechts.
- **Kommentarlisten** links über den Dateien, in Datei-Reihenfolge: „GitLab-Kommentare“ (offene Agent-Hinweise 🤖,
  eigene bzw. übernommene Kommentare 💬) und „KI-Threads“ (Gespräche mit Agenten, privat). Leere Listen sind ausgeblendet.
  Die Reihenfolge der GitLab-Kommentare ist die Sende-Reihenfolge bei „Review abschließen“: nach Datei und Zeile, mit
  „⇅ sortieren“ per Drag & Drop oder ⤒/⤓ (ganz nach oben/unten) änderbar. Sie wird beim MR gespeichert, Neues landet
  an seiner Stelle nach Datei und Zeile, ein übernommener Hinweis behält seinen Platz. Ein Klick springt zum Kommentar und klappt dafür bei Bedarf Kontext oder Datei auf.
- **Commit-Ansichten** (auch im lokalen Projekt-Diff): Unter „Beschreibung & Commits“ hat jeder Commit zwei Knöpfe.
  - *nur dieser*: Diff dieses einen Commits, **nur lesen**. Kommentare und Hinweise werden auf den Stand nach dem
    Commit zurückgerechnet und stehen an ihrer Zeile. Geht das nicht (Zeile später geändert, alte Seite des MR, außerhalb
    der Änderungen), stehen sie unter dem Dateinamen mit dem Grund.
  - *seit diesem*: alles nach dem Commit bis zum MR-Stand. Rechts steht der MR-Stand, dort wird normal kommentiert und
    übernommen. Links (Stand des Commits) lässt sich nicht kommentieren.
  - Einträge in Dateien, die die Ansicht nicht ändert, werden nur gezählt. Kommentare gehören immer zum ganzen MR.
- **Kommentar schreiben**: Auf eine Zeilennummer klicken (links = alte Zeile, rechts = neue). Speichern mit Strg+Enter, abbrechen mit Esc.
  Allgemeine Kommentare über „＋ allgemeiner Kommentar“.
- **Agent-Hinweise** (lila) stehen an ihrer Zeile. Liegt die Zeile außerhalb des Diffs, stehen sie oben unter „Review“.
  Ein Klick auf den Ort klappt den Kontext dorthin auf (oder öffnet ein Popup, wenn die Datei nicht im MR ist).
  „Siehe auch“-Verweise öffnen den Code im Popup, die Zeile bzw. der Bereich (`pfad:10-20`) ist hervorgehoben.
  Liegt die Datei im Diff, zeigt das Popup deren Diff (Lücken aufklappbar, „alles aufklappen“), sonst den Dateiinhalt
  (mehr laden / ganze Datei). Die Verweise gehören nicht zum GitLab-Kommentar.
  Mit „übernehmen“ oder „anpassen & übernehmen“ werden Hinweise zu einem eigenen Kommentar, „verwerfen“ blendet sie aus.
- **Kommentare** lassen sich bearbeiten und löschen. Das Etikett zeigt den Stand: *Entwurf (lokal)*, *in GitLab (Entwurf)*,
  *geändert* oder *wird in GitLab gelöscht*.
- **Review abschließen → GitLab** legt neue Kommentare als Draft-Notes an, aktualisiert geänderte und löscht entfernte.
  Nichts wird veröffentlicht: In GitLab steht dann „Pending comments“, dort prüfen und das Review abschicken.
  Mehrfaches Abschließen erzeugt keine Duplikate. Einen schon veröffentlichten Kommentar fasst das Tool nicht mehr an.
- Kommentare zu Zeilen außerhalb des Diffs versucht das Tool zuerst als Zeilen-Kommentar. Lehnt GitLab das ab, wird daraus
  ein allgemeiner Kommentar mit Link auf `datei:zeile`.

Der Review-Stand liegt in `~/.local/share/merge-train/reviews/`, der Seiten-Cache in `~/.cache/merge-train/`.

## Fragen an einen Agenten (GitLab-Modus)

Auch zu einem MR kann man einen Agenten fragen (Claude, Copilot …), wie im lokalen Modus, nur privat:
Im Kommentar-Editor gibt es neben „als Review-Kommentar“ je Agent einen Knopf **„an <Name>“**. Solche Fragen liegen
als eigene Fäden in der Review-Datei des MR und gehen **nie** nach GitLab („Review abschließen“ überspringt sie).
„Fragen senden“ schickt die Entwürfe ab, die Antworten erscheinen als Gespräch an der Zeile.

Aktiv sind die Knöpfe nur für Agenten aus `[agenten]` in der Einstellung oder wenn gerade einer zuhört (sonst ausgegraut):

```toml
[agenten]
Copilot = "wt.exe -w 0 nt --title Copilot wsl.exe -e bash -lc 'cd {ordner} && copilot -i \"$0\"' {prompt}"   # Beispiel, anpassen
```

„Fragen senden“ startet den Befehl (Platzhalter `{ordner}` = Klon, `{projekt}`, `{prompt}`), sofern nicht schon jemand
zuhört. Der Agent braucht nur die Shell, Befehle wie im lokalen Modus, mit der MR-Kennung aus dem Prompt (im Klon geht
es auch ohne):

```sh
merge-train agent feedback gitlab.example.com/gruppe/projekt/42   # oder im Klon: merge-train agent feedback
merge-train agent antworten <id> "…"
merge-train agent kommentar <h:key | Kommentar-id | Faden-id> "…"   # GitLab-Kommentar umformulieren (siehe unten)
merge-train agent horchen gitlab.example.com/gruppe/projekt/42 --als Copilot   # Seite zeigt „🎧 Copilot hört zu“
```

Bittet man im Faden, einen GitLab-Kommentar umzuformulieren, landet die Änderung im Kommentar selbst: `feedback` zeigt
unter jedem Faden die Kommentare und Agent-Hinweise an dessen Zeile. `agent kommentar h:<key>` ändert einen noch nicht
übernommenen Agent-Hinweis (dessen `text` in der Review-JSON). Bei einem bestehenden Kommentar oder einer Faden-id legt
es einen neuen Agent-Hinweis an derselben Stelle an. Review-Kommentare entstehen nur durch „übernehmen“: Der Agent
legt nie selbst welche an, und der alte Kommentar bleibt, bis man ihn selbst löscht.

## GitLab nur auf Knopfdruck

Beim Öffnen oder Neuladen einer Seite fragt merge-train GitLab nicht. MR-Daten (Titel, Beschreibung, Branches,
GitLab-Stand) und die MR-Liste für den Zug liegen im Cache. Geholt wird nur:

- von `merge-train agent pruefen|zeigen` (macht der jira-review-Skill, wenn er den Branch aktualisiert hat) und `merge-train <MR>`,
- im **Güterbahnhof** links vom Zug: „↻ MRs“ (offene MRs, bei denen ich Reviewer bin) und „↻ MR-Daten“ (dieser MR),
- beim **Review abschließen**: aktueller GitLab-Stand (steht GitLab woanders als die Seite, wird nichts übertragen),
  dann die Draft-Notes.

## Einstellungen

`~/.config/merge-train/config.toml`, Vorlage: [`config.example.toml`](config.example.toml). Die wichtigsten Einträge:

| Schlüssel | Standard | Wofür |
|---|---|---|
| `lokal` | `true` | Quelle „lokal“ (Projekt-Diff `claude` → `reviewed`) an/aus |
| `projekte` | `~/Projects` | Ordner mit Repos oder Liste aus Ordnern/einzelnen Repos für „lokal“ |
| `von`, `bis` | `reviewed`, `claude` | „lokal“ vergleicht `bis` gegen `von`. `bis = "arbeitsstand"`: das Arbeitsverzeichnis samt nicht Committetem (z. B. was ein Agent gerade baut) gegen `von = "origin/main"`; Index und Branch bleiben unberührt, „fertig“ gibt es dann nicht |
| `gitlab` | `true` | Quelle „GitLab“ (MRs) an/aus |
| `gitlab_host` | leer | Host, wenn ihn weder URL noch Remote liefern |
| `mr_liste` | `reviewer` | welche MRs der Zug zeigt |
| `hinweise` | `[]` | Globs für Agent-Hinweis-Dateien (automatische Zuordnung über `branch`) |
| `repos` | `{}` | lokale Klone der GitLab-Projekte (Diff und Dateien kommen nur von dort) |
| `browser` | leer | Browser-Befehl, unter WSL z. B. `wslview` |
| `[agenten]` | leer | Agenten für Fragen zum MR: Name = Startbefehl (siehe [Fragen an einen Agenten](#fragen-an-einen-agenten-gitlab-modus)) |
| `log_tage` | `7` | Log der Anfragen an die Quellen (lokales git, GitLab) mit Dauer und Anlass, eine Datei je Tag in `~/.cache/merge-train/aussen-<datum>.log`; so viele Tage aufbewahrt, `0` = aus |

Wird das Skript oder die Einstellungsdatei geändert, startet der Server mit dem neuen Stand neu.

## Auf einen anderen Rechner übertragen (z. B. WSL, nur GitLab)

```sh
git clone git@github.com:Myricaulus/merge-train.git ~/merge-train
~/merge-train/install.sh --nur-gitlab
```

`install.sh` baut `merge-train`, richtet die Git-Hooks fürs Neubauen ein, verlinkt `~/.local/bin/merge-train`, legt die Einstellungen mit `lokal = false` an (unter WSL mit `browser = "wslview"`,
wenn vorhanden) und prüft `pygments` und `glab`. Danach:

1. `glab auth login --hostname <gitlab-host>`. Beim Arbeits-GitLab zusätzlich `gitlab_host` eintragen.
2. In `~/.config/merge-train/config.toml` die Einträge `hinweise` (z. B. `"~/workspaces/projekt/tasks/*-review-markers.json"`)
   und `repos` setzen.
3. Unter WSL: `sudo apt install wslu python3-pygments` (`wslview` öffnet den Windows-Browser). Der Server hört auf `127.0.0.1`,
   und WSL2 reicht `localhost` an Windows durch. Klappt das nicht, in `%UserProfile%\.wslconfig` `localhostForwarding=true` setzen.
4. Der jira-review-Skill arbeitet mit `merge-train agent …` (Format und Ausgaben: [`docs/agent-hinweise.md`](docs/agent-hinweise.md)).
   Im Code werden keine Marker mehr gesetzt.

Python ≥ 3.8 genügt. Ohne `tomllib` (vor 3.11) liest ein einfacher Ersatzparser die Einstellungen.
Er versteht nur `schlüssel = wert`, `[abschnitt]` und einzeilige Listen.

## Entwicklung

Der Code liegt in `src/`: die Python-Abschnitte als `src/NN_name.py` (in dieser Reihenfolge aneinandergehängt),
CSS und JS in `src/web/`. Dort eingebettet über `NAME = r"""@einbetten web/datei.js@"""`.

```sh
./bauen            # src/ → merge-train (schreibt nur bei Änderung; der laufende Server startet dann neu)
./bauen --pruefen  # Exit 1, wenn merge-train nicht zu src/ passt
```

`merge-train` ist das gebaute Ergebnis und nicht eingecheckt (`.gitignore`). `~/.local/bin/merge-train` zeigt darauf.
`install.sh` richtet Git-Hooks ein (post-merge, post-checkout, post-rewrite), die danach `./bauen` ausführen.
Ein `git pull` genügt also weiterhin zum Aktualisieren.

## Tests

```sh
python3 tests/test_gitlab.py      # GitLab-Modus komplett, mit tests/fake-glab statt GitLab
```

`tests/fake-glab` spielt `glab api` gegen ein lokales Git-Repo nach: MR, Diffs, Commits, Dateien und Draft-Notes.
Mit `--behalten` bleibt der Testordner liegen.
