# Eine Akte je Branch (Schritt 4a aus `ein-waggon.md`)

*Mit dem Nutzer abgestimmt, gebaut am 27.11.2026. Schritt 4b (Agent-Hinweise über die CLI statt Review-JSON) kommt
danach und ist dem Nutzer weniger wichtig.*

## Auf dem Laptop testen (echtes GitLab)

Der Laptop holt `main`. Die Commits müssen also erst über `reviewed` nach `main`. Rückmeldungen gehen als Faden in
merge-train oder in den todo-Eintrag „heutige Änderungen auf der Arbeit testen“. Die Ergebnisse von Schritt 3 kommen
vor 4a (am 27.11. mit GitLab getestet, sah gut aus).

**Nach Schritt 3 (Stand `2aa9f45`, prüft Schritt 1–3)**

- *Eigener MR, Quell-Branch ausgecheckt:*
  - Der Zug zeigt nur `!N projekt`, kein lokaler Waggon daneben.
  - Die Seite zeigt den Arbeitsstand. Eine nicht committete Änderung erscheint nach kurzer Zeit, ohne Neuladen.
  - Fäden, die vorher im lokalen Waggon zu diesem Branch hingen, stehen jetzt im MR. In keinem der beiden Waggons
    fehlt einer oder steht doppelt.
  - Im Klon zeigen `merge-train status` und `thread` auf den MR, nicht auf `projekt:…`.
  - Eine GitLab-Diskussion an einer lokal geänderten Zeile ist „lokal geändert“ markiert und zeigt den damaligen Code.
    Nach „passt hier“ verschwindet die Marke, auch nach dem Neuladen.
  - An einer lokal geänderten Zeile gibt es keinen GitLab-Kommentar, nach dem Push schon. Antworten auf Diskussionen
    gehen immer.
- *Branch ohne MR:*
  - „MR erstellen“ zuerst auf einem Branch probieren, der in GitLab schon einen MR hat. merge-train übernimmt ihn, ohne
    einen zweiten anzulegen.
  - Dann echt anlegen, mit „als Entwurf“. Prüfen:
    - Ziel-Branch-Vorschlag: `von` bzw. der Standard-Branch von origin.
    - Titel und Beschreibung kommen aus den Commits.
    - Der Hinweis sagt, was gepusht wird.
    - Der MR in GitLab heißt „Draft: …“.
    - Danach landet die Seite im MR, und es ist ein Waggon (wie oben).
- *Fremder MR (von einem Kollegen):*
  - Mit sauberem Arbeitsverzeichnis öffnen. Der Quell-Branch wird ausgecheckt, der lokale Waggon verschwindet (nur wenn
    er bis = Arbeitsstand hat). Der Agent darf nur antworten.
  - Dann im Klon selbst auf einen anderen Branch wechseln. Unter den Commits erscheint der Hinweis „nur lesen“ mit
    „auschecken“.
  - Mit offenen Änderungen lehnt „auschecken“ ab und nennt den Grund. Mit sauberem Stand checkt es aus, und die Seite
    lädt neu.
  - Fäden aus dem Klon gehen beim fremden MR als Review-Gespräch an den MR.
- *Nebenher:* mehrere Tabs auf denselben MR. Die Branches dürfen nicht hin- und herspringen, denn ausgecheckt wird nur
  beim ersten Öffnen.

**Nach Schritt 4a**

Vorher `DATEN/` sichern: Die Migration schreibt die Projekt-Akten um. Ein Rückweg ist nicht eingebaut.

- *Migration:*
  - Ein Projekt mit Fäden auf mehreren Branches öffnen. Unter „fremde Fäden“ stehen alle noch da, jeder bei seinem
    Branch, keiner fehlt.
  - `DATEN/lokal/<projekt>.json` enthält nur noch `mr`, `zweige` und `zweige_migriert`.
  - Die Branch-Akten liegen unter `DATEN/zweige/<projekt>/`.
- *Eine Akte:*
  - Eigener MR, lokale Seite mit festem bis = Quell-Branch: Es gibt keinen lokalen Waggon neben dem MR (Lücke 2), auch
    wenn ein anderer Branch ausgecheckt ist.
  - Ein im Klon angelegter Faden steht sofort im MR.
  - Haken („abgehakt“) und die Struktur einer Seite stören die andere nicht. Keine Seite gilt ständig als veraltet.
- *MR neu anlegen* (Schritt 2) für einen Branch, der schon Fäden hat: Die Fäden stehen danach im MR.
- *Branch wechseln:* Der Agent antwortet auf einen Faden, nachdem du den Branch gewechselt hast. Die Antwort landet am
  richtigen Faden.
- *Aufräumen:*
  - Einen Branch mit Fäden löschen, einen anderen nach `von` mergen. Spätestens 10 min danach (Seite neu laden) sind
    beide aus „fremde Fäden“ verschwunden.
  - Die Dateien liegen in `DATEN/zweige/<projekt>/archiv/`.
  - Ein geschlossener MR behält seine Fäden, bis sein Branch weg oder gemergt ist.
- *Gespräch:* `merge-train agent horchen` im Klon wacht bei einem neuen Faden auf, auch auf einem Branch mit MR.

## Ziel

Fäden und Review-Daten eines Branches liegen in **einer** Akte. Der lokale Waggon und der MR-Waggon desselben Branches
lesen und schreiben dieselbe Datei; nichts wird kopiert oder umgezogen. Fäden von Branches, die es nicht mehr gibt,
verschwinden aus der Ansicht. URLs, Waggon-Kennungen (`projekt:x`, `host/gruppe/projekt/42`) und der Zug bleiben.

