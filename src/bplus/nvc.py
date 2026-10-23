"""EEG–fNIRS 神经血管耦合（NVC）分析 + 合成数据验证（MASTER COMMAND §43、§74）。

方法（全部可追溯）：
  1. EEG 取 theta 频段（4–8 Hz）→ Hilbert 包络 → 平滑；
  2. 把包络与 HbO 都插值到同一分析网格（默认 10 Hz，见 sync.yaml resampling）；
  3. 计算 r(τ) = corr(EEGθ_env(t), HbO(t+τ))，τ 扫描 −2…15 s；
  4. 峰值 τ 即 NVC 滞后；峰值相关即耦合强度；
  5. 显著性：**循环移位替代检验**（保留自相关结构），对 τ 范围内的最大 |r| 做零分布；
  6. 不确定性：**循环块 bootstrap** 给出滞后 95% CI。

阈值（PROJECT_ENGINEERING_THRESHOLD，非国际标准）：
  * 滞后恢复误差 ≤ 1.0 s（§74 明确要求 "lag ≈ 5 sec"）
  * 耦合显著：r ≥ 0.30 且 p < 0.05
  * 无耦合对照：不应同时满足上述两条
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
from scipy.signal import butter, hilbert, sosfiltfilt


@dataclass
class NVCSettings:
    eeg_band_hz: tuple[float, float] = (4.0, 8.0)
    grid_hz: float = 10.0
    lag_min_s: float = -2.0
    lag_max_s: float = 15.0
    smooth_s: float = 0.5
    n_surrogates: int = 200
    n_bootstrap: int = 200
    block_s: float = 20.0
    min_r: float = 0.30
    alpha: float = 0.05
    max_lag_error_s: float = 1.0


@dataclass
class NVCResult:
    lag_s: float
    r_peak: float
    p_value: float
    ci_low_s: float
    ci_high_s: float
    n_samples: int
    grid_hz: float
    lags_s: list[float] = field(default_factory=list)
    r_curve: list[float] = field(default_factory=list)
    settings: dict = field(default_factory=dict)

    @property
    def significant(self) -> bool:
        return self.r_peak >= self.settings.get("min_r", 0.30) and self.p_value < self.settings.get("alpha", 0.05)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["significant"] = self.significant
        d["evidence_status"] = "PROJECT_ENGINEERING_THRESHOLD"
        return d


def bandpass(x: np.ndarray, fs: float, lo: float, hi: float, order: int = 4) -> np.ndarray:
    """零相位带通（二阶节 SOS 形式）。

    ⚠️ 必须用 SOS：当 lo/nyq 很小（例如 0.1 Hz @ 1000 Hz 采样）时，
    `butter(..., b, a)` + `filtfilt` 会数值失稳并产出 inf → 所有 epoch 被判为伪迹。
    这是本项目踩过的真实坑（见 PROTOCOL_DECISION_LOG D-021）。
    """
    nyq = fs / 2.0
    hi = min(hi, nyq * 0.99)
    lo = max(lo, 1e-6)
    sos = butter(order, [lo / nyq, hi / nyq], btype="band", output="sos")
    return sosfiltfilt(sos, x)


def theta_envelope(eeg: np.ndarray, fs: float, *, band=(4.0, 8.0), smooth_s: float = 0.5) -> np.ndarray:
    """theta 频段包络：带通 → Hilbert 幅值 → 滑动平均。"""
    bp = bandpass(eeg, fs, band[0], band[1])
    env = np.abs(hilbert(bp))
    win = max(1, int(smooth_s * fs))
    kernel = np.ones(win) / win
    return np.convolve(env, kernel, mode="same")


def to_grid(t_src: np.ndarray, x: np.ndarray, t_dst: np.ndarray) -> np.ndarray:
    """线性插值到统一网格（重采样只作用于**信号**，事件时间戳永不重采样，D-005）。

    支持缺失数据：NaN 会被剔除后再插值（§74 要求测试 missing data）。
    若有效样本少于 50%，直接抛错——宁可失败，也不要用不可靠的数据算耦合。
    """
    x = np.asarray(x, dtype=float)
    mask = np.isfinite(x)
    if mask.sum() < 0.5 * len(x):
        raise ValueError(f"有效样本不足（{mask.sum()}/{len(x)}），无法可靠重采样")
    return np.interp(t_dst, np.asarray(t_src)[mask], x[mask])


def lagged_correlation(env: np.ndarray, hbo: np.ndarray, fs: float,
                       lag_min_s: float, lag_max_s: float) -> tuple[np.ndarray, np.ndarray]:
    """r(τ) = corr(env(t), hbo(t+τ))；τ>0 表示 HbO 滞后于 EEG。"""
    lags = np.arange(lag_min_s, lag_max_s + 1e-9, 1.0 / fs)
    n = len(env)
    env_z = (env - env.mean()) / (env.std() + 1e-12)
    hbo_z = (hbo - hbo.mean()) / (hbo.std() + 1e-12)
    r = np.empty_like(lags)
    for i, lag in enumerate(lags):
        shift = int(round(lag * fs))
        if shift >= 0:
            a = env_z[:n - shift] if shift > 0 else env_z
            b = hbo_z[shift:]
        else:
            a = env_z[-shift:]
            b = hbo_z[:n + shift]
        if len(a) < 10:
            r[i] = np.nan
            continue
        aa = (a - a.mean()) / (a.std() + 1e-12)
        bb = (b - b.mean()) / (b.std() + 1e-12)
        r[i] = float(np.mean(aa * bb))
    return lags, r


def _shift(x: np.ndarray, k: int) -> np.ndarray:
    return np.roll(x, k)


def surrogate_p_value(env: np.ndarray, hbo: np.ndarray, fs: float, lags: np.ndarray, r_obs: np.ndarray,
                      *, n_surrogates: int, min_shift_s: float = 20.0,
                      seed: int = 0) -> float:
    """循环移位替代检验：零假设 = 两信号无时间锁定关系。"""
    rng = np.random.default_rng(seed)
    n = len(env)
    obs = np.nanmax(r_obs)
    max_shift = max(1, int(min_shift_s * fs))
    count = 0
    for _ in range(n_surrogates):
        k = int(rng.integers(max_shift, n - max_shift))
        _, r_s = lagged_correlation(_shift(env, k), hbo, fs, lags[0], lags[-1])
        if np.nanmax(r_s) >= obs:
            count += 1
    return (count + 1.0) / (n_surrogates + 1.0)


def bootstrap_lag_ci(env: np.ndarray, hbo: np.ndarray, fs: float, lags: np.ndarray, *,
                     n_bootstrap: int, block_s: float, seed: int = 0) -> tuple[float, float, float]:
    """循环块 bootstrap：返回 (峰值滞后中位数, 2.5% 分位, 97.5% 分位)。"""
    rng = np.random.default_rng(seed + 1)
    n = len(env)
    block = max(2, int(block_s * fs))
    n_blocks = max(1, n // block)
    peaks = []
    for _ in range(n_bootstrap):
        idx = []
        for _ in range(n_blocks):
            start = int(rng.integers(0, n - block))
            idx.append(np.arange(start, start + block))
        idx = np.concatenate(idx)[:n]
        _, r_s = lagged_correlation(env[idx], hbo[idx], fs, lags[0], lags[-1])
        if np.all(np.isnan(r_s)):
            continue
        peaks.append(lags[int(np.nanargmax(r_s))])
    if len(peaks) < 10:
        return float("nan"), float("nan"), float("nan")
    return float(np.median(peaks)), float(np.percentile(peaks, 2.5)), float(np.percentile(peaks, 97.5))


def analyze_nvc(eeg: np.ndarray, eeg_fs: float, hbo: np.ndarray, fnirs_fs: float,
                settings: NVCSettings | None = None, *, seed: int = 0) -> NVCResult:
    s = settings or NVCSettings()
    env = theta_envelope(eeg, eeg_fs, band=s.eeg_band_hz, smooth_s=s.smooth_s)
    t_fnirs = np.arange(len(hbo)) / fnirs_fs
    t_grid = np.arange(0, t_fnirs[-1], 1.0 / s.grid_hz)
    env_g = to_grid(np.arange(len(env)) / eeg_fs, env, t_grid)
    hbo_g = to_grid(t_fnirs, hbo, t_grid)
    lags, r = lagged_correlation(env_g, hbo_g, s.grid_hz, s.lag_min_s, s.lag_max_s)
    i_peak = int(np.nanargmax(r))
    peak_lag, peak_r = float(lags[i_peak]), float(r[i_peak])
    p = surrogate_p_value(env_g, hbo_g, s.grid_hz, lags, r, n_surrogates=s.n_surrogates, seed=seed)
    _, lo, hi = bootstrap_lag_ci(env_g, hbo_g, s.grid_hz, lags, n_bootstrap=s.n_bootstrap,
                                 block_s=s.block_s, seed=seed)
    return NVCResult(lag_s=peak_lag, r_peak=peak_r, p_value=p, ci_low_s=lo, ci_high_s=hi,
                     n_samples=len(t_grid), grid_hz=s.grid_hz,
                     lags_s=[float(x) for x in lags], r_curve=[float(x) for x in r],
                     settings={"min_r": s.min_r, "alpha": s.alpha, "max_lag_error_s": s.max_lag_error_s,
                               "eeg_band_hz": list(s.eeg_band_hz), "smooth_s": s.smooth_s,
                               "n_surrogates": s.n_surrogates, "n_bootstrap": s.n_bootstrap})


def effective_system_lag(drive: np.ndarray, drive_fs: float, hbo: np.ndarray, fnirs_fs: float,
                         *, grid_hz: float = 10.0, lag_max_s: float = 15.0) -> float:
    """用**真实 drive**（而不是名义 HRF 峰值）测出的系统滞后。

    这是比"HRF 峰值 = 5.0 s"更严格的基准：算法估计的是互相关峰值，
    其基准就应该是 drive 与 HbO 的互相关峰值（宽 HRF 会把峰值推后）。
    """
    t_fnirs = np.arange(len(hbo)) / fnirs_fs
    t_grid = np.arange(0, t_fnirs[-1], 1.0 / grid_hz)
    d = to_grid(np.arange(len(drive)) / drive_fs, drive, t_grid)
    h = to_grid(t_fnirs, hbo, t_grid)
    lags, r = lagged_correlation(d, h, grid_hz, -2.0, lag_max_s)
    return float(lags[int(np.nanargmax(r))])


def validate_against_truth(result: NVCResult, true_lag_s: float, *, coupled: bool,
                           effective_lag_s: float | None = None) -> dict:
    """按 §74 判定：coupled 时滞后必须恢复且显著；uncoupled 时不应显著。"""
    err = abs(result.lag_s - true_lag_s)
    checks = {
        "lag_true_s": true_lag_s,
        "lag_estimated_s": result.lag_s,
        "lag_error_s": err,
        "lag_within_tolerance": err <= result.settings.get("max_lag_error_s", 1.0),
        "r_peak": result.r_peak,
        "p_value": result.p_value,
        "significant": result.significant,
        "ci95_s": [result.ci_low_s, result.ci_high_s],
    }
    if effective_lag_s is not None:
        checks["lag_effective_s"] = effective_lag_s
        checks["lag_error_vs_effective_s"] = abs(result.lag_s - effective_lag_s)
        checks["lag_within_effective_tolerance"] = (
            checks["lag_error_vs_effective_s"] <= result.settings.get("max_lag_error_s", 1.0))
    if coupled:
        ok = checks["lag_within_tolerance"] and result.significant
        if effective_lag_s is not None:
            ok = ok and checks["lag_within_effective_tolerance"]
        checks["verdict"] = "PASS" if ok else "FAIL"
    else:
        checks["verdict"] = "PASS" if not result.significant else "FAIL"
    checks["evidence_status"] = "PROJECT_ENGINEERING_THRESHOLD"
    return checks
