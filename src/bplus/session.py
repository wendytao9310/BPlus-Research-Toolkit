"""Session assembly: configs -> timeline -> trigger log (DEMO mode)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config as cfg_mod
from .adapters import (AseeProAdapter, AudioAdapter, CameraAdapter, CurryEEGAdapter,
                       LightNIRSAdapter, SeetaPsychAdapter, SynAmpsAuxPhysiologyAdapter)
from .io import EventLog
from .protocol import SessionTimeline, build_session
from .triggers import TriggerManager, LogOnlyBackend


@dataclass
class SessionResult:
    timeline: SessionTimeline
    out_dir: Path
    manifest: dict[str, Any]


def adapter_report() -> list[dict[str, Any]]:
    return [a().describe() for a in (
        CurryEEGAdapter, LightNIRSAdapter, AseeProAdapter,
        SynAmpsAuxPhysiologyAdapter, CameraAdapter, AudioAdapter,
        SeetaPsychAdapter,
    )]


def build_demo_session(participant_id: str, session_id: str, *, out_dir: str | Path,
                       protocol: dict[str, Any] | None = None,
                       paradigm_names: tuple[str, ...] = ("rest", "mmn", "vft", "nback", "emotion"),
                       ) -> SessionResult:
    protocol_cfg = protocol or cfg_mod.protocol_config()
    # Keep the current formal launcher selection separate from compatibility
    # with archived protocol files.  If an older protocol still names a
    # paradigm (for example ``recovery``), load it only for timeline replay;
    # this does not add it back to the current launcher or formal workflow.
    protocol_names = {
        name
        for phase in protocol_cfg.get("phases", [])
        for name in phase.get("paradigms", [])
    }
    requested_names = set(paradigm_names) | protocol_names
    paradigm_cfgs = {name: cfg_mod.paradigm_config(name) for name in requested_names}
    timeline = build_session(protocol_cfg, paradigm_cfgs, strict=True)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    log = EventLog(out, participant_id=participant_id, session_id=session_id)
    manager = TriggerManager(
        participant_id=participant_id,
        session_id=session_id,
        # DEMO mode never drives physical TTL hardware.
        # Real TTL output is handled only by TriggerPulse in the PsychoPy path.
        backends=[LogOnlyBackend()],
        log=log,
    )

    manager.start()
    for ev in timeline.events:
        manager.send(ev.code, trial_id=ev.trial_id, block_id=ev.block_id, phase=ev.phase,
                     paradigm=ev.meta.get("paradigm"), **{k: v for k, v in ev.meta.items() if k != "paradigm"})
    manager.end()

    manifest = {
        "participant_id": participant_id,
        "session_id": session_id,
        "mode": protocol_cfg.get("mode", "DEMO"),
        "timeline": timeline.summary(),
        "paradigm_evidence": {name: c.get("evidence", {}) for name, c in paradigm_cfgs.items()},
        "adapters": adapter_report(),
        "trigger_log": {"csv": str(log.csv_path), "jsonl": str(log.jsonl_path),
                        "n_events": len(manager.events)},
    }
    (out / f"sub-{participant_id}_ses-{session_id}_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return SessionResult(timeline=timeline, out_dir=out, manifest=manifest)
