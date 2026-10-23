import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.preflight import run_preflight


def test_demo_preflight_passes_and_writes_report(tmp_path, monkeypatch):
    from collections import namedtuple
    import bplus.preflight as preflight

    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(preflight.shutil, "disk_usage", lambda _: usage(100 * 1024 ** 3, 50 * 1024 ** 3,
                                                                         50 * 1024 ** 3))
    report = run_preflight("TEST001", "1", mode="DEMO", paradigm="nback", out_dir=tmp_path)
    assert report["verdict"] == "PASS"
    assert Path(report["path"]).exists()


def test_real_preflight_is_blocked_until_physical_trigger_is_validated(tmp_path):
    report = run_preflight("TEST001", "1", mode="REAL", paradigm="nback", out_dir=tmp_path)
    assert report["verdict"] == "FAIL"
    assert any(c["name"] == "physical_trigger" and c["status"] == "FAIL" for c in report["checks"])


def test_emotion_real_preflight_reports_gate_instead_of_crashing(tmp_path):
    report = run_preflight("TEST001", "1", mode="REAL", paradigm="emotion", out_dir=tmp_path)
    assert report["verdict"] == "FAIL"
    assert any(c["name"] == "emotion_stimuli" for c in report["checks"])
