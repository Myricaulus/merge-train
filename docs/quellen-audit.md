# GitLab-Aufrufe nach Herkunft: Analyse und geplantes Audit

Stand: 2026-11-13, Commit `de44115` (Branch `claude`). Analyse aus dem Code, gegengeprüft mit dem Außen-Log
`~/.cache/merge-train/aussen-*.log` vom 10.–13.11. Das Log zeigte genau diese Kombinationen und keine anderen.

## Anlass

Grundsatz laut README („GitLab nur auf Knopfdruck“): GitLab wird nur auf Anforderung gefragt. Die README zählt dazu
aber auch `merge-train agent pruefen|zeigen`. Laut Nutzer sind Syntaxprüfungen eines Agenten **keine**
Nutzer-Interaktion. Heute fragen beide Befehle GitLab bei jedem Lauf. Ist GitLab nicht erreichbar, scheitern sie
(`mr_fuer_hinweise`, `agent_cli.py`), obwohl die Prüfung selbst rein lokal ist und die Akte alle MR-Daten im Cache hat.

## Ist-Stand: Aufrufe je Herkunft

Abkürzung: `…/mr` = `projects/<projekt>/merge_requests/<iid>`. Listen holt `alle()` seitenweise mit
`?per_page=100&page=<n>`. Alle Aufrufe laufen über `glab()` in `gitlab.py`.

### CLI `merge-train agent pruefen <json>` / `merge-train agent zeigen <json>` (gleich)
Code: `befehl_hinweise` → `mr_fuer_hinweise` (`agent_cli.py`), dann `mr_meta_holen` (`gitlab.py`).
- `GET projects/<projekt>/merge_requests?state=opened&source_branch=<branch>`: nur, wenn weder `--mr` noch „mr“ in der JSON steht.
- `GET …/mr` über den Standard-Host von glab (`mr_vollstaendig`): nur, wenn der MR ohne Host angegeben ist und weder `gitlab_host` noch ein Remote ihn liefern.
- `GET …/mr` (`mr_meta_holen`): **immer**.

### CLI `merge-train <MR-URL | !42 | gruppe/projekt!42>`
Code: `cli.py`, nur mit `gitlab = true`.
- `GET …/mr` über den Standard-Host: nur bei einem MR ohne Host.
- `GET …/mr`: immer.

### Startseite, Formular „MR öffnen“ (Route `mr-oeffnen`)
- `GET …/mr` über den Standard-Host: nur bei `gruppe/projekt!42` ohne bekannten Host, sonst kein Aufruf.

### Güterbahnhof „↻ MRs“ (`api/gitlab` aktion `mrliste` → `mr_liste_aktion`, `mr_liste_holen`)
- `GET user`: immer, ungecacht.
- `GET merge_requests?scope=all&state=opened&reviewer_username=<ich>&per_page=50`: je nach Einstellung `mr_liste`.
- Dasselbe mit `author_username` bzw. `assignee_username`, ebenfalls je nach `mr_liste`.
- Danach für jeden MR (4 parallel) `mr_gitlab_holen`, also dieselben Aufrufe wie bei „↻ MR-Daten“.

### Güterbahnhof „↻ MR-Daten“ (aktion `mrdaten` → `mr_daten_holen` → `mr_gitlab_holen`; nur auf einer MR-Seite)
- `GET …/mr` und `GET …/mr/draft_notes`: parallel (`meta_und_entwuerfe`).
- `GET user` + `GET …/mr/notes`: nur, wenn zu gesendeten Kommentaren die Draft-Note in GitLab fehlt (`abgleich_vorbereiten`). `user` nur einmal je Host und Serverlauf (`ich()`).
- `GET …/mr/discussions`: immer.

### Rote Meldung „⇣ lokal aktualisieren“ (aktion `aktualisieren` → `aktualisieren_aktion`)
Nur sichtbar, wenn GitLab woanders steht und origin weiter ist.
- `git fetch --recurse-submodules=on-demand origin` (`branch_aktualisieren`).
- Danach dieselben Aufrufe wie bei „↻ MR-Daten“.

