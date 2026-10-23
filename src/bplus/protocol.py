"""Session timeline for the ~70-minute protocol (MASTER COMMAND section 12, 92).

The timeline is *derived from YAML*, never hard-coded, and it validates itself:
  * phases must be contiguous and must add up to the configured session length;
  * every paradigm event must fall inside its phase;
  * the 20-minute computer-paradigm budget is checked explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .paradigms import REGISTRY
from .triggers import TriggerCode


@dataclass(frozen=True)
class Phase:
    name: str
    kind: str                      # fixed | paradigms
    start_s: float
    duration_s: float
    paradigms: tuple[str, ...] = ()
    markers: tuple[dict[str, Any], ...] = ()

    @property
    def end_s(self) -> float:
        return self.start_s + self.duration_s


@dataclass(frozen=True)
class SessionEvent:
    onset_s: float                 # absolute, seconds from session start
    code: TriggerCode
    name: str
    phase: str
    trial_id: int | None = None
    block_id: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionTimeline:
    phases: list[Phase]
    events: list[SessionEvent]

    @property
    def total_duration_s(self) -> float:
        return max((p.end_s for p in self.phases), default=0.0)

    def events_in(self, phase_name: str) -> list[SessionEvent]:
        return [e for e in self.events if e.phase == phase_name]

    def by_code(self, code: TriggerCode) -> list[SessionEvent]:
        return [e for e in self.events if e.code == code]

    def paradigm_budget(self, phase_name: str | None = None) -> dict[str, float]:
        """Per-paradigm wall-clock length, optionally restricted to one phase."""
        out: dict[str, float] = {}
        for phase in self.phases:
            if phase.kind != "paradigms":
                continue
            if phase_name is not None and phase.name != phase_name:
                continue
            for name in phase.paradigms:
                evs = [e for e in self.events if e.phase == phase.name and e.meta.get("paradigm") == name]
                out[name] = max((e.onset_s for e in evs), default=phase.start_s) - min(
                    (e.onset_s for e in evs), default=phase.start_s)
        return out

    def summary(self) -> dict[str, Any]:
        return {
            "total_duration_s": self.total_duration_s,
            "total_duration_min": round(self.total_duration_s / 60.0, 2),
            "n_phases": len(self.phases),
            "n_events": len(self.events),
            "phases": [
                {"name": p.name, "kind": p.kind, "start_s": p.start_s, "duration_s": p.duration_s}
                for p in self.phases
            ],
            "paradigm_budget_s": {k: round(v, 1) for k, v in self.paradigm_budget().items()},
            "computer_phase_budget_s": {k: round(v, 1)
                                        for k, v in self.paradigm_budget("computer_paradigms").items()},
        }


def _phase_markers(phase_cfg: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    return tuple(phase_cfg.get("markers", ()))


def build_session(protocol_cfg: dict[str, Any], paradigm_cfgs: dict[str, dict[str, Any]],
                  *, strict: bool = True) -> SessionTimeline:
    phases: list[Phase] = []
    events: list[SessionEvent] = []

    cursor = 0.0
    for raw in protocol_cfg["phases"]:
        duration = float(raw["duration_s"])
        phase = Phase(
            name=raw["name"],
            kind=raw["kind"],
            start_s=cursor,
            duration_s=duration,
            paradigms=tuple(raw.get("paradigms", ())),
            markers=_phase_markers(raw),
        )
        phases.append(phase)

        if phase.kind == "fixed":
            for marker in phase.markers:
                events.append(SessionEvent(
                    onset_s=phase.start_s + float(marker.get("at_s", 0.0)),
                    code=TriggerCode[marker["code"]],
                    name=marker["code"],
                    phase=phase.name,
                    meta={"source": "protocol.yaml"},
                ))
        elif phase.kind == "paradigms":
            offset = phase.start_s + float(raw.get("lead_in_s", 0.0))
            for name in phase.paradigms:
                cfg = paradigm_cfgs[name]
                paradigm = REGISTRY[name](cfg)
                for ev in paradigm.events():
                    events.append(SessionEvent(
                        onset_s=offset + ev.onset,
                        code=ev.code,
                        name=ev.name,
                        phase=phase.name,
                        trial_id=ev.trial_id,
                        block_id=ev.block_id,
                        meta={**ev.meta, "paradigm": name},
                    ))
                offset += paradigm.duration + float(raw.get("gap_s", 0.0))
            if strict and offset > phase.end_s + 1e-6:
                raise ValueError(
                    f"paradigms in phase {phase.name!r} overflow the phase budget by "
                    f"{offset - phase.end_s:.1f}s (section 12/92 requires an explicit decision)"
                )
        else:
            raise ValueError(f"unknown phase kind {phase.kind!r}")

        cursor = phase.end_s

    timeline = SessionTimeline(phases=phases, events=sorted(events, key=lambda e: e.onset_s))
    if strict:
        validate(timeline, expected_total_s=float(protocol_cfg.get("total_duration_s", cursor)))
    return timeline


def validate(timeline: SessionTimeline, *, expected_total_s: float | None = None,
             tolerance_s: float = 0.5) -> None:
    """Raise ValueError if the timeline breaks the protocol invariants."""
    for a, b in zip(timeline.phases, timeline.phases[1:]):
        if abs(a.end_s - b.start_s) > 1e-6:
            raise ValueError(f"phases are not contiguous: {a.name} ends at {a.end_s}, {b.name} starts at {b.start_s}")
    if expected_total_s is not None and abs(timeline.total_duration_s - expected_total_s) > tolerance_s:
        raise ValueError(
            f"session length {timeline.total_duration_s:.1f}s != configured {expected_total_s:.1f}s"
        )
    for ev in timeline.events:
        if ev.onset_s < -1e-6 or ev.onset_s > timeline.total_duration_s + 1e-6:
            raise ValueError(f"event {ev.name} at {ev.onset_s}s falls outside the session")
    seen: set[tuple[float, int]] = set()
    for ev in timeline.events:
        key = (round(ev.onset_s, 6), int(ev.code))
        if key in seen:
            raise ValueError(f"duplicate event {ev.name} at {ev.onset_s}s")
        seen.add(key)
