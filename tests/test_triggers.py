import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.io import EventLog, read_event_log
from bplus.triggers import LOG_COLUMNS, TriggerCode, TriggerManager


def test_section57_codes_are_exact():
    expected = {
        "REST_START": 10, "REST_END": 11,
        "MMN_START": 100, "MMN_STANDARD": 101, "MMN_DEVIANT": 102, "MMN_END": 109,
        "VFT_START": 200, "VFT_BLOCK": 201, "VFT_REST": 202, "VFT_END": 209,
        "NBACK_START": 300, "NBACK_0BACK": 301, "NBACK_2BACK": 302,
        "NBACK_TARGET": 303, "NBACK_NONTARGET": 304, "NBACK_END": 309,
        "EMOTION_START": 400, "EMOTION_NEUTRAL": 401, "EMOTION_POSITIVE": 402,
        "EMOTION_NEGATIVE": 403, "EMOTION_END": 409,
        "EMOTION_CUE": 410, "EMOTION_RATING": 411, "EMOTION_BLOCK": 412,
        "INTERVIEW_START": 500, "INTERVIEW_QUESTION": 501, "INTERVIEW_ANSWER": 502,
        "INTERVIEW_END": 509,
        "RECOVERY_START": 600, "RECOVERY_END": 601,
    }
    for name, value in expected.items():
        assert int(TriggerCode[name]) == value, name


def test_phase_codes_do_not_collide():
    values = [int(c) for c in TriggerCode]
    assert len(values) == len(set(values))


def test_log_rows_have_all_required_columns(tmp_path):
    log = EventLog(tmp_path, participant_id="T01", session_id="1")
    manager = TriggerManager("T01", "1", log=log)
    manager.send(TriggerCode.MMN_DEVIANT, trial_id=7, block_id=2, phase="computer_paradigms", hz=1200)
    rows = read_event_log(log.csv_path)
    assert len(rows) == 1
    assert set(rows[0]).issuperset(LOG_COLUMNS)
    assert rows[0]["event_code"] == "102"
    assert rows[0]["trial_id"] == "7"
    assert "1200" in rows[0]["meta"]
    assert log.jsonl_path.exists()
