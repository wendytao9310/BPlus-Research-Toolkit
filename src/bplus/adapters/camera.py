"""Camera / microphone (interview audio-video)."""
from __future__ import annotations

from .base import AdapterInfo, AdapterStatus, DeviceAdapter


class CameraAdapter(DeviceAdapter):
    info = AdapterInfo(
        name="camera",
        device="interview camera",
        vendor="TBC",
        status=AdapterStatus.PLACEHOLDER.value,
        interface="TBC (USB / IP camera) - must respect the ethics approval for video recording",
        data_path="experiment_pc/video",
        trigger_path="software time-stamp + LSL; a clap/TTL sync pulse is recommended",
        notes="Clinical interview A/V needs an explicit ethics decision before implementation.",
    )

    def describe(self) -> dict:
        return self.info.as_dict()
