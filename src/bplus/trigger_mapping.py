"""Logical BPlus event codes -> physical TTL codes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


DEFAULT_MAP_PATH = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "trigger_physical_map.yaml"
)


@dataclass(frozen=True)
class PhysicalTriggerMap:
    logical_to_physical: dict[int, int]
    physical_code_min: int
    physical_code_max: int
    low_code: int = 0

    @classmethod
    def from_yaml(
        cls,
        path: str | Path = DEFAULT_MAP_PATH,
    ) -> "PhysicalTriggerMap":
        path = Path(path)
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))

        mapping = {
            int(logical): int(physical)
            for logical, physical in cfg["mapping"].items()
        }

        obj = cls(
            logical_to_physical=mapping,
            physical_code_min=int(cfg["physical_code_min"]),
            physical_code_max=int(cfg["physical_code_max"]),
            low_code=int(cfg.get("low_code", 0)),
        )

        obj.validate()
        return obj

    def validate(self) -> None:
        if not self.logical_to_physical:
            raise ValueError("physical trigger mapping is empty")

        physical = list(self.logical_to_physical.values())

        if len(physical) != len(set(physical)):
            raise ValueError("duplicate physical trigger codes detected")

        if self.low_code in physical:
            raise ValueError(
                f"LOW/reset code {self.low_code} cannot be used as an event code"
            )

        invalid = sorted(
            code
            for code in physical
            if not self.physical_code_min <= code <= self.physical_code_max
        )

        if invalid:
            raise ValueError(
                "physical trigger codes outside allowed range "
                f"{self.physical_code_min}..{self.physical_code_max}: {invalid}"
            )

    def to_physical(self, logical_code: int) -> int:
        logical_code = int(logical_code)

        try:
            return self.logical_to_physical[logical_code]
        except KeyError as exc:
            raise KeyError(
                f"logical trigger code {logical_code} has no physical TTL mapping"
            ) from exc

    def to_logical(self, physical_code: int) -> int:
        physical_code = int(physical_code)

        reverse = {
            physical: logical
            for logical, physical in self.logical_to_physical.items()
        }

        try:
            return reverse[physical_code]
        except KeyError as exc:
            raise KeyError(
                f"physical TTL code {physical_code} has no logical trigger mapping"
            ) from exc
