# merge-train

> **TL;DR:** Müde vom Reviewen riesiger KI-MRs, aber du willst kein Meat Proxy sein, der nur noch Kommentare zwischen
> Agent und GitLab hin- und herkopiert? Dann steig in den merge-train: Du fragst direkt an der Zeile, dein Agent
> antwortet genau dort, und du entscheidest, was rausgeht.

merge-train ist dein Code-Review im Browser, so schnell wie lokales Git, weil es auch genau das ist: Der Diff kommt aus
deinem Klon, nicht aus einer trägen API, und selbst riesige Änderungen öffnen sich sofort. Woher die Reviews kommen, ist
egal: Eigene Branches, GitLab-Merge-Requests und bald GitHub-Pull-Requests stehen als **Quellen** gemeinsam in einem Zug,
und alles, was ansteht, siehst du auf einen Blick. Durch den Code bewegst du dich wie in einer IDE: Jede Datei- oder
Zeilenangabe in Kommentaren, Agent-Findings und Antworten ist ein Link, und Siehe-auch-Verweise und Dateivergleiche
öffnen die Stelle im Popup, samt Diff und aufklappbarem Kontext. Der eigentliche Clou ist die Arbeit mit KI-Agenten: Du
schreibst Fragen oder Änderungswünsche direkt an die Codezeile, dein Lieblings-Harness hört mit, antwortet genau dort
oder setzt es auf seinem Branch um. Findings eines Review-Agenten erscheinen als Vorschläge an der richtigen Zeile, die
du übernimmst, anpasst oder verwirfst. Nach außen geht nur, was du selbst freigibst. Du behältst also die Kontrolle, und
die KI erledigt die Fleißarbeit. Und weil merge-train ein einziges Skript ohne Abhängigkeiten ist, passt du es leicht
an: Jede Änderung an Server oder Seite ist nach `./bauen` sofort im Browser zu sehen, ohne Neustart von Hand.
Obendrauf gibt es einen Güterbahnhof im Seitenkopf, bei dem man jedem fertigen Review buchstäblich beim Beladen zusieht.

## Überblick

Merge-Requests im Browser ansehen, so wie der „Changes“-Reiter in GitLab, nur schneller. Jeder Waggon im Zug ist ein
Vergleich Quelle → Ziel in einem lokalen Klon. Die Waggons kommen aus drei **Quellen** (einzeln an- und abschaltbar,
alle eingeschalteten fahren im selben Zug):

