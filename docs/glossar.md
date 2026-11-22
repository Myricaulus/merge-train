# merge-train · Glossar

*Angelegt am 22.11.2026. Damit alle, Mensch und KI, dieselbe Sprache sprechen.*

**Regeln**
- **Ein Wort, eine Bedeutung.** Was hier steht, meint in Doku, Code, Ausgaben von `merge-train agent` und auf der Seite
  genau das. Wer ein Wort anders braucht, nimmt ein anderes oder klärt es zuerst hier.
- **Neues Wort → zuerst hier eintragen**, mit Quelle. Noch nicht entschiedene Vorschläge tragen „Vorschlag“.
- **Nicht hier:** wo eine Funktion im Code steht und wie man sie erweitert (`docs/funktionen.md`), das Format der
  Review-JSON (`docs/agent-hinweise.md`), die Zeichnung des Güterbahnhofs im Einzelnen (`docs/gueterbahnhof.md`).
  Begriffe aus MyrSpace (Myrling, Lauf, Sichtung …) meinen dasselbe wie in `~/Projects/myrspace/GLOSSAR.md`.
- **Spalte „Seite“:** wie es auf der Seite heißt, wenn das anders ist. Code-Namen stehen in `Schreibmaschine`.
- Quellen kurz: **R** = `README.md`, **A** = `AGENTS.md`, **F** = `docs/funktionen.md`, **H** = `docs/agent-hinweise.md`,
  **G** = `docs/gueterbahnhof.md`, **S** = `skill/merge-train/SKILL.md`, **M** = `src/merge_train/myrling.py` (Vertrag
  mit nas-lauf).

---

## 1 · Grundbegriffe

| Begriff | Bedeutung | Seite | Quelle |
|---|---|---|---|
| **merge-train** | Code-Review im Browser aus dem lokalen Klon: ein Python-Skript ohne Abhängigkeiten, gebaut aus `src/`, mit kleinem Server auf `127.0.0.1:8771`. | | R |
| **Zug** | Alle Waggons aller eingeschalteten Quellen, im Kopf jeder Seite. Zeigt auf einen Blick, was ansteht. | | R, F 14 |
| **Waggon** | Ein Vergleich Quelle-Branch → Ziel in einem lokalen Klon: ein lokales Projekt, ein MR oder ein Lauf des Myrlings. Schlüssel für alles andere (Seite, Akte, Fäden). `Waggon` | | F, R |
| **Wagen** | Die Zeichnung eines Waggons im Zug: Schüttgutwagen mit Ladezettel und Füllung. `wagen_fuer`, `alle_wagen` | | G, F 14 |
| **Quelle** | Woher Waggons kommen: **lokal**, **Myrling**, **GitLab** (geplant GitHub). Einzeln an- und abschaltbar. `Quelle` | | R, F 1 |
| **Art** (eines Waggons) | Wie ein Waggon gebaut ist: Kennung, Seite, Dateiname, Akten-Ordner, Fähigkeiten. `LokalArt`, `MyrlingArt`, `MrArt` | | F 1 |
| **Fähigkeit** | Was ein Waggon kann: `review` (Kommentare nach GitLab), `fertig` (Ziel-Branch setzen), `committen` (Agent darf umsetzen statt nur antworten). `kann` | | F 2 |
| **Akte** | JSON-Datei je Waggon mit Kommentaren, Fäden, Hinweis-Status und Abhaken. Liegt im Aktenschrank. `akte.py` | | F, R „Wo liegt was“ |
| **Aktenschrank** | `~/.local/share/merge-train/`, im Repo als Symlink `aktenschrank`. | | R |
| **Einstellung** | `~/.config/merge-train/config.toml`, im Repo als Symlink `config`. | | R |
| **Nutzer** (du) | Der Mensch, der reviewt, entscheidet und freigibt. Auf der Seite „du“, Symbol `ich_symbol` (🤓). | 🤓 | A, R |
| **Agent** | Ein KI-Harness mit Namen (Claude, Copilot …), der Fragen beantwortet, Hinweise schreibt oder umsetzt. Stellt sich vor (Umgebung, `--als`, `MERGE_TRAIN_AGENT`). | 🤖 | R „Wer schreibt“ |

## 2 · Vergleich und Diff

