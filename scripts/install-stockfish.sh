#!/usr/bin/env bash
# Install Stockfish for the Master level. Safe to re-run.
set -euo pipefail

if command -v stockfish >/dev/null 2>&1 || [ -x /usr/games/stockfish ]; then
  echo "Stockfish already installed: $(command -v stockfish || echo /usr/games/stockfish)"
  exit 0
fi

case "$(uname -s)" in
  Darwin)
    command -v brew >/dev/null || { echo "Install Homebrew first (https://brew.sh), then: brew install stockfish"; exit 1; }
    brew install stockfish
    ;;
  Linux)
    if command -v apt-get >/dev/null; then
      sudo apt-get update -qq && sudo apt-get install -y stockfish
    elif command -v dnf >/dev/null; then
      sudo dnf install -y stockfish
    elif command -v pacman >/dev/null; then
      sudo pacman -S --noconfirm stockfish
    else
      echo "Unknown package manager. Download a build from https://stockfishchess.org/download/"
      echo "then set RCM_STOCKFISH=/path/to/stockfish"
      exit 1
    fi
    ;;
  *)
    echo "Download Stockfish from https://stockfishchess.org/download/ and set RCM_STOCKFISH=<path>"
    exit 1
    ;;
esac
echo "Installed: $(command -v stockfish || echo /usr/games/stockfish)"
