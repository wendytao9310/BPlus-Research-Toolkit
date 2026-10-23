#!/usr/bin/env python
"""Run SeetaPsych after acquisition; never inside the PsychoPy presentation loop."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.adapters.seetapsych import (SeetaPsychAdapter, SeetaPsychSettings, analyze_video)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="BPlus SeetaPsych 离线视频分析")
    ap.add_argument("video", type=Path)
    ap.add_argument("--participant", required=True)
    ap.add_argument("--session", default="1")
    ap.add_argument("--out", type=Path, default=Path("data/session"))
    ap.add_argument("--with-gaze", action="store_true", help="加入屏幕注视点（需先完成相机/屏幕标定）")
    ap.add_argument("--prepare", action="store_true", help="允许 SeetaPsych 安装模块依赖并缓存模型")
    args = ap.parse_args(argv)
    attrs = list(SeetaPsychSettings().attributes)
    if args.with_gaze:
        attrs.append("face/gaze_screen")
    settings = SeetaPsychSettings(attributes=tuple(attrs), install_requirements=args.prepare,
                                  cache_models=args.prepare)
    adapter = SeetaPsychAdapter(settings)
    stem = args.out / f"sub-{args.participant}_ses-{args.session}_seetapsych"
    jsonl_path, csv_path, count = analyze_video(adapter, args.video, stem)
    print(json.dumps({"jsonl": str(jsonl_path), "csv": str(csv_path), "frames": count,
                      "attributes": attrs}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
