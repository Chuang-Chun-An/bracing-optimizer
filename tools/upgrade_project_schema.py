"""Offline upgrade of project JSON files to schema version 3.

Schema 3 keeps Column/Beam positions inside each Strut row. DXF recognition
details remain in ``dxf_import_state`` and are not project-level entities.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 3


class ProjectUpgradeError(ValueError):
    """The source JSON cannot be upgraded without guessing project data."""


def _legacy_position_text(values: Sequence[Any]) -> str:
    cleaned = [value for value in values if value not in (None, "")]
    if cleaned:
        try:
            if all(float(value) == 0 for value in cleaned):
                return ""
        except (TypeError, ValueError):
            pass
    return ",".join(str(value).strip() for value in cleaned)


def _normalize_strut(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(row))
    if "BeamPositions" not in normalized:
        normalized["BeamPositions"] = _legacy_position_text(
            (normalized.get("Beam1"), normalized.get("Beam2"))
        )
    if "ColumnPositions" not in normalized:
        normalized["ColumnPositions"] = _legacy_position_text(
            (normalized.get("Column1"), normalized.get("Column2"))
        )
    normalized.setdefault("AssociatedColumnIDs", "")
    normalized.setdefault("AssociatedBeamIDs", "")
    normalized.setdefault("TargetJackRegion", 2)
    for old_key in ("Beam1", "Beam2", "Column1", "Column2"):
        normalized.pop(old_key, None)
    return normalized


def upgrade_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a schema-3 copy without mutating the source mapping."""

    if not isinstance(payload, Mapping):
        raise ProjectUpgradeError("project.json 必須是物件")
    upgraded = copy.deepcopy(dict(payload))
    try:
        source_version = int(upgraded.get("schema_version", 1) or 1)
    except (TypeError, ValueError) as exc:
        raise ProjectUpgradeError("schema_version 不是整數") from exc
    if source_version > SCHEMA_VERSION:
        raise ProjectUpgradeError(
            f"檔案版本 {source_version} 高於升級工具支援版本 {SCHEMA_VERSION}"
        )

    input_data = upgraded.get("input_data")
    if not isinstance(input_data, dict):
        raise ProjectUpgradeError("input_data 必須是物件")
    for table_name in ("walers", "struts", "braces"):
        if not isinstance(input_data.get(table_name), list):
            raise ProjectUpgradeError(f"input_data.{table_name} 必須是陣列")

    input_data["struts"] = [
        _normalize_strut(row)
        for row in input_data["struts"]
        if isinstance(row, Mapping)
    ]
    for obsolete_table in ("columns", "beams", "strut_obstacles"):
        input_data.pop(obsolete_table, None)

    upgraded["schema_version"] = SCHEMA_VERSION
    upgraded.setdefault("dxf_asset", None)
    return upgraded


def upgrade_file(path: str | Path, *, backup: bool = True) -> dict[str, Any]:
    """Upgrade one JSON file atomically and optionally retain its old bytes."""

    project_path = Path(path).resolve()
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    upgraded = upgrade_payload(payload)
    source_version = int(payload.get("schema_version", 1) or 1)
    temporary_path = project_path.with_name(f".{project_path.name}.schema3.tmp")
    backup_path = project_path.with_name(
        f"{project_path.name}.schema{source_version}.bak"
    )
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(upgraded, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if backup:
            shutil.copy2(project_path, backup_path)
        os.replace(temporary_path, project_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return upgraded


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="要升級的 project JSON")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="不建立 .schema2.bak；僅適合已有版本控制的檔案",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    for path in args.paths:
        upgraded = upgrade_file(path, backup=not args.no_backup)
        strut_count = len(upgraded["input_data"]["struts"])
        print(f"{path}: schema 3, struts={strut_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
