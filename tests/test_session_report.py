import csv
import json

from bplus.reports import generate_session_report


HEADERS = ["participant_id", "session_id", "paradigm", "trial_index", "block_id", "condition",
           "code", "onset_s", "stim", "is_target", "expected_key", "responded", "key",
           "rt_ms", "correct", "valence", "arousal", "practice"]


def _write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def test_session_report_uses_real_behavior_and_marks_unavailable_modalities(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    base = {column: "" for column in HEADERS}
    nback_rows = [
        {**base, "participant_id": "P01", "session_id": "1", "paradigm": "nback",
         "trial_index": "1", "is_target": "1", "responded": "1", "key": "return",
         "rt_ms": "510", "correct": "1", "practice": "0"},
        {**base, "participant_id": "P01", "session_id": "1", "paradigm": "nback",
         "trial_index": "2", "is_target": "0", "responded": "0", "correct": "1", "practice": "0"},
        {**base, "participant_id": "P01", "session_id": "1", "paradigm": "nback",
         "trial_index": "3", "is_target": "1", "responded": "0", "correct": "0", "practice": "0"},
    ]
    _write(session / "sub-P01_ses-1_nback_behavior.csv", nback_rows)
    report = generate_session_report(session, tmp_path / "reports", participant_id="P01", session_id="1",
                                     paradigms=["nback", "emotion"])
    html = report.read_text(encoding="utf-8")
    assert "66.7%" in html and "1/2" in html and "510 ms" in html
    assert "BPlus Youth Multimodal Research Report" in html
    assert "DATA PENDING" in html and "Insufficient data" in html
    assert "does not infer conclusions from demonstration or missing data" in html
    metadata = json.loads((session / "sub-P01_ses-1_metadata.json").read_text(encoding="utf-8"))
    assert metadata == {"participant_id": "P01", "session_id": "1", "age": None}


def test_session_report_summarizes_emotion_ratings(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    base = {column: "" for column in HEADERS}
    rows = [
        {**base, "participant_id": "P02", "session_id": "2", "paradigm": "emotion",
         "trial_index": "1", "valence": "4", "arousal": "2"},
        {**base, "participant_id": "P02", "session_id": "2", "paradigm": "emotion",
         "trial_index": "2", "valence": "2", "arousal": "4"},
    ]
    _write(session / "sub-P02_ses-2_emotion_behavior.csv", rows)
    report = generate_session_report(session, tmp_path / "reports", participant_id="P02", session_id="2",
                                     paradigms=["emotion"])
    html = report.read_text(encoding="utf-8")
    assert "3.00" in html and "2/1" not in html and "completed" in html.lower()


def test_paradigm_log_does_not_claim_physiology_qc_pass(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    base = {column: "" for column in HEADERS}
    _write(session / "sub-P03_ses-1_mmn_behavior.csv", [
        {**base, "participant_id": "P03", "session_id": "1", "paradigm": "mmn", "trial_index": "1"}
    ])
    report = generate_session_report(session, tmp_path / "reports", participant_id="P03", session_id="1",
                                     paradigms=["mmn"], age=13)
    html = report.read_text(encoding="utf-8")
    mmn_card = html.split("Automatic Sensory Processing · MMN", 1)[1].split("</section>", 1)[0]
    assert "DATA PENDING" in mmn_card
    assert "<span class=\"badge PASS\">PASS</span>" not in mmn_card
