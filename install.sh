#!/bin/sh
# merge-train auf diesem Rechner einrichten.
#   ./install.sh             lokaler Projekt-Diff + GitLab
#   ./install.sh --nur-gitlab  nur GitLab-MRs (lokal = false), z. B. unter WSL
set -e
HIER=$(cd "$(dirname "$0")" && pwd)
NUR_GITLAB=0
[ "$1" = "--nur-gitlab" ] && NUR_GITLAB=1

python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || { echo "Python ≥ 3.8 nötig"; exit 1; }

# merge-train wird aus src/ gebaut (nicht eingecheckt). Die Git-Hooks bauen nach pull/checkout/rebase neu,
# damit ein `git pull` zum Aktualisieren genügt (der laufende Server startet dann mit dem neuen Stand).
"$HIER/bauen"
HOOKS=$(git -C "$HIER" rev-parse --git-path hooks)
case "$HOOKS" in /*) ;; *) HOOKS="$HIER/$HOOKS";; esac
for h in post-merge post-checkout post-rewrite; do
  if [ -e "$HOOKS/$h" ] && ! grep -q "merge-train: bauen" "$HOOKS/$h"; then
    echo "• $HOOKS/$h gibt es schon – dort selbst \"./bauen\" ergänzen"; continue
  fi
  printf '#!/bin/sh\n# merge-train: bauen (von install.sh)\ncd "$(git rev-parse --show-toplevel)" && ./bauen >/dev/null || true\n' > "$HOOKS/$h"
  chmod +x "$HOOKS/$h"
done
echo "✓ Git-Hooks: nach pull/checkout/rebase wird merge-train neu gebaut"

mkdir -p "$HOME/.local/bin"
ln -sf "$HIER/merge-train" "$HOME/.local/bin/merge-train"
echo "✓ ~/.local/bin/merge-train → $HIER/merge-train"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "  Hinweis: ~/.local/bin ist nicht im PATH";; esac

mkdir -p "$HOME/.claude/skills"
ln -sfn "$HIER/skill/merge-train" "$HOME/.claude/skills/merge-train"
echo "✓ Claude-Skill: ~/.claude/skills/merge-train → $HIER/skill/merge-train"

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

# Zum Hineinschauen (Entwicklung): Einstellung und Aktenschrank (Akten, Fäden, Review-Stände) vom Repo aus
# erreichbar – Symlinks, in .gitignore
DATEN="${XDG_DATA_HOME:-$HOME/.local/share}/merge-train"
mkdir -p "$DATEN"
ln -sfn "$(dirname "$KONF")" "$HIER/config"
ln -sfn "$DATEN" "$HIER/aktenschrank"
echo "✓ $HIER/config → $(dirname "$KONF"), $HIER/aktenschrank → $DATEN"

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