| Begriff | Bedeutung | Seite | Quelle |
|---|---|---|---|
| **von, bis** | Lokal verglichene Branches: `bis` gegen `von`, Standard `claude` → `reviewed`. Je Projekt änderbar (`[zweige]`, Waggon-Karte). | | R, F 3 |
| **Branches `claude`, `reviewed`, `main`** | Stand des Agenten, vom Nutzer gereviewter Stand, deployter Stand. Gleicher Commit heißt nur: alles gereviewt und deployt. | | A |
| **Arbeitsstand** | `bis = "arbeitsstand"`: das Arbeitsverzeichnis samt nicht Committetem. „fertig“ gibt es dann nicht. | | R, F 3 |
| **Quell-Branch, Ziel-Branch** | Bei einem MR: der Branch des MR und der, in den er soll. Verglichen wird gegen den gemeinsamen Vorgänger. | | R |
| **Basis** | Wogegen verglichen wird: `von`, der gemeinsame Vorgänger, beim Myrling je Datei die zuletzt angesehene Fassung. | | R, M |
| **Stand** (eines Waggons) | Der Commit, der gezeigt wird (`bis`, Quell-Branch oder Stand des Laufs). | | R |
| **Ansicht** | Sicht auf denselben Vergleich: `alles`, `commit:<sha>` („nur dieser“, nur lesen), `seit:<sha>` („seit diesem“). | nur dieser, seit diesem | F 5 |
| **Kontext** | Ausgeblendete Zeilen zwischen den Hunks, nachladbar (▼ 20 / ▲ 20 / alle) und kommentierbar. | | R |
| **Popup** | Code an einem Verweis (`pfad:zeile`, Siehe-auch, Vergleich): Diff der Datei, sonst ihr Inhalt. | | R, F 7 |
| **Siehe-auch** | Verweis in einem Hinweis oder Thread auf eine weitere Stelle. Gehört nie zum GitLab-Kommentar. `see_also`, `--siehe` | Siehe auch | R, H |
| **Vergleich** (⇄) | Zwei Stellen nebeneinander, auch aus verschiedenen Ständen (`@ref`). `--vergleich A B` | ⇄ | F 7 |
| **Mitwandern** | Fäden und Hinweise folgen ihrer Zeile über neue Commits. Wurde die Zeile selbst geändert, stehen sie unter dem Dateinamen. `zeilen.py` | | R, F 6 |
| **Beobachten** | Eigene Instanz für einen Ordner, die den Arbeitsstand live zeigt und bei Änderung neu lädt. `--beobachten` | | R, F 16 |

## 3 · Gespräch mit Agenten

| Begriff | Bedeutung | Seite | Quelle |
|---|---|---|---|
| **Faden** (Thread) | Gespräch mit einem Agenten an einer Zeile, einem Bereich, einem GitLab-Kommentar oder allgemein. Gehört zum Branch, auf dem er entstand. Geht nie nach GitLab. | KI-Thread | R, F 8 |
| **Nachricht** | Ein Beitrag in einem Faden. | | R |
| **Bereich** | Faden über mehrere Zeilen (Umschalt-Klick), links lila markiert. | | R |
| **Entwurf** (eines Fadens) | Nachricht, die noch nicht an den Agenten gesendet ist. | orange ○ | R |
| **senden** | „An Agent senden“ schickt alle Entwürfe ab. ✓ gesendet, ✓✓ abgeholt. | An Agent senden | R |
| **abholen** | Der Agent liest gesendete Nachrichten mit `agent feedback` oder `agent horchen`. | ✓✓ | R |
| **horchen** (zuhören) | Eine Session wartet mit `agent horchen` auf gesendete Nachrichten. | 🎧 … hört zu | R, F 9 |
| **Zustellweg** | Wie gesendete Nachrichten zum Agenten kommen: horchen, todo-Eintrag oder eigener Befehl. `zustellweg` | | F 9 |
| **Startprompt** | Was ein gestarteter Agent als ersten Auftrag bekommt. Die letzten fünf zeigt „📨“. | 📨 | R |
| **status** | Einstieg des Agenten: Branch, Änderungen, Fäden und was jetzt zu tun ist. `merge-train status` | | S, F 8 |
| **erledigt** | Faden abgeschlossen, vom Nutzer („✓ erledigt“) oder vom Agenten (`--erledigt`). | grüner ✓ | R |
| **Kontext-Füllstand** | Wie voll das Kontextfenster der zuhörenden Session ist, aus deren Transcript. | „34 % ctx“ | R |

