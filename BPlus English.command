#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT_DIR/.venv-exp/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
fi
if [[ ! -x "$PYTHON" ]]; then
  osascript -e 'display dialog "The BPlus environment is unavailable. Run scripts/setup_environment.sh first." buttons {"OK"} default button 1 with icon stop'
  exit 2
fi
cd "$ROOT_DIR"
mkdir -p logs
echo "===== BPlus English launcher started $(date '+%Y-%m-%d %H:%M:%S') =====" >> logs/launcher.log
exec "$PYTHON" launcher/bplus_launcher.py >> logs/launcher.log 2>&1
