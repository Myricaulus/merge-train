"""merge-train als Paket. Die Module bauen in dieser Reihenfolge aufeinander auf (jedes nutzt nur die davor):

  einstellungen  Einstellungen, Ordner, kleine Helfer
  git            lokales git: Aufruf, Diff zerlegen, Arbeitsstand, Repos, Dateiinhalte
  syntax         Syntaxhervorhebung
  zeilen         Zeilen-Arithmetik (alt ↔ neu)
  web            CSS, JavaScript, Bilder aus web/
  diff_html      HTML eines Datei-Diffs
  zustand        Zustand je Waggon (JSON): Kommentare, Fäden, Struktur der Seite
  gitlab         GitLab über glab
  hinweise       Agent-Hinweise (drafts) lesen und auflösen
  ansichten      Ansichten: alles, commit:<sha>, seit:<sha>
  seite          Seiten bauen (fragt beim Aufruf die Quellen: einzige Rückwärts-Abhängigkeit)
  quellen        Lokal und GitLab: was die Quellen können
  zuhoerer       Agenten-Sessions, die zuhören
  review         Review-Kommentare, Abgleich mit GitLab, abschließen
  gespraech      Gespräch mit dem Agenten
  server         HTTP-Server
  agent_cli      merge-train agent …
  cli            Aufruf von der Kommandozeile
"""
