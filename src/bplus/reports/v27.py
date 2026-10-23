"""BPlus report v2.7 payload builder and fixed-layout renderer.

The HTML template only displays a payload. Metric extraction, QC suppression,
and cautious wording are handled here so missing or failed modalities cannot
leak misleading values into the participant report.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from .interpretation import describe_metric, interpretation_config


TEMPLATE_DIR = Path(__file__).with_name("templates")


def _get(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for key in dotted.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current.get("value") if isinstance(current, dict) and "value" in current else current


def _display(value: Any, unit: str = "", digits: int = 2) -> str:
    if value is None:
        return "Pending"
    if isinstance(value, float):
        value = f"{value:.{digits}f}"
    return f"{value}{(' ' + unit) if unit else ''}"


def _qc_status(package: dict[str, Any], module: str, has_values: bool) -> str:
    analysis = package.get("analysis") or {}
    entry = analysis.get(module) or {}
    raw = str((entry.get("qc") or {}).get("status", "")).upper()
    if raw in {"FAIL", "QC_FAILED", "FAILED"}:
        return "FAIL"
    if raw in {"WARN", "WARNING"}:
        return "WARN"
    if raw == "PASS":
        return "PASS"
    return "PASS" if has_values else "DATA PENDING"


def _row(name: str, value: Any, unit: str, description: str, qc: str,
         *, metric: str | None = None, state: str | None = None, digits: int = 2) -> dict[str, str]:
    if qc == "FAIL":
        return {"name": name, "display_value": "—", "state": "Insufficient data", "state_class": "state-pending",
                "description": "This module did not meet the predefined quality requirements, so no status interpretation is provided."}
    if value is None:
        return {"name": name, "display_value": "Pending", "state": "Insufficient data", "state_class": "state-pending",
                "description": description}
    if state is None:
        state, basis = describe_metric(metric or "", value)
    else:
        basis = interpretation_config()["disclaimer"]
    state_class = "state-warn" if qc == "WARN" else "state-response"
    return {"name": name, "display_value": _display(value, unit, digits), "state": state,
            "state_class": state_class, "description": description, "basis": basis}


def _module(key: str, title: str, description: str, rows: list[dict[str, str]], qc: str,
            width: str, summary: str) -> dict[str, Any]:
    if qc == "FAIL":
        summary = "This module did not meet the predefined quality requirements, so no status interpretation is provided."
    elif qc == "WARN":
        summary = f"{summary} This module has a quality warning and should be interpreted cautiously."
    elif qc == "DATA PENDING":
        summary = "Complete quantitative measures are currently unavailable; no classification is provided."
    return {"key": key, "title": title, "description": description, "rows": rows,
            "qc": qc, "badge_class": "WARN" if qc == "DATA PENDING" else qc,
            "width": width, "summary": summary}


def _clinical_row(name: str, value: Any, description: str, clinician_state: Any = None) -> dict[str, str]:
    if value is None or value == "":
        return {"name": name, "display_value": "Not collected", "state": "Not collected",
                "state_class": "state-pending", "description": description}
    state = str(clinician_state).strip() if clinician_state not in (None, "") else "Awaiting clinician interpretation"
    return {"name": name, "display_value": str(value), "state": state,
            "state_class": "state-warn", "description": description}


def _clinical_module(package: dict[str, Any], features: dict[str, Any]) -> dict[str, Any]:
    age = package.get("age")
    try:
        age = int(age) if age not in (None, "") else None
    except (TypeError, ValueError):
        age = None
    common = [
        ("K-SADS Clinical Interview", "k_sads_status", "k_sads_interpretation", "Administered and interpreted by a clinician."),
        ("CDRS-R", "cdrs_r_total", "cdrs_r_status", "The Children's Depression Rating Scale result is interpreted only by clinical staff."),
    ]
    if age is not None and 6 <= age < 9:
        specs = common + [("SDQ Parent Version", "sdq_parent_total", "sdq_parent_status", "Completed by the participant's parent or guardian.")]
    elif age is not None and 9 <= age < 12:
        specs = common + [("CDI", "cdi_total", "cdi_status", "Completed by the participant."),
                          ("PHQ-15", "phq15_total", "phq15_status", "Completed by the participant."),
                          ("SDQ Parent Version", "sdq_parent_total", "sdq_parent_status", "Completed by the participant's parent or guardian.")]
    elif age is not None and 12 <= age <= 18:
        specs = common + [("PHQ-9", "phq9_total", "phq9_status", "Completed by the participant."),
                          ("PHQ-15", "phq15_total", "phq15_status", "Completed by the participant.")]
    else:
        specs = common
    values = [_get(features, f"clinical.{key}") for _, key, _, _ in specs]
    source_status = str(((package.get("sources") or {}).get("clinical") or {}).get("status", "MISSING")).upper()
    if not any(value is not None for value in values):
        qc = "DATA PENDING"
    elif source_status in {"VERIFIED", "PILOT"}:
        qc = "PASS"
    else:
        qc = "WARN"
    age_text = f"{age} years" if age is not None else "Age not entered"
    rows = [_clinical_row(name, value, description, _get(features, f"clinical.{state_key}"))
            for (name, _, state_key, description), value in zip(specs, values)]
    summary = (f"The interview and scales specified by the protocol for age {age_text} are shown; all results require clinical interpretation."
               if age is not None else "Age was not entered, so only general clinical-interview items are shown; enter age to confirm the scale set.")
    return {"key": "clinical", "title": "Clinical / Psychological Data", "description": f"Age stratum: {age_text}. The system displays collected results only and does not make automatic judgments.",
            "rows": rows, "qc": qc, "badge_class": "WARN" if qc == "DATA PENDING" else qc,
            "width": "w-100", "summary": summary}


def build_report_payload(package: dict[str, Any], profile: dict[str, Any] | None = None,
                         *, stage: str = "REVIEWED") -> dict[str, Any]:
    source_statuses = {str((source or {}).get("status", "MISSING")).upper()
                       for source in (package.get("sources") or {}).values()}
    simulated = "SIMULATED" in source_statuses
    if simulated:
        stage = "SIMULATION"
    features = package.get("features") or {}
    methodology = package.get("methodology") or {}
    modeling_status = methodology.get("modelling") or {
        "status": "NOT_TRAINED",
        "status_zh": "Not trained / not validated",
        "current_output": "This report displays descriptive results from imported data only; it does not output depression probability or diagnosis.",
        "planned_primary_analysis": "To be implemented after cohort data, outcomes, and the analysis plan are locked.",
        "planned_prediction": "To be trained after the dataset, labels, and participant-level validation plan are locked.",
        "required_before_activation": [
            "Freeze the event dictionary and publication-level preprocessing parameters",
            "Define clinician-confirmed labels or a prespecified continuous outcome",
            "Complete participant-level internal validation, calibration assessment, and independent external validation",
        ],
    }
    modules: list[dict[str, Any]] = []

    rest_values = [_get(features, key) for key in ("rest.alpha_relative_power", "rest.theta_relative_power",
                                                    "rest.iaf_hz", "rest.fnirs_baseline_stability")]
    rest_qc = _qc_status(package, "rest", any(v is not None for v in rest_values))
    modules.append(_module("rest", "Resting Baseline", "Records the three-minute resting state before the main tasks to establish the pre-task baseline for this session.", [
        _row("Resting alpha relative power", rest_values[0], "", "Describes the relative level of alpha rhythm during quiet rest.", rest_qc),
        _row("Resting theta relative power", rest_values[1], "", "Describes the relative level of slower EEG rhythm during quiet rest.", rest_qc),
        _row("Individual alpha peak frequency (IAF)", rest_values[2], "Hz", "Identifies the participant's primary alpha-rhythm frequency.", rest_qc),
        _row("fNIRS baseline stability", rest_values[3], "", "Assesses whether prefrontal oxygenation provides a reliable baseline.", rest_qc),
    ], rest_qc, "w-50", "Resting-baseline measures were recorded for this session."))

    mmn_values = [_get(features, "eeg.mmn_amplitude_uv"), _get(features, "eeg.mmn_latency_ms"),
                  _get(package, "analysis.mmn.qc.n_deviant")]
    if mmn_values[0] is None:
        absolute = _get(features, "eeg.mmn_amplitude_abs_uv")
        mmn_values[0] = -absolute if isinstance(absolute, (int, float)) else None
    mmn_qc = _qc_status(package, "mmn", any(v is not None for v in mmn_values))
    modules.append(_module("mmn", "Automatic Sensory Processing · MMN", "Records the automatic EEG response to auditory change.", [
        _row("100–250 ms MMN amplitude", mmn_values[0], "µV", "A more negative value indicates a more pronounced standard-versus-deviant difference response in this task.", mmn_qc, metric="eeg.mmn_amplitude_uv"),
        _row("Peak latency", mmn_values[1], "ms", "Time at which the automatic auditory-difference response reaches its peak.", mmn_qc, metric="eeg.mmn_latency_ms", digits=0),
        _row("Usable deviant trials", mmn_values[2], "", "A larger number of usable trials generally supports a more stable averaged waveform.", mmn_qc, metric="analysis.mmn.qc.n_deviant", digits=0),
    ], mmn_qc, "w-50", "An analyzable automatic auditory-difference response was obtained."))

    nback_p3 = _get(features, "eeg.nback_p3_diff_uv")
    nback_p3_name = "P3 condition difference"
    nback_p3_description = "A positive value indicates a larger information-updating response under high versus low load."
    if nback_p3 is None:
        nback_p3 = _get(features, "eeg.nback_enter_locked_positive_uv")
        nback_p3_name = "Enter response-locked positive potential"
        nback_p3_description = "Centroparietal mean potential time-locked to Enter (marker 6); this response-locked measure is not equivalent to a target-stimulus-locked P3 condition difference."
    nback_values = [_get(features, "nback.d_prime"), _get(features, "nback.median_rt_ms"),
                    nback_p3, _get(features, "eeg.frontal_theta_diff_db"),
                    _get(features, "fnirs.nback_hbo_beta_um")]
    nback_qc = _qc_status(package, "nback", any(v is not None for v in nback_values))
    modules.append(_module("nback", "Working Memory · N-back", "Records target discrimination, response speed, and load-related physiological change.", [
        _row("d-prime (target discrimination)", nback_values[0], "", "Combines hits and false alarms to describe separation of targets and non-targets.", nback_qc, metric="nback.d_prime"),
        _row("Median response time", nback_values[1], "ms", "Describes correct-response speed and must be interpreted with d-prime, omissions, and false alarms.", nback_qc, metric="nback.median_rt_ms", digits=0),
        _row(nback_p3_name, nback_values[2], "µV", nback_p3_description, nback_qc, metric="eeg.nback_p3_diff_uv"),
        _row("Frontal theta condition difference", nback_values[3], "dB", "A positive value indicates increased frontal theta activity under higher load.", nback_qc, metric="eeg.frontal_theta_diff_db"),
        _row("PFC HbO beta", nback_values[4], "µM", "A positive value indicates higher prefrontal oxygenation during the task relative to baseline.", nback_qc, metric="fnirs.nback_hbo_beta_um"),
    ], nback_qc, "w-67", "Analyzable results were obtained for the working-memory task."))

    vft_values = [_get(features, "fnirs.vft_left_pfc_hbo_beta_um"),
                  _get(features, "fnirs.vft_right_pfc_hbo_beta_um"),
                  _get(features, "fnirs.vft_hbo_delta_um"), _get(features, "vft.valid_words"),
                  _get(features, "eeg.vft_frontal_theta_change_db")]
    vft_qc = _qc_status(package, "vft", any(v is not None for v in vft_values))
    modules.append(_module("vft", "Language / Executive Function · VFT", "Examines lexical retrieval, executive control, and prefrontal oxygenation response.", [
        _row("Left PFC HbO beta", vft_values[0], "µM", "Describes the direction of left-prefrontal oxygenation response during lexical retrieval.", vft_qc, metric="fnirs.vft_left_pfc_hbo_beta_um"),
        _row("Right PFC HbO beta", vft_values[1], "µM", "Describes the direction of right-prefrontal oxygenation response during lexical retrieval.", vft_qc, metric="fnirs.vft_right_pfc_hbo_beta_um"),
        _row("PFC HbO task-minus-rest", vft_values[2], "µM", "A positive value indicates higher oxygenation during the task than during the resting phase in this session.", vft_qc, metric="fnirs.vft_hbo_delta_um"),
        _row("Valid word count", vft_values[3], "", "Reflects lexical-retrieval output in this session; interpretation still requires age- and education-matched norms.", vft_qc, metric="vft.valid_words", digits=0),
        _row("Frontal theta task-segment change", vft_values[4], "dB", "Compares the VFT segment between markers 3 and 4 with an equal-length pre-task baseline; a positive value indicates increased frontal theta power during the task.", vft_qc,
             metric="eeg.vft_frontal_theta_change_db"),
    ], vft_qc, "w-33", "The language/executive task was completed and the prefrontal response was recorded."))

    emotion_lpp = _get(features, "eeg.emotion_lpp_neg_neu_uv")
    emotion_lpp_name = "LPP negative-minus-neutral"
    emotion_lpp_description = "A positive value indicates a larger sustained EEG response to negative than neutral stimuli."
    if emotion_lpp is None:
        emotion_lpp = _get(features, "eeg.emotion_target_face_lpp_uv")
        emotion_lpp_name = "Target-face-locked LPP"
        emotion_lpp_description = "Centroparietal mean potential 300–800 ms after target-face onset (marker 7). Because the marker does not distinguish positive, neutral, and negative conditions, it is not interpreted as a negative-minus-neutral contrast."
    emotion_values = [emotion_lpp, _get(features, "fnirs.emotion_hbo_neg_neu_um"),
                      _get(features, "emotion.valence_diff"), _get(features, "emotion.arousal_mean")]
    emotion_qc = _qc_status(package, "emotion", any(v is not None for v in emotion_values))
    modules.append(_module("emotion", "Emotion Processing · Emotion", "Compares subjective ratings, EEG, and oxygenation responses across emotion conditions.", [
        _row(emotion_lpp_name, emotion_values[0], "µV", emotion_lpp_description, emotion_qc, metric="eeg.emotion_lpp_neg_neu_uv"),
        _row("HbO negative-minus-neutral", emotion_values[1], "µM", "A positive value indicates a higher oxygenation response in the negative than neutral condition.", emotion_qc, metric="fnirs.emotion_hbo_neg_neu_um"),
        _row("Subjective valence difference", emotion_values[2], "", "A negative value indicates that negative stimuli were rated as less pleasant than neutral stimuli.", emotion_qc, metric="emotion.valence_diff"),
        _row("Mean arousal rating", emotion_values[3], "", "Derived from the participant's 1–5 arousal ratings.", emotion_qc, metric="emotion.arousal_mean"),
    ], emotion_qc, "w-50", "Analyzable results were obtained for the emotion task."))

    interview_values = [_get(features, "fnirs.interview_left_probe_hbo_response"),
                        _get(features, "fnirs.interview_right_probe_hbo_response"),
                        _get(features, "fnirs.interview_left_right_hbo_difference"),
                        _get(features, "fnirs.interview_hbr_response"),
                        _get(features, "fnirs.interview_post_task_recovery"),
                        _get(features, "fnirs.interview_valid_blocks"),
                        _get(features, "fnirs.interview_usable_channels")]
    interview_qc = _qc_status(package, "interview", any(v is not None for v in interview_values))
    modules.append(_module("interview", "Interactive Interview", "Compares fNIRS oxygenation during the interview with the preceding resting phase.", [
        _row("Left-probe HbO response", interview_values[0], "relative", "Left-probe HbO change during the interview relative to the preceding rest period.", interview_qc, metric="fnirs.interview_left_probe_hbo_response", digits=5),
        _row("Right-probe HbO response", interview_values[1], "relative", "Right-probe HbO change during the interview relative to the preceding rest period.", interview_qc, metric="fnirs.interview_right_probe_hbo_response", digits=5),
        _row("Left-minus-right probe HbO", interview_values[2], "relative", "Describes the probe-level difference in this session only and does not infer a regional brain diagnosis.", interview_qc, metric="fnirs.interview_left_right_hbo_difference", digits=5),
        _row("Overall HbR response", interview_values[3], "relative", "HbR change during the interview relative to the preceding rest period.", interview_qc, metric="fnirs.interview_hbr_response", digits=5),
        _row("Late-interview HbO change", interview_values[4], "relative", "HbO difference in the late interview recording relative to the pre-task baseline; it does not represent recovery after the entire experiment.", interview_qc, metric="fnirs.interview_post_task_recovery", digits=5),
        _row("Valid blocks", interview_values[5], "/30", "Interview blocks passing timing and signal-quality control.", interview_qc,
             metric="fnirs.interview_valid_blocks", digits=0),
        _row("Usable channels", interview_values[6], "/20", "Number of channels passing optical signal-quality screening.", interview_qc,
             metric="fnirs.interview_usable_channels", digits=0),
    ], interview_qc, "w-50", "Automated analysis of the interview-period fNIRS measures is complete."))

    completed = sum(module["qc"] not in {"DATA PENDING", "FAIL"} for module in modules)
    dq = package.get("data_quality") or {}
    overall_qc = "PASS" if str(dq.get("band", "")).upper() in {"GOOD", "ACCEPTABLE", "PASS"} else "WARN"
    if simulated:
        overall_qc = "WARN"
    confidence = (profile or {}).get("confidence_overall", {}).get("label", "Low")
    available = [module["title"].split(" · ")[-1] for module in modules
                 if module["qc"] not in {"DATA PENDING", "FAIL"}]
    pending = [module["title"].split(" · ")[-1] for module in modules if module["qc"] in {"DATA PENDING", "FAIL"}]
    summary = f"Analyzable results obtained: {', '.join(available)}." if available else "No reviewed multimodal result is currently available."
    if pending:
        summary += f" Pending or failed QC: {', '.join(pending)}."
    return {
        "report_version": "2.7", "stage": stage,
        "participant_id": str(package.get("participant_id", "—")),
        "session_id": str(package.get("session_id", "—")),
        "date": datetime.now().strftime("%Y-%m-%d"), "overall_qc": overall_qc,
        "completion_percent": round(completed / len(modules) * 100) if modules else 0,
        "completed_modules": completed, "total_modules": len(modules),
        "confidence": confidence, "modules": modules,
        "clinical_module": _clinical_module(package, features), "overall_summary": summary,
        "recording_inventory": _recording_inventory(package),
        "quality_rows": _quality_rows(package),
        "preprocessing_methods": methodology.get("preprocessing", []),
        "modeling_status": modeling_status,
        "interpretation_basis": interpretation_config()["disclaimer"],
        "evidence_references": interpretation_config().get("references", []),
        "notice": ("Software simulation validation report: the data are synthetic and must not be used as a real participant result, research conclusion, or clinical judgment. "
                   if simulated else "")
                  + "This report presents numeric result → current status → brief meaning. Status descriptions apply only to the current research task and are not equivalent to a clinical diagnosis or long-term ability assessment.",
        "method_version": "bplus-report-0.3.0 / BPLUS-DESCRIPTIVE-STATE-1",
    }


def _quality_rows(package: dict[str, Any]) -> list[dict[str, str]]:
    dq = package.get("data_quality") or {}
    rows = [{"name": "Overall data-quality score", "value": _display(dq.get("score"), "", 1),
             "state": dq.get("band") or dq.get("band_zh") or "Insufficient data",
             "description": "Summarizes data completeness and quality-control results for this session."}]
    components = dq.get("components") or {}
    for name, value in components.items():
        if isinstance(value, (list, tuple)):
            display = ", ".join(str(item) for item in value) if value else "None"
        elif isinstance(value, dict):
            display = ", ".join(f"{key}={item}" for key, item in value.items())
        else:
            display = str(value)
        rows.append({"name": name, "value": display, "state": "PASS" if value not in (None, False, 0, [], {}) else "WARN",
                     "description": "From the automated quality-control record."})
    return rows


def _recording_inventory(package: dict[str, Any]) -> list[dict[str, str]]:
    analysis = package.get("analysis") or {}
    rows = []
    for item in analysis.get("eeg_recordings", []):
        source = Path(str(item.get("header", ""))).name
        repair = item.get("derived_filename_repair") or {}
        role = "Resting-state candidate (filename repaired)" if repair else "Continuous EEG (task label awaiting alignment)"
        rows.append({"modality": "EEG", "record": source,
                     "protocol": f"{item.get('sampling_rate_hz', '—')} Hz",
                     "duration": f"{float(item.get('duration_s', 0)):.1f} s",
                     "qc": str(item.get("status", "UNKNOWN")), "role": role})
    for item in analysis.get("fnirs_recordings", []):
        protocol = Path(str(item.get("protocol") or "Unknown")).name
        rows.append({"modality": "fNIRS", "record": str(item.get("session", "—")),
                     "protocol": protocol, "duration": f"{float(item.get('duration_s', 0)):.1f} s",
                     "qc": str(item.get("qc", "UNKNOWN")),
                     "role": "Interview" if item.get("task_label") == "interview" else "Unnamed task segment (read successfully; mapping pending)"})
    for item in analysis.get("eeg_bundle_errors", []):
        rows.append({"modality": "EEG", "record": Path(str(item.get("file", ""))).name,
                     "protocol": "—", "duration": "—", "qc": "REJECTED",
                     "role": str(item.get("error", "Could not parse"))})
    for item in analysis.get("fnirs_bundle_errors", []):
        rows.append({"modality": "fNIRS", "record": str(item.get("session", "—")),
                     "protocol": "—", "duration": "—", "qc": "REJECTED",
                     "role": str(item.get("error", "Could not parse"))})
    return rows


def render_v27_html(payload: dict[str, Any]) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]),
                      undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)
    return env.get_template("participant_report_v2_7.html.j2").render(report=payload)


__all__ = ["build_report_payload", "render_v27_html"]
