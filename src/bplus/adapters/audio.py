"""Interview audio capture."""
from __future__ import annotations

from .base import AdapterInfo, AdapterStatus, DeviceAdapter


class AudioAdapter(DeviceAdapter):
    info = AdapterInfo(
        name="audio",
        device="interview microphone",
        vendor="TBC",
        status=AdapterStatus.PLACEHOLDER.value,
        interface="TBC (USB audio) - 48 kHz mono recommended for later transcription",
        data_path="experiment_pc/audio",
        trigger_path="software time-stamp + LSL",
        notes="Interview audio is only used for the clinical anchor, never for automatic scoring.",
    )

    def describe(self) -> dict:
        return self.info.as_dict()
