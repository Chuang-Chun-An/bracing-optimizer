"""Convert the exported machinery inventory JSON into Solver inventory rows.

This module is a preparation tool only.  The application runtime reads the
normalized ``data/inventory.json`` through ``JsonInventoryRepository`` and
never depends on this source-export format.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


PROFILE_PATTERN = re.compile(r"H\s*(\d+)\s*[*xX×＊]\s*(\d+)", re.IGNORECASE)
LENGTH_PATTERN = re.compile(
    r"L\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*M",
    re.IGNORECASE,
)


class InventoryConversionError(ValueError):
    pass


def _quantity(row: Mapping[str, Any]) -> int | float:
    total = row.get("總數")
    if total is None:
        total = sum(
            float(row.get(column) or 0)
            for column in ("倉庫數量", "工務所數量", "工務所SITE數量")
        )
    try:
        value = float(total)
    except (TypeError, ValueError) as exc:
        raise InventoryConversionError(f"無效的庫存數量：{total!r}") from exc
    if value < 0:
        raise InventoryConversionError(f"庫存數量不可為負數：{value}")
    return int(value) if value.is_integer() else value


def convert_source_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return one normalized steel-beam row, or None for unrelated material."""

    if not isinstance(row, Mapping):
        raise InventoryConversionError("原始庫存資料列必須是物件。")
    description = str(row.get("品名規格", "") or "").strip()
    if "調整塊" in description:
        return None
    if "支撐樑" in description:
        usage = "支撐"
    elif "圍令樑" in description:
        usage = "圍令"
    else:
        return None

    profile_match = PROFILE_PATTERN.search(description)
    length_match = LENGTH_PATTERN.search(description)
    if profile_match is None or length_match is None:
        code = str(row.get("機料編號", "") or "").strip()
        raise InventoryConversionError(
            f"無法解析規格或長度：{code} {description}"
        )

    length_mm = int(round(float(length_match.group(1)) * 1000))
    if length_mm <= 0:
        raise InventoryConversionError(f"料長必須大於 0：{description}")
    return {
        "ItemCode": str(row.get("機料編號", "") or "").strip(),
        "Spec": f"H{profile_match.group(1)}x{profile_match.group(2)}",
        "Usage": usage,
        "Length": length_mm,
        "Qty": _quantity(row),
    }


def convert_source_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    source_file: str = "",
) -> dict[str, Any]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise InventoryConversionError("原始庫存 JSON 必須是陣列。")

    inventory = []
    excluded_adjustment_blocks = 0
    excluded_unrelated = 0
    for row in rows:
        description = (
            str(row.get("品名規格", "") or "").strip()
            if isinstance(row, Mapping)
            else ""
        )
        converted = convert_source_row(row)
        if converted is not None:
            inventory.append(converted)
        elif "調整塊" in description and "支撐樑" in description:
            excluded_adjustment_blocks += 1
        else:
            excluded_unrelated += 1

    inventory.sort(
        key=lambda item: (
            {"支撐": 0, "圍令": 1}.get(item["Usage"], 99),
            item["Spec"],
            item["Length"],
            item["ItemCode"],
        )
    )
    return {
        "schema_version": 1,
        "source": {
            "type": "machinery_inventory_json_export",
            "file": source_file,
            "total_rows": len(rows),
            "included_rows": len(inventory),
            "excluded_adjustment_blocks": excluded_adjustment_blocks,
            "excluded_unrelated_rows": excluded_unrelated,
        },
        "inventory": inventory,
    }


def convert_file(source_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    source = Path(source_path)
    output = Path(output_path)
    try:
        rows = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InventoryConversionError(f"無法讀取原始庫存 JSON：{source}") from exc
    payload = convert_source_rows(rows, source_file=source.name)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert machinery inventory JSON")
    parser.add_argument("source")
    parser.add_argument("output")
    args = parser.parse_args()
    payload = convert_file(args.source, args.output)
    print(json.dumps(payload["source"], ensure_ascii=False))


if __name__ == "__main__":
    main()
