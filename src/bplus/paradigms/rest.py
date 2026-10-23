"""Rest / baseline (section 28): 3 min eyes-open fixation, used for personal baseline."""
from __future__ import annotations

from ..triggers import TriggerCode
from .base import Event, Paradigm


class RestParadigm(Paradigm):
    name = "rest"

    def events(self) -> list[Event]:
        duration = float(self.cfg.get("duration_s", 180.0))
        return self._sorted([
            Event(0.0, TriggerCode.REST_START, "REST_START", meta={"eyes": self.cfg.get("eyes", "open")}),
            Event(duration, TriggerCode.REST_END, "REST_END"),
        ])
