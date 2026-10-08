"""Headless AutoLISP event adapter used by the main Solver application."""

from __future__ import annotations

import copy
import json
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from bracing_optimizer.application.project_data import TABLE_SPECS, build_input_row
from dxf_import.models import GeometryTolerances


EVENT_FILE_NAME = "support_distribution_uv_cad_builder_temp.json"
DEFAULT_TEMP_PATH = Path(tempfile.gettempdir()) / EVENT_FILE_NAME
POLL_INTERVAL_MS = 500
DXF_BINDING_MATCH_TOLERANCE_MM = 5.0
WALER_ENDPOINT_TOLERANCE_MM = 50.0

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
POSITION_FIELDS = ("BeamPositions", "ColumnPositions")
STRUT_BRACE_LENGTH_FIELDS = (
    "FromBraceToWalerStartLen",
    "FromBraceToWalerEndLen",
    "ToBraceToWalerStartLen",
    "ToBraceToWalerEndLen",
)
STRUT_UPDATE_FIELDS = frozenset((*COORDINATE_FIELDS, *POSITION_FIELDS))
LINEAR_UPDATE_FIELDS = frozenset(COORDINATE_FIELDS)
MINIMUM_LINEAR_UPDATE_LENGTH_MM = GeometryTolerances().minimum_component_length_mm
UPDATE_POLICIES = {
    "walers": {
        "id_field": "WalerID",
        "label": "Waler",
        "allowed_fields": LINEAR_UPDATE_FIELDS,
    },
    "struts": {
        "id_field": "StrutID",
        "label": "Strut",
        "allowed_fields": STRUT_UPDATE_FIELDS,
    },
    "braces": {
        "id_field": "BraceID",
        "label": "Brace",
        "allowed_fields": LINEAR_UPDATE_FIELDS,
    },
}


@dataclass(frozen=True)
class CadMappedEvent:
    """One validated CAD operation, ready to be committed by the application."""

    operation: str
    table_name: str
    row: dict[str, Any]
    row_index: int | None
    target_id: str
    world_start: tuple[float, float]
    world_end: tuple[float, float]
    endpoints_changed: bool = False
    associated_ids_cleared: bool = False
    corner_brace_lengths_cleared: bool = False


def _table_key(table_name: str) -> str:
    key = TABLE_ALIASES.get(str(table_name).strip().lower())
    if key is None:
        raise ValueError(f"不支援的 CAD 事件類型：{table_name}")
    return key


def _normalized_number(value: Any, field: str) -> int | float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"CAD 事件的 {field} 必須是數字。") from exc
    if not math.isfinite(number):
        raise ValueError(f"CAD 事件的 {field} 必須是有限數字。")
    return int(number) if number.is_integer() else number


def _normalize_coordinates(values: dict[str, Any]) -> None:
    coordinates = []
    for field in COORDINATE_FIELDS:
        number = _normalized_number(values.get(field, ""), field)
        values[field] = number
        coordinates.append(float(number))
    if math.hypot(
        coordinates[2] - coordinates[0],
        coordinates[3] - coordinates[1],
    ) <= 0:
        raise ValueError("CAD 事件的線段長度必須大於 0。")


def _position_values(value: Any, field: str) -> list[int | float]:
    if value is None or str(value).strip() == "":
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        tokens = list(value)
    else:
        tokens = str(value).split(",")
    if any(str(token).strip() == "" for token in tokens):
        raise ValueError(f"CAD 事件的 {field} 格式錯誤。")
    return [_normalized_number(str(token).strip(), field) for token in tokens]


def _position_text(values: Sequence[int | float]) -> str:
    formatted = []
    for value in values:
        number = float(value)
        formatted.append(
            str(int(number)) if number.is_integer() else format(number, ".12g")
        )
    return ",".join(formatted)


def _validate_position_range(
    values: Sequence[int | float],
    field: str,
    line_length: float,
) -> None:
    for value in values:
        if not 0 <= float(value) <= line_length:
            raise ValueError(
                f"CAD 事件的 {field} 必須位於 0～{line_length:g} mm。"
            )


