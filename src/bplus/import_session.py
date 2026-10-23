"""Stage complete modality folders, then analyze once into one BPlus report package."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analysis import (analyze_mmn_epochs, build_analysis_package, read_vft_scoring,
                       review_package)
from .clinical import apply_clinical_assessment
from .eeg import analyze_cgx_bundle, write_cgx_outputs
from .fnirs import ShimadzuFolderImporter, analyze_interview, build_fnirs_analysis_package
from .multimodal_merge import (build_behavior_analysis_package, merge_analysis_packages,
                               write_integrated_package)
from .reports import generate_multimodal_report


MODALITY_LABELS = {"eeg": "EEG", "fnirs": "近红外", "behavior": "行为任务",
                   "mmn_epochs": "MMN预处理结果（可选）",
                   "vft_scoring": "VFT人工计分",
                   "eye": "眼动", "physiology": "心率/生理", "clinical": "临床/心理"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_path(import_root: str | Path, participant_id: str, session_id: str) -> Path:
    return (Path(import_root) / f"sub-{participant_id}_ses-{session_id}" /
            "multimodal_import_session.json")


def load_import_session(import_root: str | Path, *, participant_id: str,
                        session_id: str) -> dict[str, Any]:
    path = manifest_path(import_root, participant_id, session_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema": "BPLUS-IMPORT-SESSION-1", "participant_id": participant_id,
            "session_id": session_id, "modalities": {}, "status": "STAGING",
            "created_at": datetime.now(timezone.utc).isoformat()}


def _inventory(folder: Path) -> dict[str, Any]:
    files = sorted(path for path in folder.rglob("*") if path.is_file())
    suffixes: dict[str, int] = {}
    for path in files:
        suffix = path.suffix.lower() or "[no_extension]"
        suffixes[suffix] = suffixes.get(suffix, 0) + 1
    return {"root": str(folder.resolve()), "file_count": len(files),
            "total_bytes": sum(path.stat().st_size for path in files), "suffix_counts": suffixes,
            "files": [{"path": str(path.resolve()), "bytes": path.stat().st_size}
                      for path in files]}


def _preflight(modality: str, inventory: dict[str, Any]) -> list[str]:
    suffixes = inventory["suffix_counts"]
    issues = []
    if modality == "eeg":
        if not suffixes.get(".vhdr"):
            issues.append("未发现 BrainVision .vhdr")
        if not suffixes.get(".eeg"):
            issues.append("未发现 BrainVision .eeg")
        if not suffixes.get(".vmrk"):
            issues.append("未发现 BrainVision .vmrk")
    elif modality == "fnirs" and not (suffixes.get(".omm") or suffixes.get(".csv") or suffixes.get(".txt")):
        issues.append("未发现可识别的 Shimadzu/通用近红外文件")
    elif modality == "behavior" and not suffixes.get(".csv"):
        issues.append("未发现行为 CSV")
    return issues


def stage_folder(import_root: str | Path, *, participant_id: str, session_id: str,
                 modality: str, folder: str | Path) -> tuple[Path, dict[str, Any]]:
    if modality not in MODALITY_LABELS:
        raise ValueError(f"不支持的数据类型：{modality}")
    source = Path(folder).resolve()
    if not source.is_dir():
        raise NotADirectoryError(f"不是文件夹：{source}")
    manifest = load_import_session(import_root, participant_id=participant_id, session_id=session_id)
    inventory = _inventory(source)
    issues = _preflight(modality, inventory)
    manifest["modalities"][modality] = {
        "label": MODALITY_LABELS[modality], "status": "STAGED_WITH_WARNINGS" if issues else "STAGED",
        "inventory": inventory, "issues": issues, "staged_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = manifest_path(import_root, participant_id, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, manifest["modalities"][modality]


def stage_file(import_root: str | Path, *, participant_id: str, session_id: str,
               modality: str, file: str | Path) -> tuple[Path, dict[str, Any]]:
    """Stage one audited supplemental file without analyzing it."""
    if modality not in {"mmn_epochs", "vft_scoring", "clinical"}:
        raise ValueError(f"不支持的补充数据类型：{modality}")
    source = Path(file).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"未找到文件：{source}")
    expected = {"mmn_epochs": ".npz", "vft_scoring": ".csv", "clinical": ".json"}[modality]
    if source.suffix.lower() != expected:
        raise ValueError(f"{MODALITY_LABELS[modality]}必须为 {expected} 文件")
    manifest = load_import_session(import_root, participant_id=participant_id, session_id=session_id)
    entry = {
        "label": MODALITY_LABELS[modality], "status": "STAGED",
        "file": {"path": str(source), "bytes": source.stat().st_size, "sha256": _sha256(source)},
        "issues": [], "staged_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest["modalities"][modality] = entry
    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = manifest_path(import_root, participant_id, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, entry


def summarize_import_session(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key in MODALITY_LABELS:
        entry = (manifest.get("modalities") or {}).get(key)
        rows.append({"modality": key, "label": MODALITY_LABELS[key],
                     "status": entry.get("status") if entry else "NOT_STAGED",
                     "file_count": (entry.get("inventory", {}).get("file_count", 0)
                                    if entry and "inventory" in entry else (1 if entry else 0)),
                     "root": (entry.get("inventory", {}).get("root", "")
                              if entry and "inventory" in entry else entry.get("file", {}).get("path", "") if entry else ""),
                     "issues": entry.get("issues", []) if entry else []})
    return rows


def run_unified_analysis(manifest_file: str | Path, *, project_root: str | Path,
                         reviewer: str, age: int | None = None) -> dict[str, Any]:
    """The single analysis seam: staged sources in, one integrated report out."""
    source_manifest = Path(manifest_file)
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    participant = str(manifest["participant_id"])
    session = str(manifest["session_id"])
    if not reviewer.strip():
        raise ValueError("统一分析前必须填写操作员/审核人")
    project = Path(project_root)
    run_root = project / "data" / "analysis" / "unified" / f"sub-{participant}_ses-{session}"
    source_packages: list[Path] = []
    modalities = manifest.get("modalities") or {}
    supplemental_mmn = None
    supplemental_vft_scoring = None
    if "mmn_epochs" in modalities:
        import numpy as np
        mmn_path = Path(modalities["mmn_epochs"]["file"]["path"])
        with np.load(mmn_path, allow_pickle=False) as data:
            standard_key = "standard_epochs_uv" if "standard_epochs_uv" in data else "standard_epochs"
            deviant_key = "deviant_epochs_uv" if "deviant_epochs_uv" in data else "deviant_epochs"
            supplemental_mmn = analyze_mmn_epochs(
                data[standard_key], data[deviant_key], data["times_ms"],
                [str(item) for item in data["channel_names"]])
        supplemental_mmn["source"] = {"path": str(mmn_path), "sha256": _sha256(mmn_path)}
    if "vft_scoring" in modalities:
        scoring_path = Path(modalities["vft_scoring"]["file"]["path"])
        supplemental_vft_scoring = read_vft_scoring(scoring_path)
        supplemental_vft_scoring["source"] = {"path": str(scoring_path), "sha256": _sha256(scoring_path)}

    if "eeg" in modalities:
        eeg_folder = modalities["eeg"]["inventory"]["root"]
        package = analyze_cgx_bundle(eeg_folder, participant_id=participant,
                                     session_id=session, age=age)
        if supplemental_mmn:
            package.setdefault("features", {}).setdefault("eeg", {}).update(
                supplemental_mmn.get("features", {}))
            package.setdefault("analysis", {})["mmn_supplement"] = supplemental_mmn
            package["data_quality"]["notes"].append(
                "MMN指标使用已暂存的预处理epoch文件；原始EEG仍保留用于来源与整体质控")
        package = review_package(package, reviewer=reviewer, decision="APPROVED",
                                 note="统一分析：审核 EEG 数据包清单、自动质控与来源")
        source_packages.append(write_cgx_outputs(package, run_root / "eeg")["package"])

    if "fnirs" in modalities:
        fnirs_folder = modalities["fnirs"]["inventory"]["root"]
        raws, fnirs_errors = ShimadzuFolderImporter(
            fnirs_folder, subject_id=participant, session_id=session).load_all()
        if not raws:
            raise ValueError("近红外数据包没有可安全解析的完整记录")
        # The 15-30-15 repeated protocol is the only currently validated
        # Interview mapping. Other sessions are parsed/QC'd and retained as
        # unlabeled task recordings rather than silently discarded.
        raw = next((item for item in raws if "15-30-15" in item.metadata.get("timepath", "")),
                   max(raws, key=lambda item: item.duration))
        result = analyze_interview(raw)
        package = build_fnirs_analysis_package(raw, result, participant_id=participant,
                                               session_id=session, age=age)
        recording_rows = []
        all_source_files = []
        for item in raws:
            item_result = analyze_interview(item)
            recording_rows.append({
                "session": item.source_files["omm"].stem,
                "protocol": item.metadata.get("timepath"), "duration_s": item.duration,
                "blocks": len(item.blocks), "valid_blocks": item.qc["task"]["valid_blocks"],
                "usable_channels": item.qc["channels"]["usable"], "qc": item.qc["status"],
                "task_label": "interview" if item is raw else "UNLABELED_TASK",
                "descriptive_analysis": item_result,
            })
            for source_path in item.source_files.values():
                all_source_files.append({"path": str(source_path.resolve()),
                                         "sha256": _sha256(source_path),
                                         "bytes": source_path.stat().st_size})
        package["sources"]["fnirs"].update({"root": str(Path(fnirs_folder).resolve()),
                                              "files": all_source_files})
        package["analysis"]["fnirs_recordings"] = recording_rows
        package["analysis"]["fnirs_bundle_errors"] = fnirs_errors
        package["data_quality"]["components"]["fnirs_sessions_analyzed"] = len(raws)
        package["data_quality"]["components"]["fnirs_sessions_rejected"] = len(fnirs_errors)
        package["data_quality"]["notes"].append(
            f"近红外整包共分析 {len(raws)} 段记录；其中未命名任务段仅作描述性保留")
        if fnirs_errors:
            package["data_quality"]["notes"].append("近红外未纳入记录：" + "；".join(
                f"{item['session']}（{item['error']}）" for item in fnirs_errors))
        package = review_package(package, reviewer=reviewer, decision="APPROVED",
                                 note="统一分析：审核近红外数据包清单、自动质控与任务切段")
        path = run_root / "fnirs" / "fnirs_analysis_package.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
        source_packages.append(path)

    behavior_root = (modalities.get("behavior") or {}).get("inventory", {}).get("root")
    behavior = build_behavior_analysis_package(
        behavior_root or project / "data" / "session", participant_id=participant,
        session_id=session, age=age)
    if behavior:
        if supplemental_vft_scoring:
            behavior.setdefault("features", {}).setdefault("vft", {}).update(
                supplemental_vft_scoring.get("totals", {}))
            behavior.setdefault("analysis", {})["vft_scoring"] = supplemental_vft_scoring
            behavior["data_quality"]["components"]["vft_scoring"] = (
                supplemental_vft_scoring.get("status") == "SCORED")
        behavior = review_package(behavior, reviewer=reviewer, decision="APPROVED",
                                  note="统一分析：核对行为任务原始记录")
        path = run_root / "behavior" / "behavior_analysis_package.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(behavior, ensure_ascii=False, indent=2), encoding="utf-8")
        source_packages.append(path)

    if (supplemental_mmn and "eeg" not in modalities) or (
            supplemental_vft_scoring and not behavior):
        supplemental = build_analysis_package(
            participant, session, age=age,
            mmn=supplemental_mmn if "eeg" not in modalities else None,
            vft_scoring=supplemental_vft_scoring if not behavior else None)
        supplemental = review_package(
            supplemental, reviewer=reviewer, decision="APPROVED",
            note="统一分析：核对MMN预处理补充文件与VFT人工计分")
        path = run_root / "supplemental" / "supplemental_analysis_package.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(supplemental, ensure_ascii=False, indent=2), encoding="utf-8")
        source_packages.append(path)

    if not source_packages:
        raise ValueError("尚未导入任何可分析的数据包")
    integrated = merge_analysis_packages(
        source_packages, participant_id=participant, session_id=session,
        reviewer=reviewer, age=age,
        note="统一分析：所有已暂存模态完成批处理、质控、来源核对后生成")
    if "clinical" in modalities:
        clinical_path = Path(modalities["clinical"]["file"]["path"])
        clinical_payload = json.loads(clinical_path.read_text(encoding="utf-8"))
        integrated = apply_clinical_assessment(
            integrated, clinical_payload.get("assessment") or {},
            clinician=str(clinical_payload.get("clinician") or reviewer),
            note=str(clinical_payload.get("note") or ""))
        integrated = review_package(
            integrated, reviewer=reviewer, decision="APPROVED",
            note="统一分析：审核人核对多模态结果与临床/心理资料")
    integrated["import_session"] = {"manifest": str(source_manifest.resolve()),
                                    "sha256": _sha256(source_manifest)}
    package_path = write_integrated_package(integrated, run_root / "integrated")
    reports = generate_multimodal_report(
        package_path, project / "data" / "reports" / "multimodal", require_review=True)
    manifest["status"] = "ANALYZED"
    manifest["last_run"] = {"completed_at": datetime.now(timezone.utc).isoformat(),
                            "integrated_package": str(package_path), "report": str(reports["html"])}
    source_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"manifest": source_manifest, "package": package_path, "report": reports["html"],
            "integrated": integrated, "source_packages": source_packages}


__all__ = ["load_import_session", "manifest_path", "run_unified_analysis", "stage_file", "stage_folder",
           "summarize_import_session"]
