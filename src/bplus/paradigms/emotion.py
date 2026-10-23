"""Emotional-picture blocks with jittered ITI and block-level valence/arousal ratings.

证据来源（LIT，见 configs/paradigms/emotion.yaml）：
Balconi & Vanutelli, Sci Rep 2016;6:23083 —— 情绪图片 + fNIRS/EEG，块内随机，
刺激 6 s、ISI 8 s。我们保留"块 + 长 ITI"的结构以保护血流动力学回落，
但把刺激缩短为 3 s、ITI 改为 4–6 s 抖动，并把评分集中到块末（避免评分屏打断血氧响应）。
"""
from __future__ import annotations

import random

from ..triggers import TriggerCode
from .base import Event, Paradigm

_CONDITION_CODE = {
    "neutral": TriggerCode.EMOTION_NEUTRAL,
    "positive": TriggerCode.EMOTION_POSITIVE,
    "negative": TriggerCode.EMOTION_NEGATIVE,
}


class EmotionParadigm(Paradigm):
    name = "emotion"

    def events(self) -> list[Event]:
        cfg = self.cfg
        blocks_per_condition = int(cfg.get("blocks_per_condition", 2))
        trials_per_block = int(cfg.get("trials_per_block", 4))
        cue_s = float(cfg.get("cue_s", 0.5))
        face_s = float(cfg.get("face_s", 3.0))
        iti_lo, iti_hi = (float(x) for x in cfg.get("iti_s", [4.0, 6.0]))
        rating_s = float(cfg.get("block_rating_s", 6.0))
        rng = random.Random(int(cfg.get("random_seed", 20260922)))

        blocks = [c for c in ("neutral", "positive", "negative") for _ in range(blocks_per_condition)]
        rng.shuffle(blocks)

        events = [Event(0.0, TriggerCode.EMOTION_START, "EMOTION_START")]
        t = float(cfg.get("start_delay_s", 5.0))
        trial_id = 0
        for block_id, condition in enumerate(blocks, start=1):
            events.append(Event(t, TriggerCode.EMOTION_BLOCK, "EMOTION_BLOCK", block_id=block_id,
                                meta={"condition": condition}))
            t += cue_s
            for _ in range(trials_per_block):
                trial_id += 1
                events.append(Event(t, _CONDITION_CODE[condition], _CONDITION_CODE[condition].name,
                                    trial_id=trial_id, block_id=block_id,
                                    meta={"condition": condition,
                                          "stimulus_id": f"{condition}_{trial_id:03d}",
                                          "visual_measurement_anchor": True,
                                          "response_windows_s": cfg.get("visual_measurement", {}).get(
                                              "windows_s", {})}))
                t += face_s + rng.uniform(iti_lo, iti_hi)
            events.append(Event(t, TriggerCode.EMOTION_RATING, "EMOTION_RATING", block_id=block_id,
                                meta={"condition": condition, "scales": ["valence", "arousal"]}))
            t += rating_s + float(cfg.get("inter_block_s", 2.0))
        events.append(Event(t + float(cfg.get("tail_s", 5.0)), TriggerCode.EMOTION_END, "EMOTION_END"))
        return self._sorted(events)
