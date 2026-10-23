import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.qc import compute_dq, dq_from_feature_dict, score_eeg, score_fnirs, score_physiology, score_synchronization


def test_dq_weights_match_the_master_command():
    dq = compute_dq(eeg=score_eeg(usable_channel_ratio=0.95, epoch_rejection_ratio=0.05),
                    fnirs=score_fnirs(sci=0.9, channel_quality=0.95),
                    epoch=score_synchronization(verdict="PASS", pulse_completeness=True, offset_ms=10, jitter_sd_ms=5),
                    sync=score_synchronization(verdict="PASS", pulse_completeness=True, offset_ms=10, jitter_sd_ms=5),
                    physiology=score_physiology(valid_segment_ratio=0.95, hrv_sdnn_ms=40, scr_events=5))
    assert dq.components["weights_declared"] == {"eeg": 0.25, "fnirs": 0.30, "epoch": 0.20,
                                                 "synchronization": 0.15, "physiology": 0.10}
    assert dq.components["weights_effective"] == dq.components["weights_declared"]
    assert dq.components["missing"] == []
    assert dq.band in ("GOOD", "ACCEPTABLE", "POOR", "INVALID")


def test_poor_eeg_lowers_dq_and_is_flagged():
    good = compute_dq(eeg=score_eeg(usable_channel_ratio=0.95),
                      fnirs=score_fnirs(sci=0.9, channel_quality=0.95),
                      epoch=score_synchronization(verdict="PASS", pulse_completeness=True, offset_ms=5, jitter_sd_ms=3),
                      sync=score_synchronization(verdict="PASS", pulse_completeness=True, offset_ms=5, jitter_sd_ms=3),
                      physiology=score_physiology(valid_segment_ratio=0.95, hrv_sdnn_ms=40, scr_events=3))
    bad = compute_dq(eeg=score_eeg(usable_channel_ratio=0.55, line_noise_ratio=0.5,
                                   movement_artifact_ratio=0.4, epoch_rejection_ratio=0.4),
                     fnirs=score_fnirs(sci=0.9, channel_quality=0.95),
                     epoch=score_synchronization(verdict="PASS", pulse_completeness=True, offset_ms=5, jitter_sd_ms=3),
                     sync=score_synchronization(verdict="PASS", pulse_completeness=True, offset_ms=5, jitter_sd_ms=3),
                     physiology=score_physiology(valid_segment_ratio=0.95, hrv_sdnn_ms=40, scr_events=3))
    assert bad.score < good.score
    assert any("eeg" in n for n in bad.notes)


def test_failed_synchronization_zeroes_its_component_and_flags():
    sync = score_synchronization(verdict="FAIL", pulse_completeness=False, offset_ms=200, jitter_sd_ms=90)
    assert sync.score == 0.0 and sync.label == "INVALID"
    dq = compute_dq(eeg=score_eeg(usable_channel_ratio=0.95), fnirs=score_fnirs(sci=0.9, channel_quality=0.95),
                    epoch=score_synchronization(verdict="PASS", pulse_completeness=True, offset_ms=5, jitter_sd_ms=3),
                    sync=sync, physiology=score_physiology(valid_segment_ratio=0.95, hrv_sdnn_ms=40, scr_events=3))
    assert any("synchronization" in n for n in dq.notes)


def test_dq_from_feature_dict_reads_sync_report():
    features = {"eeg": {"usable_channel_ratio": 0.92, "line_noise_ratio": 0.1, "artifact_ratio": 0.05,
                        "epoch_rejection_ratio": 0.08},
                "fnirs": {"sci": 0.88, "channel_quality": 0.9, "motion_artifact_ratio": 0.05, "baseline_drift": 0.1},
                "epoch": {"valid_ratio": 0.9, "n_per_condition": 40},
                "physiology": {"valid_segment_ratio": 0.95, "hrv_sdnn_ms": 45, "scr_events": 6}}
    sync = {"verdict": "PASS", "counts": {"eeg": 10, "fnirs": 10}, "missing_codes": [], "offset_ms": 12.0, "jitter_sd_ms": 8.0}
    dq = dq_from_feature_dict(features, sync_report=sync)
    assert dq.score > 70 and dq.band in ("GOOD", "ACCEPTABLE")
    assert dq.components["synchronization"]["score"] == 100.0
