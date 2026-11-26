# Ein Waggon je Branch (Zielbild)

*Mit dem Nutzer abgestimmt am 26.11.2026. Schritte 1–3 sind gebaut, 4 steht als todo-Eintrag im Projekt.*

## Worum es geht

Ein Waggon ist ein Branch in einem lokalen Klon. Quellen wie GitLab (später GitHub) sind Schichten auf diesem Branch:
Hat er einen MR, kommen dessen Diskussionen, Agent-Hinweise und „Review abschließen“ dazu. Ohne MR bleibt es beim Diff,
den Fäden und „fertig“. So gibt es für einen Branch genau einen Ort für Fäden und Kommentare, egal ob der Agent sie im
Klon anlegt oder eine Quelle sie liefert.

Läufe des Myrlings sind Skripte, keine Branches. Sie bleiben eine eigene Art.

## Regeln

- **Arbeitsstand nur für den ausgecheckten Branch.** Ist der Branch im Klon ausgecheckt, zeigt der Waggon den
  Arbeitsstand (auch nicht Committetes). Jeder andere Branch zeigt seinen letzten Commit.
- **Auschecken nur sauber.** Beim ersten Öffnen eines MR checkt merge-train seinen Quell-Branch aus, wenn das
  Arbeitsverzeichnis sauber ist (das geht schnell, und so ist es überall gleich). Ging das nicht oder hast du danach
  selbst gewechselt, sagt ein Hinweis, dass die Seite nur aus den Refs liest, und bietet „auschecken“ an.
- **von:** mit MR der Ziel-Branch (gemeinsamer Vorgänger), ohne MR `von` des Projekts (Standard `reviewed`). „fertig“
  gibt es, wo `von` ein lokaler Branch ist und kein Arbeitsstand gezeigt wird.
- **Der Agent darf umsetzen** auf dem eigenen Branch (eigener MR oder Branch ohne MR), beim fremden MR nur antworten.
- **Kommentare aus Quellen im Arbeitsstand:** Sie hängen an ihrem Anker (Stand der Quelle + Zeile + Code der Zeile)
  und werden auf den Arbeitsstand umgerechnet:
  - Zeile unverändert: der Kommentar rückt mit.
  - Zeile lokal geändert: er bleibt etwa an seiner Stelle im geänderten Block, markiert „lokal geändert“, mit dem
    damaligen Code.
  - Zeile weg: er steht an der nächsten noch vorhandenen Zeile, ebenso markiert.
  - Bei einer unsicheren Zuordnung kann der Nutzer sie bestätigen („passt hier“). Der bestätigte Ort wird der neue
    Anker (Arbeitsstand + Zeile + Code), die Marke verschwindet, und der Kommentar wandert von dort weiter mit.
- **Eigene Kommentare im Arbeitsstand:** Fäden an den Agenten gehen an jeder Zeile. Ein GitLab-Kommentar an einer Zeile
  geht nur, wo der Code dem gepushten Stand in GitLab entspricht; er bekommt die Position im GitLab-Stand. An lokal
  geänderten Zeilen erst nach dem Push. Antworten auf Diskussionen und allgemeine Kommentare gehen immer.

## Schritte

1. **Eigener MR mit ausgechecktem Quell-Branch = ein Waggon.** Der lokale Waggon geht im MR-Waggon auf (der Zug zeigt
   nur `!42 projekt`). Die Seite zeigt den Arbeitsstand, der Beobachter baut sie bei Änderungen neu. `thread`,
   `feedback`, `status` und `horchen` im Klon gehen an den MR. Die Fäden des lokalen Waggons zu diesem Branch ziehen
   beim ersten Zusammenlegen in den MR um. Kommentare der Quelle hängen an ihrem Anker (Regeln oben), samt
   „passt hier“. GitLab-Kommentare an Zeilen nur, wo der Code dem GitLab-Stand entspricht.
2. **Branch ohne MR:** derselbe Waggon, ohne Kommentare der Quelle, mit Knopf „MR erstellen“. Der fragt zuerst GitLab
   nach einem offenen MR zum Branch und übernimmt ihn, wenn es einen gibt. Sonst kommt eine Rückfrage (Ziel-Branch, Titel,
   Beschreibung, Entwurf; was gepusht wird). Dann pusht er den Branch und legt den MR über die API an (`glab api`, wie
   alle Aufrufe). Danach greift Schritt 1.
3. **Fremder MR:** Ist sein Quell-Branch ausgecheckt, geht der lokale Waggon ebenso im MR auf, aber auf dem
   Commit-Stand; der Agent antwortet nur. Steht der Branch eines MR nicht im Klon, Hinweis „nur lesen“ mit Knopf
   „auschecken“ (nur sauber). Ausgeblendet wird der lokale Waggon nur, wenn er diesen Branch zeigt (bis = Arbeitsstand
   oder der Branch selbst).
4. **Eine Akte je Branch** (4a, Befund und Bauplan: [`branch-akte.md`](branch-akte.md)): lokaler und MR-Waggon eines
   Branches teilen eine Akte (die des MR, die Branch-Datei verweist darauf), Fäden gelöschter oder gemergter Branches
   wandern ins Archiv. Danach (4b, weniger wichtig): Agent-Hinweise über die CLI statt über die Review-JSON
   (jira-review), mit fester id je Hinweis.
