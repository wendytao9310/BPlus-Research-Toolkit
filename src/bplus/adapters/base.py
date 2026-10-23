"""Device adapters.

MASTER COMMAND section 17 forbids inventing vendor APIs. Every adapter therefore declares
exactly how real it is, and any method that would need a vendor SDK raises a message that
says which document or installer is required instead of pretending to work.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class AdapterStatus(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"
    SIMULATED = "SIMULATED"
    PLACEHOLDER = "PLACEHOLDER"
    REQUIRES_VENDOR_SDK = "REQUIRES_VENDOR_SDK"
    REQUIRES_VENDOR_DOC = "REQUIRES_VENDOR_DOC"


@dataclass
class AdapterInfo:
    name: str
    device: str
    vendor: str
    status: str
    interface: str
    data_path: str
    trigger_path: str
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class DeviceAdapter(ABC):
    """Minimal lifecycle shared by every device."""

    info: AdapterInfo

    def start(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Machine-readable status, used by the deployment report."""

    def _unsupported(self, what: str) -> NotImplementedError:
        return NotImplementedError(
            f"{self.info.name}: {what} needs {self.info.status}. "
            f"Interface={self.info.interface}. Notes={self.info.notes}"
        )
