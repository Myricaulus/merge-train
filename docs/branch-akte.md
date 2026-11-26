# Eine Akte je Branch (Schritt 4a aus `ein-waggon.md`): Befund und Bauplan

*Stand 27.11.2026, mit dem Nutzer abgestimmt, noch nicht gebaut. Schritt 4b (Agent-Hinweise über die CLI statt
Review-JSON) kommt danach und ist dem Nutzer weniger wichtig.*

## Ziel

Fäden und Review-Daten eines Branches liegen in **einer** Akte. Der lokale Waggon und der MR-Waggon desselben Branches
lesen und schreiben dieselbe Datei; nichts wird kopiert oder umgezogen. Fäden von Branches, die es nicht mehr gibt,
verschwinden aus der Ansicht. URLs, Waggon-Kennungen (`projekt:x`, `host/gruppe/projekt/42`) und der Zug bleiben.

## Befund (heute)

- Lokale Akte: eine Datei je **Projekt** (`DATEN/lokal/<projekt>.json`). Jeder Faden hat ein Feld `branch`
  (`branch_von`: bis bzw. beim Arbeitsstand der ausgecheckte Branch). Die Seite zeigt nur die Fäden des aktuellen
  Branches (`faeden_von(akte, branch)`), die übrigen nur lesend unter „fremde Fäden“ (`faden_fremd`,
  `gespraech_daten` in `gespraech.py`).
- MR-Akte: eine Datei je MR (`DATEN/reviews/<host_projekt_iid>.json`), Fäden mit `branch` = Quell-Branch.
- Schritt 1–3: Ist der Quell-Branch eines offenen MR ausgecheckt, zieht `faeden_umziehen` (`quellen.py`) die Fäden des
  lokalen Waggons zu diesem Branch einmal in die MR-Akte (`zusammengelegt`).
- **Lücke 1:** Fäden von Branches ohne MR bleiben für immer in der Projekt-Datei. Weggeräumt wird nur bei „fertig“
  (`faeden_archivieren`, nur erledigte), und im Arbeitsstand-Modus gibt es kein „fertig“. Gelöschte oder gemergte
  Branches hängen weiter unter „fremde Fäden“.
- **Lücke 2:** Zeigt der lokale Waggon einen festen Branch (bis = `feature`), der nicht ausgecheckt ist, und hat
  `feature` einen offenen MR, gibt es zwei Waggons für denselben Branch mit getrennten Fäden (`zusammengelegt` fragt nur
  den ausgecheckten Branch).

## Was knirscht und wie es gelöst wird

1. **Seiten-Felder** (`struktur`, `abgehakt`, `fuellung`) gehören zu einer *Seite*, nicht zum Branch. Teilen sich
   lokale Seite und MR-Seite eine Akte, überschreiben sie sich (Seite gilt ständig als veraltet, die CLI rechnet gegen
   die falsche Struktur). Lösung in `akte.py`: In einer Datei, deren `mr` ein anderer Waggon ist als der ladende,
   liegen die Seiten-Felder des Ladenden unter `seiten[<waggon.id>]`. `akte_laden` tauscht sie für die Sicht nach
   oben (die des Besitzers nach `seiten[<besitzer.id>]`), `akte_speichern` tauscht zurück. Der übrige Code
   (`struktur_laden(akte)` an ~23 Stellen) bleibt unverändert.
2. **MR-Daten kommen vor dem Klon** (`mr_meta_holen` bei „↻ MRs“). Lösung: Die MR-Akte bleibt die eigentliche Datei;
   die Branch-Datei wird ein **Verweis** darauf (`{"verweis": "<pfad der MR-Akte>"}`), sobald der Klon des MR ein
   lokales Projekt ist („verknüpfen“).

## Bauplan

**Ablage**
- `DATEN/zweige/<quote(projekt)>/<quote(branch)>.json`: Branch-Akte bzw. Verweis. `quote(…, safe="")`, damit `a/b`
  und `a_b` nicht kollidieren und der Projektname zurückgewonnen werden kann.
- `DATEN/lokal/<projekt>.json` bleibt als **Projekt-Akte**: nur `mr` (`{lokal: p}`), `zweige` (von/bis auf der Seite
  gewählt) und `zweige_migriert`. `zweige_gewaehlt` (`waggon.py`) und `projekt_einstellen` (`quellen.py`) lesen bzw.
  schreiben diese Datei direkt (sonst Rekursion: Auflösen braucht `branch_von` → `von_bis` → `zweige_gewaehlt`).
- Begleitdateien (`.horcht`, `.prompt`, `.seite`, `.agent`) bleiben je Waggon am alten Ort.

**`akte.py`**
- `akte_datei(waggon, ".json")` löst für lokale Waggons auf: Migration falls nötig → aktueller Branch
  (`branch_von(projekt_wurzel(p))`, Wurzel je Prozess cachen, `finde_repos` ist teuer) → Branch-Datei → ggf.
  Verweis folgen. Andere Endungen und MR/Myrling wie bisher.
