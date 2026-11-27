# Eine Art „Branch“ (Schritt 5 aus `ein-waggon.md`): Bauplan

*Mit dem Nutzer abgestimmt am 27.11.2026, noch nicht gebaut. Ersetzt den Verweis aus Schritt 4a (`branch-akte.md`).*

## Ziel

merge-train kennt für Code nur noch **eine** Art Waggon: einen Branch eines Repos. Ein GitLab-MR (später ein GitHub-PR)
ist eine **Schicht** auf diesem Branch: Er bringt Diskussionen, Agent-Hinweise, Review-Kommentare und „Review
abschließen“ mit. Ohne MR bleibt es beim Diff, den Fäden und „fertig“. Ob ein Branch einen MR hat, weiß merge-train
erst, wenn MR-Daten geholt sind („↻ MRs“, „MR-Daten holen“, `agent zeigen`): Dann schaltet die Akte des Quell-Branches
die Kommentare der Quelle frei. Der Myrling bleibt eine eigene Art (Läufe sind
Skripte, keine Branches).

Warum: Zwei Arten für denselben Branch brauchen Code, der sie wieder zusammenführt (zusammenlegen, ausblenden, Verweis,
Seiten-Felder tauschen, Fäden umziehen, zwei Seiten, zwei Zug-Bauer). Das bläht das Projekt auf und macht jede Änderung
doppelt.

## Regeln

- **Ein Repo ist sein origin.** Repo-Kennung = Projektpfad aus origin (`gruppe/projekt`, ohne Host: SSH-Aliasse und
  https nennen den Host verschieden, GitLab nennt ihn noch einmal anders). Ohne origin: der Projektname des Ordners.
- **Waggon = (Repo, Branch).** Kennung `gruppe/projekt@branch`, Name `projekt@branch`, Seite `/b/<Kennung>`.
- **Ein Branch ist eine Akte**, in allen Klonen und Worktrees desselben Repos. Klone eines Repos: die Repos unter
  `projekte`, `[repos]`, `klon_ordner`, die in Akten gemerkten und ihre Worktrees (`git worktree list`).
- **Arbeitsstand nur aus dem Haupt-Klon** des Repos: dem Eintrag in `[repos]`, ohne ihn dem Repo unter `projekte`
  (kein Worktree), sonst dem ersten gefundenen. Ist der Branch dort ausgecheckt, gelten die Arbeitsstand-Regeln aus
  `ein-waggon.md`. Sonst zeigt der Waggon den Commit-Stand: aus dem Haupt-Klon, wenn er den Branch hat (lokal, sonst
  `origin/<branch>`), sonst aus dem ersten Klon oder Worktree, der ihn hat.
- **Abkürzungen** (Eingabe, alte Links), alle lösen auf einen Branch-Waggon auf:
  - `projekt:<name>` und `/<name>.html`: der Branch, den das Projekt (der Ordner) gerade zeigt (bis bzw. beim
    Arbeitsstand der ausgecheckte).
  - MR-Kennung `host/gruppe/projekt/42`, MR-URL, `!42`, `/mr/…`: der Branch, dessen Akte diesen MR trägt (`gitlab`).
    Trägt ihn noch keine, bietet der Güterbahnhof wie heute „MR-Daten holen“ an. Das Holen liefert den Quell-Branch und
    schreibt die MR-Daten gleich in dessen Akte (es gibt keine Akte je MR).
- **von:** mit MR der Ziel-Branch, sonst `von` des Projekts (pro Ordner, wie heute in `lokal/<projekt>.json`).
- **kann:** `review` = hat einen MR; `fertig` = kein MR, von ist ein lokaler Branch, kein Arbeitsstand;
  `committen` = kein MR oder eigener MR.

## Ablage

- `zweige/<quote(repo)>/<quote(branch)>.json`: **die** Akte des Branches. Felder wie heute; `mr` wird `{repo, branch}`.
  Die MR-Schicht liegt flach daneben wie heute in der MR-Akte (`meta`, `diskussionen`, Review-Kommentare, `hinweise` …),
  dazu `gitlab` = `{host, projekt, iid}` des aktuellen MR. Keine `seiten`, kein Verweis.
- Neuer MR für denselben Branch (anderer iid): die Felder der alten MR-Schicht gehen als Kopie nach
  `zweige/<repo>/archiv/`, die Fäden bleiben.
- Begleitdateien (`.horcht`, `.prompt`, `.seite`, `.agent`) neben der Akte des Branches: ein Zuhörer je Branch.
- `lokal/<projekt>.json` bleibt die Projekt-Akte des Ordners (`zweige` = von/bis, Marker der Migration).
- Aufräumen wie in 4a (gelöscht oder in von gemergt → `archiv/`), dazu: Branch mit geschlossenem MR, der weg ist.

## Was wegfällt

