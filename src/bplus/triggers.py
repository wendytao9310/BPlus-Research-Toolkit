"""Unified trigger system.

Implements MASTER COMMAND V4.0 sections 57-59:
  * a single trigger-code table (section 57),
  * a trigger log with the required columns (section 58),
  * pluggable backends so DEMO / PILOT / REAL modes share one code path (section 18).

No device API is invented here: the parallel-port / LabJack / LSL backends are the
officially supported PsychoPy and LSL interfaces; vendor SDKs are only referenced by
name and never called.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Protocol

# --------------------------------------------------------------------------------------
# Trigger code table (section 57). Codes 1-9 are a PROJECT-designed extension for the
# session-level phases that section 57 does not cover; they are documented as such.
# --------------------------------------------------------------------------------------


class TriggerCode(IntEnum):
    # -- session phases (PROJECT extension) -------------------------------------------
    SESSION_START = 1
    CONSENT_START = 2
    SETUP_START = 3
    SETUP_END = 4
    QC_START = 5
    QC_END = 6
    SESSION_END = 7

    # -- section 57 (verbatim) ---------------------------------------------------------
    REST_START = 10
    REST_END = 11

    MMN_START = 100
    MMN_STANDARD = 101
    MMN_DEVIANT = 102
    MMN_END = 109

    VFT_START = 200
    VFT_BLOCK = 201
    VFT_REST = 202          # PROJECT extension: rest period onset inside a VFT block
    VFT_END = 209

    NBACK_START = 300
    NBACK_0BACK = 301
    NBACK_2BACK = 302
    NBACK_TARGET = 303
    NBACK_NONTARGET = 304
    NBACK_END = 309

    EMOTION_START = 400
    EMOTION_NEUTRAL = 401
    EMOTION_POSITIVE = 402
    EMOTION_NEGATIVE = 403
    EMOTION_END = 409
    EMOTION_CUE = 410       # PROJECT extension: trial cue onset
    EMOTION_RATING = 411    # PROJECT extension: valence/arousal rating onset
    EMOTION_BLOCK = 412     # PROJECT extension: emotion block onset (LIT: block design)

    INTERVIEW_START = 500
    INTERVIEW_QUESTION = 501
    INTERVIEW_ANSWER = 502
    INTERVIEW_END = 509

    RECOVERY_START = 600
    RECOVERY_END = 601


@dataclass
class TriggerEvent:
    """One logged trigger (section 58)."""

    participant_id: str
    session_id: str
    event_code: int
    event_name: str
    timestamp: str
    experiment_clock: float
    hardware_clock: float | None = None
    trial_id: int | None = None
    block_id: int | None = None
    device: str = "experiment_pc"
    software: str = "bplus-mvp0"
    phase: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def as_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["meta"] = json.dumps(row["meta"], ensure_ascii=False, sort_keys=True)
        row["hardware_clock"] = "" if self.hardware_clock is None else self.hardware_clock
        row["trial_id"] = "" if self.trial_id is None else self.trial_id
        row["block_id"] = "" if self.block_id is None else self.block_id
        row["phase"] = "" if self.phase is None else self.phase
        return row


# --------------------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------------------


class TriggerBackend(Protocol):
    name: str
    status: str  # IMPLEMENTED | SIMULATED | PLACEHOLDER | REQUIRES_VENDOR_SDK

    def emit(self, code: int) -> float | None:  # pragma: no cover - interface
        """Push one code to the hardware and return the hardware clock if available."""


class SimulatedBackend:
    """DEMO mode: records the code, returns the local monotonic clock."""

    name = "simulated"
    status = "SIMULATED"

    def emit(self, code: int) -> float:
        return time.perf_counter()


class LogOnlyBackend:
    """只记录、不驱动硬件。

    真机运行时，硬件边沿由 `TriggerPulse`（挂在 win.callOnFlip 上）负责；
    这个后端只把事件写进日志，避免同一路并行口被驱动两次。
    """

    name = "log-only"
    status = "IMPLEMENTED"

    def emit(self, code: int) -> float:
        return time.perf_counter()


class ParallelPortBackend:
    """REAL mode on Windows: uses the official PsychoPy parallel-port interface."""

    name = "parallel"
    status = "IMPLEMENTED"

    def __init__(self, address: int = 0x0378) -> None:
        from psychopy import parallel  # imported lazily: only used on the experiment PC

        self._port = parallel.ParallelPort(address=address)
        self._port.setData(0)  # type: ignore[attr-defined]

    def emit(self, code: int) -> float:
        self._port.setData(int(code))  # type: ignore[attr-defined]
        stamp = time.perf_counter()
        self._port.setData(0)  # type: ignore[attr-defined]
        return stamp


class LabJackBackend:
    """REAL mode: PsychoPy's LabJack U3/U6 interface (section 16/§57 of the spec)."""

    name = "labjack"
    status = "IMPLEMENTED"

    def __init__(self, device: str = "U3") -> None:
        from psychopy.hardware import labjacks

        self._jack = labjacks.LabJackU3() if device.upper() == "U3" else labjacks.LabJackU6()

    def emit(self, code: int) -> float:
        self._jack.setData(int(code))
        stamp = time.perf_counter()
        self._jack.setData(0)
        return stamp