## 4 · GitLab-Review

| Begriff | Bedeutung | Seite | Quelle |
|---|---|---|---|
| **MR** | GitLab-Merge-Request, ein Waggon der Quelle GitLab. | | R |
| **Review-JSON** | Datei eines Review-Agenten (`tasks/<KEY>-review-markers.json`) mit Findings als Markern. | | H |
| **Marker** | Ein Eintrag der Review-JSON: Ort (needle, `line`), Text, Siehe-auch. | | H |
| **Agent-Hinweis** | Ein Marker an seiner Zeile, lila, noch nicht übernommen. = Stufe **draft**. | lila Hinweis | R, A |
| **Review-Kommentar** | Eigener oder übernommener Kommentar, der nach GitLab geht. | GitLab-Kommentar | R |
| **draft / staged / sent** | Stufen eines GitLab-Kommentars: Agent-Hinweis · übernommen, wird gesendet · in GitLab. staged entsteht nur durch den Nutzer. | siehe A | A |
| **übernehmen, verwerfen** | Agent-Hinweis wird Review-Kommentar bzw. ausgeblendet. Nur der Nutzer. | übernehmen, anpassen & übernehmen | R |
| **Draft-Note** | GitLabs Entwurf eines Kommentars im MR (stage **sent**, unveröffentlicht). Nicht dasselbe wie draft. | in GitLab (Entwurf), ➜ | A, R |
| **Review abschließen** | Gleicht die staged Kommentare mit GitLab ab, veröffentlicht auf Wunsch und setzt das Urteil. | Review abschließen → GitLab | R, F 10 |
| **Urteil** | Kommentieren, Genehmigen (Approve) oder Ändern lassen (Request changes). | ▾ am Knopf | R, F 10 |
| **Diskussion** | Veröffentlichter Kommentar samt Antworten in GitLab, auch fremde. | GitLab-Diskussion | R, F 12 |
| **abwarten** | Ball in einer Diskussion ohne Antwort abgeben, nur in merge-train. | ☑ abwarten | R |
| **GitLab-Stand** | Commit, auf dem GitLab den MR zuletzt hatte, verglichen mit dem Klon. | rote Meldung | R, F 13 |
| **Klon** | Lokales Repo eines GitLab-Projekts, aus dem Diff und Dateien kommen (`[repos]`, `klon_ordner`). | | R |
| **MR-Daten** | Titel, Beschreibung, Branches, Diskussionen, GitLab-Stand eines MR. Nur auf Knopfdruck geholt. | ↻ MR-Daten | R, F 13 |

## 5 · Wer ist dran (Stände der Listen)

| Begriff | Bedeutung | Seite | Quelle |
|---|---|---|---|
| **Liste** | „GitLab-Kommentare“, „GitLab-Diskussionen“, „KI-Threads“, links über den Dateien. | | R, F |
| **`stand`** | Wer bei einem Eintrag jetzt dran ist: `entwurf`, `dran`, `gitlab_entwurf`, `wartet`, `erledigt`. | ○ ● ➜ ○ ✓ | F „Stände“ |
| **`wer`** | Wer zuletzt gehandelt hat: `du`, `agent`, `extern`. | 🤓 🤖 Logo | F „Stände“ |
| **extern** | Von außen aus der Quelle. Ob ein Mensch schrieb, weiß man nicht sicher. | Logo der Quelle | F „Stände“ |
| **Marke** | Zeichen am Wagen: „💬 n neu“, „● n dran“, „✓ erledigt“ … | | R, F 14 |

## 6 · Abhaken und fertig (lokal)

| Begriff | Bedeutung | Seite | Quelle |
|---|---|---|---|
| **abhaken** | Eine Datei als gesehen markieren (☐ im Dateikopf), je Stand der Datei. Füllt den Wagen. `abhaken.py` | ☐ | F 4, G |
| **Füllung** (Füllgrad) | Zeilen der abgehakten Dateien / Zeilen aller Dateien, jede mit Mindestportion. | Schüttgut | G |
| **fertig** | Setzt `von` auf den gesehenen Stand (`git push .`, nur Fast-Forward) und räumt erledigte Fäden weg. | fertig ✓ | R, F 15 |
| **abgeben** | Nur die abgehakten Dateien als Commit auf den **Teilstand** `<von>-wip`. | abgeben | F 15 |
| **Runde** | Was heute fertig oder abgegeben ist, zählt für die **Abfahrt** des Zugs. `runde_eintragen` | | F 15 |

