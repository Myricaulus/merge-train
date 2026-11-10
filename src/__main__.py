"""merge-train – Merge-Requests claude → reviewed aller Projekte, sofort im Browser.
Dazu: Review von GitLab-Merge-Requests (über glab) mit Kommentaren und Agent-Hinweisen.

Aufruf:
  merge-train [projekt] [--nur-datei]                   lokaler Zug bzw. nur dieses Projekt
  merge-train <MR-URL> | '!42' | gruppe/projekt!42      GitLab-MR reviewen
  merge-train --mrs                                     Zug der MRs, bei denen ich Reviewer bin
  merge-train --stopp                                   Server beenden
  merge-train --beobachten [ordner] [--von HEAD]        Arbeitsstand live beobachten (eigene Instanz)
  merge-train agent zeigen|pruefen <hinweise.json>      Agent-Hinweise zu einem MR (siehe docs/agent-hinweise.md)

Ein kleiner Server auf 127.0.0.1 baut die Seiten beim Abruf (wie der „Changes“-Reiter in GitLab): oben Güterbahnhof
und Zug, darunter Commits, links die Dateiliste, rechts die Diffs mit Syntaxhervorhebung.
Verglichen wird wie in GitLab ab dem gemeinsamen Vorgänger (reviewed...claude).

Tasten: j/k nächste/vorige Datei, i nebeneinander/inline, z alle zu/auf,
c Commits ein-/ausklappen, Enter fertig.

Einstellungen: ~/.config/merge-train/config.toml (Vorlage: config.example.toml).

Der Code liegt im Paket merge_train/ – ein Modul je Thema, die Reihenfolge der Abhängigkeiten steht in merge_train/__init__.py.
"""
from merge_train.cli import main

if __name__ == "__main__":
    main()
