import pytest

from bplus.clinical import apply_clinical_assessment
from bplus.reports.v27 import build_report_payload


def _package(age=15):
    return {"participant_id": "P01", "session_id": "1", "age": age,
            "sources": {name: {"status": "MISSING"} for name in ("eeg", "fnirs", "eye", "behavior", "clinical")},
            "data_quality": {"score": 70, "band": "ACCEPTABLE"}, "features": {}}


def test_clinician_result_and_state_are_displayed_verbatim():
    package = apply_clinical_assessment(
        _package(), {"cdrs_r_total": "41", "cdrs_r_status": "医生评估：需结合访谈继续观察",
                     "phq9_total": "12", "phq9_status": "医生评估：症状负担中等"},
        clinician="Dr Li")
    rows = {row["name"]: row for row in build_report_payload(package)["clinical_module"]["rows"]}
    assert rows["CDRS-R"]["display_value"] == "41"
    assert rows["CDRS-R"]["state"] == "医生评估：需结合访谈继续观察"
    assert rows["PHQ-9"]["state"] == "医生评估：症状负担中等"
    assert package["sources"]["clinical"]["reviewer"] == "Dr Li"
    assert package["review"]["decision"] == "PENDING"


def test_clinical_score_range_is_validated_without_auto_interpretation():
    with pytest.raises(ValueError, match="0–27"):
        apply_clinical_assessment(_package(), {"phq9_total": 30}, clinician="Dr Li")