### „Review abschließen“ (`api/abschliessen` → `abschliessen`/`abschluss_lauf`)
Optionen: Urteil kommentieren / genehmigen / Änderungen anfordern, Häkchen „direkt veröffentlichen“.
- `GET …/mr` + `GET …/mr/draft_notes`: immer. Abbruch, wenn GitLab auf einem anderen Stand ist als die Seite.
- `GET user` + `GET …/mr/notes`: nur, wenn Draft-Notes fehlen.
- Je staged Kommentar (`schritt_ausfuehren`):
  - `DELETE …/mr/draft_notes/<id>` bei „wird gelöscht“.
  - `PUT …/mr/draft_notes/<id>` bei „geändert“.
  - `POST …/mr/draft_notes` bei neuen Kommentaren (`entwurf_anlegen`), mit drei Varianten des Inhalts: Antwort (`in_reply_to_discussion_id`), an der Zeile (`position`), allgemein. Lehnt GitLab die Zeile ab, wird es allgemein.
- `DELETE …/mr/draft_notes/<id>`: nur, wenn der Kommentar während des Sendens gelöscht wurde.
- `POST …/mr/draft_notes/bulk_publish`, danach `mr_gitlab_holen`: nur mit „direkt“, ohne Fehler und wenn es Schritte oder Entwürfe gibt.
- `POST …/mr/approve`: nur bei „genehmigen“ (`urteil_senden`).
- `POST graphql` (`mergeRequestRequestChanges`): nur bei „Änderungen anfordern“.

### GitLab-Diskussion „↩ antworten“ (`api/kommentar` aktion `antworten` → `antwort_senden`)
- `POST …/mr/discussions/<id>/notes`: nur mit „sofort senden“. Ohne das Häkchen wird die Antwort nur lokal staged.

### GitLab-Diskussion „✓ erledigt“ / „wieder öffnen“ (aktion `erledigen` / `wiedereroeffnen` → `diskussion_aufloesen`)
- `PUT …/mr/discussions/<id>?resolved=true` bzw. `?resolved=false`: nur, wenn die Diskussion in der Akte bekannt ist.

### Ohne GitLab, aber mit Zugriff auf das Remote
- **Beim Bauen einer MR-Seite** (Öffnen, `pruefen`/`zeigen`, MR-Daten): `git fetch -q origin` (`mr_lokal`), nur wenn der Quell- oder Ziel-Branch lokal fehlt. Einmal je Klon und Branch je Serverlauf.
- **Beim ersten Öffnen eines MR:** Beim Auschecken (`mr_auschecken` → `branch_auschecken`) läuft `git submodule update --init --recursive`, das holt nur, wenn Submodul-Commits fehlen.

### Kein Aufruf
Laden und Neuladen der Seite, `api/zug`, „☑ abwarten“ (abhaken), lokale Kommentar-Aktionen.

## Vorhandene Protokollierung

- `aussen_log` (`git.py`) schreibt jede Anfrage an git und GitLab mit Dauer, Ergebnis und `anlass()` in `~/.cache/merge-train/aussen-<datum>.log`, `log_tage` Tage lang (Standard 7).
- Der Anlass kommt aus `ANLASS.name`:
  - CLI: `"cli " + argv[1:3]` (`cli.py`).
  - Server: `"GET <pfad>"` / `"POST <pfad>"`, bei `aktion` `"<pfad> <aktion>"` (`mit_anlass`, `post` in `server.py`). Alles auf 32 Zeichen gekürzt.
  - Threads: Den Anlass reichen `meta_und_entwuerfe` und `mr_liste_aktion` weiter, seit Commit c19fe4f (11.11. 10:45). 26 ältere Einträge haben „-“.
- Lücken:
  - Der Anlass ist der Routenname, nicht die Stelle, an der geklickt wurde.
  - Bei `/api/abschliessen` fehlen Urteil und „direkt“.
  - Das Log ist reiner Text und lässt sich schlecht auswerten.
  - Nichts verhindert einen neuen Codepfad, der `glab()` ohne Herkunft aufruft.

## Geplante Änderung: GitLab-Aufrufe nach Herkunft prüfbar

Aufwand grob 200–300 Zeilen samt Tests.

1. **Herkunftstabelle an einer Stelle** (z. B. `gitlab.py` oder ein neues `herkunft.py`): Name → Beschreibung → erlaubte Endpoint-Muster, z. B.
   - `cli:mr-oeffnen`, `startseite:mr-oeffnen`
   - `bahnhof:mrs`, `bahnhof:mr-daten`, `meldung:lokal-aktualisieren`
   - `review:abschliessen` mit Unterart `kommentieren|genehmigen|aendern` und Zusatz `direkt`
   - `diskussion:antworten-sofort`, `diskussion:erledigen`, `diskussion:wiedereroeffnen`
   - ggf. `cli:agent-pruefen` / `cli:agent-zeigen` (siehe offene Entscheidung)

   Die Muster normalisieren Platzhalter so, wie die Analyse oben unterscheidet: `GET /x`, `GET /x?query=<wert>`, `GET /x/sub` und `GET /x/sub/<wert>` sind jeweils eigene Aufrufe.