`LokalArt`, `MrArt`, die Quellen-Klassen `Lokal` und `GitLab` in ihrer heutigen Form, `ein_waggon`, `zusammengelegt`,
`im_mr_waggon`, `klon_mrs`, `mrs_mit_klon`, `zweig_verknuepfen`, `verweis_ziel`, `_seite_tauschen`, `SEITEN_FELDER`,
`seiten`, `andere_zweig_akten` mit Verweisen, `entwicklung_ziel`/`review_ziel` (es gibt nur noch einen Waggon je
Klon und Branch), der getrennte Zugbau (`lokal_wagen`, `mr_wagen`), die getrennten Seiten `projekt_seite`/`mr_seite`
und Routen `*.html`/`mr/…` (nur noch als Weiterleitung).

## Bauplan

**5a Identität und Akte**
- `repo_kennung(klon)` (`git.py`), `repo_klone(repo)` (alle bekannten Klone), `branch_klon(repo, branch)` (Regel oben,
  je Prozess gemerkt).
- `Waggon(repo, branch)` bzw. `Waggon(myrling)`, eine `BranchArt` in `waggon.py`; `Waggon.aus_id` mit den Abkürzungen.
- `akte_datei` für Branch-Waggons; `waggon.gitlab` = MR der Schicht (aus der Akte) für alle GitLab-Aufrufe, die heute
  `mr.host`/`mr.projekt`/`mr.iid` lesen (`gitlab.py`, `review.py`, `hinweise.py`, `agent_cli.py`).
- `repo_haupt_klon(repo)` (Regel oben); Arbeitsstand (`eigener_arbeitsstand`, Beobachter) nur dort.
- `mr_meta_holen` schreibt in die Akte des Quell-Branches (Repo aus dem MR-Projektpfad) und setzt dort `gitlab`.
- Migration einmal beim Start: `reviews/*.json` mit Quell-Branch und die Branch-Akten aus 4a nach
  `zweige/<repo>/<branch>.json` (gleicher Branch: nach id vereinigen), Verweise löschen, Begleitdateien mitnehmen.
  MR-Akten ohne MR-Daten (Quell-Branch unbekannt) tragen nur Hinweis-Status und angemeldete Review-JSONs: Die kommen
  beim ersten „MR-Daten holen“ dazu, bis dahin bleibt die Datei liegen. Vorher `DATEN/` nach `DATEN/vor-schritt-5/`
  kopieren.

**5b Eine Quelle, eine Seite**
- Quelle `Branch` mit Schichten (`GitLab`, später `GitHub`); `ort`, `ziel`, `branch`, `prompt`, `zeilen_stand` je
  nach Schicht statt je Art.
- `branch_seite(waggon)` aus `projekt_seite` und `mr_seite`: gleicher Diff-Bau, die Schicht liefert Kopf, Diskussionen,
  Review-Knöpfe (`knoepfe_mehr`).
- Beobachter und Arbeitsstand (`eigener_arbeitsstand`) über den Klon des Branches statt über die Art.

**5c Zug und Server**
- Ein Zugbau: je Projekt der Branch, den es zeigt; je MR aus der MR-Liste sein Quell-Branch; gleiche Kennung = ein
  Waggon.
- Routen `b/<Kennung>`; `*.html`, `mr/…`, `mr-oeffnen` leiten weiter. `api/projekt` (von/bis) über den Ordner des
  Klons.
- `web/*.js`: Kennung statt `projekt:`/MR-Pfad, sonst nur `kann`.

**5d Agent, Doku, Tests**
- `gespraech_ziele`: im Klon der Branch, den er zeigt (plus Myrling-Läufe des Repos); `status`, `feedback`, `horchen`
  ohne Sonderfälle für „zusammengelegt“.
- Tests: Pfade (`reviews/…`, `lokal/proj.horcht`) und Kennungen in `test_gitlab.py`, `test_ui.py`, `test_einheiten.py`
  umstellen; neue Teile für Migration, zwei Klone eines Repos, Abkürzungen.
- `docs/funktionen.md`, `glossar.md` (Waggon, Art, Schicht, Repo-Kennung), README („Wo liegt was“), Skill
  `merge-train` (Kennungen), `ein-waggon.md`; `branch-akte.md` auf den Rest von 4a (Aufräumen, Migration) kürzen.

Jeder Teil ist ein eigener Commit mit grünem Hook; 5a und 5b gehören eng zusammen, weil die Seiten an der Art hängen.

## Auf dem Laptop testen (nach Schritt 5)

Vorher `DATEN/` sichern (die Migration legt zusätzlich `DATEN/vor-schritt-5/` an).
- Zug: Jeder Branch steht einmal da, auch wenn er in zwei Klonen liegt oder einen MR hat.
- Alte Lesezeichen (`/<projekt>.html`, `/mr/…`, MR-URL in `merge-train agent …`) landen auf dem Branch.
- Eigener MR, fremder MR, Branch ohne MR: wie in den Listen „Nach Schritt 3“ und „Nach Schritt 4a“ in `branch-akte.md`.
- Worktree oder zweiter Klon desselben Repos: dieselben Fäden; den Arbeitsstand zeigt nur der Haupt-Klon (`[repos]`).
- Branch, für den noch keine MR-Daten geholt sind: keine GitLab-Kommentare; nach „↻ MRs“ bzw. „MR-Daten holen“ sind sie
  da, die Fäden bleiben.
- Neuer MR für einen Branch, der schon einen hatte: Fäden bleiben, alte Diskussionen liegen im Archiv.
