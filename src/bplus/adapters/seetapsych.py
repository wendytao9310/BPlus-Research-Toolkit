"""Optional SeetaPsych offline video-analysis integration.

The acquisition computer should record a timestamped face video; inference is deliberately
kept out of the PsychoPy timing loop.  The adapter accepts an injected runner in tests and
imports SeetaPsych only when a real pipeline is requested.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from .base import AdapterInfo, AdapterStatus, DeviceAdapter


DEFAULT_ATTRIBUTES = (
    "face/detection",
    "face/expression",
    "face/action_units",
    "face/dimensional_affect",
    "face/heart_rate",
)


class SeetaPsychUnavailable(RuntimeError):
    """Raised when the optional SeetaPsych runtime is not installed."""


@dataclass(frozen=True)
class SeetaPsychSettings:
    attributes: tuple[str, ...] = DEFAULT_ATTRIBUTES
    device: str = "auto"
    install_requirements: bool = False
    cache_models: bool = False
    primary_face_index: int = 0
    provenance: Mapping[str, str] = field(default_factory=lambda: {
        "paper": "arXiv:2609.19719v1",
        "toolkit": "SeetaPsych v1.0",
    })


class SeetaPsychAdapter(DeviceAdapter):
    info = AdapterInfo(
        name="seetapsych_offline",
        device="experiment/interview RGB camera recording",
        vendor="SeetaPsych open-source ecosystem",
        status=AdapterStatus.IMPLEMENTED.value,
        interface="seetapsych-lib Pipeline/Runner (optional dependency; offline inference)",
        data_path="data/session/sub-*_ses-*_seetapsych.{jsonl,csv}",
        trigger_path="camera timestamp mapped to BPlus monotonic/session time; shared sync event",
        notes=("Secondary research measurement only. It must not replace aSee Pro, ECG/PPG, "
               "clinical ratings, or participant self-report without local validation."),
    )

    def __init__(self, settings: SeetaPsychSettings | None = None, *, runner: Any | None = None) -> None:
        self.settings = settings or SeetaPsychSettings()
        self.runner = runner

    def describe(self) -> dict[str, Any]:
        out = self.info.as_dict()
        out["attributes"] = list(self.settings.attributes)
        out["execution"] = "POST_ACQUISITION_OFFLINE"
        out["provenance"] = dict(self.settings.provenance)
        return out

    def start(self) -> None:
        if self.runner is None:
            self.runner = self._build_runner()

    def stop(self) -> None:
        self.runner = None

    def _build_runner(self) -> Any:
        try:
            from seetapsych_lib.runtime.factory import Factory
            from seetapsych_lib.runtime.pipeline import Pipeline
            from seetapsych_lib.runtime.runner import Runner
        except ImportError as exc:
            raise SeetaPsychUnavailable(
                "SeetaPsych is optional. Install the locked analysis environment described in "
                "docs/SEETAPSYCH_INTEGRATION.md before running real inference."
            ) from exc

        factory = Factory()
        pipeline = Pipeline(factory, attributes=list(self.settings.attributes))
        pipeline.solve()
        if self.settings.install_requirements:
            pipeline.install_requirements()
        if self.settings.cache_models:
            pipeline.cache_models()
        return Runner(pipeline)

    def analyze_frame(self, frame: Any, *, frame_index: int, timestamp_s: float) -> dict[str, Any]:
        if self.runner is None:
            self.start()
        report = self.runner.run(data={"default": frame})
        return normalize_report(report, frame_index=frame_index, timestamp_s=timestamp_s,
                                primary_face_index=self.settings.primary_face_index)


def _face_item(report: Mapping[str, Any], key: str, index: int) -> Mapping[str, Any]:
    value = report.get(key, [])
    if isinstance(value, list) and 0 <= index < len(value) and isinstance(value[index], Mapping):
        return value[index]
    return {}


def normalize_report(report: Mapping[str, Any], *, frame_index: int, timestamp_s: float,
                     primary_face_index: int = 0) -> dict[str, Any]:
    """Map public SeetaPsych attribute contracts to a stable BPlus row."""
    expression = _face_item(report, "face_expression", primary_face_index)
    action_units = _face_item(report, "face_action_units", primary_face_index)
    affect = _face_item(report, "face_dimensional_affect", primary_face_index)
    gaze = _face_item(report, "face_gaze_screen", primary_face_index)
    detections = report.get("face_detection", [])
    detection = _face_item(report, "face_detection", primary_face_index)
    heart = report.get("face_heart_rate", {})
    if not isinstance(heart, Mapping):
        heart = {}
    dominant = None
    valid_expression = {k: float(v) for k, v in expression.items() if isinstance(v, (int, float))}
    if valid_expression:
        dominant = max(valid_expression, key=valid_expression.get)
    return {
        "frame_index": int(frame_index),
        "timestamp_s": float(timestamp_s),
        "face_count": len(detections) if isinstance(detections, list) else 0,
        "primary_face_score": detection.get("score"),
        "dominant_expression": dominant,
        "expression": valid_expression,
        "action_units": {k: v for k, v in action_units.items() if v is not None},
        "valence": affect.get("valence"),
        "arousal": affect.get("arousal"),
        "heart_rate_bpm": heart.get("hr_bpm"),
        "heart_rate_fps": heart.get("fps"),
        "gaze_success": gaze.get("success"),
        "gaze_screen_px": gaze.get("gaze_screen_px"),
    }


def _json_default(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def write_results(rows: Iterable[Mapping[str, Any]], output_stem: str | Path) -> tuple[Path, Path, int]:
    """Write lossless JSONL plus a flat analysis index CSV."""
    stem = Path(output_stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path, csv_path = stem.with_suffix(".jsonl"), stem.with_suffix(".csv")
    flat_fields = ("frame_index", "timestamp_s", "face_count", "primary_face_score",
                   "dominant_expression", "valence", "arousal", "heart_rate_bpm",
                   "heart_rate_fps", "gaze_success")
    count = 0
    with jsonl_path.open("w", encoding="utf-8") as jf, csv_path.open(
            "w", newline="", encoding="utf-8") as cf:
        writer = csv.DictWriter(cf, fieldnames=flat_fields)
        writer.writeheader()
        for row in rows:
            payload = dict(row)
            jf.write(json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")
            writer.writerow({key: payload.get(key) for key in flat_fields})
            count += 1
    return jsonl_path, csv_path, count


def iter_video_frames(video_path: str | Path) -> Iterator[tuple[int, float, Any]]:
    """Yield every frame; full frame rate is required by buffered rPPG methods."""
    try:
        import cv2
    except ImportError as exc:
        raise SeetaPsychUnavailable("Video decoding requires OpenCV (`opencv-python`).") from exc
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if fps <= 0:
        capture.release()
        raise ValueError("Video FPS is missing; preserve camera timing metadata during acquisition.")
    index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp_ms = float(capture.get(cv2.CAP_PROP_POS_MSEC))
            timestamp_s = timestamp_ms / 1000.0 if timestamp_ms > 0 else index / fps
            yield index, timestamp_s, frame
            index += 1
    finally:
        capture.release()


def analyze_video(adapter: SeetaPsychAdapter, video_path: str | Path,
                  output_stem: str | Path) -> tuple[Path, Path, int]:
    def rows() -> Iterator[dict[str, Any]]:
        for index, timestamp_s, frame in iter_video_frames(video_path):
            yield adapter.analyze_frame(frame, frame_index=index, timestamp_s=timestamp_s)
    return write_results(rows(), output_stem)
