#!/usr/bin/env python
"""端到端 DEMO：合成被试 → 特征 → QC/DQ → 三层状态 → 被试 4 页报告 + 研究者报告。

    MPLCONFIGDIR=/tmp/mpl .venv/bin/python scripts/run_state_demo.py --group depressed_like

产出（data/reports/）：
  participant_report.md    被试 4 页报告（不含任何原始指标，有硬守卫）
  researcher_report.md     研究者报告（含全部量化特征与可追溯输入）
  report.html              自包含 HTML（上层被试视图 + 折叠的研究者附录）
  state_profile.json       完整状态画像（供 Streamlit Dashboard 读取）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus import config as cfg_mod  # noqa: E402
from bplus.features import (count_scr, extract_mmn, glm_task_beta, hrv_sdnn,  # noqa: E402
                            line_noise_ratio, motion_artifact_ratio, scalp_coupling_index,
                            task_response)
from bplus.nvc import NVCSettings, analyze_nvc  # noqa: E402
from bplus.protocol import build_session  # noqa: E402
from bplus.qc import dq_from_feature_dict  # noqa: E402
from bplus.reports import render_participant_markdown, render_researcher_markdown, to_html  # noqa: E402
from bplus.simulate import generate_session  # noqa: E402
from bplus.state import StateEngine  # noqa: E402
from bplus.triggers import TriggerCode  # noqa: E402

CLINICAL_PRESETS = {
    "healthy_like":   {"phq9_total": 3.0, "gad7_total": 2.0, "sleep_score": 2.0, "social_impairment": 1.0},
    "depressed_like": {"phq9_total": 14.0, "gad7_total": 10.0, "sleep_score": 6.0, "social_impairment": 5.0},
}


def _events_by_code(timeline, code):
    return [e.onset_s for e in timeline.events if int(e.code) == int(code)]


def _blocks(timeline, code, duration_s, amp):
    return [(e.onset_s, duration_s, amp) for e in timeline.events if int(e.code) == int(code)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="BPlus 端到端 DEMO（合成被试）")
    ap.add_argument("--participant", default="DEMO01")
    ap.add_argument("--session", default="1")
    ap.add_argument("--group", default="depressed_like", choices=["healthy_like", "depressed_like"])
    ap.add_argument("--duration", type=float, default=4200.0, help="合成时长（默认 70 min）")
    ap.add_argument("--out", default="data/reports")
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args(argv)

    # 1) 70 分钟协议时间线（真配置）
    protocol = cfg_mod.protocol_config()
    paradigm_names = ("rest", "mmn", "vft", "nback", "emotion", "recovery")
    timeline = build_session(protocol, {n: cfg_mod.paradigm_config(n) for n in paradigm_names})

    dev_on = _events_by_code(timeline, TriggerCode.MMN_DEVIANT)
    std_on = _events_by_code(timeline, TriggerCode.MMN_STANDARD)
    task_blocks = (_blocks(timeline, TriggerCode.VFT_BLOCK, 15.0, 0.50)
                   + _blocks(timeline, TriggerCode.NBACK_2BACK, 24.0, 0.55)
                   + _blocks(timeline, TriggerCode.NBACK_0BACK, 24.0, 0.28))

    # 2) 合成被试（EEG 含已知 MMN；fNIRS 含已知任务激活与 NVC）
    session = generate_session(args.duration, coupled=True, lag_s=5.0, coupling=0.7, seed=args.seed,
                               mmn_events={"deviant_onsets_s": dev_on, "standard_onsets_s": std_on},
                               group=args.group, task_blocks=task_blocks, task_amp=0.4)

    # 3) 特征提取
    mmn = extract_mmn(session.eeg, session.eeg_fs, deviant_onsets_s=dev_on, standard_onsets_s=std_on)
    vft_blocks = _blocks(timeline, TriggerCode.VFT_BLOCK, 15.0, 0.50)
    nback_blocks = (_blocks(timeline, TriggerCode.NBACK_2BACK, 24.0, 0.55)
                    + _blocks(timeline, TriggerCode.NBACK_0BACK, 24.0, 0.28))
    # VFT：单周期设计 → 用「任务 − 静息」均值对比（与锚论文 P001 / 岛津惯例一致）
    vft_task_on = [(e.onset_s, float(e.meta.get("sub_block_s", 15.0)))
                   for e in timeline.events if int(e.code) == int(TriggerCode.VFT_BLOCK)]
    vft_rest_on = [(e.onset_s, float(e.meta.get("duration_s", 30.0)))
                   for e in timeline.events if int(e.code) == int(TriggerCode.VFT_REST)]
    vft_contrast = task_response(session.hbo, session.fnirs_fs, task_windows=vft_task_on,
                                 rest_windows=vft_rest_on)
    nback_glm = glm_task_beta(session.hbo, session.fnirs_fs, task_blocks=nback_blocks)
    # 块间稳定性：每个子模块各自的 ΔHbO 的离散度
    per_sub_block = [task_response(session.hbo, session.fnirs_fs, task_windows=[b], rest_windows=vft_rest_on)["delta"]
                     for b in vft_task_on]
    nvc = analyze_nvc(session.eeg, session.eeg_fs, session.hbo, session.fnirs_fs,
                      NVCSettings(n_surrogates=100, n_bootstrap=60), seed=3)

    # 恢复指标：任务后 HbO 回落到基线的比例（0 = 完全回落，1 = 完全没回落）
    fnirs_fs = session.fnirs_fs
    def _mean(onset, dur):
        i0, i1 = int(onset * fnirs_fs), min(len(session.hbo), int((onset + dur) * fnirs_fs))
        return float(session.hbo[i0:i1].mean()) if i1 > i0 else float("nan")
    rest_on = _events_by_code(timeline, TriggerCode.REST_START)[0]
    rec_on = _events_by_code(timeline, TriggerCode.RECOVERY_START)[0]
    baseline_hbo, recovery_hbo = _mean(rest_on, 60), _mean(rec_on, 100)
    task_hbo = _mean(vft_blocks[0][0] + 20, 40)
    denom = (task_hbo - baseline_hbo) or 1e-9
    hbo_return = float(np.clip((recovery_hbo - baseline_hbo) / denom, 0.0, 1.0))

    rng = np.random.default_rng(args.seed)
    mood = {"healthy_like": (3.4, 2.6), "depressed_like": (2.5, 3.2)}[args.group]
    features = {
        "nback": {"d_prime": 3.1 if args.group == "healthy_like" else 1.9,
                  "rt_cv": 0.16 if args.group == "healthy_like" else 0.27,
                  "accuracy": 0.95 if args.group == "healthy_like" else 0.84,
                  "omission_rate": 0.04 if args.group == "healthy_like" else 0.16,
                  "false_alarm_rate": 0.03 if args.group == "healthy_like" else 0.14,
                  "median_rt_ms": 480.0 if args.group == "healthy_like" else 560.0},
        "eeg": {"mmn_amplitude_abs_uv": abs(mmn["mmn_amplitude_uv"] or 0.0),
                "mmn_latency_ms": mmn["mmn_latency_ms"],
                "usable_channel_ratio": 0.94, "line_noise_ratio": line_noise_ratio(session.eeg, session.eeg_fs),
                "artifact_ratio": 0.02, "epoch_rejection_ratio": 0.07},
        "fnirs": {"vft_hbo_delta_um": vft_contrast["delta"], "nback_hbo_beta_um": nback_glm["beta_um"],
                  "vft_hbo_block_sd": float(np.std(per_sub_block)),
                  "sci": scalp_coupling_index(session.raw_760, session.raw_850, session.fnirs_fs),
                  "channel_quality": 0.92,
                  "motion_artifact_ratio": motion_artifact_ratio(session.hbo),
                  "baseline_drift": float(abs(session.hbo[len(session.hbo)//2:].mean() - session.hbo[:len(session.hbo)//2].mean()) / (np.std(session.hbo) + 1e-9))},
        "nvc": {"r": nvc.r_peak, "p_value": nvc.p_value, "lag_s": nvc.lag_s,
                "ci_low_s": nvc.ci_low_s, "ci_high_s": nvc.ci_high_s},
        "physiology": {"hrv_sdnn_ms": hrv_sdnn(session.beats), "scr_count": float(count_scr(session.eda, session.eeg_fs)),
                       "valid_segment_ratio": 0.96},
        "emotion": {"valence_mean": mood[0] + 0.1 * rng.standard_normal(),
                    "arousal_mean": mood[1] + 0.1 * rng.standard_normal()},
        "recovery": {"hbo_return_ratio": hbo_return,
                     "hrv_return_ratio": float(np.clip(0.25 + 0.2 * rng.standard_normal(), 0, 1))},
        "eye": {"gaze_dispersion_deg": 2.4 if args.group == "healthy_like" else 3.6},
        "epoch": {"valid_ratio": 0.93, "n_per_condition": 60},
        "clinical": dict(CLINICAL_PRESETS[args.group]),
    }

    # 4) 同步体检报告（用同一套比较逻辑，保证 DQ 里的同步项有真实来源）
    from bplus.sync_check import Pulse, compare
    codes = list(range(101, 111))
    eeg_p = [Pulse(c, i * 1.0) for i, c in enumerate(codes)]
    fnirs_p = [Pulse(c, i * 1.0 + 0.012 + 0.004 * rng.standard_normal()) for i, c in enumerate(codes)]
    sync_report = compare(codes, eeg_p, fnirs_p, session=f"sub-{args.participant}_ses-{args.session}").as_dict()

    # 5) DQ + 状态
    dq = dq_from_feature_dict(features, sync_report=sync_report)
    profile = StateEngine().evaluate(features, participant_id=args.participant, session_id=args.session,
                                     dq=dq.as_dict(),
                                     significance=1.0 if nvc.significant else 0.5)

    # 6) 报告落盘
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "participant_report.md").write_text(render_participant_markdown(profile.as_dict()), encoding="utf-8")
    (out / "researcher_report.md").write_text(render_researcher_markdown(profile.as_dict(), features), encoding="utf-8")
    (out / "report.html").write_text(to_html(profile.as_dict(), features), encoding="utf-8")
    (out / "state_profile.json").write_text(json.dumps(
        {"profile": profile.as_dict(), "features": features, "sync_report": sync_report,
         "synthetic_truth": session.meta["truth"],
         "note": "DEMO：数据为合成，仅用于验证链路，不得作为科学结论"},
        ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    # 7) 控制台摘要
    print("=" * 84)
    print(f"participant={args.participant}  group={args.group}  duration={args.duration:.0f}s")
    print(f"MMN: {mmn['mmn_amplitude_uv']:.2f} μV @ {mmn['mmn_latency_ms']:.0f} ms "
          f"(真值 {session.truth.mmn_amplitude_uv:.2f} μV @ {session.truth.mmn_latency_ms:.0f} ms; "
          f"{mmn['n_deviants']} 偏差 / {mmn['n_standards']} 标准)")
    if abs(mmn["mmn_amplitude_uv"]) < 1.5:
        print("  ⚠️ 该 MMN 幅度接近噪声底线：协议只有 ~51-60 个偏差试次时，"
              "1 μV 量级的 MMN 无法可靠测量（须在 PILOT 用实测信噪比复核，见 D-017）")
    print(f"NVC: r={nvc.r_peak:.3f}  p={nvc.p_value:.4f}  lag={nvc.lag_s:.1f}s (真值 {session.truth.fnirs_lag_s:.1f}s)")
    print(f"HbO: VFT ΔHbO(任务−静息)={vft_contrast['delta']:.3f} μM (真值 0.50)  |  "
          f"N-back GLM β={nback_glm['beta_um']:.3f} μM (真值 ~0.3-0.55)")
    print(f"DQ={dq.score} ({dq.band})  |  同步: {sync_report['verdict']} offset={sync_report['offset_ms']} ms")
    print("-" * 84)
    print(f"{'层级':<10}{'状态':<18}{'等级':<12}{'置信度':<8}")
    for layer, group in (("任务", profile.task_state), ("脑功能", profile.brain_state), ("临床", profile.clinical_state)):
        for v in group.values():
            print(f"{layer:<10}{v['zh']:<18}{v['level_zh']:<12}{v['confidence']:<8}")
    print("-" * 84)
    print(f"综合画像: {profile.integrated['level_zh']} (score={profile.integrated['score']:.3f})  "
          f"整体置信度: {profile.confidence_overall['label_zh']}")
    print(f"报告目录: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
