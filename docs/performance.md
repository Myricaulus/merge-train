# Performance: Messungen an einem großen MR

Gemessen am 9.11.2026 an `gruppe/projekt/quelle!161` (PROJ-824): 140–142 Dateien, darunter Integrationstests mit
1.734 neuen Zeilen, zwei generierte EF-Migrationsdateien und ein SQL-Ausgabe-Dump mit 1 MB. Rechner: Laptop, WSL2.
Browser für die Messung: Playwright-Chromium (`chrome-headless-shell`, Revision 1228) in WSL, ohne GPU.
Mit Firefox unter Windows ist nicht gemessen, dort fühlt es sich flüssig an.

## Ergebnis

| | vorher (GitLab-API) | lokal, erster Stand | lokal, jetzt |
|---|---|---|---|
| Dateien mit Diff | 86 von 140 (54 „collapsed“/„too_large“) | 142 | 142 |
| Seite erzeugen, kalt | 4,7 s | 4,3 s | 2,7–3,2 s |
| `agent pruefen`, Seite im Cache | 1,3 s | 1,4 s | 1,1 s |
| Seite abrufen, Cache | 0,5 s | – | 0,6 s (davon ~0,5 s GitLab: aktueller MR-Stand) |
| HTML-Größe | 2,0 MB | 9,6 MB | 3,8 MB |
| DOM fertig (Server-Antwort ~0,6 s) | – | 4,5 s | 2,5 s (frischer Browser), 0,2 s (weitere Ladevorgänge) |
| Inline-Ansicht (`i`) | im HTML | im HTML | 0,2 s (anfangs 4,4 s, siehe unten) |
| Kontext nachladen | – | – | 0,1–0,2 s |
| große Datei nachladen | – | – | 0,07–0,2 s |
| `/api/review` (warm) | – | – | 7 ms, Zeichnen 7 ms |

## Was die Zeit gekostet hat und was geholfen hat

Profil des Seitenaufbaus im lokalen Modus (cProfile, 7,4 s mit Profiler-Overhead):

1. **Lexer-Suche, 1,8 s**: `pygments.get_lexer_for_filename` durchsucht bei jedem Aufruf alle Plugin-Entry-Points
   (~6 ms), 284 Aufrufe. Jetzt einmal pro Dateiendung (`_LEXER`).
2. **Token-Klassen, 1,6 s**: `klasse(tt)` für über 300.000 Tokens, jedes Mal eine Kette von `in`-Prüfungen.
   Jetzt pro Token-Typ gemerkt (`_KLASSE`).
3. **Jede Zeile doppelt im HTML**: Die Tabellen nebeneinander und inline standen beide in der Seite.
   Jetzt baut der Browser die Inline-Tabelle beim ersten `i` (`inlBauen`). Die Seite ist damit nur noch halb so groß.
4. **Riesen-Dateien**: Generierte Dateien (`*.Designer.cs`, `*ModelSnapshot.cs`, Lockfiles, `.min.js`, `.snap`) und
   Diffs über 3.000 Zeilen oder 300 KB werden erst auf Klick geladen (`/api/datei`). Liegt ein Hinweis oder
   Kommentar darin, lädt die Datei automatisch. Allein der SQL-Dump hatte 2,15 MB HTML.
5. **Alle Dateiinhalte mit einem Aufruf**: `git cat-file --batch` statt einzelner `git show`.

Im Browser:

6. **`content-visibility:auto` auf `.datei`**: Nur sichtbare Dateien werden gerendert, gesucht wird trotzdem
   überall, Strg+F funktioniert. Jede Datei bekommt eine geschätzte Höhe (`contain-intrinsic-size`,
   19 px pro Diffzeile, seit 2 px mehr Zeilenabstand 21 px), damit Scrollbalken und Sprünge über die Dateiliste stimmen (gemessen: 8 px Abstand = `scroll-margin`).
   Datei-Variante der Seite: DOM fertig 0,8–2,8 s → 0,2 s (beim wiederholten Laden im selben Browser).
7. **MR-Zug blockierte den Seitenaufbau**: `<script src="/mrzug.js">` im `<head>` wartete auf zwei GitLab-Abfragen.
   Jetzt per `fetch` nach dem Aufbau. Bis die Antwort da ist, zeichnet die Seite den zuletzt gesehenen Zug aus
   `localStorage`, und `#zug` hält 92 px frei, damit nichts springt.
8. **Inline-Ansicht 4,4 s → 0,2 s**: Nach jeder der 139 gebauten Tabellen lief ein komplettes `zeichnen()`.
   Jetzt einmal am Ende, und die Zeilen werden als ein HTML-String pro Tabelle gebaut statt Zeile für Zeile.