Warum: Mit einer Akte je Projekt (Fäden nur über ihr Feld `branch` getrennt) blieben Fäden gelöschter oder gemergter
Branches für immer unter „fremde Fäden“ (weggeräumt wurde nur bei „fertig“, und im Arbeitsstand gibt es kein „fertig“).
Und zeigte der lokale Waggon einen festen Branch mit MR, der nicht ausgecheckt war, gab es zwei Waggons für denselben
Branch mit getrennten Fäden.

## Aufbau

**Ablage** (unter `DATEN`, Kopfkommentar von `akte.py`)
- `zweige/<quote(projekt)>/<quote(branch)>.json`: Branch-Akte bzw. Verweis `{"verweis": "reviews/<mr>.json"}` (relativ
  zu `DATEN`). `quote(…, safe="")`, damit `a/b` und `a_b` nicht kollidieren.
- `lokal/<projekt>.json` ist die **Projekt-Akte**: nur `mr`, `zweige` (von/bis auf der Seite gewählt) und
  `zweige_migriert`. `zweige_gewaehlt` und `projekt_einstellen` lesen bzw. schreiben sie direkt
  (`projekt_akte_lesen`/`projekt_akte_bearbeiten`): Welche Branch-Akte gilt, hängt selbst von bis ab.
- Begleitdateien (`.horcht`, `.prompt`, `.seite`, `.agent`) bleiben je Waggon in `lokal/`.

**Auflösen** (`akte_datei` → `zweig_akte_pfad`): Migration falls nötig → aktueller Branch (`branch_von`, Klon je Prozess
gemerkt) → Branch-Datei → Verweis folgen (fehlt die MR-Akte, gilt die Branch-Datei). Gibt es das Projekt nicht mehr,
gilt die Projekt-Akte. `akte_bearbeiten` löst einmal auf und speichert in dieselbe Datei, auch wenn dazwischen der
Branch wechselt; `pfad=` an `akte_lesen`/`akte_bearbeiten` nimmt die Akte eines anderen Branches.

**Seiten-Felder** (`struktur`, `abgehakt`, `fuellung`) gehören zu einer Seite, nicht zum Branch. In einer Akte, deren
`mr` ein anderer Waggon ist als der ladende, liegen die des Ladenden unter `seiten[<waggon.id>]`. `_seite_tauschen`
tauscht sie beim Laden nach oben (die des Besitzers nach `seiten[<besitzer>]`) und beim Speichern zurück. Der übrige
Code (`struktur_laden(akte)`) merkt davon nichts.

**Migration** (`zweige_migrieren`, einmal je Projekt beim ersten Zugriff): Fäden nach `branch` auf die Branch-Akten
(vorhandene nach id vereinigt), Fäden ohne Branch und alle übrigen Felder außer `mr`/`zweige` in die Akte des aktuellen
Branches; danach ist `lokal/<projekt>.json` die Projekt-Akte mit `zweige_migriert`. Ein Rückweg ist nicht eingebaut.

**Verknüpfen** (`zweig_verknuepfen`, aus `klon_mrs` beim Zug und bei den Agent-Zielen): Für jedes offene MR aus
`mrs_mit_klon()`, dessen Klon ein lokales Projekt ist, wird die Branch-Datei ein Verweis. Eine echte Branch-Akte gibt
vorher ihre Fäden (und `todo_id`) an die MR-Akte ab, ihre Seiten-Felder nach `seiten["projekt:<p>"]`. Ein Verweis auf
eine andere (alte) MR-Akte zieht die Fäden dieses Branches von dort um. Beim Schließen eines MR bleibt der Verweis.

**Ein Waggon** (`zusammengelegt`, `im_mr_waggon`): Zeigt der lokale Waggon (`branch_von`) den Quell-Branch eines offenen
MR in diesem Klon, geht er im MR-Waggon auf, egal ob der Branch ausgecheckt ist. `mr_wagen` zeigt diese MRs auch ohne
Eintrag in der MR-Liste. Die Agent-Ziele (`gespraech_ziele`) nehmen dann den MR.

**Aufräumen** (`zweige_aufraeumen`, beim Zug, höchstens alle 10 min je Projekt): Branch-Dateien, deren Branch nicht
der aktuelle, bis oder von ist und der weg ist (weder `refs/heads/<b>` noch `refs/remotes/origin/<b>`) oder in von
gemergt: Die echte Datei geht nach `zweige/<p>/archiv/<name>-<zeit>.json`, ein Verweis wird gelöscht (die MR-Akte
bleibt). Achtung: Ein Branch ohne eigene Commits gilt als gemergt, sobald er nicht mehr der aktuelle ist.

**Lesen über Branches hinweg**: „fremde Fäden“ (`gespraech_daten`) = Fäden anderer Branches in der eigenen Akte plus die
aus den Akten der anderen Branches (`andere_zweig_akten`). `faden_antworten` sucht auch dort (der Agent antwortet,
nachdem der Nutzer den Branch gewechselt hat). `agent feedback` und `horchen` bleiben beim aktuellen Branch.

**Tests**: `branch_akte_test` in `tests/test_gitlab.py` (Teil `gemischt`, eigener Datenordner): Migration, fremde Fäden,
Antwort auf einen anderen Branch, Verweis samt Seiten-Feldern, Aufräumen ins Archiv, Lücke 2.
