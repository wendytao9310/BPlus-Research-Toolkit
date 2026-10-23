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
    assert rows["100–250 ms MMN amplitude"]["state"] == "Moderate auditory-change response"
    assert rows["Peak latency"]["state"] == "Intermediate response timing"
    assert rows["d-prime (target discrimination)"]["state"] == "Clear target discrimination"
    assert rows["Median response time"]["state"] == "Faster response speed"
    assert rows["Mean arousal rating"]["state"] == "Higher subjective arousal"
    html = render_v27_html(payload)
    assert "How the Current Response Status Is Derived" in html
    assert "not clinical cutoffs supplied by those papers" in html


def test_missing_and_failed_metrics_are_never_interpreted():
    assert describe_metric("nback.d_prime", None)[0] == "Insufficient data"
