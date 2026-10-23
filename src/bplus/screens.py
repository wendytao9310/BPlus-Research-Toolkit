"""范式 -> 可呈现的"试次表"（trial table）：把纯时间轴变成有内容、可按键、可评分的试次。

这是事件流（`paradigms/`）与真实呈现（PsychoPy）之间的桥梁：
  * 事件流回答"什么时候发什么触发码"；
  * 试次表回答"屏幕上显示什么、被试该按什么、反应窗口多长"。
无显示器即可单元测试。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import config as cfg_mod
from .paradigms import REGISTRY
from .triggers import TriggerCode

FIXATION = "+"


@dataclass
class Trial:
    index: int
    onset_s: float
    code: int
    kind: str                      # fixation | text | image | rating | tone
    block_id: int | None = None
    condition: str = ""
    text: str = FIXATION
    image: str | None = None
    tone_hz: float | None = None
    tone_ms: float | None = None
    duration_s: float = 1.0
    is_target: bool | None = None
    expected_key: str | None = None
    response_window_s: tuple[float, float] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def _gap(events, i: int, fallback: float) -> float:
    if i + 1 < len(events):
        return max(0.05, events[i + 1].onset - events[i].onset)
    return fallback


def _nback_trials(cfg: dict, events) -> list[Trial]:
    trials, tidy = [], 0
    stim = float(cfg.get("stimulus_s", 0.5))
    isi = float(cfg.get("isi_s", 1.5))
    for i, ev in enumerate(events):
        if ev.code in (TriggerCode.NBACK_0BACK, TriggerCode.NBACK_2BACK):
            tidy += 1
            level = int(ev.meta.get("level", 0))
            practice = bool(ev.meta.get("practice", False))
            prefix = "Practice block" if practice else "Main block"
            if level == 0:
                target_digit = ev.meta.get("target_digit")
                text = (f"{prefix} | 0-back\n\nTarget digit for this block: {target_digit}\n\n"
                        f"Press Enter when you see {target_digit}\nDo not press for any other digit")
            else:
                text = (f"{prefix} | 2-back\n\n"
                        "Press Enter when the current digit matches the digit two trials earlier\n"
                        "Do not press when it does not match")
            trials.append(Trial(
                index=tidy, onset_s=ev.onset, code=int(ev.code), kind="instruction",
                block_id=ev.block_id, condition=f"{level}-back-cue", text=text,
                duration_s=float(ev.meta.get("duration_s", cfg.get("cue_s", 3.0))),
                meta=dict(ev.meta),
            ))
            continue
        if ev.code not in (TriggerCode.NBACK_TARGET, TriggerCode.NBACK_NONTARGET):
            continue
        tidy += 1
        is_target = bool(ev.meta.get("is_target"))
        trials.append(Trial(
            index=tidy, onset_s=ev.onset, code=int(ev.code), kind="text",
            block_id=ev.block_id, condition=f"{ev.meta.get('level')}-back",
            text=str(ev.meta.get("digit", "?")), duration_s=stim,
            is_target=is_target, expected_key=cfg.get("match_key", "return") if is_target else None,
            response_window_s=(0.0, stim + isi),
            meta={"level": ev.meta.get("level"), "practice": ev.meta.get("practice", False),
                  "target_digit": ev.meta.get("target_digit"),
                  "fixation_after_s": max(0.0, isi)},
        ))
    return trials


def _mmn_trials(cfg: dict, events) -> list[Trial]:
    tone_ms = float(cfg.get("tone_ms", 100))
    tones = {int(TriggerCode.MMN_STANDARD): float(cfg.get("standard_hz", 1000)),
             int(TriggerCode.MMN_DEVIANT): float(cfg.get("deviant_hz", 2000))}
    trials, tidy = [], 0
    for i, ev in enumerate(events):
        if ev.code not in (TriggerCode.MMN_STANDARD, TriggerCode.MMN_DEVIANT):
            continue
        tidy += 1
        trials.append(Trial(
            index=tidy, onset_s=ev.onset, code=int(ev.code), kind="tone",
            block_id=ev.block_id, condition="deviant" if ev.code is TriggerCode.MMN_DEVIANT else "standard",
            text=FIXATION, tone_hz=tones[int(ev.code)], tone_ms=tone_ms,
            duration_s=_gap(events, i, float(cfg.get("soa_ms", 1000)) / 1000.0),
            is_target=None, expected_key=None, response_window_s=None,
            meta={"soa_s": float(cfg.get("soa_ms", 1000)) / 1000.0, "passive": True},
        ))
    return trials


def _vft_trials(cfg: dict, events) -> list[Trial]:
    trials = []
    syllables = {i + 1: p.get("text", "") for i, p in enumerate(cfg.get("prompts", []))}
    for ev in events:
        if ev.code is TriggerCode.VFT_REST:
            trials.append(Trial(index=len(trials) + 1, onset_s=ev.onset, code=int(ev.code), kind="text",
                                text="Baseline phase\n\nCount continuously and steadily from 1.\nKeep your body still and avoid unnecessary movement.",
                                duration_s=float(ev.meta.get("duration_s", 30)),
                                condition=ev.meta.get("kind", "rest"), meta=dict(ev.meta)))
        elif ev.code is TriggerCode.VFT_BLOCK:
            sub = int(ev.meta.get("sub_block", 1))
            trials.append(Trial(index=len(trials) + 1, onset_s=ev.onset, code=int(ev.code), kind="text",
                                block_id=ev.block_id, condition="task",
                                text=(f"Verbal Fluency Task\n\nTarget syllable: {syllables.get(sub, '')}\n\n"
                                      "Say as many words as possible beginning with this syllable.\n"
                                      "Do not repeat words or use personal or place names."),
                                duration_s=float(ev.meta.get("sub_block_s", 15)),
                                meta=dict(ev.meta)))
    return trials


def _emotion_trials(cfg: dict, events) -> list[Trial]:
    # Resolve real files from the reviewed manifest. The event stream carries
    # logical trial ids, which are not filenames.
    from .stimuli import DEFAULT_ROOT, load_manifest
    available: dict[str, list[str]] = {"neutral": [], "positive": [], "negative": []}
    for record in load_manifest(DEFAULT_ROOT):
        path = DEFAULT_ROOT / record.file
        if record.condition in available and path.exists():
            available[record.condition].append(str(path))
    used = {condition: 0 for condition in available}
    trials, tidy = [], 0
    face_s = float(cfg.get("face_s", 3.0))
    for i, ev in enumerate(events):
        if ev.code in (TriggerCode.EMOTION_NEUTRAL, TriggerCode.EMOTION_POSITIVE, TriggerCode.EMOTION_NEGATIVE):
            tidy += 1
            condition = str(ev.meta.get("condition", ""))
            choices = available.get(condition, [])
            image = choices[used[condition] % len(choices)] if choices else None
            used[condition] += 1
            trials.append(Trial(index=tidy, onset_s=ev.onset, code=int(ev.code),
                                kind="image" if image else "text",
                                block_id=ev.block_id, condition=condition,
                                image=image, text=f"[{condition} stimulus unavailable]",
                                duration_s=face_s, meta=dict(ev.meta)))
        elif ev.code is TriggerCode.EMOTION_RATING:
            trials.append(Trial(index=len(trials) + 1, onset_s=ev.onset, code=int(ev.code), kind="rating",
                                block_id=ev.block_id, condition=str(ev.meta.get("condition", "")),
                                text="Please rate the image block you just viewed:\nPleasantness (1-5)    Arousal (1-5)",
                                duration_s=float(cfg.get("block_rating_s", 6.0)), meta=dict(ev.meta)))
    return trials


def _fixation_trials(events, cfg: dict, code: int, label: str) -> list[Trial]:
    for ev in events:
        if ev.code is code:
            instruction = ("Resting-state baseline\n\nRelax, keep your eyes open, and fixate on the central cross.\n"
                           "Remain quiet and keep your body still.\n\n+") if label == "rest" else (
                           "Post-task recovery\n\nRelax, keep your eyes open, and fixate on the central cross.\n"
                           "Remain quiet and keep your body still.\n\n+")
            return [Trial(index=1, onset_s=ev.onset, code=int(code), kind="fixation", text=instruction,
                          duration_s=float(cfg.get("duration_s", 180)), condition=label, meta=dict(ev.meta))]
    return []


def build_trials(paradigm: str, cfg: dict | None = None, events=None) -> list[Trial]:
    cfg = cfg if cfg is not None else cfg_mod.paradigm_config(paradigm)
    events = events if events is not None else REGISTRY[paradigm](cfg).events()
    if paradigm == "nback":
        return _nback_trials(cfg, events)
    if paradigm == "mmn":
        return _mmn_trials(cfg, events)
    if paradigm == "vft":
        return _vft_trials(cfg, events)
    if paradigm == "emotion":
        return _emotion_trials(cfg, events)
    if paradigm == "rest":
        return _fixation_trials(events, cfg, TriggerCode.REST_START, "rest")
    if paradigm == "recovery":
        return _fixation_trials(events, cfg, TriggerCode.RECOVERY_START, "recovery")
    raise ValueError(f"unknown paradigm {paradigm!r}")
