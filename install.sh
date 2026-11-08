#!/bin/sh
# merge-train auf diesem Rechner einrichten.
#   ./install.sh             lokaler Projekt-Diff + GitLab
#   ./install.sh --nur-gitlab  nur GitLab-MRs (lokal = false), z. B. unter WSL
set -e
HIER=$(cd "$(dirname "$0")" && pwd)
NUR_GITLAB=0
[ "$1" = "--nur-gitlab" ] && NUR_GITLAB=1

python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || { echo "Python ≥ 3.8 nötig"; exit 1; }

mkdir -p "$HOME/.local/bin"
ln -sf "$HIER/merge-train" "$HOME/.local/bin/merge-train"
echo "✓ ~/.local/bin/merge-train → $HIER/merge-train"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "  Hinweis: ~/.local/bin ist nicht im PATH";; esac

if [ -d "$HOME/.config/fish" ]; then
  mkdir -p "$HOME/.config/fish/completions"
  ln -sf "$HIER/completions/merge-train.fish" "$HOME/.config/fish/completions/merge-train.fish"
  echo "✓ fish-Vervollständigung"
fi

KONF="${XDG_CONFIG_HOME:-$HOME/.config}/merge-train/config.toml"
if [ ! -e "$KONF" ]; then
  mkdir -p "$(dirname "$KONF")"
  cp "$HIER/config.example.toml" "$KONF"
  if [ $NUR_GITLAB = 1 ]; then
    sed -i 's/^# lokal = true/lokal = false/' "$KONF"
  fi
  if grep -qi microsoft /proc/version 2>/dev/null && command -v wslview >/dev/null; then
    sed -i 's/^# browser = ""/browser = "wslview"/' "$KONF"
  fi
  echo "✓ Einstellungen: $KONF (bitte ansehen: hinweise, repos, gitlab_host)"
else
  echo "• Einstellungen schon vorhanden: $KONF"
fi

python3 -c 'import pygments' 2>/dev/null && echo "✓ pygments" || \
  echo "• pygments fehlt (ohne Syntaxfarben): sudo apt install python3-pygments  bzw.  pip install --user pygments"
if command -v glab >/dev/null; then
  echo "✓ glab $(glab --version 2>/dev/null | head -1)"
  glab auth status >/dev/null 2>&1 && echo "✓ glab angemeldet" || echo "• glab noch nicht angemeldet: glab auth login --hostname <gitlab-host>"
else
  echo "• glab fehlt: https://gitlab.com/gitlab-org/cli#installation"
fi
if grep -qi microsoft /proc/version 2>/dev/null && ! command -v wslview >/dev/null && ! command -v xdg-open >/dev/null; then
  echo "• WSL: wslview fehlt (sudo apt install wslu), sonst wird explorer.exe genommen"
fi
