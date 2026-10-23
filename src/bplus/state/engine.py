"""状态引擎（MASTER COMMAND §33-38、§52-56）。

三层状态 + 综合画像，全部 config 驱动、逐项可追溯：
  * Task State        —— 认知负荷 / 注意 / 情绪唤醒 / 任务适应 / 恢复
  * Brain State       —— PFC 活动 / 执行控制 / 感觉加工 / 情绪加工 / EEG-fNIRS 协调 / 恢复
  * Clinical State    —— 抑郁 / 焦虑 / 睡眠 / 社会功能（**只能**来自问卷与访谈）
  * Integrated Profile—— 三层加权组合 + 数据质量 + 置信度

关键纪律：
  * 每个分数都带 `inputs`（用了哪些指标、原值、归一化值、参考区间、权重、证据等级）→ §53 可追溯；
  * confidence 由 数据质量 / 指标覆盖率 / 显著性 三者加权，且**明确不等于诊断概率**（§39）；
  * 支持个体基线（§55）与会话间纵向比较（§56）；
  * 临床阈值必须由医院确认（CLINICAL_PENDING_HOSPITAL_CONFIRMATION）。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

from .. import config as cfg_mod


@dataclass
class StateScore:
    key: str
    zh: str
    level: str
    level_zh: str
    score: float
    confidence: str
    confidence_score: float
    inputs: list = field(default_factory=list)
    evidence_status: str = "PROJECT_DESIGN"
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class StateProfile:
    participant_id: str
    session_id: str
    task_state: dict = field(default_factory=dict)
    brain_state: dict = field(default_factory=dict)
    clinical_state: dict = field(default_factory=dict)
    integrated: dict = field(default_factory=dict)
    data_quality: dict = field(default_factory=dict)
    confidence_overall: dict = field(default_factory=dict)
    baseline_used: bool = False
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def flat_levels(self) -> dict:
        out = {}
        for group in ("task_state", "brain_state", "clinical_state"):
            for k, v in getattr(self, group).items():
                out[f"{group}.{k}"] = v["level"]
        return out


def _get(features: dict, key: str):
    """按 'a.b' 取值；缺失返回 None（而不是 0，避免把缺失当低值）。"""
    cur: Any = features
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    if isinstance(cur, dict):
        return cur.get("value")
    return cur


def _normalise(value: float, ref: list[float], direction: str) -> float:
    lo, hi = float(ref[0]), float(ref[1])
    if hi == lo:
        return 0.5
    x = float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))
    return 1.0 - x if direction == "negative" else x


def _band(score: float, bands: list[dict]) -> dict:
    for b in bands:
        if score < b["max"]:
            return b
    return bands[-1]


class StateEngine:
    def __init__(self, config: dict | None = None) -> None:
        self.cfg = config or cfg_mod.load_yaml("scoring.yaml")

    # ------------------------------------------------------------------ helpers
    def _eval_group(self, group_cfg: dict, features: dict, dq_norm: float,
                    baseline: dict | None, significance: float = 1.0) -> dict:
        out = {}
        for key, spec in group_cfg.items():
            metrics, used, missing = [], [], []
            weighted_sum, weight_total = 0.0, 0.0
            for m in spec["metrics"]:
                raw = _get(features, m["key"])
                if raw is None or (isinstance(raw, float) and not np.isfinite(raw)):
                    missing.append(m["key"])
                    continue
                norm = _normalise(float(raw), m["ref"], m["direction"])
                entry = {"metric": m["key"], "value": float(raw), "normalised": round(norm, 4),
                         "ref": m["ref"], "direction": m["direction"], "weight": m["weight"],
                         "evidence": m.get("evidence", self.cfg["evidence_status_default"])}
                if baseline and m["key"] in baseline:
                    b = float(baseline[m["key"]])
                    delta = float(raw) - b
                    span = float(m["ref"][1]) - float(m["ref"][0]) or 1.0
                    delta_norm = float(np.clip(abs(delta) / (0.5 * span), 0.0, 1.0))
                    w = self.cfg["baseline"]["weight"]
                    entry["baseline_value"] = b
                    entry["baseline_delta"] = delta
                    norm = (1 - w) * norm + w * delta_norm
                    entry["normalised_with_baseline"] = round(norm, 4)
                metrics.append(entry)
                weighted_sum += norm * m["weight"]
                weight_total += m["weight"]
                used.append(m["key"])
            score = (weighted_sum / weight_total) if weight_total else float("nan")
            coverage = weight_total / sum(m["weight"] for m in spec["metrics"])
            conf = (self.cfg["confidence"]["weights"]["data_quality"] * dq_norm
                    + self.cfg["confidence"]["weights"]["coverage"] * coverage
                    + self.cfg["confidence"]["weights"]["significance"] * significance) if weight_total else 0.0
            conf_band = _band(conf, self.cfg["confidence"]["bands"])
            band = (_band(score, self.cfg["bands"][spec.get("bands", "severity")])
                    if weight_total else {"label": "Insufficient", "zh": "数据不足"})
            notes = []
            if missing:
                notes.append(f"缺失指标：{', '.join(missing)}（已按可用指标归一化权重）")
            if spec.get("evidence_status"):
                notes.append(f"证据状态：{spec['evidence_status']}")
            if spec.get("evidence_status", "").startswith("CLINICAL_PENDING"):
                notes.append("临床分级阈值尚未由医院确认，报告必须标注")
            out[key] = StateScore(
                key=key, zh=spec.get("zh", key), level=band["label"], level_zh=band.get("zh", band["label"]),
                score=round(float(score), 4) if np.isfinite(score) else float("nan"),
                confidence=conf_band["label"], confidence_score=round(float(conf), 4),
                inputs=metrics, evidence_status=spec.get("evidence_status", self.cfg["evidence_status_default"]),
                notes=notes).as_dict()
        return out

    # ------------------------------------------------------------------ main
    def evaluate(self, features: dict, *, participant_id: str = "unknown", session_id: str = "1",
                 dq: dict | None = None, baseline: dict | None = None,
                 significance: float = 1.0) -> StateProfile:
        dq = dq or {}
        dq_norm = float(dq.get("score", 70.0)) / 100.0
        profile = StateProfile(participant_id=participant_id, session_id=session_id,
                               data_quality=dq, baseline_used=bool(baseline))
        profile.task_state = self._eval_group(self.cfg["task_state"], features, dq_norm, baseline, significance=1.0)
        profile.brain_state = self._eval_group(self.cfg["brain_state"], features, dq_norm, baseline, significance=significance)
        profile.clinical_state = self._eval_group(self.cfg["clinical_state"], features, dq_norm, baseline, significance=1.0)

        w = self.cfg["integrated"]["weights"]
        integrated = {}
        for layer, wkey in (("task_state", "task"), ("brain_state", "brain"), ("clinical_state", "clinical")):
            scores = [v["score"] for v in getattr(profile, layer).values() if np.isfinite(v["score"])]
            integrated[layer] = float(np.mean(scores)) if scores else float("nan")
        available = {k: v for k, v in integrated.items() if np.isfinite(v)}
        total_w = sum(w[k.replace("_state", "")] for k in available)
        integ_score = (sum(v * w[k.replace("_state", "")] for k, v in available.items()) / total_w
                       if total_w else float("nan"))
        band = (_band(integ_score, self.cfg["bands"]["severity"])
                if np.isfinite(integ_score) else {"label": "Insufficient", "zh": "数据不足"})
        conf_scores = [v["confidence_score"] for layer in ("task_state", "brain_state", "clinical_state")
                       for v in getattr(profile, layer).values() if v["inputs"]]
        conf = float(np.mean(conf_scores)) if conf_scores else 0.0
        conf_band = _band(conf, self.cfg["confidence"]["bands"])
        profile.integrated = {
            "score": round(float(integ_score), 4) if np.isfinite(integ_score) else None,
            "level": band["label"], "level_zh": band.get("zh", band["label"]),
            "layer_scores": {k: (round(v, 4) if np.isfinite(v) else None) for k, v in integrated.items()},
            "weights": w, "weights_effective": {
                k.replace("_state", ""): round(w[k.replace("_state", "")] / total_w, 4)
                for k in available} if total_w else {},
            "data_quality": {"score": dq.get("score"), "band": dq.get("band")},
            "note": self.cfg["integrated"]["note"],
        }
        profile.confidence_overall = {"score": round(conf, 4), "label": conf_band["label"],
                                      "label_zh": conf_band.get("zh", conf_band["label"]),
                                      "note": self.cfg["confidence"]["note"]}
        if dq.get("notes"):
            profile.notes.extend(dq["notes"])
        return profile


def compare_sessions(prev: dict, cur: dict) -> dict:
    """纵向比较（§56）：给出每个状态层级的迁移方向。"""
    out = {}
    for group in ("task_state", "brain_state", "clinical_state"):
        for key, cur_v in (cur.get(group) or {}).items():
            prev_v = (prev.get(group) or {}).get(key)
            if not prev_v:
                continue
            d = float(cur_v["score"]) - float(prev_v["score"])
            out[f"{group}.{key}"] = {"previous": prev_v["level"], "current": cur_v["level"],
                                     "score_delta": round(d, 4),
                                     "direction": "worse" if d > 0.05 else "better" if d < -0.05 else "stable"}
    return out
