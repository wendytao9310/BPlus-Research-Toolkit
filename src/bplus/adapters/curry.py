"""Compumedics Neuroscan SynAmps^2 acquired with CURRY (8)."""
from __future__ import annotations

from .base import AdapterInfo, AdapterStatus, DeviceAdapter


class CurryEEGAdapter(DeviceAdapter):
    """EEG side of the 2-computer chain.

    Verified (docs, 2026-09-22): MNE exposes read_raw_curry / read_raw_cnt / read_raw_edf, and
    `read_raw_curry` since MNE 1.11 REQUIRES the third-party `curryreader` package
    (mne-tools/curry-python-reader, BSD-3, v0.1.2 - very new, so treat as a risk).

    Two paths, both to be validated on the acquisition PC:
      A (native): `.cdt` + `.dpa`/`.ceo` sidecars in the same folder  -> needs curryreader
      B (export): CURRY 8 `File -> Export` to `.cnt` or `.edf`         -> mature readers
    Decision rule: run both once, compare channel count / sampling rate / trigger channel.
    """

    info = AdapterInfo(
        name="curry_eeg",
        device="SynAmps^2",
        vendor="Compumedics Neuroscan",
        status=AdapterStatus.REQUIRES_VENDOR_DOC.value,
        interface="CURRY 8 native .cdt (+ .dpa/.ceo) or Export to .cnt/.edf; TTL trigger input",
        data_path="acquisition_pc/CURRY",
        trigger_path="TTL from experiment PC parallel port / LabJack -> SynAmps^2 trigger input",
        notes="No public SDK; export then read offline. .cdt needs `pip install curryreader`.",
    )

    def describe(self) -> dict:
        return self.info.as_dict()

    def read_exported(self, path: str):
        """Offline reader (implemented via MNE; import is lazy)."""
        import mne

        suffix = path.lower().rsplit(".", 1)[-1]
        if suffix in {"cdt", "dap"}:
            return mne.io.read_raw_curry(path, preload=False, verbose="ERROR")
        if suffix == "cnt":
            return mne.io.read_raw_cnt(path, preload=False, verbose="ERROR")
        if suffix == "edf":
            return mne.io.read_raw_edf(path, preload=False, verbose="ERROR")
        raise ValueError(f"unsupported EEG export {path!r}; expected .cdt/.dap/.cnt/.edf")
