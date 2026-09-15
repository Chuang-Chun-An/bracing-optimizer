"""Build GUI-independent Solver inputs from normalized project data.

The builders in this module are read-only adapters.  They translate the
project model's geometry and inventory rows into application-level Solver
problems without mutating the project or depending on Tkinter.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping, Sequence

from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_mapper import ProjectDomainMappingError
from bracing_optimizer.algorithms import support


UNLIMITED_INVENTORY_QTY = 99
SUPPORT_USAGE = "支撐"
WALER_USAGE = "圍令"
SUPPORT_STATION_DEDUP_TOLERANCE_MM = 1.0


class SolverInputBuildError(ValueError):
    """Raised when project rows cannot form a valid Solver input."""

    def __init__(self, issues: Sequence[str]):
        self.issues = tuple(str(issue) for issue in issues if str(issue).strip())
        super().__init__("\n".join(self.issues))


@dataclass(frozen=True)
class SupportZoneInput:
    """Prepared engineering problem for every support in one zoning."""

    zoning: str
    configs: tuple[support.SupportConfig, ...]

    @property
    def units(self) -> tuple["SupportOptimizationUnit", ...]:
        grouped: dict[str, list[support.SupportConfig]] = {}
        order: list[str] = []
        for config in self.configs:
            group_id = str(config.shared_layout_group or "").strip()
            unit_id = f"group:{group_id}" if group_id else f"single:{config.support_id}"
            if unit_id not in grouped:
                grouped[unit_id] = []
                order.append(unit_id)
            grouped[unit_id].append(config)
        return tuple(
            SupportOptimizationUnit(
                unit_id=(
                    unit_id.removeprefix("group:")
                    if unit_id.startswith("group:")
                    else grouped[unit_id][0].support_id
                ),
                configs=tuple(grouped[unit_id]),
                require_shared_layout=unit_id.startswith("group:"),
            )
            for unit_id in order
        )


@dataclass(frozen=True)
class SupportOptimizationUnit:
    """One Phase 2 position: one strut, or two struts sharing a layout."""

    unit_id: str
    configs: tuple[support.SupportConfig, ...]
    require_shared_layout: bool = False


@dataclass(frozen=True)
class WalerProblemInput:
    """Prepared Waler problem used by both its dialog and optimization use case."""

    waler_id: str
    start_point: tuple[float, float]
    end_point: tuple[float, float]
    total_length: int
    forbidden_points: tuple[int, ...]
    material_spec: str
    stock_items: tuple[dict[str, object], ...]
    purchasable_lengths: tuple[int, ...]


def to_number(value):
    """Return a finite number, or ``None`` for blank/invalid input."""

    if isinstance(value, (int, float)):
        number = float(value)
    elif value is None:
        return None
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def line_length(x1, y1, x2, y2) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def parse_position_list(value) -> tuple[list[int | float], str | None]:
    """Parse the current comma-separated position format without mutation."""

    if value is None:
        return [], None
    text = str(value).strip().replace("，", ",")
    if not text:
        return [], None
    parts = text.split(",")
    if any(not part.strip() for part in parts):
        return [], "位置清單中有空白項目"

    positions = []
    for part in parts:
        token = part.strip()
        number = to_number(token)
        if number is None:
            return [], f"{token} 不是有效數字"
        positions.append(number)
    return positions, None


def project_point_onto_segment(
    start_point: tuple[float, float],
    end_point: tuple[float, float],
    point: tuple[float, float],
    *,
    tolerance: float = 1e-6,
) -> int | None:
    """Return distance from segment start when ``point`` lies on the segment."""

    wx1, wy1 = start_point
    wx2, wy2 = end_point
    px, py = point
    segment_length = line_length(wx1, wy1, wx2, wy2)
    if segment_length <= 0:
        return None
    dx = wx2 - wx1
    dy = wy2 - wy1
    projection = ((px - wx1) * dx + (py - wy1) * dy) / segment_length
    distance_to_line = abs(dx * (wy1 - py) - dy * (wx1 - px)) / segment_length
    if distance_to_line > tolerance:
        return None
    if projection < -tolerance or projection - segment_length > tolerance:
        return None
    return int(round(projection))


class InventoryLookup:
    """Query an in-memory snapshot of normalized project inventory rows."""

    def __init__(self, rows: Sequence[Mapping[str, object]]):
        self._rows = tuple(dict(row) for row in rows)

    def _rows_for(self, material_spec: str, usage: str):
        spec_key = str(material_spec or "").strip().casefold()
        usage_key = str(usage or "").strip().casefold()
        if not spec_key:
            return []
        return [
            row
            for row in self._rows
            if str(row.get("Spec", "") or "").strip().casefold() == spec_key
            and str(row.get("Usage", "") or "").strip().casefold() == usage_key
        ]

    def purchasable_lengths(
        self,
        material_spec: str = "",
        usage: str = "",
    ) -> list[int]:
        material_spec = str(material_spec or "").strip()
        usage_key = str(usage or "").strip().casefold()
        rows = (
            self._rows_for(material_spec, usage)
            if material_spec
            else [
                row
                for row in self._rows
                if not usage_key
                or str(row.get("Usage", "") or "").strip().casefold()
                in ("", usage_key)
            ]
        )
        lengths = set()
        for row in rows:
            length = to_number(row.get("Length"))
            if length is None or length <= 0:
                continue
            lengths.add(int(round(length)))
        if not lengths and not material_spec:
            return list(support.STEEL_LENGTHS)
        return sorted(lengths)

    def stock_items(
        self,
        material_spec: str = "",
        usage: str = "",
    ) -> list[dict[str, object]]:
        material_spec = str(material_spec or "").strip()
        if not material_spec:
            return [
                {
                    "id": f"UNLIMITED-{length}",
                    "length": length,
                    "qty": UNLIMITED_INVENTORY_QTY,
                }
                for length in self.purchasable_lengths("", usage)
            ]

        stock_items = []
        for index, row in enumerate(self._rows_for(material_spec, usage), start=1):
            length = to_number(row.get("Length"))
            quantity = to_number(row.get("Qty"))
            if length is None or quantity is None or quantity <= 0:
                continue
            stock_items.append({
                "id": str(row.get("ItemCode", "") or "").strip()
                or f"{material_spec}-{length}-{index}",
                "length": length,
                "qty": quantity,
            })
        return stock_items

    def quantity(self, material_spec: str, usage: str, length: int) -> int | float:
        material_spec = str(material_spec or "").strip()
        if not material_spec:
            return UNLIMITED_INVENTORY_QTY
        target_length = int(round(length))
        total = 0
        for row in self._rows_for(material_spec, usage):
            row_length = to_number(row.get("Length"))
            quantity = to_number(row.get("Qty"))
            if row_length is None or quantity is None or quantity < 0:
                continue
            if int(round(row_length)) == target_length:
                total += quantity
        return total


class SupportInputBuilder:
    """Translate project strut rows into immutable zoning input containers."""

    def build_zone(
        self,
        project_data: ProjectDataModel,
        zoning: str,
    ) -> SupportZoneInput:
        normalized_zoning = str(zoning or "").strip()
        return SupportZoneInput(
            zoning=normalized_zoning,
            configs=tuple(self._build_configs(project_data, normalized_zoning)),
        )

    def build_all(self, project_data: ProjectDataModel) -> tuple[support.SupportConfig, ...]:
        return tuple(self._build_configs(project_data, None))

    def build_one(
        self,
        project_data: ProjectDataModel,
        support_id: str,
    ) -> support.SupportConfig | None:
        target_id = str(support_id or "").strip()
        return next(
            (
                config
                for config in self._build_configs(project_data, None)
                if str(config.support_id).strip() == target_id
            ),
            None,
        )

    @staticmethod
    def _build_configs(
        project_data: ProjectDataModel,
        zoning: str | None,
    ) -> list[support.SupportConfig]:
        try:
            domain = project_data.to_domain(strict=True)
        except ProjectDomainMappingError as exc:
            raise SolverInputBuildError(exc.issues) from exc
        lookup = InventoryLookup(project_data.inventory)
        waler_type_by_id = {
            waler.id: support.normalize_waler_type(waler.material_spec)
            for waler in domain.walers
            if waler.id
        }
        configs = []
        issues = []
        for strut in domain.struts:
            if zoning is not None and strut.zoning != zoning:
                continue

            support_id = strut.id
            if strut.axis is None:
                issues.append(
                    f"支撐 {support_id or '<未命名>'} 缺少有效長度或完整座標"
                )
                continue
            total_length = strut.axis.length
            if total_length <= 0:
                issues.append(f"支撐 {support_id or '<未命名>'} 長度必須大於 0")
                continue
            group_id = str(strut.shared_layout_group or "").strip()
            pile_centers = [
                int(round(value)) for value in strut.column_positions
            ]
            waler_centers = [
                int(round(value)) for value in strut.beam_positions
            ]
            from_waler_type = waler_type_by_id.get(
                strut.from_waler_id,
                "Steel",
            )
            to_waler_type = waler_type_by_id.get(
                strut.to_waler_id,
                "Steel",
            )
            configs.append(support.SupportConfig(
                support_id=support_id,
                total_length=int(round(total_length)),
                pile_centers=pile_centers,
                waler_centers=waler_centers,
                target_jack_region=strut.target_jack_region,
                material_spec=strut.material_spec,
                from_waler_type=from_waler_type,
                to_waler_type=to_waler_type,
                steel_lengths=lookup.purchasable_lengths(
                    strut.material_spec,
                    SUPPORT_USAGE,
                ),
                shared_layout_group=group_id,
            ))

        if issues:
            raise SolverInputBuildError(issues)
        grouped_configs: dict[str, list[support.SupportConfig]] = {}
        ordered_keys: list[str] = []
        for config in configs:
            key = (
                f"group:{config.shared_layout_group}"
                if config.shared_layout_group
                else f"single:{config.support_id}"
            )
            if key not in grouped_configs:
                grouped_configs[key] = []
                ordered_keys.append(key)
            grouped_configs[key].append(config)
        for key, group_configs in grouped_configs.items():
            if not key.startswith("group:"):
                continue
            # DXFImportResult.to_project_rows() has already aligned every
            # member's start/end and station values to the group's canonical
            # FromWaler -> ToWaler direction.  Union in that formal Project
            # station frame so old or manually edited rows cannot omit a
            # physical Column constraint from one lane.
            merged_pile_centers: list[float] = []
            for value in sorted(
                float(position)
                for config in group_configs
                for position in config.pile_centers
            ):
                if not any(
                    abs(value - existing)
                    <= SUPPORT_STATION_DEDUP_TOLERANCE_MM
                    for existing in merged_pile_centers
                ):
                    merged_pile_centers.append(value)
            shared_pile_centers = [
                int(round(value)) for value in merged_pile_centers
            ]
            grouped_configs[key] = [
                replace(
                    config,
                    pile_centers=list(shared_pile_centers),
                )
                for config in group_configs
            ]
        return [
            config
            for key in ordered_keys
            for config in grouped_configs[key]
        ]


class WalerInputBuilder:
    """Translate all project Waler rows while preserving eager-build behavior."""

    @staticmethod
    def build_all(
        project_data: ProjectDataModel,
    ) -> dict[str, WalerProblemInput]:
        lookup = InventoryLookup(project_data.inventory)
        domain = project_data.to_domain(strict=False)
        prepared = {}
        issues = []
        for waler in domain.walers:
            waler_id = waler.id
            if not waler_id:
                continue
            if waler.axis is None:
                issues.append(f"圍令 {waler_id} 缺少完整座標")
                continue
            start_point = waler.axis.start.as_tuple()
            end_point = waler.axis.end.as_tuple()
            total_length = waler.axis.length
            if total_length <= 0:
                issues.append(f"圍令 {waler_id} 長度必須大於 0")
                continue
            prepared[waler_id] = {
                "start_point": start_point,
                "end_point": end_point,
                "total_length": int(round(total_length)),
                "forbidden_points": [],
                "material_spec": waler.material_spec,
            }

        if issues:
            raise SolverInputBuildError(issues)

        def add_projected_point(waler_id, point, before=None, after=None):
            if not waler_id or waler_id not in prepared or None in point:
                return
            data = prepared[waler_id]
            position = project_point_onto_segment(
                data["start_point"],
                data["end_point"],
                point,
            )
            if position is None:
                return
            data["forbidden_points"].append(position)
            if before is not None:
                data["forbidden_points"].append(position - before)
            if after is not None:
                data["forbidden_points"].append(position + after)

        for strut in domain.struts:
            start = strut.axis.start.as_tuple() if strut.axis is not None else (None, None)
            end = strut.axis.end.as_tuple() if strut.axis is not None else (None, None)
            add_projected_point(
                strut.from_waler_id,
                start,
                strut.from_brace_to_waler_start_len,
                strut.from_brace_to_waler_end_len,
            )
            add_projected_point(
                strut.to_waler_id,
                end,
                strut.to_brace_to_waler_start_len,
                strut.to_brace_to_waler_end_len,
            )

        for brace in domain.braces:
            start = brace.axis.start.as_tuple() if brace.axis is not None else (None, None)
            end = brace.axis.end.as_tuple() if brace.axis is not None else (None, None)
            add_projected_point(
                brace.from_waler_id,
                start,
            )
            add_projected_point(
                brace.to_waler_id,
                end,
            )

        results = {}
        for waler_id, data in prepared.items():
            material_spec = data["material_spec"]
            results[waler_id] = WalerProblemInput(
                waler_id=waler_id,
                start_point=data["start_point"],
                end_point=data["end_point"],
                total_length=data["total_length"],
                forbidden_points=tuple(sorted(set(data["forbidden_points"]))),
                material_spec=material_spec,
                stock_items=tuple(lookup.stock_items(material_spec, WALER_USAGE)),
                purchasable_lengths=tuple(
                    lookup.purchasable_lengths(material_spec, WALER_USAGE)
                ),
            )
        return results


__all__ = [
    "InventoryLookup",
    "SolverInputBuildError",
    "SupportOptimizationUnit",
    "SupportInputBuilder",
    "SupportZoneInput",
    "UNLIMITED_INVENTORY_QTY",
    "WalerInputBuilder",
    "WalerProblemInput",
    "line_length",
    "parse_position_list",
    "project_point_onto_segment",
    "to_number",
]
