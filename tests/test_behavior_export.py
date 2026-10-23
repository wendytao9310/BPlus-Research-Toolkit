import csv
import json
import zipfile

import pytest

from bplus.behavior_export import export_all_behavior_sessions, export_behavior_session


def _write_behavior(path):
    columns = ["participant_id", "session_id", "paradigm", "trial_index", "block_id", "condition",
               "code", "onset_s", "stim", "is_target", "expected_key", "responded", "key",
               "rt_ms", "correct", "valence", "arousal", "practice"]
    rows = [
        ["P01", "1", "nback", 1, 1, "2back", 302, 1.0, "8", 1, "return", 1, "return", 510, 1, "", "", 0],
        ["P01", "1", "nback", 2, 1, "2back", 301, 3.0, "4", 0, "", 0, "", "", 1, "", "", 0],
        ["P01", "1", "nback", 3, 1, "2back", 301, 5.0, "6", 0, "", 1, "return", 620, 0, "", "", 0],
        ["P01", "1", "nback", 4, 1, "2back", 302, 7.0, "8", 1, "return", 0, "", "", 0, "", "", 0],
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle); writer.writerow(columns); writer.writerows(rows)


def test_behavior_export_creates_long_bids_summary_dictionary_qc_and_zip(tmp_path):
    session = tmp_path / "session"; session.mkdir()
    _write_behavior(session / "sub-P01_ses-1_nback_behavior.csv")
    result = export_behavior_session(session, tmp_path / "exports", participant_id="P01", session_id="1")
    for key in ("trials", "summary", "dictionary", "qc", "manifest", "zip"):
        assert result[key].exists()
    with result["trials"].open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["outcome"] for row in rows] == ["hit", "correct_rejection", "false_alarm", "miss"]
    events = result["folder"] / "sub-P01_ses-1_task-nback_events.tsv"
    text = events.read_text(encoding="utf-8")
    assert "onset\tduration\ttrial_type" in text
    assert "0.510000" in text
    with result["summary"].open(newline="", encoding="utf-8-sig") as handle:
        summary = list(csv.DictReader(handle))[0]
    assert summary["participant_id"] == "P01"
    assert float(summary["hit_rate"]) == pytest.approx(0.5)
    assert float(summary["false_alarm_rate"]) == pytest.approx(0.5)
    assert json.loads(result["manifest"].read_text(encoding="utf-8"))["n_trials"] == 4
    with zipfile.ZipFile(result["zip"]) as archive:
        assert any(name.endswith("behavior_trials.csv") for name in archive.namelist())


def test_batch_export_preserves_subject_and_session_in_cohort_summary(tmp_path):
    session = tmp_path / "session"; session.mkdir()
    _write_behavior(session / "sub-P01_ses-1_nback_behavior.csv")
    result = export_all_behavior_sessions(session, tmp_path / "exports")
    assert result["n_sessions"] == 1
    text = result["cohort_summary"].read_text(encoding="utf-8-sig")
    assert "participant_id" in text and "P01" in text


def test_nback_cue_rows_remain_in_events_but_not_summary(tmp_path):
    session = tmp_path / "session"; session.mkdir()
    _write_behavior(session / "sub-P01_ses-1_nback_behavior.csv")
    path = session / "sub-P01_ses-1_nback_behavior.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    rows.append({key: "" for key in rows[0]})
    rows[-1].update({"participant_id": "P01", "session_id": "1", "paradigm": "nback",
                     "trial_index": "5", "block_id": "2", "condition": "2back-cue",
                     "code": "301", "onset_s": "9.0", "stim": "说明页", "practice": "0"})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    result = export_behavior_session(session, tmp_path / "exports", participant_id="P01", session_id="1")
    assert "2back-cue" in (result["folder"] / "sub-P01_ses-1_task-nback_events.tsv").read_text()
    assert "2back-cue" not in result["summary"].read_text(encoding="utf-8-sig")
