"""ECG / GSR recorded through the SynAmps^2 auxiliary (bipolar) channels."""
from __future__ import annotations

from .base import AdapterInfo, AdapterStatus, DeviceAdapter


class SynAmpsAuxPhysiologyAdapter(DeviceAdapter):
    """Preferred physiology path: ECG/GSR as AUX channels of the EEG amplifier.

    This is the lowest-risk option because the signals are then sampled by the same
    amplifier/clock as the EEG, so no extra synchronisation is needed (section 16, 43).
    The alternative (BIOPAC MP160 / Thought Technology) must be confirmed against the
    actual lab hardware before an adapter is written.
    """

    info = AdapterInfo(
        name="synamps_aux_physio",
        device="ECG + GSR via SynAmps^2 AUX channels",
        vendor="Compumedics Neuroscan",
        status=AdapterStatus.IMPLEMENTED.value,
        interface="AUX/bipolar input channels on the amplifier (configured in CURRY)",
        data_path="acquisition_pc/CURRY (AUX channels)",
        trigger_path="same TTL as EEG",
        notes="Channel map must be recorded in channels.tsv before the first pilot.",
    )

    def describe(self) -> dict:
        return self.info.as_dict()

    def channel_map(self) -> dict[str, str]:
        """Populated after the first real acquisition; kept empty on purpose."""
        return {}
