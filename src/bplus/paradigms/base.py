"""Paradigm base class: every paradigm is a pure event generator.

Keeping paradigms as *event generators* (instead of monolithic PsychoPy scripts) makes
them (a) unit-testable without a display, (b) reusable across DEMO/PILOT/REAL modes and
(c) auditable against the literature, as required by MASTER COMMAND sections 6-8 and 67.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..triggers import TriggerCode


@dataclass(frozen=True)
class Event:
    """One marker to be sent at `onset` seconds after the paradigm started."""

    onset: float
    code: TriggerCode
    name: str
    trial_id: int | None = None
    block_id: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class Paradigm(ABC):
    name: str = "unnamed"

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        self.evidence = cfg.get("evidence", {})

    @abstractmethod
    def events(self) -> list[Event]:
        """All markers, sorted by onset, onset relative to paradigm start."""

    @property
    def duration(self) -> float:
        evs = self.events()
        return max((e.onset for e in evs), default=0.0) + float(self.cfg.get("tail_s", 0.0))

    # -- helpers ----------------------------------------------------------------------
    @staticmethod
    def _sorted(events: list[Event]) -> list[Event]:
        return sorted(events, key=lambda e: (e.onset, int(e.code)))

    def describe(self) -> dict[str, Any]:
        evs = self.events()
        return {
            "paradigm": self.name,
            "events": len(evs),
            "duration_s": round(self.duration, 3),
            "evidence": self.evidence,
        }
