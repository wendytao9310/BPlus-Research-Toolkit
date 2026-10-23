"""Configuration loading (all thresholds/parameters live in YAML, never hard-coded)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.environ.get("BPLUS_CONFIG_DIR", ROOT / "configs"))


def load_yaml(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.is_absolute():
        p = CONFIG_DIR / p
    with p.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def paradigm_config(name: str) -> dict[str, Any]:
    return load_yaml(Path("paradigms") / f"{name}.yaml")


def protocol_config() -> dict[str, Any]:
    return load_yaml("protocol.yaml")


def triggers_config() -> dict[str, Any]:
    return load_yaml("triggers.yaml")


def devices_config() -> dict[str, Any]:
    return load_yaml("devices.yaml")