## 7 · Quelle Myrling

| Begriff | Bedeutung | Seite | Quelle |
|---|---|---|---|
| **Myrling** (Quelle) | Skripte, die der Myrling ausführen soll und die noch angesehen werden müssen. Heute liefert sie `nas-lauf` (`myrling_befehl`). | | R, M |
| **Lauf** | Ein Skript mit Begleitdateien, ein Waggon je Lauf. | ⛭ skript | M, F 1 |
| **Begleitdateien** | Dateien, die ein Skript mitbringt, jede gegen ihre eigene Basis. | | M |
| **`fp`** | Hash über Skript und Begleitdateien, vom Befehl geliefert. | | M |
| **Lauf-Stand** | Was der Befehl über einen Lauf sagt: `neu`, `geaendert`, `abgelehnt`, `gesehen`. | | M |

## 8 · Seite und Betrieb

| Begriff | Bedeutung | Seite | Quelle |
|---|---|---|---|
| **Güterbahnhof** | Kopf der Seite: Kulisse, Verladegebäude, Förderband, Gleis, Zug. | | G |
| **Leitstand** | Knöpfe aller Quellen im Verladegebäude („↻ MRs“, „↻ MR-Daten“, „↻ Änderungen“). | | R, G |
| **Stellwerk** (HUD) | Anzeige rechts: LED des Servers, Stand von merge-train, Zuhörer, Zähler, Kontext-Füllstand. | | R, F 17 |
| **Toast, Glocke** | Meldung des Servers (10 s), die letzten 50 unter 🔔. | 🔔 | R |
| **Leerlauf** | Sekunden ohne Anfrage, nach denen sich der Server beendet. | | R |
| **Vorfall** | Bericht eines Agenten, wo merge-train in die Irre führte (`--art bug\|wunsch`). | | A, R |
| **bauen** | `./bauen`: `src/` → `merge-train`. | | A |
| **Teil** (eines Testlaufs) | Was `./testen` einzeln auswählt: `./pruefen`, Smoke, Klassen der Einheitentests, Teile von `test_gitlab.py`, UI-Teile. | | A, F 21 |
| **voll** | Testlauf mit allen Teilen samt UI-Tests (`--voll`, Takt im pre-commit, pre-push). | | A |
| **pruefen** | `./pruefen`: JS und CSS lintet Biome, Zusammenhang über `App`. | | R |

---

## 9 · Noch mehrdeutig

Wörter, die in merge-train heute zwei oder mehr Bedeutungen haben. Bis entschieden ist, gilt die Unterscheidung rechts.

| Wort | Bedeutungen | Vorschlag |
|---|---|---|
| **Stand** | Commit eines Waggons · `stand` (wer ist dran) · GitLab-Stand · Lauf-Stand · Stand von merge-train im HUD | nie allein: **Waggon-Stand**, **Listen-Stand** (`stand`), **GitLab-Stand**, **Lauf-Stand**; „wer ist dran“ beim Reden |
| **Entwurf** | Faden-Nachricht, nicht gesendet · staged Kommentar („Entwurf (lokal)“) · Draft-Note in GitLab | in Doku: **ungesendet** (Faden), **staged**, **Draft-Note**; Seiten-Labels bleiben |
| **Quelle** | Quelle von Waggons (lokal, Myrling, GitLab) · Quell-Branch („Quelle → Ziel“) | „Quelle“ nur für die Waggon-Quelle, sonst immer **Quell-Branch** |
| **Faden / Thread** | dasselbe, Seite sagt „KI-Thread“, Doku „Faden“, CLI `thread` | Vorschlag: **Faden** in Doku, „Thread“ nur in Seite und CLI |
| **Hinweis** | Agent-Hinweis (draft) · Meldung oben („sagt das ein Hinweis oben“) | „Hinweis“ nur für Agent-Hinweise, sonst **Meldung** |
| **prüfen** | `agent pruefen` (Review-JSON anmelden) · `./pruefen` (Lint) · Lauf, der „auf eine Prüfung wartet“ | Myrling: **Sichtung** (wie MyrSpace); die beiden Befehle behalten ihren Namen |
| **Waggon / Wagen** | Vergleich (Daten) · seine Zeichnung im Zug | so lassen, aber streng trennen |
