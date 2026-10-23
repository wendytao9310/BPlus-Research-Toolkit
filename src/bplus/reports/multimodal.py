"""Validated multimodal feature package -> four-page BPlus state report."""
from __future__ import annotations

import json
import csv
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..state import StateEngine
from ..methodology import build_methodology, preprocessing_audit, write_model_feature_row
from .renderer import render_participant_markdown, render_researcher_markdown, to_html
from .v27 import build_report_payload, render_v27_html

REQUIRED_TOP_LEVEL = {"participant_id", "session_id", "features", "data_quality", "sources"}
ALLOWED_SOURCE_STATUS = {"VERIFIED", "PILOT", "SIMULATED", "MISSING"}


def validate_multimodal_package(package: dict[str, Any]) -> list[str]:
    missing = sorted(REQUIRED_TOP_LEVEL - set(package))
    if missing:
        raise ValueError(f"The multimodal analysis package is missing fields: {', '.join(missing)}")
    if not isinstance(package["features"], dict):
        raise ValueError("features must be a JSON object")
    if not isinstance(package["data_quality"], dict):
        raise ValueError("data_quality must be a JSON object")
    if not isinstance(package["sources"], dict):
        raise ValueError("sources must be a JSON object")
    warnings: list[str] = []
    for modality in ("eeg", "fnirs", "eye", "behavior", "physiology", "clinical"):
        source = package["sources"].get(modality) or {"status": "MISSING"}
        status = str(source.get("status", "MISSING")).upper()
        if status not in ALLOWED_SOURCE_STATUS:
            raise ValueError(f"Unsupported sources.{modality}.status: {status}")
        if status in {"SIMULATED", "MISSING"}:
            warnings.append(f"{modality}: {status}")
    score = package["data_quality"].get("score")
    if score is not None and not 0 <= float(score) <= 100:
        raise ValueError("data_quality.score must be between 0 and 100")
    return warnings


def generate_multimodal_report(package_path: str | Path, out_dir: str | Path, *,
                               require_review: bool = False) -> dict[str, Path]:
    source_path = Path(package_path)
    package = json.loads(source_path.read_text(encoding="utf-8"))
    warnings = validate_multimodal_package(package)
    if package.get("workflow_schema") == "BPLUS-ANALYSIS-1" or require_review:
        decision = (package.get("review") or {}).get("decision")
        if decision != "APPROVED":
            raise ValueError("The analysis has not passed researcher review, so a participant status report cannot be generated")
    participant = str(package["participant_id"]).strip()
    session = str(package["session_id"]).strip()
    if not participant or not session:
        raise ValueError("Participant ID and session ID cannot be empty")

    dq = dict(package["data_quality"])
    dq.setdefault("score", 0.0)
    dq.setdefault("band", "INCOMPLETE")
    dq.setdefault("band_zh", "Incomplete data")
    dq.setdefault("notes", [])
    dq["notes"] = list(dq["notes"]) + [f"Input modality status: {warning}" for warning in warnings]
    significance = float(package.get("significance", 1.0))
    profile = StateEngine().evaluate(package["features"], participant_id=participant,
                                     session_id=session, dq=dq, significance=significance)
    profile.notes.extend(dq["notes"])
    profile_dict = profile.as_dict()

    output = Path(out_dir) / f"sub-{participant}_ses-{session}"
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "html": output / "report.html",
        "report_payload": output / "report_payload.json",
        "metrics": output / "metrics.json",
        "metrics_csv": output / "metrics.csv",
        "qc": output / "qc.json",
        "provenance": output / "provenance.json",
        "participant_markdown": output / "participant_report.md",
        "researcher_markdown": output / "researcher_report.md",
        "state_profile": output / "state_profile.json",
        "analysis_methods": output / "analysis_methods.json",
        "preprocessing_log": output / "preprocessing_log.json",
        "model_features": output / "model_features.csv",
        "modeling_status": output / "modeling_status.json",
    }
    methods = build_methodology(package)
    package["methodology"] = methods
    payload = build_report_payload(package, profile_dict, stage="REVIEWED")
    paths["html"].write_text(render_v27_html(payload), encoding="utf-8")
    paths["report_payload"].write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["metrics"].write_text(json.dumps(package["features"], ensure_ascii=False, indent=2), encoding="utf-8")
    _write_metrics_csv(paths["metrics_csv"], package["features"])
    qc_payload = {"data_quality": dq, "analysis_qc": {
        key: value.get("qc", {}) for key, value in (package.get("analysis") or {}).items()
        if isinstance(value, dict)}}
    paths["qc"].write_text(json.dumps(qc_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    provenance = _provenance(source_path, package)
    paths["provenance"].write_text(json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["analysis_methods"].write_text(json.dumps(methods, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["preprocessing_log"].write_text(
        json.dumps(preprocessing_audit(package, methods), ensure_ascii=False, indent=2), encoding="utf-8")
    paths["modeling_status"].write_text(
        json.dumps(methods["modelling"], ensure_ascii=False, indent=2), encoding="utf-8")
    write_model_feature_row(paths["model_features"], package)
    paths["participant_markdown"].write_text(render_participant_markdown(profile_dict), encoding="utf-8")
    paths["researcher_markdown"].write_text(
        render_researcher_markdown(profile_dict, package["features"]), encoding="utf-8")
    audit = {"profile": profile_dict, "features": package["features"], "sources": package["sources"],
             "data_quality": dq, "input_package": str(source_path.resolve()), "warnings": warnings,
             "review": package.get("review"), "analysis": package.get("analysis"),
             "report_scope": "RESEARCH STATE DESCRIPTION; NOT A MEDICAL OR PSYCHOLOGICAL DIAGNOSIS"}
    paths["state_profile"].write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def _flatten(data: dict[str, Any], prefix: str = ""):
    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _flatten(value, name)
        else:
            yield name, value


def _write_metrics_csv(path: Path, features: dict[str, Any]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["metric", "value"])
        writer.writerows(_flatten(features))


def _provenance(source_path: Path, package: dict[str, Any]) -> dict[str, Any]:
    project_root = Path(__file__).resolve().parents[3]
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "NOT_AVAILABLE"
    encoded = json.dumps(package, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {"pipeline_version": "0.2.0", "report_version": "2.7", "git_commit": commit,
            "config_hash": hashlib.sha256(encoded).hexdigest(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "input_files": [str(source_path.resolve())],
            "report_scope": "RESEARCH STATE DESCRIPTION; NOT A DIAGNOSIS"}