- **lokal** (`lokal = true`): Für alle Repos unter `~/Projects` wird `claude` gegen `reviewed` verglichen.
  „fertig ✓“ setzt `reviewed` auf den gesehenen Stand. Fragen und Wünsche zum Code gehen per Klick auf die Zeilennummer
  an Claude, der sie auf `claude` umsetzen darf (siehe [Gespräch mit Claude](#gespräch-mit-claude-lokaler-modus)).
  von/bis gibt es auch je Projekt: `[zweige.<projekt>]` in der Einstellung, oder im Zug den Waggon mit „▾“ aufklappen
  (Projektinfos, Branches zur Auswahl, „↺ Standard“). Repos, denen ein Branch fehlt, fahren als gestrichelter
  Waggon „⚠ fehlt“ mit, wenn sie ausdrücklich unter `projekte` stehen.
- **Myrling** (`myrling = true`, Befehl `myrling_befehl`): Skripte, die der Myrling ausführen soll und die auf eine
  Prüfung warten. Ein Waggon „⛭ skript“ je Skript. Der Diff zeigt das Skript und
  seine Begleitdateien, jede gegen die Fassung, die du zuletzt angesehen hast. Fragen an der Zeile gehen an den Agenten
  im Repo der Skripte, der sie ändern und committen darf. Fehlt der Befehl, ist die Quelle aus.
- **GitLab** (`gitlab = true`): ein MR mit eigenen Review-Kommentaren und Agent-Hinweisen. „Review abschließen“ legt
  die Kommentare als **Entwürfe** im MR an, veröffentlicht wird danach in GitLab. Dazu private Fragen an Agenten
  (siehe [Fragen an einen Agenten](#fragen-an-einen-agenten-gitlab-modus)), die nur antworten, nichts ändern.

Es gibt nur eine Seite: Kopf mit Güterbahnhof (Leitstand-Knöpfe aller eingeschalteten Quellen) und Zug, Diff aus dem
lokalen Git (Kontext nachladen, große Dateien auf Klick, Commit-Ansichten), Gespräch an den Zeilen. Was ein Waggon
zusätzlich kann (Review, „fertig“), bestimmt seine Quelle. GitLab wird nur auf Anforderung gefragt
(siehe [GitLab nur auf Knopfdruck](#gitlab-nur-auf-knopfdruck)). Eine weitere Quelle (z. B. GitHub-PRs) wäre eine
weitere Klasse in `src/merge_train/quellen.py`.

Ein einzelnes Python-Skript, ohne Abhängigkeiten außer `git` (Syntaxfarben mit `pygments`, GitLab mit `glab`).
Gebaut wird es aus `src/` (siehe [Entwicklung](#entwicklung)).
Ein kleiner Server auf `127.0.0.1:8771` liefert die Seiten aus und beendet sich nach einer Stunde ohne Anfrage
(`leerlauf`; offene Seiten fragen alle 4 s nach und halten ihn wach) oder mit `merge-train --stopp`.
`merge-train agent thread`, `feedback` und `horchen` starten ihn wieder, damit die Seite gleich erreichbar ist.

## Aufruf

```sh
merge-train                     # lokaler Zug (bei lokal = false: Liste der MRs zum Review)
merge-train myproj              # nur dieses Projekt
merge-train https://gitlab.example.com/gruppe/projekt/-/merge_requests/42
merge-train '!42'               # MR 42 des Projekts im aktuellen Ordner (git remote origin)
merge-train gruppe/projekt!42
merge-train --mrs               # MRs, bei denen ich Reviewer bin
merge-train --stopp             # Server beenden (laufende Aktionen werden noch fertig)
merge-train --beobachten [ordner] [--von REF]   # Arbeitsstand live, siehe „Beobachten“
merge-train agent pruefen tasks/PROJ-824-review-markers.json   # siehe docs/agent-hinweise.md
merge-train agent pruefen tasks/PROJ-824-review-markers.json --seit   # Review-Update seit reviewed_commit
merge-train agent zeigen  tasks/PROJ-824-review-markers.json
merge-train status [projekt|MR]            # Agent, zuerst: Branch, Änderungen, Fäden des Branches, was zu tun ist
merge-train agent feedback [projekt|MR]     # Agent: Fragen/Feedback abholen (lokal oder zu einem MR)
merge-train agent antworten <id> "…" [--erledigt]
merge-train agent horchen [projekt|MR] [--als Name]   # Agent: warten, bis „An Agent senden“ gedrückt wird
merge-train agent feedback --horchen [projekt|MR]      # Agent: was wartet, sofort – sonst wie horchen
merge-train agent thread [--ort pfad:zeile[-bis]] [--siehe …] [--vergleich A B] "…"   # Agent: eigenen Thread anlegen
```

In bash `'!42'` in Anführungszeichen setzen, sonst greift die History-Expansion.

## Die Diff-Seite (alle Quellen)

- **Quelle des Diffs**: Diff, Dateien und Commits kommen immer aus dem lokalen Klon, nie aus GitLab. Lokal ist der Stand
  der Branch `claude`, die Basis `reviewed` (`bis`/`von` in der Einstellung). Bei einem MR ist der Stand der Quell-Branch (lokal, sonst `origin/…`), die Basis
  der gemeinsame Vorgänger mit dem Ziel-Branch. Welcher Branch ausgecheckt ist und lokale Änderungen spielen keine Rolle
  (außer beim [Beobachten](#beobachten-arbeitsstand-live-z-b-was-ein-agent-in-einem-worktree-baut)).
  Diffs nicht über die GitLab-API, weil sie bei großen Änderungen oft keinen Diff liefert und langsam ist.
- **Kontext**: Ausgeblendete Zeilen zwischen den Hunks lassen sich nachladen (▼ 20 / ▲ 20 / alle). Auch dort kann man kommentieren.
  Generierte Dateien (`*.Designer.cs`, `*ModelSnapshot.cs`, Lockfiles …) und sehr große Diffs werden erst auf Klick geladen,
  automatisch, sobald ein Kommentar oder Hinweis darin liegt.
- **Commit-Ansichten**: Unter „Beschreibung & Commits“ hat jeder Commit zwei Knöpfe.
  - *nur dieser*: Diff dieses einen Commits, **nur lesen**. Kommentare und Hinweise werden auf den Stand nach dem
    Commit zurückgerechnet und stehen an ihrer Zeile. Geht das nicht (Zeile später geändert, alte Seite des Diffs, außerhalb
    der Änderungen), stehen sie unter dem Dateinamen mit dem Grund.
  - *seit diesem*: alles nach dem Commit bis zum Stand. Rechts steht der Stand, dort wird normal kommentiert und
    übernommen. Links (Stand des Commits) lässt sich nicht kommentieren.
  - Einträge in Dateien, die die Ansicht nicht ändert, werden nur gezählt. Kommentare und Fäden gehören immer zum ganzen Vergleich.
- **Siehe-auch-Links und `pfad:zeile`** (in Agent-Hinweisen und Nachrichten) öffnen den Code im Popup, die Zeile bzw.
  der Bereich (`pfad:10-20`) ist hervorgehoben. Liegt die Datei im Diff, zeigt das Popup deren Diff (Lücken aufklappbar,
  „alles aufklappen“), sonst den Dateiinhalt (mehr laden / ganze Datei).
- **Kommentarlisten** links über den Dateien, in Datei-Reihenfolge: „KI-Threads“ (Gespräche mit Agenten) und bei einem MR
  „GitLab-Kommentare“ und „GitLab-Diskussionen“ (siehe unten). Leere Listen sind ausgeblendet. Ein Klick springt zum
  Eintrag und klappt dafür bei Bedarf Kontext oder Datei auf. Alle drei sind gleich gebaut, jeder Eintrag zeigt zwei
  Dinge: **wer zuletzt gehandelt hat** (🤓 du, Symbol einstellbar mit `ich_symbol`; 🤖 ein Agent; das GitLab-Logo: von
  außen) und **wer jetzt dran ist**:
  orange ○ Entwurf, noch nicht gesendet · lila ● du bist dran · orange ➜ Entwurf in GitLab, dort abschicken ·
  blauer ○ die anderen sind dran · grüner ✓ erledigt.
  Ein Klick auf das Zeichen erledigt einen KI-Thread bzw. wartet bei einer Diskussion ab („☑ abwarten“). Neben dem
  Titel steht für jeden Stand, der in der Liste vorkommen kann, ein kleiner Filterknopf mit Anzahl, auch bei 0. Grüner
  Rahmen = angezeigt, Klick blendet den Stand aus (grau). Das merkt sich der Browser je Waggon und Liste. Die Regeln
  dahinter: [Stände der Listen](docs/funktionen.md#stände-der-listen-wer-ist-dran).
- **Stellwerk** (HUD) rechts im Güterbahnhof, auf Stelzen über dem Gleis: LED (grün: Server läuft, rot: nicht erreichbar,
  gelb: neuer Server, die Seite lädt gleich neu), Stand von merge-train (letzter Commit mit Zeit, `*` = Änderungen in
  `src/` noch nicht committet), wer zuhört, Zahl der Kommentare, Hinweise und KI-Threads (offen = nicht erledigt; in der
  Liste „KI-Threads“ schließt ein Klick auf ○ einen Thread) und der Kontext-Füllstand der Claude-Session, die zuletzt
  mit `agent horchen` zugehört hat („34 % ctx“ als Balken: bis 15 % grün, bis 20 % nach orange, bis 25 % nach rot, ab 35 % giftlila mit
  schillerndem Rahmen; Schwellen in `kontext_schwellen`), solange die Session läuft, also auch
  während sie arbeitet. Der Füllstand stammt aus deren Transcript (`~/.claude/projects/*/<session>.jsonl`), der Agent
  muss nichts tun. Fenster 200k, mit `[1m]` im Modell 1M, sonst `kontext_fenster` in der Einstellung. Meldungen des Servers erscheinen als Toasts (10 s, wegklickbar), die letzten 50 unter 🔔 unten rechts.

## Gespräch mit Claude (lokaler Modus)

Fragen zum Code oder Änderungswünsche schreibt man direkt an die Zeile, wie ein Review-Kommentar:

1. **Klick auf eine Zeilennummer** (oder „＋ allgemeine Frage“): Die Nachricht ist zunächst ein **Entwurf**.
   Man kann mehrere sammeln, bearbeiten oder löschen.
   Umschalt-Klick auf eine zweite Zeile derselben Datei macht daraus einen Bereich: Der Faden steht unter der letzten
   Zeile, die Zeilen sind links lila markiert und wandern nach neuen Commits mit. Bei Review-Kommentaren (GitLab) geht das nicht.
2. **„An Agent senden“** schickt alle Entwürfe ab. ✓ heißt gesendet, ✓✓ heißt von Claude abgeholt.
   **„📨“** daneben zeigt, was zuletzt genau beim Agenten ankam: die Ausgabe von `horchen`/`feedback` bzw. den
   Startprompt, die letzten 5 und nur in einer Nebendatei der Akte (`<akte>.prompt`). Mit „vor dem Senden zeigen“
   zeigt „An Agent senden“ das erst als Vorschau und sendet auf „senden“.
3. Claude holt sie mit `merge-train agent feedback` ab (Ort im aktuellen Stand, Code drumherum, Verlauf), beantwortet
   Fragen bzw. setzt Wünsche auf `claude` um und antwortet je Faden mit `merge-train agent antworten <id> "…"`
   (`--erledigt`, wenn umgesetzt). Die Antwort erscheint sofort an der Zeile (die Seite fragt alle 4 s nach),
   dazu eine Desktop-Meldung. Im Zug zeigt der Waggon „💬 n neu“, der Tab-Titel „(n)“.
4. Mit **„↩ antworten“** geht das Gespräch weiter, „✓ erledigt“ schließt einen Faden.

Der Agent kann auch selbst Threads anlegen (`merge-train agent thread`), etwa nach einer Umsetzung: je offenem Punkt
einer an der Zeile („neu von Claude“), mit Siehe-auch-Links und Dateivergleich (`--siehe`, `--vergleich A B`), und
die Zusammenfassung als allgemeiner Thread oben. Dateinamen und `pfad:zeile` in Nachrichten sind Links ins Popup.

Nach neuen Commits wandern die Fäden mit ihrer Zeile mit. Wurde die Zeile selbst geändert, steht der Faden unter dem
Dateinamen, mit dem damaligen Zeilentext. „fertig“ warnt bei offenen Fäden oder ungesendeten Entwürfen und räumt
erledigte Fäden weg. Offene bleiben für den nächsten Stand.

**Fäden gehören zum Branch**, auf dem sie entstanden sind: zu `bis`, bei `bis = "arbeitsstand"` zum ausgecheckten
Branch (bei einem MR zu dessen Quell-Branch). Seite, Zähler im Zug, „An Agent senden“, `agent feedback`/`horchen` und
„fertig“ sehen nur die Fäden des aktuellen Branches. Nach einem Wechsel zurück sind die alten wieder da. Oben im
Gespräch blendet „N Fäden aus anderen Branches zeigen“ die übrigen ein, nur zum Lesen und ohne Ort im Diff.
Der Knopf merkt sich die Wahl.

**Wer bekommt das Feedback?**

- **Eine Claude-Session hört zu**: Läuft in einer Session `merge-train agent horchen` (im Hintergrund), geht das
  Feedback direkt dorthin. Oben steht dann „🎧 Claude hört zu“. Dazu genügt es, der Session zu sagen: „hör auf merge-train“.
  Eine Session hört nur auf die Waggons ihres eigenen Projekts; jedes Projekt kann also seine eigene Session haben.
  Deshalb sitzt der Kopfhörer auch auf dem Dach des Waggons: 🎧, wenn sie zuhört (ab und zu langweilt sie sich
  sichtbar), wackelndes Werkzeug, wenn sie gerade arbeitet.
  **„🎧 ✕“** neben „An Agent senden“ beendet das Zuhören, ebenso das Schließen der Seite. Die Session merkt davon
  nichts: `horchen` endet nicht, sondern wartet stumm bis zum Ende der Session. Sein Ende würde den Agenten wecken
  und einen Request mit dem ganzen Kontext kosten. Wieder zuhören: der Session „hör zu“ sagen.
  In anderen Repos (z. B. dem Klon eines MR) kennt die Session das über den Claude-Skill `merge-train`
  (`skill/merge-train/SKILL.md`, bei der [Installation](#installation) verlinkt).
- **Keine hört zu**: Ist das Werkzeug `todo` installiert (eigenes Werkzeug des Autors, nicht Teil von merge-train und
  nicht veröffentlicht), legt „An Agent senden“ dort einen Eintrag im Projekt an (mit Startprompt), und dessen Panel pulsiert.
  „▶ Session starten“ auf der Seite öffnet ihn mit `todo los` (Konsole im Projekt, Enter startet Claude).
  Weitere Nachrichten hängen sich als Notiz an denselben Eintrag. Sind alle Fäden beantwortet, hakt merge-train ihn ab.
  Ohne `todo` und ohne `feedback_befehl` sagt die Seite nur, dass keine Session zuhört.
- **Eigener Befehl**: `feedback_befehl` in der Einstellung startet stattdessen etwas Eigenes, z. B.
  `feedback_befehl = "konsole --workdir {ordner} -e claude {prompt}"` (Platzhalter `{ordner}`, `{projekt}`, `{prompt}`).

Die Akte des Projekts (Fäden, Nachrichten) liegt in `~/.local/share/merge-train/lokal/<projekt>.json`.

## GitLab-Review

- **Stand**: Lag GitLab beim letzten Holen auf einem anderen Stand als der Klon (`[repos]`, `klon_ordner` oder Repo der Hinweis-Datei),
  sagt das ein Hinweis oben.
- **GitLab-Kommentare** (Liste links): offene Agent-Hinweise (🤖 ●: du bist dran, übernehmen oder verwerfen) und
  eigene bzw. übernommene Kommentare (🤓 ○ Entwurf, ➜ Entwurf in GitLab). Die Reihenfolge
  ist die Sende-Reihenfolge bei „Review abschließen“: nach Datei und Zeile, mit „⇅“ (vor den Filterknöpfen) per Drag & Drop oder ⤒/⤓
  (ganz nach oben/unten) änderbar. Sie wird beim MR gespeichert, Neues landet an seiner Stelle nach Datei und Zeile,
  ein übernommener Hinweis behält seinen Platz.
- **Kommentar schreiben**: Auf eine Zeilennummer klicken (links = alte Zeile, rechts = neue). Speichern mit Strg+Enter, abbrechen mit Esc.
  Allgemeine Kommentare über „＋ allgemeiner Kommentar“.
- **Agent-Hinweise** (lila) stehen an ihrer Zeile. Liegt die Zeile außerhalb des Diffs, stehen sie oben unter „Review“.
  Ein Klick auf den Ort klappt den Kontext dorthin auf (oder öffnet ein Popup, wenn die Datei nicht im MR ist).
  „Siehe auch“-Verweise (Popup wie oben) gehören nicht zum GitLab-Kommentar.
  Mit „übernehmen“ oder „anpassen & übernehmen“ werden Hinweise zu einem eigenen Kommentar, „verwerfen“ blendet sie aus.
- **Kommentare** lassen sich bearbeiten und löschen. Das Etikett zeigt den Stand: *Entwurf (lokal)*, *in GitLab (Entwurf)*,
  *geändert* oder *wird in GitLab gelöscht*.
- **Review abschließen → GitLab** legt neue Kommentare als Draft-Notes an, aktualisiert geänderte und löscht entfernte.
  Mit **„☑ direkt veröffentlichen“** (Standard, daneben, im Browser gemerkt) werden danach alle deine Entwürfe im MR
  veröffentlicht, wie „Submit review“ in GitLab (eine Benachrichtigung), und die Diskussionen gleich geholt. Ohne
  Haken bleiben sie „Pending comments“ in GitLab (➜), dort prüfen und das Review abschicken.
  Mehrfaches Abschließen erzeugt keine Duplikate. Einen in GitLab veröffentlichten Kommentar fasst das Tool nicht an.
  Das **„▾“ rechts am Knopf** wählt das Urteil: *Kommentieren* (Standard), *Genehmigen* (Approve) oder *Ändern lassen*
  (Request changes). Genehmigen und Ändern lassen gehen auch ohne Kommentar und gelten nur für dieses eine Abschließen.
- **GitLab-Diskussionen als Threads**: „↻ MR-Daten“ holt alle Diskussionen des MR (ohne Systemnotizen wie „changed this
  line“). Veröffentlichte eigene Kommentare und die anderer (andere Reviewer, im eigenen MR die Reviewer, direkt in GitLab
  Geschriebenes) stehen als Threads an ihrer Zeile, genau wie die KI-Threads: Verlauf mit deinen Beiträgen rechts, Stand
  (z. B. „neue Nachricht – du bist dran“, „wartet auf die anderen“, „in GitLab erledigt“), „↩ antworten“ und „wieder
  öffnen“. Links stehen sie in der Liste „GitLab-Diskussionen“. Der einzige Unterschied ist das Ziel: Erledigen und
  wieder öffnen gehen sofort an GitLab. Die Liste „GitLab-Kommentare“ enthält nur noch, was „Review abschließen“ sendet.
  Bist du dran, aber es gibt nichts zu sagen: **„☑ abwarten“** gibt den Ball ohne Antwort ab (nur in merge-train, in
  GitLab bleibt die Diskussion offen; „↺ doch dran“ nimmt es zurück). Schreibt danach jemand, bist du wieder dran.
  **„✓ in GitLab erledigt“** löst sie in GitLab auf; nur dann wird die Box grau.
- **Antworten auf GitLab-Diskussionen**: Mit „sofort senden“
  geht die Antwort gleich als veröffentlichter Kommentar in die Diskussion, ohne lokalen und GitLab-Entwurf. Ohne wird sie
  ein lokaler Entwurf in der Diskussion, und „Review abschließen“ legt sie als Draft-Antwort an. „sofort senden“ ist eine
  Einstellung des Browsers und gilt auch für Fragen an Agenten. Sie steht neben „Review abschließen“ und in jedem
  Eingabefeld. „Review abschließen“ ist ausgegraut, solange es nichts zu senden gibt.
- **Der MR-Waggon im Zug** zeigt, was am meisten zählt: „💬 N neu“ (Agent-Antworten in Fäden), „● N dran“ (Diskussionen, in denen du dran bist), sonst
  „✓ in GitLab“ (abgeschlossen) bzw. „✓ erledigt“ oder „● N Komm.“. Fertig (grüner Rahmen) ist der Waggon, sobald
  nichts mehr bei dir liegt: keine Diskussion, in der du dran bist, keine Entwürfe (lokal oder in GitLab). Wartet eine
  Diskussion auf die anderen, hält das nicht auf. Der Tooltip nennt Rolle (Reviewer/Autor), Diskussionen je Stand,
  Entwürfe in GitLab, neue Antworten, eigene Kommentare und Fäden.
- Kommentare zu Zeilen außerhalb des Diffs versucht das Tool zuerst als Zeilen-Kommentar. Lehnt GitLab das ab, wird daraus
  ein allgemeiner Kommentar mit Link auf `datei:zeile`.

Der Review-Stand liegt in `~/.local/share/merge-train/reviews/`, der Seiten-Cache in `~/.cache/merge-train/`.

## Fragen an einen Agenten (GitLab-Modus)

Auch zu einem MR kann man einen Agenten fragen (Claude, Copilot …), wie im lokalen Modus, nur privat:
Im Kommentar-Editor gibt es neben „als Review-Kommentar“ je Agent einen Knopf **„an <Name>“**. Solche Fragen liegen
als eigene Fäden in der Review-Datei des MR und gehen **nie** nach GitLab („Review abschließen“ überspringt sie).
„An Agent senden“ schickt die Entwürfe ab, die Antworten erscheinen als Gespräch an der Zeile.

„an Claude“ gibt es immer, wie im lokalen Modus: Hört niemand zu und ist nichts eingerichtet, bleiben die Fragen
gesendet liegen, bis eine Session sie mit `merge-train agent feedback <MR>` abholt („📨“ zeigt, was sie dann bekommt).
Weitere Agenten kommen aus `[agenten]` in der Einstellung oder dazu, wenn gerade einer zuhört:

```toml
[agenten]
Copilot = "wt.exe -w 0 nt --title Copilot wsl.exe -e bash -lc 'cd {ordner} && copilot -i \"$0\"' {prompt}"   # Beispiel, anpassen
```

„An Agent senden“ startet den Befehl (Platzhalter `{ordner}` = Klon, `{projekt}`, `{prompt}`), sofern nicht schon jemand
zuhört. Der Agent braucht nur die Shell, Befehle wie im lokalen Modus, mit der MR-Kennung aus dem Prompt (im Klon geht
es auch ohne):

```sh
merge-train agent feedback gitlab.example.com/gruppe/projekt/42   # oder im Klon: merge-train agent feedback
merge-train agent antworten <id> "…"
merge-train agent kommentar <h:key | Kommentar-id | Faden-id> "…"   # GitLab-Kommentar umformulieren (siehe unten)
merge-train agent kommentare [MR]                                  # lesen: was am MR schon kommentiert ist
merge-train agent vorfall "<Titel>" --art bug|wunsch -              # Bericht, wo merge-train in die Irre führte: todo, sonst vorfaelle/ (Issue nur mit vorfall_github) (docs/vorfaelle/README.md)
merge-train agent horchen gitlab.example.com/gruppe/projekt/42 --als Copilot   # Seite zeigt „🎧 Copilot hört zu“
```

Bittet man im Faden, einen GitLab-Kommentar umzuformulieren, landet die Änderung im Kommentar selbst: `feedback` zeigt
unter jedem Faden die Kommentare und Agent-Hinweise an dessen Zeile. `agent kommentar h:<key>` ändert einen noch nicht
übernommenen Agent-Hinweis (dessen `text` in der Review-JSON). Bei einem bestehenden Kommentar oder einer Faden-id legt
es einen neuen Agent-Hinweis an derselben Stelle an. Review-Kommentare entstehen nur durch „übernehmen“: Der Agent
legt nie selbst welche an, und der alte Kommentar bleibt, bis man ihn selbst löscht.

Direkter geht es mit **„💬 an Agent“** an einem Kommentar oder Agent-Hinweis: Die Nachricht wird ein Faden, der an
genau diesem Kommentar hängt und darunter steht. Wie jeder Faden geht er nie nach GitLab, wird mit „An Agent senden“
abgeschickt (oder gesammelt und später per `agent feedback` abgeholt). `feedback` zeigt den Kommentar als Ziel
(„HÄNGT AN …“), und `agent kommentar <Faden-id> "…"` ändert genau ihn: einen draft direkt, sonst als neuen draft
daneben. Danach hängt der Faden am draft und ist erledigt, ohne Antwort. Antworten schreibt der Agent nur, wenn man um
eine Erklärung bittet („erklär mir …“).

**Wer schreibt:** Auf der Seite steht der Name des Agenten (Antworten, Threads, Hinweise). merge-train erkennt ihn aus
der Umgebung (Claude Code, Cursor, Gemini CLI, Codex, `AI_AGENT`). Andere stellen sich mit `--als "Copilot (Claude Sonnet 4.5)"`
vor oder setzen `MERGE_TRAIN_AGENT`. Ohne Namen lehnen `thread`, `horchen` und `kommentar` ab, `antworten` nimmt den
gefragten Agenten. Für Hinweise nennt die Review-JSON den Namen im Feld `agent`. Sonst gilt der Agent, der sie mit
`agent pruefen|zeigen` angemeldet hat.

## GitLab nur auf Knopfdruck

Beim Öffnen oder Neuladen einer Seite fragt merge-train GitLab nicht. MR-Daten (Titel, Beschreibung, Branches,
GitLab-Stand) und die MR-Liste für den Zug liegen im Cache. Geholt wird nur:

- von `merge-train agent pruefen|zeigen` (macht der mr-review-Skill, wenn er den Branch aktualisiert hat) und `merge-train <MR>`,
- im **Güterbahnhof** links vom Zug: „↻ MRs“ (offene MRs, bei denen ich Reviewer oder Autor bin, dazu je MR MR-Daten,
  Entwürfe und Diskussionen, parallel, ohne die Seiten zu bauen) und „↻ MR-Daten“ (dieser MR,
  mit Antworten und Erledigt-Status der veröffentlichten Kommentare),
- beim **Review abschließen**: aktueller GitLab-Stand (steht GitLab woanders als die Seite, wird nichts übertragen),
  dann die Draft-Notes.

Steht GitLab woanders als der lokale Klon, sagt das eine rote Meldung über dem Diff. Ist origin weiter (neue Commits
im MR), holt **„⇣ lokal aktualisieren“** origin und zieht den Quell-Branch nach: vorspulen oder, nach einem Force-Push,
neu setzen, ausgecheckt samt Arbeitsverzeichnis und Submodulen. Lokale Commits oder nicht committete Änderungen
bleiben unangetastet, dann bricht es mit Meldung ab. Danach holt der Knopf gleich die MR-Daten, damit die Meldung
auch verschwindet, wenn inzwischen weiter gepusht wurde. Holt der Zug neue MR-Daten im Hintergrund und ändert sich
dadurch die Seite, lädt ein offener Tab von selbst neu (nicht, solange ein Eingabefeld offen ist).

Beim ersten Öffnen eines MR checkt merge-train dessen Quell-Branch im lokalen Klon aus (fehlt er, mit Tracking aus
origin; noch nicht geholt, holt merge-train origin einmal selbst), damit IDE und Agent gleich auf dem richtigen Stand sind – nur wenn dort nichts Uncommittetes liegt und HEAD
auf einem Branch steht (kein Rebase), samt Submodulen. Die Seite lädt dafür nicht neu, die Glocke meldet den Wechsel.
Einmal je MR: wechselst du danach selbst zurück, bleibt es so. Abschalten mit `mr_auschecken = false`.

## Wo liegt was

merge-train hält sich an die Linux-Ordner (XDG): Einstellung, Daten und Cache liegen getrennt. Zum Hineinschauen
liegen im Repo zwei Symlinks aus der [Installation](#installation) (in `.gitignore`): `config` und `aktenschrank`.

| Was | Ort | im Repo |
|---|---|---|
| Einstellung | `~/.config/merge-train/config.toml` (`$XDG_CONFIG_HOME`, `$MERGE_TRAIN_CONFIG`) | `config/` |
| Akten: Fäden, Nachrichten, Review-Stände, gewählte von/bis | `~/.local/share/merge-train/` (`$XDG_DATA_HOME`): `lokal/<projekt>.json`, `reviews/<mr>.json`, `beobachten/` | `aktenschrank/` |
| Seiten-Cache, MR-Liste, Log der Anfragen | `~/.cache/merge-train/` (`$XDG_CACHE_HOME`) | – |

## Einstellungen

`~/.config/merge-train/config.toml`, Vorlage: [`config.example.toml`](config.example.toml). Die wichtigsten Einträge:

| Schlüssel | Standard | Wofür |
|---|---|---|
| `lokal` | `true` | Quelle „lokal“ (Projekt-Diff `claude` → `reviewed`) an/aus |
| `projekte` | `~/Projects` | Ordner mit Repos oder Liste aus Ordnern/einzelnen Repos für „lokal“ |
| `von`, `bis` | `reviewed`, `claude` | „lokal“ vergleicht `bis` gegen `von`. `bis = "arbeitsstand"`: das Arbeitsverzeichnis samt nicht Committetem (z. B. was ein Agent gerade baut) gegen `von = "origin/main"`; Index und Branch bleiben unberührt, „fertig“ gibt es dann nicht |
| `myrling` | `true` | Quelle „Myrling“ (Skripte, die auf eine Prüfung warten) an/aus; aus, wenn `myrling_befehl` fehlt |
| `myrling_befehl` | `nas-lauf` | liefert die anstehenden Läufe (`--anstehend --json`), darf `~` und Argumente enthalten |
| `gitlab` | `true` | Quelle „GitLab“ (MRs) an/aus |
| `gitlab_host` | leer | Host, wenn ihn weder URL noch Remote liefern |
| `mr_liste` | `reviewer,author` | welche MRs der Zug zeigt: `reviewer`, `author`, `assignee` (mehrere mit Komma) oder `keine` |
| `hinweise` | `[]` | Globs für Agent-Hinweis-Dateien (automatische Zuordnung über `branch`) |
| `repos` | `{}` | lokale Klone der GitLab-Projekte (Diff und Dateien kommen nur von dort) |
| `[zweige]` | leer | je lokalem Projekt eigene von/bis: `[zweige.merge-train]` mit `von = "reviewed"`, `bis = "claude"` (auf der Seite gewählte gehen vor) |
| `klon_ordner` | `[]` | Ordner (oder Liste), in denen weitere Klone liegen: ein MR aus `gruppe/metrics-client` findet `<ordner>/metrics-client`, wenn dessen origin auf dieses Projekt zeigt – ohne Eintrag unter `[repos]` |
| `browser` | leer | Browser-Befehl, unter WSL z. B. `wslview` |
| `[agenten]` | leer | Agenten für Fragen zum MR: Name = Startbefehl (siehe [Fragen an einen Agenten](#fragen-an-einen-agenten-gitlab-modus)) |
| `port`, `leerlauf` | `8771`, `3600` | Port des Servers; nach so vielen Sekunden ohne Anfrage beendet er sich. Offene Seiten fragen alle 4 s, ein kurzer Leerlauf (z. B. `120`, Hintergrund-Tabs drosselt der Browser) beendet ihn also bald nach dem Schließen des Tabs |
| `ich_symbol` | `🤓` | dein Symbol in den Listen links („zuletzt von dir“, siehe Kommentarlisten) |
| `vorfall_github` | leer | GitHub-Repo (`owner/repo`), in dem `agent vorfall` ohne `todo` ein Issue anlegt; leer = nur Datei in `vorfaelle/`, die man nach Durchsicht selbst einreicht |
| `log_tage` | `7` | Log der Anfragen an die Quellen (lokales git, GitLab) mit Dauer und Anlass, eine Datei je Tag in `~/.cache/merge-train/aussen-<datum>.log`; so viele Tage aufbewahrt, `0` = aus |

Wird das Skript oder die Einstellungsdatei geändert, startet der Server mit dem neuen Stand neu.

### Beobachten: Arbeitsstand live (z. B. was ein Agent in einem Worktree baut)

```sh
merge-train --beobachten ~/worktrees/merge-train-fable              # nicht Committetes gegen HEAD
merge-train --beobachten ~/worktrees/merge-train-fable --von main   # alles seit main, samt nicht Committetem
merge-train --beobachten --stopp [ordner]                           # diese Instanz beenden
```

Ohne Ordner das aktuelle Repo. Jedes Repo bekommt eine eigene Instanz mit freiem Port. Einstellung, Cache und Gespräch
liegen in `~/.local/share/merge-train/beobachten/<name>-<hash>/`, dein normaler Server und sein Zug bleiben unberührt.

- Ein Watcher (inotify) meldet Änderungen im Arbeitsverzeichnis (ohne ignorierte Dateien, neue Ordner kommen dazu) und an
  HEAD, Index und Branches. Erst dann prüft git, ob sich der Stand wirklich geändert hat, und die Seite lädt neu (nicht, solange
  ein Eingabefeld offen ist). Ohne inotify wird alle 5 s geprüft.
- Nach dem Neuladen hat das seit dem vorigen Stand Neue einen lila Rahmen, die Seite scrollt sanft zur ersten Stelle. Der
  Rahmen bleibt bis zur nächsten Änderung.
- Schließt du den Tab, beendet sich die Instanz nach etwa 10 s (Beacon beim Verlassen der Seite; Neuladen zählt nicht).
  Sonst nach 90 s ohne Anfrage.
- `merge-train agent …` aus diesem Repo landet von selbst bei der Instanz, solange sie läuft (außer das Repo ist ohnehin im
  normalen Zug). Feedback heißt hier: im Arbeitsverzeichnis umsetzen, nicht committen.

## Installation

```sh
git clone git@github.com:Myricaulus/merge-train.git ~/merge-train
~/merge-train/install.idem.sh
```

Das Skript lässt sich beliebig oft aufrufen. Es baut `merge-train` und richtet die Git-Hooks ein (nach
pull/checkout/rebase `./bauen`, vor commit/push `./testen`, siehe [Tests](#tests)). Es verlinkt
`~/.local/bin/merge-train`, den Claude-Skill nach `~/.claude/skills/merge-train` und die fish-Vervollständigung. Fehlen
die Einstellungen, legt es sie an (unter WSL mit `browser = "wslview"`, wenn vorhanden). Dazu kommen die Symlinks
`config` und `aktenschrank` im Repo. Zuletzt prüft es `pygments` und `glab`. Danach:

1. `glab auth login --hostname <gitlab-host>`. Beim Arbeits-GitLab zusätzlich `gitlab_host` eintragen.
2. In `~/.config/merge-train/config.toml` die Einträge `hinweise` (z. B. `"~/workspaces/projekt/tasks/*-review-markers.json"`)
   und `repos` setzen.
3. Unter WSL: `sudo apt install wslu python3-pygments` (`wslview` öffnet den Windows-Browser). Der Server hört auf `127.0.0.1`,
   und WSL2 reicht `localhost` an Windows durch. Klappt das nicht, in `%UserProfile%\.wslconfig` `localhostForwarding=true` setzen.
4. MR-Reviews durch einen Agenten: `install.idem.sh --mr-review` verlinkt den Skill `mr-review`
   ([`skill/mr-review/SKILL.md`](skill/mr-review/SKILL.md)). Er bereitet den Klon vor, prüft gegen die Anforderungen
   und schreibt die Findings als Review-JSON, die merge-train als Hinweise im MR-Diff zeigt (Format und Ausgaben:
   [`docs/agent-hinweise.md`](docs/agent-hinweise.md)). Eigene Skills bauen darauf auf und ergänzen nur, woher die
   Anforderungen kommen (z. B. Jira), Build-Befehle und Sprachen. So macht es `jira-review`.

Python ≥ 3.8 genügt. Ohne `tomllib` (vor 3.11) liest ein einfacher Ersatzparser die Einstellungen.
Er versteht nur `schlüssel = wert`, `[abschnitt]` und einzeilige Listen.

## Entwicklung

Der Code liegt in `src/`: das Python-Paket `src/merge_train/` (ein Modul je Thema; die Reihenfolge der Abhängigkeiten
steht in `__init__.py`), CSS und JS in `src/merge_train/web/`. `./bauen` bündelt alles zu einer ausführbaren Datei
(Python-Zip). Zum Ausprobieren ohne Bauen: `python3 src`.

```sh
./bauen            # src/ → merge-train (schreibt nur bei Änderung; der laufende Server startet dann neu)
./bauen --pruefen  # Exit 1, wenn merge-train nicht zu src/ passt
```

`merge-train` ist das gebaute Ergebnis und nicht eingecheckt (`.gitignore`). `~/.local/bin/merge-train` zeigt darauf.
Die Git-Hooks aus der [Installation](#installation) bauen nach pull/checkout/rebase neu, zum Aktualisieren genügt also
ein `git pull`.

Bausteine:

- **`Waggon`** (`waggon.py`): Schlüssel eines Vergleichs, `Waggon(lokal="proj")` oder `Waggon(host=…, projekt=…, iid=…)`;
  daran `.id` (Kennung der Seite), `.name`, `.url`, `.dateiname`, `.kann` (review/fertig/committen). `Fehler` = Meldung
  für Nutzer oder Agent.
- **Akte je Waggon** (`akte.py`, Aufbau der Datei oben dort): Review-Kommentare, Gesprächsfäden, Hinweis-Status. Ändern
  nur mit `with akte_bearbeiten(waggon) as akte:` (sperrt auch gegen andere Prozesse wie `merge-train agent`, speichert
  nur bei Änderung, nicht bei einer Ausnahme), Aktionen der Seite über `aktion_ausfuehren` (abgelehnt = nichts
  gespeichert), lesen mit `akte_lesen`. Gesperrt keine GitLab-Anfragen.
- **Server** (`server.py`): Handler mit `@route(methode, pfad, …)`; Schlüssel, Quelle, Waggon, Struktur und Fehler
  behandelt `bearbeiten()` an einer Stelle. Ein Handler bekommt `waggon=`/`struktur=` als Schlüsselwörter und gibt ein
  dict (JSON 200) oder eine `Antwort` zurück. Fehlercodes: `Ungueltig` 400, `GitLabFehler` 502, sonst `Fehler` 409.
  Starten, Bewachen und `--stopp` stehen in `prozess.py`.
- **Seiten-Skripte** (`web/*.js`, Liste und Reihenfolge in `web.py`): jede Datei in eigener Funktion, gemeinsam nur über
  `App` (`app.js`); oben in jeder Datei, was sie braucht und bereitstellt.

Prüfwerkzeuge:

```sh
python3 werkzeug/imports_richten.py                                              # Import-Zeilen neu, meldet Rückwärts-Abhängigkeiten
./bauen && MERGE_TRAIN_CONFIG=/nonexistent python3 werkzeug/namen_pruefen.py merge-train   # vergessene Imports
python3 werkzeug/app_pruefen.py                    # JS: App-Namen, Ladereihenfolge, Kopfkommentare (läuft in ./pruefen)
python3 werkzeug/seiten_vergleich.py [REF]         # Diff-Seite von REF (Standard HEAD) und Arbeitsstand im Browser vergleichen
```

`seiten_vergleich.py` ist für Umbauten am JS gedacht, die nichts am Verhalten ändern sollen: Es baut beide Stände, legt
ein Test-Repo an, spielt in Chromium dieselben Schritte durch (Seite, Fäden, Antwort, Popups, Toast) und vergleicht das
DOM. Braucht `chromium` (`sudo pacman -Syu chromium`), kein Node.

Neue Module in `werkzeug/imports_richten.py` (`REIHENFOLGE`) und `src/merge_train/__init__.py` eintragen; Namen müssen
paketweit eindeutig sein. Die Seite im Browser ausprobieren: `python3 src --beobachten` (eigene Instanz, eigener Port)
oder eigener Server mit eigener Konfig (`port = …`, `MERGE_TRAIN_CONFIG=…`), nie der auf 8771.

## Tests

```sh
./testen                          # nur, was die Änderungen betreffen (pre-commit-Hook); --voll alles, --liste nur zeigen
python3 tests/test_einheiten.py   # Logik einzeln (Zeilen, Stufen, Akte, Routen, Abschließen gegen GitLab-Fake), < 1 s
python3 tests/test_gitlab.py      # GitLab-Modus komplett, mit tests/fake-glab statt GitLab
```

Was `./testen` wann auswählt und wie der pre-push-Hook schon getestete Stände überspringt:
[`docs/funktionen.md`](docs/funktionen.md#21-tests-mini-ci).
`./pruefen` lintet `src/merge_train/web/*.js|css` mit Biome (Regeln in `biome.json`), je Seite das Bündel, das sie bekommt.
Ohne Biome, aber mit node prüft es nur die Syntax der Bündel (`node --check`); Biome gibt es auch über
`npm install -g @biomejs/biome`. Vorher prüft es mit `werkzeug/app_pruefen.py`, wie die Dateien über `App` zusammenhängen.

`tests/fake-glab` spielt `glab api` gegen ein lokales Git-Repo nach: MR, Diffs, Commits, Dateien, Draft-Notes und Diskussionen.
Mit `--behalten` bleibt der Testordner liegen.

## Lizenz

Copyright © 2026 Myricaulus. merge-train steht unter der [GNU Affero General Public License v3.0](LICENSE)
(AGPL-3.0-only): Nutzen, Ändern und Weitergeben sind frei; wer eine geänderte Fassung weitergibt oder anderen über ein
Netzwerk anbietet, legt ihren Quelltext unter derselben Lizenz offen.

**Kommerzielle Lizenz:** Für Unternehmen, die merge-train ohne die Pflichten der AGPL einsetzen oder einbauen wollen,
gibt es eine kommerzielle Lizenz auf Anfrage (Kontakt über GitHub, [@Myricaulus](https://github.com/Myricaulus)).

**Beiträge:** Damit beide Lizenzen möglich bleiben, werden Beiträge nur mit einer Übertragung der Nutzungsrechte an den
Rechteinhaber übernommen; bitte vor einem Pull-Request ein Issue aufmachen.

Ausgenommen ist `src/merge_train/web/gitlab.svg`: das GitLab-Logo, eine Marke von GitLab Inc., hier nur als Hinweis
auf GitLab-Links.
