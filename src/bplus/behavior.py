"""行为指标：命中/漏报/虚报、d'、反应时与 RT-CV（MASTER COMMAND §23-25）。"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field


@dataclass
class TrialResponse:
    trial_id: int
    block_id: int | None = None
    condition: str = ""
    is_target: bool | None = None
    responded: bool = False
    key: str | None = None
    rt_ms: float | None = None
    correct: bool | None = None
    pressed_target_key: bool | None = None   # 是否按下了"目标键"（信号检测的核心变量）
    valence: int | None = None
    arousal: int | None = None
    meta: dict = field(default_factory=dict)


def evaluate_nback(responses: list[TrialResponse], *, target_key: str = "return") -> list[TrialResponse]:
    """按信号检测口径判定：核心变量是"是否按下目标键"。

    双键 N-back（匹配键 + 非匹配键）下：
      * 目标试次按"匹配键" = 命中；不按 = 漏报；
      * 非目标试次按"匹配键" = 虚报（false alarm）；按"非匹配键"或什么都不按 = 正确拒绝。
    这样 §25 要求的 hit / false alarm / omission / commission 都能算出来。
    """
    for r in responses:
        if r.is_target is None:
            continue
        pressed_target = bool(r.responded and r.key == target_key)
        r.pressed_target_key = pressed_target
        r.correct = (pressed_target == bool(r.is_target))
    return responses


def d_prime(hits: int, n_targets: int, false_alarms: int, n_nontargets: int) -> float:
    """带 log-linear 校正的 d'（避免 hit/FA = 0 或 1 时数值爆炸）。"""
    if n_targets <= 0 or n_nontargets <= 0:
        return float("nan")
    hr = (hits + 0.5) / (n_targets + 1.0)
    far = (false_alarms + 0.5) / (n_nontargets + 1.0)
    z = lambda p: math.sqrt(2.0) * _erfinv(2.0 * p - 1.0)
    return z(hr) - z(far)


def _erfinv(x: float) -> float:
    """Winitzki 近似的 erfinv（足够 d' 使用，避免引入 scipy 依赖）。"""
    x = max(min(x, 0.999999), -0.999999)
    a = 0.147
    ln = math.log(1 - x * x)
    t = 2.0 / (math.pi * a) + ln / 2.0
    return math.copysign(math.sqrt(math.sqrt(t * t - ln / a) - t), x)


def rt_variability(rts: list[float]) -> float:
    """RT-CV = SD(RT) / mean(RT)（§25 明确要求）。"""
    vals = [r for r in rts if r is not None and r > 0]
    if len(vals) < 2:
        return float("nan")
    mean = statistics.fmean(vals)
    return statistics.stdev(vals) / mean if mean else float("nan")


def summarize(responses: list[TrialResponse], *, target_key: str = "return") -> dict:
    for r in responses:
        if r.pressed_target_key is None:
            r.pressed_target_key = bool(r.responded and r.key == target_key)
    targets = [r for r in responses if r.is_target]
    nontargets = [r for r in responses if r.is_target is False]
    hits = sum(1 for r in targets if r.pressed_target_key)
    omissions = sum(1 for r in targets if not r.pressed_target_key)
    false_alarms = sum(1 for r in nontargets if r.pressed_target_key)
    commissions = false_alarms
    correct_rejections = len(nontargets) - false_alarms
    correct = [r for r in responses if r.correct]
    rts = [r.rt_ms for r in correct if r.rt_ms is not None]
    return {
        "n_trials": len(responses),
        "n_targets": len(targets),
        "n_nontargets": len(nontargets),
        "hits": hits,
        "omissions": omissions,
        "false_alarms": false_alarms,
        "commissions": commissions,
        "correct_rejections": correct_rejections,
        "accuracy": (sum(1 for r in responses if r.correct) / len(responses)) if responses else float("nan"),
        "hit_rate": (hits / len(targets)) if targets else float("nan"),
        "false_alarm_rate": (false_alarms / len(nontargets)) if nontargets else float("nan"),
        "d_prime": d_prime(hits, len(targets), false_alarms, len(nontargets)),
        "median_rt_ms": statistics.median(rts) if rts else float("nan"),
        "mean_rt_ms": statistics.fmean(rts) if rts else float("nan"),
        "rt_cv": rt_variability(rts),
        "n_rt": len(rts),
    }
