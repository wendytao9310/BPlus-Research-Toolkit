import json

import numpy as np

from bplus.import_session import (load_import_session, manifest_path, run_unified_analysis,
                                  stage_file, stage_folder, summarize_import_session)


def test_stage_whole_folder_does_not_analyze(tmp_path):
    source = tmp_path / "eeg_source"
    source.mkdir()
    (source / "run.vhdr").write_text("header", encoding="utf-8")
    (source / "run.vmrk").write_text("marker", encoding="utf-8")
    (source / "run.eeg").write_bytes(b"raw")
    imports = tmp_path / "project" / "data" / "imports"
    path, entry = stage_folder(imports, participant_id="P01", session_id="1",
                               modality="eeg", folder=source)
    assert path == manifest_path(imports, "P01", "1")
    assert entry["status"] == "STAGED"
    assert entry["inventory"]["file_count"] == 3
    assert not (tmp_path / "project" / "data" / "analysis").exists()
    assert not (tmp_path / "project" / "data" / "reports").exists()


def test_staging_modalities_accumulates_in_one_manifest(tmp_path):
    eeg = tmp_path / "eeg"; eeg.mkdir()
    for suffix in (".vhdr", ".vmrk", ".eeg"):
        (eeg / f"run{suffix}").write_text("x", encoding="utf-8")
    behavior = tmp_path / "behavior"; behavior.mkdir()
    (behavior / "sub-P01_ses-1_nback_behavior.csv").write_text("trial_id\n1\n", encoding="utf-8")
    imports = tmp_path / "imports"
    stage_folder(imports, participant_id="P01", session_id="1", modality="eeg", folder=eeg)
    stage_folder(imports, participant_id="P01", session_id="1", modality="behavior", folder=behavior)
    manifest = load_import_session(imports, participant_id="P01", session_id="1")
    rows = {row["modality"]: row for row in summarize_import_session(manifest)}
    assert rows["eeg"]["status"] == "STAGED"
    assert rows["behavior"]["status"] == "STAGED"
    assert rows["fnirs"]["status"] == "NOT_STAGED"


def test_unified_button_builds_one_report_from_staged_behavior(tmp_path):
    project = tmp_path / "project"
    behavior = tmp_path / "behavior" / "nested"
    behavior.mkdir(parents=True)
    (behavior / "sub-P01_ses-1_emotion_behavior.csv").write_text(
        "trial_id,practice,valence,arousal\n1,0,4,3\n2,0,5,4\n", encoding="utf-8")
    imports = project / "data" / "imports"
    path, _ = stage_folder(imports, participant_id="P01", session_id="1",
                           modality="behavior", folder=behavior.parent)
    result = run_unified_analysis(path, project_root=project, reviewer="Researcher")
    assert result["report"].exists()
    assert result["package"].exists()
    package = json.loads(result["package"].read_text(encoding="utf-8"))
    assert package["features"]["emotion"]["valence_mean"] == 4.5
    assert package["data_quality"]["components"]["present_modalities"] == ["behavior"]


def test_unified_analysis_reads_publication_behavior_export(tmp_path):
    project = tmp_path / "project"
    export = tmp_path / "export"
    export.mkdir()
    trials = export / "sub-P02_ses-1_behavior_trials.csv"
    trials.write_text(
        "participant_id,session_id,task,condition,is_target,response_given,response_key,response_time_ms,valence,arousal,practice\n"
        "P02,1,nback,0-back,True,True,return,510,,,False\n"
        "P02,1,nback,0-back,False,False,,,,,False\n"
        "P02,1,emotion,negative,,,,,2,4,False\n"
        "P02,1,emotion,neutral,,,,,4,3,False\n", encoding="utf-8")
    imports = project / "data" / "imports"
    path, _ = stage_folder(imports, participant_id="P02", session_id="1",
                           modality="behavior", folder=export)
    result = run_unified_analysis(path, project_root=project, reviewer="Researcher")
    package = json.loads(result["package"].read_text(encoding="utf-8"))
    assert package["sources"]["behavior"]["status"] == "VERIFIED"
    assert package["features"]["nback"]["accuracy"] == 1.0
    assert package["features"]["emotion"]["valence_diff"] == -2.0


def test_supplemental_mmn_and_vft_scoring_join_unified_report(tmp_path):
    project = tmp_path / "project"
    supplements = tmp_path / "supplements"; supplements.mkdir()
    times = np.linspace(-100, 300, 81)
    standard = np.zeros((12, 2, len(times)))
    deviant = np.zeros_like(standard)
    deviant[:, :, np.argmin(abs(times - 180))] = -3.0
    mmn = supplements / "mmn_epochs.npz"
    np.savez(mmn, standard_epochs_uv=standard, deviant_epochs_uv=deviant,
             times_ms=times, channel_names=np.array(["Fz", "Cz"]))
    scoring = supplements / "vft_scoring.csv"
    scoring.write_text(
        "block,prompt,transcript,valid_words,repetitions,intrusions,reviewer\n"
        "1,动物,猫 狗 马,3,0,0,DrA\n", encoding="utf-8")
    imports = project / "data" / "imports"
    path, _ = stage_file(imports, participant_id="P03", session_id="1",
                         modality="mmn_epochs", file=mmn)
    stage_file(imports, participant_id="P03", session_id="1",
               modality="vft_scoring", file=scoring)
    result = run_unified_analysis(path, project_root=project, reviewer="Researcher")
    package = json.loads(result["package"].read_text(encoding="utf-8"))
    assert package["features"]["eeg"]["mmn_latency_ms"] == 180.0
    assert package["features"]["vft"]["valid_words"] == 3
    assert result["report"].exists()


def test_clinical_assessment_is_staged_then_added_by_unified_button(tmp_path):
    project = tmp_path / "project"
    behavior = tmp_path / "behavior"; behavior.mkdir()
    (behavior / "sub-P04_ses-1_emotion_behavior.csv").write_text(
        "trial_id,practice,valence,arousal\n1,0,3,4\n", encoding="utf-8")
    clinical = tmp_path / "clinical.json"
    clinical.write_text(json.dumps({
        "participant_id": "P04", "session_id": "1", "clinician": "Dr A",
        "assessment": {"phq9_total": 8, "phq9_status": "由临床医生解释"},
        "note": "verified entry",
    }, ensure_ascii=False), encoding="utf-8")
    imports = project / "data" / "imports"
    path, _ = stage_folder(imports, participant_id="P04", session_id="1",
                           modality="behavior", folder=behavior)
    stage_file(imports, participant_id="P04", session_id="1",
               modality="clinical", file=clinical)
    result = run_unified_analysis(path, project_root=project, reviewer="Researcher")
    package = json.loads(result["package"].read_text(encoding="utf-8"))
    assert package["features"]["clinical"]["phq9_total"] == 8
    assert package["sources"]["clinical"]["status"] == "VERIFIED"
    assert result["report"].exists()
