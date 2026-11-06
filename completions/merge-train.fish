# fish-Vervollständigung für merge-train (verlinkt nach ~/.config/fish/completions/)
complete -c merge-train -f
complete -c merge-train -n 'not string match -q -- "-*" (commandline -ct)' -a '(merge-train --projekte 2>/dev/null)'
complete -c merge-train -l einrichten -d 'Link-Handler mr:// für als Datei geöffnete Seiten einrichten'
complete -c merge-train -l inline -d 'inline statt nebeneinander starten'
complete -c merge-train -l nur-datei -d 'Seite nur erzeugen, nicht öffnen'
complete -c merge-train -l von -x -a '(git branch --format="%(refname:short)" 2>/dev/null)' -d 'Basis (Standard: reviewed)'
complete -c merge-train -l bis -x -a '(git branch --format="%(refname:short)" 2>/dev/null)' -d 'Ziel (Standard: claude)'
complete -c merge-train -s h -l help -d 'Hilfe anzeigen'
