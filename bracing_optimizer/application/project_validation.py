"""Data-only validation for editable project input tables."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Mapping

from bracing_optimizer.application.project_data import ProjectDataModel


STRUT_BRACE_LENGTH_FIELDS = (
    ("FromBraceToWalerStartLen", "起點角撐長度(靠圍令起點)"),
    ("FromBraceToWalerEndLen", "起點角撐長度(靠圍令終點)"),
    ("ToBraceToWalerStartLen", "終點角撐長度(靠圍令起點)"),
    ("ToBraceToWalerEndLen", "終點角撐長度(靠圍令終點)"),
)


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    table: str
    row_index: int
    message: str
    field: str | None = None


@dataclass(frozen=True)
class ProjectValidationReport:
    errors: tuple[ValidationIssue, ...] = ()
    warnings: tuple[ValidationIssue, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors


def _number(value):
    if isinstance(value, (int, float)):
        number = float(value)
    elif value is None or str(value).strip() == "":
        return None
    else:
        try:
            number = float(str(value).strip())
        except ValueError:
            return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def _line_length(start_x, start_y, end_x, end_y) -> float:
    return math.hypot(end_x - start_x, end_y - start_y)


def _position_list(value) -> tuple[list[int | float], str | None]:
    if value is None:
        return [], None
    text = str(value).strip().replace("，", ",")
    if not text:
        return [], None
    parts = text.split(",")
    if any(not part.strip() for part in parts):
        return [], "位置格式錯誤"
    positions = []
    for part in parts:
        token = part.strip()
        number = _number(token)
        if number is None:
            return [], f"{token} 不是有效數字"
        positions.append(number)
    return positions, None


def _has_duplicates(values) -> bool:
    normalized = [round(float(value), 6) for value in values]
    return len(normalized) != len(set(normalized))


def _waler_coordinates(row: Mapping):
    values = tuple(
        _number(row.get(field))
        for field in ("StartX", "StartY", "EndX", "EndY")
    )
    if any(value is None for value in values):
        return None
    if _line_length(*values) <= 0:
        return None
    return values


def _point_on_waler(row: Mapping, point_x, point_y, tolerance=50) -> bool:
    coordinates = _waler_coordinates(row)
    if coordinates is None or point_x is None or point_y is None:
        return True
    start_x, start_y, end_x, end_y = coordinates
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    length_squared = delta_x * delta_x + delta_y * delta_y
    projection = (
        (point_x - start_x) * delta_x
        + (point_y - start_y) * delta_y
    ) / length_squared
    projection = min(max(projection, 0.0), 1.0)
    closest_x = start_x + projection * delta_x
    closest_y = start_y + projection * delta_y
    return math.hypot(point_x - closest_x, point_y - closest_y) <= tolerance


def _walers_nearly_parallel(first: Mapping, second: Mapping, tolerance=15) -> bool:
    first_coordinates = _waler_coordinates(first)
    second_coordinates = _waler_coordinates(second)
    if first_coordinates is None or second_coordinates is None:
        return False
    first_x1, first_y1, first_x2, first_y2 = first_coordinates
    second_x1, second_y1, second_x2, second_y2 = second_coordinates
    first_angle = math.degrees(
        math.atan2(first_y2 - first_y1, first_x2 - first_x1)
    )
    second_angle = math.degrees(
        math.atan2(second_y2 - second_y1, second_x2 - second_x1)
    )
    difference = abs((first_angle - second_angle + 180) % 360 - 180)
    return min(difference, 180 - difference) <= tolerance


def _line_nearly_perpendicular_to_waler(
    start_x,
    start_y,
    end_x,
    end_y,
    waler: Mapping,
    tolerance=30,
) -> bool:
    coordinates = _waler_coordinates(waler)
    if coordinates is None or None in (start_x, start_y, end_x, end_y):
        return True
    waler_x1, waler_y1, waler_x2, waler_y2 = coordinates
    line_delta_x = end_x - start_x
    line_delta_y = end_y - start_y
    waler_delta_x = waler_x2 - waler_x1
    waler_delta_y = waler_y2 - waler_y1
    line_length = math.hypot(line_delta_x, line_delta_y)
    waler_length = math.hypot(waler_delta_x, waler_delta_y)
    if line_length <= 0 or waler_length <= 0:
        return True
    dot_ratio = abs(
        (
            line_delta_x * waler_delta_x
            + line_delta_y * waler_delta_y
        )
        / (line_length * waler_length)
    )
    return dot_ratio <= math.sin(math.radians(tolerance))


class ProjectDataValidator:
    """Validate project rows without touching Tk widgets or mutating rows."""

    def __init__(
        self,
        field_label: Callable[[str, str], str] | None = None,
    ) -> None:
        self._field_label = field_label or (lambda _table, field: field)

    def validate(self, project_data: ProjectDataModel) -> ProjectValidationReport:
        errors = []
        warnings = []
        material_options = self._material_options(project_data)
        waler_ids = set()
        waler_by_id = {}

        for row_index, row in enumerate(project_data.walers, start=1):
            row_errors = []
            waler_id = str(row.get("WalerID", "")).strip()
            if not waler_id:
                row_errors.append(self._required("walers", "WalerID"))
            elif waler_id in waler_ids:
                row_errors.append(
                    f"{self._field_label('walers', 'WalerID')} 不可重複"
                )
            else:
                waler_ids.add(waler_id)
                waler_by_id[waler_id] = row

            coordinates, coordinate_errors = self._coordinates("walers", row)
            row_errors.extend(coordinate_errors)
            if coordinates is not None:
                start_x, start_y, end_x, end_y = coordinates
                if _line_length(start_x, start_y, end_x, end_y) <= 0:
                    row_errors.append("圍令長度必須大於 0")
            material_spec = str(row.get("material_spec", "") or "").strip()
            if material_spec and material_spec not in material_options["圍令"]:
                row_errors.append("材料規格必須從設定頁的圍令規格選擇")
            errors.extend(self._issues("error", "walers", row_index, row_errors))

        strut_ids = set()
        strut_group_rows: dict[str, list[tuple[int, Mapping]]] = {}
        for row_index, row in enumerate(project_data.struts, start=1):
            row_errors = []
            row_warnings = []
            strut_id = str(row.get("StrutID", "")).strip()
            if not strut_id:
                row_errors.append(self._required("struts", "StrutID"))
            elif strut_id in strut_ids:
                row_errors.append(
                    f"{self._field_label('struts', 'StrutID')} 不可重複"
                )
            else:
                strut_ids.add(strut_id)

            shared_layout_group = str(
                row.get("SharedLayoutGroup", "") or ""
            ).strip()
            if shared_layout_group:
                strut_group_rows.setdefault(shared_layout_group, []).append(
                    (row_index, row)
                )

            for endpoint in ("FromWaler", "ToWaler"):
                value = str(row.get(endpoint, "")).strip()
                if value and value not in waler_ids:
                    row_errors.append(
                        f"{self._field_label('struts', endpoint)} 必須存在於圍令表"
                    )
            from_waler = str(row.get("FromWaler", "") or "").strip()
            to_waler = str(row.get("ToWaler", "") or "").strip()
            if from_waler and from_waler == to_waler:
                row_errors.append(
                    f"❌ 支撐 {strut_id or row_index} 起點圍令與終點圍令不可相同"
                )

            coordinates, coordinate_errors = self._coordinates("struts", row)
            row_errors.extend(coordinate_errors)
            length = None
            if coordinates is not None:
                length = _line_length(*coordinates)
                if length <= 0:
                    row_errors.append("支撐長度必須大於 0")
                start_x, start_y, end_x, end_y = coordinates
                if from_waler in waler_by_id and not _point_on_waler(
                    waler_by_id[from_waler],
                    start_x,
                    start_y,
                ):
                    row_errors.append(
                        f"❌ 支撐 {strut_id or row_index} 起點未落於圍令 {from_waler} 上"
                    )
                if to_waler in waler_by_id and not _point_on_waler(
                    waler_by_id[to_waler],
                    end_x,
                    end_y,
                ):
                    row_errors.append(
                        f"❌ 支撐 {strut_id or row_index} 終點未落於圍令 {to_waler} 上"
                    )
                if (
                    from_waler
                    and to_waler
                    and from_waler != to_waler
                    and from_waler in waler_by_id
                    and to_waler in waler_by_id
                    and _walers_nearly_parallel(
                        waler_by_id[from_waler],
                        waler_by_id[to_waler],
                    )
                    and not _line_nearly_perpendicular_to_waler(
                        *coordinates,
                        waler_by_id[from_waler],
                    )
                ):
                    row_warnings.append(
                        f"⚠ 支撐 {strut_id or row_index} 與所選圍令方向可能不一致"
                    )

            for field in ("BeamPositions", "ColumnPositions"):
                positions, position_error = _position_list(row.get(field, ""))
                position_label = (
                    "托梁位置" if field == "BeamPositions" else "中間柱位置"
                )
                if position_error:
                    row_errors.append(
                        f"❌ {position_label}格式錯誤：{position_error}"
                    )
                    continue
                if _has_duplicates(positions):
                    row_warnings.append(
                        f"⚠ 支撐 {strut_id or row_index} {position_label}重複"
                    )
                for position in positions:
                    if length is not None and not 0 <= position <= length:
                        row_errors.append(
                            f"{self._field_label('struts', field)} "
                            f"{self._format_position(position)} 不在 0 ~ "
                            f"{self._format_position(length)} mm 範圍內"
                        )

            for field, label in STRUT_BRACE_LENGTH_FIELDS:
                value = _number(row.get(field, ""))
                if value is None:
                    row_errors.append(f"{label} 必須是數字且不可為負數")
                elif value < 0:
                    row_errors.append(
                        f"❌ {strut_id or row_index} {label}不可為負數"
                    )

            target_region = _number(row.get("TargetJackRegion", ""))
            target_label = self._field_label("struts", "TargetJackRegion")
            if target_region is None:
                row_errors.append(f"{target_label} 必須是大於 0 的整數")
            elif not float(target_region).is_integer():
                row_errors.append(f"{target_label} 必須是整數")
            elif target_region <= 0:
                row_errors.append(f"{target_label} 必須大於 0")

            material_spec = str(row.get("material_spec", "") or "").strip()
            if material_spec and material_spec not in material_options["支撐"]:
                row_errors.append("材料規格必須從設定頁的支撐規格選擇")
            errors.extend(self._issues("error", "struts", row_index, row_errors))
            warnings.extend(
                self._issues("warning", "struts", row_index, row_warnings)
            )

        for group_id, grouped_rows in strut_group_rows.items():
            group_errors = []
            if len(grouped_rows) != 2:
                group_errors.append(
                    f"雙路支撐群組 {group_id} 必須剛好包含兩支支撐"
                )
            else:
                (_first_index, first), (_second_index, second) = grouped_rows
                if str(first.get("Zoning", "") or "").strip() != str(
                    second.get("Zoning", "") or ""
                ).strip():
                    group_errors.append(
                        f"雙路支撐群組 {group_id} 的兩支支撐必須位於相同分區"
                    )
                if str(first.get("material_spec", "") or "").strip() != str(
                    second.get("material_spec", "") or ""
                ).strip():
                    group_errors.append(
                        f"雙路支撐群組 {group_id} 的材料規格必須相同"
                    )
                if (
                    str(first.get("FromWaler", "") or "").strip(),
                    str(first.get("ToWaler", "") or "").strip(),
                ) != (
                    str(second.get("FromWaler", "") or "").strip(),
                    str(second.get("ToWaler", "") or "").strip(),
                ):
                    group_errors.append(
                        f"雙路支撐群組 {group_id} 的兩支支撐必須使用相同圍令方向"
                    )
            for row_index, _row in grouped_rows:
                errors.extend(
                    ValidationIssue(
                        "error",
                        "struts",
                        row_index,
                        message,
                        "SharedLayoutGroup",
                    )
                    for message in group_errors
                )

        brace_ids = set()
        for row_index, row in enumerate(project_data.braces, start=1):
            row_errors = []
            brace_id = str(row.get("BraceID", "")).strip()
            if not brace_id:
                row_errors.append(self._required("braces", "BraceID"))
            elif brace_id in brace_ids:
                row_errors.append(
                    f"{self._field_label('braces', 'BraceID')} 不可重複"
                )
            else:
                brace_ids.add(brace_id)
            for endpoint in ("FromWaler", "ToWaler"):
                value = str(row.get(endpoint, "")).strip()
                if value and value not in waler_ids:
                    row_errors.append(
                        f"{self._field_label('braces', endpoint)} "
                        "若有填值，應存在於圍令表"
                    )
            from_waler = str(row.get("FromWaler", "") or "").strip()
            to_waler = str(row.get("ToWaler", "") or "").strip()
            if from_waler and from_waler == to_waler:
                row_errors.append(
                    f"❌ 斜撐 {brace_id or row_index} 起點圍令與終點圍令不可相同"
                )
            coordinates, coordinate_errors = self._coordinates("braces", row)
            row_errors.extend(coordinate_errors)
            if coordinates is not None:
                if _line_length(*coordinates) <= 0:
                    row_errors.append("斜撐長度必須大於 0")
                start_x, start_y, end_x, end_y = coordinates
                if from_waler in waler_by_id and not _point_on_waler(
                    waler_by_id[from_waler],
                    start_x,
                    start_y,
                ):
                    row_errors.append(
                        f"❌ 斜撐 {brace_id or row_index} 起點未落於圍令 {from_waler} 上"
                    )
                if to_waler in waler_by_id and not _point_on_waler(
                    waler_by_id[to_waler],
                    end_x,
                    end_y,
                ):
                    row_errors.append(
                        f"❌ 斜撐 {brace_id or row_index} 終點未落於圍令 {to_waler} 上"
                    )
            errors.extend(self._issues("error", "braces", row_index, row_errors))

        for row_index, row in enumerate(project_data.inventory, start=1):
            row_errors = []
            usage = str(row.get("Usage", "") or "").strip()
            material_spec = str(row.get("Spec", "") or "").strip()
            if usage and usage not in ("支撐", "圍令"):
                row_errors.append("用途必須是支撐或圍令")
            if (
                material_spec
                and usage
                and material_spec not in material_options.get(usage, set())
            ):
                row_errors.append("規格必須存在於材料規格表")
            for field in ("Length", "Qty"):
                value = _number(row.get(field, ""))
                label = self._field_label("inventory", field)
                if value is None:
                    row_errors.append(f"{label} 必須是數字")
                elif field == "Length" and value <= 0:
                    row_errors.append(f"{label} 必須大於 0")
                elif field == "Qty" and value < 0:
                    row_errors.append(f"{label} 不可為負數")
            errors.extend(self._issues("error", "inventory", row_index, row_errors))

        material_keys = set()
        for row_index, row in enumerate(project_data.material_specs, start=1):
            row_errors = []
            usage = str(row.get("Usage", "") or "").strip()
            material_spec = str(row.get("Spec", "") or "").strip()
            if usage not in ("支撐", "圍令"):
                row_errors.append("用途必須是支撐或圍令")
            if not material_spec:
                row_errors.append("材料規格不可空白")
            key = usage, material_spec.casefold()
            if material_spec and key in material_keys:
                row_errors.append("用途與材料規格不可重複")
            material_keys.add(key)
            errors.extend(
                self._issues("error", "material_specs", row_index, row_errors)
            )

        return ProjectValidationReport(tuple(errors), tuple(warnings))

    def _coordinates(self, table: str, row: Mapping):
        values = []
        errors = []
        for field in ("StartX", "StartY", "EndX", "EndY"):
            value = _number(row.get(field, ""))
            if value is None:
                errors.append(f"{self._field_label(table, field)} 必須是數字")
            else:
                values.append(value)
        return (tuple(values) if len(values) == 4 else None), errors

    def _required(self, table: str, field: str) -> str:
        return f"{self._field_label(table, field)} 不可空白"

    @staticmethod
    def _issues(severity, table, row_index, messages):
        return [
            ValidationIssue(severity, table, row_index, message)
            for message in messages
        ]

    @staticmethod
    def _material_options(project_data: ProjectDataModel):
        options = {"支撐": set(), "圍令": set()}
        for row in project_data.material_specs:
            usage = str(row.get("Usage", "") or "").strip()
            material_spec = str(row.get("Spec", "") or "").strip()
            if usage in options and material_spec:
                options[usage].add(material_spec)
        return options

    @staticmethod
    def _format_position(value) -> str:
        number = float(value)
        return str(int(number)) if number.is_integer() else f"{number:g}"


__all__ = [
    "ProjectDataValidator",
    "ProjectValidationReport",
    "ValidationIssue",
]