class LSLMarkerBackend:
    """Any mode: publishes the trigger as an LSL marker stream (section 59)."""

    name = "lsl"
    status = "IMPLEMENTED"

    def __init__(self, stream_name: str = "BPlus_Markers") -> None:
        from pylsl import StreamInfo, StreamOutlet  # lazy: only needed with LSL installed

        info = StreamInfo(stream_name, "Markers", 1, 0, "int32", "bplus-markers")
        self._outlet = StreamOutlet(info)

    def emit(self, code: int) -> float | None:
        self._outlet.push_sample([int(code)])
        return None


def make_backend(name: str, **kwargs: Any) -> TriggerBackend:
    """Create a TriggerManager backend.

    Physical TTL backends are intentionally blocked here.

    Parallel/LabJack TTL must use the frame-synchronised TriggerPulse path,
    which applies the logical-to-physical mapping and enforces pulse width.
    The legacy emit() implementations raise and lower the line immediately
    and therefore are not safe for Pilot-0 acquisition.
    """
    table = {
        "log-only": LogOnlyBackend,
        "simulated": SimulatedBackend,
        "lsl": LSLMarkerBackend,
    }

    if name in {"parallel", "labjack"}:
        raise RuntimeError(
            f"{name!r} is a physical TTL backend and is disabled in "
            "TriggerManager/make_backend because legacy emit() does not "
            "enforce pulse width. Use the TriggerPulse physical-output path."
        )

    if name not in table:
        known = sorted([*table, "parallel", "labjack"])
        raise ValueError(f"unknown trigger backend {name!r}; known: {known}")

    return table[name](**kwargs)  # type: ignore[return-value]


# --------------------------------------------------------------------------------------
# Manager
# --------------------------------------------------------------------------------------


class TriggerManager:
    """Single entry point for every marker in the protocol."""

    def __init__(
        self,
        participant_id: str,
        session_id: str,
        backends: list[TriggerBackend] | None = None,
        *,
        log=None,
        clock=time.perf_counter,
    ) -> None:
        self.participant_id = participant_id
        self.session_id = session_id
        self.backends = backends if backends is not None else [SimulatedBackend()]
        self.log = log
        self._clock = clock
        self.events: list[TriggerEvent] = []

    def send(
        self,
        code: TriggerCode | int,
        *,
        trial_id: int | None = None,
        block_id: int | None = None,
        phase: str | None = None,
        device: str = "experiment_pc",
        **meta: Any,
    ) -> TriggerEvent:
        code_int = int(code)
        try:
            name = TriggerCode(code_int).name
        except ValueError:
            name = f"UNKNOWN_{code_int}"
        hardware_clock = None
        for backend in self.backends:
            stamp = backend.emit(code_int)
            if hardware_clock is None:
                hardware_clock = stamp
        event = TriggerEvent(
            participant_id=self.participant_id,
            session_id=self.session_id,
            event_code=code_int,
            event_name=name,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            experiment_clock=self._clock(),
            hardware_clock=hardware_clock,
            trial_id=trial_id,
            block_id=block_id,
            device=device,
            phase=phase,
            meta=dict(meta),
        )
        self.events.append(event)
        if self.log is not None:
            self.log.append(event)
        return event

    # -- convenience wrappers ---------------------------------------------------------
    def start(self) -> None:
        self.send(TriggerCode.SESSION_START)

    def end(self) -> None:
        self.send(TriggerCode.SESSION_END)


LOG_COLUMNS = [
    "participant_id",
    "session_id",
    "event_code",
    "event_name",
    "timestamp",
    "experiment_clock",
    "hardware_clock",
    "trial_id",
    "block_id",
    "device",
    "software",
    "phase",
    "meta",
]
