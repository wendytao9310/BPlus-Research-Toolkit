"""7invensun (七鑫易维) aSee Pro F250 desktop eye tracker."""
from __future__ import annotations

from .base import AdapterInfo, AdapterStatus, DeviceAdapter


class AseeProAdapter(DeviceAdapter):
    """Eye-tracking side of the experiment PC.

    Correction vs. the first draft of the plan: the lab uses 7invensun aSee Pro F250,
    NOT Tobii Spectrum. Therefore PyGaze/Titta (Tobii wrappers) are reference-only here.
    The vendor SDK is licensed with the device, so this adapter is REQUIRES_VENDOR_SDK:
    the acquisition layer must be written against the aSee Pro SDK (Windows), while
    everything downstream stays on pymovements (vendor-neutral).
    """

    info = AdapterInfo(
        name="asee_pro_f250",
        device="aSee Pro F250",
        vendor="7invensun (七鑫易维)",
        status=AdapterStatus.REQUIRES_VENDOR_SDK.value,
        interface="aSee Pro SDK (vendor, included with purchase) + calibration UI; TTL sync TBC",
        data_path="experiment_pc/eye",
        trigger_path="to verify: SDK timestamp + optional TTL in/out box",
        notes="Export gaze samples to a documented column layout, then analyse with pymovements.",
    )

    def describe(self) -> dict:
        return self.info.as_dict()

    def start(self) -> None:
        raise self._unsupported("starting a recording session")

    def stop(self) -> None:
        raise self._unsupported("stopping a recording session")
