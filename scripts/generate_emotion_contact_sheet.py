#!/usr/bin/env python
"""生成情绪刺激 contact sheet（人工审核用）。等价于 `emotion_library.py contacts`。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scripts.emotion_library import cmd_contacts  # noqa: E402


class _Args:
    root = "stimuli/emotion"


if __name__ == "__main__":
    raise SystemExit(cmd_contacts(_Args()))
