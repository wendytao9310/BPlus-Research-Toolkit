"""Transparent participant-facing descriptions derived from numeric metrics."""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from .. import config as cfg_mod


@lru_cache(maxsize=1)
def interpretation_config() -> dict[str, Any]:
    return cfg_mod.load_yaml("report_interpretation.yaml")


def describe_metric(metric: str, value: Any) -> tuple[str, str]:
    """Return (short state, evidence basis) without making a clinical claim."""
    if value is None:
        return "Insufficient data", "This measure was not obtained"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "Result recorded", "Non-numeric result"
    if not math.isfinite(numeric):
        return "Insufficient data", "The measure is not a finite numeric value"
    cfg = interpretation_config()
    spec = (cfg.get("metrics") or {}).get(metric)
    if not spec:
        return "Current result obtained", cfg["disclaimer"]
    for band in spec.get("bands", []):
        if numeric < float(band["max"]):
            return str(band["label"]), cfg["disclaimer"]
    return "Researcher review required", cfg["disclaimer"]


__all__ = ["describe_metric", "interpretation_config"]
