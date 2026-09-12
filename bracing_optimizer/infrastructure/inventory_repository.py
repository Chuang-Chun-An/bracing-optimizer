"""Inventory data-source boundary.

The application consumes repository rows only while initializing the Settings
tab.  Solver code never reads JSON, Excel, SQL, or HTTP sources directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


INVENTORY_COLUMNS = ("ItemCode", "Spec", "Usage", "Length", "Qty")


class InventoryRepositoryError(ValueError):
    pass


def _first_value(source: Mapping[str, Any], names: Sequence[str], default=""):
    for name in names:
        if name in source:
            return source[name]
    return default


def normalize_inventory_row(source: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        raise InventoryRepositoryError("庫存資料列必須是物件。")

    row = {
        "ItemCode": _first_value(
            source,
            ("ItemCode", "item_code", "itemCode", "機料編號", "料號"),
        ),
        "Spec": _first_value(
            source,
            ("Spec", "spec", "material_spec", "規格", "材料規格"),
        ),
        "Usage": _first_value(
            source,
            ("Usage", "usage", "用途"),
        ),
        "Length": _first_value(
            source,
            ("Length", "length", "長度", "料長"),
        ),
        "Qty": _first_value(
            source,
            ("Qty", "qty", "quantity", "數量", "庫存數量"),
        ),
    }
    row["ItemCode"] = str(row["ItemCode"] or "").strip()
    row["Spec"] = str(row["Spec"] or "").strip()
    row["Usage"] = str(row["Usage"] or "").strip()
    return row


class InventoryRepository(ABC):
    """Replaceable inventory source used to populate application settings."""

    @abstractmethod
    def list_items(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class JsonInventoryRepository(InventoryRepository):
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def list_items(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise InventoryRepositoryError(
                f"無法讀取庫存 JSON：{self.path}\n{exc}"
            ) from exc

        rows = payload.get("inventory", []) if isinstance(payload, Mapping) else payload
        if not isinstance(rows, list):
            raise InventoryRepositoryError("inventory.json 的 inventory 必須是陣列。")
        return [normalize_inventory_row(row) for row in rows]


class InMemoryInventoryRepository(InventoryRepository):
    """Small adapter for tests and future service integrations."""

    def __init__(self, rows: Sequence[Mapping[str, Any]]):
        self._rows = [normalize_inventory_row(row) for row in rows]

    def list_items(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._rows)


__all__ = [
    "INVENTORY_COLUMNS",
    "InventoryRepository",
    "InventoryRepositoryError",
    "JsonInventoryRepository",
    "InMemoryInventoryRepository",
    "normalize_inventory_row",
]
