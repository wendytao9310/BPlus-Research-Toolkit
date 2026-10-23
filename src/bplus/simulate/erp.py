"""在合成 EEG 上叠加已知的 MMN 事件相关电位（让特征提取也能被验证）。

依据（见 configs/paradigms/mmn.yaml）：
  * 锚论文 P001：MMN 分析窗 100–250 ms；抑郁组 Fz 波幅 2.42±2.18 μV vs 对照 5.65±5.59 μV，
    潜伏期 227.88±31.08 ms vs 208.70±25.35 ms；
  * Murphy 2022 / Fitzgerald 2020：偏差刺激诱发负向偏转。
"""
from __future__ import annotations

import numpy as np


def add_mmn_erp(eeg: np.ndarray, fs: float, *, deviant_onsets_s, standard_onsets_s=(),
                deviant_amplitude_uv: float = -3.5, deviant_latency_ms: float = 200.0,
                width_ms: float = 60.0, standard_amplitude_uv: float = -0.6,
                standard_latency_ms: float = 120.0, noise_uv: float = 0.0,
                seed: int = 0) -> np.ndarray:
    """在每个偏差/标准刺激起点后叠加一个高斯偏转（负向 = MMN 方向）。

    返回新的 EEG（单位 μV）。差异波峰值 ≈ |deviant_amplitude − standard_amplitude|，
    峰值时间 ≈ deviant_latency_ms。
    """
    rng = np.random.default_rng(seed)
    out = np.asarray(eeg, dtype=float).copy()
    n = len(out)
    sigma_ms = max(1.0, width_ms) / 2.355                  # FWHM → sigma

    def _stamp(onset_s: float, amp: float, latency_ms: float) -> None:
        start = int(float(onset_s) * fs)
        lo = max(0, start - int(0.05 * fs))
        hi = min(n, start + int(0.6 * fs))
        if hi <= lo:
            return
        t_ms = (np.arange(lo, hi) - start) / fs * 1000.0 - latency_ms
        out[lo:hi] += amp * np.exp(-0.5 * (t_ms / sigma_ms) ** 2)

    for onset in deviant_onsets_s:
        _stamp(onset, deviant_amplitude_uv, deviant_latency_ms)
    for onset in standard_onsets_s:
        _stamp(onset, standard_amplitude_uv, standard_latency_ms)
    if noise_uv:
        out += noise_uv * rng.standard_normal(n)
    return out
