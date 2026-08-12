"""Headless AutoLISP event adapter used by the main Solver application."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from project_data import TABLE_SPECS, build_input_row


EVENT_FILE_NAME = "support_distribution_uv_cad_builder_temp.json"
DEFAULT_TEMP_PATH = Path(tempfile.gettempdir()) / EVENT_FILE_NAME
POLL_INTERVAL_MS = 500

TABLE_ALIASES = {
    "waler": "walers",
    "walers": "walers",
    "support": "struts",
    "supports": "struts",
    "strut": "struts",
    "struts": "struts",
    "brace": "braces",
    "braces": "braces",
}
COORDINATE_FIELDS = ("StartX", "StartY", "EndX", "EndY")


def _table_key(table_name: str) -> str:
    key = TABLE_ALIASES.get(str(table_name).strip().lower())
    if key is None:
        raise ValueError(f"不支援的 CAD 事件類型：{table_name}")
    return key


def _normalize_coordinates(values: dict[str, Any]) -> None:
    coordinates = []
    for field in COORDINATE_FIELDS:
        try:
            number = float(values.get(field, ""))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"CAD 事件的 {field} 必須是數字。") from exc
        if not math.isfinite(number):
            raise ValueError(f"CAD 事件的 {field} 必須是有限數字。")
        values[field] = int(number) if number.is_integer() else number
        coordinates.append(number)
    if math.hypot(
        coordinates[2] - coordinates[0],
        coordinates[3] - coordinates[1],
    ) <= 0:
        raise ValueError("CAD 事件的線段長度必須大於 0。")


class CadEventReader:
    """Read and validate the small JSON envelope written by AutoLISP."""

    @staticmethod
    def load(path: str | Path) -> dict:
        event = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(event, dict):
            raise ValueError("暫存 JSON 最上層必須是物件。")
        if event.get("event_id") is None:
            raise ValueError("暫存 JSON 缺少 event_id。")
        _table_key(str(event.get("type", "")).strip().lower())
        if not isinstance(event.get("data"), dict):
            raise ValueError("暫存 JSON 的 data 必須是物件。")
        return event


class CadEventMapper:
    """Convert a CAD event into one complete Solver input row without owning data."""

    @staticmethod
    def build_row(
        table_name: str,
        values: Mapping[str, Any],
        existing_rows: Sequence[dict],
    ) -> dict:
        key = _table_key(table_name)
        if not isinstance(values, Mapping):
            raise ValueError("CAD 事件的 data 必須是物件。")
        normalized_values = dict(values)
        _normalize_coordinates(normalized_values)
        return build_input_row(key, normalized_values, existing_rows)

    @classmethod
    def map_event(
        cls,
        event: Mapping[str, Any],
        rows_by_table: Mapping[str, Sequence[dict]],
    ) -> tuple[str, dict]:
        if not isinstance(event, Mapping):
            raise ValueError("CAD 事件必須是物件。")
        table_name = _table_key(str(event.get("type", "")).strip().lower())
        values = event.get("data")
        if not isinstance(values, Mapping):
            raise ValueError("CAD 事件的 data 必須是物件。")
        return table_name, cls.build_row(
            table_name,
            values,
            rows_by_table.get(table_name, ()),
        )


class TempEventWatcher:
    """Read one pending event and delete only the event that was committed."""

    def __init__(self, temp_path: str | Path = DEFAULT_TEMP_PATH) -> None:
        self.temp_path = Path(temp_path)
        self.last_event_id: Any = None

    def check_new_event(self) -> dict | None:
        if not self.temp_path.is_file():
            return None
        event = CadEventReader.load(self.temp_path)
        event_id = event["event_id"]
        if event_id == self.last_event_id:
            return None
        return event

    def acknowledge(self, event: Mapping[str, Any]) -> None:
        """Record a committed event and delete it unless a newer event replaced it."""
        event_id = event["event_id"]
        if self.temp_path.is_file():
            current_event = CadEventReader.load(self.temp_path)
            if current_event.get("event_id") == event_id:
                self.temp_path.unlink()
        self.last_event_id = event_id


__all__ = [
    "DEFAULT_TEMP_PATH",
    "EVENT_FILE_NAME",
    "POLL_INTERVAL_MS",
    "TABLE_SPECS",
    "CadEventMapper",
    "CadEventReader",
    "TempEventWatcher",
]
