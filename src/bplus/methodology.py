"""Auditable preprocessing and modelling metadata for BPlus reports.

This module describes what the current pipeline actually executed.  It must not
claim publication-grade preprocessing or a trained clinical model when those
steps have not run.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _present(package: dict[str, Any], modality: str) -> bool:
    source = (package.get("sources") or {}).get(modality) or {}
    return str(source.get("status", "MISSING")).upper() != "MISSING"


def build_methodology(package: dict[str, Any]) -> dict[str, Any]:
    analysis = package.get("analysis") or {}
    eeg_qc = ((analysis.get("eeg_import") or {}).get("qc") or {})
    interview = analysis.get("interview") or {}
    interview_qc = interview.get("qc") or {}
    rows: list[dict[str, str]] = []

    if _present(package, "eeg"):
        sfreq = eeg_qc.get("sampling_rate_hz", "read from recording")
        rows.append({
            "modality": "EEG",
            "status": "Executed (engineering level)",
            "executed": (f"Read-only BrainVision import; identified sampling rate ({sfreq} Hz) and events 1–8; "
                         "0.5–40 Hz band-pass; robust peak-to-peak and standard-deviation bad-channel detection; "
                         "two-second-window artifact ratio; power spectrum, event-locked waveform, and task-segment feature extraction."),
            "not_executed": ("Average reference, bad-channel interpolation, ICA ocular/cardiac correction, and complete event-conditioned publication-level epoch cleaning have not been executed; "
                             "a 50 Hz notch should only be enabled after confirming line-noise contamination."),
            "scope": "Current results support automated QC and descriptive research reporting and are not equivalent to a frozen publication preprocessing pipeline.",
        })
    if _present(package, "fnirs"):
        delay = ((interview.get("parameters") or {}).get("hemodynamic_delay_s") or
                 interview_qc.get("hemodynamic_delay_s") or 5.0)
        rows.append({
            "modality": "fNIRS",
            "status": "Executed (descriptive)",
            "executed": ("Read-only Shimadzu OMM/PAT/EXT/AIN import; validated timeline, light intensity, and channels; converted voltage, absorbance, and HbO/HbR; "
                         f"extracted descriptive interview-versus-pre-task-baseline changes by task block using a {delay:g}-second hemodynamic delay."),
            "not_executed": ("Motion-artifact correction with frozen parameters, short-separation/physiological-noise regression, prewhitening, and task GLM have not been executed; "
                             "current results must not be described as GLM-validated cortical activation."),
            "scope": "Usable channels, valid blocks, rejection records, and all source files are retained; formal publication parameters must be locked by pilot testing.",
        })
    if _present(package, "behavior"):
        rows.append({
            "modality": "Behavioral",
            "status": "Executed",
            "executed": ("Read trial-level CSV; excluded practice trials; calculated N-back hits, false alarms, omissions, "
                         "accuracy, d-prime, and response time from targets, responses, and timing; summarized Emotion valence and arousal ratings."),
            "not_executed": "Behavioral results were not used to backfill missing neural events; anomalous trials still require consistent exclusion under preregistered rules.",
            "scope": "Trial-level raw exports are retained; aggregate features are derived results only.",
        })
    if not rows:
        rows.append({
            "modality": "Multimodal",
            "status": "No executable data available",
            "executed": "Report structure initialized only.",
            "not_executed": "No signal preprocessing or feature extraction has been executed.",
            "scope": "No participant status or model conclusion may be generated.",
        })

    return {
        "schema": "BPLUS-METHODS-1",
        "preprocessing": rows,
        "modelling": {
            "status": "NOT_TRAINED",
            "status_zh": "Not trained / not validated",
            "current_output": "This report uses descriptive single-session measures and project rules only; it does not output depression probability or diagnosis.",
            "planned_primary_analysis": ("Begin with group-by-task-condition mixed-effects models and continuous symptom-dimension analysis, reporting effect sizes, "
                                         "95% confidence intervals, and FDR correction."),
            "planned_prediction": ("After cohort accumulation, begin with an Elastic Net baseline; place all preprocessing, imputation, scaling, and feature selection "
                                   "inside participant-level nested cross-validation, followed by external validation using independent time-period or center data."),
            "required_before_activation": [
                "Freeze the event dictionary and publication-level preprocessing parameters",
                "Use clinician-confirmed labels or a prespecified continuous outcome",
                "Complete participant-level internal validation, calibration assessment, and independent external validation",
                "Lock the model version, intended population, failure conditions, and researcher approval workflow",
            ],
        },
    }


def _flatten_numeric(data: dict[str, Any], prefix: str = ""):
    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _flatten_numeric(value, name)
        elif isinstance(value, (int, float, bool)) and value is not None:
            yield name, value


def write_model_feature_row(path: str | Path, package: dict[str, Any]) -> Path:
    """Write one audit-friendly participant/session row for later cohort assembly."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    row: dict[str, Any] = {
        "participant_id": package.get("participant_id"),
        "session_id": package.get("session_id"),
        "age": package.get("age"),
        "data_quality.score": (package.get("data_quality") or {}).get("score"),
        "data_quality.band": (package.get("data_quality") or {}).get("band"),
    }
    for modality, source in (package.get("sources") or {}).items():
        row[f"source_status.{modality}"] = (source or {}).get("status", "MISSING")
    row.update(dict(_flatten_numeric(package.get("features") or {})))
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    return output


def preprocessing_audit(package: dict[str, Any], methods: dict[str, Any]) -> dict[str, Any]:
    analysis = package.get("analysis") or {}
    exclusions = {
        "eeg_rejected_records": analysis.get("eeg_bundle_errors", []),
        "fnirs_rejected_records": analysis.get("fnirs_bundle_errors", []),
        "eeg_bad_channels": ((analysis.get("eeg_import") or {}).get("qc") or {}).get("bad_channels", []),
    }
    return {
        "schema": "BPLUS-PREPROCESSING-AUDIT-1",
        "participant_id": package.get("participant_id"),
        "session_id": package.get("session_id"),
        "methods": methods["preprocessing"],
        "analysis_qc": {key: value.get("qc", {}) for key, value in analysis.items()
                        if isinstance(value, dict)},
        "exclusions": exclusions,
        "notes": (package.get("data_quality") or {}).get("notes", []),
    }


__all__ = ["build_methodology", "preprocessing_audit", "write_model_feature_row"]
