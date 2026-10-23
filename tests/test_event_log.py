import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.session import build_demo_session
from bplus.triggers import LOG_COLUMNS


def test_demo_session_writes_log_and_manifest(tmp_path):
    result = build_demo_session("T99", "1", out_dir=tmp_path)
    manifest = result.manifest

    assert manifest["mode"] == "DEMO"
    assert manifest["timeline"]["total_duration_min"] == 70.0
    assert manifest["trigger_log"]["n_events"] > 100

    csv_path = Path(manifest["trigger_log"]["csv"])
    assert csv_path.exists() and Path(manifest["trigger_log"]["jsonl"]).exists()
    with csv_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert set(rows[0]) == set(LOG_COLUMNS)
    assert rows[0]["event_name"] == "SESSION_START"
    assert rows[-1]["event_name"] == "SESSION_END"

    adapters = {a["name"]: a for a in manifest["adapters"]}
    assert adapters["asee_pro_f250"]["status"] == "REQUIRES_VENDOR_SDK"
    assert adapters["lightnirs"]["status"] == "REQUIRES_VENDOR_DOC"
    assert adapters["synamps_aux_physio"]["status"] == "IMPLEMENTED"