def _event_contract(event: Mapping[str, Any]) -> tuple[str, str, str, Mapping[str, Any]]:
    if not isinstance(event, Mapping):
        raise ValueError("CAD 事件必須是物件。")
    event_id = str(event.get("event_id", "") or "").strip()
    if not event_id:
        raise ValueError("暫存 JSON 缺少 event_id。")
    operation = str(event.get("operation", "") or "").strip().lower()
    table_name = (
        "control"
        if operation == "cancel"
        else _table_key(str(event.get("type", "")).strip().lower())
    )
    if operation not in {"add", "update", "cancel"}:
        raise ValueError("CAD 事件的 operation 必須是 add、update 或 cancel。")
    coordinate_space = str(event.get("coordinate_space", "") or "").strip().upper()
    if coordinate_space != "WCS":
        raise ValueError("CAD 事件的 coordinate_space 必須是 WCS。")
    values = event.get("data")
    if not isinstance(values, Mapping):
        raise ValueError("暫存 JSON 的 data 必須是物件。")

    target_id = str(event.get("target_id", "") or "").strip()
    if operation == "cancel":
        if str(event.get("type", "") or "").strip().lower() != "control":
            raise ValueError("CAD cancel 事件的 type 必須是 control。")
        if target_id:
            raise ValueError("CAD cancel 事件不得包含 target_id。")
        if values:
            raise ValueError("CAD cancel 事件的 data 必須是空物件。")
        return operation, table_name, "", values
    if operation == "update":
        policy = UPDATE_POLICIES[table_name]
        if not target_id:
            raise ValueError(f"{policy['label']} update 缺少 target_id。")
        allowed_fields = policy["allowed_fields"]
        missing = [field for field in allowed_fields if field not in values]
        if missing:
            raise ValueError(
                f"{policy['label']} update 缺少欄位："
                + ", ".join(sorted(missing))
            )
        unexpected = set(values) - allowed_fields
        if unexpected:
            raise ValueError(
                f"{policy['label']} update 不得修改欄位："
                + ", ".join(sorted(unexpected))
            )
    elif target_id:
        raise ValueError("CAD add 事件不得包含 target_id。")
    return operation, table_name, target_id, values


def _mapping_line(
    item: Mapping[str, Any],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    try:
        start = float(item["StartX"]), float(item["StartY"])
        end = float(item["EndX"]), float(item["EndY"])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (*start, *end)):
        return None
    return start, end


def _serialized_line(
    item: Mapping[str, Any],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    try:
        start_value, end_value = item.get("start"), item.get("end")
        if (
            not isinstance(start_value, Sequence)
            or isinstance(start_value, (str, bytes))
            or len(start_value) < 2
            or not isinstance(end_value, Sequence)
            or isinstance(end_value, (str, bytes))
            or len(end_value) < 2
        ):
            return None
        start = float(start_value[0]), float(start_value[1])
        end = float(end_value[0]), float(end_value[1])
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (*start, *end)):
        return None
    return start, end


def _endpoint_error(first, second) -> float:
    return min(
        max(math.dist(first[0], second[0]), math.dist(first[1], second[1])),
        max(math.dist(first[0], second[1]), math.dist(first[1], second[0])),
    )


