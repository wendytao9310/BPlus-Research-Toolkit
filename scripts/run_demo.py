#!/usr/bin/env python
"""DEMO-mode session runner (no hardware, section 18).

    python scripts/run_demo.py --participant DEMO01 --session 1 --out data/demo
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bplus.session import build_demo_session  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BPlus DEMO-mode session (no hardware)")
    parser.add_argument("--participant", default="DEMO01")
    parser.add_argument("--session", default="1")
    parser.add_argument("--out", default="data/demo")
    parser.add_argument("--json", action="store_true", help="print the manifest only")
    args = parser.parse_args(argv)

    result = build_demo_session(args.participant, args.session, out_dir=args.out)
    manifest = result.manifest

    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    tl = manifest["timeline"]
    print(f"mode            : {manifest['mode']}")
    print(f"session length  : {tl['total_duration_min']} min ({tl['total_duration_s']} s)")
    print(f"phases          : {tl['n_phases']}")
    print(f"trigger events  : {tl['n_events']}")
    print("\nphase plan:")
    for ph in tl["phases"]:
        print(f"  {ph['start_s']:>7.0f}s  +{ph['duration_s']:>6.0f}s  {ph['name']} ({ph['kind']})")
    budget = tl.get("computer_phase_budget_s", {})
    if budget:
        phase = next(p for p in tl["phases"] if p["name"] == "computer_paradigms")
        print(f"\ncomputer-paradigm budget (phase window {phase['duration_s']:.0f}s):")
        for name, seconds in budget.items():
            print(f"  {name:<9} {seconds:>6.1f}s")
        used = sum(budget.values())
        print(f"  {'used':<9} {used:>6.1f}s   margin {phase['duration_s'] - used:>6.1f}s")
    print("\nadapters:")
    for ad in manifest["adapters"]:
        print(f"  {ad['name']:<22} {ad['status']:<22} {ad['device']}")
    print(f"\ntrigger log: {manifest['trigger_log']['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