2. **Herkunft setzen statt Routenname:** Server und CLI setzen die Herkunft aus der Tabelle. Bei `api/abschliessen` gehören Urteil und `direkt` dazu. Das JS braucht nichts Neues, wenn sich die Herkunft aus Route und `aktion` eindeutig ergibt.
3. **Ohne Herkunft kein Aufruf:** `glab()` verweigert Aufrufe ohne eingetragene Herkunft oder mit einem Endpoint, der für diese Herkunft nicht erlaubt ist (`GitLabFehler`). `aussen_log` bleibt für git, wie es ist.
4. **Log als JSONL** (`aussen-<datum>.jsonl`): Zeit, Dauer, Quelle, Herkunft, Endpoint-Muster, roher Pfad, MR, Ergebnis.
5. **`merge-train audit [--tage N]`:** Ausgabe nach Herkunft → Endpoint-Muster mit Anzahl. Zusätzlich „nie gesehen“ für Muster, die in der Tabelle stehen, aber im Log nicht vorkommen.
6. **Tests** (`tests/test_einheiten.py`, `tests/test_gitlab.py` mit `tests/fake-glab`):
   - Jede Herkunft löst nur ihre erlaubten Muster aus.
   - Ein Aufruf ohne Herkunft schlägt fehl.
   - „Seite und Zug ohne GitLab-Anfrage“ bleibt bestehen.
7. **Doku:** README „GitLab nur auf Knopfdruck“ und `docs/funktionen.md` auf die Herkunftstabelle verweisen lassen, dieses Dokument danach auf den Stand bringen oder auflösen.

### Offene Entscheidung (Nutzer)
Sollen `agent pruefen` und `agent zeigen` GitLab gar nicht mehr fragen?
- Vorschlag: Sie lesen den MR nur aus dem Cache. Der MR wird über die Branch-Zuordnung in den Akten unter `~/.local/share/merge-train/reviews/` gefunden, der GitLab-Stand kommt aus `meta`, dazu ein Hinweis auf das Alter der Daten.
- Ohne Cache: eine Meldung „erst in merge-train ‚↻ MR-Daten‘ / ‚↻ MRs‘ klicken“.
- Danach fragt nur noch der Nutzer GitLab: per Klick oder mit `merge-train <MR>` von Hand.
- Folgen: Die Skills jira-review und merge-train sowie `docs/agent-hinweise.md` beschreiben `pruefen`/`zeigen` dann als offline. Die Warnung „GitLab steht auf …“ stützt sich dann auf den zuletzt geholten Stand.

## Nebenbei erledigt / offen aus derselben Sitzung

- **Erledigt:** Bereichsvergleich in `see_also` (`"diff": "pfad:von-bis"`, `line`/`end` am Eintrag). Zeilen werden von `reviewed_commit` auf den MR-Stand umgerechnet, Änderungen im Bereich erscheinen als ⚠ bzw. „Achtung“. Commit `de44115`.
- **Erledigt:** Bei !163 / #2 hat `tasks/PROJ-32-review-markers.json` (im Klon `~/workspaces/projekt`) zwei Bereichsvergleiche: alter Handler 27–62 gegen neuen 28–62 (Prüfungen) und 66–83 gegen 124–138 (Aufbau der Antwort). Sicherung des alten Stands: `/tmp/claude-1000/-home-wsl-workspaces-merge-train/337e47f0-1904-4bdf-a023-345b67ecb612/scratchpad/PROJ-32-review-markers.vorher.json`.
- **Offen:** Der Kommentar zu #2 (schon übernommen) übertreibt mit „repeats much of the old one“. Die Prüfungen laufen gleich ab, aber anders umgesetzt (lokale Zeitzone statt UTC, Min/Max). Das tragende Argument ist „alter Endpoint ungenutzt“. Angeboten: umformulierten Entwurf daneben legen (`merge-train agent kommentar`).
- **Offen:** jira-review-Skill (`~/.claude/skills/jira-review/SKILL.md`, nicht im Repo).
  - In „Placement for ‚now unused / replaced‘“ ergänzen: Wiederholt der neue Code den alten, gehört zum alten Gegenstück ein `see_also` mit `diff` (jetzt bevorzugt als Bereichsvergleich).
  - In Schritt 4 Duplikation weiter fassen („or code that largely repeats another file“).
