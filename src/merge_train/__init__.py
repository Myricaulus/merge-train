"""merge-train als Paket. Die Module bauen in dieser Reihenfolge aufeinander auf (jedes nutzt nur die davor):

  einstellungen  Einstellungen, Ordner, kleine Helfer
  waggon         der Waggon (lokales Projekt oder MR): Kennung, Name, was er kann; Fehler
  git            lokales git: Aufruf, Diff zerlegen, Arbeitsstand, Repos, Dateiinhalte
  syntax         Syntaxhervorhebung
  zeilen         Zeilen-Arithmetik (alt ↔ neu)
  web            CSS, JavaScript, Bilder aus web/
  diff_html      HTML eines Datei-Diffs
  zustand        Zustand je Waggon (JSON): Kommentare, Fäden, Struktur der Seite
  beobachter     --beobachten: Änderungen im Repo merken (inotify), Seite veraltet, neue Zeilen
  gitlab         GitLab über glab
  hinweise       Agent-Hinweise (drafts) lesen und auflösen
  ansichten      Ansichten: alles, commit:<sha>, seit:<sha>
  seite          Seiten bauen
  quellen        Lokal und GitLab: Ort, Seite und Waggons je Quelle
  zuhoerer       Agenten-Sessions, die zuhören
  review         Review-Kommentare, Abgleich mit GitLab, abschließen
  gespraech      Gespräch mit dem Agenten
  server         HTTP-Server
  instanz        --beobachten: eigene Instanz je Repo (Port, Ordner), agent-Befehle dorthin
  agent_cli      merge-train agent …
  cli            Aufruf von der Kommandozeile
"""
