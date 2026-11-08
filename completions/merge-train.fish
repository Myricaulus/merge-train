# fish-Vervollständigung für merge-train (verlinkt nach ~/.config/fish/completions/)
complete -c merge-train -f
complete -c merge-train -n 'not string match -q -- "-*" (commandline -ct)' -a '(merge-train --projekte 2>/dev/null)'
complete -c merge-train -l inline -d 'inline statt nebeneinander starten'
complete -c merge-train -l nur-datei -d 'Seite nur erzeugen, nicht öffnen'
complete -c merge-train -l von -x -a '(git branch --format="%(refname:short)" 2>/dev/null)' -d 'Basis (Standard: reviewed)'
complete -c merge-train -l bis -x -a '(git branch --format="%(refname:short)" 2>/dev/null)' -d 'Ziel (Standard: claude)'
complete -c merge-train -s h -l help -d 'Hilfe anzeigen'
complete -c merge-train -l mrs -d 'GitLab-MRs zum Review'
complete -c merge-train -n '__fish_is_first_arg' -a agent -d 'Agent-Hinweise (jira-review) zu einem MR'
complete -c merge-train -n '__fish_seen_subcommand_from agent; and not __fish_seen_subcommand_from zeigen pruefen' -a 'zeigen pruefen'
complete -c merge-train -n '__fish_seen_subcommand_from zeigen pruefen' -F -a '(__fish_complete_suffix .json)'
complete -c merge-train -n '__fish_seen_subcommand_from zeigen pruefen' -l mr -x -d 'MR-URL oder !iid'
complete -c merge-train -n '__fish_seen_subcommand_from zeigen' -l nicht-oeffnen -d 'nur URL ausgeben'
