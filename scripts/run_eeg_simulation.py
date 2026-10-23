#!/usr/bin/env python3
"""Run the CURRY-shaped EEG/MMN software validation loop."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from bplus.eeg import read_curry_metadata, run_mmn_simulation


def _curry_metadata(path: Path | None) -> tuple[float, list[str], dict]:
    if path is None:
        return 1000.0, [], {}
    return read_curry_metadata(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="BPlus EEG/MMN 软件模拟闭环")
    parser.add_argument("--curry", type=Path, help="可选：只读取 CURRY 文件元数据以匹配采样率和通道")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--participant", default="SIM-EEG001")
    parser.add_argument("--session", default="1")
    args = parser.parse_args()
    sfreq, channels, metadata = _curry_metadata(args.curry)
    paths = run_mmn_simulation(args.output, participant_id=args.participant,
                               session_id=args.session, sfreq=sfreq,
                               channel_names=channels or None, source_metadata=metadata)
    print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
