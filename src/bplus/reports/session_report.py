"""Generate a transparent post-session report from recorded behavior CSV files."""
from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path

from .v27 import build_report_payload, render_v27_html


PARADIGM_LABELS = {
    "rest": "Resting-state baseline",
    "mmn": "Auditory MMN",
    "vft": "Verbal Fluency Task",
    "nback": "N-back working memory",
    "emotion": "Emotion image task",
    "recovery": "Post-task recovery",
}


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _number(value: str | None) -> float | None:
    try:
        number = float(value or "")
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _nback_summary(rows: list[dict[str, str]]) -> dict[str, str]:
    scored = [row for row in rows if row.get("practice") != "1" and row.get("is_target") in {"0", "1"}]
    targets = [row for row in scored if row["is_target"] == "1"]
    nontargets = [row for row in scored if row["is_target"] == "0"]
    hits = sum(row.get("key") == "return" for row in targets)
    false_alarms = sum(row.get("key") == "return" for row in nontargets)
    correct = hits + len(nontargets) - false_alarms
    correct_rts = [_number(row.get("rt_ms")) for row in targets if row.get("key") == "return"]
    rts = [value for value in correct_rts if value is not None]
    return {
        "main_trials": str(len(scored)),
        "overall_accuracy": f"{correct / len(scored) * 100:.1f}%" if scored else "No data",
        "target_hits": f"{hits}/{len(targets)}" if targets else "No data",
        "omissions": str(len(targets) - hits),
        "false_alarms": str(false_alarms),
        "median_hit_rt": f"{statistics.median(rts):.0f} ms" if rts else "No data",
    }


def _emotion_summary(rows: list[dict[str, str]]) -> dict[str, str]:
    valence = [_number(row.get("valence")) for row in rows]
    arousal = [_number(row.get("arousal")) for row in rows]
    valence = [value for value in valence if value is not None]
    arousal = [value for value in arousal if value is not None]
    return {
        "completed_rating_blocks": str(min(len(valence), len(arousal))),
        "mean_pleasantness_1_5": f"{statistics.fmean(valence):.2f}" if valence else "No data",
        "mean_arousal_1_5": f"{statistics.fmean(arousal):.2f}" if arousal else "No data",
    }


def generate_session_report(session_dir: str | Path, report_dir: str | Path, *, participant_id: str,
                            session_id: str, paradigms: list[str], age: int | None = None) -> Path:
    """Create the v2.7 pending-analysis report from actually recorded behavior."""
    session_root, output_root = Path(session_dir), Path(report_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    records: dict[str, tuple[Path | None, list[dict[str, str]]]] = {}
    for paradigm in paradigms:
        path = session_root / f"sub-{participant_id}_ses-{session_id}_{paradigm}_behavior.csv"
        records[paradigm] = (path if path.exists() else None, _read_rows(path) if path.exists() else [])

    completed = sum(path is not None for path, _ in records.values())
    features: dict = {"nback": {}, "emotion": {}, "eeg": {}, "fnirs": {}, "vft": {},
                      "recovery": {}, "eye": {}, "physiology": {}, "clinical": {}}
    analysis: dict = {}
    nback_path, nback_rows = records.get("nback", (None, []))
    if nback_path:
        summary = _nback_summary(nback_rows)
        features["nback"] = {
            "accuracy": float(summary["overall_accuracy"].rstrip("%")) / 100,
            "median_rt_ms": _number(summary["median_hit_rt"].replace(" ms", "")),
        }
        analysis["nback"] = {"qc": {"status": "PASS"}}

    emotion_path, emotion_rows = records.get("emotion", (None, []))
    if emotion_path:
        emotion = _emotion_summary(emotion_rows)
        features["emotion"] = {
            "valence_mean": _number(emotion["mean_pleasantness_1_5"]),
            "arousal_mean": _number(emotion["mean_arousal_1_5"]),
        }
        analysis["emotion"] = {"qc": {"status": "PASS"}}

    completion = completed / len(paradigms) if paradigms else 0
    package = {"participant_id": participant_id, "session_id": session_id, "age": age,
               "features": features,
               "sources": {"behavior": {"status": "VERIFIED"}}, "analysis": analysis,
               "data_quality": {"score": round(completion * 100, 1),
                                "band": "INCOMPLETE", "band_zh": "Multimodal analysis pending",
                                "notes": ["This report currently contains behavioral records only; physiological data still require processing and review"]}}
    payload = build_report_payload(package, stage="PENDING_ANALYSIS")
    payload["completion_percent"] = round(completion * 100)
    payload["confidence"] = "Low"
    payload["overall_qc"] = "WARN"
    payload["overall_summary"] = (f"Behavioral records were generated for {completed}/{len(paradigms)} selected paradigms. "
                                  "EEG, fNIRS, eye-tracking, and physiological measures require analysis, QC, and researcher review before updating.")
    if nback_path:
        summary = _nback_summary(nback_rows)
        module = next(item for item in payload["modules"] if item["key"] == "nback")
        module["rows"].insert(0, {"name": "Overall accuracy", "display_value": summary["overall_accuracy"],
                                  "state": "Result recorded", "state_class": "state-response",
                                  "description": f"Target hits {summary['target_hits']}; main trials only."})
    html = render_v27_html(payload)
    output = output_root / f"sub-{participant_id}_ses-{session_id}_report.html"
    output.write_text(html, encoding="utf-8")
    output.with_name(f"sub-{participant_id}_ses-{session_id}_report_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = {"participant_id": participant_id, "session_id": session_id, "age": age}
    (session_root / f"sub-{participant_id}_ses-{session_id}_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
