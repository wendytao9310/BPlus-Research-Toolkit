#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "$0")/.." && pwd)"
build_root="${BPLUS_BUILD_ROOT:-/tmp/bplus-macos-build}"
python_bin="${BPLUS_BUILD_PYTHON:-$project_root/.venv/bin/python}"

mkdir -p "$build_root/pyinstaller-config" "$build_root/matplotlib"
export PYINSTALLER_CONFIG_DIR="$build_root/pyinstaller-config"
export MPLCONFIGDIR="$build_root/matplotlib"

cd "$project_root"
"$python_bin" -m PyInstaller --noconfirm --clean \
  --windowed --onedir --name "BPlus Research Toolkit" \
  --paths src \
  --add-data configs:configs \
  --add-data stimuli:stimuli \
  --add-data src/bplus/reports/templates:bplus/reports/templates \
  --collect-data psychopy --collect-submodules bplus \
  --hidden-import tkinter \
  --hidden-import psychopy.visual --hidden-import psychopy.sound \
  --hidden-import psychopy.event --hidden-import psychopy.core \
  --hidden-import psychopy.parallel --hidden-import psychopy.hardware.labjacks \
  --exclude-module psychopy.iohub.devices.eyetracker \
  --distpath "$build_root/dist" --workpath "$build_root/work" \
  launcher/bplus_launcher.py

app="$build_root/dist/BPlus Research Toolkit.app"
smoke="$build_root/frozen-smoke"
rm -rf "$smoke"
BPLUS_USER_DATA_DIR="$build_root/user-data" \
  "$app/Contents/MacOS/BPlus Research Toolkit" --bplus-self-test "$smoke"

echo "Built and smoke-tested: $app"
