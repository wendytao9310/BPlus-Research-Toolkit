#!/usr/bin/env python
"""情绪刺激评定的 pilot 任务（真实 PsychoPy / 无头 DEMO）。

    # 无头预演（自动生成"像人"的评分，验证整条链路）
    python scripts/emotion_rating_task.py --rater DEMO01 --dummy --out data/pilot_emotion

    # 真机（被试看刺激后用数字键 1–5 评分）
    python scripts/emotion_rating_task.py --rater P01 --out data/pilot_emotion --real

每人产出：data/pilot_emotion/<rater>_ratings.csv
评定维度（见 PILOT_PROTOCOL.md）：效价 / 唤醒度 / 情绪类别 / 强度 / 清晰度 /
年龄观感 / 文化熟悉度 / 是否不适。
"""
from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.stimuli import load_manifest  # noqa: E402

QUESTIONS = [
    ("valence",  "这张脸的情绪有多不愉快 / 愉快？ 1=非常不愉快 … 5=非常愉快", ["1", "2", "3", "4", "5"]),
    ("arousal",  "这张脸的情绪有多激动？ 1=非常平静 … 5=非常激动", ["1", "2", "3", "4", "5"]),
    ("category", "你判断这张脸是：1=负性 2=中性 3=正性", ["1", "2", "3"]),
    ("intensity", "情绪表达的强度？ 1=很弱 … 5=很强", ["1", "2", "3", "4", "5"]),
    ("clarity",  "表情是否清晰可辨？ 1=很不清晰 … 5=很清晰", ["1", "2", "3", "4", "5"]),
    ("age_look", "这张脸看起来像几岁？ 1=儿童 2=青少年 3=青年 4=中年 5=老年", ["1", "2", "3", "4", "5"]),
    ("culture_fit", "这张脸在中国青少年中是否常见 / 熟悉？ 1=很不熟悉 … 5=很熟悉", ["1", "2", "3", "4", "5"]),
    ("discomfort", "这张图是否让你感到不适？ 1=否 2=轻微 3=明显", ["1", "2", "3"]),
]
FIELDS = ["rater", "stimulus_id", "condition", "block_order"] + [q[0] for q in QUESTIONS]


def simulate_ratings(manifest, rater: str, rng: random.Random) -> list[dict]:
    """DEMO：按"像人"的分布生成评分（正/中/负的效价与唤醒度分布不同）。"""
    rows = []
    for i, r in enumerate(manifest, start=1):
        base_val = {"positive": 4.1, "neutral": 3.0, "negative": 2.0}[r.condition]
        base_aro = {"positive": 3.4, "neutral": 2.6, "negative": 3.6}[r.condition]
        clamp = lambda x: int(min(5, max(1, round(x))))
        rows.append({
            "rater": rater, "stimulus_id": r.stimulus_id, "condition": r.condition, "block_order": i,
            "valence": clamp(base_val + rng.gauss(0, 0.5)),
            "arousal": clamp(base_aro + rng.gauss(0, 0.5)),
            "category": {"positive": 3, "neutral": 2, "negative": 1}[r.condition] if rng.random() > 0.15
                        else rng.randint(1, 3),
            "intensity": clamp({"positive": 3.6, "neutral": 2.6, "negative": 3.7}[r.condition] + rng.gauss(0, 0.6)),
            "clarity": clamp(4.3 + rng.gauss(0, 0.5)),
            "age_look": clamp(2.2 + rng.gauss(0, 0.4)),
            "culture_fit": clamp(3.4 + rng.gauss(0, 0.7)),
            "discomfort": 1 if rng.random() > 0.05 else 2,
        })
    return rows


def run_real(manifest, rater: str, *, face_s: float = 3.0, start_delay_s: float = 5.0) -> list[dict]:
    """真机：PsychoPy 呈现 + 数字键评分。"""
    from psychopy import core, event, visual

    win = visual.Window(size=(1280, 800), fullscr=True, color="black", units="pix")
    face = visual.ImageStim(win, image=None, size=(560, 560))
    text = visual.TextStim(win, text="", color="white", height=26, wrapWidth=1000)
    clock = core.Clock()
    rows = []
    text.text = ("接下来你会看到一些表情图片。\n\n"
                 "每张图后请用数字键回答 8 个问题。\n"
                 "如果任何一张让你不舒服，你可以随时按 ESC 停止。\n\n"
                 "按空格开始。")
    text.draw(); win.flip(); event.waitKeys(keyList=["space", "escape"])
    for i, r in enumerate(manifest, start=1):
        face.image = str(Path("stimuli/emotion") / r.file)
        face.draw(); win.flip(); core.wait(face_s)
        text.text = "+"; text.draw(); win.flip(); core.wait(0.5)
        answers = {}
        for key, prompt, allowed in QUESTIONS:
            text.text = f"({i}/{len(manifest)}) {prompt}"
            text.draw(); win.flip()
            resp = event.waitKeys(keyList=allowed + ["escape"], timeStamped=clock)
            if resp and resp[0][0] == "escape":
                win.close(); return rows
            answers[key] = int(resp[0][0])
        rows.append({"rater": rater, "stimulus_id": r.stimulus_id, "condition": r.condition,
                     "block_order": i, **answers})
    text.text = "评定结束，感谢你的参与！\n\n按空格退出。"; text.draw(); win.flip()
    event.waitKeys(keyList=["space"])
    win.close()
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="情绪刺激评定 pilot 任务")
    ap.add_argument("--rater", required=True)
    ap.add_argument("--out", default="data/pilot_emotion")
    ap.add_argument("--dummy", action="store_true")
    ap.add_argument("--real", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)

    manifest = load_manifest("stimuli/emotion")
    if not manifest:
        print("manifest.csv 为空：先登记刺激"); return 2
    rows = simulate_ratings(manifest, args.rater, random.Random(args.seed)) if not args.real \
        else run_real(manifest, args.rater)

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    path = out / f"{args.rater}_ratings.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    print(f"已写入 {path}（{len(rows)} 张）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
