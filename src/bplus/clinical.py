"""Clinician-entered clinical/psychological report data.

The module stores and displays qualified-reviewer input verbatim. It never
derives diagnoses or severity labels from questionnaire totals.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


ITEMS = {
    "k_sads": {"result": "k_sads_status", "state": "k_sads_interpretation"},
    "cdrs_r": {"result": "cdrs_r_total", "state": "cdrs_r_status"},
    "cdi": {"result": "cdi_total", "state": "cdi_status"},
    "phq9": {"result": "phq9_total", "state": "phq9_status"},
    "phq15": {"result": "phq15_total", "state": "phq15_status"},
    "sdq_parent": {"result": "sdq_parent_total", "state": "sdq_parent_status"},
}

NUMERIC_RANGES = {
    "cdrs_r_total": (17, 113), "cdi_total": (0, 54), "phq9_total": (0, 27),
    "phq15_total": (0, 30), "sdq_parent_total": (0, 40),
}


def _clean_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    allowed = {field for item in ITEMS.values() for field in item.values()}
    for key, value in assessment.items():
        if key not in allowed or value in (None, ""):
            continue
        if key in NUMERIC_RANGES:
            try:
                number = int(str(value).strip())
            except ValueError as exc:
                raise ValueError(f"{key} 必须填写整数") from exc
            lower, upper = NUMERIC_RANGES[key]
            if not lower <= number <= upper:
                raise ValueError(f"{key} 必须在 {lower}–{upper} 之间")
            cleaned[key] = number
        else:
            cleaned[key] = str(value).strip()
    return cleaned


def apply_clinical_assessment(package: dict[str, Any], assessment: dict[str, Any], *,
                              clinician: str, note: str = "") -> dict[str, Any]:
    """Attach clinician-entered results and interpretations to an analysis package."""
    if not clinician.strip():
        raise ValueError("必须填写临床医生/评估人员姓名")
    values = _clean_assessment(assessment)
    if not values:
        raise ValueError("至少填写一项临床或心理评估结果")
    updated = deepcopy(package)
    features = updated.setdefault("features", {})
    features.setdefault("clinical", {}).update(values)
    recorded_at = datetime.now(timezone.utc).isoformat()
    updated.setdefault("sources", {})["clinical"] = {
        "status": "VERIFIED", "format": "clinician-entered structured assessment",
        "reviewer": clinician.strip(), "recorded_at": recorded_at,
    }
    updated.setdefault("analysis", {})["clinical"] = {
        "qc": {"status": "PASS", "notes": ["临床状态为评估人员原样录入，系统未自动分级。"]},
        "reviewer": clinician.strip(), "recorded_at": recorded_at, "note": note.strip(),
        "entered_fields": sorted(values),
    }
    # Any prior package approval does not automatically approve newly added
    # clinical content. The caller must perform a fresh package review.
    updated["review"] = {"decision": "PENDING", "reviewer": "", "note": "新增临床资料后待重新审核"}
    return updated


__all__ = ["ITEMS", "NUMERIC_RANGES", "apply_clinical_assessment"]
