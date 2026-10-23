import json
import pytest

from bplus.reports import generate_multimodal_report
from bplus.state import StateEngine


def test_missing_features_are_insufficient_not_high():
    profile = StateEngine().evaluate({}, dq={"score": 0, "band": "INCOMPLETE", "band_zh": "数据不完整"})
    assert all(item["level_zh"] == "数据不足" for item in profile.brain_state.values())
    assert all(item["confidence"] == "Low" for item in profile.brain_state.values())
    assert profile.integrated["level_zh"] == "数据不足"
    assert profile.integrated["score"] is None


def test_partial_report_renormalizes_available_layers_and_writes_audit(tmp_path):
    package = {
        "participant_id": "P01", "session_id": "1",
        "sources": {
            "eeg": {"status": "PILOT", "file": "P01.cnt"},
            "fnirs": {"status": "PILOT", "file": "P01.txt"},
            "eye": {"status": "MISSING"}, "behavior": {"status": "VERIFIED"},
            "clinical": {"status": "MISSING"},
        },
        "data_quality": {"score": 78, "band": "ACCEPTABLE", "band_zh": "可接受"},
        "significance": 0.5,
        "features": {
            "nback": {"d_prime": 2.1, "rt_cv": 0.2, "accuracy": 0.88,
                      "omission_rate": 0.1, "false_alarm_rate": 0.08},
            "eeg": {"mmn_amplitude_abs_uv": 1.7, "mmn_latency_ms": 190},
            "fnirs": {"nback_hbo_beta_um": 0.22, "vft_hbo_block_sd": 0.12, "sci": 0.82},
            "nvc": {"r": 0.3, "p_value": 0.04},
            "emotion": {"valence_mean": 3.2, "arousal_mean": 2.9},
            "recovery": {"hbo_return_ratio": 0.3}, "eye": {}, "clinical": {},
        },
    }
    source = tmp_path / "package.json"
    source.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    paths = generate_multimodal_report(source, tmp_path / "reports")
    html = paths["html"].read_text(encoding="utf-8")
    audit = json.loads(paths["state_profile"].read_text(encoding="utf-8"))
    assert "BPlus 青少年多模态研究报告" in html
    assert "自动感觉加工 · MMN" in html
    assert "工作记忆 · N-back" in html
    assert "数据不足" in html
    assert audit["sources"]["eeg"]["status"] == "PILOT"
    assert audit["profile"]["integrated"]["weights_effective"]
    for key in ("report_payload", "metrics", "metrics_csv", "qc", "provenance",
                "analysis_methods", "preprocessing_log", "model_features", "modeling_status"):
        assert paths[key].exists()
    payload = json.loads(paths["report_payload"].read_text(encoding="utf-8"))
    assert payload["report_version"] == "2.7"
    assert payload["participant_id"] == "P01"
    assert payload["total_modules"] == 6
    assert all(module["key"] != "recovery" for module in payload["modules"])
    assert "任务后恢复" not in html
    assert "研究者方法记录 · 数据预处理" in html
    assert "模型状态：尚未训练／尚未验证" in html
    model_status = json.loads(paths["modeling_status"].read_text(encoding="utf-8"))
    assert model_status["status"] == "NOT_TRAINED"
    model_row = paths["model_features"].read_text(encoding="utf-8-sig")
    assert "participant_id" in model_row and "nback.d_prime" in model_row


def test_failed_module_qc_suppresses_values(tmp_path):
    package = {
        "participant_id": "P02", "session_id": "1",
        "sources": {name: {"status": "MISSING"} for name in ("eeg", "fnirs", "eye", "behavior", "clinical")},
        "data_quality": {"score": 20, "band": "INCOMPLETE", "band_zh": "数据不完整"},
        "features": {"eeg": {"mmn_amplitude_uv": -9.99, "mmn_latency_ms": 180}},
        "analysis": {"mmn": {"qc": {"status": "QC_FAILED"}}},
    }
    source = tmp_path / "failed.json"
    source.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    paths = generate_multimodal_report(source, tmp_path / "reports")
    html = paths["html"].read_text(encoding="utf-8")
    assert "−9.99" not in html and "-9.99" not in html
    assert "本模块数据未达到预设质量要求" in html


def test_age_specific_clinical_rows_do_not_invent_uncollected_scores(tmp_path):
    package = {
        "participant_id": "P10", "session_id": "1", "age": 10,
        "sources": {name: {"status": "MISSING"} for name in ("eeg", "fnirs", "eye", "behavior", "clinical")},
        "data_quality": {"score": 0, "band": "INCOMPLETE", "band_zh": "数据不完整"},
        "features": {"clinical": {"cdi_total": 12}},
    }
    source = tmp_path / "age10.json"
    source.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    paths = generate_multimodal_report(source, tmp_path / "reports")
    html = paths["html"].read_text(encoding="utf-8")
    assert "CDI" in html and "PHQ-15" in html and "SDQ 家长版" in html
    assert "PHQ-9" not in html
    assert "未采集" in html and "由临床人员解释" in html


def test_age_15_clinical_rows_use_adolescent_battery(tmp_path):
    package = {
        "participant_id": "P15", "session_id": "1", "age": 15,
        "sources": {name: {"status": "MISSING"} for name in ("eeg", "fnirs", "eye", "behavior", "clinical")},
        "data_quality": {"score": 0, "band": "INCOMPLETE", "band_zh": "数据不完整"},
        "features": {"clinical": {}},
    }
    source = tmp_path / "age15.json"
    source.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
    html = generate_multimodal_report(source, tmp_path / "reports")["html"].read_text(encoding="utf-8")
    assert "PHQ-9" in html and "PHQ-15" in html
    assert "CDI" not in html and "SDQ 家长版" not in html


def test_formal_entry_point_requires_review_even_for_legacy_package(tmp_path):
    package = {
        "participant_id": "P03", "session_id": "1",
        "sources": {name: {"status": "MISSING"} for name in ("eeg", "fnirs", "eye", "behavior", "clinical")},
        "data_quality": {"score": 0, "band": "INCOMPLETE"}, "features": {},
    }
    source = tmp_path / "legacy.json"
    source.write_text(json.dumps(package), encoding="utf-8")
    with pytest.raises(ValueError, match="研究者审核"):
        generate_multimodal_report(source, tmp_path / "reports", require_review=True)
