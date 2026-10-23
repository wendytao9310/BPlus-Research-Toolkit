"""Pre-session checks shared by the launcher and command-line workflows."""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config


@dataclass
class Check:
    name: str
    status: str
    detail: str
    blocking: bool = True


def run_preflight(participant_id: str, session_id: str, *, mode: str, paradigm: str,
                  out_dir: str | Path) -> dict:
    checks: list[Check] = []
    pid_ok = bool(re.fullmatch(r"[A-Za-z0-9_-]{2,32}", participant_id))
    checks.append(Check("participant_id", "PASS" if pid_ok else "FAIL",
                        "2-32 characters: letters, numbers, _ or -"))
    checks.append(Check("session_id", "PASS" if bool(session_id.strip()) else "FAIL", "non-empty"))
    for rel in ("protocol.yaml", "triggers.yaml", "sync.yaml", f"paradigms/{paradigm}.yaml"):
        try:
            config.load_yaml(rel)
            checks.append(Check(f"config:{rel}", "PASS", "readable"))
        except Exception as exc:
            checks.append(Check(f"config:{rel}", "FAIL", str(exc)))
    free = shutil.disk_usage(Path(out_dir).resolve().parent if Path(out_dir).resolve().parent.exists() else Path.cwd()).free
    minimum_gb = 20 if mode == "REAL" else 5
    checks.append(Check("disk_space", "PASS" if free >= minimum_gb * 1024 ** 3 else "FAIL",
                        f"{free / 1024 ** 3:.1f} GB free; minimum {minimum_gb} GB for {mode}"))
    if mode == "REAL":
        checks.append(Check("psychopy", "PASS" if importlib.util.find_spec("psychopy") else "FAIL",
                            "required for real visual/audio presentation"))
        checks.append(Check("physical_trigger", "FAIL",
                            "P0-4 TTL validation is not signed off; real acquisition remains blocked"))
    else:
        checks.append(Check("hardware", "WARNING", "DEMO/PILOT software path; no physical device claim", False))
    if paradigm == "emotion" and mode == "REAL":
        from .stimuli import validate_library
        validation = validate_library()
        checks.append(Check("emotion_stimuli", "PASS" if validation.ok else "FAIL",
                            "validated" if validation.ok else "; ".join(validation.blockers[:6])))
    verdict = "FAIL" if any(c.blocking and c.status == "FAIL" for c in checks) else "PASS"
    report = {"schema": "bplus.preflight.v1", "timestamp": datetime.now(timezone.utc).isoformat(),
              "participant_id": participant_id, "session_id": session_id, "mode": mode,
              "paradigm": paradigm, "verdict": verdict, "checks": [asdict(c) for c in checks]}
    target = Path(out_dir) / f"sub-{participant_id}_ses-{session_id}_preflight_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["path"] = str(target)
    return report
