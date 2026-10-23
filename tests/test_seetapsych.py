import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.adapters.seetapsych import SeetaPsychAdapter, normalize_report, write_results


class FakeRunner:
    def run(self, data):
        assert "default" in data
        return {
            "face_detection": [{"score": 0.98, "xyxy": [1, 2, 3, 4]}],
            "face_expression": [{"neutral": 0.2, "sad": 0.8}],
            "face_action_units": [{"AU4": 0.7, "AU12": 0.1}],
            "face_dimensional_affect": [{"valence": -0.4, "arousal": 0.3}],
            "face_heart_rate": {"fps": 30.0, "hr_bpm": 72.5, "wait_seconds": 0.0},
        }


def test_adapter_normalizes_public_attribute_contract():
    row = SeetaPsychAdapter(runner=FakeRunner()).analyze_frame(object(), frame_index=5, timestamp_s=0.2)
    assert row["dominant_expression"] == "sad"
    assert row["heart_rate_bpm"] == 72.5
    assert row["action_units"]["AU4"] == 0.7
    assert row["face_count"] == 1


def test_missing_faces_are_explicit_not_fabricated():
    row = normalize_report({}, frame_index=0, timestamp_s=0.0)
    assert row["face_count"] == 0
    assert row["dominant_expression"] is None
    assert row["heart_rate_bpm"] is None


def test_results_write_lossless_and_flat_outputs(tmp_path):
    rows = [normalize_report({}, frame_index=0, timestamp_s=0.0)]
    jsonl, csv_path, count = write_results(rows, tmp_path / "result")
    assert count == 1 and jsonl.exists() and csv_path.exists()
    payload = json.loads(jsonl.read_text(encoding="utf-8"))
    assert payload["frame_index"] == 0
