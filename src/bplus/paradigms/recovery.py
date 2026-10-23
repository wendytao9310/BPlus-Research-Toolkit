"""Recovery (section 29): post-task baseline used for the recovery index."""
from __future__ import annotations

from ..triggers import TriggerCode
from .base import Event, Paradigm


class RecoveryParadigm(Paradigm):
    name = "recovery"

    def events(self) -> list[Event]:
        duration = float(self.cfg.get("duration_s", 120.0))
        return self._sorted([
            Event(0.0, TriggerCode.RECOVERY_START, "RECOVERY_START"),
            Event(duration, TriggerCode.RECOVERY_END, "RECOVERY_END"),
        ])
