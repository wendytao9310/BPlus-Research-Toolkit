"""合成数据生成器（MASTER COMMAND §73-74）。

要求：必须能人为设置**已知神经信号、已知 HbO 响应、已知 lag、已知 coupling**，
并且这些真值要随数据一起导出，供后续算法验证使用。

物理设定：
  1. `neural_drive` 是慢变的"神经驱动"信号（0.01–0.08 Hz + 低通噪声）；
  2. EEG theta 振幅被 drive 调制 → theta 包络 ≈ drive（coupled 条件下）；
  3. HbO = drive ⊛ HRF(峰值 lag_s) + 生理噪声 + 漂移 + 运动伪迹；
  4. 因此 EEG theta 包络与 HbO 的互相关峰值应出现在 **+lag_s** 处。
     （lag > 0 表示 HbO 滞后于 EEG，符合神经血管耦合的方向性）
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from .erp import add_mmn_erp

FNIRS_FS = 1.0 / 0.075          # 13.333 Hz（决策 D-001）
EEG_FS = 1000.0
EYE_FS = 250.0


@dataclass
class SyntheticTruth:
    coupled: bool
    coupling_strength: float
    fnirs_lag_s: float
    hrv_sdnn_ms: float
    n_motion_artifacts: int
    n_scr_events: int
    theta_hz: float
    mmn_amplitude_uv: float = float("nan")
    mmn_latency_ms: float = float("nan")
    group: str = "synthetic"


@dataclass
class SyntheticSession:
    duration_s: float
    eeg_fs: float
    fnirs_fs: float
    eye_fs: float
    eeg: np.ndarray
    hbo: np.ndarray
    hbr: np.ndarray
    eeg_t: np.ndarray
    fnirs_t: np.ndarray
    gaze_x: np.ndarray
    gaze_y: np.ndarray
    pupil: np.ndarray
    eye_t: np.ndarray
    ecg: np.ndarray
    eda: np.ndarray
    physio_t: np.ndarray
    drive: np.ndarray
    truth: SyntheticTruth
    raw_760: np.ndarray | None = None
    raw_850: np.ndarray | None = None
    beats: np.ndarray | None = None
    meta: dict = field(default_factory=dict)


def _soft_noise(n: int, rng: np.random.Generator, alpha: float = 1.5) -> np.ndarray:
    """1/f^alpha 噪声（用 FFT 整形白噪声）。"""
    white = rng.standard_normal(n)
    freqs = np.fft.rfftfreq(n, d=1.0)
    freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
    shaped = white
    spec = np.fft.rfft(shaped) / freqs ** (alpha / 2.0)
    out = np.fft.irfft(spec, n=n)
    return out / (np.std(out) + 1e-12)


def neural_drive(duration_s: float, fs: float = 10.0, seed: int = 0) -> np.ndarray:
    """慢变神经驱动（0.01–0.08 Hz + 低通噪声），归一化到均值 0、SD 1。"""
    rng = np.random.default_rng(seed)
    n = int(duration_s * fs)
    t = np.arange(n) / fs
    drive = (0.6 * np.sin(2 * np.pi * 0.012 * t + rng.uniform(0, 6.28))
             + 0.4 * np.sin(2 * np.pi * 0.030 * t + rng.uniform(0, 6.28))
             + 0.3 * np.sin(2 * np.pi * 0.065 * t + rng.uniform(0, 6.28))
             + 0.5 * _soft_noise(n, rng))
    drive = np.convolve(drive, np.ones(int(2.0 * fs)) / (2.0 * fs), mode="same")
    return (drive - drive.mean()) / (drive.std() + 1e-12)


def hrf(peak_s: float = 5.0, fs: float = 10.0, duration_s: float = 30.0) -> np.ndarray:
    """双伽马 HRF，峰值时间可设（默认 5 s → 对应 NVC 典型滞后）。"""
    t = np.arange(0, duration_s, 1.0 / fs)
    a1, a2 = 6.0, 16.0
    b1 = peak_s / (a1 - 1.0) if peak_s > 0 else 1.0
    b2 = b1 * 1.6
    g1 = t ** (a1 - 1) * np.exp(-t / b1) / (b1 ** a1 * math.gamma(a1))
    g2 = t ** (a2 - 1) * np.exp(-t / b2) / (b2 ** a2 * math.gamma(a2))
    h = g1 - 0.35 * g2
    h = h - np.mean(h[-int(5 * fs):])                       # 去尾部基线
    return h / (np.abs(h).max() + 1e-12)


def generate_eeg(duration_s: float, *, fs: float = EEG_FS, theta_hz: float = 6.3,
                 drive: np.ndarray | None = None, drive_fs: float = 10.0,
                 coupling: float = 0.6, noise: float = 1.0, line_noise: float = 0.25,
                 seed: int = 0, output_uv: float | None = None) -> np.ndarray:
    """EEG：theta 振荡 + 振幅被 drive 调制 + 1/f 噪声 + 50 Hz 工频干扰。

    output_uv 不为 None 时，把信号缩放到该标准差（μV），以便 MMN 等指标用 μV 报告。
    """
    rng = np.random.default_rng(seed + 11)
    n = int(duration_s * fs)
    t = np.arange(n) / fs
    if drive is None:
        drive = neural_drive(duration_s, drive_fs, seed)
    d = np.interp(t, np.arange(len(drive)) / drive_fs, drive)
    d = (d - d.mean()) / (d.std() + 1e-12)
    amp = 1.0 + coupling * d
    # ⚠️ 关键：theta 必须**不锁相**于刺激序列。若用固定 6 Hz + 2 s 规则刺激，
    # 每个试次的 theta 相位完全相同 → 平均后不会抵消，会污染 MMN 差异波（实测伪 MMN −11 μV）。
    # 因此加入慢相位漂移，并把频率取成与刺激周期不成整数比的值。
    phase = 2 * np.pi * theta_hz * t + 1.5 * np.sin(2 * np.pi * 0.037 * t) + 0.3 * np.sin(2 * np.pi * 0.7 * t)
    theta = amp * np.sin(phase)
    eeg = (2.5 * theta + 1.0 * _soft_noise(n, rng) + 0.35 * noise * rng.standard_normal(n)
           + line_noise * np.sin(2 * np.pi * 50.0 * t))
    eeg = (eeg - np.mean(eeg)) / (np.std(eeg) + 1e-12)
    if output_uv is not None:
        eeg = eeg * float(output_uv)
    return eeg.astype(np.float64)


def _task_regressors(fs: float, n: int, task_blocks) -> np.ndarray:
    """把 [(onset_s, duration_s, amplitude)] 变成"方波 ⊛ HRF"的 HbO 回归量。"""
    reg = np.zeros(n)
    for onset, dur, amp in task_blocks or ():
        i0, i1 = int(onset * fs), min(n, int((onset + dur) * fs))
        if i1 > i0:
            reg[i0:i1] += amp
    kernel = hrf(peak_s=5.0, fs=fs)
    conv = np.convolve(reg, kernel)[:n]
    # 归一化：让"方波 ⊛ HRF"的稳态平台幅度 = 请求的 μM 值（否则 60 s 方波会长到 ~10 μM）
    return conv * (1.0 / (np.sum(kernel) + 1e-12))


def generate_fnirs(duration_s: float, *, fs: float = FNIRS_FS, drive: np.ndarray | None = None,
                   drive_fs: float = 10.0, lag_s: float = 5.0, hbo_amp: float = 1.0,
                   physio_noise: float = 0.6, drift: float = 0.4, motion_artifacts: int = 5,
                   task_blocks=None, task_amp: float = 0.4, hbo_scale_um: float = 0.12,
                   seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """fNIRS：HbO = drive ⊛ HRF(lag_s) + 生理噪声 + 漂移 + 运动伪迹；HbR ≈ -0.4 HbO + 噪声。"""
    rng = np.random.default_rng(seed + 23)
    n = int(duration_s * fs)
    t = np.arange(n) / fs
    if drive is None:
        drive = neural_drive(duration_s, drive_fs, seed)
    # 把 drive 插值到 fNIRS 采样率后与 HRF 卷积
    d = np.interp(t, np.arange(len(drive)) / drive_fs, drive)
    kernel = hrf(peak_s=lag_s, fs=fs)
    # ⚠️ 必须用 'full' 再截断：mode='same' 会把卷积结果对齐到核的**中心**，
    # 使有效滞后偏移半个核长（30 s 核 → −15 s）。这是本文件里踩过的一个真实坑。
    hbo_neural = np.convolve(d, kernel)[:n]
    # 归一到 SD=1，再按 μM 缩放（真实 fNIRS 的 ΔHbO 量级约 0.1–0.5 μM）
    hbo_neural = hbo_neural / (np.std(hbo_neural) + 1e-12) * hbo_scale_um
    # 生理噪声：Mayer 波 0.1 Hz、呼吸 0.25 Hz、心跳 1 Hz
    physio = (0.5 * np.sin(2 * np.pi * 0.10 * t + rng.uniform(0, 6.28))
              + 0.3 * np.sin(2 * np.pi * 0.25 * t + rng.uniform(0, 6.28))
              + 0.2 * np.sin(2 * np.pi * 1.0 * t + rng.uniform(0, 6.28)))
    slow = np.cumsum(_soft_noise(n, rng, alpha=2.0)) / np.sqrt(n)      # 随机游走型漂移
    task_signal = _task_regressors(fs, n, task_blocks) * task_amp      # μM
    # 单位 μM：神经慢成分 0.12 μM（真实量级），任务响应 0.4 μM，系统生理噪声 ~0.03 μM
    hbo = (hbo_amp * hbo_neural + task_signal + 0.05 * physio_noise * physio
           + 0.05 * drift * slow + 0.02 * rng.standard_normal(n))
    # 运动伪迹：短时大幅阶跃
    for _ in range(motion_artifacts):
        i = rng.integers(0, max(1, n - int(0.5 * fs)))
        width = int(rng.integers(1, max(2, int(0.3 * fs))))
        hbo[i:i + width] += rng.choice([-1, 1]) * rng.uniform(2.5, 5.0)
    hbr = -0.4 * hbo + 0.02 * rng.standard_normal(n)
    return hbo.astype(np.float64), hbr.astype(np.float64)


def generate_eye(duration_s: float, *, fs: float = EYE_FS, arousal: np.ndarray | None = None,
                 arousal_fs: float = 10.0, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """眼动：注视 + 扫视 + 眨眼缺失，瞳孔直径随唤醒度变化。"""
    rng = np.random.default_rng(seed + 37)
    n = int(duration_s * fs)
    t = np.arange(n) / fs
    if arousal is None:
        arousal = neural_drive(duration_s, arousal_fs, seed)
    a = np.interp(t, np.arange(len(arousal)) / arousal_fs, arousal)
    x, y, pos = np.zeros(n), np.zeros(n), (0.0, 0.0)
    pupil = 3.0 + 0.5 * (a - a.mean()) / (a.std() + 1e-12) + 0.05 * rng.standard_normal(n)
    i = 0
    while i < n:
        if rng.random() < 0.15:                     # 扫视
            pos = (rng.uniform(-10, 10), rng.uniform(-6, 6))
            dur = int(rng.integers(int(0.02 * fs), int(0.06 * fs)))
        else:                                        # 注视
            dur = int(rng.integers(int(0.2 * fs), int(1.2 * fs)))
        x[i:i + dur], y[i:i + dur] = pos
        i += dur
    blink = rng.random(n) < 0.002
    x[blink] = np.nan; y[blink] = np.nan; pupil[blink] = np.nan
    return x, y, pupil


def generate_physio(duration_s: float, *, fs: float = EEG_FS, hr_bpm: float = 72.0,
                    n_scr: int = 8, seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """ECG（含 HRV）与 EDA（含 SCR 事件）。"""
    rng = np.random.default_rng(seed + 53)
    n = int(duration_s * fs)
    t = np.arange(n) / fs
    rr = 60.0 / hr_bpm + 0.02 * _soft_noise(max(2, int(duration_s)), rng, alpha=1.0)
    beats, tt = [], 0.0
    k = 0
    while tt < duration_s:
        beats.append(tt)
        tt += float(rr[k % len(rr)]) if len(rr) else 60.0 / hr_bpm
        k += 1
    ecg = 0.02 * rng.standard_normal(n)
    for b in beats:                                   # QRS 复合波
        i = int(b * fs)
        if 0 <= i < n - int(0.1 * fs):
            seg = int(0.08 * fs)
            ecg[i:i + seg] += np.hanning(seg) * 2.0 * np.sin(np.linspace(0, np.pi, seg))
    drift_raw = np.cumsum(_soft_noise(n, rng, alpha=2.0))
    tonic = 2.0 + 0.3 * drift_raw / (np.std(drift_raw) + 1e-12)      # SD = 0.3 μS（真实量级）
    eda = tonic + 0.05 * rng.standard_normal(n)
    for _ in range(n_scr):
        i = int(rng.integers(0, max(1, n - int(8 * fs))))
        rise = np.exp(-np.arange(int(6 * fs)) / (fs * 1.5))
        eda[i:i + len(rise)] += rng.uniform(0.1, 0.5) * rise
    return ecg.astype(np.float64), eda.astype(np.float64), np.array(beats)


def generate_session(duration_s: float = 300.0, *, coupled: bool = True,
                     lag_s: float = 5.0, coupling: float = 0.6, seed: int = 0,
                     mmn_events: dict | None = None, group: str = "synthetic",
                     task_blocks=None, task_amp: float = 1.0) -> SyntheticSession:
    """一次完整的合成会话。

    coupled=False 时 EEG 与 fNIRS 由**不同的** drive 驱动。
    mmn_events: {"deviant_onsets_s": [...], "standard_onsets_s": [...]} → 叠加已知 MMN；
    group: "healthy_like" | "depressed_like" | "synthetic" → 改变 MMN 振幅/潜伏期（对标锚论文效应量）；
    task_blocks: [(onset_s, duration_s, amplitude)] → 任务期 HbO 激活（VFT / N-back 等）。
    """
    rng = np.random.default_rng(seed)
    drive_neural = neural_drive(duration_s, 10.0, seed)
    drive_hbo = drive_neural if coupled else neural_drive(duration_s, 10.0, seed + 999)
    eeg = generate_eeg(duration_s, drive=drive_neural, coupling=coupling if coupled else 0.0,
                       line_noise=0.25, seed=seed, output_uv=20.0)
    hbo, hbr = generate_fnirs(duration_s, drive=drive_hbo, lag_s=lag_s,
                              task_blocks=task_blocks, task_amp=task_amp, seed=seed)
    # 原始光强（供真正的 SCI 计算：同一通道两个波长的相关）
    rng_int = np.random.default_rng(seed + 77)
    t_raw = np.arange(len(hbo)) / FNIRS_FS
    # 共享的生理成分：Mayer 0.1 Hz + 呼吸 0.25 Hz + 心跳 1.0 Hz（1 Hz 落在 SCI 的 0.7–1.5 Hz 频带）
    shared = (1.0 * np.sin(2 * np.pi * 1.0 * t_raw + rng_int.uniform(0, 6.28))
              + 0.6 * np.sin(2 * np.pi * 0.1 * t_raw + rng_int.uniform(0, 6.28))
              + 0.4 * np.sin(2 * np.pi * 0.25 * t_raw + rng_int.uniform(0, 6.28))
              + 0.3 * rng_int.standard_normal(len(hbo)))
    neural = (hbo - hbo.mean()) / (hbo.std() + 1e-12)
    raw_760 = 100.0 + 0.30 * shared + 0.60 * neural + 0.25 * rng_int.standard_normal(len(hbo))
    raw_850 = 100.0 + 0.27 * shared + 0.45 * neural - 0.20 * ((hbr - hbr.mean()) / (hbr.std() + 1e-12)) \
        + 0.25 * rng_int.standard_normal(len(hbo))
    mmn_amp, mmn_lat = float("nan"), float("nan")
    if mmn_events:
        params = {"healthy_like": (-3.5, 200.0), "depressed_like": (-1.6, 235.0),
                  "synthetic": (-3.5, 200.0)}.get(group, (-3.5, 200.0))
        # 真值 = 差异波（偏差 − 标准）的幅度与潜伏期
        mmn_amp, mmn_lat = params[0] - (-0.6), params[1]
        # 标准与偏差取同一潜伏期 → 差异波峰值 = deviant − standard（可解释的真值）
        eeg = add_mmn_erp(eeg, EEG_FS, deviant_onsets_s=mmn_events.get("deviant_onsets_s", ()),
                          standard_onsets_s=mmn_events.get("standard_onsets_s", ()),
                          deviant_amplitude_uv=params[0], deviant_latency_ms=params[1],
                          standard_amplitude_uv=-0.6, standard_latency_ms=params[1], seed=seed)
    gaze_x, gaze_y, pupil = generate_eye(duration_s, arousal=drive_neural, seed=seed)
    ecg, eda, beats = generate_physio(duration_s, seed=seed)
    rr_s = np.diff(beats) if len(beats) > 1 else np.array([0.8])
    truth = SyntheticTruth(coupled=coupled, coupling_strength=coupling if coupled else 0.0,
                           fnirs_lag_s=lag_s, hrv_sdnn_ms=float(np.std(rr_s) * 1000),
                           n_motion_artifacts=5, n_scr_events=8, theta_hz=6.0,
                           mmn_amplitude_uv=mmn_amp, mmn_latency_ms=mmn_lat, group=group)
    return SyntheticSession(
        duration_s=duration_s, eeg_fs=EEG_FS, fnirs_fs=FNIRS_FS, eye_fs=EYE_FS,
        eeg=eeg, hbo=hbo, hbr=hbr,
        eeg_t=np.arange(len(eeg)) / EEG_FS,
        fnirs_t=np.arange(len(hbo)) / FNIRS_FS,
        gaze_x=gaze_x, gaze_y=gaze_y, pupil=pupil,
        eye_t=np.arange(len(gaze_x)) / EYE_FS,
        ecg=ecg, eda=eda, physio_t=np.arange(len(ecg)) / EEG_FS,
        drive=drive_neural, truth=truth, raw_760=raw_760, raw_850=raw_850, beats=beats,
        meta={"note": "synthetic data for algorithm validation only — never for scientific claims",
              "truth": asdict(truth), "seed": seed},
    )
