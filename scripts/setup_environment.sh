#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_DIR="$ROOT_DIR/.venv-exp"
UV_BIN="${UV_BIN:-$HOME/.local/bin/uv}"
# Codex/macOS sandboxes may deny writes to ~/.cache. Keep the installer
# reproducible by using a project-local cache unless the operator overrides it.
UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT_DIR/.uv-cache}"
export UV_CACHE_DIR

if [[ ! -x "$UV_BIN" ]]; then
  echo "[BLOCKED] uv not found at $UV_BIN"
  echo "Install uv once, or set UV_BIN to its absolute path."
  exit 2
fi

if [[ ! -x "$ENV_DIR/bin/python" ]]; then
  "$UV_BIN" venv --python 3.11 "$ENV_DIR"
  echo "[PASS] Created $ENV_DIR"
else
  echo "[PASS] Reusing existing $ENV_DIR"
fi

"$UV_BIN" pip install --python "$ENV_DIR/bin/python" -r "$ROOT_DIR/requirements-lock.txt"
"$ENV_DIR/bin/python" "$ROOT_DIR/scripts/check_environment.py" --profile experiment