## Offen: ~2 s beim ersten Laden in einem frischen Browser

Beim ersten Laden in einem frisch gestarteten Headless-Chromium vergehen zwischen dem Eintreffen des HTML
(~0,6 s) und „DOM fertig“ etwa 1,9 s. Jeder weitere Ladevorgang derselben Seite im selben Browser braucht ~0,2 s.

Was der Trace zeigt (`perf/trace.mjs`): fast die ganze Zeit ist **ein einziger `Layout`-Block (~1,6 s)**,
`ParseHTML` nur ~50 ms.

Was es **nicht** ist (je ein frischer Browser pro Messung, `perf/frisch.mjs` / `perf/erstladen.mjs`):

| Variante | DOM fertig |
|---|---|
| Seite wie ausgeliefert | 1.958 / 2.003 ms |
| ohne `content-visibility` | 2.755 / 2.660 ms |
| ohne jedes Skript | 1.987 / 2.069 ms |
| Skript erst nach dem ersten Frame | 1.996 / 1.970 ms |
| Dateien ab der 4. zuerst `content-visibility:hidden` | 2.050 / 2.076 ms |
| vorher eine Aufwärmseite mit `⋯ → − ✎ 🤖 💬` (Schrift-Fallback) | 3.752 ms |

- Skripte (erzwungenes Layout durch `kh()`/`markiere()`) sind es nicht: ohne Skript gleich lang.
- Schrift-Fallback für Sonderzeichen ist es vermutlich nicht. Die Aufwärmseite hat aber womöglich nie gerendert
  (data:-URL, 7 ms), also nicht ganz sicher.
- `content-visibility` hilft nur wenig (2,7 → 2,0 s). Selbst `hidden` ab der 4. Datei ändert nichts.
  Das spricht dafür, dass nicht das Layout der Diff-Tabellen die Zeit kostet.

Ideen für die weitere Suche:

- Im Trace die `Layout`-Events genauer ansehen (`args.beginData`/`endData`: `dirtyObjects`, `totalObjects`, welcher Root).
- Gleiche Messung mit einem Chromium **mit** GPU bzw. direkt unter Windows (Firefox-Profiler), um WSL/Software-Rendering
  auszuschließen. Unter WSL bindet `~/.config/fontconfig/fonts.conf` `/mnt/c/Windows/Fonts` über 9p ein. Der erste
  Zugriff auf eine Schrift kann dort teuer sein. Test: `FONTCONFIG_FILE` auf eine Konfiguration ohne die Windows-Schriften setzen.
- Halbieren: die linke Dateiliste (142 Links) und den Kopf ohne die Dateien laden. Bleibt die Zeit, liegt es am Anlaufen des Browsers.

## Messskripte

Alle in `perf/`. Sie nutzen das Puppeteer aus der npx-Installation von `chrome-devtools-mcp` und Playwrights
Headless-Shell. Pfade über `PUPPETEER` (Pfad zu `…/chrome-devtools-mcp/build/src/third_party/index.js`) und
`CHROME` (Browser-Binary) überschreibbar.

```sh
merge-train agent zeigen tasks/PROJ-824-review-markers.json --nicht-oeffnen    # Server starten, Seite erzeugen
URL=http://127.0.0.1:8771/mr/gitlab.example.com/gruppe/projekt/quelle/161
node perf/browser-messung.mjs $URL       # Ladezeit + Funktionsprobe (Kontext, Inline, Popup, große Datei, Sprung/Sticky, JS-Fehler)
node perf/trace.mjs $URL /tmp/trace.json # Trace aufnehmen, Summe der langen Events
node perf/erstladen.mjs ~/.cache/merge-train/mr/<seite>.html /tmp/varianten   # Varianten ohne/mit verschobenem Skript
node perf/frisch.mjs /tmp/varianten aktuell ohneSkript                          # jede Variante in frischem Browser
```

Die Skripte lesen nur. Sie legen keine Kommentare an und ändern keinen Review-Stand.
Seitenaufbau in Python profilieren:

```python
import importlib.util, importlib.machinery, cProfile, pstats
loader = importlib.machinery.SourceFileLoader("mt", "merge-train")
spec = importlib.util.spec_from_loader("mt", loader); m = importlib.util.module_from_spec(spec); loader.exec_module(m)
mr = m.mr_vollstaendig(m.mr_ref("https://gitlab.example.com/gruppe/projekt/quelle/-/merge_requests/161"))
cProfile.run("m.mr_seite(mr)", sort="cumulative")   # vorher den Cache ~/.cache/merge-train/mr/*161* löschen
```