def _point_segment_distance(
    point: tuple[float, float],
    line: tuple[tuple[float, float], tuple[float, float]],
) -> float:
    start, end = line
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= 0:
        return math.inf
    projection = (
        (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
    ) / length_squared
    projection = min(max(projection, 0.0), 1.0)
    closest = start[0] + projection * dx, start[1] + projection * dy
    return math.dist(point, closest)


def _unique_row_index(
    rows: Sequence[Mapping[str, Any]],
    field: str,
    identifier: str,
    table_name: str,
) -> int:
    target = identifier.casefold()
    matches = [
        index
        for index, row in enumerate(rows)
        if str(row.get(field, "") or "").strip().casefold() == target
    ]
    if not matches:
        raise ValueError(f"找不到目標構件 {identifier}（{table_name}）。")
    if len(matches) != 1:
        raise ValueError(
            f"目標構件 {identifier} 在 {table_name} 中不是唯一 ID。"
        )
    return matches[0]


def _waler_line(
    walers: Sequence[Mapping[str, Any]],
    identifier: str,
) -> tuple[tuple[float, float], tuple[float, float]]:
    target = identifier.casefold()
    matches = [
        row
        for row in walers
        if str(row.get("WalerID", "") or "").strip().casefold() == target
    ]
    if len(matches) != 1:
        raise ValueError(f"無法唯一確認既有圍令：{identifier}")
    line = _mapping_line(matches[0])
    if line is None or math.dist(*line) <= 0:
        raise ValueError(f"既有圍令 {identifier} 的座標無法用於方向判斷。")
    return line


def _normalized_waler_relation_direction(
    start: tuple[float, float],
    end: tuple[float, float],
    old_row: Mapping[str, Any],
    walers: Sequence[Mapping[str, Any]],
    *,
    member_label: str,
) -> bool:
    """Return True when the event direction must be reversed."""

    from_id = str(old_row.get("FromWaler", "") or "").strip()
    to_id = str(old_row.get("ToWaler", "") or "").strip()
    if not from_id and not to_id:
        return False

    from_line = _waler_line(walers, from_id) if from_id else None
    to_line = _waler_line(walers, to_id) if to_id else None

    def score(candidate_start, candidate_end) -> float | None:
        distances = []
        if from_line is not None:
            distances.append(_point_segment_distance(candidate_start, from_line))
        if to_line is not None:
            distances.append(_point_segment_distance(candidate_end, to_line))
        if any(value > WALER_ENDPOINT_TOLERANCE_MM for value in distances):
            return None
        return sum(distances)

    direct_score = score(start, end)
    reverse_score = score(end, start)
    if direct_score is None and reverse_score is None:
        raise ValueError(
            f"新{member_label}幾何無法維持原 FromWaler / ToWaler 關係，"
            "本次更新未套用。"
        )
    if direct_score is None:
        return True
    if reverse_score is None:
        return False
    if not math.isclose(direct_score, reverse_score, abs_tol=1e-9):
        return reverse_score < direct_score

    old_line = _mapping_line(old_row)
    if old_line is None:
        return False
    direct_change = math.dist(old_line[0], start) + math.dist(old_line[1], end)
    reverse_change = math.dist(old_line[0], end) + math.dist(old_line[1], start)
    return reverse_change < direct_change


def _normalized_waler_direction(
    start: tuple[float, float],
    end: tuple[float, float],
    old_row: Mapping[str, Any],
) -> bool:
    """Return True when reversing best preserves old Waler endpoint semantics."""

    old_line = _mapping_line(old_row)
    if old_line is None:
        return False
    forward_cost = math.dist(old_line[0], start) + math.dist(old_line[1], end)
    reverse_cost = math.dist(old_line[0], end) + math.dist(old_line[1], start)
    return reverse_cost < forward_cost


def _coordinates_changed(
    old_row: Mapping[str, Any],
    start: tuple[float, float],
    end: tuple[float, float],
) -> bool:
    old_line = _mapping_line(old_row)
    return old_line is None or any(
        not math.isclose(old, new, rel_tol=0.0, abs_tol=1e-9)
        for old, new in zip((*old_line[0], *old_line[1]), (*start, *end))
    )


def _validate_linear_update_length(
    start: tuple[float, float],
    end: tuple[float, float],
    member_label: str,
) -> None:
    if math.dist(start, end) < MINIMUM_LINEAR_UPDATE_LENGTH_MM:
        raise ValueError(
            f"{member_label} update 線段長度必須至少為 "
            f"{MINIMUM_LINEAR_UPDATE_LENGTH_MM:g} mm。"
        )


class CadEventReader:
    """Read and validate the small JSON envelope written by AutoLISP."""

    @staticmethod
    def load(path: str | Path) -> dict:
        event = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(event, dict):
            raise ValueError("暫存 JSON 最上層必須是物件。")
        operation, _table_name, _target_id, values = _event_contract(event)
        if operation == "cancel":
            return event
        normalized_values = dict(values)
        _normalize_coordinates(normalized_values)
        for field in POSITION_FIELDS:
            if field in normalized_values:
                _position_values(normalized_values[field], field)
        return event


class CadEventMapper:
    """Convert CAD events into staged rows without owning project data."""

    @staticmethod
    def is_cancel_event(event: Mapping[str, Any]) -> bool:
        return (
            isinstance(event, Mapping)
            and str(event.get("operation", "") or "").strip().lower() == "cancel"
        )

    @staticmethod
    def validate_cancel_event(event: Mapping[str, Any]) -> None:
        operation, _table_name, _target_id, _values = _event_contract(event)
        if operation != "cancel":
            raise ValueError("CAD 事件不是 cancel 事件。")

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
        line_length = math.hypot(
            float(normalized_values["EndX"]) - float(normalized_values["StartX"]),
            float(normalized_values["EndY"]) - float(normalized_values["StartY"]),
        )
        if key == "struts":
            for field in POSITION_FIELDS:
                if field not in normalized_values:
                    continue
                positions = _position_values(normalized_values[field], field)
                _validate_position_range(positions, field, line_length)
                normalized_values[field] = _position_text(positions)
        return build_input_row(key, normalized_values, existing_rows)

    @classmethod
    def map_command(
        cls,
        event: Mapping[str, Any],
        rows_by_table: Mapping[str, Sequence[dict]],
        *,
        coordinate_system: Any = None,
    ) -> CadMappedEvent:
        operation, table_name, target_id, raw_values = _event_contract(event)
        if operation == "cancel":
            raise ValueError("CAD cancel 事件必須由 Main 處理。")
        values = dict(raw_values)
        _normalize_coordinates(values)
        world_start = float(values["StartX"]), float(values["StartY"])
        world_end = float(values["EndX"]), float(values["EndY"])
        transform = (
            coordinate_system.transform
            if coordinate_system is not None
            else lambda point: point
        )
        project_start = tuple(float(value) for value in transform(world_start))
        project_end = tuple(float(value) for value in transform(world_end))
        if len(project_start) != 2 or len(project_end) != 2 or not all(
            math.isfinite(value) for value in (*project_start, *project_end)
        ):
            raise ValueError("WCS 無法轉換為有效的 Project 座標。")
        if math.dist(project_start, project_end) <= 0:
            raise ValueError("CAD 事件的 Project 線段長度必須大於 0。")
        values.update(
            StartX=_normalized_number(project_start[0], "StartX"),
            StartY=_normalized_number(project_start[1], "StartY"),
            EndX=_normalized_number(project_end[0], "EndX"),
            EndY=_normalized_number(project_end[1], "EndY"),
        )

        if operation == "add":
            row = cls.build_row(
                table_name,
                values,
                rows_by_table.get(table_name, ()),
            )
            return CadMappedEvent(
                operation,
                table_name,
                row,
                None,
                "",
                world_start,
                world_end,
            )

        policy_mapper = {
            "walers": cls._map_waler_update,
            "struts": cls._map_strut_update,
            "braces": cls._map_brace_update,
        }[table_name]
        policy = UPDATE_POLICIES[table_name]
        rows = rows_by_table.get(table_name, ())
        row_index = _unique_row_index(
            rows,
            policy["id_field"],
            target_id,
            table_name,
        )
        return policy_mapper(
            target_id,
            values,
            rows_by_table,
            rows[row_index],
            row_index,
            project_start,
            project_end,
            world_start,
            world_end,
        )

    @staticmethod
    def _map_waler_update(
        target_id,
        _values,
        _rows_by_table,
        old_row,
        row_index,
        project_start,
        project_end,
        world_start,
        world_end,
    ) -> CadMappedEvent:
        table_name = "walers"
        policy = UPDATE_POLICIES[table_name]
        _validate_linear_update_length(
            project_start,
            project_end,
            policy["label"],
        )
        if _normalized_waler_direction(project_start, project_end, old_row):
            project_start, project_end = project_end, project_start
            world_start, world_end = world_end, world_start

        staged_row = copy.deepcopy(dict(old_row))
        staged_row.update(
            StartX=_normalized_number(project_start[0], "StartX"),
            StartY=_normalized_number(project_start[1], "StartY"),
            EndX=_normalized_number(project_end[0], "EndX"),
            EndY=_normalized_number(project_end[1], "EndY"),
        )
        return CadMappedEvent(
            "update",
            table_name,
            staged_row,
            row_index,
            str(old_row.get(policy["id_field"], target_id) or target_id).strip(),
            world_start,
            world_end,
            _coordinates_changed(old_row, project_start, project_end),
        )

    @staticmethod
    def _map_strut_update(
        target_id,
        values,
        rows_by_table,
        old_row,
        row_index,
        project_start,
        project_end,
        world_start,
        world_end,
    ) -> CadMappedEvent:
        table_name = "struts"
        policy = UPDATE_POLICIES[table_name]
        reverse = _normalized_waler_relation_direction(
            project_start,
            project_end,
            old_row,
            rows_by_table.get("walers", ()),
            member_label="支撐",
        )
        beam_positions = _position_values(values["BeamPositions"], "BeamPositions")
        column_positions = _position_values(
            values["ColumnPositions"], "ColumnPositions"
        )
        new_length = math.dist(project_start, project_end)
        _validate_position_range(beam_positions, "BeamPositions", new_length)
        _validate_position_range(column_positions, "ColumnPositions", new_length)
        if reverse:
            project_start, project_end = project_end, project_start
            world_start, world_end = world_end, world_start
            beam_positions = sorted(new_length - float(value) for value in beam_positions)
            column_positions = sorted(
                new_length - float(value) for value in column_positions
            )

        staged_row = copy.deepcopy(dict(old_row))
        staged_row.update(
            StartX=_normalized_number(project_start[0], "StartX"),
            StartY=_normalized_number(project_start[1], "StartY"),
            EndX=_normalized_number(project_end[0], "EndX"),
            EndY=_normalized_number(project_end[1], "EndY"),
            BeamPositions=_position_text(beam_positions),
            ColumnPositions=_position_text(column_positions),
        )
        associated_ids_cleared = any(
            str(old_row.get(field, "") or "").strip()
            for field in ("AssociatedColumnIDs", "AssociatedBeamIDs")
        )
        staged_row["AssociatedColumnIDs"] = ""
        staged_row["AssociatedBeamIDs"] = ""

        endpoints_changed = _coordinates_changed(
            old_row,
            project_start,
            project_end,
        )

        def has_corner_brace_value(field: str) -> bool:
            value = old_row.get(field, 0)
            try:
                return abs(float(value or 0)) > 1e-9
            except (TypeError, ValueError):
                return bool(str(value or "").strip())

        corner_brace_lengths_cleared = endpoints_changed and any(
            has_corner_brace_value(field) for field in STRUT_BRACE_LENGTH_FIELDS
        )
        if endpoints_changed:
            for field in STRUT_BRACE_LENGTH_FIELDS:
                staged_row[field] = 0

        return CadMappedEvent(
            "update",
            table_name,
            staged_row,
            row_index,
            str(old_row.get(policy["id_field"], target_id) or target_id).strip(),
            world_start,
            world_end,
            endpoints_changed,
            associated_ids_cleared,
            corner_brace_lengths_cleared,
        )

    @staticmethod
    def _map_brace_update(
        target_id,
        _values,
        rows_by_table,
        old_row,
        row_index,
        project_start,
        project_end,
        world_start,
        world_end,
    ) -> CadMappedEvent:
        table_name = "braces"
        policy = UPDATE_POLICIES[table_name]
        _validate_linear_update_length(
            project_start,
            project_end,
            policy["label"],
        )
        from_id = str(old_row.get("FromWaler", "") or "").strip()
        to_id = str(old_row.get("ToWaler", "") or "").strip()
        if not from_id or not to_id or from_id.casefold() == to_id.casefold():
            raise ValueError(
                "既有斜撐必須具有不同的 FromWaler / ToWaler，"
                "本次更新未套用。"
            )
        reverse = _normalized_waler_relation_direction(
            project_start,
            project_end,
            old_row,
            rows_by_table.get("walers", ()),
            member_label="斜撐",
        )
        if reverse:
            project_start, project_end = project_end, project_start
            world_start, world_end = world_end, world_start

        staged_row = copy.deepcopy(dict(old_row))
        staged_row.update(
            StartX=_normalized_number(project_start[0], "StartX"),
            StartY=_normalized_number(project_start[1], "StartY"),
            EndX=_normalized_number(project_end[0], "EndX"),
            EndY=_normalized_number(project_end[1], "EndY"),
        )
        return CadMappedEvent(
            "update",
            table_name,
            staged_row,
            row_index,
            str(old_row.get(policy["id_field"], target_id) or target_id).strip(),
            world_start,
            world_end,
            _coordinates_changed(old_row, project_start, project_end),
        )

    @classmethod
    def map_event(
        cls,
        event: Mapping[str, Any],
        rows_by_table: Mapping[str, Sequence[dict]],
    ) -> tuple[str, dict]:
        """Compatibility facade for callers that only need the staged row."""

        mapped = cls.map_command(event, rows_by_table)
        return mapped.table_name, mapped.row

    @staticmethod
    def _locate_dxf_linear_binding(
        dxf_state: Mapping[str, Any] | None,
        mapped: CadMappedEvent,
        old_row: Mapping[str, Any],
        *,
        collection_name: str,
        member_label: str,
    ) -> tuple[dict[str, Any] | None, list[Any] | None, int | None, str]:
        if not isinstance(dxf_state, Mapping):
            return None, None, None, "專案沒有 DXF state"
        staged = copy.deepcopy(dict(dxf_state))
        converted = staged.get("converted")
        if not isinstance(converted, Mapping):
            return staged, None, None, "DXF state 缺少 converted"
        converted = dict(converted)
        members_value = converted.get(collection_name)
        if not isinstance(members_value, Sequence) or isinstance(
            members_value, (str, bytes)
        ):
            return staged, None, None, f"DXF state 缺少 {member_label} binding"
        members = list(members_value)
        converted[collection_name] = members
        staged["converted"] = converted

        target_key = mapped.target_id.casefold()
        project_id_matches = [
            index
            for index, item in enumerate(members)
            if isinstance(item, Mapping)
            and str(item.get("project_id", "") or "").strip().casefold()
            == target_key
        ]
        if len(project_id_matches) > 1:
            return staged, None, None, "DXF project_id binding 不唯一"

        if project_id_matches:
            match_index = project_id_matches[0]
        else:
            old_line = _mapping_line(old_row)
            if old_line is None:
                return staged, None, None, "更新前 Project 幾何無法比對"
            geometry_matches = [
                index
                for index, item in enumerate(members)
                if isinstance(item, Mapping)
                and (line := _serialized_line(item)) is not None
                and _endpoint_error(old_line, line)
                <= DXF_BINDING_MATCH_TOLERANCE_MM
            ]
            if not geometry_matches:
                return staged, None, None, f"找不到更新前 {member_label} 的 DXF binding"
            if len(geometry_matches) != 1:
                return staged, None, None, f"更新前 {member_label} 的 DXF binding 不唯一"
            match_index = geometry_matches[0]
        return staged, members, match_index, ""

    @classmethod
    def stage_dxf_strut_binding(
        cls,
        dxf_state: Mapping[str, Any] | None,
        mapped: CadMappedEvent,
        old_row: Mapping[str, Any],
        *,
        event_id: Any,
    ) -> tuple[dict[str, Any] | None, bool, str]:
        """Stage a confirmed Strut binding update without touching source geometry."""

        staged, struts, match_index, reason = cls._locate_dxf_linear_binding(
            dxf_state,
            mapped,
            old_row,
            collection_name="struts",
            member_label="Strut",
        )
        if staged is None or struts is None or match_index is None:
            return staged, False, reason
        converted = staged["converted"]

        item = copy.deepcopy(dict(struts[match_index]))
        project_start = float(mapped.row["StartX"]), float(mapped.row["StartY"])
        project_end = float(mapped.row["EndX"]), float(mapped.row["EndY"])
        item.update(
            start=list(project_start),
            end=list(project_end),
            local_start=list(project_start),
            local_end=list(project_end),
            world_start=list(mapped.world_start),
            world_end=list(mapped.world_end),
            beam_positions=_position_values(
                mapped.row.get("BeamPositions", ""), "BeamPositions"
            ),
            column_positions=_position_values(
                mapped.row.get("ColumnPositions", ""), "ColumnPositions"
            ),
            associated_columns=[],
            associated_beams=[],
            selection_source="cad_manual",
            project_id=mapped.target_id,
            cad_event_id=str(event_id),
        )
        for field, state_field in zip(
            STRUT_BRACE_LENGTH_FIELDS,
            (
                "from_brace_to_waler_start_len",
                "from_brace_to_waler_end_len",
                "to_brace_to_waler_start_len",
                "to_brace_to_waler_end_len",
            ),
        ):
            item[state_field] = float(mapped.row.get(field, 0) or 0)
        struts[match_index] = item

        internal_id = str(item.get("id", "") or "").strip()
        if internal_id:
            staged["component_associations"] = [
                association
                for association in staged.get("component_associations", ()) or ()
                if not isinstance(association, Mapping)
                or str(association.get("strut_id", "") or "").strip()
                != internal_id
            ]
            staged["beam_crossings"] = [
                crossing
                for crossing in staged.get("beam_crossings", ()) or ()
                if not isinstance(crossing, Mapping)
                or str(crossing.get("strut_id", "") or "").strip()
                != internal_id
            ]
            for collection_name in ("columns", "beams", "corner_braces"):
                members = converted.get(collection_name)
                if not isinstance(members, Sequence) or isinstance(
                    members, (str, bytes)
                ):
                    continue
                updated_members = []
                for member_value in members:
                    if not isinstance(member_value, Mapping):
                        updated_members.append(member_value)
                        continue
                    member = copy.deepcopy(dict(member_value))
                    if (
                        str(member.get("associated_strut_id", "") or "").strip()
                        == internal_id
                    ):
                        member.update(
                            associated_strut_id="",
                            association_station=None,
                            association_distance=None,
                            world_association_point=None,
                            local_association_point=None,
                        )
                    if collection_name == "beams":
                        member["associated_strut_ids"] = [
                            identifier
                            for identifier in member.get(
                                "associated_strut_ids", ()
                            )
                            or ()
                            if str(identifier).strip() != internal_id
                        ]
                        member["crossings"] = [
                            crossing
                            for crossing in member.get("crossings", ()) or ()
                            if not isinstance(crossing, Mapping)
                            or str(crossing.get("strut_id", "") or "").strip()
                            != internal_id
                        ]
                    updated_members.append(member)
                converted[collection_name] = updated_members

        return staged, True, ""

    @classmethod
    def stage_dxf_brace_binding(
        cls,
        dxf_state: Mapping[str, Any] | None,
        mapped: CadMappedEvent,
        old_row: Mapping[str, Any],
        *,
        event_id: Any,
    ) -> tuple[dict[str, Any] | None, bool, str]:
        """Stage a uniquely matched Brace review binding update."""

        staged, braces, match_index, reason = cls._locate_dxf_linear_binding(
            dxf_state,
            mapped,
            old_row,
            collection_name="braces",
            member_label="Brace",
        )
        if staged is None or braces is None or match_index is None:
            return staged, False, reason

        item = copy.deepcopy(dict(braces[match_index]))
        project_start = float(mapped.row["StartX"]), float(mapped.row["StartY"])
        project_end = float(mapped.row["EndX"]), float(mapped.row["EndY"])
        item.update(
            start=list(project_start),
            end=list(project_end),
            local_start=list(project_start),
            local_end=list(project_end),
            world_start=list(mapped.world_start),
            world_end=list(mapped.world_end),
            selection_source="cad_manual",
            project_id=mapped.target_id,
            cad_event_id=str(event_id),
        )
        braces[match_index] = item
        return staged, True, ""

    @classmethod
    def stage_dxf_update_binding(
        cls,
        dxf_state: Mapping[str, Any] | None,
        mapped: CadMappedEvent,
        old_row: Mapping[str, Any],
        *,
        event_id: Any,
    ) -> tuple[dict[str, Any] | None, bool, str]:
        """Dispatch optional review-state synchronization for a Project update."""

        if mapped.table_name == "struts":
            return cls.stage_dxf_strut_binding(
                dxf_state,
                mapped,
                old_row,
                event_id=event_id,
            )
        if mapped.table_name == "braces":
            return cls.stage_dxf_brace_binding(
                dxf_state,
                mapped,
                old_row,
                event_id=event_id,
            )
        return dxf_state, False, "Waler geometry 變更需重新確認 DXF Review state"


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
    "DXF_BINDING_MATCH_TOLERANCE_MM",
    "EVENT_FILE_NAME",
    "POLL_INTERVAL_MS",
    "TABLE_SPECS",
    "CadEventMapper",
    "CadEventReader",
    "CadMappedEvent",
    "TempEventWatcher",
]
