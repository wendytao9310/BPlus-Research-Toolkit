"""Safely combine modality analysis packages for one participant/session."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .behavior import TrialResponse, evaluate_nback, summarize


MODALITIES = ("eeg", "fnirs", "eye", "behavior", "physiology", "clinical")
FEATURE_GROUPS = ("eeg", "rest", "fnirs", "vft", "nback", "nvc", "emotion", "recovery",
                  "eye", "physiology", "clinical")
STATUS_RANK = {"MISSING": 0, "SIMULATED": 1, "PILOT": 2, "VERIFIED": 3}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nonempty(value: Any) -> bool:
    return value not in (None, "", [], {})


def _merge_dict(target: dict[str, Any], incoming: dict[str, Any], *, context: str) -> None:
    """Merge without silently replacing two different measured values."""
    for key, value in incoming.items():
        if not _nonempty(value):
            continue
        if key not in target or not _nonempty(target[key]):
            target[key] = copy.deepcopy(value)
        elif isinstance(target[key], dict) and isinstance(value, dict):
            _merge_dict(target[key], value, context=f"{context}.{key}")
        elif target[key] != value:
            raise ValueError(f"同一被试存在冲突指标：{context}.{key}；请核对来源后再合并")


def load_analysis_packages(paths: Iterable[str | Path], *, participant_id: str,
                           session_id: str) -> list[tuple[Path, dict[str, Any]]]:
    loaded = []
    expected = (str(participant_id).strip(), str(session_id).strip())
    if not all(expected):
        raise ValueError("被试编号和会话编号不能为空")
    for item in paths:
        path = Path(item)
        package = json.loads(path.read_text(encoding="utf-8"))
        if not {"participant_id", "session_id", "features", "sources"}.issubset(package):
            continue
        actual = (str(package["participant_id"]).strip(), str(package["session_id"]).strip())
        if actual != expected:
            raise ValueError(
                f"禁止跨被试/会话合并：期望 sub-{expected[0]} ses-{expected[1]}，"
                f"但 {path.name} 内记录为 sub-{actual[0]} ses-{actual[1]}")
        loaded.append((path, package))
    if not loaded:
        raise ValueError("没有找到可识别的 BPlus 分析包")
    return loaded


def discover_analysis_packages(analysis_root: str | Path, *, participant_id: str,
                               session_id: str) -> list[Path]:
    """Discover by internal identity; filename alone is never trusted."""
    matches = []
    for path in Path(analysis_root).rglob("*.json"):
        if path.name == "integrated_analysis_package.json" or "integrated" in path.parts:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(data, dict) or "features" not in data or "sources" not in data:
            continue
        if (str(data.get("participant_id", "")).strip() == str(participant_id).strip() and
                str(data.get("session_id", "")).strip() == str(session_id).strip()):
            matches.append(path)
    return sorted(matches)


def build_behavior_analysis_package(session_root: str | Path, *, participant_id: str,
                                    session_id: str, age: int | None = None) -> dict[str, Any] | None:
    """Convert this participant's native task logs into report-ready features."""
    root = Path(session_root)
    files = sorted(root.rglob(f"sub-{participant_id}_ses-{session_id}_*_behavior.csv"))
    exported = sorted(root.rglob(f"sub-{participant_id}_ses-{session_id}_behavior_trials.csv"))
    # The publication export is a normalized long table and is a valid input to
    # unified analysis. Prefer it when the selected folder does not contain the
    # native per-task logs; never count both copies of the same trials.
    if not files and exported:
        files = [exported[0]]
    if not files:
        return None
    features: dict[str, Any] = {key: {} for key in FEATURE_GROUPS}
    analysis: dict[str, Any] = {}
    source_files = []
    nback_trials: list[TrialResponse] = []
    valence, arousal = [], []
    valence_by_condition: dict[str, list[float]] = {}
    for path in files:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        native_task = path.name.rsplit("_", 2)[-2]
        for index, row in enumerate(rows, 1):
            task = str(row.get("task") or native_task).strip().lower()
            practice = str(row.get("practice", "")).strip().lower()
            if practice in {"1", "true", "yes"}:
                continue
            is_target = str(row.get("is_target", "")).strip().lower()
            if task == "nback" and is_target in {"0", "1", "true", "false"}:
                response = str(row.get("responded", row.get("response_given", ""))).strip().lower()
                rt = row.get("rt_ms", row.get("response_time_ms", ""))
                nback_trials.append(TrialResponse(
                    trial_id=index, condition=str(row.get("condition", "")),
                    is_target=is_target in {"1", "true"}, responded=response in {"1", "true", "yes"},
                    key=str(row.get("key", row.get("response_key", ""))),
                    rt_ms=float(rt) if rt else None))
            if task == "emotion":
                for key, output in (("valence", valence), ("arousal", arousal)):
                    try:
                        value = float(row[key])
                        output.append(value)
                        if key == "valence":
                            condition = str(row.get("condition", "")).strip().lower()
                            valence_by_condition.setdefault(condition, []).append(value)
                    except (KeyError, TypeError, ValueError):
                        pass
        source_files.append({"path": str(path.resolve()), "sha256": _sha256(path)})
    if nback_trials:
        evaluate_nback(nback_trials)
        metrics = summarize(nback_trials)
        features["nback"] = {key: metrics[key] for key in
                             ("d_prime", "accuracy", "hit_rate", "false_alarm_rate", "mean_rt_ms",
                              "median_rt_ms") if metrics.get(key) is not None}
        if metrics.get("n_targets"):
            features["nback"]["omission_rate"] = metrics["omissions"] / metrics["n_targets"]
        analysis["nback"] = {"qc": {"status": "PASS", "n_trials": len(nback_trials)}}
    if valence or arousal:
        if valence:
            features["emotion"]["valence_mean"] = sum(valence) / len(valence)
            negative = valence_by_condition.get("negative", [])
            neutral = valence_by_condition.get("neutral", [])
            if negative and neutral:
                features["emotion"]["valence_diff"] = (
                    sum(negative) / len(negative) - sum(neutral) / len(neutral))
        if arousal:
            features["emotion"]["arousal_mean"] = sum(arousal) / len(arousal)
        analysis["emotion"] = {"qc": {"status": "PASS", "n_ratings": min(len(valence), len(arousal))}}
    return {
        "workflow_schema": "BPLUS-ANALYSIS-1", "participant_id": participant_id,
        "session_id": session_id, "age": age,
        "sources": {**{name: {"status": "MISSING"} for name in MODALITIES},
                    "behavior": {"status": "VERIFIED", "format": "BPlus task behavior CSV",
                                 "files": source_files}},
        "data_quality": {"score": 100.0, "band": "ACCEPTABLE", "band_zh": "可接受",
                         "components": {"behavior_files": len(files)}, "notes": []},
        "features": features, "analysis": analysis,
        "review": {"decision": "PENDING", "reviewer": "", "note": ""},
    }


