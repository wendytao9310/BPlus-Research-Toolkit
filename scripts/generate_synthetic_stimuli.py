#!/usr/bin/env python
"""生成**示意图式**情绪面孔占位刺激（不是真人照片，也不是 AI 生成的真人脸）。

用途：让 Emotion 范式在 DEMO / PILOT 下能跑通完整链路。
限制：这些刺激被标记为 `NOT_FOR_REAL_PARTICIPANTS`，**永远不会**通过 REAL MODE 闸门。

    .venv/bin/python scripts/generate_synthetic_stimuli.py --out stimuli/emotion/raw/synthetic --per-condition 8
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

SKIN = [(238, 210, 186), (226, 188, 158), (206, 165, 132), (176, 136, 104)]
HAIR = [(60, 45, 40), (35, 30, 32), (90, 60, 45), (25, 25, 30)]
SIZE = 512


def draw_face(condition: str, idx: int) -> Image.Image:
    img = Image.new("L", (SIZE, SIZE), 200)
    d = ImageDraw.Draw(img)
    skin = SKIN[idx % len(SKIN)][0]
    hair = HAIR[idx % len(HAIR)][0]
    cx, cy, r = SIZE // 2, int(SIZE * 0.52), int(SIZE * 0.32)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=skin, outline=120, width=3)          # 脸
    d.chord([cx - r, cy - r - 18, cx + r, cy + int(r * 0.28)], 180, 360, fill=hair)        # 头发
    eye_y = cy - int(r * 0.18)
    for dx in (-int(r * 0.42), int(r * 0.42)):
        d.ellipse([cx + dx - 16, eye_y - 12, cx + dx + 16, eye_y + 12], fill=40)
        d.ellipse([cx + dx - 5, eye_y - 5, cx + dx + 5, eye_y + 5], fill=10)
    d.line([cx - 30, eye_y - 46, cx + 30, eye_y - 46], fill=hair, width=6)                # 眉
    mouth_y = cy + int(r * 0.42)
    if condition == "positive":                                                            # 微笑
        d.arc([cx - int(r * 0.55), mouth_y - int(r * 0.34), cx + int(r * 0.55), mouth_y + int(r * 0.34)],
              20, 160, fill=60, width=8)
    elif condition == "negative":                                                          # 下弯
        d.arc([cx - int(r * 0.55), mouth_y - int(r * 0.10), cx + int(r * 0.55), mouth_y + int(r * 0.58)],
              200, 340, fill=60, width=8)
    else:                                                                                  # 平直
        d.line([cx - int(r * 0.40), mouth_y, cx + int(r * 0.40), mouth_y], fill=60, width=8)
    d.rectangle([0, 0, SIZE - 1, SIZE - 1], outline=90, width=2)
    d.text((14, 10), f"SYNTHETIC PLACEHOLDER — {condition.upper()} #{idx+1}", fill=90)
    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成示意图式情绪面孔占位刺激")
    ap.add_argument("--out", default="stimuli/emotion/raw/synthetic")
    ap.add_argument("--per-condition", type=int, default=8)
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for cond in ("positive", "neutral", "negative"):
        for i in range(args.per_condition):
            draw_face(cond, i).save(out / f"{cond}_{i+1:02d}.png")
            n += 1
    (out / "README.txt").write_text(
        "SYNTHETIC SCHEMATIC PLACEHOLDERS (项目自绘示意图，非真人照片、非 AI 真人脸).\n"
        "仅用于 DEMO/PILOT 链路验证；标记为 NOT_FOR_REAL_PARTICIPANTS，永远无法通过 REAL MODE 闸门。\n"
        f"共 {n} 张：positive / neutral / negative 各 {args.per_condition} 张。\n", encoding="utf-8")
    print(f"已生成 {n} 张示意图刺激 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
