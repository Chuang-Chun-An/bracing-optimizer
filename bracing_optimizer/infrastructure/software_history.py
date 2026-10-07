"""Read the packaged initial-development-history projection."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bracing_optimizer.application.software_information import (
    HISTORY_UNAVAILABLE_MESSAGE,
    SoftwareHistoryEntry,
    SoftwareHistoryLoadResult,
)


LOGGER = logging.getLogger(__name__)
SOFTWARE_HISTORY_SCHEMA_VERSION = 1
SOFTWARE_HISTORY_SOURCE_HEADING = "起始歷史紀錄（截至 2026/09/28 早上）"


class SoftwareHistoryValidationError(ValueError):
    """Raised internally when the packaged resource violates its contract."""


def _parse_history_payload(payload: Any) -> tuple[SoftwareHistoryEntry, ...]:
    if not isinstance(payload, Mapping):
        raise SoftwareHistoryValidationError("歷程資料必須是 JSON object。")

    schema_version = payload.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SOFTWARE_HISTORY_SCHEMA_VERSION
    ):
        raise SoftwareHistoryValidationError(
            "software_history schema_version 必須為 1。"
        )
    if payload.get("source_heading") != SOFTWARE_HISTORY_SOURCE_HEADING:
        raise SoftwareHistoryValidationError("歷程來源標題不符。")

    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise SoftwareHistoryValidationError("歷程 entries 必須是非空白陣列。")

    entries: list[SoftwareHistoryEntry] = []
    expected_keys = {"date_label", "record"}
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, Mapping):
            raise SoftwareHistoryValidationError(
                f"歷程 entry {index} 必須是 JSON object。"
            )
        if set(raw_entry) != expected_keys:
            raise SoftwareHistoryValidationError(
                f"歷程 entry {index} 欄位必須為 date_label、record。"
            )
        date_label = raw_entry["date_label"]
        record = raw_entry["record"]
        if not isinstance(date_label, str) or not date_label.strip():
            raise SoftwareHistoryValidationError(
                f"歷程 entry {index} 的 date_label 必須是非空白字串。"
            )
        if not isinstance(record, str) or not record.strip():
            raise SoftwareHistoryValidationError(
                f"歷程 entry {index} 的 record 必須是非空白字串。"
            )
        entries.append(SoftwareHistoryEntry(date_label=date_label, record=record))
    return tuple(entries)


class SoftwareHistoryRepository:
    """Load a validated history projection without leaking failures to the UI."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> SoftwareHistoryLoadResult:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            entries = _parse_history_payload(payload)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            SoftwareHistoryValidationError,
        ) as exc:
            LOGGER.warning(
                "Unable to load software history from %s: %s",
                self.path,
                exc,
                exc_info=True,
            )
            return SoftwareHistoryLoadResult(
                available=False,
                message=HISTORY_UNAVAILABLE_MESSAGE,
            )
        return SoftwareHistoryLoadResult(available=True, entries=entries)


__all__ = [
    "SOFTWARE_HISTORY_SCHEMA_VERSION",
    "SOFTWARE_HISTORY_SOURCE_HEADING",
    "SoftwareHistoryRepository",
    "SoftwareHistoryValidationError",
]
