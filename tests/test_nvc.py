import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.nvc import (NVCSettings, analyze_nvc, bandpass, lagged_correlation, theta_envelope,
                       to_grid, validate_against_truth)
from bplus.simulate import generate_session

FAST = NVCSettings(n_surrogates=60, n_bootstrap=60, grid_hz=10.0)


@pytest.fixture(scope="module")
def coupled():
    s = generate_session(180, coupled=True, lag_s=5.0, coupling=0.7, seed=11)
    return s, analyze_nvc(s.eeg, s.eeg_fs, s.hbo, s.fnirs_fs, FAST, seed=1)


@pytest.fixture(scope="module")
def uncoupled():
    s = generate_session(180, coupled=False, seed=12)
    return s, analyze_nvc(s.eeg, s.eeg_fs, s.hbo, s.fnirs_fs, FAST, seed=2)


def test_bandpass_keeps_the_theta_band():
    fs = 1000.0
    t = np.arange(0, 10, 1 / fs)
    x = np.sin(2 * np.pi * 6 * t) + np.sin(2 * np.pi * 40 * t)
    y = bandpass(x, fs, 4, 8)
    spec = np.abs(np.fft.rfft(y))
    freqs = np.fft.rfftfreq(len(y), 1 / fs)
    assert freqs[int(np.argmax(spec))] == pytest.approx(6.0, abs=0.5)


def test_to_grid_interpolates_monotonically():
    t_src = np.arange(0, 10, 1.0)
    x = t_src * 2.0
    got = to_grid(t_src, x, np.array([0.0, 2.5, 5.0]))
    assert got == pytest.approx([0.0, 5.0, 10.0])


def test_lagged_correlation_recovers_a_known_shift():
    fs = 10.0
    rng = np.random.default_rng(0)
    a = np.cumsum(rng.standard_normal(1200))
    b = np.roll(a, 50)                        # b 滞后 a 5 s
    lags, r = lagged_correlation(a, b, fs, -2, 15)
    assert abs(lags[int(np.argmax(r))] - 5.0) <= 0.3


def test_coupled_recovers_lag_within_one_second(coupled):
    s, res = coupled
    checks = validate_against_truth(res, s.truth.fnirs_lag_s, coupled=True)
    assert checks["lag_within_tolerance"], checks
    assert checks["verdict"] == "PASS", checks
    assert res.r_peak >= 0.30
    assert res.p_value < 0.05
    assert res.ci_low_s <= s.truth.fnirs_lag_s <= res.ci_high_s


def test_uncoupled_is_not_significant(uncoupled):
    s, res = uncoupled
    checks = validate_against_truth(res, s.truth.fnirs_lag_s, coupled=False)
    assert checks["verdict"] == "PASS", checks          # 无耦合时"不显著"才算通过
    assert not res.significant


def test_theta_envelope_is_slower_than_raw_signal():
    s = __import__("bplus.simulate", fromlist=["generate_session"]).generate_session(60, seed=21)
    env = theta_envelope(s.eeg, s.eeg_fs, smooth_s=1.0)
    assert float(np.std(np.diff(env))) < 0.05 * float(np.std(env))
