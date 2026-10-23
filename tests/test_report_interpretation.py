from bplus.reports.interpretation import describe_metric
from bplus.reports.v27 import build_report_payload, render_v27_html


def test_numeric_metrics_receive_functional_states_not_measurement_status():
    package = {
        "participant_id": "P01", "session_id": "1",
        "sources": {"eeg": {"status": "PILOT"}, "fnirs": {"status": "PILOT"},
                    "eye": {"status": "MISSING"}, "behavior": {"status": "VERIFIED"},
                    "clinical": {"status": "MISSING"}},
        "data_quality": {"score": 85, "band": "ACCEPTABLE"},
        "features": {"eeg": {"mmn_amplitude_uv": -3.2, "mmn_latency_ms": 205},
                     "nback": {"d_prime": 2.1, "median_rt_ms": 620},
                     "emotion": {"arousal_mean": 4.3}},
        "analysis": {"mmn": {"qc": {"status": "PASS", "n_deviant": 40}},
                     "nback": {"qc": {"status": "PASS"}},
                     "emotion": {"qc": {"status": "PASS"}}},
    }
    payload = build_report_payload(package)
    rows = {row["name"]: row for module in payload["modules"] for row in module["rows"]}
    assert rows["100–250 ms MMN 波幅"]["state"] == "声音变化反应中等"
    assert rows["峰值潜伏期"]["state"] == "反应时序居中"
    assert rows["d′（目标辨别能力）"]["state"] == "目标辨别较清晰"
    assert rows["反应时中位数"]["state"] == "作答速度较快"
    assert rows["平均激动程度"]["state"] == "主观唤醒较高"
    html = render_v27_html(payload)
    assert "当前反应状态如何得到" in html
    assert "不是论文提供的临床切点" in html


def test_missing_and_failed_metrics_are_never_interpreted():
    assert describe_metric("nback.d_prime", None)[0] == "数据不足"
