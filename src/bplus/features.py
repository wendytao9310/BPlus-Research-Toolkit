"""特征提取（§41-43、§71）：从一次（合成或真实）会话里抽出可追溯的指标。

每个特征都是 `Feature(value, unit, source, evidence, window, notes)`，
后续状态引擎只消费这些带出处的特征，保证 §53 的"可追溯"要求。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
from scipy.ndimage import uniform_filter1d

from .nvc import (NVCSettings, analyze_nvc, bandpass, theta_envelope)  # noqa: F401


@dataclass
class Feature:
    value: float | None
    unit: str = ""
    source: str = ""
    evidence: str = "PROJECT_DESIGN"
    window: str = ""
    notes: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _mad(x: np.ndarray) -> float:
    med = np.median(x)
    return float(np.median(np.abs(x - med))) + 1e-12


# --------------------------------------------------------------------------- EEG/ERP
def extract_mmn(eeg: np.ndarray, fs: float, *, deviant_onsets_s, standard_onsets_s,
                window_ms=(100.0, 250.0), baseline_ms=(-100.0, 0.0),
                epoch_ms=(-100.0, 500.0), lp_hz: float = 20.0,
                score_lp_hz: float = 8.0, reject_uv: float = 150.0) -> dict:
    """MMN = 偏差 − 标准 差异波在 100–250 ms 内的负峰（锚论文 P001 的口径）。

    `score_lp_hz`：在差异波上再低通（默认 8 Hz）再取峰——这是 MMN 幅度/潜伏期测量的常规做法，
    可显著降低"取最小值"带来的噪声偏置（随机噪声的极值会被误当成 MMN）。
    """
    sig = bandpass(np.asarray(eeg, float), fs, 0.1, min(lp_hz, fs / 2 * 0.95))
    i0, i1 = int(epoch_ms[0] / 1000 * fs), int(epoch_ms[1] / 1000 * fs)
    t_ms = np.arange(i0, i1) / fs * 1000.0
    base = (t_ms >= baseline_ms[0]) & (t_ms <= baseline_ms[1])
    win = (t_ms >= window_ms[0]) & (t_ms <= window_ms[1])

    def _average(onsets):
        epochs, rejected = [], 0
        for onset in onsets:
            s = int(float(onset) * fs) + i0
            if s < 0 or s + (i1 - i0) > len(sig):
                continue
            ep = sig[s:s + (i1 - i0)].copy()
            if np.max(np.abs(ep)) > reject_uv:
                rejected += 1
                continue
            epochs.append(ep - ep[base].mean())
        if not epochs:
            return None, 0, rejected
        return np.mean(np.vstack(epochs), axis=0), len(epochs), rejected

    dev, n_dev, rej_dev = _average(deviant_onsets_s)
    std, n_std, rej_std = _average(standard_onsets_s)
    if dev is None or std is None:
        return {"mmn_amplitude_uv": None, "mmn_latency_ms": None, "n_deviants": n_dev,
                "n_standards": n_std, "rejected": rej_dev + rej_std, "difference_wave_uv": [],
                "difference_wave_ms": []}
    diff = dev - std
    if score_lp_hz:
        diff = bandpass(diff, fs, 0.3, min(score_lp_hz, fs / 2 * 0.95))
    seg, seg_t = diff[win], t_ms[win]
    i_peak = int(np.argmin(seg))
    return {
        "mmn_amplitude_uv": float(seg[i_peak]),
        "mmn_latency_ms": float(seg_t[i_peak]),
        "n_deviants": n_dev,
        "n_standards": n_std,
        "rejected": rej_dev + rej_std,
        "difference_wave_uv": [float(x) for x in diff],
        "difference_wave_ms": [float(x) for x in t_ms],
    }


def line_noise_ratio(eeg: np.ndarray, fs: float, *, line_hz: float = 50.0, bw_hz: float = 2.0) -> float:
    """50 Hz 工频能量占 1–100 Hz 总能量的比例（用于 QC）。"""
    x = np.asarray(eeg, float)
    f = np.fft.rfftfreq(len(x), 1 / fs)
    p = np.abs(np.fft.rfft(x - x.mean())) ** 2
    band = (f >= 1) & (f <= min(100, fs / 2 * 0.95))
    line = (f >= line_hz - bw_hz) & (f <= line_hz + bw_hz)
    return float(p[line].sum() / (p[band].sum() + 1e-12))


def band_power(x: np.ndarray, fs: float, lo: float, hi: float) -> float:
    f = np.fft.rfftfreq(len(x), 1 / fs)
    p = np.abs(np.fft.rfft(np.asarray(x, float) - np.mean(x))) ** 2
    sel = (f >= lo) & (f <= hi)
    return float(p[sel].sum())


# --------------------------------------------------------------------------- fNIRS
def scalp_coupling_index(raw_a: np.ndarray, raw_b: np.ndarray, fs: float,
                         band=(0.7, 1.5)) -> float:
    """SCI = 同一通道两个波长在 0.7–1.5 Hz 的相关系数（MNE-NIRS 口径）。

    注意：真实 SCI 需要**原始光强**（两个波长）；这里用合成 raw_760/raw_850 演示该实现，
    并标注 evidence=SIMULATED。
    """
    a = bandpass(np.asarray(raw_a, float), fs, band[0], min(band[1], fs / 2 * 0.95))
    b = bandpass(np.asarray(raw_b, float), fs, band[0], min(band[1], fs / 2 * 0.95))
    if np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def motion_artifact_ratio(hbo: np.ndarray, *, thresh_um: float = 0.5) -> float:
    """运动伪迹占比：用**幅度变化阈值**（Homer 风格），而不是 MAD 相对阈值。

    ⚠️ 用 k×MAD 的相对阈值会把生理性慢波也标成伪迹（本项目实测把 5 个真伪迹数成 15% 的样本）。
    fNIRS 的惯例是按"单次采样内的幅度跳变"判断（Homer 的 hmrMotionArtifact 即用幅度阈值，
    默认 0.5 μM 量级）。阈值必须在 PILOT 上按设备与采样率标定。
    """
    d = np.abs(np.diff(np.asarray(hbo, float)))
    return float(np.mean(d > thresh_um))


def baseline_drift(hbo: np.ndarray) -> float:
    x = np.asarray(hbo, float)
    half = len(x) // 2
    return float(abs(x[half:].mean() - x[:half].mean()) / (x.std() + 1e-12))


def task_response(hbo: np.ndarray, fnirs_fs: float, *, task_windows, rest_windows) -> dict:
    """任务块相对静息块的 ΔHbO（均值对比）。

    ⚠️ 对**单周期**设计（如锚论文的 VFT：30 s 静息 + 60 s 任务 + 60 s 静息），
    这是比 GLM 更稳健的主指标：本项目实测在 70 min 记录上用线性漂移回归时，
    任务回归量与漂移项高度共线，β 甚至翻成负号（VFT β=−0.41，N-back β=−0.33，真值均为正）。
    因此：**单周期 VFT 用均值对比，多块设计（N-back）才用 GLM**（见 D-021）。
    """
    x = np.asarray(hbo, float)

    def _mean(windows):
        vals = []
        for onset, dur in windows or ():
            i0, i1 = int(onset * fnirs_fs), min(len(x), int((onset + dur) * fnirs_fs))
            if i1 > i0:
                vals.append(float(x[i0:i1].mean()))
        return float(np.mean(vals)) if vals else float("nan")

    task, rest = _mean(task_windows), _mean(rest_windows)
    return {"task_mean": task, "rest_mean": rest,
            "delta": (task - rest) if not (np.isnan(task) or np.isnan(rest)) else float("nan")}


# --------------------------------------------------------------------------- 生理
def hrv_sdnn(beats_s: np.ndarray) -> float:
    rr = np.diff(np.asarray(beats_s, float)) * 1000.0
    return float(np.std(rr)) if len(rr) > 1 else float("nan")


def count_scr(eda: np.ndarray, fs: float, *, min_amplitude: float = 0.05,
              min_distance_s: float = 3.0, baseline_s: float = 60.0, smooth_s: float = 1.0) -> int:
    """数 SCR（皮电反应）事件：去基线漂移 → 平滑 → 局部极大 → 幅度过滤 → 最小间隔。

    ⚠️ 基线必须用 `uniform_filter1d(mode="nearest")`：`np.convolve(mode="same")`
    在信号两端会因补零产生巨大伪影，导致边缘冒出几十个假 SCR（本项目实测 8 个真事件被数成 75 个）。

    阈值是 ENGINEERING 初值，须在 PILOT 上用真实 EDA 标定（生产环境应改用 NeuroKit2 的 EDA 分解）。
    """
    x = np.asarray(eda, float)
    base_win = max(3, int(baseline_s * fs))
    x = x - uniform_filter1d(x, size=base_win, mode="nearest")
    win = max(1, int(smooth_s * fs))
    x = uniform_filter1d(x, size=win, mode="nearest")
    min_dist = max(1, int(min_distance_s * fs))
    peaks, last = 0, -10 ** 9
    decay_s = 6.0
    for i in range(1, len(x) - 1):
        if x[i] > x[i - 1] and x[i] >= x[i + 1] and x[i] > min_amplitude and (i - last) > min_dist:
            j = min(len(x) - 1, i + int(decay_s * fs))
            if x[i] - x[j] > 0.3 * x[i]:        # 必须回落（SCR 的相位形态）
                peaks += 1
                last = i
    return peaks


def glm_task_beta(hbo: np.ndarray, fnirs_fs: float, *, task_blocks, duration_s: float | None = None,
                  drift_order: int = 2) -> dict:
    """简化 GLM：HbO ~ β·(任务方波 ⊛ HRF) + 截距 + 多项式漂移。

    返回 β（单位 μM）——MNE-NIRS 一阶 GLM 的最小可用版本。

    注意：必须保留 2 阶漂移项；块数太少（例如单周期 VFT）时该回归量会与漂移项共线，
    β 不可靠 → 此时请改用 `task_response()` 的均值对比。
    """
    x = np.asarray(hbo, float)
    n = len(x)
    t = np.arange(n) / fnirs_fs
    reg = _task_regressor(fnirs_fs, n, task_blocks)
    cols = [reg, np.ones(n)]
    for order in range(1, drift_order + 1):
        cols.append((t - t.mean()) ** order / (max(1.0, t.max()) ** order))
    X = np.column_stack(cols)
    try:
        beta, *_ = np.linalg.lstsq(X, x, rcond=None)
    except np.linalg.LinAlgError:
        return {"beta_um": float("nan"), "n_regressors": X.shape[1]}
    resid = x - X @ beta
    return {"beta_um": float(beta[0]), "intercept": float(beta[1]), "resid_sd": float(np.std(resid)),
            "n_regressors": X.shape[1], "window": f"{len(task_blocks or [])} task blocks"}


def _task_regressor(fs: float, n: int, task_blocks) -> np.ndarray:
    """任务方波 ⊛ HRF，并归一化到稳态平台 = 1（与 simulate 中的实现保持一致）。"""
    from .simulate.synthetic import hrf

    reg = np.zeros(n)
    for onset, dur, *_ in task_blocks or ():
        i0, i1 = int(onset * fs), min(n, int((onset + dur) * fs))
        if i1 > i0:
            reg[i0:i1] = 1.0
    kernel = hrf(peak_s=5.0, fs=fs)
    return np.convolve(reg, kernel)[:n] / (np.sum(kernel) + 1e-12)
