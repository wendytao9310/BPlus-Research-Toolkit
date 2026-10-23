"""Shimadzu LIGHTNIRS fNIRS system."""
from __future__ import annotations

from .base import AdapterInfo, AdapterStatus, DeviceAdapter


class LightNIRSAdapter(DeviceAdapter):
    """fNIRS side of the 2-computer chain.

    PUBLIC_VERIFIED: one LIGHTNIRS unit measures up to 22 channels (52 with two units).
    USER_REPORTED: Trig In is TTL (high 2.4-5 V / low 0-0.8 V), default rising edge, and the
        marker is written into the exported event column.
    USER_REPORTED (conflicting): sampling interval is quoted as 10 ms / 13.3 ms / 75 ms.
        -> resolve on site before freezing pulse width and epoch windows (see HARDWARE_AUDIT 1.5).
    TO_VERIFY: whether the exported marker column really carries our codes, and the 3D
        source/detector positions (native export has none -> measured digitizer OR virtual
        registration, which must be declared as such in the methods section).
    Plan: export CSV/TXT (Oxy-Hb / Deoxy-Hb / Total-Hb + marker column) -> SNIRF -> MNE-NIRS.
    """

    info = AdapterInfo(
        name="lightnirs",
        device="LIGHTNIRS",
        vendor="Shimadzu",
        status=AdapterStatus.REQUIRES_VENDOR_DOC.value,
        interface="LIGHTNIRS software export (CSV/TXT with marker column) + Trig In (TTL, rising edge)",
        data_path="acquisition_pc/LIGHTNIRS",
        trigger_path="TTL from experiment PC -> Trig In; pulse width must be >= 2 sampling intervals",
        notes="22 ch/unit; sampling interval unresolved (10 ms vs 13.3 ms vs 75 ms); no native 3D coords.",
    )

    def describe(self) -> dict:
        return self.info.as_dict()

    def read_exported_csv(self, path: str):
        """Offline reader for the LIGHTNIRS export; column mapping must be filled from a real file."""
        raise self._unsupported("parsing a LIGHTNIRS CSV export")

    def to_snirf(self, path: str, out_path: str):
        raise self._unsupported("writing SNIRF")
