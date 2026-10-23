#!/usr/bin/env python
"""Machine-readable BPlus software and readiness audit."""
from __future__ import annotations

import argparse
import importlib
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

IMPORTS = {
    "yaml": ("core", True),
    "numpy": ("analysis", True),
    "scipy": ("analysis", True),
    "psychopy": ("experiment", True),
    "pylsl": ("experiment", True),
    "serial": ("experiment", False),
    "tkinter": ("launcher", True),
    "cv2": ("seetapsych", False),
    "seetapsych_lib": ("seetapsych", False),
}


def audit(profile: str = "core") -> dict:
    order = {"core": 0, "analysis": 1, "launcher": 1, "experiment": 2, "seetapsych": 3}
    maximum = order[profile]
    checks = []
    for module, (group, required) in IMPORTS.items():
        if order[group] > maximum and group != profile:
            continue
        try:
            value = importlib.import_module(module)
            checks.append({"name": module, "status": "PASS", "required": required,
                           "version": getattr(value, "__version__", "stdlib")})
        except Exception as exc:
            status = "FAIL" if required else "WARNING"
            checks.append({"name": module, "status": status, "required": required,
                           "detail": f"{type(exc).__name__}: {exc}"})

    config_files = ["configs/protocol.yaml", "configs/triggers.yaml", "configs/sync.yaml"]
    for rel in config_files:
        exists = (ROOT / rel).exists()
        checks.append({"name": rel, "status": "PASS" if exists else "FAIL", "required": True})

    free_gb = shutil.disk_usage(ROOT).free / 1024 ** 3
    minimum_gb = 20 if profile == "experiment" else 5
    checks.append({"name": "disk_free_gb", "status": "PASS" if free_gb >= minimum_gb else "FAIL",
                   "required": True, "value": round(free_gb, 1), "minimum": minimum_gb})
    checks.append({"name": "physical_ttl", "status": "BLOCKED", "required": False,
                   "detail": "Needs Windows experiment PC + trigger interface + EEG/fNIRS physical validation"})
    verdict = "FAIL" if any(x["status"] == "FAIL" for x in checks) else "PASS"
    return {"schema": "bplus.environment.v1", "generated_at": datetime.now(timezone.utc).isoformat(),
            "profile": profile, "verdict": verdict, "python": platform.python_version(),
            "executable": sys.executable, "platform": platform.platform(), "checks": checks}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["core", "analysis", "launcher", "experiment", "seetapsych"],
                        default="core")
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "environment_check.json")
    args = parser.parse_args(argv)
    report = audit(args.profile)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in report["checks"]:
        print(f"[{item['status']}] {item['name']} {item.get('version', item.get('detail', ''))}")
    print(f"[{report['verdict']}] environment profile={args.profile}; report={args.out}")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
