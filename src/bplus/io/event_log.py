"""Trigger-log writer: CSV (human/Analysis) + JSONL (append-only audit trail)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ..triggers import LOG_COLUMNS, TriggerEvent


class EventLog:
    def __init__(self, directory: str | Path, *, participant_id: str, session_id: str) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.directory / f"sub-{participant_id}_ses-{session_id}_triggers.csv"
        self.jsonl_path = self.directory / f"sub-{participant_id}_ses-{session_id}_triggers.jsonl"
        self._csv_ready = False

    def append(self, event: TriggerEvent) -> None:
        row = event.as_row()
        is_new = not self.csv_path.exists()
        with self.csv_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=LOG_COLUMNS)
            if is_new:
                writer.writeheader()
            writer.writerow(row)
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._csv_ready = True


def read_event_log(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))
