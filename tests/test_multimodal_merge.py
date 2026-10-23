import json

import pytest

from bplus.multimodal_merge import (build_behavior_analysis_package, merge_analysis_packages,
                                    write_integrated_package)


def _package(pid, session, modality, feature_group, features, score=80):
    sources = {key: {"status": "MISSING"} for key in
               ("eeg", "fnirs", "eye", "behavior", "physiology", "clinical")}
    sources[modality] = {"status": "VERIFIED", "file": f"{pid}_{modality}.dat"}
    return {"participant_id": pid, "session_id": session, "sources": sources,
            "features": {feature_group: features},
            "data_quality": {"score": score, "notes": []}, "analysis": {}}


def test_merges_same_participant_modalities_and_keeps_provenance(tmp_path):
    eeg = tmp_path / "sub-001_ses-1_eeg.json"
    fnirs = tmp_path / "sub-001_ses-1_fnirs.json"
    eeg.write_text(json.dumps(_package("001", "1", "eeg", "eeg", {"mmn_latency_ms": 190})))
    fnirs.write_text(json.dumps(_package("001", "1", "fnirs", "fnirs", {"sci": 0.88}, 90)))
    merged = merge_analysis_packages([eeg, fnirs], participant_id="001", session_id="1",
                                     reviewer="Researcher A", age=15)
    assert merged["features"]["eeg"]["mmn_latency_ms"] == 190
    assert merged["features"]["fnirs"]["sci"] == 0.88
    assert merged["sources"]["eeg"]["status"] == "VERIFIED"
    assert len(merged["source_packages"]) == 2
    assert merged["data_quality"]["score"] == 85
    path = write_integrated_package(merged, tmp_path / "integrated")
    assert path.exists()


def test_rejects_cross_participant_merge(tmp_path):
    path = tmp_path / "sub-001_ses-1_eeg.json"
    path.write_text(json.dumps(_package("002", "1", "eeg", "eeg", {"x": 1})))
    with pytest.raises(ValueError, match="禁止跨被试"):
        merge_analysis_packages([path], participant_id="001", session_id="1", reviewer="R")


def test_rejects_conflicting_metric(tmp_path):
    one = tmp_path / "one.json"; two = tmp_path / "two.json"
    one.write_text(json.dumps(_package("001", "1", "eeg", "eeg", {"x": 1})))
    two.write_text(json.dumps(_package("001", "1", "eeg", "eeg", {"x": 2})))
    with pytest.raises(ValueError, match="冲突指标"):
        merge_analysis_packages([one, two], participant_id="001", session_id="1", reviewer="R")


def test_builds_behavior_features_for_same_identity(tmp_path):
    path = tmp_path / "sub-001_ses-1_nback_behavior.csv"
    path.write_text(
        "participant_id,session_id,paradigm,trial_index,condition,is_target,responded,key,rt_ms,practice\n"
        "001,1,nback,1,target,1,1,return,500,0\n"
        "001,1,nback,2,nontarget,0,0,,,0\n", encoding="utf-8")
    package = build_behavior_analysis_package(tmp_path, participant_id="001", session_id="1")
    assert package["sources"]["behavior"]["status"] == "VERIFIED"
    assert package["features"]["nback"]["accuracy"] == 1.0
