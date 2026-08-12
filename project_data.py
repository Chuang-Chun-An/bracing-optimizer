"""Shared input schema and the single project-data model used by the Solver."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from typing import Any


TABLE_SPECS = {
    "walers": {
        "id_field": "WalerID",
        "id_prefix": "W",
        "columns": ("WalerID", "StartX", "StartY", "EndX", "EndY", "material_spec", "Remark"),
        "defaults": {
            "StartX": "",
            "StartY": "",
            "EndX": "",
            "EndY": "",
            "material_spec": "",
            "Remark": "",
        },
    },
    "struts": {
        "id_field": "StrutID",
        "id_prefix": "S",
        "columns": (
            "StrutID",
            "FromWaler",
            "ToWaler",
            "StartX",
            "StartY",
            "EndX",
            "EndY",
            "material_spec",
            "BeamPositions",
            "ColumnPositions",
            "AssociatedColumnIDs",
            "AssociatedBeamIDs",
            "FromBraceToWalerStartLen",
            "FromBraceToWalerEndLen",
            "ToBraceToWalerStartLen",
            "ToBraceToWalerEndLen",
            "TargetJackRegion",
            "Zoning",
        ),
        "defaults": {
            "FromWaler": "",
            "ToWaler": "",
            "StartX": "",
            "StartY": "",
            "EndX": "",
            "EndY": "",
            "material_spec": "",
            "BeamPositions": "",
            "ColumnPositions": "",
            "AssociatedColumnIDs": "",
            "AssociatedBeamIDs": "",
            "FromBraceToWalerStartLen": 0,
            "FromBraceToWalerEndLen": 0,
            "ToBraceToWalerStartLen": 0,
            "ToBraceToWalerEndLen": 0,
            "TargetJackRegion": 2,
            "Zoning": "",
        },
    },
    "braces": {
        "id_field": "BraceID",
        "id_prefix": "B",
        "columns": (
            "BraceID",
            "FromWaler",
            "ToWaler",
            "StartX",
            "StartY",
            "EndX",
            "EndY",
        ),
        "defaults": {
            "FromWaler": "",
            "ToWaler": "",
            "StartX": "",
            "StartY": "",
            "EndX": "",
            "EndY": "",
        },
    },
    "inventory": {
        "id_field": None,
        "id_prefix": None,
        "columns": ("Length", "Qty"),
        "defaults": {
            "Length": "",
            "Qty": "",
        },
    },
}

TABLE_COLUMNS = {
    table_name: tuple(spec["columns"])
    for table_name, spec in TABLE_SPECS.items()
}
GEOMETRY_TABLES = ("walers", "struts", "braces")


def _legacy_position_list(values: Sequence[Any]) -> str:
    cleaned = [value for value in values if value not in (None, "")]
    if cleaned:
        try:
            if all(float(value) == 0 for value in cleaned):
                return ""
        except (TypeError, ValueError):
            pass
    return ",".join(str(value).strip() for value in cleaned)


def normalize_legacy_fields(table_name: str, source: Mapping[str, Any]) -> dict[str, Any]:
    values = copy.deepcopy(dict(source))
    if table_name == "struts":
        if "BeamPositions" not in values:
            values["BeamPositions"] = _legacy_position_list(
                [values.get("Beam1"), values.get("Beam2")]
            )
        if "ColumnPositions" not in values:
            values["ColumnPositions"] = _legacy_position_list(
                [values.get("Column1"), values.get("Column2")]
            )
        values.setdefault("TargetJackRegion", 2)
        for old_key in ("Beam1", "Beam2", "Column1", "Column2"):
            values.pop(old_key, None)
    elif table_name == "braces":
        values.pop("Type", None)
    return values


def next_identifier(
    rows: Sequence[Mapping[str, Any]],
    id_field: str,
    prefix: str,
) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$", re.IGNORECASE)
    numbers = []
    for row in rows:
        match = pattern.fullmatch(str(row.get(id_field, "")).strip())
        if match:
            numbers.append(int(match.group(1)))
    return f"{prefix}{max(numbers, default=0) + 1}"


def build_input_row(
    table_name: str,
    values: Mapping[str, Any],
    existing_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    spec = TABLE_SPECS[table_name]
    normalized_values = normalize_legacy_fields(table_name, values)
    row = copy.deepcopy(spec["defaults"])
    id_field = spec["id_field"]
    if id_field is not None:
        row[id_field] = next_identifier(
            existing_rows,
            id_field,
            spec["id_prefix"],
        )
    for column in spec["columns"]:
        if column != id_field and column in normalized_values:
            row[column] = normalized_values[column]
    return {column: row.get(column, "") for column in spec["columns"]}


def normalize_project_row(
    table_name: str,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    if table_name not in TABLE_SPECS:
        raise ValueError(f"不支援的資料表：{table_name}")
    if not isinstance(source, Mapping):
        raise ValueError(f"{table_name} 的資料列必須是物件。")
    values = normalize_legacy_fields(table_name, source)
    spec = TABLE_SPECS[table_name]
    normalized = copy.deepcopy(values)
    for column in spec["columns"]:
        normalized.setdefault(column, copy.deepcopy(spec["defaults"].get(column, "")))
    return {
        column: normalized.get(column, copy.deepcopy(spec["defaults"].get(column, "")))
        for column in spec["columns"]
    }


class ProjectDataModel:
    """Own the Solver's only mutable copy of all input tables."""

    def __init__(
        self,
        *,
        walers: Sequence[Mapping[str, Any]] = (),
        struts: Sequence[Mapping[str, Any]] = (),
        braces: Sequence[Mapping[str, Any]] = (),
        inventory: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self.walers: list[dict[str, Any]] = []
        self.struts: list[dict[str, Any]] = []
        self.braces: list[dict[str, Any]] = []
        self.inventory: list[dict[str, Any]] = []
        self.replace_table("walers", walers)
        self.replace_table("struts", struts)
        self.replace_table("braces", braces)
        self.replace_table("inventory", inventory)

    def rows(self, table_name: str) -> list[dict[str, Any]]:
        if table_name not in TABLE_SPECS:
            raise ValueError(f"不支援的資料表：{table_name}")
        return getattr(self, table_name)

    def replace_table(
        self,
        table_name: str,
        rows: Sequence[Mapping[str, Any]],
    ) -> None:
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise ValueError(f"{table_name} 必須是資料列陣列。")
        normalized = [normalize_project_row(table_name, row) for row in rows]
        setattr(self, table_name, normalized)

    def geometry_rows(self) -> dict[str, list[dict[str, Any]]]:
        return {
            table_name: self.rows(table_name)
            for table_name in GEOMETRY_TABLES
        }

    def to_case_data(self) -> dict[str, list[dict[str, Any]]]:
        return {
            table_name: copy.deepcopy(self.rows(table_name))
            for table_name in GEOMETRY_TABLES
        }


__all__ = [
    "GEOMETRY_TABLES",
    "TABLE_COLUMNS",
    "TABLE_SPECS",
    "ProjectDataModel",
    "build_input_row",
    "next_identifier",
    "normalize_legacy_fields",
    "normalize_project_row",
]
