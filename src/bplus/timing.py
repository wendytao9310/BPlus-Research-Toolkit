"""触发时序策略：脉宽、最小间隔、量化误差（ENGINEERING 级，非国际标准）。

对应 MASTER COMMAND §57-59 与本次冻结的 sync.yaml。
规则的核心逻辑必须显式编码，避免"照抄一个数字"式的工程错误。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class PulsePolicy:
    width_ms: float
    min_gap_ms: float
    latching: str = "unknown"          # unknown | yes | no
    fnirs_sampling_interval_ms: float = 75.0

    @classmethod
    def from_config(cls, sync_cfg: dict) -> "PulsePolicy":
        pulse = sync_cfg.get("pulse", {})
        fnirs = sync_cfg.get("fnirs", {})
        return cls(
            width_ms=float(pulse.get("width_ms", 100)),
            min_gap_ms=float(pulse.get("min_gap_ms", 500)),
            latching=str(fnirs.get("latching", "unknown")),
            fnirs_sampling_interval_ms=float(fnirs.get("sampling_interval_ms", 75)),
        )

    def capture_rule(self) -> str:
        if self.latching == "yes":
            return (f"latching=yes: 脉宽 {self.width_ms:.0f} ms 足够（边沿锁存），"
                    f"可选降到 {self.width_ms:.0f} ms 以下")
        if self.latching == "no":
            return (f"latching=no: 脉宽必须 > 采样周期 {self.fnirs_sampling_interval_ms:.0f} ms，"
                    f"当前 {self.width_ms:.0f} ms 安全")
        return (f"latching=unknown: 采用保守值 {self.width_ms:.0f} ms "
                f"(> 采样周期 {self.fnirs_sampling_interval_ms:.0f} ms)")

    def problems(self) -> list[str]:
        """返回工程上不成立的配置（空列表 = 通过）。"""
        out: list[str] = []
        if self.latching in ("no", "unknown") and self.width_ms <= self.fnirs_sampling_interval_ms:
            out.append(
                f"脉宽 {self.width_ms:.0f} ms <= fNIRS 采样周期 {self.fnirs_sampling_interval_ms:.0f} ms，"
                "在不锁定/未确认锁存的设备上会漏抓触发"
            )
        if self.width_ms <= 0:
            out.append("脉宽必须为正")
        return out

    def max_event_quantisation_ms(self) -> float:
        """fNIRS 事件时间戳的最坏量化误差（一个采样周期）。"""
        return self.fnirs_sampling_interval_ms


def check_event_spacing(onsets_ms: Sequence[float], policy: PulsePolicy) -> list[str]:
    """检查事件间隔是否与脉宽冲突（脉冲重叠 = 两个事件在硬件上分不开）。"""
    issues: list[str] = []
    ordered = sorted(onsets_ms)
    for a, b in zip(ordered, ordered[1:]):
        gap = b - a
        if gap < policy.width_ms:
            issues.append(f"事件间隔 {gap:.0f} ms < 脉宽 {policy.width_ms:.0f} ms（脉冲会重叠/合并）")
        elif gap < policy.min_gap_ms:
            issues.append(f"事件间隔 {gap:.0f} ms 小于项目约定的最小间隔 {policy.min_gap_ms:.0f} ms")
    return issues


def check_events(events: Iterable, policy: PulsePolicy) -> list[str]:
    """对某范式的全部事件做一次间隔体检（events 需有 .onset，单位秒）。"""
    onsets_ms = [float(e.onset) * 1000.0 for e in events]
    return check_event_spacing(onsets_ms, policy)
