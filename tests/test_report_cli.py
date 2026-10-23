import csv

from bplus.report import generate_report


def test_cli_falls_back_to_pending_behavior_report(tmp_path):
    root = tmp_path
    session = root / "data" / "session"
    session.mkdir(parents=True)
    path = session / "sub-P01_ses-1_nback_behavior.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["practice", "is_target", "key", "rt_ms"])
        writer.writeheader()
        writer.writerow({"practice": "0", "is_target": "1", "key": "return", "rt_ms": "500"})
    report = generate_report("sub-P01", "ses-1", root=root)
    assert report.exists()
    assert "实验完成待分析版" in report.read_text(encoding="utf-8")
