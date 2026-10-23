import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.state import StateEngine
from bplus.state.engine import compare_sessions

FEATS = {
    "nback": {"d_prime": 2.6, "rt_cv": 0.18, "accuracy": 0.93, "omission_rate": 0.08, "false_alarm_rate": 0.05},
    "eeg": {"mmn_amplitude_abs_uv": 2.83, "mmn_latency_ms": 205},
    "fnirs": {"vft_hbo_beta_um": 0.5, "vft_hbo_block_sd": 0.18, "nback_hbo_beta_um": 0.35, "sci": 0.87},
    "nvc": {"r": 0.55, "p_value": 0.005},
    "physiology": {"hrv_sdnn_ms": 45, "scr_count": 8},
    "emotion": {"valence_mean": 3.2, "arousal_mean": 3.1},
    "recovery": {"hbo_return_ratio": 0.25, "hrv_return_ratio": 0.3},
    "eye": {"gaze_dispersion_deg": 3.0},
    "clinical": {"phq9_total": 12, "gad7_total": 8, "sleep_score": 5, "social_impairment": 3},
}


def _engine():
    return StateEngine()


def test_all_three_layers_and_integrated_are_produced():
    p = _engine().evaluate(FEATS, dq={"score": 88, "band": "GOOD"}, participant_id="T01")
    assert set(p.task_state) >= {"cognitive_load", "attention", "emotional_arousal",
                                 "task_adaptation", "recovery"}
    assert set(p.brain_state) >= {"pfc_activity", "executive_control", "sensory_processing",
                                  "emotion_processing", "eeg_fnirs_coordination", "recovery"}
    assert set(p.clinical_state) >= {"depressive_symptoms", "anxiety_symptoms",
                                     "sleep_concerns", "social_functioning"}
    assert p.integrated["level"] in ("Low", "Mild", "Moderate", "High")
    assert 0.0 <= p.integrated["score"] <= 1.0


def test_every_score_is_traceable_to_its_inputs():
    p = _engine().evaluate(FEATS, dq={"score": 88, "band": "GOOD"})
    for group in (p.task_state, p.brain_state, p.clinical_state):
        for v in group.values():
            assert v["inputs"], v["key"]
            for i in v["inputs"]:
                assert {"metric", "value", "normalised", "ref", "weight", "evidence"} <= set(i)


def test_missing_metrics_reduce_coverage_and_confidence():
    full = _engine().evaluate(FEATS, dq={"score": 90, "band": "GOOD"})
    partial_feats = {"nback": {"d_prime": 2.6}}          # 只有 1 个指标
    partial = _engine().evaluate(partial_feats, dq={"score": 90, "band": "GOOD"})
    assert partial.task_state["cognitive_load"]["confidence_score"] < \
           full.task_state["cognitive_load"]["confidence_score"]
    assert any("缺失指标" in n for n in partial.task_state["cognitive_load"]["notes"])


def test_low_data_quality_lowers_confidence():
    good = _engine().evaluate(FEATS, dq={"score": 95, "band": "GOOD"})
    bad = _engine().evaluate(FEATS, dq={"score": 35, "band": "INVALID"})
    assert bad.confidence_overall["score"] < good.confidence_overall["score"]


def test_baseline_blending_changes_the_score():
    p1 = _engine().evaluate(FEATS, dq={"score": 88, "band": "GOOD"})
    baseline = {k: v for k, v in
                (("nback.d_prime", 3.6), ("nback.rt_cv", 0.12), ("fnirs.nback_hbo_beta_um", 0.15))}
    p2 = _engine().evaluate(FEATS, dq={"score": 88, "band": "GOOD"}, baseline=baseline)
    assert p2.baseline_used is True
    assert p2.task_state["cognitive_load"]["score"] != p1.task_state["cognitive_load"]["score"]


def test_longitudinal_comparison_reports_direction():
    prev = _engine().evaluate({**FEATS, "clinical": {**FEATS["clinical"], "phq9_total": 20}},
                              dq={"score": 88, "band": "GOOD"}).as_dict()
    cur = _engine().evaluate(FEATS, dq={"score": 88, "band": "GOOD"}).as_dict()
    diff = compare_sessions(prev, cur)
    assert diff["clinical_state.depressive_symptoms"]["direction"] in ("better", "worse", "stable")
    assert diff["clinical_state.depressive_symptoms"]["score_delta"] < 0      # 症状变轻


def test_clinical_states_carry_the_hospital_pending_flag():
    p = _engine().evaluate(FEATS, dq={"score": 88, "band": "GOOD"})
    for v in p.clinical_state.values():
        assert v["evidence_status"].startswith("CLINICAL_PENDING")
        assert any("医院确认" in n for n in v["notes"])