def write_behavior_analysis_package(package: dict[str, Any], output_root: str | Path) -> Path:
    output = (Path(output_root) / f"sub-{package['participant_id']}_ses-{package['session_id']}" /
              "behavior_analysis_package.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def merge_analysis_packages(paths: Iterable[str | Path], *, participant_id: str,
                            session_id: str, reviewer: str, age: int | None = None,
                            note: str = "") -> dict[str, Any]:
    packages = load_analysis_packages(paths, participant_id=participant_id, session_id=session_id)
    if not reviewer.strip():
        raise ValueError("生成综合报告前必须填写研究者/审核人")
    merged_features = {key: {} for key in FEATURE_GROUPS}
    merged_sources = {key: {"status": "MISSING"} for key in MODALITIES}
    merged_analysis: dict[str, Any] = {}
    scores, notes, source_records = [], [], []
    resolved_age = age

    for path, package in packages:
        package_age = package.get("age")
        if resolved_age is None and package_age is not None:
            resolved_age = int(package_age)
        elif package_age is not None and resolved_age is not None and int(package_age) != resolved_age:
            raise ValueError(f"同一被试年龄记录冲突：{resolved_age} 与 {package_age}")
        for group, values in (package.get("features") or {}).items():
            if isinstance(values, dict):
                merged_features.setdefault(group, {})
                _merge_dict(merged_features[group], values, context=f"features.{group}")
        for modality, source in (package.get("sources") or {}).items():
            if not isinstance(source, dict):
                continue
            status = str(source.get("status", "MISSING")).upper()
            current = str(merged_sources.get(modality, {}).get("status", "MISSING")).upper()
            if STATUS_RANK.get(status, -1) > STATUS_RANK.get(current, -1):
                merged_sources[modality] = copy.deepcopy(source)
        for key, value in (package.get("analysis") or {}).items():
            if key not in merged_analysis:
                merged_analysis[key] = copy.deepcopy(value)
            elif merged_analysis[key] != value:
                merged_analysis[f"{key}_{len(merged_analysis) + 1}"] = copy.deepcopy(value)
        dq = package.get("data_quality") or {}
        if dq.get("score") is not None:
            scores.append(float(dq["score"]))
        notes.extend(str(item) for item in dq.get("notes", []) if item)
        source_records.append({"path": str(path.resolve()), "sha256": _sha256(path),
                               "review": package.get("review")})

    present = [name for name in MODALITIES
               if merged_sources.get(name, {}).get("status", "MISSING").upper() != "MISSING"]
    missing = [name for name in MODALITIES if name not in present]
    score = round(sum(scores) / len(scores), 2) if scores else 0.0
    simulated = any(merged_sources[name].get("status", "").upper() == "SIMULATED" for name in present)
    band = "ACCEPTABLE" if present and score >= 60 and not simulated else "INCOMPLETE"
    band_zh = "可接受" if band == "ACCEPTABLE" else "数据不完整"
    if missing:
        notes.append("尚未导入的模态：" + "、".join(missing))
    if simulated:
        notes.append("综合包包含模拟数据，仅可用于软件验证，不得作为真实被试结论")
    now = datetime.now(timezone.utc).isoformat()
    return {
        "workflow_schema": "BPLUS-INTEGRATED-1",
        "participant_id": str(participant_id).strip(), "session_id": str(session_id).strip(),
        "age": resolved_age, "sources": merged_sources,
        "data_quality": {"score": score, "band": band, "band_zh": band_zh,
                         "components": {"present_modalities": present, "missing_modalities": missing,
                                        "source_package_count": len(packages)},
                         "notes": list(dict.fromkeys(notes))},
        "features": merged_features, "analysis": merged_analysis,
        "source_packages": source_records,
        "review": {"decision": "APPROVED", "reviewer": reviewer.strip(),
                   "note": note.strip() or "审核人核对被试编号、会话编号、来源与质控后批准归并",
                   "reviewed_at": now},
    }


def write_integrated_package(package: dict[str, Any], output_root: str | Path) -> Path:
    output = (Path(output_root) / f"sub-{package['participant_id']}_ses-{package['session_id']}" /
              "integrated_analysis_package.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


__all__ = ["build_behavior_analysis_package", "discover_analysis_packages", "load_analysis_packages",
           "merge_analysis_packages", "write_behavior_analysis_package", "write_integrated_package"]
