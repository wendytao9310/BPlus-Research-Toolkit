#!/usr/bin/env python
"""合成数据 + NVC 验证（MASTER COMMAND §73-74）。

    MPLCONFIGDIR=/tmp/mpl python scripts/run_nvc_demo.py --duration 300

产出：
  data/nvc/nvc_report.json      验证结果（含真值、估计值、显著性、CI、判定）
  figures/nvc_validation.png    4 联图（EEGθ+包络 / HbO+HbR / 互相关曲线 / 替代检验零分布）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.nvc import (NVCSettings, analyze_nvc, effective_system_lag, theta_envelope,  # noqa: E402
                       validate_against_truth)
from bplus.simulate import generate_session  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="合成数据 NVC 验证")
    ap.add_argument("--duration", type=float, default=300.0)
    ap.add_argument("--lag", type=float, default=5.0)
    ap.add_argument("--coupling", type=float, default=0.7)
    ap.add_argument("--surrogates", type=int, default=200)
    ap.add_argument("--bootstrap", type=int, default=200)
    ap.add_argument("--out-json", default="data/nvc/nvc_report.json")
    ap.add_argument("--out-fig", default="figures/nvc_validation.png")
    args = ap.parse_args(argv)

    settings = NVCSettings(n_surrogates=args.surrogates, n_bootstrap=args.bootstrap)

    results = {}
    cases = {}
    for name, coupled in (("coupled", True), ("uncoupled", False)):
        s = generate_session(args.duration, coupled=coupled, lag_s=args.lag,
                             coupling=args.coupling, seed=11 if coupled else 12)
        res = analyze_nvc(s.eeg, s.eeg_fs, s.hbo, s.fnirs_fs, settings, seed=1 if coupled else 2)
        eff = effective_system_lag(s.drive, 10.0, s.hbo, s.fnirs_fs) if coupled else None
        checks = validate_against_truth(res, s.truth.fnirs_lag_s, coupled=coupled, effective_lag_s=eff)
        results[name] = {"truth": s.meta["truth"], "result": res.as_dict(), "checks": checks}
        cases[name] = (s, res)

    robustness = _robustness(args)
    report = {
        "experiment": "synthetic NVC validation",
        "settings": results["coupled"]["result"]["settings"],
        "cases": results,
        "robustness": robustness,
        "verdict": {k: v["checks"]["verdict"] for k, v in results.items()},
        "overall": "PASS" if all(v["checks"]["verdict"] == "PASS" for v in results.values()) else "FAIL",
        "note": "合成数据仅用于算法验证，不得作为科学结论",
        "evidence_status": "PROJECT_ENGINEERING_THRESHOLD",
    }
    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    _plot(cases, Path(args.out_fig), true_lag=args.lag)

    print("=" * 78)
    for name, r in results.items():
        c, res = r["checks"], r["result"]
        eff = f"  effective={c['lag_effective_s']:.2f}s  err_vs_eff={c.get('lag_error_vs_effective_s', float('nan')):.2f}s" if "lag_effective_s" in c else ""
        print(f"[{name:9}] lag_true={c['lag_true_s']:.1f}s  lag_est={c['lag_estimated_s']:.2f}s  "
              f"err={c['lag_error_s']:.2f}s{eff}\n            r={c['r_peak']:.3f}  p={c['p_value']:.4f}  "
              f"CI95=[{c['ci95_s'][0]:.1f},{c['ci95_s'][1]:.1f}]  → {c['verdict']}")
    print("=" * 78)
    print("鲁棒性扫描（耦合条件；误差 = |估计滞后 − 名义 5.0 s|）")
    for row in robustness["sweep"]:
        print(f"  noise={row['physio_noise']:.1f} artifacts={row['motion_artifacts']:>2}  "
              f"lag={row['lag_s']:.2f}s  err={row['lag_error_s']:.2f}s  r={row['r_peak']:.3f}  p={row['p_value']:.3f}")
    print("耦合强度扫描（看检出下限）：")
    for row in robustness["coupling_sweep"]:
        print(f"  coupling={row['coupling']:.2f}  lag={row['lag_s']:.2f}s  err={row['lag_error_s']:.2f}s  "
              f"r={row['r_peak']:.3f}  p={row['p_value']:.3f}  significant={row['significant']}")
    print(f"  缺失数据(10% NaN)：lag={robustness['missing_data']['lag_s']:.2f}s  "
          f"err={robustness['missing_data']['lag_error_s']:.2f}s  r={robustness['missing_data']['r_peak']:.3f}")
    print("=" * 78)
    print("overall:", report["overall"])
    print("report:", out_json)
    print("figure:", args.out_fig)
    return 0 if report["overall"] == "PASS" else 1


def _robustness(args) -> dict:
    """§74 要求：同时测试 surrogate / bootstrap / noise / missing data。"""
    import numpy as np

    from bplus.simulate import generate_fnirs, neural_drive

    sweep = []
    fast = NVCSettings(n_surrogates=100, n_bootstrap=60)
    for physio_noise, artifacts in ((0.2, 0), (0.6, 5), (1.2, 15)):
        s = generate_session(args.duration, coupled=True, lag_s=args.lag, coupling=args.coupling, seed=31)
        hbo, _ = generate_fnirs(args.duration, drive=s.drive, lag_s=args.lag,
                                physio_noise=physio_noise, motion_artifacts=artifacts, seed=31)
        res = analyze_nvc(s.eeg, s.eeg_fs, hbo, s.fnirs_fs, fast, seed=3)
        sweep.append({"physio_noise": physio_noise, "motion_artifacts": artifacts,
                      "lag_s": res.lag_s, "lag_error_s": abs(res.lag_s - args.lag),
                      "r_peak": res.r_peak, "p_value": res.p_value,
                      "pass": abs(res.lag_s - args.lag) <= 1.0 and res.significant})
    # 耦合强度扫描：找出"还能检出耦合"的下限（检验替代检验的检验力）
    coupling_sweep = []
    for level in (0.15, 0.30, 0.50, 0.70):
        s_c = generate_session(args.duration, coupled=True, lag_s=args.lag, coupling=level, seed=51)
        res_c = analyze_nvc(s_c.eeg, s_c.eeg_fs, s_c.hbo, s_c.fnirs_fs, fast, seed=5)
        coupling_sweep.append({"coupling": level, "lag_s": res_c.lag_s,
                               "lag_error_s": abs(res_c.lag_s - args.lag), "r_peak": res_c.r_peak,
                               "p_value": res_c.p_value, "significant": res_c.significant})

    # 缺失数据：随机把 10% 的 fNIRS 样本设为 NaN
    s = generate_session(args.duration, coupled=True, lag_s=args.lag, coupling=args.coupling, seed=41)
    hbo_missing = s.hbo.copy()
    rng = np.random.default_rng(5)
    hbo_missing[rng.random(len(hbo_missing)) < 0.10] = np.nan
    res_missing = analyze_nvc(s.eeg, s.eeg_fs, hbo_missing, s.fnirs_fs, fast, seed=4)
    missing = {"fraction_missing": 0.10, "lag_s": res_missing.lag_s,
               "lag_error_s": abs(res_missing.lag_s - args.lag), "r_peak": res_missing.r_peak,
               "p_value": res_missing.p_value,
               "pass": abs(res_missing.lag_s - args.lag) <= 1.0 and res_missing.significant}
    return {"sweep": sweep, "coupling_sweep": coupling_sweep, "missing_data": missing,
            "all_pass": all(r["pass"] for r in sweep) and missing["pass"],
            "evidence_status": "PROJECT_ENGINEERING_THRESHOLD"}


def _plot(cases, path: Path, *, true_lag: float) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    s, res = cases["coupled"]
    t = np.arange(len(s.eeg)) / s.eeg_fs
    env = theta_envelope(s.eeg, s.eeg_fs)
    tn = s.fnirs_t

    ax = axes[0, 0]
    ax.plot(t[: int(20 * s.eeg_fs)], s.eeg[: int(20 * s.eeg_fs)], lw=0.4, alpha=0.35, label="EEG (raw)")
    ax.plot(t[: int(20 * s.eeg_fs)], env[: int(20 * s.eeg_fs)], lw=1.6, label="theta envelope (4-8 Hz)")
    ax.set_title("A. EEG theta envelope (first 20 s)"); ax.set_xlabel("time (s)"); ax.legend(fontsize=8)

    ax = axes[0, 1]
    ax.plot(tn, s.hbo, lw=1.0, label="HbO (synthetic)")
    ax.plot(tn, s.hbr, lw=1.0, alpha=0.7, label="HbR (synthetic)")
    ax.set_title(f"B. fNIRS at {s.fnirs_fs:.2f} Hz (truth lag = {true_lag:.1f} s)")
    ax.set_xlabel("time (s)"); ax.legend(fontsize=8)

    ax = axes[1, 0]
    lags = np.array(res.lags_s); r = np.array(res.r_curve)
    ax.plot(lags, r, lw=1.6)
    ax.axvline(true_lag, color="green", ls="--", lw=1.2, label=f"true lag {true_lag:.1f} s")
    ax.axvline(res.lag_s, color="red", ls=":", lw=1.2, label=f"estimated {res.lag_s:.1f} s")
    ax.axhline(0, color="gray", lw=0.6)
    ax.set_title(f"C. r(tau) = corr(EEGtheta_env(t), HbO(t+tau))   peak r={res.r_peak:.3f}, p={res.p_value:.4f}")
    ax.set_xlabel("lag tau (s)"); ax.set_ylabel("r"); ax.legend(fontsize=8)

    ax = axes[1, 1]
    uncoupled_res = cases["uncoupled"][1]
    ax.plot(uncoupled_res.lags_s, uncoupled_res.r_curve, lw=1.4, color="darkorange",
            label=f"uncoupled control (max r={max(uncoupled_res.r_curve):.3f})")
    ax.plot(lags, r, lw=1.4, color="tab:blue", label="coupled")
    ax.axhline(0, color="gray", lw=0.6)
    ax.set_title("D. coupled vs uncoupled control"); ax.set_xlabel("lag tau (s)"); ax.legend(fontsize=8)

    fig.suptitle("NVC validation on synthetic data — PROJECT_ENGINEERING_THRESHOLD (not a clinical standard)",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(path, dpi=150)
    print("saved figure:", path)


if __name__ == "__main__":
    raise SystemExit(main())
