"""Publication-oriented export of BPlus computerized task behavior data.

Raw session CSV files remain untouched. Exports contain a harmonized long
table, BIDS-compatible events TSV files, summary statistics, a data dictionary,
quality flags and a SHA-256 provenance manifest.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import statistics
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .behavior import TrialResponse, evaluate_nback, summarize

SCHEMA_VERSION = "BPLUS-BEHAVIOR-1.0"
RAW_PATTERN = re.compile(r"^sub-(?P<participant>.+)_ses-(?P<session>.+)_(?P<task>[^_]+)_behavior\.csv$")
LONG_COLUMNS = [
    "participant_id", "session_id", "task", "trial_index", "block_id", "condition",
    "trial_type", "event_code", "onset_s", "duration_s", "stimulus", "is_target",
    "expected_response", "response_given", "response_key", "response_time_ms",
    "correct", "outcome", "valence", "arousal", "practice", "source_file",
]
BIDS_COLUMNS = [
    "onset", "duration", "trial_type", "value", "stim_file", "block", "trial_index",
    "is_target", "expected_response", "response", "response_time", "correct",
    "outcome", "valence", "arousal", "practice",
]


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _blank(value: Any, *, bids: bool = False) -> str:
    if value in (None, ""):
        return "n/a" if bids else ""
    return str(value)


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    return str(value).strip().lower() in {"1", "true", "yes"}


def _duration(task: str, row: dict[str, str]) -> float:
    code = str(row.get("code", ""))
    if task == "mmn":
        return 0.1
    if task == "nback":
        return 0.5
    if task == "emotion":
        return 6.0 if code == "411" else 3.0
    if task == "vft":
        return 15.0
    if task == "rest":
        return 180.0
    if task == "recovery":
        return 180.0
    return 0.0


def _outcome(task: str, is_target: bool | None, responded: bool, correct: bool | None,
             key: str) -> str:
    if task != "nback" or is_target is None:
        if correct is True:
            return "correct"
        if correct is False:
            return "incorrect"
        return "response" if responded else "no_response_required"
    pressed_target = responded and key in {"return", "enter"}
    if is_target and pressed_target:
        return "hit"
    if is_target and not pressed_target:
        return "miss"
    if not is_target and pressed_target:
        return "false_alarm"
    return "correct_rejection"


def _harmonize(path: Path) -> list[dict[str, Any]]:
    match = RAW_PATTERN.match(path.name)
    if not match:
        raise ValueError(f"无法识别行为文件名：{path.name}")
    rows = _read(path)
    task = match.group("task")
    output = []
    for position, row in enumerate(rows, 1):
        is_target = _bool(row.get("is_target"))
        responded = bool(_bool(row.get("responded")))
        correct = _bool(row.get("correct"))
        key = row.get("key", "")
        output.append({
            "participant_id": row.get("participant_id") or match.group("participant"),
            "session_id": row.get("session_id") or match.group("session"),
            "task": row.get("paradigm") or task,
            "trial_index": row.get("trial_index") or position,
            "block_id": row.get("block_id", ""), "condition": row.get("condition", ""),
            "trial_type": row.get("condition") or task, "event_code": row.get("code", ""),
            "onset_s": row.get("onset_s", ""), "duration_s": _duration(task, row),
            "stimulus": row.get("stim", ""), "is_target": is_target,
            "expected_response": row.get("expected_key", ""), "response_given": responded,
            "response_key": key, "response_time_ms": row.get("rt_ms", ""),
            "correct": correct, "outcome": _outcome(task, is_target, responded, correct, key),
            "valence": row.get("valence", ""), "arousal": row.get("arousal", ""),
            "practice": bool(_bool(row.get("practice"))), "source_file": path.name,
        })
    return output


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=BIDS_COLUMNS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            rt = _float(row["response_time_ms"])
            writer.writerow({
                "onset": _blank(row["onset_s"], bids=True),
                "duration": f"{float(row['duration_s']):.3f}", "trial_type": _blank(row["trial_type"], bids=True),
                "value": _blank(row["event_code"], bids=True), "stim_file": _blank(row["stimulus"], bids=True),
                "block": _blank(row["block_id"], bids=True), "trial_index": _blank(row["trial_index"], bids=True),
                "is_target": _blank(int(row["is_target"]) if row["is_target"] is not None else None, bids=True),
                "expected_response": _blank(row["expected_response"], bids=True),
                "response": _blank(row["response_key"], bids=True),
                "response_time": _blank(f"{rt / 1000.0:.6f}" if rt is not None else None, bids=True),
                "correct": _blank(int(row["correct"]) if row["correct"] is not None else None, bids=True),
                "outcome": row["outcome"], "valence": _blank(row["valence"], bids=True),
                "arousal": _blank(row["arousal"], bids=True), "practice": int(row["practice"]),
            })


def _summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["task"], row["condition"] or "all")].append(row)
    output = []
    for (task, condition), items in sorted(groups.items()):
        valid = [item for item in items if not item["practice"]]
        if task == "nback":
            # Cue/instruction rows remain in events.tsv for synchronization but
            # are not behavioral trials and must never enter performance stats.
            valid = [item for item in valid if item["is_target"] is not None]
        if not valid:
            continue
        rts = [_float(item["response_time_ms"]) for item in valid]
        rts = [value for value in rts if value is not None and value > 0]
        correct_values = [item["correct"] for item in valid if item["correct"] is not None]
        record = {"participant_id": valid[0]["participant_id"] if valid else "",
                  "session_id": valid[0]["session_id"] if valid else "",
                  "task": task, "condition": condition, "n_trials": len(valid),
                  "n_responses": sum(bool(item["response_given"]) for item in valid),
                  "accuracy": (sum(correct_values) / len(correct_values)) if correct_values else "",
                  "mean_rt_ms": statistics.fmean(rts) if rts else "",
                  "median_rt_ms": statistics.median(rts) if rts else "",
                  "rt_sd_ms": statistics.stdev(rts) if len(rts) > 1 else "",
                  "valence_mean": "", "arousal_mean": "", "d_prime": "",
                  "hit_rate": "", "false_alarm_rate": "", "omission_rate": ""}
        valence = [_float(item["valence"]) for item in valid]
        arousal = [_float(item["arousal"]) for item in valid]
        valence = [value for value in valence if value is not None]
        arousal = [value for value in arousal if value is not None]
        if valence:
            record["valence_mean"] = statistics.fmean(valence)
        if arousal:
            record["arousal_mean"] = statistics.fmean(arousal)
        if task == "nback":
            responses = [TrialResponse(trial_id=index, condition=str(item["condition"]),
                                       is_target=item["is_target"], responded=bool(item["response_given"]),
                                       key=str(item["response_key"] or ""), rt_ms=_float(item["response_time_ms"]))
                         for index, item in enumerate(valid, 1)]
            evaluate_nback(responses)
            metrics = summarize(responses)
            finite_or_blank = lambda value: value if isinstance(value, (int, float)) and math.isfinite(value) else ""
            record.update({"accuracy": finite_or_blank(metrics["accuracy"]),
                           "mean_rt_ms": finite_or_blank(metrics["mean_rt_ms"]),
                           "median_rt_ms": finite_or_blank(metrics["median_rt_ms"]),
                           "d_prime": finite_or_blank(metrics["d_prime"]),
                           "hit_rate": finite_or_blank(metrics["hit_rate"]),
                           "false_alarm_rate": finite_or_blank(metrics["false_alarm_rate"]),
                           "omission_rate": metrics["omissions"] / metrics["n_targets"]
                           if metrics["n_targets"] else ""})
        output.append(record)
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dictionary() -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "missing_value": {"CSV": "empty", "BIDS_TSV": "n/a"},
        "columns": {
            "participant_id": "匿名研究编号", "session_id": "会话编号", "task": "实验范式",
            "trial_index": "范式内试次序号", "block_id": "任务块编号", "condition": "实验条件",
            "trial_type": "BIDS 事件类型", "event_code": "刺激/触发码", "onset_s": "相对会话开始的事件起点（秒）",
            "duration_s": "事件持续时间（秒）", "stimulus": "刺激标识或相对路径", "is_target": "是否目标试次",
            "expected_response": "预期按键", "response_given": "是否作答", "response_key": "实际按键",
            "response_time_ms": "反应时（毫秒）", "correct": "正确性", "outcome": "hit/miss/false_alarm/correct_rejection 等",
            "valence": "效价评分 1–5", "arousal": "唤醒评分 1–5", "practice": "是否练习试次",
        },
        "analysis_notes": [
            "正式分析应预先定义反应时剔除规则，并报告剔除数量。",
            "N-back 建议联合报告 d-prime、准确率、命中率、误报率、遗漏率和反应时。",
            "MMN、Rest、Recovery 的无按键试次不是遗漏反应。",
            "Emotion 评分按效价与唤醒分别分析；刺激级与块级设计不得混淆。",
        ],
    }


def export_behavior_session(session_dir: str | Path, output_root: str | Path, *,
                            participant_id: str, session_id: str) -> dict[str, Path]:
    source = Path(session_dir)
    files = sorted(source.glob(f"sub-{participant_id}_ses-{session_id}_*_behavior.csv"))
    if not files:
        raise FileNotFoundError(f"未找到 sub-{participant_id} ses-{session_id} 的行为记录")
    output = Path(output_root) / f"sub-{participant_id}_ses-{session_id}"
    output.mkdir(parents=True, exist_ok=True)
    all_rows = [row for path in files for row in _harmonize(path)]
    trials = output / f"sub-{participant_id}_ses-{session_id}_behavior_trials.csv"
    _write_csv(trials, all_rows, LONG_COLUMNS)
    summary_rows = _summary(all_rows)
    summary = output / f"sub-{participant_id}_ses-{session_id}_behavior_summary.csv"
    summary_columns = list(summary_rows[0]) if summary_rows else ["task", "condition"]
    _write_csv(summary, summary_rows, summary_columns)
    sidecar = output / "behavior_data_dictionary.json"
    sidecar.write_text(json.dumps(_dictionary(), ensure_ascii=False, indent=2), encoding="utf-8")
    event_paths = []
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        by_task[row["task"]].append(row)
    for task, task_rows in sorted(by_task.items()):
        events = output / f"sub-{participant_id}_ses-{session_id}_task-{task}_events.tsv"
        _write_tsv(events, task_rows); event_paths.append(events)
        metadata = output / f"task-{task}_events.json"
        metadata.write_text(json.dumps({"TaskName": task, "Columns": _dictionary()["columns"],
                                        "SchemaVersion": SCHEMA_VERSION}, ensure_ascii=False, indent=2), encoding="utf-8")
        event_paths.append(metadata)
    qc_rows = []
    for path in files:
        rows = _read(path)
        qc_rows.append({"source_file": path.name, "n_rows": len(rows),
                        "missing_onset": sum(not row.get("onset_s") for row in rows),
                        "invalid_rt": sum((_float(row.get("rt_ms")) or 0) < 0 for row in rows),
                        "sha256": _sha256(path), "status": "PASS" if rows else "FAIL"})
    qc = output / "behavior_qc.csv"
    _write_csv(qc, qc_rows, list(qc_rows[0]))
    manifest = output / "export_manifest.json"
    manifest_payload = {"schema": SCHEMA_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
                        "participant_id": participant_id, "session_id": session_id,
                        "source_files": [{"path": str(path.resolve()), "sha256": _sha256(path)} for path in files],
                        "n_trials": len(all_rows), "tasks": sorted(by_task),
                        "privacy": "De-identified research ID only; verify before external sharing."}
    manifest.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    readme = output / "README.md"
    readme.write_text("# BPlus 行为数据导出\n\n每个试次一行。CSV 用于 R/Python/SPSS；events.tsv 遵循 BIDS 事件表结构。"
                      "原始会话日志未修改。正式论文分析前请依据预注册方案确定排除规则。\n", encoding="utf-8")
    archive = output.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(output.iterdir()):
            bundle.write(path, arcname=f"{output.name}/{path.name}")
    return {"folder": output, "zip": archive, "trials": trials, "summary": summary,
            "dictionary": sidecar, "qc": qc, "manifest": manifest,
            **{f"event_{index}": path for index, path in enumerate(event_paths, 1)}}


def export_all_behavior_sessions(session_dir: str | Path, output_root: str | Path) -> dict[str, Any]:
    identities = set()
    for path in Path(session_dir).glob("sub-*_ses-*_behavior.csv"):
        match = RAW_PATTERN.match(path.name)
        if match:
            identities.add((match.group("participant"), match.group("session")))
    packages = [export_behavior_session(session_dir, output_root, participant_id=participant,
                                        session_id=session)
                for participant, session in sorted(identities)]
    cohort_rows = []
    for package in packages:
        cohort_rows.extend(_read(package["summary"]))
    cohort = Path(output_root) / "cohort_behavior_summary.csv"
    if cohort_rows:
        _write_csv(cohort, cohort_rows, list(cohort_rows[0]))
    return {"n_sessions": len(packages), "packages": packages, "cohort_summary": cohort}


__all__ = ["export_all_behavior_sessions", "export_behavior_session"]