- `akte_bearbeiten`: Pfad **einmal** auflösen, laden und speichern auf denselben Pfad (Branch-Wechsel dazwischen).
  Optional `pfad=` für einen Faden eines anderen Branches (siehe `faden_antworten`).
- `zweig_akten(projekt)` → [(branch, pfad)] der Geschwister (ohne `archiv/`, Verweise aufgelöst).
- `zweig_verknuepfen(mr, projekt)` (unter der Sperre): Branch-Datei fehlt → Verweis schreiben. Echte Branch-Akte →
  ihre Fäden (und `todo_id`) in die MR-Akte, ihre Seiten-Felder nach `seiten["projekt:<p>"]`, dann Verweis. Verweis auf
  eine *andere* (alte) MR-Akte → die Fäden dieses Branches von dort in die neue umziehen, Verweis umstellen. Beim
  Schließen eines MR bleibt der Verweis (Fäden bleiben sichtbar, bis Aufräumen greift).

**Migration (lazy, je Projekt, „Hausaufgaben“)**: Hat die Projekt-Akte noch kein `zweige_migriert`: Fäden nach
`branch` auf die Branch-Akten verteilen (vorhandene nach id vereinigen), Fäden ohne Branch und alle übrigen Felder außer
`mr`/`zweige` in die Akte des aktuellen Branches; dann Projekt-Akte = `{mr, zweige, zweige_migriert}`.

**`quellen.py`**
- `Lokal.wagen`: für jedes offene MR aus `mrs_mit_klon()`, dessen Klon (realpath) ein Repo aus `finde_repos` ist,
  `zweig_verknuepfen`. Ausblenden (`im_mr_waggon`): der lokale Waggon zeigt (`branch_von`) den Quell-Branch eines
  offenen MR in diesem Klon, egal ob ausgecheckt (schließt Lücke 2). `mr_wagen` zeigt diese MRs dann auch ohne Eintrag
  in der MR-Liste (wie heute `ausgecheckte`).
- `faeden_umziehen` entfällt, `zusammengelegt` liefert nur noch den MR (für die Agent-Ziele in `agent_cli.py`).
- **Aufräumen** (Regel 3), in `Lokal.wagen`, höchstens alle 10 min je Projekt: Branch-Dateien, deren Branch nicht der
  aktuelle, bis oder von ist und der weg ist (weder `refs/heads/<b>` noch `refs/remotes/origin/<b>`) oder in von
  gemergt ist (`merge-base --is-ancestor b von`) → echte Datei nach `zweige/<p>/archiv/<name>-<datum>.json`, Verweis
  löschen (die MR-Akte bleibt).

**Weitere Stellen**
- `gespraech_daten` (`gespraech.py`): „fremde Fäden“ = Fäden anderer Branches in der eigenen Akte + Fäden aus den
  Geschwister-Akten (`zweig_akten`).
- `alle_gespraeche` (`gespraech.py`): auch Projekte aus `DATEN/zweige/*` (unquote), nicht nur aus `lokal/*.json`.
- `faden_antworten` (`agent_cli.py`): Fäden auch in den Geschwister-Akten suchen und mit `pfad=` bearbeiten (der
  Agent antwortet, nachdem der Nutzer den Branch gewechselt hat).
- `zuhoerer.py` Zeilen 113 und 240: `os.path.dirname(akte_datei(waggon))` → `akte_datei(waggon, ".horcht")`, sonst
  zeigt der Glob für lokale Waggons in den Branch-Ordner.
- `akte.py`-Kopfkommentar, `docs/funktionen.md`, `docs/glossar.md` (Branch-Akte, Verweis, Projekt-Akte),
  `docs/ein-waggon.md` (Schritt 4a gebaut), README („Wo liegt was“).

**Tests** (`tests/test_gitlab.py`; die Tests lesen kaum lokale Akten-Pfade, nur `.horcht`):
- Migration: alte Projekt-Akte mit Fäden zweier Branches und einem ohne Branch → Branch-Akten, Marker, nichts verloren.
- Verknüpfen: Klon von MR !1 ist lokales Projekt → `zweige/repo/feature.json` ist ein Verweis; ein lokal angelegter
  Faden landet in der MR-Akte; Seiten-Felder der lokalen Seite stehen unter `seiten`, die MR-`struktur` bleibt.
- Lücke 2: bis = `feature` fest, anderer Branch ausgecheckt → kein lokaler Waggon neben dem MR.
- Aufräumen: Branch mit Faden löschen → seine Datei liegt in `archiv/`, „fremde Fäden“ zeigt ihn nicht mehr.
- `agent antworten` auf einen Faden eines anderen Branches findet ihn.
