"""DXF component recognition and conversion to Solver-safe engineering models.

``ezdxf`` entities live only inside :class:`DXFImporter`.  The public import
result contains immutable engineering lines and serializable diagnostics; Waler
lines are the inner contact faces while Strut/Brace lines are their axes.  The
Solver therefore never depends on a DXF entity or block object.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from enum import IntFlag, auto
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from cad_view_interaction import CADViewInteractionController, CADViewport

try:
    import ezdxf
    from ezdxf.disassemble import recursive_decompose as _recursive_decompose
except ImportError:  # pragma: no cover - only a broken installation
    ezdxf = None
    _recursive_decompose = None


Point = tuple[float, float]
WorkArea = tuple[int, int, int, int]
_WINDOW_GEOMETRY_PATTERN = re.compile(
    r"^\s*(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?\s*$"
)
ERROR_SEVERITIES = {"error", "critical"}
CONNECTION_VALIDATION_CODES = {
    "AMBIGUOUS_WALER_CONNECTION",
    "STRUT_NOT_CONNECTED",
    "STRUT_ONE_END_NOT_CONNECTED",
    "BRACE_NOT_CONNECTED",
    "BRACE_ONE_END_NOT_CONNECTED",
}
COMPONENT_ASSOCIATION_CODES = {
    "COLUMN_NOT_ASSOCIATED",
    "BEAM_NOT_ASSOCIATED",
    "AMBIGUOUS_COMPONENT_ASSOCIATION",
    "BEAM_CROSSING_SNAPPED",
    "BEAM_OVERLAPS_STRUT",
}


def _parse_window_geometry(
    geometry: str,
) -> tuple[int, int, int | None, int | None] | None:
    match = _WINDOW_GEOMETRY_PATTERN.fullmatch(str(geometry or ""))
    if match is None:
        return None
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        return None
    x = int(match.group(3)) if match.group(3) is not None else None
    y = int(match.group(4)) if match.group(4) is not None else None
    return width, height, x, y


def fit_window_geometry_to_work_areas(
    requested: str,
    fallback: str,
    work_areas: Sequence[WorkArea],
) -> str:
    """Keep a remembered Tk window rectangle fully inside an active monitor."""

    parsed = _parse_window_geometry(requested) or _parse_window_geometry(fallback)
    usable_areas = tuple(
        area
        for area in work_areas
        if area[2] > area[0] and area[3] > area[1]
    )
    if parsed is None or not usable_areas:
        return fallback

    width, height, x, y = parsed
    if x is None or y is None:
        fallback_parsed = _parse_window_geometry(fallback)
        if (
            fallback_parsed is not None
            and fallback_parsed[2] is not None
            and fallback_parsed[3] is not None
        ):
            x, y = fallback_parsed[2], fallback_parsed[3]
        else:
            left, top, right, bottom = usable_areas[0]
            x = left + max((right - left - width) // 2, 0)
            y = top + max((bottom - top - height) // 2, 0)

    assert x is not None and y is not None

    def intersection_area(area: WorkArea) -> int:
        left, top, right, bottom = area
        overlap_width = max(0, min(x + width, right) - max(x, left))
        overlap_height = max(0, min(y + height, bottom) - max(y, top))
        return overlap_width * overlap_height

    intersecting = max(usable_areas, key=intersection_area)
    if intersection_area(intersecting) > 0:
        target = intersecting
    else:
        center_x = x + width / 2
        center_y = y + height / 2

        def distance_to_area(area: WorkArea) -> float:
            left, top, right, bottom = area
            dx = max(left - center_x, 0.0, center_x - right)
            dy = max(top - center_y, 0.0, center_y - bottom)
            return dx * dx + dy * dy

        target = min(usable_areas, key=distance_to_area)

    left, top, right, bottom = target
    available_width = right - left
    available_height = bottom - top
    width = min(width, available_width)
    height = min(height, available_height)
    x = min(max(x, left), right - width)
    y = min(max(y, top), bottom - height)

    def offset(value: int) -> str:
        return f"+{value}" if value >= 0 else str(value)

    return f"{width}x{height}{offset(x)}{offset(y)}"


def _active_monitor_work_areas(window: Any) -> tuple[WorkArea, ...]:
    """Return active monitor work areas, including negative multi-monitor coordinates."""

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class MonitorInfo(ctypes.Structure):
                _fields_ = (
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                )

            monitors: list[tuple[bool, WorkArea]] = []
            callback_type = ctypes.WINFUNCTYPE(
                wintypes.BOOL,
                wintypes.HANDLE,
                wintypes.HDC,
                ctypes.POINTER(wintypes.RECT),
                wintypes.LPARAM,
            )
            user32 = ctypes.windll.user32

            @callback_type
            def collect_monitor(
                monitor: Any,
                _device_context: Any,
                _monitor_rect: Any,
                _data: Any,
            ) -> bool:
                info = MonitorInfo()
                info.cbSize = ctypes.sizeof(MonitorInfo)
                if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    work = info.rcWork
                    monitors.append(
                        (
                            bool(info.dwFlags & 1),
                            (
                                int(work.left),
                                int(work.top),
                                int(work.right),
                                int(work.bottom),
                            ),
                        )
                    )
                return True

            user32.EnumDisplayMonitors(None, None, collect_monitor, 0)
            if monitors:
                monitors.sort(key=lambda item: not item[0])
                return tuple(area for _is_primary, area in monitors)
        except (AttributeError, OSError, TypeError, ValueError):
            pass

    try:
        left = int(window.winfo_vrootx())
        top = int(window.winfo_vrooty())
        width = int(window.winfo_vrootwidth())
        height = int(window.winfo_vrootheight())
        if width > 0 and height > 0:
            return ((left, top, left + width, top + height),)
    except Exception:
        pass
    return ((0, 0, 1920, 1080),)


class DXFImportError(RuntimeError):
    """Raised when a DXF cannot be read or a blocked result is exported."""


@dataclass(frozen=True)
class GeometryTolerances:
    """All geometry/recognition tolerances, in drawing units (normally mm)."""

    endpoint_tolerance_mm: float = 50.0
    parallel_angle_tolerance_deg: float = 2.0
    width_tolerance_mm: float = 50.0
    collinear_tolerance_mm: float = 25.0
    duplicate_tolerance_mm: float = 50.0
    minimum_component_length_mm: float = 100.0
    connection_tolerance_mm: float = 250.0
    component_association_tolerance_mm: float = 250.0
    # Columns are commonly drawn beside a Strut centreline because both are
    # represented by their physical H-section footprints.  Their association
    # tolerance is therefore derived from both section widths plus this
    # installation/drafting allowance, while the maximum prevents an
    # unrelated distant Strut from being selected.
    column_association_clearance_mm: float = 150.0
    maximum_column_association_tolerance_mm: float = 750.0
    beam_crossing_tolerance_mm: float = 100.0
    beam_crossing_duplicate_tolerance_mm: float = 1.0
    ambiguous_connection_delta_mm: float = 25.0
    maximum_component_width_mm: float = 600.0
    minimum_slenderness_ratio: float = 1.5
    minimum_projection_overlap_ratio: float = 0.8
    ambiguous_candidate_score_delta: float = 0.03


@dataclass(frozen=True)
class BlockInstanceInfo:
    handle: str
    block_name: str
    insertion_point: Point
    rotation: float
    xscale: float
    yscale: float


@dataclass(frozen=True)
class ValidationMessage:
    severity: str
    code: str
    message: str
    role: str = ""
    source_handles: tuple[str, ...] = ()


@dataclass(frozen=True)
class EngineeringLineCandidate:
    """Legacy/internal line evidence used to derive endpoint candidates."""

    id: str
    label: str
    world_start: Point
    world_end: Point
    source: str


@dataclass(frozen=True)
class CandidatePoint:
    """One exact world-coordinate point offered for a member endpoint."""

    id: str
    world_point: Point
    local_point: Point
    point_type: str
    label: str
    source_handles: tuple[str, ...] = ()
    source_entity_types: tuple[str, ...] = ()
    recommended_for: tuple[str, ...] = ()
    score: float = 0.0
    point_types: tuple[str, ...] = ()
    valid_for: tuple[str, ...] = ("start", "end")
    component_id: str = ""


@dataclass(frozen=True)
class CoordinateSystem:
    mode: str = "world"
    origin_x: float = 0.0
    origin_y: float = 0.0
    source: str = "cad_world"

    def __post_init__(self) -> None:
        if self.mode not in {"world", "local"}:
            raise ValueError(f"不支援的座標系統模式：{self.mode}")
        if not math.isfinite(self.origin_x) or not math.isfinite(self.origin_y):
            raise ValueError("座標原點必須是有限數字")

    def transform(self, point: Point) -> Point:
        if self.mode == "local":
            return point[0] - self.origin_x, point[1] - self.origin_y
        return point


def parse_coordinate_origin(origin_x: str, origin_y: str) -> tuple[float, float]:
    """Validate coordinate-entry text using the user-facing error contract."""

    if not str(origin_x).strip() or not str(origin_y).strip():
        raise DXFImportError("請輸入原點座標")
    try:
        x_value, y_value = float(origin_x), float(origin_y)
    except (TypeError, ValueError) as exc:
        raise DXFImportError("原點座標格式錯誤") from exc
    if not math.isfinite(x_value) or not math.isfinite(y_value):
        raise DXFImportError("原點座標格式錯誤")
    return x_value, y_value


def coordinate_system_from_candidate(candidate: CandidatePoint) -> CoordinateSystem:
    """Use one explicitly selected DXF point as the exact local origin."""

    return CoordinateSystem(
        "local",
        float(candidate.world_point[0]),
        float(candidate.world_point[1]),
        "selected_candidate_point",
    )


def normalize_project_coordinate(value: Any) -> int:
    """Normalize a Solver-facing drawing coordinate to the nearest millimetre."""

    number = float(value)
    return math.floor(number + 0.5) if number >= 0 else math.ceil(number - 0.5)


@dataclass(frozen=True)
class Waler:
    id: str
    start: Point
    end: Point
    source_layer: str
    source_handles: tuple[str, ...]
    source_entity_types: tuple[str, ...]
    recognition_method: str
    centerline_computed: bool
    source_width: float
    confidence: float
    warnings: tuple[str, ...] = ()
    block_instances: tuple[BlockInstanceInfo, ...] = ()
    engineering_line_kind: str = "inner_line"
    world_start: Point | None = None
    world_end: Point | None = None
    local_start: Point | None = None
    local_end: Point | None = None
    line_candidates: tuple[EngineeringLineCandidate, ...] = ()
    selected_candidate_id: str = ""
    candidate_points: tuple[CandidatePoint, ...] = ()
    recommended_start_point_id: str = ""
    recommended_end_point_id: str = ""
    selected_start_point_id: str = ""
    selected_end_point_id: str = ""
    selection_source: str = "auto"

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_start", self.start if self.world_start is None else self.world_start)
        object.__setattr__(self, "world_end", self.end if self.world_end is None else self.world_end)
        object.__setattr__(self, "local_start", self.start if self.local_start is None else self.local_start)
        object.__setattr__(self, "local_end", self.end if self.local_end is None else self.local_end)

    @property
    def source_type(self) -> str:
        return "+".join(self.source_entity_types)

    def to_project_row(self) -> dict[str, Any]:
        recognition = f"DXF {self.recognition_method} ({self.confidence:.0%})"
        return {
            "WalerID": self.id,
            "StartX": self.start[0],
            "StartY": self.start[1],
            "EndX": self.end[0],
            "EndY": self.end[1],
            "material_spec": "",
            "Remark": recognition,
        }


@dataclass(frozen=True)
class Strut:
    id: str
    start: Point
    end: Point
    source_layer: str
    source_handles: tuple[str, ...]
    source_entity_types: tuple[str, ...]
    recognition_method: str
    centerline_computed: bool
    source_width: float
    from_waler: str
    to_waler: str
    confidence: float
    warnings: tuple[str, ...] = ()
    block_instances: tuple[BlockInstanceInfo, ...] = ()
    world_start: Point | None = None
    world_end: Point | None = None
    local_start: Point | None = None
    local_end: Point | None = None
    line_candidates: tuple[EngineeringLineCandidate, ...] = ()
    selected_candidate_id: str = ""
    candidate_points: tuple[CandidatePoint, ...] = ()
    recommended_start_point_id: str = ""
    recommended_end_point_id: str = ""
    selected_start_point_id: str = ""
    selected_end_point_id: str = ""
    selection_source: str = "auto"
    beam_positions: tuple[float, ...] = ()
    column_positions: tuple[float, ...] = ()
    associated_columns: tuple[str, ...] = ()
    associated_beams: tuple[str, ...] = ()
    from_brace_to_waler_start_len: float = 0.0
    from_brace_to_waler_end_len: float = 0.0
    to_brace_to_waler_start_len: float = 0.0
    to_brace_to_waler_end_len: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_start", self.start if self.world_start is None else self.world_start)
        object.__setattr__(self, "world_end", self.end if self.world_end is None else self.world_end)
        object.__setattr__(self, "local_start", self.start if self.local_start is None else self.local_start)
        object.__setattr__(self, "local_end", self.end if self.local_end is None else self.local_end)

    @property
    def source_type(self) -> str:
        return "+".join(self.source_entity_types)

    def to_project_row(self) -> dict[str, Any]:
        def position_text(values: Sequence[float]) -> str:
            return ",".join(f"{value:g}" for value in values)

        return {
            "StrutID": self.id,
            "FromWaler": self.from_waler,
            "ToWaler": self.to_waler,
            "StartX": self.start[0],
            "StartY": self.start[1],
            "EndX": self.end[0],
            "EndY": self.end[1],
            "material_spec": "",
            "BeamPositions": position_text(self.beam_positions),
            "ColumnPositions": position_text(self.column_positions),
            "AssociatedColumnIDs": ",".join(self.associated_columns),
            "AssociatedBeamIDs": ",".join(self.associated_beams),
            "FromBraceToWalerStartLen": self.from_brace_to_waler_start_len,
            "FromBraceToWalerEndLen": self.from_brace_to_waler_end_len,
            "ToBraceToWalerStartLen": self.to_brace_to_waler_start_len,
            "ToBraceToWalerEndLen": self.to_brace_to_waler_end_len,
            "TargetJackRegion": 2,
            "Zoning": "DXF",
        }


@dataclass(frozen=True)
class Brace:
    id: str
    start: Point
    end: Point
    source_layer: str
    source_handles: tuple[str, ...]
    source_entity_types: tuple[str, ...]
    recognition_method: str
    centerline_computed: bool
    source_width: float
    from_waler: str
    to_waler: str
    confidence: float
    warnings: tuple[str, ...] = ()
    block_instances: tuple[BlockInstanceInfo, ...] = ()
    world_start: Point | None = None
    world_end: Point | None = None
    local_start: Point | None = None
    local_end: Point | None = None
    line_candidates: tuple[EngineeringLineCandidate, ...] = ()
    selected_candidate_id: str = ""
    candidate_points: tuple[CandidatePoint, ...] = ()
    recommended_start_point_id: str = ""
    recommended_end_point_id: str = ""
    selected_start_point_id: str = ""
    selected_end_point_id: str = ""
    selection_source: str = "auto"

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_start", self.start if self.world_start is None else self.world_start)
        object.__setattr__(self, "world_end", self.end if self.world_end is None else self.world_end)
        object.__setattr__(self, "local_start", self.start if self.local_start is None else self.local_start)
        object.__setattr__(self, "local_end", self.end if self.local_end is None else self.local_end)

    @property
    def source_type(self) -> str:
        return "+".join(self.source_entity_types)

    def to_project_row(self) -> dict[str, Any]:
        return {
            "BraceID": self.id,
            "FromWaler": self.from_waler,
            "ToWaler": self.to_waler,
            "StartX": self.start[0],
            "StartY": self.start[1],
            "EndX": self.end[0],
            "EndY": self.end[1],
        }


@dataclass(frozen=True)
class AuxiliaryComponent:
    """Recognized non-Solver linear component retained in the import model."""

    id: str
    start: Point
    end: Point
    source_layer: str
    source_handles: tuple[str, ...]
    source_entity_types: tuple[str, ...]
    recognition_method: str
    centerline_computed: bool
    source_width: float
    confidence: float
    warnings: tuple[str, ...] = ()
    block_instances: tuple[BlockInstanceInfo, ...] = ()
    world_start: Point | None = None
    world_end: Point | None = None
    local_start: Point | None = None
    local_end: Point | None = None
    line_candidates: tuple[EngineeringLineCandidate, ...] = ()
    selected_candidate_id: str = ""
    candidate_points: tuple[CandidatePoint, ...] = ()
    recommended_start_point_id: str = ""
    recommended_end_point_id: str = ""
    selected_start_point_id: str = ""
    selected_end_point_id: str = ""
    selection_source: str = "auto"
    associated_strut_id: str = ""
    association_station: float | None = None
    association_distance: float | None = None
    world_association_point: Point | None = None
    local_association_point: Point | None = None
    reference_point: Point | None = None
    world_reference_point: Point | None = None
    local_reference_point: Point | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_start", self.start if self.world_start is None else self.world_start)
        object.__setattr__(self, "world_end", self.end if self.world_end is None else self.world_end)
        object.__setattr__(self, "local_start", self.start if self.local_start is None else self.local_start)
        object.__setattr__(self, "local_end", self.end if self.local_end is None else self.local_end)
        default_reference = _midpoint(self.start, self.end)
        object.__setattr__(
            self,
            "reference_point",
            default_reference if self.reference_point is None else self.reference_point,
        )
        object.__setattr__(
            self,
            "world_reference_point",
            default_reference
            if self.world_reference_point is None
            else self.world_reference_point,
        )
        object.__setattr__(
            self,
            "local_reference_point",
            default_reference
            if self.local_reference_point is None
            else self.local_reference_point,
        )

    def to_project_row(self) -> dict[str, Any]:
        return {
            "ID": self.id,
            "StartX": self.start[0],
            "StartY": self.start[1],
            "EndX": self.end[0],
            "EndY": self.end[1],
            "SourceLayer": self.source_layer,
            "AssociatedStrutID": self.associated_strut_id,
            "AssociationStation": self.association_station,
            "AssociationDistance": self.association_distance,
            "ReferenceX": self.reference_point[0] if self.reference_point else None,
            "ReferenceY": self.reference_point[1] if self.reference_point else None,
        }


@dataclass(frozen=True)
class Column(AuxiliaryComponent):
    """DXF-classified intermediate-column engineering line."""


@dataclass(frozen=True)
class BeamCrossing:
    """One physical crossing between a bearer-beam path and a Strut."""

    beam_id: str
    strut_id: str
    world_point: Point
    local_point: Point
    strut_station: float
    beam_segment_index: int
    distance: float = 0.0
    recognition_method: str = "segment_intersection"


@dataclass(frozen=True)
class Beam(AuxiliaryComponent):
    """Bearer beam retained as an ordered path instead of one chord."""

    world_path: tuple[Point, ...] = ()
    local_path: tuple[Point, ...] = ()
    path: tuple[Point, ...] = ()
    associated_strut_ids: tuple[str, ...] = ()
    crossings: tuple[BeamCrossing, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        default_path = (self.world_start, self.world_end)
        world_path = self.world_path or default_path
        local_path = self.local_path or world_path
        active_path = self.path or world_path
        object.__setattr__(self, "world_path", tuple(world_path))
        object.__setattr__(self, "local_path", tuple(local_path))
        object.__setattr__(self, "path", tuple(active_path))

    def to_project_row(self) -> dict[str, Any]:
        row = super().to_project_row()
        row.update(
            WorldPath=[list(point) for point in self.world_path],
            LocalPath=[list(point) for point in self.local_path],
            AssociatedStrutIDs=",".join(self.associated_strut_ids),
            Crossings=[asdict(crossing) for crossing in self.crossings],
        )
        return row


@dataclass(frozen=True)
class CornerBrace(AuxiliaryComponent):
    """DXF-classified corner-brace engineering line."""


@dataclass(frozen=True)
class LayerInfo:
    name: str
    entity_count: int
    entity_types: Mapping[str, int]


@dataclass(frozen=True)
class EntityDebugInfo:
    role: str
    layer: str
    entity_type: str
    handle: str
    status: str
    severity: str = "info"
    output_ids: tuple[str, ...] = ()
    block_instance: str = ""
    detail: str = ""


@dataclass(frozen=True)
class SourceGeometry:
    role: str
    source_handle: str
    points: tuple[Point, ...]
    closed: bool
    source_layer: str = ""
    source_entity_type: str = ""


@dataclass(frozen=True)
class SourceText:
    """Preview-only text retained from an auxiliary DXF layer."""

    role: str
    source_handle: str
    text: str
    position: Point
    height: float = 0.0
    rotation: float = 0.0
    source_layer: str = ""
    source_entity_type: str = ""


@dataclass(frozen=True)
class ComponentAssociation:
    """One confirmed Column/Beam ownership relation to a Solver strut."""

    component_id: str
    component_role: str
    strut_id: str
    station: float
    distance: float
    world_projection_point: Point
    local_projection_point: Point


@dataclass(frozen=True)
class ProblemRecord:
    severity: str
    code: str
    component: str
    description: str
    role: str
    source_handles: tuple[str, ...]
    member_ids: tuple[str, ...]


@dataclass
class SelectionState:
    """Single source of truth for all non-Solver import interactions."""

    selected_component_id: str = ""
    hovered_component_id: str = ""
    mode: str = "idle"
    selected_candidate_point_id: str = ""
    selected_candidate_source: str = ""
    hovered_candidate_point_id: str = ""
    preview_candidate_point_id: str = ""
    selected_start_point_id: str = ""
    selected_end_point_id: str = ""
    pending_start_point_id: str = ""
    pending_end_point_id: str = ""
    selection_source: str = "programmatic"
    pending_selection_source: str = "auto"
    pick_baseline_start_point_id: str = ""
    pick_baseline_end_point_id: str = ""
    revision: int = 0


class PreviewController(CADViewInteractionController):
    """Backward-compatible name for the shared CAD interaction controller."""

    nearest_member = CADViewInteractionController.nearest_segment
    candidate_hits = CADViewInteractionController.point_hits


@dataclass(frozen=True)
class ValidationOverviewItem:
    level: str
    text: str


@dataclass(frozen=True)
class DXFImportResult:
    """Serializable result of recognition, validation and connection analysis."""

    source_path: str
    layer_names: tuple[str, ...]
    selected_layers: Mapping[str, tuple[str, ...]]
    layer_info: tuple[LayerInfo, ...]
    walers: tuple[Waler, ...]
    struts: tuple[Strut, ...]
    braces: tuple[Brace, ...]
    entity_debug: tuple[EntityDebugInfo, ...]
    messages: tuple[ValidationMessage, ...]
    source_entity_counts: Mapping[str, int]
    source_geometry: tuple[SourceGeometry, ...] = ()
    source_texts: tuple[SourceText, ...] = ()
    coordinate_system: CoordinateSystem = CoordinateSystem()
    columns: tuple[Column, ...] = ()
    beams: tuple[Beam, ...] = ()
    corner_braces: tuple[CornerBrace, ...] = ()
    layer_classification: Mapping[str, str] = field(default_factory=dict)
    component_associations: tuple[ComponentAssociation, ...] = ()
    beam_crossings: tuple[BeamCrossing, ...] = ()

    @property
    def can_import(self) -> bool:
        return not any(message.severity in ERROR_SEVERITIES for message in self.messages)

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(
            f"{item.code}: {item.message}"
            for item in self.messages
            if item.severity in {"warning", "error", "critical"}
        )

    def summary(self) -> dict[str, Any]:
        method_counts = Counter(
            member.recognition_method
            for member in (
                *self.walers,
                *self.struts,
                *self.braces,
                *self.columns,
                *self.beams,
                *self.corner_braces,
            )
        )

        def connection_counts(members: Sequence[Strut | Brace]) -> tuple[int, int, int]:
            fully = sum(bool(member.from_waler and member.to_waler) for member in members)
            partial = sum(bool(member.from_waler) ^ bool(member.to_waler) for member in members)
            return fully, partial, len(members) - fully - partial

        full_s, partial_s, none_s = connection_counts(self.struts)
        full_b, partial_b, none_b = connection_counts(self.braces)
        severities = Counter(message.severity for message in self.messages)
        failed_codes = {
            "WALER_ENGINEERING_LINE_FAILED",
            "STRUT_CENTERLINE_FAILED",
            "BRACE_CENTERLINE_FAILED",
            "WALER_RECOGNITION_FAILED",
            "STRUT_RECOGNITION_FAILED",
            "BRACE_RECOGNITION_FAILED",
        }
        return {
            "selected_layers": dict(self.selected_layers),
            "source_entities": dict(self.source_entity_counts),
            "recognized_components": {
                "walers": len(self.walers),
                "struts": len(self.struts),
                "braces": len(self.braces),
                "columns": len(self.columns),
                "beams": len(self.beams),
                "corner_braces": len(self.corner_braces),
            },
            "auxiliary_geometry": sum(
                geometry.role == "auxiliary"
                for geometry in self.source_geometry
            ),
            "centerlines": {
                "existing": method_counts["existing_centerline"],
                "computed": sum(
                    member.centerline_computed
                    for member in (
                        *self.walers,
                        *self.struts,
                        *self.braces,
                        *self.columns,
                        *self.beams,
                        *self.corner_braces,
                    )
                ),
                "failed": sum(message.code in failed_codes for message in self.messages),
            },
            "connection_status": {
                "fully_connected_struts": full_s,
                "partially_connected_struts": partial_s,
                "unconnected_struts": none_s,
                "fully_connected_braces": full_b,
                "partially_connected_braces": partial_b,
                "unconnected_braces": none_b,
            },
            "messages": {
                "info": severities["info"],
                "warning": severities["warning"],
                "error": severities["error"],
                "critical": severities["critical"],
            },
            "can_import": self.can_import,
        }

    def to_project_rows(
        self,
        existing_rows: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return 1 mm-normalized Solver rows; keep the DXF model full precision."""

        if not self.can_import:
            codes = sorted({item.code for item in self.messages if item.severity in ERROR_SEVERITIES})
            raise DXFImportError(f"DXF 轉換含阻擋錯誤，無法匯入：{', '.join(codes)}")
        existing_rows = existing_rows or {}
        used = {
            "walers": {str(row.get("WalerID", "")) for row in existing_rows.get("walers", ())},
            "struts": {str(row.get("StrutID", "")) for row in existing_rows.get("struts", ())},
            "braces": {str(row.get("BraceID", "")) for row in existing_rows.get("braces", ())},
        }

        def allocate(table: str, prefix: str, count: int) -> list[str]:
            result: list[str] = []
            number = 1
            while len(result) < count:
                candidate = f"{prefix}{number}"
                number += 1
                if candidate not in used[table]:
                    used[table].add(candidate)
                    result.append(candidate)
            return result

        def normalize_row_coordinates(row: dict[str, Any]) -> dict[str, Any]:
            for field_name in (
                "StartX",
                "StartY",
                "EndX",
                "EndY",
                "ReferenceX",
                "ReferenceY",
            ):
                value = row.get(field_name)
                if value is not None and value != "":
                    row[field_name] = normalize_project_coordinate(value)
            return row

        waler_ids = allocate("walers", "W", len(self.walers))
        strut_ids = allocate("struts", "S", len(self.struts))
        brace_ids = allocate("braces", "B", len(self.braces))
        id_map = {old.id: new for old, new in zip(self.walers, waler_ids)}
        strut_id_map = {old.id: new for old, new in zip(self.struts, strut_ids)}
        walers = []
        for member, identifier in zip(self.walers, waler_ids):
            row = normalize_row_coordinates(member.to_project_row())
            row["WalerID"] = identifier
            walers.append(row)
        struts = []
        for member, identifier in zip(self.struts, strut_ids):
            row = normalize_row_coordinates(member.to_project_row())
            row.update(
                StrutID=identifier,
                FromWaler=id_map.get(member.from_waler, member.from_waler),
                ToWaler=id_map.get(member.to_waler, member.to_waler),
            )
            struts.append(row)
        braces = []
        for member, identifier in zip(self.braces, brace_ids):
            row = normalize_row_coordinates(member.to_project_row())
            row.update(
                BraceID=identifier,
                FromWaler=id_map.get(member.from_waler, member.from_waler),
                ToWaler=id_map.get(member.to_waler, member.to_waler),
            )
            braces.append(row)

        def auxiliary_rows(
            members: Sequence[AuxiliaryComponent],
        ) -> list[dict[str, Any]]:
            rows = []
            for member in members:
                row = normalize_row_coordinates(member.to_project_row())
                row["AssociatedStrutID"] = strut_id_map.get(
                    member.associated_strut_id,
                    member.associated_strut_id,
                )
                if isinstance(member, Beam):
                    row["AssociatedStrutIDs"] = ",".join(
                        strut_id_map.get(strut_id, strut_id)
                        for strut_id in member.associated_strut_ids
                    )
                    row["Crossings"] = [
                        {
                            **asdict(crossing),
                            "strut_id": strut_id_map.get(
                                crossing.strut_id,
                                crossing.strut_id,
                            ),
                        }
                        for crossing in member.crossings
                    ]
                rows.append(row)
            return rows

        return {
            "walers": walers,
            "struts": struts,
            "braces": braces,
            "columns": auxiliary_rows(self.columns),
            "beams": auxiliary_rows(self.beams),
            "corner_braces": auxiliary_rows(self.corner_braces),
        }

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "coordinate_system": asdict(self.coordinate_system),
            "source_path": self.source_path,
            "layer_names": list(self.layer_names),
            "selected_layers": dict(self.selected_layers),
            "layer_classification": dict(self.layer_classification),
            "layer_assignments": [
                {
                    "layer_name": layer_name,
                    "layer_type": layer_type,
                }
                for layer_name, layer_type in self.layer_classification.items()
            ],
            "layer_info": [asdict(item) for item in self.layer_info],
            "converted": {
                "walers": [asdict(item) for item in self.walers],
                "struts": [asdict(item) for item in self.struts],
                "braces": [asdict(item) for item in self.braces],
                "columns": [asdict(item) for item in self.columns],
                "beams": [asdict(item) for item in self.beams],
                "corner_braces": [asdict(item) for item in self.corner_braces],
            },
            "validation_messages": [asdict(item) for item in self.messages],
            "component_associations": [
                asdict(item) for item in self.component_associations
            ],
            "beam_crossings": [asdict(item) for item in self.beam_crossings],
            "entities": [asdict(item) for item in self.entity_debug],
            "source_geometry": [asdict(item) for item in self.source_geometry],
        }


def apply_coordinate_system(
    result: DXFImportResult,
    coordinate_system: CoordinateSystem,
) -> DXFImportResult:
    """Create transformed engineering models while preserving all world data."""

    def transform_member(
        member: Waler | Strut | Brace | AuxiliaryComponent,
    ) -> Waler | Strut | Brace | AuxiliaryComponent:
        world_start = member.world_start or member.start
        world_end = member.world_end or member.end
        local_start = coordinate_system.transform(world_start)
        local_end = coordinate_system.transform(world_end)
        active_start = local_start if coordinate_system.mode == "local" else world_start
        active_end = local_end if coordinate_system.mode == "local" else world_end
        candidate_points = tuple(
            replace(
                candidate,
                local_point=coordinate_system.transform(candidate.world_point),
            )
            for candidate in member.candidate_points
        )
        world_association_point = getattr(member, "world_association_point", None)
        local_association_point = (
            coordinate_system.transform(world_association_point)
            if world_association_point is not None
            else None
        )
        association_changes = (
            {
                "local_association_point": local_association_point,
                "reference_point": (
                    coordinate_system.transform(member.world_reference_point)
                    if coordinate_system.mode == "local"
                    and member.world_reference_point is not None
                    else member.world_reference_point
                ),
                "local_reference_point": (
                    coordinate_system.transform(member.world_reference_point)
                    if member.world_reference_point is not None
                    else None
                ),
            }
            if isinstance(member, AuxiliaryComponent)
            else {}
        )
        if isinstance(member, Beam):
            world_path = member.world_path or (world_start, world_end)
            local_path = tuple(
                coordinate_system.transform(point) for point in world_path
            )
            association_changes.update(
                world_path=world_path,
                local_path=local_path,
                path=(
                    local_path
                    if coordinate_system.mode == "local"
                    else world_path
                ),
                crossings=tuple(
                    replace(
                        crossing,
                        local_point=coordinate_system.transform(
                            crossing.world_point
                        ),
                    )
                    for crossing in member.crossings
                ),
            )
        return replace(
            member,
            start=active_start,
            end=active_end,
            world_start=world_start,
            world_end=world_end,
            local_start=local_start,
            local_end=local_end,
            candidate_points=candidate_points,
            **association_changes,
        )

    component_associations = tuple(
        replace(
            association,
            local_projection_point=coordinate_system.transform(
                association.world_projection_point
            ),
        )
        for association in result.component_associations
    )
    beam_crossings = tuple(
        replace(
            crossing,
            local_point=coordinate_system.transform(crossing.world_point),
        )
        for crossing in result.beam_crossings
    )

    return replace(
        result,
        walers=tuple(transform_member(member) for member in result.walers),
        struts=tuple(transform_member(member) for member in result.struts),
        braces=tuple(transform_member(member) for member in result.braces),
        columns=tuple(transform_member(member) for member in result.columns),
        beams=tuple(transform_member(member) for member in result.beams),
        corner_braces=tuple(
            transform_member(member) for member in result.corner_braces
        ),
        component_associations=component_associations,
        beam_crossings=beam_crossings,
        coordinate_system=coordinate_system,
    )


def build_problem_records(result: DXFImportResult) -> tuple[ProblemRecord, ...]:
    """Convert validation messages into concise, component-oriented UI rows."""

    members: tuple[Waler | Strut | Brace | AuxiliaryComponent, ...] = (
        *result.walers,
        *result.struts,
        *result.braces,
        *result.columns,
        *result.beams,
        *result.corner_braces,
    )
    records = []
    for message in result.messages:
        handles = set(message.source_handles)
        member_ids = tuple(
            member.id
            for member in members
            if handles.intersection(member.source_handles)
        )
        component = ", ".join(member_ids)
        if not component and message.source_handles:
            component = ", ".join(message.source_handles)
        records.append(
            ProblemRecord(
                message.severity,
                message.code,
                component or "—",
                message.message,
                message.role,
                message.source_handles,
                member_ids,
            )
        )
    severity_order = {"critical": 0, "error": 1, "warning": 2, "info": 3}
    return tuple(
        sorted(records, key=lambda item: (severity_order.get(item.severity, 4), item.code, item.component))
    )


def build_validation_overview(result: DXFImportResult) -> tuple[ValidationOverviewItem, ...]:
    """Build the short checklist an engineer should be able to scan quickly."""

    coordinate = result.coordinate_system
    coordinate_text = (
        f"使用局部座標，原點 ({coordinate.origin_x:g}, {coordinate.origin_y:g})"
        if coordinate.mode == "local"
        else "使用原始 CAD 座標"
    )
    items = [
        ValidationOverviewItem("success", "圖層已讀取"),
        ValidationOverviewItem("success", coordinate_text),
    ]
    role_data = (
        ("strut", "支撐", result.struts),
        ("waler", "圍令", result.walers),
        ("brace", "斜撐", result.braces),
    )
    for role, label, members in role_data:
        engineering_line_code = (
            "WALER_ENGINEERING_LINE_FAILED"
            if role == "waler"
            else f"{role.upper()}_CENTERLINE_FAILED"
        )
        failed = any(
            message.role == role
            and message.severity in ERROR_SEVERITIES
            and message.code
            in {f"{role.upper()}_RECOGNITION_FAILED", engineering_line_code}
            for message in result.messages
        )
        if members and not failed:
            items.append(ValidationOverviewItem("success", f"{label}辨識成功（{len(members)}）"))
        else:
            items.append(ValidationOverviewItem("error", f"{label}辨識失敗或沒有可用構件"))

    for label, members in (
        ("中間柱", result.columns),
        ("托梁", result.beams),
        ("角撐", result.corner_braces),
    ):
        if members:
            items.append(
                ValidationOverviewItem("success", f"{label}辨識成功（{len(members)}）")
            )

    unassociated_columns = sum(not member.associated_strut_id for member in result.columns)
    unassociated_beams = sum(not member.associated_strut_id for member in result.beams)
    if result.columns:
        items.append(
            ValidationOverviewItem(
                "error" if unassociated_columns else "success",
                (
                    f"{unassociated_columns} 根中間柱尚未關聯支撐"
                    if unassociated_columns
                    else "中間柱皆已關聯支撐"
                ),
            )
        )
    if result.beams:
        items.append(
            ValidationOverviewItem(
                "error" if unassociated_beams else "success",
                (
                    f"{unassociated_beams} 根托梁尚未關聯支撐"
                    if unassociated_beams
                    else "托梁皆已關聯支撐"
                ),
            )
        )

    for role, label, members in (("strut", "支撐", result.struts), ("brace", "斜撐", result.braces)):
        incomplete = sum(not (member.from_waler and member.to_waler) for member in members)
        if incomplete:
            items.append(ValidationOverviewItem("error", f"{incomplete} 根{label}未完整連接圍令"))
        elif members:
            items.append(ValidationOverviewItem("success", f"{label}皆已連接圍令"))

    failed_engineering_lines = sum(
        "CENTERLINE_FAILED" in message.code
        or message.code == "WALER_ENGINEERING_LINE_FAILED"
        for message in result.messages
    )
    if failed_engineering_lines:
        items.append(
            ValidationOverviewItem(
                "error", f"{failed_engineering_lines} 個構件工程線建立失敗"
            )
        )
    duplicate_count = sum(message.code == "DUPLICATED_COMPONENT" for message in result.messages)
    if duplicate_count:
        items.append(ValidationOverviewItem("warning", f"{duplicate_count} 組重複幾何已自動合併"))
    manual_count = sum(
        member.selection_source != "auto"
        for member in (
            *result.walers,
            *result.struts,
            *result.braces,
            *result.columns,
            *result.beams,
            *result.corner_braces,
        )
    )
    if manual_count:
        items.append(
            ValidationOverviewItem("info", f"已人工選擇 {manual_count} 個構件工程線")
        )
    if result.can_import:
        items.append(ValidationOverviewItem("success", "工程模型可以匯入 Solver"))
    else:
        items.append(ValidationOverviewItem("error", "存在阻擋錯誤，目前不可匯入 Solver"))
    return tuple(items)


@dataclass
class _Primitive:
    points: list[Point]
    closed: bool
    entity_type: str
    source_handle: str
    source_width: float = 0.0

    def segments(self) -> list[tuple[Point, Point]]:
        pairs = list(zip(self.points, self.points[1:]))
        if self.closed and len(self.points) > 2:
            pairs.append((self.points[-1], self.points[0]))
        return [(a, b) for a, b in pairs if _distance(a, b) > 1e-9]


@dataclass
class _GeometryGroup:
    key: str
    role: str
    layer: str
    primitives: list[_Primitive]
    handles: set[str]
    entity_types: set[str]
    block_instances: list[BlockInstanceInfo]


@dataclass
class _Candidate:
    start: Point
    end: Point
    recognition_method: str
    centerline_computed: bool
    source_width: float
    confidence: float
    layer: str
    handles: set[str]
    entity_types: set[str]
    block_instances: list[BlockInstanceInfo]
    source_keys: set[str]
    warnings: list[str]
    boundary_lines: tuple[tuple[Point, Point], ...] = ()
    recognized_axis: tuple[Point, Point] | None = None
    reference_point: Point | None = None
    path_points: tuple[Point, ...] = ()
    source_points: tuple[Point, ...] = ()


def _point(value: Any) -> Point:
    return float(value[0]), float(value[1])


def _mline_center_path(entity: Any) -> tuple[list[Point], float]:
    """Return the geometric mid-path between the outermost MLINE rails.

    An MLINE vertex is its *reference* path, which can be justified to the top
    or bottom rail.  ``line_params`` already contains ezdxf's resolved style,
    scale, corner stretch and justification offsets, so averaging its extreme
    rail offsets yields the actual member centre without modifying the entity.
    """

    points: list[Point] = []
    widths: list[float] = []
    for vertex in entity.vertices:
        offsets = [
            float(parameters[0])
            for parameters in vertex.line_params
            if parameters and math.isfinite(float(parameters[0]))
        ]
        location = vertex.location
        if len(offsets) >= 2:
            bottom, top = min(offsets), max(offsets)
            center_offset = (bottom + top) / 2.0
            miter = vertex.miter_direction
            center = (
                float(location[0]) + float(miter[0]) * center_offset,
                float(location[1]) + float(miter[1]) * center_offset,
            )
            widths.append(top - bottom)
        else:
            center = _point(location)
        if not points or not _same_point(points[-1], center, 1e-9):
            points.append(center)
    # Corner miters stretch the offset distance; the smallest resolved span is
    # the perpendicular section width rather than that stretched miter length.
    source_width = min(widths) if widths else 0.0
    return points, source_width


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _vector(start: Point, end: Point) -> Point:
    return end[0] - start[0], end[1] - start[1]


def _length(start: Point, end: Point) -> float:
    return math.hypot(*_vector(start, end))


def _unit(start: Point, end: Point) -> Point | None:
    length = _length(start, end)
    if length <= 1e-12:
        return None
    return (end[0] - start[0]) / length, (end[1] - start[1]) / length


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _same_point(a: Point, b: Point, tolerance: float) -> bool:
    return _distance(a, b) <= tolerance


def _midpoint(a: Point, b: Point) -> Point:
    return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2


def _project_onto_segment(point: Point, start: Point, end: Point) -> Point:
    direction = _vector(start, end)
    length_sq = _dot(direction, direction)
    if length_sq <= 1e-20:
        return start
    ratio = _dot(_vector(start, point), direction) / length_sq
    ratio = max(0.0, min(1.0, ratio))
    return start[0] + ratio * direction[0], start[1] + ratio * direction[1]


def _segment_distance(point: Point, start: Point, end: Point) -> float:
    return _distance(point, _project_onto_segment(point, start, end))


def _closest_points_between_segments(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
) -> tuple[Point, Point, float]:
    """Return the closest finite points on two non-intersecting 2D segments."""

    intersection = _segment_intersection_point(first, second)
    if intersection is not None:
        return intersection, intersection, 0.0
    options = (
        (first[0], _project_onto_segment(first[0], *second)),
        (first[1], _project_onto_segment(first[1], *second)),
        (_project_onto_segment(second[0], *first), second[0]),
        (_project_onto_segment(second[1], *first), second[1]),
    )
    first_point, second_point = min(
        options,
        key=lambda pair: _distance(pair[0], pair[1]),
    )
    return first_point, second_point, _distance(first_point, second_point)


def _segments_have_parallel_overlap(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
    angle_tolerance_deg: float,
) -> bool:
    """True when parallel segments overlap longitudinally (no unique crossing)."""

    if _angle_difference_deg(first, second) > angle_tolerance_deg:
        return False
    first_axis = _unit(*first)
    if first_axis is None:
        return False
    first_range = (0.0, _length(*first))
    second_values = sorted(
        _dot(_vector(first[0], point), first_axis) for point in second
    )
    overlap = min(first_range[1], second_values[1]) - max(
        first_range[0], second_values[0]
    )
    return overlap > 1e-6


def _segment_intersection_point(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
    tolerance: float = 1e-6,
) -> Point | None:
    p, q = first[0], second[0]
    r, s = _vector(*first), _vector(*second)
    denominator = _cross(r, s)
    if abs(denominator) <= 1e-12:
        return None
    q_minus_p = _vector(p, q)
    first_ratio = _cross(q_minus_p, s) / denominator
    second_ratio = _cross(q_minus_p, r) / denominator
    first_margin = tolerance / max(_length(*first), 1e-9)
    second_margin = tolerance / max(_length(*second), 1e-9)
    if not (-first_margin <= first_ratio <= 1 + first_margin):
        return None
    if not (-second_margin <= second_ratio <= 1 + second_margin):
        return None
    return p[0] + first_ratio * r[0], p[1] + first_ratio * r[1]


def _line_segment_intersection_point(
    line: tuple[Point, Point],
    segment: tuple[Point, Point],
    tolerance: float = 1e-6,
) -> Point | None:
    """Intersect an unbounded engineering axis with one finite segment."""

    p, q = line[0], segment[0]
    r, s = _vector(*line), _vector(*segment)
    denominator = _cross(r, s)
    if abs(denominator) <= 1e-12:
        return None
    q_minus_p = _vector(p, q)
    line_ratio = _cross(q_minus_p, s) / denominator
    segment_ratio = _cross(q_minus_p, r) / denominator
    margin = tolerance / max(_length(*segment), 1e-9)
    if not (-margin <= segment_ratio <= 1 + margin):
        return None
    return p[0] + line_ratio * r[0], p[1] + line_ratio * r[1]


def _line_distance(point: Point, start: Point, end: Point) -> float:
    """Perpendicular distance to an unbounded line."""

    direction = _vector(start, end)
    length = math.hypot(*direction)
    if length <= 1e-12:
        return _distance(point, start)
    return abs(_cross(direction, _vector(start, point))) / length


def _angle_difference_deg(a: tuple[Point, Point], b: tuple[Point, Point]) -> float:
    unit_a, unit_b = _unit(*a), _unit(*b)
    if unit_a is None or unit_b is None:
        return 180.0
    cosine = max(-1.0, min(1.0, abs(_dot(unit_a, unit_b))))
    return math.degrees(math.acos(cosine))


def _projection_range(segment: tuple[Point, Point], axis: Point) -> tuple[float, float]:
    values = (_dot(segment[0], axis), _dot(segment[1], axis))
    return min(values), max(values)


def _projection_overlap_ratio(
    first: tuple[Point, Point], second: tuple[Point, Point]
) -> float:
    axis = _unit(*first)
    if axis is None:
        return 0.0
    first_range = _projection_range(first, axis)
    second_range = _projection_range(second, axis)
    overlap = max(0.0, min(first_range[1], second_range[1]) - max(first_range[0], second_range[0]))
    denominator = max(min(first_range[1] - first_range[0], second_range[1] - second_range[0]), 1e-12)
    return overlap / denominator


def _line_separation(first: tuple[Point, Point], second: tuple[Point, Point]) -> float:
    return (
        _segment_distance(second[0], *first)
        + _segment_distance(second[1], *first)
        + _segment_distance(first[0], *second)
        + _segment_distance(first[1], *second)
    ) / 4


def _ordered_line(start: Point, end: Point) -> tuple[Point, Point]:
    return (start, end) if start <= end else (end, start)


def _same_line(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
    tolerance: float = 1e-6,
) -> bool:
    return min(
        max(_distance(first[0], second[0]), _distance(first[1], second[1])),
        max(_distance(first[0], second[1]), _distance(first[1], second[0])),
    ) <= tolerance


def _paths_duplicate(
    first: Sequence[Point],
    second: Sequence[Point],
    tolerance: float,
) -> bool:
    """Compare ordered paths without collapsing different bent routes."""

    if len(first) != len(second):
        return False
    direct = all(_same_point(a, b, tolerance) for a, b in zip(first, second))
    reverse = all(
        _same_point(a, b, tolerance)
        for a, b in zip(first, reversed(second))
    )
    return direct or reverse


def _lines_duplicate(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
    tolerances: GeometryTolerances,
) -> bool:
    if _angle_difference_deg(first, second) > tolerances.parallel_angle_tolerance_deg:
        return False
    direct = max(_distance(first[0], second[0]), _distance(first[1], second[1]))
    reverse = max(_distance(first[0], second[1]), _distance(first[1], second[0]))
    if min(direct, reverse) <= tolerances.duplicate_tolerance_mm:
        return True
    return (
        _line_separation(first, second) <= tolerances.duplicate_tolerance_mm
        and _projection_overlap_ratio(first, second) >= 0.95
        and abs(_length(*first) - _length(*second)) <= max(
            tolerances.endpoint_tolerance_mm,
            max(_length(*first), _length(*second)) * 0.05,
        )
    )


def outline_centerline(
    points: Sequence[Point],
    tolerances: GeometryTolerances | None = None,
) -> tuple[Point, Point, float, float] | None:
    """Return arbitrary-angle long-axis centreline, width and confidence."""

    tolerances = tolerances or GeometryTolerances()
    values = list(points)
    if len(values) > 2 and _same_point(values[0], values[-1], 1e-6):
        values.pop()
    if len(values) < 4:
        return None
    edges = [
        (values[index], values[(index + 1) % len(values)])
        for index in range(len(values))
    ]
    # Prefer the midpoints of the two short end caps.  This also handles
    # outlines trimmed against perpendicular walers, where the two caps are
    # not parallel even though the member itself has a clear long axis.
    cap_pairs: list[tuple[float, tuple[Point, Point], tuple[Point, Point]]] = []
    for first_index, first in enumerate(edges):
        first_length = _length(*first)
        if first_length <= 1e-9 or first_length > tolerances.maximum_component_width_mm:
            continue
        for second_index in range(first_index + 1, len(edges)):
            if second_index - first_index in {1, len(edges) - 1}:
                continue
            second = edges[second_index]
            second_length = _length(*second)
            if second_length <= 1e-9 or second_length > tolerances.maximum_component_width_mm:
                continue
            if abs(first_length - second_length) > max(
                tolerances.width_tolerance_mm,
                max(first_length, second_length) * 0.15,
            ):
                continue
            start, end = _midpoint(*first), _midpoint(*second)
            axis_length = _distance(start, end)
            width = (first_length + second_length) / 2
            slenderness = axis_length / max(width, 1e-9)
            if slenderness >= tolerances.minimum_slenderness_ratio:
                cap_pairs.append((slenderness, first, second))
    if cap_pairs:
        slenderness, first_cap, second_cap = max(cap_pairs, key=lambda item: item[0])
        start, end = _midpoint(*first_cap), _midpoint(*second_cap)
        width = (_length(*first_cap) + _length(*second_cap)) / 2
        confidence = min(0.98, 0.88 + min(slenderness / 100, 0.10))
        start, end = _ordered_line(start, end)
        return start, end, width, confidence

    longest = max(edges, key=lambda edge: _length(*edge))
    axis = _unit(*longest)
    if axis is None:
        return None
    normal = -axis[1], axis[0]
    along = [_dot(point, axis) for point in values]
    across = [_dot(point, normal) for point in values]
    component_length = max(along) - min(along)
    width = max(across) - min(across)
    if width <= 1e-9:
        return None
    slenderness = component_length / width
    if slenderness < tolerances.minimum_slenderness_ratio:
        return None
    center_across = (max(across) + min(across)) / 2
    start = (
        axis[0] * min(along) + normal[0] * center_across,
        axis[1] * min(along) + normal[1] * center_across,
    )
    end = (
        axis[0] * max(along) + normal[0] * center_across,
        axis[1] * max(along) + normal[1] * center_across,
    )
    confidence = min(0.97, 0.85 + min(slenderness / 100, 0.12))
    return start, end, width, confidence


def _outline_long_boundary_lines(
    primitive: _Primitive,
    axis_line: tuple[Point, Point],
    tolerances: GeometryTolerances,
) -> tuple[tuple[Point, Point], ...]:
    """Return consolidated long faces for a closed member outline."""

    axis_length = _length(*axis_line)
    axis = _unit(*axis_line)
    if axis_length <= 1e-9 or axis is None:
        return ()
    normal = -axis[1], axis[0]
    across = [(_dot(point, normal), point) for point in primitive.points]
    low_side = min(value for value, _point_value in across)
    high_side = max(value for value, _point_value in across)
    side_tolerance = max(
        tolerances.collinear_tolerance_mm,
        (high_side - low_side) * 0.1,
    )
    consolidated: list[tuple[Point, Point]] = []
    for side in (low_side, high_side):
        side_along = [
            _dot(point, axis)
            for across_value, point in across
            if abs(across_value - side) <= side_tolerance
        ]
        if len(side_along) < 2:
            continue
        start_along, end_along = min(side_along), max(side_along)
        if end_along - start_along < axis_length * 0.5:
            continue
        consolidated.append(
            _ordered_line(
                (
                    axis[0] * start_along + normal[0] * side,
                    axis[1] * start_along + normal[1] * side,
                ),
                (
                    axis[0] * end_along + normal[0] * side,
                    axis[1] * end_along + normal[1] * side,
                ),
            )
        )
    if len(consolidated) == 2:
        return tuple(consolidated)

    # Fallback for an unusual outline whose long faces cannot be consolidated
    # by projection (for example, a heavily segmented imported polyline).
    candidates: list[tuple[Point, Point]] = []
    for segment in primitive.segments():
        if _length(*segment) < axis_length * 0.5:
            continue
        if _angle_difference_deg(axis_line, segment) > tolerances.parallel_angle_tolerance_deg:
            continue
        if (
            _projection_overlap_ratio(axis_line, segment)
            < tolerances.minimum_projection_overlap_ratio
        ):
            continue
        ordered = _ordered_line(*segment)
        if not any(_same_line(ordered, item) for item in candidates):
            candidates.append(ordered)
    candidates.sort(key=lambda item: _length(*item), reverse=True)
    return tuple(candidates)


def rectangle_centerline(
    points: Sequence[Point], tolerance: float = 1e-6
) -> tuple[Point, Point] | None:
    """Compatibility helper for callers that only need the centreline."""

    settings = GeometryTolerances(
        endpoint_tolerance_mm=max(tolerance, 1e-9),
        minimum_component_length_mm=0.0,
    )
    result = outline_centerline(points, settings)
    return None if result is None else (result[0], result[1])


def _column_section_candidate_from_group(
    group: _GeometryGroup,
    tolerances: GeometryTolerances,
) -> tuple[_Candidate | None, list[ValidationMessage]]:
    """Recognize a plan-view column section without treating it as a member axis.

    Column geometry is a horizontal section through a vertical member.  Its
    centroid is therefore the engineering reference used for Strut association;
    the principal line retained on the candidate is compatibility/diagnostic
    geometry only.
    """

    segments = [
        segment
        for primitive in group.primitives
        for segment in primitive.segments()
        if _length(*segment) > 1e-9
    ]
    if not segments:
        return None, []

    # A single LINE remains a supported legacy column representation.  Its
    # midpoint is the section reference point.
    if len(segments) == 1:
        start, end = _ordered_line(*segments[0])
        return (
            _Candidate(
                start,
                end,
                "existing_centerline",
                False,
                0.0,
                0.95,
                group.layer,
                set(group.handles),
                set(group.entity_types),
                list(group.block_instances),
                {group.key},
                [],
                ((start, end),),
                reference_point=_midpoint(start, end),
            ),
            [],
        )

    # Prefer the area centroid of closed section outlines.  Fall back to a
    # length-weighted boundary centroid for exploded/open LINE geometry.
    polygon_centroids: list[tuple[float, Point]] = []
    for primitive in group.primitives:
        if not primitive.closed or len(primitive.points) < 3:
            continue
        twice_area = 0.0
        centroid_x_numerator = 0.0
        centroid_y_numerator = 0.0
        polygon_segments = list(
            zip(
                primitive.points,
                (*primitive.points[1:], primitive.points[0]),
            )
        )
        for first, second in polygon_segments:
            cross = first[0] * second[1] - second[0] * first[1]
            twice_area += cross
            centroid_x_numerator += (first[0] + second[0]) * cross
            centroid_y_numerator += (first[1] + second[1]) * cross
        if abs(twice_area) <= 1e-9:
            continue
        polygon_centroids.append(
            (
                abs(twice_area) / 2,
                (
                    centroid_x_numerator / (3 * twice_area),
                    centroid_y_numerator / (3 * twice_area),
                ),
            )
        )

    # Treat every boundary segment as a uniform line element.  Its moments are
    # insensitive to how densely a polyline was segmented, unlike averaging
    # the raw vertices.
    total_length = sum(_length(*segment) for segment in segments)
    if total_length <= 1e-9:
        return None, []
    if polygon_centroids:
        total_area = sum(area for area, _centroid in polygon_centroids)
        center_x = sum(
            area * centroid[0] for area, centroid in polygon_centroids
        ) / total_area
        center_y = sum(
            area * centroid[1] for area, centroid in polygon_centroids
        ) / total_area
    else:
        center_x = sum(
            _length(*segment) * (segment[0][0] + segment[1][0]) / 2
            for segment in segments
        ) / total_length
        center_y = sum(
            _length(*segment) * (segment[0][1] + segment[1][1]) / 2
            for segment in segments
        ) / total_length
    center = (center_x, center_y)

    raw_xx = sum(
        _length(*segment)
        * (
            segment[0][0] ** 2
            + segment[0][0] * segment[1][0]
            + segment[1][0] ** 2
        )
        / 3
        for segment in segments
    ) / total_length
    raw_yy = sum(
        _length(*segment)
        * (
            segment[0][1] ** 2
            + segment[0][1] * segment[1][1]
            + segment[1][1] ** 2
        )
        / 3
        for segment in segments
    ) / total_length
    raw_xy = sum(
        _length(*segment)
        * (
            2 * segment[0][0] * segment[0][1]
            + segment[0][0] * segment[1][1]
            + segment[1][0] * segment[0][1]
            + 2 * segment[1][0] * segment[1][1]
        )
        / 6
        for segment in segments
    ) / total_length
    covariance_xx = max(0.0, raw_xx - center_x * center_x)
    covariance_yy = max(0.0, raw_yy - center_y * center_y)
    covariance_xy = raw_xy - center_x * center_y

    angle = 0.5 * math.atan2(
        2 * covariance_xy,
        covariance_xx - covariance_yy,
    )
    axis = (math.cos(angle), math.sin(angle))
    points = [point for segment in segments for point in segment]
    along = [_dot(_vector(center, point), axis) for point in points]
    normal = (-axis[1], axis[0])
    across = [_dot(_vector(center, point), normal) for point in points]
    start = (center_x + axis[0] * min(along), center_y + axis[1] * min(along))
    end = (center_x + axis[0] * max(along), center_y + axis[1] * max(along))
    start, end = _ordered_line(start, end)
    width = max(across) - min(across)
    trace = covariance_xx + covariance_yy
    discriminant = math.hypot(
        covariance_xx - covariance_yy,
        2 * covariance_xy,
    )
    confidence = 0.90 if trace <= 1e-12 else min(0.98, 0.85 + 0.13 * discriminant / trace)
    return (
        _Candidate(
            start,
            end,
            "column_section_centroid",
            True,
            width,
            confidence,
            group.layer,
            set(group.handles),
            set(group.entity_types),
            list(group.block_instances),
            {group.key},
            [],
            tuple(_ordered_line(*segment) for segment in segments),
            recognized_axis=(start, end),
            reference_point=center,
        ),
        [],
    )


def _corner_brace_candidates_from_group(
    group: _GeometryGroup,
    tolerances: GeometryTolerances,
) -> tuple[list[_Candidate], list[ValidationMessage]]:
    """Recognize each corner brace using its rails and connection plates.

    A fabrication block may contain a left and a right corner brace.  Each
    brace is defined by two parallel long edges and one transverse connection
    plate at each end; therefore one INSERT can intentionally create two
    engineering members.  Plate midpoints are only the preliminary recognition
    axis.  The later refinement step uses the rail midline intersections as the
    engineering endpoints.
    """

    segments = [
        segment
        for primitive in group.primitives
        for segment in primitive.segments()
        if _length(*segment) > 1e-9
    ]
    options: list[
        tuple[
            float,
            int,
            int,
            int,
            int,
            tuple[Point, Point],
            tuple[Point, Point],
            tuple[Point, Point],
            tuple[Point, Point],
        ]
    ] = []

    def connecting_plate(
        first_point: Point,
        second_point: Point,
        excluded: set[int],
    ) -> tuple[int, tuple[Point, Point], float] | None:
        matches: list[tuple[float, int, tuple[Point, Point]]] = []
        for index, segment in enumerate(segments):
            if index in excluded:
                continue
            direct = max(
                _distance(segment[0], first_point),
                _distance(segment[1], second_point),
            )
            reverse = max(
                _distance(segment[1], first_point),
                _distance(segment[0], second_point),
            )
            error = min(direct, reverse)
            if error <= tolerances.endpoint_tolerance_mm:
                matches.append((error, index, segment))
        if not matches:
            return None
        error, index, segment = min(matches, key=lambda item: (item[0], item[1]))
        return index, segment, error

    for first_index, first in enumerate(segments):
        first_length = _length(*first)
        if first_length < tolerances.minimum_component_length_mm:
            continue
        for second_index in range(first_index + 1, len(segments)):
            second = segments[second_index]
            second_length = _length(*second)
            if second_length < tolerances.minimum_component_length_mm:
                continue
            if (
                _angle_difference_deg(first, second)
                > tolerances.parallel_angle_tolerance_deg
            ):
                continue
            if (
                _projection_overlap_ratio(first, second)
                < tolerances.minimum_projection_overlap_ratio
            ):
                continue
            separation = _line_separation(first, second)
            if not (
                tolerances.collinear_tolerance_mm
                < separation
                <= tolerances.maximum_component_width_mm
            ):
                continue
            if (
                min(first_length, second_length)
                / max(separation, 1e-9)
                < tolerances.minimum_slenderness_ratio
            ):
                continue
            if abs(first_length - second_length) > max(
                tolerances.width_tolerance_mm,
                max(first_length, second_length) * 0.05,
            ):
                continue

            direct_error = _distance(first[0], second[0]) + _distance(
                first[1], second[1]
            )
            reverse_error = _distance(first[0], second[1]) + _distance(
                first[1], second[0]
            )
            second_start, second_end = (
                second if direct_error <= reverse_error else (second[1], second[0])
            )
            excluded = {first_index, second_index}
            start_plate = connecting_plate(first[0], second_start, excluded)
            end_plate = connecting_plate(first[1], second_end, excluded)
            if start_plate is None or end_plate is None:
                continue
            if start_plate[0] == end_plate[0]:
                continue
            start_midpoint = _midpoint(*start_plate[1])
            end_midpoint = _midpoint(*end_plate[1])
            if (
                _length(start_midpoint, end_midpoint)
                < tolerances.minimum_component_length_mm
            ):
                continue
            score = (
                first_length
                + second_length
                - start_plate[2]
                - end_plate[2]
            )
            options.append(
                (
                    score,
                    first_index,
                    second_index,
                    start_plate[0],
                    end_plate[0],
                    first,
                    second,
                    start_plate[1],
                    end_plate[1],
                )
            )

    selected: list[_Candidate] = []
    used_rails: set[int] = set()
    used_plates: set[int] = set()
    for (
        _score,
        first_index,
        second_index,
        start_plate_index,
        end_plate_index,
        first,
        second,
        start_plate,
        end_plate,
    ) in sorted(options, key=lambda item: item[0], reverse=True):
        if {first_index, second_index}.intersection(used_rails):
            continue
        if {start_plate_index, end_plate_index}.intersection(used_plates):
            continue
        start, end = _ordered_line(
            _midpoint(*start_plate),
            _midpoint(*end_plate),
        )
        used_rails.update((first_index, second_index))
        used_plates.update((start_plate_index, end_plate_index))
        selected.append(
            _Candidate(
                start,
                end,
                "connection_plate_midpoints",
                True,
                (
                    _length(*start_plate) + _length(*end_plate)
                )
                / 2.0,
                0.99,
                group.layer,
                set(group.handles),
                set(group.entity_types),
                list(group.block_instances),
                {
                    f"{group.key}:corner_brace:{first_index}:{second_index}"
                },
                [],
                (
                    _ordered_line(*first),
                    _ordered_line(*second),
                    _ordered_line(*start_plate),
                    _ordered_line(*end_plate),
                ),
                recognized_axis=(start, end),
                reference_point=_midpoint(start, end),
                source_points=tuple(
                    dict.fromkeys(
                        point
                        for primitive in group.primitives
                        for point in primitive.points
                    )
                ),
            )
        )
    return selected, []


def _candidate_from_group(
    group: _GeometryGroup,
    role: str,
    tolerances: GeometryTolerances,
) -> tuple[_Candidate | None, list[ValidationMessage]]:
    if role == "column":
        return _column_section_candidate_from_group(group, tolerances)

    if role == "beam":
        mline_primitives = [
            primitive
            for primitive in group.primitives
            if primitive.entity_type == "MLINE" and len(primitive.points) >= 2
        ]
        if mline_primitives:
            # The extractor has already converted MLINE justification into
            # the true section mid-path. Keeping its vertex order is essential:
            # a first-to-last chord loses bends and therefore Strut crossings.
            mline_primitive = max(
                mline_primitives,
                key=lambda primitive: sum(
                    _length(start, end)
                    for start, end in zip(
                        primitive.points,
                        primitive.points[1:],
                    )
                ),
            )
            raw_path = mline_primitive.points
            path: list[Point] = []
            for point in raw_path:
                if not path or not _same_point(point, path[-1], 1e-6):
                    path.append(point)
            path_length = sum(
                _length(start, end)
                for start, end in zip(path, path[1:])
            )
            if len(path) >= 2 and path_length > 1e-9:
                return (
                    _Candidate(
                        path[0],
                        path[-1],
                        "mline_center_path",
                        True,
                        mline_primitive.source_width,
                        0.99,
                        group.layer,
                        set(group.handles),
                        set(group.entity_types),
                        list(group.block_instances),
                        {group.key},
                        [],
                        tuple(zip(path, path[1:])),
                        recognized_axis=(path[0], path[-1]),
                        reference_point=path[len(path) // 2],
                        path_points=tuple(path),
                    ),
                    [],
                )

    messages: list[ValidationMessage] = []
    ambiguous_line_code = (
        "AMBIGUOUS_INNER_LINE" if role == "waler" else "AMBIGUOUS_CENTERLINE"
    )
    outline_candidates: list[
        tuple[Point, Point, float, float, tuple[tuple[Point, Point], ...]]
    ] = []
    for primitive in group.primitives:
        if primitive.closed:
            candidate = outline_centerline(primitive.points, tolerances)
            if candidate is not None:
                axis_line = candidate[0], candidate[1]
                outline_candidates.append(
                    (*candidate, _outline_long_boundary_lines(primitive, axis_line, tolerances))
                )

    segments = [segment for primitive in group.primitives for segment in primitive.segments()]
    explicit_centerline_segments = [
        segment
        for primitive in group.primitives
        if not primitive.closed and len(primitive.points) == 2
        for segment in primitive.segments()
    ]
    outline_candidates.sort(
        key=lambda item: (_length(item[0], item[1]), item[3]),
        reverse=True,
    )
    outline = outline_candidates[0] if outline_candidates else None
    if len(outline_candidates) > 1:
        best_outline = outline_candidates[0]
        runner_up = outline_candidates[1]
        score_delta = abs(best_outline[3] - runner_up[3])
        different = not _lines_duplicate(
            (best_outline[0], best_outline[1]),
            (runner_up[0], runner_up[1]),
            tolerances,
        )
        if different and score_delta <= tolerances.ambiguous_candidate_score_delta:
            messages.append(
                ValidationMessage(
                    "error",
                    ambiguous_line_code,
                    (
                        "同一圍令幾何群組有兩組位置不同的內側線候選。"
                        if role == "waler"
                        else "同一幾何群組有兩個分數相近但位置不同的外框中心線候選。"
                    ),
                    role,
                    tuple(sorted(group.handles)),
                )
            )
    matching_centerlines: list[tuple[Point, Point]] = []
    if outline is not None:
        outline_line = outline[0], outline[1]
        for segment in explicit_centerline_segments:
            if _angle_difference_deg(outline_line, segment) > tolerances.parallel_angle_tolerance_deg:
                continue
            if _projection_overlap_ratio(outline_line, segment) < tolerances.minimum_projection_overlap_ratio:
                continue
            if _line_separation(outline_line, segment) <= outline[2] / 2 + tolerances.collinear_tolerance_mm:
                matching_centerlines.append(segment)

    if matching_centerlines and role != "waler":
        chosen = max(matching_centerlines, key=lambda line: _length(*line))
        candidate = _Candidate(
            *_ordered_line(*chosen),
            "existing_centerline",
            False,
            outline[2] if outline is not None else 0.0,
            0.99,
            group.layer,
            set(group.handles),
            set(group.entity_types),
            list(group.block_instances),
            {group.key},
            [],
            outline[4] if outline is not None else (),
        )
        distinct = [line for line in matching_centerlines if not _lines_duplicate(chosen, line, tolerances)]
        if distinct:
            messages.append(
                ValidationMessage(
                    "error",
                    ambiguous_line_code,
                    "同一來源找到多條差異明顯的既有中心線。",
                    role,
                    tuple(sorted(group.handles)),
                )
            )
        return candidate, messages

    if outline is not None:
        start, end, width, confidence = outline[:4]
        return (
            _Candidate(
                *_ordered_line(start, end),
                "closed_outline_axis",
                True,
                width,
                confidence,
                group.layer,
                set(group.handles),
                set(group.entity_types),
                list(group.block_instances),
                {group.key},
                [],
                outline[4],
            ),
            messages,
        )

    pair_candidates: list[tuple[float, tuple[Point, Point], tuple[Point, Point]]] = []
    for index, first in enumerate(segments):
        for second in segments[index + 1 :]:
            if _angle_difference_deg(first, second) > tolerances.parallel_angle_tolerance_deg:
                continue
            if _projection_overlap_ratio(first, second) < tolerances.minimum_projection_overlap_ratio:
                continue
            separation = _line_separation(first, second)
            if separation <= tolerances.collinear_tolerance_mm:
                continue
            if separation > tolerances.maximum_component_width_mm:
                continue
            length_delta = abs(_length(*first) - _length(*second))
            if length_delta > max(tolerances.width_tolerance_mm, max(_length(*first), _length(*second)) * 0.05):
                continue
            pair_candidates.append((_length(*first) + _length(*second), first, second))

    if pair_candidates:
        pair_candidates.sort(key=lambda item: item[0], reverse=True)
        _score, first, second = pair_candidates[0]

        def pair_midline(
            first_edge: tuple[Point, Point],
            second_edge: tuple[Point, Point],
        ) -> tuple[Point, Point]:
            axis = _unit(*first_edge)
            assert axis is not None
            second_start, second_end = second_edge
            if _dot(_vector(*second_edge), axis) < 0:
                second_start, second_end = second_end, second_start
            return _ordered_line(
                _midpoint(first_edge[0], second_start),
                _midpoint(first_edge[1], second_end),
            )

        chosen_midline = pair_midline(first, second)
        if len(pair_candidates) > 1:
            runner_score, runner_first, runner_second = pair_candidates[1]
            score_delta = abs(_score - runner_score) / max(_score, 1e-9)
            runner_midline = pair_midline(runner_first, runner_second)
            if (
                score_delta <= tolerances.ambiguous_candidate_score_delta
                and not _lines_duplicate(chosen_midline, runner_midline, tolerances)
            ):
                messages.append(
                    ValidationMessage(
                        "error",
                        ambiguous_line_code,
                        (
                            "平行邊群組有兩組位置不同的圍令內側線候選。"
                            if role == "waler"
                            else "平行邊群組有兩個分數相近但位置不同的中心線候選。"
                        ),
                        role,
                        tuple(sorted(group.handles)),
                    )
                )
        first_axis = _unit(*first)
        assert first_axis is not None
        second_start, second_end = second
        if _dot(_vector(*second), first_axis) < 0:
            second_start, second_end = second_end, second_start
        start, end = _midpoint(first[0], second_start), _midpoint(first[1], second_end)
        separation = _line_separation(first, second)
        return (
            _Candidate(
                *_ordered_line(start, end),
                "parallel_edges_midline",
                True,
                separation,
                0.90,
                group.layer,
                set(group.handles),
                set(group.entity_types),
                list(group.block_instances),
                {group.key},
                [],
                (_ordered_line(*first), _ordered_line(*second)),
            ),
            messages,
        )

    linear_segments = [segment for segment in segments if _length(*segment) > 1e-9]
    if len(linear_segments) == 1:
        start, end = _ordered_line(*linear_segments[0])
        return (
            _Candidate(
                start,
                end,
                "existing_centerline",
                False,
                0.0,
                0.95,
                group.layer,
                set(group.handles),
                set(group.entity_types),
                list(group.block_instances),
                {group.key},
                [],
                ((start, end),),
            ),
            messages,
        )
    return None, messages


def _deduplicate_candidates(
    candidates: Sequence[_Candidate],
    role: str,
    tolerances: GeometryTolerances,
) -> tuple[list[_Candidate], list[ValidationMessage]]:
    priority = (
        {
            "closed_outline_axis": 3,
            "parallel_edges_midline": 2,
            "existing_centerline": 1,
        }
        if role == "waler"
        else {
            "mline_center_path": 4,
            "connection_plate_midpoints": 4,
            "existing_centerline": 3,
            "closed_outline_axis": 2,
            "parallel_edges_midline": 1,
        }
    )
    kept: list[_Candidate] = []
    messages: list[ValidationMessage] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (priority.get(item.recognition_method, 0), item.confidence),
        reverse=True,
    ):
        duplicate = next(
            (
                item
                for item in kept
                if _lines_duplicate(
                    (item.start, item.end),
                    (candidate.start, candidate.end),
                    tolerances,
                )
                and (
                    role != "beam"
                    or _paths_duplicate(
                        item.path_points or (item.start, item.end),
                        candidate.path_points
                        or (candidate.start, candidate.end),
                        tolerances.duplicate_tolerance_mm,
                    )
                )
            ),
            None,
        )
        if duplicate is None:
            kept.append(candidate)
            continue
        duplicate.handles.update(candidate.handles)
        duplicate.entity_types.update(candidate.entity_types)
        duplicate.source_keys.update(candidate.source_keys)
        for instance in candidate.block_instances:
            if instance not in duplicate.block_instances:
                duplicate.block_instances.append(instance)
        duplicate.source_width = max(duplicate.source_width, candidate.source_width)
        merged_boundaries = list(duplicate.boundary_lines)
        for boundary in candidate.boundary_lines:
            if not any(_same_line(boundary, item) for item in merged_boundaries):
                merged_boundaries.append(boundary)
        duplicate.boundary_lines = tuple(merged_boundaries)
        duplicate.warnings.append("DUPLICATED_COMPONENT")
        messages.append(
            ValidationMessage(
                "warning",
                "DUPLICATED_COMPONENT",
                "重疊的外框與中心線已合併為單一工程構件。",
                role,
                tuple(sorted(candidate.handles | duplicate.handles)),
            )
        )
    return kept, messages


def _select_waler_inner_lines(
    candidates_by_role: Mapping[str, Sequence[_Candidate]],
) -> None:
    """Replace Waler recognition axes with the face toward the bracing system."""

    framing_points = [
        point
        for role in ("strut", "brace")
        for candidate in candidates_by_role.get(role, ())
        for point in (candidate.start, candidate.end)
    ]
    if not framing_points:
        framing_points = [
            _midpoint(candidate.start, candidate.end)
            for candidate in candidates_by_role.get("waler", ())
        ]
    if not framing_points:
        return
    interior_reference = (
        sum(point[0] for point in framing_points) / len(framing_points),
        sum(point[1] for point in framing_points) / len(framing_points),
    )
    for candidate in candidates_by_role.get("waler", ()):
        candidate.recognized_axis = _ordered_line(candidate.start, candidate.end)
        if candidate.boundary_lines:
            contact_count = min(4, len(framing_points))

            def inner_line_score(line: tuple[Point, Point]) -> tuple[float, float]:
                contact_distances = sorted(
                    _segment_distance(point, *line) for point in framing_points
                )
                return (
                    sum(contact_distances[:contact_count]),
                    _line_distance(interior_reference, *line),
                )

            inner_line = min(
                candidate.boundary_lines,
                # Actual Strut/Brace endpoints are the strongest evidence for
                # the contact face.  The framing centroid resolves ties (for
                # example, an ideal test line drawn midway through a Waler).
                key=inner_line_score,
            )
            candidate.start, candidate.end = _ordered_line(*inner_line)
            candidate.recognition_method = (
                "existing_inner_line"
                if len(candidate.boundary_lines) == 1
                else "inner_boundary_line"
            )
        else:
            # A standalone LINE on the Waler layer is already the engineering
            # contact line; no centreline reconstruction is required.
            candidate.recognition_method = "existing_inner_line"
        candidate.centerline_computed = False


def _corner_brace_center_axis(
    candidate: _Candidate,
    tolerances: GeometryTolerances,
) -> tuple[Point, Point] | None:
    """Return the midline of the two original brace longitudinal edges."""

    preliminary_axis = (candidate.start, candidate.end)
    rail_options: list[
        tuple[float, tuple[Point, Point], tuple[Point, Point]]
    ] = []
    for first_index, first in enumerate(candidate.boundary_lines):
        if _length(*first) < tolerances.minimum_component_length_mm:
            continue
        if (
            _angle_difference_deg(first, preliminary_axis)
            > tolerances.parallel_angle_tolerance_deg
        ):
            continue
        for second in candidate.boundary_lines[first_index + 1 :]:
            if _length(*second) < tolerances.minimum_component_length_mm:
                continue
            if (
                _angle_difference_deg(first, second)
                > tolerances.parallel_angle_tolerance_deg
            ):
                continue
            if (
                _projection_overlap_ratio(first, second)
                < tolerances.minimum_projection_overlap_ratio
            ):
                continue
            separation = _line_separation(first, second)
            if not (
                tolerances.collinear_tolerance_mm
                < separation
                <= tolerances.maximum_component_width_mm
            ):
                continue
            rail_options.append(
                (_length(*first) + _length(*second), first, second)
            )
    if not rail_options:
        return None

    _score, first, second = max(rail_options, key=lambda item: item[0])
    direct_error = _distance(first[0], second[0]) + _distance(
        first[1], second[1]
    )
    reverse_error = _distance(first[0], second[1]) + _distance(
        first[1], second[0]
    )
    second_start, second_end = (
        second if direct_error <= reverse_error else (second[1], second[0])
    )
    center_axis = _ordered_line(
        _midpoint(first[0], second_start),
        _midpoint(first[1], second_end),
    )
    if _length(*center_axis) < tolerances.minimum_component_length_mm:
        return None
    return center_axis


def _refine_corner_brace_axis_intersections(
    candidates_by_role: Mapping[str, Sequence[_Candidate]],
    tolerances: GeometryTolerances,
) -> list[ValidationMessage]:
    """Move corner-brace endpoints to its original axis/member intersections.

    The fabrication connection plates are useful evidence for recognizing one
    brace inside a compound INSERT, but their midpoints are not the engineering
    station.  The station comes from the midline between the two original brace
    longitudinal edges, extended to the Waler inner line and Strut centreline.
    """

    walers = tuple(candidates_by_role.get("waler", ()))
    struts = tuple(candidates_by_role.get("strut", ()))
    messages: list[ValidationMessage] = []
    if not walers or not struts:
        return messages

    def nearest_axis(
        point: Point,
        members: Sequence[_Candidate],
    ) -> _Candidate:
        return min(
            members,
            key=lambda member: _segment_distance(
                point,
                member.start,
                member.end,
            ),
        )

    def signed_distance(
        line: tuple[Point, Point],
        point: Point,
    ) -> float:
        direction = _vector(*line)
        length = math.hypot(*direction)
        if length <= 1e-12:
            return 0.0
        return _cross(direction, _vector(line[0], point)) / length

    def contact_midpoint(
        source_points: Sequence[Point],
        contact_axis: tuple[Point, Point],
        strut_axis: tuple[Point, Point],
        preliminary: Point,
    ) -> Point | None:
        side = signed_distance(strut_axis, preliminary)
        search_radius = max(
            tolerances.maximum_component_width_mm * 2.0,
            tolerances.connection_tolerance_mm * 3.0,
        )
        projected_options: list[tuple[float, float, Point]] = []
        axis_unit = _unit(*contact_axis)
        if axis_unit is None:
            return None
        for point in source_points:
            if _distance(point, preliminary) > search_radius:
                continue
            perpendicular = _segment_distance(point, *contact_axis)
            if perpendicular > tolerances.connection_tolerance_mm:
                continue
            point_side = signed_distance(strut_axis, point)
            if (
                abs(side) > tolerances.collinear_tolerance_mm
                and point_side * side < 0.0
            ):
                continue
            projection = _project_onto_segment(point, *contact_axis)
            station = _dot(
                _vector(contact_axis[0], projection),
                axis_unit,
            )
            projected_options.append((perpendicular, station, projection))
        if not projected_options:
            return None
        closest_distance = min(item[0] for item in projected_options)
        projected: list[tuple[float, Point]] = []
        for perpendicular, station, projection in projected_options:
            if (
                perpendicular
                > closest_distance + tolerances.endpoint_tolerance_mm
            ):
                continue
            if not any(
                abs(station - existing_station)
                <= tolerances.beam_crossing_duplicate_tolerance_mm
                for existing_station, _existing_point in projected
            ):
                projected.append((station, projection))
        if len(projected) < 2:
            return None
        projected.sort(key=lambda item: item[0])
        return _midpoint(projected[0][1], projected[-1][1])

    for candidate in candidates_by_role.get("corner_brace", ()):
        if candidate.recognition_method != "connection_plate_midpoints":
            continue
        start, end = candidate.start, candidate.end
        direct_waler = nearest_axis(start, walers)
        direct_strut = nearest_axis(end, struts)
        reverse_waler = nearest_axis(end, walers)
        reverse_strut = nearest_axis(start, struts)
        direct_score = _segment_distance(
            start,
            direct_waler.start,
            direct_waler.end,
        ) + _segment_distance(
            end,
            direct_strut.start,
            direct_strut.end,
        )
        reverse_score = _segment_distance(
            end,
            reverse_waler.start,
            reverse_waler.end,
        ) + _segment_distance(
            start,
            reverse_strut.start,
            reverse_strut.end,
        )
        if direct_score <= reverse_score:
            preliminary_waler, preliminary_strut = start, end
            waler, strut = direct_waler, direct_strut
        else:
            preliminary_waler, preliminary_strut = end, start
            waler, strut = reverse_waler, reverse_strut
        strut_axis = (strut.start, strut.end)
        brace_axis = _corner_brace_center_axis(candidate, tolerances)
        waler_contact = None
        strut_contact = None
        if brace_axis is not None:
            waler_contact = _line_segment_intersection_point(
                brace_axis,
                (waler.start, waler.end),
                tolerances.endpoint_tolerance_mm,
            )
            strut_contact = _line_segment_intersection_point(
                brace_axis,
                strut_axis,
                tolerances.endpoint_tolerance_mm,
            )
        if waler_contact is None or strut_contact is None:
            # Some legacy/simple blocks do not preserve two longitudinal
            # edges.  Retain the previous connection-face method as a safe
            # recognition fallback instead of discarding the component.
            waler_contact = contact_midpoint(
                candidate.source_points,
                (waler.start, waler.end),
                strut_axis,
                preliminary_waler,
            )
            strut_contact = contact_midpoint(
                candidate.source_points,
                strut_axis,
                strut_axis,
                preliminary_strut,
            )
            recognition_method = "connection_face_midpoints"
        else:
            recognition_method = "brace_centerline_intersections"
        if waler_contact is None or strut_contact is None:
            messages.append(
                ValidationMessage(
                    "error",
                    "CORNER_BRACE_CONNECTION_POINT_FAILED",
                    "角撐連接板無法建立圍令端與支撐端接觸中點。",
                    "corner_brace",
                    tuple(sorted(candidate.handles)),
                )
            )
            continue
        # Keep the adopted endpoints exactly on the Waler inner line and Strut
        # centreline despite harmless floating-point intersection residue.
        waler_contact = _project_onto_segment(
            waler_contact,
            waler.start,
            waler.end,
        )
        strut_contact = _project_onto_segment(
            strut_contact,
            strut.start,
            strut.end,
        )
        candidate.start, candidate.end = _ordered_line(
            waler_contact,
            strut_contact,
        )
        candidate.recognized_axis = (candidate.start, candidate.end)
        candidate.reference_point = _midpoint(candidate.start, candidate.end)
        candidate.recognition_method = recognition_method
    return messages


def _engineering_line_candidates(
    role: str,
    candidate: _Candidate,
) -> tuple[EngineeringLineCandidate, ...]:
    """Build deterministic, serializable choices from recognition evidence."""

    current_line = _ordered_line(candidate.start, candidate.end)
    lines: list[tuple[tuple[Point, Point], str, str]] = [
        (
            current_line,
            "內側線（自動辨識）" if role == "waler" else "",
            candidate.recognition_method,
        )
    ]
    for boundary in candidate.boundary_lines:
        ordered = _ordered_line(*boundary)
        if not any(_same_line(ordered, existing[0]) for existing in lines):
            lines.append(
                (
                    ordered,
                    "外側線" if role == "waler" else "",
                    "recognized_boundary",
                )
            )
    if role == "waler" and candidate.recognized_axis is not None:
        axis = _ordered_line(*candidate.recognized_axis)
        if not any(_same_line(axis, existing[0]) for existing in lines):
            lines.append((axis, "中心線", "recognized_axis"))

    options = []
    for index, (line, preset_label, source) in enumerate(lines, 1):
        start, end = line
        if preset_label:
            label = preset_label
        elif index == 1 and candidate.centerline_computed:
            label = "中心線（自動辨識）"
        elif index == 1:
            label = "來源工程線（自動辨識）"
        else:
            label = f"邊界線 {index - 1}"
        options.append(
            EngineeringLineCandidate(
                f"line_{index}",
                label,
                start,
                end,
                source,
            )
        )
    return tuple(options)


class CandidatePointStore:
    """Canonical candidate-point repository.

    The builder-facing ``add()/points()`` API keeps the original per-component
    deduplication behaviour.  The component index is the UI-facing API: widgets
    retain only IDs and always resolve the immutable point through this store.
    """

    def __init__(self, tolerance: float) -> None:
        self.tolerance = max(float(tolerance), 1e-9)
        self._points: list[CandidatePoint] = []
        self._component_points: dict[str, tuple[CandidatePoint, ...]] = {}
        self._component_point_index: dict[
            tuple[str, str], CandidatePoint
        ] = {}

    def add(
        self,
        world_point: Point,
        *,
        point_type: str,
        label: str,
        source_handles: Sequence[str] = (),
        source_entity_types: Sequence[str] = (),
        recommended_for: Sequence[str] = (),
        score: float = 0.0,
        valid_for: Sequence[str] = ("start", "end"),
        preferred_id: str = "",
    ) -> str:
        point = float(world_point[0]), float(world_point[1])
        if not all(math.isfinite(value) for value in point):
            return ""
        for index, existing in enumerate(self._points):
            if not _same_point(existing.world_point, point, self.tolerance):
                continue
            use_new_description = score > existing.score
            merged = replace(
                existing,
                point_type=point_type if use_new_description else existing.point_type,
                label=label if use_new_description else existing.label,
                source_handles=tuple(
                    sorted({*existing.source_handles, *map(str, source_handles)})
                ),
                source_entity_types=tuple(
                    sorted(
                        {
                            *existing.source_entity_types,
                            *map(str, source_entity_types),
                        }
                    )
                ),
                recommended_for=tuple(
                    item
                    for item in ("start", "end")
                    if item in {*existing.recommended_for, *recommended_for}
                ),
                score=max(existing.score, float(score)),
                point_types=tuple(
                    dict.fromkeys(
                        (
                            *existing.point_types,
                            existing.point_type,
                            point_type,
                        )
                    )
                ),
                valid_for=tuple(
                    item
                    for item in ("start", "end")
                    if item in {*existing.valid_for, *valid_for}
                ),
            )
            self._points[index] = merged
            return merged.id
        identifier = preferred_id or f"P{len(self._points) + 1:02d}"
        used_ids = {item.id for item in self._points}
        if identifier in used_ids:
            identifier = f"P{len(self._points) + 1:02d}"
        candidate = CandidatePoint(
            id=identifier,
            world_point=point,
            local_point=point,
            point_type=point_type,
            label=label,
            source_handles=tuple(sorted(set(map(str, source_handles)))),
            source_entity_types=tuple(
                sorted(set(map(str, source_entity_types)))
            ),
            recommended_for=tuple(
                item for item in ("start", "end") if item in set(recommended_for)
            ),
            score=max(0.0, min(1.0, float(score))),
            point_types=(point_type,),
            valid_for=tuple(
                item for item in ("start", "end") if item in set(valid_for)
            ),
        )
        self._points.append(candidate)
        return identifier

    def points(self) -> tuple[CandidatePoint, ...]:
        return tuple(self._points)

    def rebuild(
        self,
        members: Iterable[Waler | Strut | Brace | AuxiliaryComponent],
    ) -> None:
        """Replace the UI index after recognition or coordinate conversion."""

        self._component_points.clear()
        self._component_point_index.clear()
        for member in members:
            self.register_component(member.id, member.candidate_points)

    def register_component(
        self,
        component_id: str,
        points: Sequence[CandidatePoint],
    ) -> None:
        identifier = str(component_id)
        candidates = tuple(
            point
            if point.component_id == identifier
            else replace(point, component_id=identifier)
            for point in points
        )
        self._component_points[identifier] = candidates
        stale_keys = [
            key for key in self._component_point_index if key[0] == identifier
        ]
        for key in stale_keys:
            del self._component_point_index[key]
        for point in candidates:
            self._component_point_index[(identifier, point.id)] = point

    def component_points(self, component_id: str) -> tuple[CandidatePoint, ...]:
        return self._component_points.get(str(component_id), ())

    def get(self, component_id: str, point_id: str) -> CandidatePoint | None:
        return self._component_point_index.get(
            (str(component_id), str(point_id))
        )

    def has_component(self, component_id: str) -> bool:
        return str(component_id) in self._component_points

    def component_ids(self) -> tuple[str, ...]:
        return tuple(self._component_points)


class RenderDirty(IntFlag):
    """Independent UI regions that can be refreshed in one idle flush."""

    NONE = 0
    FULL_SCENE = auto()
    COMPONENT_LAYER = auto()
    CANDIDATE_LAYER = auto()
    COMPONENT_SELECTION = auto()
    CANDIDATE_SELECTION = auto()
    HOVER = auto()
    TEMP_LINE = auto()
    DETAIL_PANEL = auto()
    TREE_SELECTION = auto()


@dataclass
class PerformanceDiagnostics:
    full_scene_rebuilds: int = 0
    engineering_member_rebuilds: int = 0
    candidate_layer_rebuilds: int = 0
    selection_overlay_updates: int = 0
    temporary_overlay_updates: int = 0
    candidate_tree_rebuilds: int = 0
    selection_controller_calls: int = 0
    idempotent_skips: int = 0
    canvas_item_count: int = 0
    render_pending: bool = False
    last_update_ms: dict[str, float] = field(default_factory=dict)

    def record(self, operation: str, started_at: float) -> None:
        self.last_update_ms[operation] = round(
            (time.perf_counter() - started_at) * 1000.0,
            3,
        )

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


class RenderScheduler:
    """Coalesce dirty regions and prevent nested preview drawing."""

    def __init__(
        self,
        after_idle: Callable[[Callable[[], None]], Any],
        render: Callable[[RenderDirty], None],
        diagnostics: PerformanceDiagnostics | None = None,
    ) -> None:
        self._after_idle = after_idle
        self._render = render
        self._diagnostics = diagnostics
        self._dirty = RenderDirty.NONE
        self._pending_token: Any = None
        self._drawing = False

    @property
    def dirty(self) -> RenderDirty:
        return self._dirty

    @property
    def pending(self) -> bool:
        return self._pending_token is not None

    def request(self, dirty: RenderDirty) -> None:
        if dirty == RenderDirty.NONE:
            return
        self._dirty |= dirty
        if self._diagnostics is not None:
            self._diagnostics.render_pending = True
        if self._drawing or self._pending_token is not None:
            return
        self._pending_token = self._after_idle(self.flush)

    def flush(self) -> None:
        self._pending_token = None
        if self._drawing:
            self.request(self._dirty)
            return
        dirty = self._dirty
        if dirty == RenderDirty.NONE:
            if self._diagnostics is not None:
                self._diagnostics.render_pending = False
            return
        self._dirty = RenderDirty.NONE
        self._drawing = True
        try:
            self._render(dirty)
        finally:
            self._drawing = False
            if self._dirty != RenderDirty.NONE:
                self.request(self._dirty)
            elif self._diagnostics is not None:
                self._diagnostics.render_pending = False


@dataclass
class PreviewScene:
    """Canvas item index; model objects never live in this view-only layer."""

    source_geometry_items: list[int] = field(default_factory=list)
    auxiliary_geometry_items: list[int] = field(default_factory=list)
    component_items: dict[str, list[int]] = field(default_factory=dict)
    candidate_point_items: dict[str, int] = field(default_factory=dict)
    selection_items: dict[str, int] = field(default_factory=dict)
    temporary_line_items: list[int] = field(default_factory=list)
    axis_items: list[int] = field(default_factory=list)
    source_handle_items: dict[str, list[int]] = field(default_factory=dict)
    item_to_component: dict[int, str] = field(default_factory=dict)
    item_to_candidate_point: dict[int, str] = field(default_factory=dict)

    def clear(self) -> None:
        self.source_geometry_items.clear()
        self.auxiliary_geometry_items.clear()
        self.component_items.clear()
        self.candidate_point_items.clear()
        self.selection_items.clear()
        self.temporary_line_items.clear()
        self.axis_items.clear()
        self.source_handle_items.clear()
        self.item_to_component.clear()
        self.item_to_candidate_point.clear()

    def clear_layer(self, layer: str) -> None:
        if layer == "engineering_members":
            for item_ids in self.component_items.values():
                for item_id in item_ids:
                    self.item_to_component.pop(item_id, None)
            self.component_items.clear()
        elif layer == "candidate_overlay":
            for item_id in self.candidate_point_items.values():
                self.item_to_candidate_point.pop(item_id, None)
            self.candidate_point_items.clear()
        elif layer == "selection_overlay":
            self.selection_items.clear()
        elif layer == "temporary_overlay":
            self.temporary_line_items.clear()
        elif layer == "source_geometry":
            self.source_geometry_items.clear()
            self.source_handle_items.clear()
        elif layer == "auxiliary_geometry":
            self.auxiliary_geometry_items.clear()
        elif layer == "coordinate_axis":
            self.axis_items.clear()


class PreviewRenderer:
    """Small Canvas drawing boundary with stable layer tags and ID indexes."""

    LAYERS = (
        "source_geometry",
        "auxiliary_geometry",
        "engineering_members",
        "candidate_overlay",
        "selection_overlay",
        "temporary_overlay",
        "coordinate_axis",
    )

    def __init__(self, canvas: Any, scene: PreviewScene) -> None:
        self.canvas = canvas
        self.scene = scene

    @staticmethod
    def _tags(layer: str, extra_tags: Sequence[str]) -> tuple[str, ...]:
        return tuple(dict.fromkeys((layer, *map(str, extra_tags))))

    def clear(self) -> None:
        self.canvas.delete("all")
        self.scene.clear()

    def delete_layer(self, layer: str) -> None:
        self.canvas.delete(layer)
        self.scene.clear_layer(layer)

    def _register(
        self,
        item_id: int,
        layer: str,
        *,
        component_id: str = "",
        candidate_point_id: str = "",
        source_handle: str = "",
        overlay_key: str = "",
    ) -> int:
        if layer == "source_geometry":
            self.scene.source_geometry_items.append(item_id)
        elif layer == "auxiliary_geometry":
            self.scene.auxiliary_geometry_items.append(item_id)
        elif layer == "engineering_members" and component_id:
            self.scene.component_items.setdefault(component_id, []).append(item_id)
            self.scene.item_to_component[item_id] = component_id
        elif layer == "candidate_overlay" and candidate_point_id:
            self.scene.candidate_point_items[candidate_point_id] = item_id
            self.scene.item_to_candidate_point[item_id] = candidate_point_id
        elif layer == "selection_overlay" and overlay_key:
            self.scene.selection_items[overlay_key] = item_id
        elif layer == "temporary_overlay":
            self.scene.temporary_line_items.append(item_id)
        elif layer == "coordinate_axis":
            self.scene.axis_items.append(item_id)
        if source_handle:
            self.scene.source_handle_items.setdefault(source_handle, []).append(
                item_id
            )
        return item_id

    def create_line(
        self,
        layer: str,
        *coordinates: float,
        component_id: str = "",
        candidate_point_id: str = "",
        source_handle: str = "",
        overlay_key: str = "",
        extra_tags: Sequence[str] = (),
        **options: Any,
    ) -> int:
        options["tags"] = self._tags(layer, extra_tags)
        item_id = self.canvas.create_line(*coordinates, **options)
        return self._register(
            item_id,
            layer,
            component_id=component_id,
            candidate_point_id=candidate_point_id,
            source_handle=source_handle,
            overlay_key=overlay_key,
        )

    def create_oval(
        self,
        layer: str,
        *coordinates: float,
        candidate_point_id: str = "",
        overlay_key: str = "",
        extra_tags: Sequence[str] = (),
        **options: Any,
    ) -> int:
        options["tags"] = self._tags(layer, extra_tags)
        item_id = self.canvas.create_oval(*coordinates, **options)
        return self._register(
            item_id,
            layer,
            candidate_point_id=candidate_point_id,
            overlay_key=overlay_key,
        )

    def create_text(
        self,
        layer: str,
        *coordinates: float,
        component_id: str = "",
        source_handle: str = "",
        overlay_key: str = "",
        extra_tags: Sequence[str] = (),
        **options: Any,
    ) -> int:
        options["tags"] = self._tags(layer, extra_tags)
        item_id = self.canvas.create_text(*coordinates, **options)
        return self._register(
            item_id,
            layer,
            component_id=component_id,
            source_handle=source_handle,
            overlay_key=overlay_key,
        )

    def create_rectangle(
        self,
        layer: str,
        *coordinates: float,
        overlay_key: str = "",
        extra_tags: Sequence[str] = (),
        **options: Any,
    ) -> int:
        options["tags"] = self._tags(layer, extra_tags)
        item_id = self.canvas.create_rectangle(*coordinates, **options)
        return self._register(
            item_id,
            layer,
            overlay_key=overlay_key,
        )


class TreeSelectionSynchronizer:
    """Suppress delayed virtual events produced by programmatic selection."""

    def __init__(
        self,
        tree: Any,
        after_idle: Callable[[Callable[[], None]], Any],
    ) -> None:
        self.tree = tree
        self._after_idle = after_idle
        self._generation = 0
        self._active_generation = 0

    @property
    def syncing(self) -> bool:
        return self._active_generation != 0

    def select(self, iid: str) -> bool:
        if not iid or not self.tree.exists(iid):
            return False
        if tuple(self.tree.selection()) == (iid,):
            self.tree.focus(iid)
            self.tree.see(iid)
            return False
        self._generation += 1
        generation = self._generation
        self._active_generation = generation
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)

        def finish() -> None:
            if self._active_generation == generation:
                self._active_generation = 0

        self._after_idle(finish)
        return True


class CandidateTreeAdapter:
    """Incremental, ID-only projection of the canonical candidate store."""

    def __init__(
        self,
        tree: Any,
        after_idle: Callable[[Callable[[], None]], Any],
    ) -> None:
        self.tree = tree
        self.selection_sync = TreeSelectionSynchronizer(tree, after_idle)
        self.point_id_by_iid: dict[str, str] = {}
        self.iid_by_point_id: dict[str, str] = {}
        self.component_id = ""
        self.hovered_point_id = ""
        self.rebuild_count = 0

    @property
    def syncing(self) -> bool:
        return self.selection_sync.syncing

    def rebuild(
        self,
        component_id: str,
        points: Sequence[CandidatePoint],
        row_values: Callable[[CandidatePoint], Sequence[Any]],
        predicate: Callable[[CandidatePoint], bool] | None = None,
    ) -> None:
        self.tree.delete(*self.tree.get_children())
        self.point_id_by_iid.clear()
        self.iid_by_point_id.clear()
        self.component_id = component_id
        self.hovered_point_id = ""
        for point in points:
            if predicate is not None and not predicate(point):
                continue
            iid = f"candidate::{component_id}::{point.id}"
            self.tree.insert("", "end", iid=iid, values=tuple(row_values(point)))
            self.point_id_by_iid[iid] = point.id
            self.iid_by_point_id[point.id] = iid
        self.rebuild_count += 1

    def point_id_for_iid(self, iid: str) -> str:
        return self.point_id_by_iid.get(iid, "")

    def sync_selection(self, point_id: str) -> bool:
        return self.selection_sync.select(self.iid_by_point_id.get(point_id, ""))

    def update_row(
        self,
        point_id: str,
        values: Sequence[Any],
    ) -> None:
        iid = self.iid_by_point_id.get(point_id, "")
        if iid and self.tree.exists(iid):
            self.tree.item(iid, values=tuple(values))

    def set_hover(self, point_id: str) -> None:
        if point_id == self.hovered_point_id:
            return
        self.tree.tag_configure("hover", background="#ffe0b2")
        previous_iid = self.iid_by_point_id.get(self.hovered_point_id, "")
        if previous_iid and self.tree.exists(previous_iid):
            self.tree.item(previous_iid, tags=())
        self.hovered_point_id = point_id
        iid = self.iid_by_point_id.get(point_id, "")
        if iid and self.tree.exists(iid):
            self.tree.item(iid, tags=("hover",))


class SelectionController:
    """One-way intent -> state transition -> dirty-region notification."""

    VALID_SOURCES = {
        "canvas",
        "candidate_tree",
        "component_tree",
        "programmatic",
        "error_list",
        "restore_recommended",
        "cad_manual",
    }

    def __init__(
        self,
        state: SelectionState,
        candidate_store: CandidatePointStore,
        member_lookup: Callable[[str], Any],
        request_render: Callable[[RenderDirty], None],
        diagnostics: PerformanceDiagnostics | None = None,
    ) -> None:
        self.state = state
        self.candidate_store = candidate_store
        self.member_lookup = member_lookup
        self.request_render = request_render
        self.diagnostics = diagnostics

    def _called(self) -> None:
        if self.diagnostics is not None:
            self.diagnostics.selection_controller_calls += 1

    def _noop(self) -> bool:
        if self.diagnostics is not None:
            self.diagnostics.idempotent_skips += 1
        return False

    def _commit(self, source: str, dirty: RenderDirty) -> bool:
        self.state.selection_source = (
            source if source in self.VALID_SOURCES else "programmatic"
        )
        self.state.revision += 1
        self.request_render(dirty)
        return True

    @staticmethod
    def _candidate_selection_source(point: CandidatePoint) -> str:
        if (
            "cad_manual" in point.point_types
            or point.point_type.startswith("cad_manual")
        ):
            return "cad_manual"
        return "manual_candidate_points"

    def select_component(self, component_id: str, source: str) -> bool:
        self._called()
        member = self.member_lookup(component_id)
        if member is None:
            return self._noop()
        if component_id == self.state.selected_component_id:
            return self._noop()
        self.state.selected_component_id = component_id
        self.state.hovered_component_id = ""
        self.state.selected_candidate_point_id = ""
        self.state.selected_candidate_source = ""
        self.state.hovered_candidate_point_id = ""
        self.state.preview_candidate_point_id = ""
        self.state.mode = "idle"
        self.state.selected_start_point_id = member.selected_start_point_id
        self.state.selected_end_point_id = member.selected_end_point_id
        self.state.pending_start_point_id = member.selected_start_point_id
        self.state.pending_end_point_id = member.selected_end_point_id
        self.state.pick_baseline_start_point_id = member.selected_start_point_id
        self.state.pick_baseline_end_point_id = member.selected_end_point_id
        self.state.pending_selection_source = member.selection_source
        return self._commit(
            source,
            RenderDirty.CANDIDATE_LAYER
            | RenderDirty.COMPONENT_SELECTION
            | RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL
            | RenderDirty.TREE_SELECTION,
        )

    def select_candidate_point(self, point_id: str, source: str) -> bool:
        self._called()
        component_id = self.state.selected_component_id
        point = self.candidate_store.get(component_id, point_id)
        if point is None:
            return self._noop()
        self.state.selected_candidate_source = (
            source if source in self.VALID_SOURCES else "programmatic"
        )
        mode = self.state.mode
        selected_changed = point_id != self.state.selected_candidate_point_id
        pending_changed = False
        if mode == "pick_start":
            if "start" not in point.valid_for:
                return self._noop()
            pending_changed = point_id != self.state.pending_start_point_id
            self.state.pending_start_point_id = point_id
            self.state.pending_selection_source = self._candidate_selection_source(
                point
            )
            self.state.mode = "idle"
        elif mode == "pick_end":
            if "end" not in point.valid_for:
                return self._noop()
            pending_changed = point_id != self.state.pending_end_point_id
            self.state.pending_end_point_id = point_id
            self.state.pending_selection_source = self._candidate_selection_source(
                point
            )
            self.state.mode = "idle"
        if not selected_changed and not pending_changed and mode == "idle":
            return self._noop()
        self.state.selected_candidate_point_id = point_id
        self.state.preview_candidate_point_id = point_id
        return self._commit(
            source,
            RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL
            | RenderDirty.TREE_SELECTION,
        )

    def set_hovered_component(self, component_id: str) -> bool:
        self._called()
        if component_id and self.member_lookup(component_id) is None:
            component_id = ""
        if component_id == self.state.hovered_component_id:
            return self._noop()
        self.state.hovered_component_id = component_id
        if component_id:
            self.state.hovered_candidate_point_id = ""
        return self._commit("canvas", RenderDirty.HOVER)

    def set_hovered_candidate(self, point_id: str) -> bool:
        self._called()
        if point_id and self.candidate_store.get(
            self.state.selected_component_id,
            point_id,
        ) is None:
            point_id = ""
        if point_id == self.state.hovered_candidate_point_id:
            return self._noop()
        self.state.hovered_candidate_point_id = point_id
        if point_id:
            self.state.hovered_component_id = ""
        return self._commit(
            "canvas",
            RenderDirty.HOVER | RenderDirty.TEMP_LINE | RenderDirty.DETAIL_PANEL,
        )

    def begin_pick_start(self) -> bool:
        return self._begin_pick("pick_start")

    def begin_pick_end(self) -> bool:
        return self._begin_pick("pick_end")

    def _begin_pick(self, mode: str) -> bool:
        self._called()
        if self.member_lookup(self.state.selected_component_id) is None:
            return self._noop()
        if self.state.mode == mode:
            return self._noop()
        self.state.mode = mode
        self.state.selected_candidate_point_id = ""
        self.state.selected_candidate_source = ""
        self.state.pick_baseline_start_point_id = self.state.pending_start_point_id
        self.state.pick_baseline_end_point_id = self.state.pending_end_point_id
        return self._commit(
            "programmatic",
            RenderDirty.CANDIDATE_LAYER
            | RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL,
        )

    def cancel_pick(self) -> bool:
        self._called()
        if self.state.mode not in {"pick_start", "pick_end"}:
            return self._noop()
        self.state.pending_start_point_id = self.state.pick_baseline_start_point_id
        self.state.pending_end_point_id = self.state.pick_baseline_end_point_id
        self.state.mode = "idle"
        return self._commit(
            "programmatic",
            RenderDirty.CANDIDATE_LAYER
            | RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL,
        )

    def swap_pending_points(self) -> bool:
        self._called()
        if not self.state.selected_component_id:
            return self._noop()
        start_id = self.state.pending_start_point_id
        end_id = self.state.pending_end_point_id
        if not start_id and not end_id:
            return self._noop()
        self.state.pending_start_point_id = end_id
        self.state.pending_end_point_id = start_id
        self.state.pending_selection_source = "manual_candidate_points"
        self.state.mode = "idle"
        return self._commit(
            "programmatic",
            RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL,
        )

    def restore_recommended_points(self) -> bool:
        self._called()
        member = self.member_lookup(self.state.selected_component_id)
        if member is None:
            return self._noop()
        values = (
            member.recommended_start_point_id,
            member.recommended_end_point_id,
        )
        if values == (
            self.state.pending_start_point_id,
            self.state.pending_end_point_id,
        ) and self.state.mode == "idle":
            return self._noop()
        self.state.pending_start_point_id = values[0]
        self.state.pending_end_point_id = values[1]
        self.state.pending_selection_source = "auto"
        self.state.mode = "idle"
        return self._commit(
            "restore_recommended",
            RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL,
        )

    def cancel_pending(self) -> bool:
        self._called()
        values = (
            self.state.selected_start_point_id,
            self.state.selected_end_point_id,
        )
        if values == (
            self.state.pending_start_point_id,
            self.state.pending_end_point_id,
        ) and self.state.mode == "idle":
            return self._noop()
        self.state.pending_start_point_id = values[0]
        self.state.pending_end_point_id = values[1]
        member = self.member_lookup(self.state.selected_component_id)
        self.state.pending_selection_source = (
            member.selection_source if member is not None else "auto"
        )
        self.state.mode = "idle"
        return self._commit(
            "programmatic",
            RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL,
        )

    def set_pending_pair(
        self,
        start_point_id: str,
        end_point_id: str,
        source: str,
    ) -> bool:
        self._called()
        component_id = self.state.selected_component_id
        start = self.candidate_store.get(component_id, start_point_id)
        end = self.candidate_store.get(component_id, end_point_id)
        if start is None or end is None:
            return self._noop()
        if (
            start_point_id == self.state.pending_start_point_id
            and end_point_id == self.state.pending_end_point_id
            and self.state.mode == "idle"
        ):
            return self._noop()
        self.state.pending_start_point_id = start_point_id
        self.state.pending_end_point_id = end_point_id
        self.state.selected_candidate_point_id = start_point_id
        self.state.selected_candidate_source = (
            source if source in self.VALID_SOURCES else "programmatic"
        )
        self.state.preview_candidate_point_id = start_point_id
        self.state.pending_selection_source = (
            "cad_manual" if source == "cad_manual" else "manual_candidate_points"
        )
        self.state.mode = "idle"
        return self._commit(
            source,
            RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL
            | RenderDirty.TREE_SELECTION,
        )

    def synchronize_formal_member(self, source: str = "programmatic") -> bool:
        self._called()
        member = self.member_lookup(self.state.selected_component_id)
        if member is None:
            return self._noop()
        self.state.selected_start_point_id = member.selected_start_point_id
        self.state.selected_end_point_id = member.selected_end_point_id
        self.state.pending_start_point_id = member.selected_start_point_id
        self.state.pending_end_point_id = member.selected_end_point_id
        self.state.pending_selection_source = member.selection_source
        self.state.mode = "idle"
        return self._commit(
            source,
            RenderDirty.COMPONENT_LAYER
            | RenderDirty.COMPONENT_SELECTION
            | RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL
            | RenderDirty.TREE_SELECTION,
        )


class ImportModelController:
    """The only UI controller allowed to commit pending endpoint choices."""

    def __init__(
        self,
        tolerances: GeometryTolerances,
        candidate_store: CandidatePointStore | None = None,
    ) -> None:
        self.tolerances = tolerances
        self.candidate_store = candidate_store

    def apply_pending(
        self,
        result: DXFImportResult,
        state: SelectionState,
    ) -> DXFImportResult:
        if self.candidate_store is not None:
            start = self.candidate_store.get(
                state.selected_component_id,
                state.pending_start_point_id,
            )
            end = self.candidate_store.get(
                state.selected_component_id,
                state.pending_end_point_id,
            )
            if start is None or end is None:
                raise DXFImportError("待套用候選點不在 CandidatePointStore 中。")
        return apply_candidate_point_selection(
            result,
            state.selected_component_id,
            state.pending_start_point_id,
            state.pending_end_point_id,
            self.tolerances,
            selection_source=state.pending_selection_source,
        )


class CandidatePointBuilder:
    """Build engineering-relevant endpoint choices from recognition evidence."""

    def __init__(
        self,
        source_geometry: Sequence[SourceGeometry],
        walers: Sequence[Waler],
        tolerances: GeometryTolerances,
    ) -> None:
        self.source_geometry = tuple(source_geometry)
        self.walers = tuple(walers)
        self.tolerances = tolerances

    @staticmethod
    def _role(member: Waler | Strut | Brace | AuxiliaryComponent) -> str:
        if isinstance(member, Waler):
            return "waler"
        if isinstance(member, Strut):
            return "strut"
        if isinstance(member, Brace):
            return "brace"
        if isinstance(member, Column):
            return "column"
        if isinstance(member, Beam):
            return "beam"
        return "corner_brace"

    def build(
        self,
        member: Waler | Strut | Brace | AuxiliaryComponent,
    ) -> Waler | Strut | Brace | AuxiliaryComponent:
        # Endpoint choices must preserve distinct section edges; the component
        # duplicate tolerance (often 50 mm) is intentionally capped at 1 mm.
        store = CandidatePointStore(
            min(
                self.tolerances.duplicate_tolerance_mm,
                self.tolerances.endpoint_tolerance_mm,
                1.0,
            )
        )
        world_start = member.world_start or member.start
        world_end = member.world_end or member.end
        role = self._role(member)
        if isinstance(member, Waler):
            start_meta = end_meta = (
                "waler_inner_line_endpoint",
                "圍令內側線端點",
                member.source_handles,
                member.source_entity_types,
            )
        elif isinstance(member, (Strut, Brace)):
            def connected_endpoint_meta(waler_id: str) -> tuple[
                str,
                str,
                tuple[str, ...],
                tuple[str, ...],
            ]:
                waler = next(
                    (candidate for candidate in self.walers if candidate.id == waler_id),
                    None,
                )
                if waler is None:
                    return (
                        "recognized_engineering_endpoint",
                        "自動辨識工程線端點",
                        member.source_handles,
                        member.source_entity_types,
                    )
                return (
                    "waler_intersection",
                    f"與 {waler.id} 圍令內側線交點",
                    tuple(sorted({*member.source_handles, *waler.source_handles})),
                    tuple(
                        sorted(
                            {
                                *member.source_entity_types,
                                *waler.source_entity_types,
                            }
                        )
                    ),
                )

            start_meta = connected_endpoint_meta(member.from_waler)
            end_meta = connected_endpoint_meta(member.to_waler)
        else:
            start_meta = end_meta = (
                "recognized_engineering_endpoint",
                "自動辨識構件端點",
                member.source_handles,
                member.source_entity_types,
            )
        start_type, start_label, start_handles, start_entity_types = start_meta
        end_type, end_label, end_handles, end_entity_types = end_meta
        start_id = store.add(
            world_start,
            point_type=start_type,
            label=f"{start_label}（起點）",
            source_handles=start_handles,
            source_entity_types=start_entity_types,
            recommended_for=("start",),
            score=1.0,
            valid_for=("start",),
        )
        end_id = store.add(
            world_end,
            point_type=end_type,
            label=f"{end_label}（終點）",
            source_handles=end_handles,
            source_entity_types=end_entity_types,
            recommended_for=("end",),
            score=1.0,
            valid_for=("end",),
        )

        for line in member.line_candidates:
            label = line.label or "辨識候選工程線"
            point_type = (
                "waler_inner_line_endpoint"
                if isinstance(member, Waler) and line.id == member.selected_candidate_id
                else "recognized_line_endpoint"
            )
            store.add(
                line.world_start,
                point_type=point_type,
                label=f"{label}起點",
                source_handles=member.source_handles,
                source_entity_types=member.source_entity_types,
                score=0.90,
                valid_for=("start",),
            )
            store.add(
                line.world_end,
                point_type=point_type,
                label=f"{label}終點",
                source_handles=member.source_handles,
                source_entity_types=member.source_entity_types,
                score=0.90,
                valid_for=("end",),
            )

        if isinstance(member, Beam):
            for index, point in enumerate(member.world_path[1:-1], 2):
                store.add(
                    point,
                    point_type="beam_path_vertex",
                    label=f"托梁路徑轉折點 {index}",
                    source_handles=member.source_handles,
                    source_entity_types=member.source_entity_types,
                    score=0.88,
                    valid_for=(
                        ("start",)
                        if _distance(point, world_start)
                        <= _distance(point, world_end)
                        else ("end",)
                    ),
                )

        axis = _unit(world_start, world_end)
        length = _length(world_start, world_end)
        raw_options: list[
            tuple[float, Point, SourceGeometry, tuple[str, ...]]
        ] = []
        if axis is not None:
            corridor = max(
                self.tolerances.collinear_tolerance_mm,
                member.source_width * 0.75,
                self.tolerances.endpoint_tolerance_mm,
            )
            extension = self.tolerances.connection_tolerance_mm
            member_handles = set(member.source_handles)
            for geometry in self.source_geometry:
                if geometry.role != role:
                    continue
                if geometry.source_handle not in member_handles:
                    continue
                if len(geometry.points) < 2:
                    continue
                xs = [point[0] for point in geometry.points]
                ys = [point[1] for point in geometry.points]
                if math.hypot(max(xs) - min(xs), max(ys) - min(ys)) < (
                    self.tolerances.minimum_component_length_mm
                ):
                    continue
                for point in geometry.points:
                    along = _dot(_vector(world_start, point), axis)
                    perpendicular = _line_distance(point, world_start, world_end)
                    if perpendicular > corridor or not (-extension <= along <= length + extension):
                        continue
                    endpoint_distance = min(
                        _distance(point, world_start),
                        _distance(point, world_end),
                    )
                    score = 0.82 if endpoint_distance <= extension else 0.58
                    valid_for = (
                        ("start",)
                        if along < length / 2
                        else ("end",)
                        if along > length / 2
                        else ("start", "end")
                    )
                    raw_options.append((score, point, geometry, valid_for))
        raw_options.sort(key=lambda item: (-item[0], item[1][0], item[1][1]))
        for score, point, geometry, valid_for in raw_options[:40]:
            store.add(
                point,
                point_type="source_geometry_vertex",
                label="原始外框有效頂點",
                source_handles=(geometry.source_handle,),
                source_entity_types=(geometry.source_entity_type,),
                score=score,
                valid_for=valid_for,
            )

        if isinstance(member, (Strut, Brace)) and axis is not None:
            for waler in self.walers:
                direct = _segment_intersection_point(
                    (world_start, world_end),
                    (waler.world_start or waler.start, waler.world_end or waler.end),
                    self.tolerances.endpoint_tolerance_mm,
                )
                extended = direct or _line_segment_intersection_point(
                    (world_start, world_end),
                    (waler.world_start or waler.start, waler.world_end or waler.end),
                    self.tolerances.endpoint_tolerance_mm,
                )
                if extended is None:
                    continue
                along = _dot(_vector(world_start, extended), axis)
                if not (
                    -self.tolerances.connection_tolerance_mm
                    <= along
                    <= length + self.tolerances.connection_tolerance_mm
                ):
                    continue
                store.add(
                    extended,
                    point_type=(
                        "waler_intersection"
                        if direct is not None
                        else "extended_axis_waler_intersection"
                    ),
                    label=(
                        f"與 {waler.id} 圍令內側線交點"
                        if direct is not None
                        else f"長軸延伸線與 {waler.id} 圍令內側線交點"
                    ),
                    source_handles=(*member.source_handles, *waler.source_handles),
                    source_entity_types=(
                        *member.source_entity_types,
                        *waler.source_entity_types,
                    ),
                    score=0.98 if direct is not None else 0.92,
                    valid_for=(
                        ("start",)
                        if along < length / 2
                        else ("end",)
                        if along > length / 2
                        else ("start", "end")
                    ),
                )

        return replace(
            member,
            candidate_points=tuple(
                replace(point, component_id=member.id)
                for point in store.points()
            ),
            recommended_start_point_id=start_id,
            recommended_end_point_id=end_id,
            selected_start_point_id=start_id,
            selected_end_point_id=end_id,
            selection_source="auto",
        )


def build_candidate_points(
    result: DXFImportResult,
    tolerances: GeometryTolerances | None = None,
) -> DXFImportResult:
    """Populate all components from one shared candidate-point source."""

    tolerances = tolerances or GeometryTolerances()
    engineering_source_geometry = tuple(
        geometry
        for geometry in result.source_geometry
        if geometry.role not in {"auxiliary", "ignore"}
    )
    builder = CandidatePointBuilder(
        engineering_source_geometry,
        result.walers,
        tolerances,
    )
    return replace(
        result,
        walers=tuple(builder.build(member) for member in result.walers),
        struts=tuple(builder.build(member) for member in result.struts),
        braces=tuple(builder.build(member) for member in result.braces),
        columns=tuple(builder.build(member) for member in result.columns),
        beams=tuple(builder.build(member) for member in result.beams),
        corner_braces=tuple(
            builder.build(member) for member in result.corner_braces
        ),
    )


def connect_components_to_walers(
    struts: Sequence[Strut],
    braces: Sequence[Brace],
    walers: Sequence[Waler],
    tolerances: GeometryTolerances | None = None,
) -> tuple[tuple[Strut, ...], tuple[Brace, ...], tuple[ValidationMessage, ...]]:
    """Connect endpoints to the nearest finite Waler segment and snap them."""

    tolerances = tolerances or GeometryTolerances()
    messages: list[ValidationMessage] = []

    def connect(point: Point, role: str, handles: tuple[str, ...]) -> tuple[str, Point]:
        distances = sorted(
            (
                _segment_distance(point, waler.start, waler.end),
                waler.id,
                _project_onto_segment(point, waler.start, waler.end),
            )
            for waler in walers
        )
        if not distances or distances[0][0] > tolerances.connection_tolerance_mm:
            return "", point
        nearest = distances[0]
        if (
            len(distances) > 1
            and distances[1][0] <= tolerances.connection_tolerance_mm
            and distances[1][0] - nearest[0] <= tolerances.ambiguous_connection_delta_mm
        ):
            messages.append(
                ValidationMessage(
                    "warning",
                    "AMBIGUOUS_WALER_CONNECTION",
                    f"端點同時接近 {nearest[1]} 與 {distances[1][1]}，採用距離較近的 {nearest[1]}。",
                    role,
                    handles,
                )
            )
        return nearest[1], nearest[2]

    connected_struts = []
    for member in struts:
        from_waler, start = connect(member.start, "strut", member.source_handles)
        to_waler, end = connect(member.end, "strut", member.source_handles)
        connected = replace(
            member,
            start=start,
            end=end,
            world_start=start,
            world_end=end,
            local_start=start,
            local_end=end,
            from_waler=from_waler,
            to_waler=to_waler,
        )
        connected_struts.append(connected)
        count = bool(from_waler) + bool(to_waler)
        if count == 0:
            messages.append(ValidationMessage("error", "STRUT_NOT_CONNECTED", f"{member.id} 兩端皆未連接圍令。", "strut", member.source_handles))
        elif count == 1:
            messages.append(ValidationMessage("error", "STRUT_ONE_END_NOT_CONNECTED", f"{member.id} 僅一端連接圍令。", "strut", member.source_handles))

    connected_braces = []
    for member in braces:
        from_waler, start = connect(member.start, "brace", member.source_handles)
        to_waler, end = connect(member.end, "brace", member.source_handles)
        connected = replace(
            member,
            start=start,
            end=end,
            world_start=start,
            world_end=end,
            local_start=start,
            local_end=end,
            from_waler=from_waler,
            to_waler=to_waler,
        )
        connected_braces.append(connected)
        count = bool(from_waler) + bool(to_waler)
        if count == 0:
            messages.append(ValidationMessage("error", "BRACE_NOT_CONNECTED", f"{member.id} 兩端皆未連接圍令。", "brace", member.source_handles))
        elif count == 1:
            messages.append(ValidationMessage("error", "BRACE_ONE_END_NOT_CONNECTED", f"{member.id} 僅一端連接圍令。", "brace", member.source_handles))
    return tuple(connected_struts), tuple(connected_braces), tuple(messages)


def _column_association_tolerance(
    column: Column,
    strut: Strut,
    tolerances: GeometryTolerances,
) -> float:
    """Return a section-aware centreline distance for Column association."""

    base = max(0.0, tolerances.component_association_tolerance_mm)
    column_width = max(0.0, float(column.source_width or 0.0))
    strut_width = max(0.0, float(strut.source_width or 0.0))
    inferred = (
        column_width / 2.0
        + strut_width / 2.0
        + max(0.0, tolerances.column_association_clearance_mm)
    )
    maximum = max(base, tolerances.maximum_column_association_tolerance_mm)
    return min(maximum, max(base, inferred))


def _associate_components_to_struts_legacy(
    struts: Sequence[Strut],
    columns: Sequence[Column],
    beams: Sequence[Beam],
    tolerances: GeometryTolerances | None = None,
) -> tuple[
    tuple[Strut, ...],
    tuple[Column, ...],
    tuple[Beam, ...],
    tuple[ComponentAssociation, ...],
    tuple[ValidationMessage, ...],
]:
    """Assign every Column/Beam to exactly one nearest valid Strut."""

    tolerances = tolerances or GeometryTolerances()
    assignments: dict[str, dict[str, list[tuple[float, str]]]] = {
        strut.id: {"column": [], "beam": []} for strut in struts
    }
    associations: list[ComponentAssociation] = []
    messages: list[ValidationMessage] = []

    def associate_component(
        component: Column | Beam,
        role: str,
    ) -> Column | Beam:
        component_start = component.world_start or component.start
        component_end = component.world_end or component.end
        center = (
            component.world_reference_point
            if isinstance(component, Column)
            and component.world_reference_point is not None
            else _midpoint(component_start, component_end)
        )
        options: list[tuple[float, str, float, Point]] = []
        for strut in struts:
            strut_start = strut.world_start or strut.start
            strut_end = strut.world_end or strut.end
            axis = _unit(strut_start, strut_end)
            strut_length = _length(strut_start, strut_end)
            if axis is None or strut_length <= 1e-9:
                continue
            station = _dot(_vector(strut_start, center), axis)
            if not (0.0 <= station <= strut_length):
                continue
            projection = (
                strut_start[0] + axis[0] * station,
                strut_start[1] + axis[1] * station,
            )
            distance = _distance(center, projection)
            if distance > _column_association_tolerance(
                component,
                strut,
                tolerances,
            ):
                continue
            options.append((distance, strut.id, station, projection))
        options.sort(key=lambda item: (item[0], item[1]))
        if not options:
            label = "中間柱" if role == "column" else "托梁"
            messages.append(
                ValidationMessage(
                    "error",
                    f"{role.upper()}_NOT_ASSOCIATED",
                    f"{component.id} 無法在有效範圍及容差內找到所屬支撐。",
                    role,
                    component.source_handles,
                )
            )
            return replace(
                component,
                associated_strut_id="",
                association_station=None,
                association_distance=None,
                world_association_point=None,
                local_association_point=None,
            )
        distance, strut_id, station, projection = options[0]
        if (
            len(options) > 1
            and options[1][0] - distance
            <= tolerances.ambiguous_connection_delta_mm
        ):
            messages.append(
                ValidationMessage(
                    "warning",
                    "AMBIGUOUS_COMPONENT_ASSOCIATION",
                    f"{component.id} 同時接近 {strut_id} 與 {options[1][1]}，採用距離較近的 {strut_id}。",
                    role,
                    component.source_handles,
                )
            )
        assignments[strut_id][role].append((station, component.id))
        associations.append(
            ComponentAssociation(
                component.id,
                role,
                strut_id,
                station,
                distance,
                projection,
                projection,
            )
        )
        return replace(
            component,
            associated_strut_id=strut_id,
            association_station=station,
            association_distance=distance,
            world_association_point=projection,
            local_association_point=projection,
        )

    associated_columns = tuple(
        associate_component(component, "column") for component in columns
    )
    associated_beams = tuple(
        associate_component(component, "beam") for component in beams
    )

    def unique_stations(values: Sequence[tuple[float, str]]) -> tuple[float, ...]:
        stations: list[float] = []
        for station, _identifier in sorted(values):
            if not any(abs(station - existing) <= 1.0 for existing in stations):
                stations.append(station)
        return tuple(stations)

    associated_struts = []
    for strut in struts:
        column_values = sorted(assignments[strut.id]["column"])
        beam_values = sorted(assignments[strut.id]["beam"])
        associated_struts.append(
            replace(
                strut,
                associated_columns=tuple(identifier for _station, identifier in column_values),
                associated_beams=tuple(identifier for _station, identifier in beam_values),
                column_positions=unique_stations(column_values),
                beam_positions=unique_stations(beam_values),
            )
        )
    return (
        tuple(associated_struts),
        associated_columns,
        associated_beams,
        tuple(associations),
        tuple(messages),
    )


def associate_components_to_struts(
    struts: Sequence[Strut],
    columns: Sequence[Column],
    beams: Sequence[Beam],
    tolerances: GeometryTolerances | None = None,
) -> tuple[
    tuple[Strut, ...],
    tuple[Column, ...],
    tuple[Beam, ...],
    tuple[ComponentAssociation, ...],
    tuple[ValidationMessage, ...],
]:
    """Associate Columns by projection and Beams by every path crossing."""

    tolerances = tolerances or GeometryTolerances()
    assignments: dict[str, dict[str, list[tuple[float, str]]]] = {
        strut.id: {"column": [], "beam": []} for strut in struts
    }
    associations: list[ComponentAssociation] = []
    messages: list[ValidationMessage] = []

    def associate_column(component: Column) -> Column:
        center = component.world_reference_point or _midpoint(
            component.world_start or component.start,
            component.world_end or component.end,
        )
        options: list[tuple[float, str, float, Point]] = []
        for strut in struts:
            start = strut.world_start or strut.start
            end = strut.world_end or strut.end
            axis = _unit(start, end)
            length = _length(start, end)
            if axis is None or length <= 1e-9:
                continue
            station = _dot(_vector(start, center), axis)
            if not (0.0 <= station <= length):
                continue
            projection = (
                start[0] + axis[0] * station,
                start[1] + axis[1] * station,
            )
            distance = _distance(center, projection)
            if distance <= _column_association_tolerance(
                component,
                strut,
                tolerances,
            ):
                options.append((distance, strut.id, station, projection))
        options.sort(key=lambda item: (item[0], item[1]))
        if not options:
            messages.append(
                ValidationMessage(
                    "error",
                    "COLUMN_NOT_ASSOCIATED",
                    f"{component.id} 未找到有效範圍內的所屬支撐。",
                    "column",
                    component.source_handles,
                )
            )
            return replace(
                component,
                associated_strut_id="",
                association_station=None,
                association_distance=None,
                world_association_point=None,
                local_association_point=None,
            )
        distance, strut_id, station, projection = options[0]
        if (
            len(options) > 1
            and options[1][0] - distance
            <= tolerances.ambiguous_connection_delta_mm
        ):
            messages.append(
                ValidationMessage(
                    "warning",
                    "AMBIGUOUS_COMPONENT_ASSOCIATION",
                    f"{component.id} 同時接近 {strut_id} 與 {options[1][1]}，已採用較近的 {strut_id}。",
                    "column",
                    component.source_handles,
                )
            )
        assignments[strut_id]["column"].append((station, component.id))
        associations.append(
            ComponentAssociation(
                component.id,
                "column",
                strut_id,
                station,
                distance,
                projection,
                projection,
            )
        )
        return replace(
            component,
            associated_strut_id=strut_id,
            association_station=station,
            association_distance=distance,
            world_association_point=projection,
            local_association_point=projection,
        )

    def associate_beam(component: Beam) -> Beam:
        path = component.world_path or (
            component.world_start or component.start,
            component.world_end or component.end,
        )
        raw_crossings: list[BeamCrossing] = []
        overlap_struts: set[str] = set()
        snapped_pairs: set[tuple[str, int]] = set()
        for segment_index, beam_segment in enumerate(zip(path, path[1:])):
            if _length(*beam_segment) <= 1e-9:
                continue
            for strut in struts:
                strut_start = strut.world_start or strut.start
                strut_end = strut.world_end or strut.end
                strut_segment = (strut_start, strut_end)
                strut_axis = _unit(*strut_segment)
                strut_length = _length(*strut_segment)
                if strut_axis is None or strut_length <= 1e-9:
                    continue
                point = _segment_intersection_point(
                    beam_segment,
                    strut_segment,
                    1e-6,
                )
                distance = 0.0
                method = "segment_intersection"
                if point is None:
                    beam_point, strut_point, distance = (
                        _closest_points_between_segments(
                            beam_segment,
                            strut_segment,
                        )
                    )
                    if _segments_have_parallel_overlap(
                        beam_segment,
                        strut_segment,
                        tolerances.parallel_angle_tolerance_deg,
                    ):
                        if (
                            distance <= tolerances.beam_crossing_tolerance_mm
                            and strut.id not in overlap_struts
                        ):
                            overlap_struts.add(strut.id)
                            messages.append(
                                ValidationMessage(
                                    "warning",
                                    "BEAM_OVERLAPS_STRUT",
                                    f"{component.id} 與 {strut.id} 平行重疊，沒有唯一交點，請人工確認。",
                                    "beam",
                                    component.source_handles,
                                )
                            )
                        continue
                    if distance > tolerances.beam_crossing_tolerance_mm:
                        continue
                    point = strut_point
                    method = "gap_snapped_intersection"
                    snapped_pairs.add((strut.id, segment_index))
                station = _dot(_vector(strut_start, point), strut_axis)
                if not (-1e-6 <= station <= strut_length + 1e-6):
                    continue
                raw_crossings.append(
                    BeamCrossing(
                        component.id,
                        strut.id,
                        point,
                        point,
                        max(0.0, min(strut_length, station)),
                        segment_index,
                        distance,
                        method,
                    )
                )

        crossings: list[BeamCrossing] = []
        for crossing in sorted(
            raw_crossings,
            key=lambda item: (
                item.beam_segment_index,
                item.strut_id,
                item.strut_station,
            ),
        ):
            duplicate = any(
                existing.strut_id == crossing.strut_id
                and _distance(existing.world_point, crossing.world_point)
                <= tolerances.beam_crossing_duplicate_tolerance_mm
                for existing in crossings
            )
            if not duplicate:
                crossings.append(crossing)

        if not crossings:
            messages.append(
                ValidationMessage(
                    "warning",
                    "BEAM_NOT_ASSOCIATED",
                    f"{component.id} 的托梁路徑未與任何支撐相交，未建立禁止點。",
                    "beam",
                    component.source_handles,
                )
            )
            return replace(
                component,
                associated_strut_id="",
                associated_strut_ids=(),
                association_station=None,
                association_distance=None,
                world_association_point=None,
                local_association_point=None,
                crossings=(),
            )

        for strut_id, segment_index in sorted(snapped_pairs):
            messages.append(
                ValidationMessage(
                    "warning",
                    "BEAM_CROSSING_SNAPPED",
                    f"{component.id} 第 {segment_index + 1} 段與 {strut_id} 有小間隙，已吸附至支撐建立禁止點。",
                    "beam",
                    component.source_handles,
                )
            )
        associated_strut_ids = tuple(
            dict.fromkeys(crossing.strut_id for crossing in crossings)
        )
        for crossing in crossings:
            assignments[crossing.strut_id]["beam"].append(
                (crossing.strut_station, component.id)
            )
            associations.append(
                ComponentAssociation(
                    component.id,
                    "beam",
                    crossing.strut_id,
                    crossing.strut_station,
                    crossing.distance,
                    crossing.world_point,
                    crossing.local_point,
                )
            )
        first = crossings[0]
        return replace(
            component,
            associated_strut_id=first.strut_id,
            associated_strut_ids=associated_strut_ids,
            association_station=first.strut_station,
            association_distance=first.distance,
            world_association_point=first.world_point,
            local_association_point=first.local_point,
            crossings=tuple(crossings),
        )

    associated_columns = tuple(associate_column(item) for item in columns)
    associated_beams = tuple(associate_beam(item) for item in beams)

    def unique_stations(values: Sequence[tuple[float, str]]) -> tuple[float, ...]:
        stations: list[float] = []
        for station, _identifier in sorted(values):
            if not any(
                abs(station - existing)
                <= tolerances.beam_crossing_duplicate_tolerance_mm
                for existing in stations
            ):
                stations.append(station)
        return tuple(stations)

    associated_struts = tuple(
        replace(
            strut,
            associated_columns=tuple(
                dict.fromkeys(
                    identifier
                    for _station, identifier in sorted(
                        assignments[strut.id]["column"]
                    )
                )
            ),
            associated_beams=tuple(
                dict.fromkeys(
                    identifier
                    for _station, identifier in sorted(
                        assignments[strut.id]["beam"]
                    )
                )
            ),
            column_positions=unique_stations(
                assignments[strut.id]["column"]
            ),
            beam_positions=unique_stations(assignments[strut.id]["beam"]),
        )
        for strut in struts
    )
    return (
        associated_struts,
        associated_columns,
        associated_beams,
        tuple(associations),
        tuple(messages),
    )


def attach_corner_braces_to_struts(
    struts: Sequence[Strut],
    walers: Sequence[Waler],
    corner_braces: Sequence[CornerBrace],
    tolerances: GeometryTolerances | None = None,
) -> tuple[Strut, ...]:
    """Map confirmed corner-brace geometry onto associated Strut fields."""

    tolerances = tolerances or GeometryTolerances()

    waler_by_id = {member.id: member for member in walers}
    corner_values: dict[str, dict[str, tuple[float, float]]] = defaultdict(dict)
    for corner in corner_braces:
        best: tuple[float, Strut, str, Waler, Point] | None = None
        for strut in struts:
            endpoint_options = (
                ("from", strut.start, strut.from_waler),
                ("to", strut.end, strut.to_waler),
            )
            for endpoint_name, _base_point, waler_id in endpoint_options:
                waler = waler_by_id.get(waler_id)
                if waler is None:
                    continue
                for waler_point, support_point in (
                    (corner.start, corner.end),
                    (corner.end, corner.start),
                ):
                    waler_distance = _segment_distance(
                        waler_point,
                        waler.start,
                        waler.end,
                    )
                    support_distance = _segment_distance(
                        support_point,
                        strut.start,
                        strut.end,
                    )
                    if max(waler_distance, support_distance) > tolerances.connection_tolerance_mm:
                        continue
                    score = waler_distance + support_distance
                    option = (score, strut, endpoint_name, waler, waler_point)
                    if best is None or score < best[0]:
                        best = option
        if best is None:
            continue
        score, strut, endpoint_name, waler, waler_point = best
        axis = _unit(waler.start, waler.end)
        if axis is None:
            continue
        base_point = strut.start if endpoint_name == "from" else strut.end
        projected_waler_point = _project_onto_segment(
            waler_point,
            waler.start,
            waler.end,
        )
        delta = _dot(_vector(base_point, projected_waler_point), axis)
        direction_name = "start" if delta < 0 else "end"
        field_name = f"{endpoint_name}_brace_to_waler_{direction_name}_len"
        previous = corner_values[strut.id].get(field_name)
        if previous is None or score < previous[0]:
            # Project dimensions are expressed in whole millimetres.  DXF
            # intersections commonly retain sub-millimetre transform residue
            # (for example 1499.936 mm for a nominal 1500 mm station).
            corner_values[strut.id][field_name] = (score, round(abs(delta)))

    attached = []
    for strut in struts:
        changes: dict[str, Any] = {
            "from_brace_to_waler_start_len": 0.0,
            "from_brace_to_waler_end_len": 0.0,
            "to_brace_to_waler_start_len": 0.0,
            "to_brace_to_waler_end_len": 0.0,
        }
        for field_name, (_score, length) in corner_values.get(strut.id, {}).items():
            changes[field_name] = length
        attached.append(replace(strut, **changes))
    return tuple(attached)


def attach_auxiliary_components(
    struts: Sequence[Strut],
    walers: Sequence[Waler],
    columns: Sequence[Column],
    beams: Sequence[Beam],
    corner_braces: Sequence[CornerBrace],
    tolerances: GeometryTolerances | None = None,
) -> tuple[Strut, ...]:
    """Compatibility wrapper for association plus corner-brace attachment."""

    associated, _columns, _beams, _records, _messages = (
        associate_components_to_struts(struts, columns, beams, tolerances)
    )
    return attach_corner_braces_to_struts(
        associated,
        walers,
        corner_braces,
        tolerances,
    )


def validate_duplicate_engineering_members(
    collections: Sequence[
        Sequence[Waler | Strut | Brace | AuxiliaryComponent]
    ],
    tolerances: GeometryTolerances,
) -> tuple[ValidationMessage, ...]:
    """Detect duplicates introduced by manual endpoint combinations."""

    messages: list[ValidationMessage] = []
    for members in collections:
        for index, first in enumerate(members):
            first_line = (
                first.world_start or first.start,
                first.world_end or first.end,
            )
            for second in members[index + 1 :]:
                second_line = (
                    second.world_start or second.start,
                    second.world_end or second.end,
                )
                if not _lines_duplicate(first_line, second_line, tolerances):
                    continue
                messages.append(
                    ValidationMessage(
                        "error",
                        "DUPLICATE_ENGINEERING_COMPONENT",
                        f"{first.id} 與 {second.id} 的工程線重複，請修正候選點。",
                        _member_model_role(first),
                        tuple(
                            sorted(
                                {
                                    *first.source_handles,
                                    *second.source_handles,
                                }
                            )
                        ),
                    )
                )
    return tuple(messages)


def _result_members(
    result: DXFImportResult,
) -> tuple[Waler | Strut | Brace | AuxiliaryComponent, ...]:
    return (
        *result.walers,
        *result.struts,
        *result.braces,
        *result.columns,
        *result.beams,
        *result.corner_braces,
    )


def _member_model_role(
    member: Waler | Strut | Brace | AuxiliaryComponent,
) -> str:
    if isinstance(member, Waler):
        return "waler"
    if isinstance(member, Strut):
        return "strut"
    if isinstance(member, Brace):
        return "brace"
    if isinstance(member, Column):
        return "column"
    if isinstance(member, Beam):
        return "beam"
    return "corner_brace"


def _replace_result_member(
    result: DXFImportResult,
    member_id: str,
    updater: Any,
) -> DXFImportResult:
    found = False
    changes: dict[str, Any] = {}
    for collection_name in (
        "walers",
        "struts",
        "braces",
        "columns",
        "beams",
        "corner_braces",
    ):
        updated = []
        for member in getattr(result, collection_name):
            if member.id == member_id:
                member = updater(member)
                found = True
            updated.append(member)
        changes[collection_name] = tuple(updated)
    if not found:
        raise DXFImportError(f"找不到工程構件：{member_id}")
    return replace(result, **changes)


def candidate_point_by_id(
    member: Waler | Strut | Brace | AuxiliaryComponent,
    point_id: str,
) -> CandidatePoint | None:
    return next(
        (point for point in member.candidate_points if point.id == point_id),
        None,
    )


def validate_candidate_point_pair(
    member: Waler | Strut | Brace | AuxiliaryComponent,
    start_point_id: str,
    end_point_id: str,
    tolerances: GeometryTolerances | None = None,
    walers: Sequence[Waler] = (),
) -> tuple[ValidationMessage, ...]:
    """Validate one pending pair without changing the formal engineering model."""

    tolerances = tolerances or GeometryTolerances()
    start_point = candidate_point_by_id(member, start_point_id)
    end_point = candidate_point_by_id(member, end_point_id)
    role = _member_model_role(member)
    if start_point is None or end_point is None:
        return (
            ValidationMessage(
                "error",
                "CANDIDATE_POINT_MISSING",
                f"{member.id} 的待套用候選點資料遺失。",
                role,
                member.source_handles,
            ),
        )
    coordinates = (*start_point.world_point, *end_point.world_point)
    if not all(math.isfinite(value) for value in coordinates):
        return (
            ValidationMessage(
                "error",
                "CANDIDATE_POINT_INVALID",
                f"{member.id} 的候選點座標不是有效數字。",
                role,
                member.source_handles,
            ),
        )
    selected_length = _distance(start_point.world_point, end_point.world_point)
    if start_point.id == end_point.id or selected_length <= 1e-9:
        return (
            ValidationMessage(
                "error",
                "ZERO_LENGTH_CANDIDATE_LINE",
                f"{member.id} 的起點與終點不可相同。",
                role,
                member.source_handles,
            ),
        )
    if selected_length < tolerances.minimum_component_length_mm:
        return (
            ValidationMessage(
                "error",
                "CANDIDATE_LINE_TOO_SHORT",
                f"{member.id} 的待套用工程線長度 {selected_length:.1f} 小於絕對最小值。",
                role,
                member.source_handles,
            ),
        )

    original_line = (
        (
            member.line_candidates[0].world_start,
            member.line_candidates[0].world_end,
        )
        if member.line_candidates
        else (member.world_start or member.start, member.world_end or member.end)
    )
    selected_line = start_point.world_point, end_point.world_point
    angle = _angle_difference_deg(original_line, selected_line)
    messages: list[ValidationMessage] = []
    if angle > max(10.0, tolerances.parallel_angle_tolerance_deg * 4):
        messages.append(
            ValidationMessage(
                "warning",
                "CANDIDATE_LINE_DIRECTION_CHANGED",
                f"{member.id} 新工程線與自動辨識長軸差異 {angle:.1f}°，請確認方向。",
                role,
                member.source_handles,
            )
        )
    original_length = _length(*original_line)
    if original_length > 0 and selected_length < original_length * 0.35:
        messages.append(
            ValidationMessage(
                "warning",
                "POSSIBLE_COMPONENT_SHORT_SIDE",
                f"{member.id} 新工程線明顯短於自動辨識結果，可能選到構件短邊。",
                role,
                member.source_handles,
            )
        )
    if isinstance(member, Waler) and member.line_candidates:
        best_fit = min(
            max(
                _line_distance(
                    start_point.world_point,
                    candidate.world_start,
                    candidate.world_end,
                ),
                _line_distance(
                    end_point.world_point,
                    candidate.world_start,
                    candidate.world_end,
                ),
            )
            for candidate in member.line_candidates
        )
        if best_fit > tolerances.connection_tolerance_mm:
            messages.append(
                ValidationMessage(
                    "warning",
                    "WALER_CANDIDATE_LINE_UNUSUAL",
                    f"{member.id} 新工程線未落在既有圍令辨識線附近。",
                    role,
                    member.source_handles,
                )
            )
    if isinstance(member, (Strut, Brace)) and walers:
        for endpoint_name, endpoint in (
            ("起點", start_point.world_point),
            ("終點", end_point.world_point),
        ):
            nearest = min(
                _segment_distance(
                    endpoint,
                    waler.world_start or waler.start,
                    waler.world_end or waler.end,
                )
                for waler in walers
            )
            if nearest > tolerances.connection_tolerance_mm:
                messages.append(
                    ValidationMessage(
                        "warning",
                        "CANDIDATE_ENDPOINT_NOT_NEAR_WALER",
                        f"{member.id} {endpoint_name}距圍令內側線 {nearest:.1f}，套用後可能無法連接。",
                        role,
                        member.source_handles,
                    )
                )
    return tuple(messages)


def apply_candidate_point_selection(
    result: DXFImportResult,
    member_id: str,
    start_point_id: str,
    end_point_id: str,
    tolerances: GeometryTolerances | None = None,
    *,
    selection_source: str = "manual_candidate_points",
) -> DXFImportResult:
    """Commit a pending pair, then rebuild connections and derived Solver rows."""

    tolerances = tolerances or GeometryTolerances()
    target = next(
        (member for member in _result_members(result) if member.id == member_id),
        None,
    )
    if target is None:
        raise DXFImportError(f"找不到工程構件：{member_id}")
    validations = validate_candidate_point_pair(
        target,
        start_point_id,
        end_point_id,
        tolerances,
        result.walers,
    )
    errors = [item for item in validations if item.severity in ERROR_SEVERITIES]
    if errors:
        raise DXFImportError(errors[0].message)
    start_point = candidate_point_by_id(target, start_point_id)
    end_point = candidate_point_by_id(target, end_point_id)
    assert start_point is not None and end_point is not None

    def restore_world(
        member: Waler | Strut | Brace | AuxiliaryComponent,
    ) -> Waler | Strut | Brace | AuxiliaryComponent:
        world_start = member.world_start or member.start
        world_end = member.world_end or member.end
        changes: dict[str, Any] = {}
        if member.id == member_id:
            world_start = start_point.world_point
            world_end = end_point.world_point
            changes.update(
                selected_start_point_id=start_point_id,
                selected_end_point_id=end_point_id,
                selection_source=selection_source,
            )
            if isinstance(member, Waler):
                changes["engineering_line_kind"] = (
                    "cad_manual" if selection_source == "cad_manual" else "manual_candidate_points"
                )
        changes.update(
            start=world_start,
            end=world_end,
            world_start=world_start,
            world_end=world_end,
            local_start=world_start,
            local_end=world_end,
        )
        if isinstance(member, Column) and member.id == member_id:
            reference_point = _midpoint(world_start, world_end)
            changes.update(
                reference_point=reference_point,
                world_reference_point=reference_point,
                local_reference_point=reference_point,
            )
        if isinstance(member, Beam):
            world_path = list(
                member.world_path or (world_start, world_end)
            )
            if member.id == member_id:
                world_path[0] = world_start
                world_path[-1] = world_end
            changes.update(
                world_path=tuple(world_path),
                local_path=tuple(world_path),
                path=tuple(world_path),
                associated_strut_ids=(),
                crossings=(),
            )
        if isinstance(member, (Strut, Brace)):
            changes.update(from_waler="", to_waler="")
        if isinstance(member, Strut):
            changes.update(
                beam_positions=(),
                column_positions=(),
                associated_columns=(),
                associated_beams=(),
                from_brace_to_waler_start_len=0.0,
                from_brace_to_waler_end_len=0.0,
                to_brace_to_waler_start_len=0.0,
                to_brace_to_waler_end_len=0.0,
            )
        if isinstance(member, (Column, Beam)):
            changes.update(
                associated_strut_id="",
                association_station=None,
                association_distance=None,
                world_association_point=None,
                local_association_point=None,
            )
        return replace(member, **changes)

    walers = tuple(restore_world(member) for member in result.walers)
    struts = tuple(restore_world(member) for member in result.struts)
    braces = tuple(restore_world(member) for member in result.braces)
    columns = tuple(restore_world(member) for member in result.columns)
    beams = tuple(restore_world(member) for member in result.beams)
    corner_braces = tuple(restore_world(member) for member in result.corner_braces)
    connected_struts, connected_braces, connection_messages = (
        connect_components_to_walers(struts, braces, walers, tolerances)
    )
    (
        connected_struts,
        columns,
        beams,
        component_associations,
        association_messages,
    ) = associate_components_to_struts(
        connected_struts,
        columns,
        beams,
        tolerances,
    )
    connected_struts = attach_corner_braces_to_struts(
        connected_struts,
        walers,
        corner_braces,
        tolerances,
    )
    duplicate_messages = validate_duplicate_engineering_members(
        (
            walers,
            connected_struts,
            connected_braces,
            columns,
            beams,
            corner_braces,
        ),
        tolerances,
    )
    base_messages = tuple(
        message
        for message in result.messages
        if message.code not in CONNECTION_VALIDATION_CODES
        and message.code not in COMPONENT_ASSOCIATION_CODES
        and message.code
        not in {
            "MANUAL_LINE_SELECTION",
            "MANUAL_POINT_SELECTION",
            "CAD_MANUAL_LINE_SELECTION",
            "CANDIDATE_LINE_DIRECTION_CHANGED",
            "POSSIBLE_COMPONENT_SHORT_SIDE",
            "WALER_CANDIDATE_LINE_UNUSUAL",
            "CANDIDATE_ENDPOINT_NOT_NEAR_WALER",
            "DUPLICATE_ENGINEERING_COMPONENT",
        }
    )
    all_updated_members = (
        *walers,
        *connected_struts,
        *connected_braces,
        *columns,
        *beams,
        *corner_braces,
    )
    manual_messages = tuple(
        ValidationMessage(
            "info",
            (
                "CAD_MANUAL_LINE_SELECTION"
                if member.selection_source == "cad_manual"
                else "MANUAL_POINT_SELECTION"
            ),
            (
                f"{member.id} 已採用 CAD 人工指定工程線。"
                if member.selection_source == "cad_manual"
                else f"{member.id} 已採用候選點建立工程線。"
            ),
            _member_model_role(member),
            member.source_handles,
        )
        for member in all_updated_members
        if member.selection_source != "auto"
    )
    world_result = replace(
        result,
        walers=walers,
        struts=connected_struts,
        braces=connected_braces,
        columns=columns,
        beams=beams,
        corner_braces=corner_braces,
        messages=(
            *base_messages,
            *connection_messages,
            *association_messages,
            *duplicate_messages,
            *validations,
            *manual_messages,
        ),
        coordinate_system=CoordinateSystem(),
        component_associations=component_associations,
        beam_crossings=tuple(
            crossing for beam in beams for crossing in beam.crossings
        ),
    )
    return apply_coordinate_system(world_result, result.coordinate_system)


def add_cad_candidate_points(
    result: DXFImportResult,
    member_id: str,
    world_start: Point,
    world_end: Point,
    tolerances: GeometryTolerances | None = None,
) -> tuple[DXFImportResult, str, str]:
    """Add CAD Temp endpoints as candidates without committing the formal line."""

    tolerances = tolerances or GeometryTolerances()
    coordinates = (*world_start, *world_end)
    if not all(math.isfinite(float(value)) for value in coordinates):
        raise DXFImportError("CAD 指定工程線座標必須是有限數字。")
    world_start = float(world_start[0]), float(world_start[1])
    world_end = float(world_end[0]), float(world_end[1])
    if _distance(world_start, world_end) < tolerances.minimum_component_length_mm:
        raise DXFImportError("CAD 指定工程線短於系統允許的最小構件長度。")
    selected_ids: list[str] = []

    def add_points(
        member: Waler | Strut | Brace | AuxiliaryComponent,
    ) -> Waler | Strut | Brace | AuxiliaryComponent:
        store = CandidatePointStore(
            min(
                tolerances.duplicate_tolerance_mm,
                tolerances.endpoint_tolerance_mm,
                1.0,
            )
        )
        for point in member.candidate_points:
            retained_types = tuple(
                point_type
                for point_type in point.point_types
                if not point_type.startswith("cad_manual")
            )
            retained_primary = (
                point.point_type
                if not point.point_type.startswith("cad_manual")
                else (retained_types[0] if retained_types else "")
            )
            if (
                not retained_primary
                and point.id
                in {
                    member.selected_start_point_id,
                    member.selected_end_point_id,
                }
            ):
                retained_primary = "formal_engineering_endpoint"
                retained_types = (retained_primary,)
            if not retained_primary:
                continue
            stripped_cad_primary = retained_primary != point.point_type
            stored_id = store.add(
                point.world_point,
                point_type=retained_primary,
                label="既有辨識候選點" if stripped_cad_primary else point.label,
                source_handles=point.source_handles,
                source_entity_types=tuple(
                    entity_type
                    for entity_type in point.source_entity_types
                    if entity_type != "CAD_TEMP"
                ),
                recommended_for=point.recommended_for,
                score=min(point.score, 0.90) if stripped_cad_primary else point.score,
                valid_for=point.valid_for,
                preferred_id=point.id,
            )
            for extra_type in retained_types:
                if extra_type == retained_primary:
                    continue
                store.add(
                    point.world_point,
                    point_type=extra_type,
                    label=point.label,
                    source_handles=point.source_handles,
                    source_entity_types=point.source_entity_types,
                    recommended_for=point.recommended_for,
                    score=max(0.0, point.score - 1e-6),
                    valid_for=point.valid_for,
                    preferred_id=stored_id,
                )
        selected_ids.append(
            store.add(
                world_start,
                point_type="cad_manual_start",
                label="CAD 人工指定起點",
                source_handles=member.source_handles,
                source_entity_types=("CAD_TEMP",),
                score=1.0,
                valid_for=("start",),
                preferred_id="cad_manual_start",
            )
        )
        selected_ids.append(
            store.add(
                world_end,
                point_type="cad_manual_end",
                label="CAD 人工指定終點",
                source_handles=member.source_handles,
                source_entity_types=("CAD_TEMP",),
                score=1.0,
                valid_for=("end",),
                preferred_id="cad_manual_end",
            )
        )
        return replace(
            member,
            candidate_points=tuple(
                replace(point, component_id=member.id)
                for point in store.points()
            ),
        )

    updated = _replace_result_member(result, member_id, add_points)
    updated = apply_coordinate_system(updated, result.coordinate_system)
    return updated, selected_ids[0], selected_ids[1]


def select_engineering_line(
    result: DXFImportResult,
    member_id: str,
    candidate_id: str,
    tolerances: GeometryTolerances | None = None,
) -> DXFImportResult:
    """Compatibility adapter: convert a legacy line choice into two point choices."""

    target = next(
        (member for member in _result_members(result) if member.id == member_id),
        None,
    )
    if target is None:
        raise DXFImportError(f"找不到工程構件：{member_id}")
    candidate = next(
        (item for item in target.line_candidates if item.id == candidate_id),
        None,
    )
    if candidate is None:
        raise DXFImportError(f"{member_id} 沒有候選線段：{candidate_id}")
    updated, start_id, end_id = add_cad_candidate_points(
        result,
        member_id,
        candidate.world_start,
        candidate.world_end,
        tolerances,
    )
    updated = apply_candidate_point_selection(
        updated,
        member_id,
        start_id,
        end_id,
        tolerances,
        selection_source="manual_candidate_points",
    )
    return _replace_result_member(
        updated,
        member_id,
        lambda member: replace(member, selected_candidate_id=candidate_id),
    )


def set_cad_engineering_line(
    result: DXFImportResult,
    member_id: str,
    world_start: Point,
    world_end: Point,
    tolerances: GeometryTolerances | None = None,
) -> DXFImportResult:
    """Compatibility API: add CAD endpoints and immediately commit both."""

    updated, start_id, end_id = add_cad_candidate_points(
        result,
        member_id,
        world_start,
        world_end,
        tolerances,
    )
    updated = apply_candidate_point_selection(
        updated,
        member_id,
        start_id,
        end_id,
        tolerances,
        selection_source="cad_manual",
    )
    legacy_line = EngineeringLineCandidate(
        "cad_manual_line",
        "CAD 人工指定工程線",
        (float(world_start[0]), float(world_start[1])),
        (float(world_end[0]), float(world_end[1])),
        "cad_temp",
    )
    return _replace_result_member(
        updated,
        member_id,
        lambda member: replace(
            member,
            line_candidates=(
                *(
                    candidate
                    for candidate in member.line_candidates
                    if candidate.id != legacy_line.id
                ),
                legacy_line,
            ),
            selected_candidate_id=legacy_line.id,
        ),
    )


class DXFImporter:
    """Read one DXF and recognize component-level engineering-line candidates."""

    GEOMETRY_TYPES = {
        "LINE",
        "LWPOLYLINE",
        "POLYLINE",
        "MLINE",
        "SOLID",
        "TRACE",
        "INSERT",
    }
    TEXT_TYPES = {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}

    def __init__(
        self,
        file_path: str | Path,
        *,
        tolerances: GeometryTolerances | None = None,
        geometry_tolerance: float | None = None,
    ):
        self.file_path = Path(file_path)
        self.tolerances = tolerances or GeometryTolerances()
        if geometry_tolerance is not None:
            self.tolerances = replace(
                self.tolerances,
                endpoint_tolerance_mm=max(float(geometry_tolerance), 1e-9),
            )
        self._document: Any = None

    def read(self) -> "DXFImporter":
        if ezdxf is None:
            raise DXFImportError("尚未安裝 ezdxf；請先安裝專案相依套件。")
        if not self.file_path.is_file():
            raise DXFImportError(f"找不到 DXF 檔案：{self.file_path}")
        try:
            self._document = ezdxf.readfile(str(self.file_path))
        except Exception as exc:
            raise DXFImportError(f"無法讀取 DXF：{exc}") from exc
        return self

    @property
    def document(self) -> Any:
        if self._document is None:
            self.read()
        return self._document

    @property
    def layer_names(self) -> tuple[str, ...]:
        return tuple(layer.dxf.name for layer in self.document.layers)

    def layer_information(self) -> tuple[LayerInfo, ...]:
        counts: dict[str, Counter[str]] = defaultdict(Counter)
        for entity in self.document.modelspace():
            counts[str(entity.dxf.layer)][entity.dxftype()] += 1
        return tuple(
            LayerInfo(name, sum(counts[name].values()), dict(sorted(counts[name].items())))
            for name in self.layer_names
        )

    def entities_on_layer(self, layer_name: str) -> tuple[Any, ...]:
        if layer_name not in self.layer_names:
            raise DXFImportError(f"DXF 中沒有圖層「{layer_name}」。")
        return tuple(
            entity
            for entity in self.document.modelspace()
            if str(entity.dxf.layer) == layer_name
        )

    def convert(
        self,
        *,
        strut_layer: str | None = None,
        waler_layer: str | None = None,
        brace_layer: str | None = None,
        layer_roles: Mapping[str, str] | None = None,
        endpoint_tolerance: float | None = None,
        coordinate_system: CoordinateSystem | None = None,
    ) -> DXFImportResult:
        tolerances = self.tolerances
        if endpoint_tolerance is not None:
            tolerances = replace(
                tolerances,
                connection_tolerance_mm=max(float(endpoint_tolerance), 0.0),
            )
        engineering_roles = (
            "waler",
            "strut",
            "brace",
            "column",
            "beam",
            "corner_brace",
        )
        supported_roles = (*engineering_roles, "auxiliary")
        if layer_roles is None:
            legacy = {
                "waler": waler_layer,
                "strut": strut_layer,
                "brace": brace_layer,
            }
            if any(not layer for layer in legacy.values()):
                raise DXFImportError("請先完成圖層用途分類")
            layer_classification = {
                str(layer): role for role, layer in legacy.items() if layer
            }
        else:
            unknown_layers = sorted(set(layer_roles).difference(self.layer_names))
            if unknown_layers:
                raise DXFImportError(
                    f"DXF 中沒有圖層：{', '.join(unknown_layers)}"
                )
            invalid_roles = sorted(
                {
                    role
                    for role in layer_roles.values()
                    if role not in {*supported_roles, "ignore"}
                }
            )
            if invalid_roles:
                raise DXFImportError(
                    f"不支援的圖層用途：{', '.join(invalid_roles)}"
                )
            layer_classification = {
                layer: layer_roles.get(layer, "ignore")
                for layer in self.layer_names
            }
        missing = sorted(
            layer
            for layer in layer_classification
            if layer not in self.layer_names
        )
        if missing:
            raise DXFImportError(f"DXF 中沒有圖層：{', '.join(missing)}")
        selected = {
            role: tuple(
                layer
                for layer in self.layer_names
                if layer_classification.get(layer) == role
            )
            for role in supported_roles
        }
        missing_required = [
            role for role in ("waler", "strut") if not selected[role]
        ]
        if missing_required:
            labels = {"waler": "圍令", "strut": "支撐"}
            raise DXFImportError(
                "請至少指定一個"
                + "、".join(labels[role] for role in missing_required)
                + "圖層"
            )

        debug: list[EntityDebugInfo] = []
        messages: list[ValidationMessage] = []
        source_geometry: list[SourceGeometry] = []
        source_texts: list[SourceText] = []
        source_counts: dict[str, int] = {}
        candidates_by_role: dict[str, list[_Candidate]] = {}

        for role in engineering_roles:
            layers = selected[role]
            role_candidates: list[_Candidate] = []
            source_counts[role] = 0
            for layer in layers:
                entities = self.entities_on_layer(layer)
                source_counts[role] += len(entities)
                debug_start = len(debug)
                groups = self._geometry_groups(
                    role,
                    layer,
                    entities,
                    debug,
                    source_geometry,
                )
                ignored_text = sum(
                    item.status == "ignored"
                    and item.entity_type in self.TEXT_TYPES
                    for item in debug[debug_start:]
                )
                if ignored_text:
                    messages.append(
                        ValidationMessage(
                            "info",
                            "TEXT_SKIPPED",
                            f"已略過 {ignored_text} 個 DXF 文字圖元；文字不參與構件辨識。",
                            role,
                        )
                    )
                groups = self._merge_related_line_groups(groups, tolerances)
                for group in groups:
                    if role == "corner_brace":
                        corner_candidates, corner_messages = (
                            _corner_brace_candidates_from_group(
                                group,
                                tolerances,
                            )
                        )
                        messages.extend(corner_messages)
                        if corner_candidates:
                            role_candidates.extend(corner_candidates)
                            continue
                    candidate, candidate_messages = _candidate_from_group(
                        group,
                        role,
                        tolerances,
                    )
                    messages.extend(candidate_messages)
                    if candidate is None:
                        has_points = any(
                            primitive.points for primitive in group.primitives
                        )
                        has_nonzero_segment = any(
                            primitive.segments() for primitive in group.primitives
                        )
                        if has_points and not has_nonzero_segment:
                            messages.append(
                                ValidationMessage(
                                    "critical",
                                    "ZERO_LENGTH_COMPONENT",
                                    "來源幾何全部為零長度。",
                                    role,
                                    tuple(sorted(group.handles)),
                                )
                            )
                        code = f"{role.upper()}_RECOGNITION_FAILED"
                        engineering_line_code = (
                            "WALER_ENGINEERING_LINE_FAILED"
                            if role == "waler"
                            else f"{role.upper()}_CENTERLINE_FAILED"
                        )
                        handles = tuple(sorted(group.handles))
                        messages.append(
                            ValidationMessage(
                                "error",
                                code,
                                "幾何群組無法可靠辨識為單一工程構件。",
                                role,
                                handles,
                            )
                        )
                        messages.append(
                            ValidationMessage(
                                "error",
                                engineering_line_code,
                                (
                                    "圍令幾何群組無法建立可靠內側工程線。"
                                    if role == "waler"
                                    else "幾何群組無法建立可靠中心線。"
                                ),
                                role,
                                handles,
                            )
                        )
                        continue
                    component_length = (
                        sum(
                            _length(start, end)
                            for start, end in zip(
                                candidate.path_points,
                                candidate.path_points[1:],
                            )
                        )
                        if candidate.path_points
                        else _length(candidate.start, candidate.end)
                    )
                    if component_length <= 1e-9:
                        messages.append(
                            ValidationMessage(
                                "critical",
                                "ZERO_LENGTH_COMPONENT",
                                "辨識結果為零長度。",
                                role,
                                tuple(sorted(candidate.handles)),
                            )
                        )
                        continue
                    if component_length < tolerances.minimum_component_length_mm:
                        messages.append(
                            ValidationMessage(
                                "error",
                                "COMPONENT_TOO_SHORT",
                                f"構件長度 {component_length:.1f} 小於允許值。",
                                role,
                                tuple(sorted(candidate.handles)),
                            )
                        )
                        continue
                    role_candidates.append(candidate)
            deduplicated, duplicate_messages = _deduplicate_candidates(role_candidates, role, tolerances)
            messages.extend(duplicate_messages)
            candidates_by_role[role] = deduplicated
            if layers and not deduplicated:
                messages.append(ValidationMessage("critical", f"{role.upper()}_RECOGNITION_FAILED", f"{role} 圖層沒有可匯入的工程構件。", role))

        # Auxiliary is preview-only source geometry. It intentionally bypasses
        # recognition, candidate points, connections, associations and Solver.
        source_counts["auxiliary"] = 0
        for layer in selected["auxiliary"]:
            entities = self.entities_on_layer(layer)
            source_counts["auxiliary"] += len(entities)
            self._collect_auxiliary_source_texts(
                layer,
                entities,
                source_texts,
                debug,
            )
            self._geometry_groups(
                "auxiliary",
                layer,
                entities,
                debug,
                source_geometry,
            )

        _select_waler_inner_lines(candidates_by_role)
        messages.extend(
            _refine_corner_brace_axis_intersections(
                candidates_by_role,
                tolerances,
            )
        )
        self._validate_one_model_per_source(candidates_by_role, messages)
        walers = tuple(self._make_waler(index, candidate) for index, candidate in enumerate(candidates_by_role["waler"], 1))
        struts = tuple(self._make_strut(index, candidate) for index, candidate in enumerate(candidates_by_role["strut"], 1))
        braces = tuple(self._make_brace(index, candidate) for index, candidate in enumerate(candidates_by_role["brace"], 1))
        columns = tuple(
            self._make_auxiliary(Column, "C", "column", index, candidate)
            for index, candidate in enumerate(candidates_by_role["column"], 1)
        )
        beams = tuple(
            self._make_auxiliary(Beam, "BM", "beam", index, candidate)
            for index, candidate in enumerate(candidates_by_role["beam"], 1)
        )
        corner_braces = tuple(
            self._make_auxiliary(
                CornerBrace,
                "CB",
                "corner_brace",
                index,
                candidate,
            )
            for index, candidate in enumerate(
                candidates_by_role["corner_brace"],
                1,
            )
        )
        struts, braces, connection_messages = connect_components_to_walers(struts, braces, walers, tolerances)
        (
            struts,
            columns,
            beams,
            component_associations,
            association_messages,
        ) = associate_components_to_struts(
            struts,
            columns,
            beams,
            tolerances,
        )
        struts = attach_corner_braces_to_struts(
            struts,
            walers,
            corner_braces,
            tolerances,
        )
        messages.extend(connection_messages)
        messages.extend(association_messages)
        final_debug = self._finalize_debug(
            debug,
            (*walers, *struts, *braces, *columns, *beams, *corner_braces),
        )
        world_result = DXFImportResult(
            str(self.file_path.resolve()),
            self.layer_names,
            selected,
            self.layer_information(),
            walers,
            struts,
            braces,
            final_debug,
            tuple(messages),
            source_counts,
            tuple(source_geometry),
            tuple(source_texts),
            columns=columns,
            beams=beams,
            corner_braces=corner_braces,
            layer_classification=layer_classification,
            component_associations=component_associations,
            beam_crossings=tuple(
                crossing for beam in beams for crossing in beam.crossings
            ),
        )
        world_result = build_candidate_points(world_result, tolerances)
        return apply_coordinate_system(
            world_result,
            coordinate_system or CoordinateSystem(),
        )

    def _collect_auxiliary_source_texts(
        self,
        layer: str,
        entities: Sequence[Any],
        source_texts: list[SourceText],
        debug: list[EntityDebugInfo],
    ) -> None:
        """Collect displayed text recursively without exposing it to recognition."""

        if _recursive_decompose is None:
            return
        for entity in entities:
            root_handle = str(
                getattr(entity.dxf, "handle", "")
                or f"NO_HANDLE_TEXT_{len(source_texts)}"
            )
            try:
                leaves = list(_recursive_decompose((entity,)))
                leaves.extend(self._unbound_nested_attdefs(entity))
                for leaf in leaves:
                    entity_type = leaf.dxftype()
                    if entity_type not in self.TEXT_TYPES:
                        continue
                    text = self._source_text_content(leaf)
                    position = self._source_text_position(leaf)
                    if not text or position is None:
                        continue
                    source_texts.append(
                        SourceText(
                            role="auxiliary",
                            source_handle=root_handle,
                            text=text,
                            position=position,
                            height=self._source_text_height(leaf),
                            rotation=self._source_text_rotation(leaf),
                            source_layer=layer,
                            source_entity_type=entity_type,
                        )
                    )
            except Exception as exc:
                debug.append(
                    EntityDebugInfo(
                        "auxiliary",
                        layer,
                        entity.dxftype(),
                        root_handle,
                        "preview_failed",
                        "warning",
                        detail=f"Unable to read preview text: {exc}",
                    )
                )

    def _unbound_nested_attdefs(self, entity: Any) -> list[Any]:
        """Return nested ATTDEF defaults that have no displayed ATTRIB."""

        if entity.dxftype() != "INSERT":
            return []
        result: list[Any] = []
        attached_tags = {
            str(getattr(attrib.dxf, "tag", "")).casefold()
            for attrib in getattr(entity, "attribs", ())
        }
        block = entity.block()
        if block is not None:
            transform = entity.matrix44()
            for child in block:
                if child.dxftype() != "ATTDEF":
                    continue
                tag = str(getattr(child.dxf, "tag", "")).casefold()
                if tag in attached_tags:
                    continue
                copy = child.copy()
                copy.transform(transform)
                result.append(copy)
        try:
            virtual_entities = entity.virtual_entities()
            for child in virtual_entities:
                if child.dxftype() == "INSERT":
                    result.extend(self._unbound_nested_attdefs(child))
        except Exception:
            pass
        return result

    @staticmethod
    def _source_text_content(entity: Any) -> str:
        if entity.dxftype() == "MTEXT":
            plain_text = getattr(entity, "plain_text", None)
            value = plain_text() if callable(plain_text) else entity.dxf.text
        else:
            value = getattr(entity.dxf, "text", "")
        return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()

    @staticmethod
    def _source_text_position(entity: Any) -> Point | None:
        get_placement = getattr(entity, "get_placement", None)
        if callable(get_placement):
            try:
                _alignment, point, _second_point = get_placement()
                return _point(point)
            except (AttributeError, TypeError, ValueError):
                pass
        insert = getattr(entity.dxf, "insert", None)
        return None if insert is None else _point(insert)

    @staticmethod
    def _source_text_height(entity: Any) -> float:
        attribute = "char_height" if entity.dxftype() == "MTEXT" else "height"
        try:
            return max(
                float(getattr(entity.dxf, attribute, 0.0) or 0.0),
                0.0,
            )
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _source_text_rotation(entity: Any) -> float:
        get_rotation = getattr(entity, "get_rotation", None)
        try:
            if callable(get_rotation):
                return float(get_rotation())
            return float(getattr(entity.dxf, "rotation", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _geometry_groups(
        self,
        role: str,
        layer: str,
        entities: Sequence[Any],
        debug: list[EntityDebugInfo],
        source_geometry: list[SourceGeometry],
    ) -> list[_GeometryGroup]:
        groups: list[_GeometryGroup] = []
        ignored_text = 0
        for entity in entities:
            handle = str(getattr(entity.dxf, "handle", "") or f"NO_HANDLE_{len(groups)}")
            group = _GeometryGroup(
                f"{role}:{handle}", role, layer, [], {handle}, set(), []
            )
            if entity.dxftype() in self.TEXT_TYPES:
                ignored_text += 1
                debug.append(
                    EntityDebugInfo(
                        role,
                        layer,
                        entity.dxftype(),
                        handle,
                        "preview_only" if role == "auxiliary" else "ignored",
                        "info",
                        detail=(
                            "文字僅保留於輔助底稿預覽，不參與構件辨識。"
                            if role == "auxiliary"
                            else "文字不參與構件辨識。"
                        ),
                    )
                )
                continue
            self._extract_entity(entity, group, debug, source_geometry, handle)
            if group.primitives or entity.dxftype() in self.GEOMETRY_TYPES:
                groups.append(group)
        if ignored_text:
            debug.append(
                EntityDebugInfo(
                    role,
                    layer,
                    "TEXT_SUMMARY",
                    "",
                    "preview_only" if role == "auxiliary" else "ignored",
                    "info",
                    detail=(
                        f"共保留 {ignored_text} 個頂層文字供輔助底稿預覽。"
                        if role == "auxiliary"
                        else f"共略過 {ignored_text} 個 DXF 文字圖元。"
                    ),
                )
            )
        return groups

    def _extract_entity(
        self,
        entity: Any,
        group: _GeometryGroup,
        debug: list[EntityDebugInfo],
        source_geometry: list[SourceGeometry],
        root_handle: str,
        block_name: str = "",
    ) -> None:
        entity_type = entity.dxftype()
        group.handles.add(root_handle)
        if entity_type in self.TEXT_TYPES:
            debug.append(
                EntityDebugInfo(
                    group.role,
                    group.layer,
                    entity_type,
                    root_handle,
                    "preview_only" if group.role == "auxiliary" else "ignored",
                    "info",
                    block_instance=block_name,
                    detail=(
                        "文字僅保留於輔助底稿預覽，不參與構件辨識。"
                        if group.role == "auxiliary"
                        else "文字不參與構件辨識。"
                    ),
                )
            )
            return
        group.entity_types.add(entity_type)
        try:
            if entity_type == "INSERT":
                info = BlockInstanceInfo(
                    root_handle,
                    str(entity.dxf.name),
                    _point(entity.dxf.insert),
                    float(entity.dxf.rotation),
                    float(entity.dxf.xscale),
                    float(entity.dxf.yscale),
                )
                group.block_instances.append(info)
                debug.append(EntityDebugInfo(group.role, group.layer, entity_type, root_handle, "expanded", "info", block_instance=info.block_name, detail="virtual_entities 已套用 insertion/rotation/scale 完整座標轉換。"))
                for child in entity.virtual_entities():
                    self._extract_entity(child, group, debug, source_geometry, root_handle, info.block_name)
                return
            points: list[Point]
            closed = False
            source_width = 0.0
            if entity_type == "LINE":
                points = [_point(entity.dxf.start), _point(entity.dxf.end)]
            elif entity_type == "LWPOLYLINE":
                points = [(float(x), float(y)) for x, y in entity.get_points("xy")]
                closed = bool(entity.closed)
            elif entity_type == "POLYLINE":
                points = [_point(vertex.dxf.location) for vertex in entity.vertices]
                closed = bool(entity.is_closed)
            elif entity_type == "MLINE":
                points, source_width = _mline_center_path(entity)
                is_closed = getattr(entity, "is_closed", False)
                closed = bool(is_closed() if callable(is_closed) else is_closed)
            elif entity_type in {"SOLID", "TRACE"}:
                points = [_point(getattr(entity.dxf, f"vtx{index}")) for index in range(4)]
                closed = True
            else:
                debug.append(EntityDebugInfo(group.role, group.layer, entity_type, root_handle, "unsupported", "info", block_instance=block_name, detail="非直線工程幾何，已略過。"))
                return
            if len(points) > 2 and _same_point(points[0], points[-1], 1e-6):
                points.pop()
                closed = True
            primitive = _Primitive(
                points,
                closed,
                entity_type,
                root_handle,
                source_width,
            )
            group.primitives.append(primitive)
            if entity_type == "MLINE":
                # Recognition uses the computed ordered centre path, while the
                # gray DXF underlay should still look like the original MLINE
                # rails/end caps shown in CAD.
                virtual_count = 0
                for child in entity.virtual_entities():
                    if child.dxftype() != "LINE":
                        continue
                    source_geometry.append(
                        SourceGeometry(
                            group.role,
                            root_handle,
                            (
                                _point(child.dxf.start),
                                _point(child.dxf.end),
                            ),
                            False,
                            group.layer,
                            "MLINE",
                        )
                    )
                    virtual_count += 1
                if not virtual_count:
                    source_geometry.append(
                        SourceGeometry(
                            group.role,
                            root_handle,
                            tuple(points),
                            closed,
                            group.layer,
                            entity_type,
                        )
                    )
            else:
                source_geometry.append(
                    SourceGeometry(
                        group.role,
                        root_handle,
                        tuple(points),
                        closed,
                        group.layer,
                        entity_type,
                    )
                )
            debug.append(
                EntityDebugInfo(
                    group.role,
                    group.layer,
                    entity_type,
                    root_handle,
                    "read",
                    "info",
                    block_instance=block_name,
                    detail=(
                        f"已由 MLINE 外緣計算構件中線；寬度約 {source_width:.3f}。"
                        if entity_type == "MLINE"
                        else ""
                    ),
                )
            )
        except Exception as exc:
            debug.append(EntityDebugInfo(group.role, group.layer, entity_type, root_handle, "error", "error", block_instance=block_name, detail=str(exc)))

    @staticmethod
    def _merge_related_line_groups(
        groups: Sequence[_GeometryGroup],
        tolerances: GeometryTolerances,
    ) -> list[_GeometryGroup]:
        line_groups = [group for group in groups if len(group.primitives) == 1 and group.primitives[0].entity_type == "LINE"]
        others = [group for group in groups if group not in line_groups]
        unseen = set(range(len(line_groups)))
        while unseen:
            seed = unseen.pop()
            component = {seed}
            queue = [seed]
            while queue:
                current = queue.pop()
                current_line = line_groups[current].primitives[0].segments()[0]
                related = []
                for candidate in list(unseen):
                    candidate_line = line_groups[candidate].primitives[0].segments()[0]
                    endpoints_touch = any(
                        _same_point(a, b, tolerances.endpoint_tolerance_mm)
                        for a in current_line
                        for b in candidate_line
                    )
                    # Separate parallel LINE entities may already be valid
                    # engineering centrelines.  Merge them only when endpoint
                    # connectivity supplies the missing outline/end-cap
                    # evidence; INSERT children are already in one group.
                    if endpoints_touch:
                        related.append(candidate)
                for candidate in related:
                    unseen.remove(candidate)
                    component.add(candidate)
                    queue.append(candidate)
            if len(component) == 1:
                others.append(line_groups[seed])
                continue
            merged_groups = [line_groups[index] for index in component]
            merged = _GeometryGroup(
                "+".join(sorted(group.key for group in merged_groups)),
                merged_groups[0].role,
                merged_groups[0].layer,
                [primitive for group in merged_groups for primitive in group.primitives],
                set().union(*(group.handles for group in merged_groups)),
                set().union(*(group.entity_types for group in merged_groups)),
                [instance for group in merged_groups for instance in group.block_instances],
            )
            others.append(merged)
        return others

    @staticmethod
    def _validate_one_model_per_source(
        candidates_by_role: Mapping[str, Sequence[_Candidate]],
        messages: list[ValidationMessage],
    ) -> None:
        for role, candidates in candidates_by_role.items():
            owners: dict[str, list[_Candidate]] = defaultdict(list)
            for candidate in candidates:
                for handle in candidate.handles:
                    owners[handle].append(candidate)
            for handle, source_candidates in owners.items():
                count = len(source_candidates)
                if count <= 1:
                    continue
                if role == "corner_brace" and all(
                    candidate.recognition_method
                    in {
                        "connection_plate_midpoints",
                        "connection_face_midpoints",
                        "brace_centerline_intersections",
                    }
                    for candidate in source_candidates
                ):
                    # A fabrication INSERT legitimately contains the left and
                    # right corner braces around one Strut.
                    continue
                messages.append(
                    ValidationMessage(
                        "critical",
                        "MULTIPLE_MODELS_FROM_ONE_SOURCE",
                        f"來源 {handle} 產生 {count} 個工程模型。",
                        role,
                        (handle,),
                    )
                )

    @staticmethod
    def _make_waler(index: int, candidate: _Candidate) -> Waler:
        line_candidates = _engineering_line_candidates("waler", candidate)
        return Waler(
            f"W{index}", candidate.start, candidate.end, candidate.layer,
            tuple(sorted(candidate.handles)), tuple(sorted(candidate.entity_types)),
            candidate.recognition_method, candidate.centerline_computed,
            candidate.source_width, candidate.confidence,
            tuple(dict.fromkeys(candidate.warnings)), tuple(candidate.block_instances),
            line_candidates=line_candidates,
            selected_candidate_id=line_candidates[0].id,
        )

    @staticmethod
    def _make_strut(index: int, candidate: _Candidate) -> Strut:
        line_candidates = _engineering_line_candidates("strut", candidate)
        return Strut(
            f"S{index}", candidate.start, candidate.end, candidate.layer,
            tuple(sorted(candidate.handles)), tuple(sorted(candidate.entity_types)),
            candidate.recognition_method, candidate.centerline_computed,
            candidate.source_width, "", "", candidate.confidence,
            tuple(dict.fromkeys(candidate.warnings)), tuple(candidate.block_instances),
            line_candidates=line_candidates,
            selected_candidate_id=line_candidates[0].id,
        )

    @staticmethod
    def _make_brace(index: int, candidate: _Candidate) -> Brace:
        line_candidates = _engineering_line_candidates("brace", candidate)
        return Brace(
            f"B{index}", candidate.start, candidate.end, candidate.layer,
            tuple(sorted(candidate.handles)), tuple(sorted(candidate.entity_types)),
            candidate.recognition_method, candidate.centerline_computed,
            candidate.source_width, "", "", candidate.confidence,
            tuple(dict.fromkeys(candidate.warnings)), tuple(candidate.block_instances),
            line_candidates=line_candidates,
            selected_candidate_id=line_candidates[0].id,
        )

    @staticmethod
    def _make_auxiliary(
        component_type: type[AuxiliaryComponent],
        prefix: str,
        role: str,
        index: int,
        candidate: _Candidate,
    ) -> AuxiliaryComponent:
        line_candidates = _engineering_line_candidates(role, candidate)
        reference_point = candidate.reference_point or _midpoint(
            candidate.start,
            candidate.end,
        )
        beam_path_changes: dict[str, Any] = {}
        if issubclass(component_type, Beam):
            world_path = candidate.path_points or (
                candidate.start,
                candidate.end,
            )
            beam_path_changes = {
                "world_path": tuple(world_path),
                "local_path": tuple(world_path),
                "path": tuple(world_path),
            }
        return component_type(
            f"{prefix}{index}",
            candidate.start,
            candidate.end,
            candidate.layer,
            tuple(sorted(candidate.handles)),
            tuple(sorted(candidate.entity_types)),
            candidate.recognition_method,
            candidate.centerline_computed,
            candidate.source_width,
            candidate.confidence,
            tuple(dict.fromkeys(candidate.warnings)),
            tuple(candidate.block_instances),
            line_candidates=line_candidates,
            selected_candidate_id=line_candidates[0].id,
            reference_point=reference_point,
            world_reference_point=reference_point,
            local_reference_point=reference_point,
            **beam_path_changes,
        )

    @staticmethod
    def _finalize_debug(
        debug: Sequence[EntityDebugInfo],
        members: Sequence[Waler | Strut | Brace | AuxiliaryComponent],
    ) -> tuple[EntityDebugInfo, ...]:
        outputs: dict[tuple[str, str], list[str]] = defaultdict(list)
        for member in members:
            if isinstance(member, Waler):
                role = "waler"
            elif isinstance(member, Strut):
                role = "strut"
            elif isinstance(member, Brace):
                role = "brace"
            elif isinstance(member, Column):
                role = "column"
            elif isinstance(member, Beam):
                role = "beam"
            else:
                role = "corner_brace"
            for handle in member.source_handles:
                outputs[(role, handle)].append(member.id)
        result = []
        for item in debug:
            ids = tuple(dict.fromkeys(outputs.get((item.role, item.handle), ())))
            status = "converted" if ids and item.status in {"read", "expanded"} else item.status
            result.append(replace(item, status=status, output_ids=ids))
        return tuple(result)


def read_dxf_layers(file_path: str | Path) -> list[str]:
    return list(DXFImporter(file_path).read().layer_names)


def import_dxf(
    file_path: str | Path,
    *,
    strut_layer: str | None = None,
    waler_layer: str | None = None,
    brace_layer: str | None = None,
    layer_roles: Mapping[str, str] | None = None,
    endpoint_tolerance: float | None = None,
    tolerances: GeometryTolerances | None = None,
    coordinate_system: CoordinateSystem | None = None,
) -> DXFImportResult:
    return DXFImporter(file_path, tolerances=tolerances).read().convert(
        strut_layer=strut_layer,
        waler_layer=waler_layer,
        brace_layer=brace_layer,
        layer_roles=layer_roles,
        endpoint_tolerance=endpoint_tolerance,
        coordinate_system=coordinate_system,
    )


# TODO: 測試用預設圖層對應，正式版可改為專案設定或使用者自訂規則。
DEFAULT_LAYER_MAPPING = {
    "ES-圍令L1H350x350": "圍令",
    "ES-LH350x350": "支撐",
    "ES-大斜撐_支撐350x350": "斜撐",
    "!T1 (站體)_角撐": "角撐",
    "ES-中間樁NO": "中間柱",
    "ES-C250x90": "托梁",
    "DIM-軸線U": "輔助線",
    "DIM-軸線X": "輔助線",
}


class DXFImportDialog:
    """Engineer-oriented import summary, issue list, location and preview UI."""

    @property
    def preview_view_bounds(self) -> tuple[float, float, float, float] | None:
        viewport = getattr(self, "preview_viewport", None)
        return None if viewport is None else viewport.view_bounds

    @preview_view_bounds.setter
    def preview_view_bounds(
        self,
        bounds: tuple[float, float, float, float] | None,
    ) -> None:
        viewport = getattr(self, "preview_viewport", None)
        if viewport is not None:
            viewport.set_view_bounds(bounds)

    LAYER_USE_OPTIONS = (
        "圍令",
        "支撐",
        "斜撐",
        "中間柱",
        "托梁",
        "角撐",
        "輔助線",
        "忽略",
    )
    USE_TO_ROLE = {
        "圍令": "waler",
        "支撐": "strut",
        "斜撐": "brace",
        "中間柱": "column",
        "托梁": "beam",
        "角撐": "corner_brace",
        "輔助線": "auxiliary",
        "忽略": "ignore",
    }
    ROLE_TO_USE = {role: label for label, role in USE_TO_ROLE.items()}
    LEVEL_COLORS = {
        "success": "#2e7d32",
        "info": "#1565c0",
        "warning": "#9a6700",
        "error": "#c62828",
        "critical": "#8e0000",
    }
    LEVEL_ICONS = {"success": "✓", "info": "ℹ", "warning": "⚠", "error": "✗", "critical": "✗"}

    @property
    def selected_member_id(self) -> str:
        return self.selection_state.selected_component_id

    @classmethod
    def _initial_layer_use(
        cls,
        layer: str,
        saved_classification: Mapping[str, Any],
    ) -> str:
        if layer in saved_classification:
            saved_role = str(saved_classification[layer])
            return cls.ROLE_TO_USE.get(saved_role, "忽略")
        return DEFAULT_LAYER_MAPPING.get(layer, "忽略")

    @staticmethod
    def _ui_state_path() -> Path:
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        return base / "SupportDistributionUV" / "dxf_import_ui_state.json"

    @classmethod
    def _load_ui_state(cls) -> dict[str, Any]:
        try:
            payload = json.loads(cls._ui_state_path().read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _restore_visible_geometry(
        window: Any,
        requested: str,
        fallback: str,
    ) -> str:
        geometry = fit_window_geometry_to_work_areas(
            requested,
            fallback,
            _active_monitor_work_areas(window),
        )
        try:
            window.geometry(geometry)
            return geometry
        except Exception:
            window.geometry(fallback)
            return fallback

    def __init__(
        self,
        parent: Any,
        file_path: str | Path,
        initial_state: Mapping[str, Any] | None = None,
        cad_event_watcher: Any = None,
    ):
        import tkinter as tk
        from tkinter import scrolledtext, ttk

        from cad_builder import DEFAULT_TEMP_PATH, TempEventWatcher

        self.tk = tk
        self.ttk = ttk
        self.file_path = Path(file_path)
        self.initial_state = dict(initial_state or {})
        self.ui_state = self._load_ui_state()
        self.cad_event_watcher = cad_event_watcher or TempEventWatcher(
            DEFAULT_TEMP_PATH
        )
        self.importer = DXFImporter(file_path).read()
        self.result: DXFImportResult | None = None
        self.world_result: DXFImportResult | None = None
        self.coordinate_valid = False
        self.selected_origin_world: Point | None = None
        self.import_mode = "replace"
        self.problem_records: tuple[ProblemRecord, ...] = ()
        self.problem_record_by_iid: dict[str, ProblemRecord] = {}
        self.selected_problem: ProblemRecord | None = None
        self.focus_member_ids: set[str] = set()
        self.focus_handles: set[str] = set()
        self.selection_state = SelectionState()
        self.member_by_tree_iid: dict[str, str] = {}
        self._updating_member_tree = False
        self.preview_viewport = CADViewport()
        self.preview_view_bounds: tuple[float, float, float, float] | None = None
        self.preview_fit_all = True
        self.preview_interaction = PreviewController()
        self.preview_transform: tuple[float, float, float, float, float] | None = None
        self.canvas_member_hit_lines: list[
            tuple[str, tuple[float, float], tuple[float, float]]
        ] = []
        self.canvas_candidate_hit_points: list[tuple[str, Point]] = []
        self.preview_scene = PreviewScene()
        self.preview_renderer: PreviewRenderer | None = None
        self.preview_window: Any = None
        self._last_normal_geometry = str(
            self.ui_state.get("main_geometry", "1180x930")
        )
        self._last_preview_geometry = str(
            self.ui_state.get("preview_geometry", "1100x800+80+80")
        )
        self.developer_expanded = False
        self.preview_cursor_var = tk.StringVar(value="游標：—")
        self.preview_coordinate_var = tk.StringVar(value="Coordinate System：尚未套用")
        self.preview_selected_member_var = tk.StringVar(value="目前構件：—")
        self.show_source_var = tk.BooleanVar(
            value=bool(self.ui_state.get("show_source", True))
        )
        self.show_auxiliary_var = tk.BooleanVar(
            value=bool(self.ui_state.get("show_auxiliary", True))
        )
        self.performance_diagnostics_enabled_var = tk.BooleanVar(
            value=bool(self.ui_state.get("performance_diagnostics", False))
        )
        self.performance_diagnostics_var = tk.StringVar(value="效能診斷：未啟用")
        self.cad_temp_status_var = tk.StringVar(value="請先選取構件，再由 CAD 指定工程線。")

        self.window = tk.Toplevel(parent)
        self.window.title("DXF 匯入與工程模型檢核")
        self._last_normal_geometry = self._restore_visible_geometry(
            self.window,
            self._last_normal_geometry,
            "1180x930",
        )
        self.window.minsize(920, 680)
        self.window.resizable(True, True)
        self.window.protocol("WM_DELETE_WINDOW", self._cancel)
        self.window.bind("<Configure>", self._on_main_window_configure)
        self.window.bind("<Escape>", self._cancel_active_pick)
        self.performance_diagnostics = PerformanceDiagnostics()
        self.candidate_point_store = CandidatePointStore(
            min(
                self.importer.tolerances.duplicate_tolerance_mm,
                self.importer.tolerances.endpoint_tolerance_mm,
                1.0,
            )
        )
        self.render_scheduler = RenderScheduler(
            self.window.after_idle,
            self._flush_render_updates,
            self.performance_diagnostics,
        )
        self.selection_controller = SelectionController(
            self.selection_state,
            self.candidate_point_store,
            self._member_by_id,
            self.render_scheduler.request,
            self.performance_diagnostics,
        )
        self.import_model_controller = ImportModelController(
            self.importer.tolerances,
            self.candidate_point_store,
        )

        self.form_scroll_host = ttk.Frame(self.window)
        form_background = ttk.Style(self.window).lookup("TFrame", "background")
        self.form_canvas = tk.Canvas(
            self.form_scroll_host,
            background=form_background or self.window.cget("background"),
            borderwidth=0,
            highlightthickness=0,
            yscrollincrement=24,
        )
        self.form_scrollbar = ttk.Scrollbar(
            self.form_scroll_host,
            orient="vertical",
            command=self.form_canvas.yview,
        )
        self.form_canvas.configure(yscrollcommand=self.form_scrollbar.set)
        self.form_canvas.pack(side="left", fill="both", expand=True)
        self.form_scrollbar.pack(side="right", fill="y")
        self.form_content = ttk.Frame(self.form_canvas)
        self.form_content_window = self.form_canvas.create_window(
            (0, 0),
            window=self.form_content,
            anchor="nw",
        )
        self.form_content.bind("<Configure>", self._update_form_scrollregion)
        self.form_canvas.bind("<Configure>", self._resize_form_content)
        self.window.bind("<MouseWheel>", self._on_form_mousewheel, add="+")
        self.window.bind("<Button-4>", self._on_form_mousewheel, add="+")
        self.window.bind("<Button-5>", self._on_form_mousewheel, add="+")

        controls = ttk.LabelFrame(
            self.form_content,
            text=f"STEP1 圖層用途分類 — {self.file_path.name}",
        )
        controls.pack(fill="x", padx=10, pady=10)
        ttk.Label(
            controls,
            text="測試圖層可能預填用途；使用者可自由修改，辨識時以目前選擇為準。",
            foreground="#37474f",
        ).pack(anchor="w", padx=8, pady=(6, 3))
        classification_body = ttk.Frame(controls)
        classification_body.pack(fill="x", padx=8, pady=(0, 5))
        classification_header = ttk.Frame(classification_body)
        classification_header.pack(fill="x", padx=(0, 16))
        ttk.Label(
            classification_header,
            text="圖層名稱",
            font=("Microsoft JhengHei", 9, "bold"),
        ).grid(row=0, column=0, padx=8, pady=4, sticky="w")
        ttk.Label(
            classification_header,
            text="DXF 圖元數量",
            font=("Microsoft JhengHei", 9, "bold"),
        ).grid(row=0, column=1, padx=8, pady=4, sticky="e")
        ttk.Label(
            classification_header,
            text="用途",
            font=("Microsoft JhengHei", 9, "bold"),
        ).grid(row=0, column=2, padx=8, pady=4, sticky="w")
        classification_header.columnconfigure(0, weight=1)
        classification_header.columnconfigure(1, minsize=120)
        classification_header.columnconfigure(2, minsize=150)

        classification_list = ttk.Frame(classification_body)
        classification_list.pack(fill="x", expand=True)
        classification_canvas = tk.Canvas(
            classification_list,
            height=245,
            highlightthickness=1,
            highlightbackground="#b0bec5",
            yscrollincrement=24,
        )
        self.classification_canvas = classification_canvas
        classification_scroll = ttk.Scrollbar(
            classification_list,
            orient="vertical",
            command=classification_canvas.yview,
        )
        classification_canvas.configure(yscrollcommand=classification_scroll.set)
        classification_canvas.pack(side="left", fill="x", expand=True)
        classification_scroll.pack(side="right", fill="y")
        classification_rows = ttk.Frame(classification_canvas)
        classification_window = classification_canvas.create_window(
            (0, 0),
            window=classification_rows,
            anchor="nw",
        )
        classification_rows.bind(
            "<Configure>",
            lambda _event: classification_canvas.configure(
                scrollregion=classification_canvas.bbox("all")
            ),
        )
        classification_canvas.bind(
            "<Configure>",
            lambda event: classification_canvas.itemconfigure(
                classification_window,
                width=event.width,
            ),
        )
        saved_classification = self.initial_state.get("layer_classification", {})
        if not isinstance(saved_classification, Mapping):
            saved_classification = {}
        if not saved_classification:
            assignments = self.initial_state.get("layer_assignments", ())
            if isinstance(assignments, Sequence) and not isinstance(
                assignments,
                (str, bytes),
            ):
                saved_classification = {
                    str(item.get("layer_name")): str(item.get("layer_type"))
                    for item in assignments
                    if isinstance(item, Mapping) and item.get("layer_name")
                }
        layer_counts = {
            item.name: item.entity_count for item in self.importer.layer_information()
        }
        self.layer_use_vars: dict[str, Any] = {}
        names = self.importer.layer_names
        for row, layer in enumerate(names):
            ttk.Label(classification_rows, text=layer).grid(
                row=row,
                column=0,
                padx=8,
                pady=2,
                sticky="w",
            )
            ttk.Label(
                classification_rows,
                text=str(layer_counts.get(layer, 0)),
            ).grid(row=row, column=1, padx=8, pady=2, sticky="e")
            variable = tk.StringVar(
                value=self._initial_layer_use(layer, saved_classification)
            )
            combo = ttk.Combobox(
                classification_rows,
                textvariable=variable,
                values=self.LAYER_USE_OPTIONS,
                state="readonly",
                width=14,
            )
            combo.grid(row=row, column=2, padx=8, pady=2, sticky="w")
            self.layer_use_vars[layer] = variable
        classification_rows.columnconfigure(0, weight=1)
        classification_rows.columnconfigure(1, minsize=120)
        classification_rows.columnconfigure(2, minsize=150)

        action_row = ttk.Frame(controls)
        action_row.pack(fill="x", padx=8, pady=(0, 7))
        self.mode_var = tk.StringVar(value="replace")
        ttk.Radiobutton(action_row, text="取代目前工程模型", variable=self.mode_var, value="replace").pack(side="left")
        ttk.Radiobutton(action_row, text="附加到目前工程模型", variable=self.mode_var, value="append").pack(side="left", padx=12)
        self.recognize_button = ttk.Button(
            action_row,
            text="完成分類並開始辨識／重新辨識",
            command=self._convert_preview,
        )
        self.recognize_button.pack(side="right")

        self._build_coordinate_system_settings(self.form_content)

        review_frame = ttk.Frame(self.form_content)
        review_frame.pack(fill="x", padx=10, pady=(0, 8))
        self._build_engineering_review(review_frame)

        diagnostics_frame = ttk.LabelFrame(
            self.form_content,
            text="STEP7 匯入檢核結果",
        )
        diagnostics_frame.pack(fill="x", padx=10, pady=(0, 10))
        self._build_diagnostics_tab(diagnostics_frame, scrolledtext)

        footer = ttk.Frame(self.window)
        footer.pack(side="bottom", fill="x", padx=10, pady=10)
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(footer, textvariable=self.status_var)
        self.status_label.pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="取消", command=self._cancel).pack(side="right", padx=(6, 0))
        self.apply_button = ttk.Button(footer, text="STEP8 匯入工程模型", command=self._apply)
        self.apply_button.pack(side="right")
        self.apply_button.configure(state="disabled", text="不可匯入")
        self.status_var.set("請先完成圖層用途分類，再按下「開始辨識」。")
        self.form_scroll_host.pack(fill="both", expand=True)
        if bool(self.ui_state.get("main_maximized", False)):
            self.window.after_idle(lambda: self._set_maximized(True))
        self.window.after_idle(self._open_preview_window)

    def _is_maximized(self) -> bool:
        try:
            return self.window.state() == "zoomed"
        except self.tk.TclError:
            try:
                return bool(self.window.attributes("-zoomed"))
            except self.tk.TclError:
                return False

    def _set_maximized(self, maximized: bool) -> None:
        try:
            self.window.state("zoomed" if maximized else "normal")
        except self.tk.TclError:
            try:
                self.window.attributes("-zoomed", maximized)
            except self.tk.TclError:
                return

    def _update_form_scrollregion(self, _event: Any = None) -> None:
        bounds = self.form_canvas.bbox("all")
        if bounds is not None:
            self.form_canvas.configure(scrollregion=bounds)

    def _resize_form_content(self, event: Any) -> None:
        self.form_canvas.itemconfigure(
            self.form_content_window,
            width=max(int(event.width), 1),
        )

    @staticmethod
    def _form_wheel_units(event: Any) -> int:
        button = getattr(event, "num", None)
        if button == 4:
            return -1
        if button == 5:
            return 1
        delta = float(getattr(event, "delta", 0) or 0)
        if delta == 0:
            return 0
        return -1 if delta > 0 else 1

    @staticmethod
    def _widget_can_scroll(widget: Any, units: int) -> bool:
        try:
            first, last = widget.yview()
        except Exception:
            return False
        if units < 0:
            return float(first) > 1e-9
        return float(last) < 1.0 - 1e-9

    @staticmethod
    def _widget_is_descendant(widget: Any, ancestor: Any) -> bool:
        current = widget
        while current is not None:
            if current is ancestor:
                return True
            current = getattr(current, "master", None)
        return False

    def _on_form_mousewheel(self, event: Any) -> str | None:
        units = self._form_wheel_units(event)
        if units == 0:
            return None

        widget = getattr(event, "widget", None)
        if widget is not None and widget is not self.form_canvas:
            classification_canvas = getattr(self, "classification_canvas", None)
            if (
                classification_canvas is not None
                and self._widget_is_descendant(widget, classification_canvas)
            ):
                if self._widget_can_scroll(classification_canvas, units):
                    classification_canvas.yview_scroll(units, "units")
                    return "break"
                # At the top or bottom, fall through to the page canvas.
            try:
                widget_class = str(widget.winfo_class())
            except Exception:
                widget_class = ""
            if widget_class in {"Treeview", "Text", "Listbox"}:
                return None
            if widget_class == "Canvas":
                if self._widget_can_scroll(widget, units):
                    widget.yview_scroll(units, "units")
                    return "break"
                # The inner list reached its boundary; continue with the
                # STEP1–STEP7 page instead of trapping the mouse wheel.

        if not self._widget_can_scroll(self.form_canvas, units):
            return None
        self.form_canvas.yview_scroll(units, "units")
        return "break"

    def _on_main_window_configure(self, event: Any) -> None:
        if event.widget is not self.window:
            return
        maximized = self._is_maximized()
        if not maximized:
            geometry = self.window.geometry()
            if geometry:
                self._last_normal_geometry = geometry

    def _save_ui_state(self) -> None:
        if self.preview_window is not None:
            try:
                self._last_preview_geometry = self.preview_window.geometry()
            except self.tk.TclError:
                pass
        payload = {
            "main_geometry": self._last_normal_geometry,
            "main_maximized": self._is_maximized(),
            "preview_geometry": self._last_preview_geometry,
            "show_source": bool(self.show_source_var.get()),
            "show_auxiliary": bool(self.show_auxiliary_var.get()),
            "performance_diagnostics": bool(
                self.performance_diagnostics_enabled_var.get()
            ),
        }
        try:
            path = self._ui_state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _build_engineering_review(self, parent: Any) -> None:
        body = self.ttk.Panedwindow(parent, orient="horizontal")

        member_frame = self.ttk.LabelFrame(body, text="STEP3 構件清單")
        self.member_tree = self.ttk.Treeview(
            member_frame,
            show="tree",
            selectmode="browse",
            height=20,
        )
        member_scroll = self.ttk.Scrollbar(
            member_frame,
            orient="vertical",
            command=self.member_tree.yview,
        )
        self.member_tree.configure(yscrollcommand=member_scroll.set)
        self.member_tree.pack(side="left", fill="both", expand=True)
        member_scroll.pack(side="right", fill="y")
        self.member_tree.bind("<<TreeviewSelect>>", self._on_member_selected)
        self.member_tree_selection = TreeSelectionSynchronizer(
            self.member_tree,
            self.window.after_idle,
        )

        detail_frame = self.ttk.LabelFrame(body, text="STEP4 人工確認與修正")
        self.member_info_vars = {
            key: self.tk.StringVar(value="—")
            for key in (
                "id",
                "role",
                "layer",
                "entities",
                "method",
                "start_x",
                "start_y",
                "end_x",
                "end_y",
            )
        }
        info_rows = (
            ("構件編號", "id"),
            ("構件類型", "role"),
            ("來源圖層", "layer"),
            ("來源 DXF 圖元", "entities"),
            ("辨識方法", "method"),
            ("StartX", "start_x"),
            ("StartY", "start_y"),
            ("EndX", "end_x"),
            ("EndY", "end_y"),
        )
        for row, (label, key) in enumerate(info_rows):
            self.ttk.Label(detail_frame, text=f"{label}：").grid(
                row=row,
                column=0,
                padx=(8, 4),
                pady=2,
                sticky="ne",
            )
            self.ttk.Label(
                detail_frame,
                textvariable=self.member_info_vars[key],
                wraplength=300,
                justify="left",
            ).grid(row=row, column=1, padx=(0, 8), pady=2, sticky="nw")

        detail_frame.columnconfigure(1, weight=1)

        candidate_frame = self.ttk.LabelFrame(
            body,
            text="STEP5 候選點（確認後才套用）",
        )
        self.candidate_filter_var = self.tk.StringVar(value="all")
        self.candidate_action_status_var = self.tk.StringVar(
            value="請先選取構件；單擊候選點只會預覽。"
        )
        self.candidate_detail_var = self.tk.StringVar(value="候選點：—")
        filter_row = self.ttk.Frame(candidate_frame)
        filter_row.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(6, 2),
        )
        for text, value in (
            ("全部", "all"),
            ("起點", "start"),
            ("終點", "end"),
            ("推薦", "recommended"),
        ):
            self.ttk.Radiobutton(
                filter_row,
                text=text,
                variable=self.candidate_filter_var,
                value=value,
                command=self._on_candidate_filter_changed,
            ).pack(side="left", padx=(0, 5))
        self.candidate_tree = self.ttk.Treeview(
            candidate_frame,
            columns=("id", "type", "world", "local", "status"),
            show="headings",
            selectmode="browse",
            height=11,
        )
        for column, text in (
            ("id", "點"),
            ("type", "用途／類型"),
            ("world", "World X, Y"),
            ("local", "Local X, Y"),
            ("status", "狀態"),
        ):
            self.candidate_tree.heading(column, text=text)
        self.candidate_tree.column("id", width=54, anchor="center", stretch=False)
        self.candidate_tree.column("type", width=185, anchor="w")
        self.candidate_tree.column("world", width=165, anchor="e")
        self.candidate_tree.column("local", width=155, anchor="e")
        self.candidate_tree.column("status", width=180, anchor="w")
        candidate_scroll = self.ttk.Scrollbar(
            candidate_frame,
            orient="vertical",
            command=self.candidate_tree.yview,
        )
        self.candidate_tree.configure(yscrollcommand=candidate_scroll.set)
        self.candidate_tree.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(8, 0),
            pady=(6, 5),
        )
        candidate_scroll.grid(
            row=1,
            column=1,
            sticky="ns",
            padx=(0, 6),
            pady=(6, 5),
        )
        self.candidate_tree.bind("<<TreeviewSelect>>", self._on_candidate_point_selected)
        self.candidate_tree.bind("<Motion>", self._on_candidate_hover)
        self.candidate_tree.bind("<Leave>", self._clear_candidate_hover)
        self.candidate_tree_adapter = CandidateTreeAdapter(
            self.candidate_tree,
            self.window.after_idle,
        )
        self.ttk.Label(
            candidate_frame,
            textvariable=self.candidate_detail_var,
            foreground="#607d8b",
            wraplength=680,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 4))
        pick_buttons = self.ttk.Frame(candidate_frame)
        pick_buttons.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=2)
        self.ttk.Button(
            pick_buttons,
            text="重新選擇起點",
            command=lambda: self._begin_candidate_pick("pick_start"),
        ).pack(side="left", padx=(0, 4))
        self.ttk.Button(
            pick_buttons,
            text="重新選擇終點",
            command=lambda: self._begin_candidate_pick("pick_end"),
        ).pack(side="left", padx=4)
        self.ttk.Button(
            pick_buttons,
            text="交換起終點",
            command=self._swap_pending_points,
        ).pack(side="left", padx=4)
        commit_buttons = self.ttk.Frame(candidate_frame)
        commit_buttons.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=2)
        self.ttk.Button(
            commit_buttons,
            text="恢復系統推薦",
            command=self._restore_recommended_points,
        ).pack(side="left", padx=(0, 4))
        self.ttk.Button(
            commit_buttons,
            text="取消修改",
            command=self._cancel_candidate_changes,
        ).pack(side="left", padx=4)
        self.ttk.Button(
            commit_buttons,
            text="套用修改",
            command=self._apply_candidate_changes,
        ).pack(side="right", padx=(4, 0))
        self.ttk.Label(
            candidate_frame,
            textvariable=self.candidate_action_status_var,
            foreground="#37474f",
            wraplength=680,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="ew", padx=8, pady=(2, 6))
        candidate_frame.rowconfigure(1, weight=1)
        candidate_frame.columnconfigure(0, weight=1)

        # Candidate picking is now primarily graphical in the independent
        # preview. Keep this table as a compact precision/overlap fallback.
        candidate_frame.configure(text="STEP5 候選點明細（精確選擇／備援）")
        filter_row.grid_remove()
        pick_buttons.grid_remove()
        commit_buttons.grid_remove()
        for widget in candidate_frame.grid_slaves(row=5):
            widget.grid_remove()
        self.candidate_tree.configure(
            displaycolumns=("id", "type", "status"),
            height=9,
        )
        self.candidate_tree.column("type", width=205, anchor="w")
        self.candidate_tree.column("status", width=145, anchor="w")
        self.candidate_tree.grid_configure(row=0, pady=(6, 4))
        candidate_scroll.grid_configure(row=0, pady=(6, 4))
        for widget in candidate_frame.grid_slaves(row=2):
            widget.grid_configure(row=1, pady=(2, 6))
        origin_action = self.ttk.Frame(candidate_frame)
        origin_action.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(0, 7),
        )
        self.set_origin_button = self.ttk.Button(
            origin_action,
            text="以選定點設定局部原點",
            command=self._set_selected_point_as_origin,
            state="disabled",
        )
        self.set_origin_button.pack(side="left", padx=(0, 8))
        self.ttk.Label(
            origin_action,
            text="此按鈕只使用表格目前選定的候選點，不使用預覽窗格點選。",
            foreground="#455a64",
            wraplength=360,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        candidate_frame.rowconfigure(0, weight=1)
        candidate_frame.rowconfigure(1, weight=0)
        candidate_frame.rowconfigure(2, weight=0)

        body.add(member_frame, weight=1)
        body.add(detail_frame, weight=1)
        body.add(candidate_frame, weight=1)

        cad_frame = self.ttk.LabelFrame(parent, text="STEP6 從 CAD 重新指定工程線")
        cad_frame.pack(side="bottom", fill="x", padx=6, pady=(0, 6))
        self.ttk.Label(
            cad_frame,
            textvariable=self.cad_temp_status_var,
            foreground="#37474f",
        ).pack(side="left", fill="x", expand=True, padx=8, pady=6)
        self.ttk.Button(
            cad_frame,
            text="從 CAD 指定工程線",
            command=self._read_cad_engineering_line,
        ).pack(side="right", padx=8, pady=5)
        body.pack(fill="both", expand=True, padx=5, pady=5)

    def _create_preview_canvas(self, parent: Any) -> None:
        old_canvas = getattr(self, "canvas", None)
        if old_canvas is not None:
            try:
                if old_canvas.winfo_exists():
                    old_canvas.destroy()
            except self.tk.TclError:
                pass
        self.canvas = self.tk.Canvas(
            parent,
            background="white",
            highlightthickness=1,
            highlightbackground="#999",
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw_preview())
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind(
            "<Leave>",
            self._on_canvas_leave,
        )
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Escape>", self._cancel_active_pick)
        self.canvas.bind("<MouseWheel>", self._on_canvas_mousewheel)
        self.canvas.bind(
            "<Button-4>",
            lambda event: self._on_canvas_mousewheel(event, 1),
        )
        self.canvas.bind(
            "<Button-5>",
            lambda event: self._on_canvas_mousewheel(event, -1),
        )
        self.canvas.bind("<ButtonPress-2>", self._start_canvas_pan)
        self.canvas.bind("<B2-Motion>", self._drag_canvas_pan)
        self.canvas.bind("<ButtonRelease-2>", self._end_canvas_pan)
        self.canvas.bind("<Double-Button-2>", self._on_canvas_middle_double_click)
        self.canvas_member_hit_lines = []
        self.canvas_candidate_hit_points = []
        self.preview_transform = None
        self.preview_scene = PreviewScene()
        self.preview_renderer = PreviewRenderer(self.canvas, self.preview_scene)
        self._draw_preview()

    def _open_preview_window(self) -> None:
        if self.preview_window is not None:
            try:
                if self.preview_window.winfo_exists():
                    self._last_preview_geometry = self._restore_visible_geometry(
                        self.preview_window,
                        self._last_preview_geometry,
                        "1100x800+80+80",
                    )
                    self.preview_window.deiconify()
                    self.preview_window.lift()
                    return
            except self.tk.TclError:
                pass

        preview_window = self.tk.Toplevel(self.window)
        self.preview_window = preview_window
        preview_window.title(f"DXF 圖面預覽 — {self.file_path.name}")
        preview_window.minsize(640, 480)
        self._last_preview_geometry = self._restore_visible_geometry(
            preview_window,
            self._last_preview_geometry,
            "1100x800+80+80",
        )
        preview_window.protocol("WM_DELETE_WINDOW", self._hide_preview_window)
        preview_window.bind("<Configure>", self._on_preview_window_configure)
        preview_window.bind("<Escape>", self._cancel_active_pick)

        toolbar = self.ttk.Frame(preview_window)
        toolbar.pack(fill="x", padx=8, pady=6)
        self.ttk.Button(
            toolbar,
            text="定位至構件",
            command=self._locate_selected_member,
        ).pack(side="left")
        self.ttk.Checkbutton(
            toolbar,
            text="疊加原始外框",
            variable=self.show_source_var,
            command=self._update_source_layer_visibility,
        ).pack(side="left")
        self.ttk.Checkbutton(
            toolbar,
            text="顯示輔助線",
            variable=self.show_auxiliary_var,
            command=self._update_source_layer_visibility,
        ).pack(side="left", padx=(8, 0))
        self.ttk.Label(
            toolbar,
            textvariable=self.preview_cursor_var,
            foreground="#455a64",
        ).pack(side="right", padx=6)
        self.ttk.Label(
            toolbar,
            text="滾輪縮放｜中鍵平移｜雙擊中鍵顯示全部",
            foreground="#555555",
        ).pack(side="right", padx=12)
        review_toolbar = self.ttk.LabelFrame(
            preview_window,
            text="候選點與工程線修正",
        )
        review_toolbar.pack(fill="x", padx=8, pady=(0, 6))
        review_actions = self.ttk.Frame(review_toolbar)
        review_actions.pack(fill="x")
        self.ttk.Label(
            review_actions,
            textvariable=self.preview_selected_member_var,
            font=("Microsoft JhengHei", 10, "bold"),
        ).pack(side="left", padx=(8, 12), pady=5)
        self.ttk.Button(
            review_actions,
            text="選起點",
            command=lambda: self._begin_candidate_pick("pick_start"),
        ).pack(side="left", padx=3, pady=4)
        self.ttk.Button(
            review_actions,
            text="選終點",
            command=lambda: self._begin_candidate_pick("pick_end"),
        ).pack(side="left", padx=3, pady=4)
        self.ttk.Button(
            review_actions,
            text="交換",
            command=self._swap_pending_points,
        ).pack(side="left", padx=3, pady=4)
        self.ttk.Button(
            review_actions,
            text="恢復推薦",
            command=self._restore_recommended_points,
        ).pack(side="left", padx=(12, 3), pady=4)
        self.ttk.Button(
            review_actions,
            text="取消修改",
            command=self._cancel_candidate_changes,
        ).pack(side="left", padx=3, pady=4)
        self.ttk.Button(
            review_actions,
            text="套用修改",
            command=self._apply_candidate_changes,
        ).pack(side="left", padx=(12, 3), pady=4)

        preview_filter = self.ttk.Frame(review_toolbar)
        preview_filter.pack(fill="x", padx=8, pady=(0, 4))
        self.ttk.Label(preview_filter, text="候選點：").pack(side="left")
        for text, value in (
            ("全部", "all"),
            ("起點", "start"),
            ("終點", "end"),
            ("推薦", "recommended"),
        ):
            self.ttk.Radiobutton(
                preview_filter,
                text=text,
                variable=self.candidate_filter_var,
                value=value,
                command=self._on_candidate_filter_changed,
            ).pack(side="left", padx=2)

        # Keep the instruction on its own line so tool controls remain usable
        # on a single, narrower monitor.
        self.ttk.Label(
            preview_window,
            textvariable=self.candidate_action_status_var,
            foreground="#c62828",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 5))

        canvas_host = self.ttk.Frame(preview_window)
        canvas_host.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._create_preview_canvas(canvas_host)

    def _hide_preview_window(self) -> None:
        if self.preview_window is None:
            return
        try:
            self._last_preview_geometry = self.preview_window.geometry()
            self.preview_window.iconify()
        except self.tk.TclError:
            pass

    def _on_preview_window_configure(self, event: Any) -> None:
        if self.preview_window is None or event.widget is not self.preview_window:
            return
        try:
            self._last_preview_geometry = self.preview_window.geometry()
        except self.tk.TclError:
            pass

    def _build_coordinate_system_settings(self, parent: Any) -> None:
        frame = self.ttk.LabelFrame(parent, text="STEP2 座標系統狀態")
        frame.pack(fill="x", padx=10, pady=(0, 8))
        self.coordinate_mode_var = self.tk.StringVar(value="world")
        self.coordinate_error_var = self.tk.StringVar(value="")
        self.coordinate_info_var = self.tk.StringVar(value="")
        self.coordinate_example_var = self.tk.StringVar(value="")

        self.ttk.Button(
            frame,
            text="使用原始 CAD 座標",
            command=self._reset_coordinate_settings,
        ).grid(row=0, column=0, padx=8, pady=(7, 3), sticky="w")
        self.ttk.Label(
            frame,
            text="預設使用原始 CAD 座標。完成構件辨識後，可在 STEP5 候選點明細表格選取一點並設定為局部原點。",
            foreground="#455a64",
        ).grid(row=0, column=1, columnspan=4, padx=(12, 8), pady=(7, 3), sticky="w")

        self.tk.Label(frame, textvariable=self.coordinate_error_var, foreground="#c62828", anchor="w").grid(
            row=1, column=0, columnspan=2, padx=8, pady=(1, 5), sticky="w"
        )
        self.ttk.Label(frame, textvariable=self.coordinate_info_var).grid(
            row=1, column=2, columnspan=2, padx=8, pady=(1, 5), sticky="w"
        )
        self.ttk.Label(frame, textvariable=self.coordinate_example_var, foreground="#455a64").grid(
            row=1, column=4, padx=8, pady=(1, 5), sticky="e"
        )
        frame.columnconfigure(4, weight=1)

    def _build_diagnostics_tab(self, parent: Any, scrolledtext: Any) -> None:
        summary_frame = self.ttk.LabelFrame(parent, text="DXF 匯入摘要")
        summary_frame.pack(fill="x", padx=6, pady=(6, 3))
        self.summary_file_var = self.tk.StringVar()
        self.summary_totals_var = self.tk.StringVar()
        self.ttk.Label(summary_frame, textvariable=self.summary_file_var, font=("Microsoft JhengHei", 10, "bold")).pack(anchor="w", padx=8, pady=(5, 2))
        columns = ("role", "layer", "source", "recognized", "skipped")
        self.summary_tree = self.ttk.Treeview(summary_frame, columns=columns, show="headings", height=6)
        headings = {"role": "類別", "layer": "選定圖層", "source": "原始 DXF 圖元", "recognized": "辨識成功", "skipped": "略過"}
        widths = {"role": 75, "layer": 460, "source": 105, "recognized": 105, "skipped": 80}
        for column in columns:
            self.summary_tree.heading(column, text=headings[column])
            self.summary_tree.column(column, width=widths[column], anchor="center" if column != "layer" else "w")
        self.summary_tree.pack(fill="x", padx=8, pady=2)
        self.ttk.Label(summary_frame, textvariable=self.summary_totals_var).pack(anchor="w", padx=8, pady=(2, 5))

        validation_frame = self.ttk.LabelFrame(parent, text="驗證結果")
        validation_frame.pack(fill="x", padx=6, pady=3)
        self.validation_content = self.ttk.Frame(validation_frame)
        self.validation_content.pack(fill="x", padx=8, pady=5)

        problem_frame = self.ttk.LabelFrame(parent, text="錯誤與警告（點選後自動定位）")
        problem_frame.pack(fill="both", expand=True, padx=6, pady=3)
        filters = self.ttk.Frame(problem_frame)
        filters.pack(fill="x", padx=6, pady=4)
        self.problem_filter_var = self.tk.StringVar(value="all")
        for value, label in (("all", "全部"), ("error", "只看 Error"), ("warning", "只看 Warning")):
            self.ttk.Radiobutton(filters, text=label, variable=self.problem_filter_var, value=value, command=self._refresh_problem_tree).pack(side="left", padx=(0, 8))
        self.selected_only_var = self.tk.BooleanVar(value=False)
        self.ttk.Checkbutton(filters, text="只看選定構件", variable=self.selected_only_var, command=self._refresh_problem_tree).pack(side="left", padx=8)

        problem_container = self.ttk.Frame(problem_frame)
        problem_container.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        problem_container.rowconfigure(0, weight=1)
        problem_container.columnconfigure(0, weight=1)
        columns = ("severity", "code", "component", "description")
        self.problem_tree = self.ttk.Treeview(problem_container, columns=columns, show="headings", selectmode="browse", height=7)
        headings = {"severity": "等級", "code": "類型", "component": "構件／來源", "description": "說明"}
        widths = {"severity": 85, "code": 250, "component": 180, "description": 520}
        for column in columns:
            self.problem_tree.heading(column, text=headings[column])
            self.problem_tree.column(column, width=widths[column], anchor="w")
        self.problem_tree.tag_configure("critical", background="#ffcdd2", foreground="#8e0000")
        self.problem_tree.tag_configure("error", background="#ffebee", foreground="#b71c1c")
        self.problem_tree.tag_configure("warning", background="#fff8e1", foreground="#8d6e00")
        self.problem_tree.tag_configure("info", background="#e3f2fd", foreground="#0d47a1")
        self.problem_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = self.ttk.Scrollbar(problem_container, orient="vertical", command=self.problem_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.problem_tree.configure(yscrollcommand=scrollbar.set)
        self.problem_tree.bind("<<TreeviewSelect>>", self._on_problem_selected)

        self.developer_button = self.ttk.Button(parent, text="▶ 開發者模式（原始 JSON）", command=self._toggle_developer_mode)
        self.developer_button.pack(fill="x", padx=6, pady=(3, 6))
        self.developer_frame = self.ttk.LabelFrame(parent, text="開發者模式")
        performance_row = self.ttk.Frame(self.developer_frame)
        performance_row.pack(fill="x", padx=5, pady=(5, 0))
        self.ttk.Checkbutton(
            performance_row,
            text="效能診斷",
            variable=self.performance_diagnostics_enabled_var,
            command=self._update_performance_diagnostics_display,
        ).pack(side="left")
        self.ttk.Label(
            performance_row,
            textvariable=self.performance_diagnostics_var,
            foreground="#455a64",
        ).pack(side="left", fill="x", expand=True, padx=8)
        self.debug_text = scrolledtext.ScrolledText(self.developer_frame, wrap="none", height=12, font=("Consolas", 9))
        self.debug_text.pack(fill="both", expand=True, padx=5, pady=5)

    def show(self) -> tuple[DXFImportResult, str] | None:
        self.window.grab_set()
        self.window.wait_window()
        return None if self.result is None else (self.result, self.import_mode)

    def _convert_preview(self) -> None:
        self.selection_state = SelectionState()
        self.selection_controller.state = self.selection_state
        self.preview_view_bounds = None
        self.preview_fit_all = True
        self.status_var.set("DXF 正在辨識，請稍候……")
        self.recognize_button.configure(state="disabled", text="辨識中……")
        self.apply_button.configure(state="disabled", text="不可匯入")
        try:
            self.window.configure(cursor="watch")
            self.window.update_idletasks()
        except self.tk.TclError:
            pass
        self.window.after_idle(self._perform_conversion)

    def _perform_conversion(self) -> None:
        from tkinter import messagebox

        try:
            layer_roles: dict[str, str] = {}
            for layer, variable in self.layer_use_vars.items():
                selected_use = variable.get()
                role = self.USE_TO_ROLE.get(selected_use)
                if role is None:
                    raise DXFImportError(
                        f"圖層「{layer}」使用了不支援的用途：{selected_use or '空白'}"
                    )
                layer_roles[layer] = role
            self.world_result = self.importer.convert(
                layer_roles=layer_roles,
                coordinate_system=CoordinateSystem(),
            )
            self._apply_coordinate_settings(show_error=False)
        except Exception as exc:
            if isinstance(exc, DXFImportError):
                error_text = str(exc)
            else:
                error_text = f"辨識發生未預期錯誤：{type(exc).__name__}: {exc}"
            self.world_result = None
            self.result = None
            self.status_var.set(error_text)
            self.apply_button.configure(state="disabled", text="不可匯入")
            messagebox.showerror("DXF 轉換失敗", error_text, parent=self.window)
        finally:
            try:
                self.window.configure(cursor="")
                self.recognize_button.configure(
                    state="normal",
                    text="完成分類並開始辨識／重新辨識",
                )
            except self.tk.TclError:
                pass

    def _reset_coordinate_settings(self) -> None:
        self.coordinate_mode_var.set("world")
        self.selected_origin_world = None
        self._apply_coordinate_settings(show_error=False)

    def _set_selected_point_as_origin(self) -> None:
        if self.world_result is None:
            self.coordinate_error_var.set("請先完成 DXF 辨識。")
            return
        state = self.selection_state
        if state.selected_candidate_source != "candidate_tree":
            self.coordinate_error_var.set(
                "請在 STEP5 候選點明細表格中選取原點；預覽窗格選點僅用於修正起終點。"
            )
            return
        candidate = self.candidate_point_store.get(
            state.selected_component_id,
            state.selected_candidate_point_id,
        )
        if candidate is None:
            self.coordinate_error_var.set(
                "請先選取構件，再於 STEP5 候選點明細表格選取要作為原點的點。"
            )
            return
        coordinate_system = coordinate_system_from_candidate(candidate)
        self.selected_origin_world = (
            coordinate_system.origin_x,
            coordinate_system.origin_y,
        )
        self.coordinate_mode_var.set("local")
        self._apply_coordinate_settings(show_error=False)

    def _update_set_origin_button_state(self) -> None:
        button = getattr(self, "set_origin_button", None)
        if button is None:
            return
        state = self.selection_state
        candidate = self.candidate_point_store.get(
            state.selected_component_id,
            state.selected_candidate_point_id,
        )
        enabled = (
            self.world_result is not None
            and state.selected_candidate_source == "candidate_tree"
            and candidate is not None
        )
        button.configure(state="normal" if enabled else "disabled")

    def _apply_coordinate_settings(
        self,
        show_error: bool = True,
        *,
        preview_dirty: RenderDirty = RenderDirty.FULL_SCENE,
        rebuild_candidate_tree: bool = True,
    ) -> None:
        if self.world_result is None:
            return
        mode = self.coordinate_mode_var.get()
        if mode == "local" and self.selected_origin_world is None:
            self.coordinate_valid = False
            self.result = self.world_result
            self.coordinate_error_var.set("請先選取一個候選點作為局部原點。")
            self._refresh_result_views(
                preview_dirty=preview_dirty,
                rebuild_candidate_tree=rebuild_candidate_tree,
            )
            return
        if mode == "local":
            coordinate_system = CoordinateSystem(
                "local",
                self.selected_origin_world[0],
                self.selected_origin_world[1],
                "selected_candidate_point",
            )
        else:
            coordinate_system = CoordinateSystem()
        self.coordinate_valid = True
        self.coordinate_error_var.set("")
        self.result = apply_coordinate_system(self.world_result, coordinate_system)
        self._refresh_result_views(
            preview_dirty=preview_dirty,
            rebuild_candidate_tree=rebuild_candidate_tree,
        )

    def _refresh_result_views(
        self,
        *,
        preview_dirty: RenderDirty = RenderDirty.FULL_SCENE,
        rebuild_candidate_tree: bool = True,
    ) -> None:
        if self.result is None:
            return
        self.candidate_point_store.rebuild(self._all_members())
        if self.selected_member_id and self._selected_member() is None:
            self.selection_state = SelectionState()
            self.selection_controller.state = self.selection_state
        self.problem_records = build_problem_records(self.result)
        self.selected_problem = None
        self.focus_member_ids.clear()
        self.focus_handles.clear()
        self._update_summary()
        self._update_validation_overview()
        self._refresh_problem_tree()
        self._refresh_member_tree()
        self._update_selected_member_panel(
            rebuild_candidates=rebuild_candidate_tree
        )
        self.debug_text.delete("1.0", "end")
        self.debug_text.insert("1.0", json.dumps(self.result.to_debug_dict(), ensure_ascii=False, indent=2))
        self._update_coordinate_display()
        self._update_import_controls()
        self.render_scheduler.request(preview_dirty)

    def _update_coordinate_display(self) -> None:
        if self.result is None:
            return
        coordinate = self.result.coordinate_system
        if self.coordinate_valid and coordinate.mode == "local":
            mode_text = "Local Coordinates"
            origin_text = f"({coordinate.origin_x:.3f}, {coordinate.origin_y:.3f})"
        elif self.coordinate_valid:
            mode_text = "World Coordinates"
            origin_text = "(0.000, 0.000)"
        else:
            mode_text = "尚未套用（目前預覽 World Coordinates）"
            origin_text = "—"
        self.coordinate_info_var.set(
            f"原始：World Coordinates　Origin：{origin_text}　Local = World - Origin"
        )
        self.preview_coordinate_var.set(
            f"Coordinate System｜Origin {origin_text}｜Current Mode：{mode_text}"
        )

        members = self._all_members()
        if members:
            sample_world = members[0].world_start or members[0].start
        else:
            sample_world = (0.0, 0.0)
        sample_local = (
            coordinate.transform(sample_world)
            if self.coordinate_valid
            else sample_world
        )
        self.coordinate_example_var.set(
            f"範例 World ({sample_world[0]:.3f}, {sample_world[1]:.3f}) → "
            f"Local ({sample_local[0]:.3f}, {sample_local[1]:.3f})"
        )

    def _update_summary(self) -> None:
        if self.result is None:
            return
        self.summary_file_var.set(f"檔名：{self.file_path.name}")
        self.summary_tree.delete(*self.summary_tree.get_children())
        recognized = {
            "strut": len(self.result.struts),
            "waler": len(self.result.walers),
            "brace": len(self.result.braces),
            "column": len(self.result.columns),
            "beam": len(self.result.beams),
            "corner_brace": len(self.result.corner_braces),
            "auxiliary": 0,
        }
        skipped: Counter[str] = Counter()
        skipped_keys: set[tuple[str, str, str]] = set()
        for item in self.result.entity_debug:
            if item.status not in {"ignored", "unsupported", "error"} or item.entity_type == "TEXT_SUMMARY":
                continue
            key = (item.role, item.handle, item.entity_type)
            if key not in skipped_keys:
                skipped_keys.add(key)
                skipped[item.role] += 1
        role_labels = {
            "strut": "支撐",
            "waler": "圍令",
            "brace": "斜撐",
            "column": "中間柱",
            "beam": "托梁",
            "corner_brace": "角撐",
            "auxiliary": "輔助線",
        }
        for role in (
            "waler",
            "strut",
            "brace",
            "column",
            "beam",
            "corner_brace",
            "auxiliary",
        ):
            self.summary_tree.insert(
                "",
                "end",
                values=(
                    role_labels[role],
                    "、".join(self.result.selected_layers.get(role, ())) or "—",
                    self.result.source_entity_counts[role],
                    recognized[role],
                    skipped[role],
                ),
            )
        counts = Counter(message.severity for message in self.result.messages)
        self.summary_totals_var.set(
            f"略過：{sum(skipped.values())}　　Warning：{counts['warning']}　　"
            f"Error：{counts['error']}　　Critical：{counts['critical']}"
        )

    def _update_validation_overview(self) -> None:
        for child in self.validation_content.winfo_children():
            child.destroy()
        if self.result is None:
            return
        items = list(build_validation_overview(self.result))
        if not self.coordinate_valid:
            items = [
                item
                for item in items
                if not item.text.startswith(("使用局部座標", "使用原始 CAD 座標"))
            ]
            items.insert(
                1,
                ValidationOverviewItem(
                    "error",
                    self.coordinate_error_var.get() or "座標系統尚未套用",
                ),
            )
        columns = 2
        for index, item in enumerate(items):
            icon = self.LEVEL_ICONS[item.level]
            label = self.tk.Label(
                self.validation_content,
                text=f"{icon}  {item.text}",
                foreground=self.LEVEL_COLORS[item.level],
                anchor="w",
                justify="left",
            )
            label.grid(row=index // columns, column=index % columns, sticky="w", padx=(0, 24), pady=2)
        for column in range(columns):
            self.validation_content.columnconfigure(column, weight=1)

    def _refresh_problem_tree(self) -> None:
        if not hasattr(self, "problem_tree"):
            return
        self.problem_tree.delete(*self.problem_tree.get_children())
        self.problem_record_by_iid.clear()
        severity_filter = self.problem_filter_var.get()
        for index, record in enumerate(self.problem_records):
            if severity_filter == "error" and record.severity not in ERROR_SEVERITIES:
                continue
            if severity_filter == "warning" and record.severity != "warning":
                continue
            if self.selected_only_var.get() and self.selected_problem is not None:
                same_member = bool(set(record.member_ids).intersection(self.selected_problem.member_ids))
                same_source = bool(set(record.source_handles).intersection(self.selected_problem.source_handles))
                if not (same_member or same_source):
                    continue
            elif self.selected_only_var.get():
                continue
            iid = f"problem_{index}"
            self.problem_record_by_iid[iid] = record
            self.problem_tree.insert(
                "",
                "end",
                iid=iid,
                values=(record.severity.upper(), record.code, record.component, record.description),
                tags=(record.severity,),
            )

    def _on_problem_selected(self, _event: Any = None) -> None:
        selection = self.problem_tree.selection()
        if not selection:
            return
        record = self.problem_record_by_iid.get(selection[0])
        if record is None:
            return
        self.selected_problem = record
        self.focus_member_ids = set(record.member_ids)
        self.focus_handles = set(record.source_handles)
        if record.member_ids:
            self._select_member(
                record.member_ids[0],
                refit=True,
                clear_problem=False,
                source="error_list",
            )
        self.preview_view_bounds = None
        self.preview_fit_all = False
        if self.selected_only_var.get():
            self._refresh_problem_tree()
        self._open_preview_window()
        self.render_scheduler.request(RenderDirty.FULL_SCENE)

    def _update_import_controls(self) -> None:
        if self.result is None:
            return
        if not self.coordinate_valid:
            self.apply_button.configure(state="disabled", text="不可匯入")
            self.status_var.set(
                f"✗ {self.coordinate_error_var.get() or '座標系統尚未套用'}；請完成座標系統設定。"
            )
            return
        counts = Counter(message.severity for message in self.result.messages)
        error_count = counts["error"] + counts["critical"]
        if error_count:
            self.apply_button.configure(state="disabled", text="不可匯入")
            self.status_var.set(f"✗ 發現 {error_count} 項阻擋錯誤，請先修正問題列表中的 Error／Critical。")
        elif counts["warning"]:
            self.apply_button.configure(state="normal", text="仍要匯入")
            self.status_var.set(f"⚠ 目前有 {counts['warning']} 項警告；建議先修正警告後再匯入。")
        else:
            self.apply_button.configure(state="normal", text="匯入工程模型")
            self.status_var.set("✓ 圖層與工程模型檢核通過，可以匯入 Solver。")

    def _toggle_developer_mode(self) -> None:
        self.developer_expanded = not self.developer_expanded
        if self.developer_expanded:
            self.developer_button.configure(text="▼ 開發者模式（原始 JSON）")
            self.developer_frame.pack(fill="both", padx=6, pady=(0, 6))
        else:
            self.developer_frame.pack_forget()
            self.developer_button.configure(text="▶ 開發者模式（原始 JSON）")

    def _all_members(
        self,
    ) -> tuple[Waler | Strut | Brace | AuxiliaryComponent, ...]:
        if self.result is None:
            return ()
        return (
            *self.result.walers,
            *self.result.struts,
            *self.result.braces,
            *self.result.columns,
            *self.result.beams,
            *self.result.corner_braces,
        )

    def _selected_member(
        self,
    ) -> Waler | Strut | Brace | AuxiliaryComponent | None:
        return self._member_by_id(self.selected_member_id)

    def _member_by_id(
        self,
        member_id: str,
    ) -> Waler | Strut | Brace | AuxiliaryComponent | None:
        return next(
            (member for member in self._all_members() if member.id == member_id),
            None,
        )

    @staticmethod
    def _preview_source_geometry(
        result: DXFImportResult,
    ) -> tuple[SourceGeometry, ...]:
        """Return source geometry from user-selected, non-ignored layers only."""

        return tuple(
            geometry
            for geometry in result.source_geometry
            if geometry.role != "ignore"
        )

    @classmethod
    def _visible_preview_source_geometry(
        cls,
        result: DXFImportResult,
        *,
        show_source: bool,
        show_auxiliary: bool,
        focus_handles: Sequence[str] = (),
    ) -> tuple[SourceGeometry, ...]:
        """Apply independent visibility rules to engineering and auxiliary lines."""

        focused = set(focus_handles)
        return tuple(
            geometry
            for geometry in cls._preview_source_geometry(result)
            if (
                show_auxiliary
                if geometry.role == "auxiliary"
                else show_source or geometry.source_handle in focused
            )
        )

    @staticmethod
    def _member_role(
        member: Waler | Strut | Brace | AuxiliaryComponent,
    ) -> tuple[str, str]:
        if isinstance(member, Waler):
            return "waler", "圍令"
        if isinstance(member, Strut):
            return "strut", "支撐"
        if isinstance(member, Brace):
            return "brace", "斜撐"
        if isinstance(member, Column):
            return "column", "中間柱"
        if isinstance(member, Beam):
            return "beam", "托梁"
        return "corner_brace", "角撐"

    def _refresh_member_tree(self) -> None:
        if not hasattr(self, "member_tree"):
            return
        self._updating_member_tree = True
        try:
            self.member_tree.delete(*self.member_tree.get_children())
            self.member_by_tree_iid.clear()
            if self.result is None:
                return
            groups = (
                ("waler", "圍令", self.result.walers),
                ("strut", "支撐", self.result.struts),
                ("brace", "斜撐", self.result.braces),
                ("column", "中間柱", self.result.columns),
                ("beam", "托梁", self.result.beams),
                ("corner_brace", "角撐", self.result.corner_braces),
            )
            selected_iid = ""
            for role, label, members in groups:
                group_iid = f"group_{role}"
                self.member_tree.insert(
                    "",
                    "end",
                    iid=group_iid,
                    text=f"{label}（{len(members)}）",
                    open=True,
                )
                for member in members:
                    iid = f"member_{member.id}"
                    suffix = " ＊" if member.selection_source != "auto" else ""
                    self.member_tree.insert(
                        group_iid,
                        "end",
                        iid=iid,
                        text=f"{member.id}{suffix}",
                    )
                    self.member_by_tree_iid[iid] = member.id
                    if member.id == self.selected_member_id:
                        selected_iid = iid
            if selected_iid:
                self.member_tree_selection.select(selected_iid)
        finally:
            self._updating_member_tree = False

    def _candidate_filter_accepts(self, candidate: CandidatePoint) -> bool:
        member = self._selected_member()
        if member is None:
            return False
        filter_mode = self.candidate_filter_var.get()
        if filter_mode in {"start", "end"}:
            return filter_mode in candidate.valid_for
        if filter_mode == "recommended":
            return bool(
                candidate.recommended_for
                or candidate.id
                in {
                    member.recommended_start_point_id,
                    member.recommended_end_point_id,
                }
            )
        return True

    def _candidate_row_values(
        self,
        member: Waler | Strut | Brace | AuxiliaryComponent,
        candidate: CandidatePoint,
    ) -> tuple[str, str, str, str, str]:
        state = self.selection_state
        statuses: list[str] = []
        if candidate.id == member.recommended_start_point_id:
            statuses.append("推薦起點")
        if candidate.id == member.recommended_end_point_id:
            statuses.append("推薦終點")
        if candidate.id == member.selected_start_point_id:
            statuses.append("正式起點")
        if candidate.id == member.selected_end_point_id:
            statuses.append("正式終點")
        if candidate.id == state.pending_start_point_id:
            statuses.append("待套用起點")
        if candidate.id == state.pending_end_point_id:
            statuses.append("待套用終點")
        if candidate.id == state.selected_candidate_point_id:
            statuses.append("目前選取")
        marker = (
            "●"
            if candidate.id
            in {state.pending_start_point_id, state.pending_end_point_id}
            else "○"
        )
        return (
            f"{marker} {candidate.id}",
            candidate.label,
            f"{candidate.world_point[0]:.3f}, {candidate.world_point[1]:.3f}",
            f"{candidate.local_point[0]:.3f}, {candidate.local_point[1]:.3f}",
            "、".join(statuses) or "候選",
        )

    def _rebuild_candidate_tree(self) -> None:
        if not hasattr(self, "candidate_tree_adapter"):
            return
        member = self._selected_member()
        if member is None:
            self.candidate_tree_adapter.rebuild("", (), lambda _point: ())
            self.performance_diagnostics.candidate_tree_rebuilds += 1
            self._update_set_origin_button_state()
            return
        points = self.candidate_point_store.component_points(member.id)
        self.candidate_tree_adapter.rebuild(
            member.id,
            points,
            lambda point: self._candidate_row_values(member, point),
            self._candidate_filter_accepts,
        )
        self.performance_diagnostics.candidate_tree_rebuilds += 1
        self.candidate_tree_adapter.sync_selection(
            self.selection_state.selected_candidate_point_id
        )
        self.candidate_tree_adapter.set_hover(
            self.selection_state.hovered_candidate_point_id
        )
        self._update_set_origin_button_state()

    def _update_candidate_tree_rows(self) -> None:
        member = self._selected_member()
        if member is None or not hasattr(self, "candidate_tree_adapter"):
            return
        for point in self.candidate_point_store.component_points(member.id):
            self.candidate_tree_adapter.update_row(
                point.id,
                self._candidate_row_values(member, point),
            )

    def _update_selected_member_panel(
        self,
        *,
        rebuild_candidates: bool = True,
    ) -> None:
        if not hasattr(self, "candidate_tree"):
            return
        member = self._selected_member()
        if member is None:
            self.preview_selected_member_var.set("目前構件：—")
            for variable in self.member_info_vars.values():
                variable.set("—")
            self.candidate_detail_var.set("候選點：—")
            if rebuild_candidates:
                self._rebuild_candidate_tree()
            return
        _role, role_label = self._member_role(member)
        self.preview_selected_member_var.set(
            f"目前構件：{member.id}｜{role_label}｜圖層 {member.source_layer}"
        )
        values = {
            "id": member.id,
            "role": role_label,
            "layer": member.source_layer,
            "entities": (
                f"{', '.join(member.source_entity_types)}\n"
                f"Handle: {', '.join(member.source_handles)}"
            ),
            "method": (
                f"{member.recognition_method}｜"
                f"{self._selection_source_label(member.selection_source)}"
            ),
            "start_x": f"{member.start[0]:.3f}",
            "start_y": f"{member.start[1]:.3f}",
            "end_x": f"{member.end[0]:.3f}",
            "end_y": f"{member.end[1]:.3f}",
        }
        for key, value in values.items():
            self.member_info_vars[key].set(value)
        if rebuild_candidates:
            self._rebuild_candidate_tree()
        else:
            self._update_candidate_tree_rows()
        self._update_candidate_detail_panel()

    def _update_candidate_detail_panel(self) -> None:
        state = self.selection_state
        point_id = (
            state.hovered_candidate_point_id
            or state.selected_candidate_point_id
        )
        candidate = self.candidate_point_store.get(
            state.selected_component_id,
            point_id,
        )
        self.candidate_detail_var.set(
            self._candidate_detail_text(candidate)
            if candidate is not None
            else "候選點：—"
        )

    def _on_candidate_filter_changed(self) -> None:
        self._rebuild_candidate_tree()
        self.render_scheduler.request(
            RenderDirty.CANDIDATE_LAYER
            | RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
        )

    def _on_member_selected(self, _event: Any = None) -> None:
        if self._updating_member_tree or self.member_tree_selection.syncing:
            return
        selection = self.member_tree.selection()
        if not selection:
            return
        member_id = self.member_by_tree_iid.get(selection[0], "")
        if not member_id:
            return
        self._select_member(
            member_id,
            refit=True,
            clear_problem=True,
            source="component_tree",
        )

    def _select_member(
        self,
        member_id: str,
        *,
        refit: bool,
        clear_problem: bool,
        source: str = "programmatic",
    ) -> None:
        if clear_problem:
            self.selected_problem = None
            self.focus_member_ids.clear()
            self.focus_handles.clear()
            if self.selected_only_var.get():
                self.selected_only_var.set(False)
                self._refresh_problem_tree()
        changed = self.selection_controller.select_component(member_id, source)
        if changed and hasattr(self, "candidate_action_status_var"):
            self.candidate_action_status_var.set(
                "單擊候選點只會預覽；請先選擇要修改起點或終點。"
            )
        if refit and changed:
            self.preview_view_bounds = None
            self.preview_fit_all = False
            self.render_scheduler.request(RenderDirty.FULL_SCENE)
        if changed and hasattr(self, "candidate_action_status_var"):
            self.candidate_action_status_var.set(
                "可直接在預覽圖點擊藍色起點或紅色終點，再點選新的黃色候選點。"
            )
        self._update_set_origin_button_state()

    @staticmethod
    def _selection_source_label(source: str) -> str:
        return {
            "auto": "自動辨識",
            "manual_candidate_points": "人工候選點",
            "cad_manual": "CAD 人工指定",
        }.get(source, source or "自動辨識")

    def _candidate_detail_text(self, candidate: CandidatePoint) -> str:
        return (
            f"{candidate.id}｜{candidate.label}\n"
            f"World：({candidate.world_point[0]:.3f}, {candidate.world_point[1]:.3f})　"
            f"Local：({candidate.local_point[0]:.3f}, {candidate.local_point[1]:.3f})"
        )

    def _on_candidate_point_selected(self, _event: Any = None) -> None:
        if self.world_result is None or self.candidate_tree_adapter.syncing:
            return
        selection = self.candidate_tree.selection()
        if not selection or not self.selected_member_id:
            return
        point_id = self.candidate_tree_adapter.point_id_for_iid(selection[0])
        if not point_id:
            return
        self._select_candidate_point(
            point_id,
            center_if_hidden=True,
            source="candidate_tree",
        )
        self._update_set_origin_button_state()

    def _select_candidate_point(
        self,
        point_id: str,
        *,
        center_if_hidden: bool = False,
        source: str = "programmatic",
    ) -> None:
        candidate = self.candidate_point_store.get(
            self.selection_state.selected_component_id,
            point_id,
        )
        if candidate is None:
            return
        previous_bounds = self.preview_view_bounds
        if center_if_hidden:
            self._center_candidate_if_hidden(candidate)
        view_changed = self.preview_view_bounds != previous_bounds
        previous_mode = self.selection_state.mode
        changed = self.selection_controller.select_candidate_point(point_id, source)
        if view_changed:
            self.render_scheduler.request(RenderDirty.FULL_SCENE)
        if not changed:
            return
        if previous_mode == "pick_start":
            self.candidate_action_status_var.set(
                f"已選擇待套用起點 {point_id}；按「套用修改」才會重建模型。"
            )
        elif previous_mode == "pick_end":
            self.candidate_action_status_var.set(
                f"已選擇待套用終點 {point_id}；按「套用修改」才會重建模型。"
            )

        if changed and previous_mode == "pick_start":
            self.candidate_action_status_var.set(
                f"已選擇待套用起點 {point_id}；橘色虛線為待套用工程線，尚未修改正式模型。"
            )
        elif changed and previous_mode == "pick_end":
            self.candidate_action_status_var.set(
                f"已選擇待套用終點 {point_id}；橘色虛線為待套用工程線，尚未修改正式模型。"
            )

    def _center_candidate_if_hidden(self, candidate: CandidatePoint) -> None:
        if self.preview_view_bounds is None or self.result is None:
            return
        point = self.result.coordinate_system.transform(candidate.world_point)
        min_x, max_x, min_y, max_y = self.preview_view_bounds
        if min_x <= point[0] <= max_x and min_y <= point[1] <= max_y:
            return
        self.preview_viewport.recenter(point)

    def _begin_candidate_pick(self, mode: str) -> None:
        member = self._selected_member()
        if member is None:
            self.candidate_action_status_var.set("請先選取構件。")
            return
        changed = (
            self.selection_controller.begin_pick_start()
            if mode == "pick_start"
            else self.selection_controller.begin_pick_end()
        )
        if not changed:
            return
        prompt = "請選擇新的起點" if mode == "pick_start" else "請選擇新的終點"
        self.candidate_filter_var.set("start" if mode == "pick_start" else "end")
        self.candidate_action_status_var.set(f"{prompt}（Esc 取消本次選點）")
        self._rebuild_candidate_tree()
        self._open_preview_window()
        try:
            self.canvas.focus_set()
        except self.tk.TclError:
            pass
        self.candidate_action_status_var.set(
            (
                "請在預覽圖點選新的起點（Esc 取消本次選點）"
                if mode == "pick_start"
                else "請在預覽圖點選新的終點（Esc 取消本次選點）"
            )
        )

    def _cancel_active_pick(self, _event: Any = None) -> str | None:
        if not self.selection_controller.cancel_pick():
            return None
        self.candidate_action_status_var.set("已取消本次選點，待套用值維持不變。")
        return "break"

    def _swap_pending_points(self) -> None:
        if not self.selection_controller.swap_pending_points():
            return
        self.candidate_action_status_var.set("已交換待套用起終點；正式模型尚未修改。")

    def _cancel_candidate_changes(self) -> None:
        if not self.selection_controller.cancel_pending():
            return
        self.candidate_action_status_var.set("已取消待套用修改；正式模型未變更。")

    def _restore_recommended_points(self) -> None:
        if not self.selection_controller.restore_recommended_points():
            return
        self.candidate_action_status_var.set(
            "已恢復系統推薦至待套用值；仍需按「套用修改」。"
        )

    def _apply_candidate_changes(self) -> None:
        from tkinter import messagebox

        message_parent = self.preview_window or self.window
        member = self._selected_member()
        if member is None or self.world_result is None:
            self.candidate_action_status_var.set("請先選取構件。")
            return
        state = self.selection_state
        validations = validate_candidate_point_pair(
            member,
            state.pending_start_point_id,
            state.pending_end_point_id,
            self.importer.tolerances,
            self.result.walers if self.result is not None else (),
        )
        errors = [item for item in validations if item.severity in ERROR_SEVERITIES]
        if errors:
            self.candidate_action_status_var.set(errors[0].message)
            messagebox.showerror(
                "候選點組合無法套用",
                errors[0].message,
                parent=message_parent,
            )
            return
        warnings = [item.message for item in validations if item.severity == "warning"]
        if warnings and not messagebox.askyesno(
            "候選點組合警告",
            "\n".join(f"⚠ {message}" for message in warnings)
            + "\n\n仍要套用嗎？",
            parent=message_parent,
        ):
            return
        try:
            self.world_result = self.import_model_controller.apply_pending(
                self.world_result,
                state,
            )
        except DXFImportError as exc:
            self.candidate_action_status_var.set(str(exc))
            return
        self._apply_coordinate_settings(
            show_error=False,
            preview_dirty=(
                RenderDirty.COMPONENT_LAYER
                | RenderDirty.COMPONENT_SELECTION
                | RenderDirty.CANDIDATE_SELECTION
                | RenderDirty.TEMP_LINE
                | RenderDirty.DETAIL_PANEL
                | RenderDirty.TREE_SELECTION
            ),
            rebuild_candidate_tree=False,
        )
        self.selection_controller.synchronize_formal_member()
        self.candidate_action_status_var.set(
            f"已套用 {member.id}，並重建連接、衍生資料及 Solver 輸入。"
        )

    def _read_cad_engineering_line(self) -> None:
        from tkinter import messagebox

        member = self._selected_member()
        if member is None or self.world_result is None:
            self.cad_temp_status_var.set("請先完成辨識並選取要修正的構件。")
            return
        role, _role_label = self._member_role(member)
        supported_roles = {
            "waler": {"waler", "walers"},
            "strut": {"strut", "struts", "support", "supports"},
            "brace": {"brace", "braces"},
        }
        if role not in supported_roles:
            self.cad_temp_status_var.set(
                "目前 CAD Temp 僅支援圍令、支撐與斜撐工程線。"
            )
            return
        try:
            event = self.cad_event_watcher.check_new_event()
            if event is None:
                self.cad_temp_status_var.set("目前沒有待讀取的 CAD Temp 工程線。")
                return
            event_type = str(event.get("type", "")).strip().lower()
            if event_type not in supported_roles[role]:
                raise DXFImportError(
                    f"CAD 事件類型 {event_type or '—'} 與選取構件 {member.id} 不相符。"
                )
            data = event.get("data")
            if not isinstance(data, Mapping):
                raise DXFImportError("CAD Temp 缺少工程線座標資料。")
            start = float(data["StartX"]), float(data["StartY"])
            end = float(data["EndX"]), float(data["EndY"])
            self.world_result, start_id, end_id = add_cad_candidate_points(
                self.world_result,
                member.id,
                start,
                end,
                self.importer.tolerances,
            )
            self.cad_event_watcher.acknowledge(event)
        except (DXFImportError, KeyError, TypeError, ValueError, OSError) as exc:
            self.cad_temp_status_var.set(str(exc))
            messagebox.showerror("CAD 工程線讀取失敗", str(exc), parent=self.window)
            return
        self.cad_temp_status_var.set(
            f"已讀取 {member.id} 的 CAD 指定工程線；請確認後按「套用修改」。"
        )
        self._apply_coordinate_settings(
            show_error=False,
            preview_dirty=(
                RenderDirty.CANDIDATE_LAYER
                | RenderDirty.CANDIDATE_SELECTION
                | RenderDirty.TEMP_LINE
                | RenderDirty.DETAIL_PANEL
                | RenderDirty.TREE_SELECTION
            ),
            rebuild_candidate_tree=True,
        )
        self.selection_controller.set_pending_pair(
            start_id,
            end_id,
            "cad_manual",
        )

    def _on_candidate_hover(self, event: Any) -> None:
        iid = self.candidate_tree.identify_row(event.y)
        point_id = self.candidate_tree_adapter.point_id_for_iid(iid)
        self.selection_controller.set_hovered_candidate(point_id)

    def _clear_candidate_hover(self, _event: Any = None) -> None:
        self.selection_controller.set_hovered_candidate("")

    @staticmethod
    def _nearest_preview_member(
        point: Point,
        hit_lines: Sequence[tuple[str, Point, Point]],
        tolerance: float = 12.0,
    ) -> str:
        return PreviewController.nearest_member(point, hit_lines, tolerance)

    @staticmethod
    def _preview_candidate_hits(
        point: Point,
        hit_points: Sequence[tuple[str, Point]],
        tolerance_pixels: float = 10.0,
    ) -> tuple[str, ...]:
        return PreviewController.candidate_hits(
            point,
            hit_points,
            tolerance_pixels,
        )

    @staticmethod
    def _preview_endpoint_hits(
        point: Point,
        endpoints: Sequence[tuple[str, Point]],
        tolerance_pixels: float = 12.0,
    ) -> tuple[str, ...]:
        """Hit-test the visible pending endpoint markers in screen pixels."""

        return PreviewController.candidate_hits(
            point,
            endpoints,
            tolerance_pixels,
        )

    def _pending_endpoint_hits(self, point: Point) -> tuple[str, ...]:
        component_id = self.selection_state.selected_component_id
        if not component_id:
            return ()
        endpoint_points: list[tuple[str, Point]] = []
        for role, point_id in (
            ("start", self.selection_state.pending_start_point_id),
            ("end", self.selection_state.pending_end_point_id),
        ):
            candidate = self.candidate_point_store.get(component_id, point_id)
            if candidate is not None:
                endpoint_points.append((role, self._candidate_canvas_point(candidate)))
        return self._preview_endpoint_hits(point, endpoint_points)

    def _sync_candidate_tree_hover(self, point_id: str) -> None:
        if hasattr(self, "candidate_tree_adapter"):
            self.candidate_tree_adapter.set_hover(point_id)

    def _on_canvas_click(self, event: Any) -> None:
        canvas_point = (float(event.x), float(event.y))
        if self.selection_state.mode == "idle":
            endpoint_hits = self._pending_endpoint_hits(canvas_point)
            if len(endpoint_hits) == 1:
                self._begin_candidate_pick(
                    "pick_start"
                    if endpoint_hits[0] == "start"
                    else "pick_end"
                )
                return
            if len(endpoint_hits) > 1:
                self.candidate_action_status_var.set(
                    "起點與終點標記在畫面上重疊，請放大圖面後再點選，或使用主視窗按鈕。"
                )
                return
        hits = self._preview_candidate_hits(
            canvas_point,
            self.canvas_candidate_hit_points,
        )
        if len(hits) == 1:
            self._select_candidate_point(hits[0], source="canvas")
            return
        if len(hits) > 1:
            self.candidate_action_status_var.set(
                "此處命中多個候選點："
                + "、".join(hits)
                + "。請由右側候選點清單精確選擇。"
            )
            return
        if self.selection_state.mode in {"pick_start", "pick_end"}:
            self.candidate_action_status_var.set(
                "選點模式只能點選黃色候選點；不能使用空白位置。"
            )
            return
        member_id = self._nearest_preview_member(
            canvas_point,
            self.canvas_member_hit_lines,
        )
        if member_id:
            self._select_member(
                member_id,
                refit=False,
                clear_problem=True,
                source="canvas",
            )

    def _locate_selected_member(self) -> None:
        self._open_preview_window()
        if self._selected_member() is not None:
            self.preview_view_bounds = None
            self.preview_fit_all = False
        self._draw_preview()

    def _on_canvas_motion(self, event: Any) -> None:
        if self.preview_viewport.view_bounds is None:
            self.preview_cursor_var.set("游標：—")
            return
        x, y = self.preview_viewport.screen_to_data(
            (float(event.x), float(event.y))
        )
        self.preview_cursor_var.set(f"游標：X={x:.3f}  Y={y:.3f}")
        point_hits = self._preview_candidate_hits(
            (float(event.x), float(event.y)),
            self.canvas_candidate_hit_points,
        )
        endpoint_hits = (
            self._pending_endpoint_hits((float(event.x), float(event.y)))
            if self.selection_state.mode == "idle"
            else ()
        )
        try:
            self.canvas.configure(
                cursor=("hand2" if point_hits or endpoint_hits else "crosshair")
            )
        except self.tk.TclError:
            pass
        hovered_point_id = point_hits[0] if point_hits else ""
        hovered_member_id = ""
        if not hovered_point_id:
            hovered_member_id = self._nearest_preview_member(
                (float(event.x), float(event.y)),
                self.canvas_member_hit_lines,
            )
        self.selection_controller.set_hovered_candidate(hovered_point_id)
        self.selection_controller.set_hovered_component(hovered_member_id)

    def _on_canvas_leave(self, _event: Any = None) -> None:
        self.preview_cursor_var.set("游標：—")
        self.selection_controller.set_hovered_candidate("")
        self.selection_controller.set_hovered_component("")

    def _on_canvas_mousewheel(self, event: Any, direction: int | None = None) -> None:
        if self.preview_viewport.view_bounds is None:
            return
        if direction is None:
            direction = 1 if getattr(event, "delta", 0) > 0 else -1
        factor = self.preview_interaction.scroll_factor(direction)
        if factor is None:
            return
        self.preview_viewport.zoom_at_screen(
            (float(event.x), float(event.y)),
            factor,
        )
        self.preview_fit_all = False
        self._draw_preview()

    def _start_canvas_pan(self, event: Any) -> None:
        if self.preview_view_bounds is not None:
            self.preview_interaction.begin_pan(
                (float(event.x), float(event.y)),
                self.preview_view_bounds,
            )
            self.canvas.configure(cursor="fleur")

    def _drag_canvas_pan(self, event: Any) -> None:
        if not self.preview_interaction.pan_active:
            return
        scale = self.preview_viewport.scale
        updated = self.preview_interaction.pan_to(
            (float(event.x), float(event.y)),
            (scale, scale),
            y_axis_screen_down=True,
        )
        if updated is None:
            return
        self.preview_view_bounds = updated
        self.preview_fit_all = False
        self._draw_preview()

    def _end_canvas_pan(self, _event: Any = None) -> None:
        self.preview_interaction.end_pan()
        try:
            self.canvas.configure(cursor="crosshair")
        except self.tk.TclError:
            pass

    def _on_canvas_middle_double_click(self, _event: Any = None) -> str:
        self._end_canvas_pan()
        self._zoom_extents()
        return "break"

    def _zoom_extents(self) -> None:
        self.preview_view_bounds = None
        self.preview_fit_all = True
        self._draw_preview()

    def _draw_preview(self) -> None:
        self.render_scheduler.request(RenderDirty.FULL_SCENE)

    def _flush_render_updates(self, dirty: RenderDirty) -> None:
        started_at = time.perf_counter()
        if dirty & RenderDirty.FULL_SCENE:
            self._rebuild_preview_scene()
            if (
                dirty & RenderDirty.CANDIDATE_LAYER
                and hasattr(self, "candidate_tree_adapter")
                and self.candidate_tree_adapter.component_id
                != self.selection_state.selected_component_id
            ):
                self._rebuild_candidate_tree()
        else:
            if dirty & RenderDirty.COMPONENT_LAYER:
                self._rebuild_engineering_member_layer()
            if dirty & RenderDirty.CANDIDATE_LAYER:
                if (
                    hasattr(self, "candidate_tree_adapter")
                    and self.candidate_tree_adapter.component_id
                    != self.selection_state.selected_component_id
                ):
                    self._rebuild_candidate_tree()
                self._rebuild_candidate_overlay()
            if dirty & (
                RenderDirty.COMPONENT_SELECTION
                | RenderDirty.CANDIDATE_SELECTION
                | RenderDirty.HOVER
            ):
                self._update_preview_selection_overlay(
                    update_associations=bool(
                        dirty & RenderDirty.COMPONENT_SELECTION
                    )
                )
            if dirty & RenderDirty.TEMP_LINE:
                self._update_temporary_line_overlay()
        if dirty & RenderDirty.TREE_SELECTION:
            self._sync_tree_selections_from_state()
        if dirty & RenderDirty.HOVER:
            self._sync_candidate_tree_hover(
                self.selection_state.hovered_candidate_point_id
            )
        if dirty & RenderDirty.COMPONENT_SELECTION:
            self._update_selected_member_panel(rebuild_candidates=False)
        elif dirty & RenderDirty.CANDIDATE_SELECTION:
            self._update_candidate_tree_rows()
            self._update_candidate_detail_panel()
        elif dirty & RenderDirty.DETAIL_PANEL:
            self._update_candidate_detail_panel()
        self.performance_diagnostics.record("render_flush", started_at)
        self._update_performance_diagnostics_display()

    def _rebuild_preview_scene(self) -> None:
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
        except self.tk.TclError:
            return
        started_at = time.perf_counter()
        if self.preview_renderer is None:
            self.preview_renderer = PreviewRenderer(canvas, self.preview_scene)
        renderer = self.preview_renderer
        renderer.clear()
        self.canvas_member_hit_lines = []
        self.canvas_candidate_hit_points = []
        self.preview_transform = None
        if self.result is None:
            return
        member_styles = self._preview_member_styles()
        raw = self._preview_source_geometry(self.result)
        coordinate_system = self.result.coordinate_system
        all_points = [
            point
            for member, *_style in member_styles
            for point in (
                member.path
                if isinstance(member, Beam) and member.path
                else (member.start, member.end)
            )
        ]
        all_points.extend(
            coordinate_system.transform(point)
            for geometry in raw
            for point in geometry.points
        )
        all_points.extend(
            coordinate_system.transform(source_text.position)
            for source_text in self.result.source_texts
        )
        selected_member = self._selected_member()
        if selected_member is not None:
            all_points.extend(
                coordinate_system.transform(candidate.world_point)
                for candidate in self.candidate_point_store.component_points(
                    selected_member.id
                )
            )
        focus_points = [
            point
            for member, *_style in member_styles
            if member.id in self.focus_member_ids
            or member.id == self.selected_member_id
            for point in (
                member.path
                if isinstance(member, Beam) and member.path
                else (member.start, member.end)
            )
        ]
        focus_points.extend(
            coordinate_system.transform(point)
            for geometry in raw
            if geometry.source_handle in self.focus_handles
            for point in geometry.points
        )
        if not all_points:
            renderer.create_text(
                "coordinate_axis",
                20,
                20,
                text="沒有可預覽的工程模型",
                anchor="nw",
            )
            return
        width, height = max(canvas.winfo_width(), 100), max(canvas.winfo_height(), 100)
        margin = 48
        self.preview_viewport.configure(width, height, margin)

        def padded_bounds(points: Sequence[Point]) -> tuple[float, float, float, float]:
            bounds_min_x = min(point[0] for point in points)
            bounds_max_x = max(point[0] for point in points)
            bounds_min_y = min(point[1] for point in points)
            bounds_max_y = max(point[1] for point in points)
            span_x = bounds_max_x - bounds_min_x
            span_y = bounds_max_y - bounds_min_y
            pad_x = max(span_x * 0.18, span_y * 0.05, 50)
            pad_y = max(span_y * 0.18, span_x * 0.05, 50)
            return (
                bounds_min_x - pad_x,
                bounds_max_x + pad_x,
                bounds_min_y - pad_y,
                bounds_max_y + pad_y,
            )

        full_min_x, full_max_x, full_min_y, full_max_y = padded_bounds(
            all_points
        )
        full_content_bounds = (
            full_min_x,
            full_max_x,
            full_min_y,
            full_max_y,
        )
        if self.preview_view_bounds is None:
            view_points = all_points if self.preview_fit_all else (focus_points or all_points)
            min_x, max_x, min_y, max_y = padded_bounds(view_points)
            self.preview_viewport.fit((min_x, max_x, min_y, max_y))
            self.preview_fit_all = False
        assert self.preview_view_bounds is not None
        min_x, max_x, min_y, max_y = self.preview_view_bounds
        scale = self.preview_viewport.scale
        full_scale = self.preview_viewport.scale_for_bounds(full_content_bounds)
        zoom_factor = scale / max(full_scale, 1e-12)

        self.preview_transform = self.preview_viewport.legacy_transform
        self.preview_zoom_factor = zoom_factor
        self._draw_source_geometry_layer(raw)
        self._draw_source_text_layer(self.result.source_texts)
        self._draw_engineering_members()
        self._rebuild_candidate_overlay(update_overlays=False)
        self._ensure_preview_overlay_items()
        self._update_preview_selection_overlay(update_associations=True)
        self._update_temporary_line_overlay()
        self._draw_coordinate_axis_layer()
        self._update_source_layer_visibility()
        for layer in PreviewRenderer.LAYERS:
            try:
                canvas.tag_raise(layer)
            except self.tk.TclError:
                pass
        self.performance_diagnostics.full_scene_rebuilds += 1
        try:
            self.performance_diagnostics.canvas_item_count = len(canvas.find_all())
        except self.tk.TclError:
            self.performance_diagnostics.canvas_item_count = 0
        self.performance_diagnostics.record("full_scene", started_at)

    def _preview_member_styles(
        self,
    ) -> list[tuple[Waler | Strut | Brace | AuxiliaryComponent, str, int, Any]]:
        if self.result is None:
            return []
        return [
            *((member, "#2e7d32", 4, None) for member in self.result.walers),
            *((member, "#2e7d32", 3, None) for member in self.result.struts),
            *((member, "#2e7d32", 3, (8, 4)) for member in self.result.braces),
            *((member, "#2e7d32", 3, (10, 3)) for member in self.result.beams),
            *((member, "#2e7d32", 3, (5, 2)) for member in self.result.corner_braces),
        ]

    def _project_preview_point(self, point: Point) -> Point:
        return self.preview_viewport.data_to_screen(point)

    def _candidate_canvas_point(self, candidate: CandidatePoint) -> Point:
        assert self.result is not None
        return self._project_preview_point(
            self.result.coordinate_system.transform(candidate.world_point)
        )

    def _preview_intersects(self, points: Sequence[Point]) -> bool:
        return self.preview_viewport.intersects(points)

    def _draw_source_geometry_layer(
        self,
        geometries: Sequence[SourceGeometry],
    ) -> None:
        if self.result is None or self.preview_renderer is None:
            return
        renderer = self.preview_renderer
        coordinate_system = self.result.coordinate_system
        for geometry in geometries:
            displayed_points = [
                coordinate_system.transform(point) for point in geometry.points
            ]
            if not self._preview_intersects(displayed_points):
                continue
            projected = [
                coordinate
                for point in displayed_points
                for coordinate in self._project_preview_point(point)
            ]
            if len(projected) < 4:
                continue
            is_auxiliary = geometry.role == "auxiliary"
            layer = "auxiliary_geometry" if is_auxiliary else "source_geometry"
            color = "#d7dde1" if is_auxiliary else "#b0bec5"
            line_width = 1
            dash = None if is_auxiliary else (4, 3)
            if not is_auxiliary and geometry.source_handle in self.focus_handles:
                color, line_width = "#1565c0", 4
            options: dict[str, Any] = {"fill": color, "width": line_width}
            if dash is not None:
                options["dash"] = dash
            renderer.create_line(
                layer,
                *projected,
                source_handle=geometry.source_handle,
                **options,
            )
            if geometry.closed and len(displayed_points) > 2:
                renderer.create_line(
                    layer,
                    *self._project_preview_point(displayed_points[-1]),
                    *self._project_preview_point(displayed_points[0]),
                    source_handle=geometry.source_handle,
                    **options,
                )

    def _draw_source_text_layer(
        self,
        source_texts: Sequence[SourceText],
    ) -> None:
        if self.result is None or self.preview_renderer is None:
            return
        renderer = self.preview_renderer
        coordinate_system = self.result.coordinate_system
        for source_text in source_texts:
            displayed_position = coordinate_system.transform(source_text.position)
            if not self._preview_intersects((displayed_position,)):
                continue
            x, y = self._project_preview_point(displayed_position)
            font_size = max(
                8,
                min(
                    28,
                    round(source_text.height * self.preview_viewport.scale),
                ),
            )
            renderer.create_text(
                "auxiliary_geometry",
                x,
                y,
                text=source_text.text,
                fill="#66757f",
                anchor="center",
                justify="center",
                font=("Microsoft JhengHei", font_size),
                angle=-source_text.rotation,
                source_handle=source_text.source_handle,
            )

    def _member_issue_levels(self) -> dict[str, str]:
        severity_rank = {"warning": 1, "error": 2, "critical": 3}
        member_levels: dict[str, str] = {}
        for record in self.problem_records:
            if record.severity not in severity_rank:
                continue
            for member_id in record.member_ids:
                if severity_rank[record.severity] > severity_rank.get(
                    member_levels.get(member_id, ""),
                    0,
                ):
                    member_levels[member_id] = record.severity
        return member_levels

    def _draw_engineering_members(self) -> None:
        if self.preview_renderer is None:
            return
        renderer = self.preview_renderer
        member_levels = self._member_issue_levels()
        self.canvas_member_hit_lines = []
        for member, color, line_width, dash in self._preview_member_styles():
            member_points = (
                member.path
                if isinstance(member, Beam) and member.path
                else (member.start, member.end)
            )
            if not self._preview_intersects(member_points):
                continue
            projected = tuple(
                self._project_preview_point(point) for point in member_points
            )
            for start, end in zip(projected, projected[1:]):
                self.canvas_member_hit_lines.append((member.id, start, end))
            options: dict[str, Any] = {
                "fill": color,
                "width": line_width,
            }
            if dash is not None:
                options["dash"] = dash
            renderer.create_line(
                "engineering_members",
                *(coordinate for point in projected for coordinate in point),
                component_id=member.id,
                **options,
            )
            level = member_levels.get(member.id)
            if level:
                renderer.create_line(
                    "engineering_members",
                    *(coordinate for point in projected for coordinate in point),
                    component_id=member.id,
                    fill=(
                        "#d32f2f"
                        if level in ERROR_SEVERITIES
                        else "#f9a825"
                    ),
                    width=7,
                    **({"dash": dash} if dash is not None else {}),
                )
            if member.id in self.focus_member_ids:
                renderer.create_line(
                    "engineering_members",
                    *(coordinate for point in projected for coordinate in point),
                    component_id=member.id,
                    fill="#1565c0",
                    width=4,
                    dash=(3, 2),
                )
            # A two-point component used to place its label at index 1, i.e.
            # exactly on its endpoint.  Corner-brace labels then covered the
            # connection to the Strut centreline and made a correct junction
            # look offset.  Place labels at the geometric half-length of the
            # displayed path instead.
            segment_lengths = [
                _distance(start, end)
                for start, end in zip(projected, projected[1:])
            ]
            half_length = sum(segment_lengths) / 2.0
            travelled = 0.0
            label_point = projected[0]
            for (start, end), segment_length in zip(
                zip(projected, projected[1:]),
                segment_lengths,
            ):
                if segment_length <= 1e-12:
                    continue
                if travelled + segment_length >= half_length:
                    fraction = (half_length - travelled) / segment_length
                    label_point = (
                        start[0] + (end[0] - start[0]) * fraction,
                        start[1] + (end[1] - start[1]) * fraction,
                    )
                    break
                travelled += segment_length
            renderer.create_text(
                "engineering_members",
                label_point[0],
                label_point[1] - 9,
                component_id=member.id,
                text=member.id,
                fill=("#1565c0" if member.id in self.focus_member_ids else color),
                font=("Arial", 9, "bold"),
            )

        # A Column is perpendicular to this plan view, so its DXF geometry is
        # a section footprint rather than a linear member.  Show the section
        # reference point instead of drawing the compatibility start/end axis.
        if self.result is None:
            return
        for member in self.result.columns:
            reference = member.reference_point or _midpoint(member.start, member.end)
            if not self._preview_intersects((reference,)):
                continue
            x, y = self._project_preview_point(reference)
            self.canvas_member_hit_lines.append(
                (member.id, (x - 8, y), (x + 8, y))
            )
            level = member_levels.get(member.id)
            color = "#1565c0" if member.id in self.focus_member_ids else "#2e7d32"
            if level:
                issue_color = "#d32f2f" if level in ERROR_SEVERITIES else "#f9a825"
                renderer.create_oval(
                    "engineering_members",
                    x - 9,
                    y - 9,
                    x + 9,
                    y + 9,
                    component_id=member.id,
                    fill="",
                    outline=issue_color,
                    width=4,
                )
            renderer.create_line(
                "engineering_members",
                x - 6,
                y,
                x + 6,
                y,
                component_id=member.id,
                fill=color,
                width=3,
            )
            renderer.create_line(
                "engineering_members",
                x,
                y - 6,
                x,
                y + 6,
                component_id=member.id,
                fill=color,
                width=3,
            )
            renderer.create_text(
                "engineering_members",
                x + 9,
                y - 9,
                component_id=member.id,
                text=member.id,
                fill=color,
                anchor="sw",
                font=("Arial", 9, "bold"),
            )

    def _rebuild_engineering_member_layer(self) -> None:
        if self.preview_renderer is None or self.preview_transform is None:
            return
        started_at = time.perf_counter()
        self.preview_renderer.delete_layer("engineering_members")
        self._draw_engineering_members()
        self._update_preview_selection_overlay(update_associations=True)
        self.performance_diagnostics.engineering_member_rebuilds += 1
        self.performance_diagnostics.record("engineering_members", started_at)

    def _candidate_visible_in_preview(self, candidate: CandidatePoint) -> bool:
        mode = self.selection_state.mode
        return self._candidate_filter_accepts(candidate) and not (
            mode == "pick_start" and "start" not in candidate.valid_for
            or mode == "pick_end" and "end" not in candidate.valid_for
        )

    def _rebuild_candidate_overlay(self, *, update_overlays: bool = True) -> None:
        if self.preview_renderer is None or self.preview_transform is None:
            return
        started_at = time.perf_counter()
        renderer = self.preview_renderer
        renderer.delete_layer("candidate_overlay")
        self.canvas_candidate_hit_points = []
        member = self._selected_member()
        if member is not None:
            for candidate in self.candidate_point_store.component_points(member.id):
                if not self._candidate_visible_in_preview(candidate):
                    continue
                x, y = self._candidate_canvas_point(candidate)
                self.canvas_candidate_hit_points.append((candidate.id, (x, y)))
                renderer.create_oval(
                    "candidate_overlay",
                    x - 5,
                    y - 5,
                    x + 5,
                    y + 5,
                    candidate_point_id=candidate.id,
                    fill="#ffffff",
                    outline="#f9a825",
                    width=2,
                )
        if update_overlays:
            self._ensure_preview_overlay_items()
            self._update_preview_selection_overlay()
            self._update_temporary_line_overlay()
        self.performance_diagnostics.candidate_layer_rebuilds += 1
        self.performance_diagnostics.record("candidate_layer", started_at)

    def _ensure_preview_overlay_items(self) -> None:
        if self.preview_renderer is None:
            return
        renderer = self.preview_renderer
        scene = self.preview_scene

        def line(key: str, layer: str, **options: Any) -> None:
            if key in scene.selection_items or (
                key == "pending_line" and scene.temporary_line_items
            ):
                return
            renderer.create_line(
                layer,
                0,
                0,
                0,
                0,
                overlay_key=key,
                state="hidden",
                **options,
            )

        def oval(key: str, **options: Any) -> None:
            if key in scene.selection_items:
                return
            renderer.create_oval(
                "selection_overlay",
                0,
                0,
                0,
                0,
                overlay_key=key,
                state="hidden",
                **options,
            )

        line("selected_component", "selection_overlay", fill="#c62828", width=5)
        line("hovered_component", "selection_overlay", fill="#00838f", width=7)
        oval("selected_candidate", fill="", outline="#1565c0", width=3)
        oval("formal_start", fill="", outline="#1b5e20", width=2)
        oval("formal_end", fill="", outline="#1b5e20", width=2)
        oval("pending_start", fill="#1565c0", outline="#0d47a1", width=2)
        oval("pending_end", fill="#d32f2f", outline="#8e0000", width=2)
        oval("hovered_candidate", fill="#fb8c00", outline="#e65100", width=3)
        if "candidate_tooltip" not in scene.selection_items:
            renderer.create_text(
                "selection_overlay",
                0,
                0,
                overlay_key="candidate_tooltip",
                text="",
                fill="#e65100",
                anchor="sw",
                justify="left",
                font=("Arial", 9, "bold"),
                state="hidden",
            )
        if "component_tooltip_bg" not in scene.selection_items:
            renderer.create_rectangle(
                "selection_overlay",
                0,
                0,
                0,
                0,
                overlay_key="component_tooltip_bg",
                fill="#e0f7fa",
                outline="#00838f",
                state="hidden",
            )
        if "component_tooltip" not in scene.selection_items:
            renderer.create_text(
                "selection_overlay",
                0,
                0,
                overlay_key="component_tooltip",
                text="",
                fill="#004d40",
                anchor="nw",
                justify="left",
                font=("Arial", 9),
                state="hidden",
            )
        if not scene.temporary_line_items:
            line(
                "pending_line",
                "temporary_overlay",
                fill="#ef6c00",
                width=3,
                dash=(8, 4),
            )

    def _set_overlay_line(
        self,
        key: str,
        member: Waler | Strut | Brace | AuxiliaryComponent | None,
    ) -> None:
        if self.preview_renderer is None:
            return
        item_id = self.preview_scene.selection_items.get(key)
        if not item_id:
            return
        if member is None:
            self.canvas.itemconfigure(item_id, state="hidden")
            return
        if isinstance(member, Column):
            reference = member.reference_point or _midpoint(member.start, member.end)
            x, y = self._project_preview_point(reference)
            self.canvas.coords(item_id, x - 7, y, x + 7, y)
            self.canvas.itemconfigure(item_id, state="normal")
            return
        if isinstance(member, Beam) and member.path:
            self.canvas.coords(
                item_id,
                *(
                    coordinate
                    for point in member.path
                    for coordinate in self._project_preview_point(point)
                ),
            )
            self.canvas.itemconfigure(item_id, state="normal")
            return
        self.canvas.coords(
            item_id,
            *self._project_preview_point(member.start),
            *self._project_preview_point(member.end),
        )
        self.canvas.itemconfigure(item_id, state="normal")

    def _set_overlay_marker(
        self,
        key: str,
        candidate: CandidatePoint | None,
        radius: int,
    ) -> None:
        item_id = self.preview_scene.selection_items.get(key)
        if not item_id:
            return
        if candidate is None:
            self.canvas.itemconfigure(item_id, state="hidden")
            return
        x, y = self._candidate_canvas_point(candidate)
        self.canvas.coords(
            item_id,
            x - radius,
            y - radius,
            x + radius,
            y + radius,
        )
        self.canvas.itemconfigure(item_id, state="normal")

    def _update_preview_selection_overlay(
        self,
        *,
        update_associations: bool = False,
    ) -> None:
        if self.preview_transform is None or self.preview_renderer is None:
            return
        started_at = time.perf_counter()
        self._ensure_preview_overlay_items()
        state = self.selection_state
        member = self._selected_member()
        hovered_member = self._member_by_id(state.hovered_component_id)
        self._set_overlay_line("selected_component", member)
        self._set_overlay_line("hovered_component", hovered_member)
        if update_associations:
            for key in tuple(self.preview_scene.selection_items):
                if not key.startswith("associated::"):
                    continue
                item_id = self.preview_scene.selection_items.pop(key)
                self.canvas.delete(item_id)
            if isinstance(member, Strut):
                associated_ids = (
                    *member.associated_columns,
                    *member.associated_beams,
                )
                for associated_id in associated_ids:
                    associated = self._member_by_id(associated_id)
                    if associated is None:
                        continue
                    associated_points = (
                        associated.path
                        if isinstance(associated, Beam) and associated.path
                        else (associated.start, associated.end)
                    )
                    self.preview_renderer.create_line(
                        "selection_overlay",
                        *(
                            coordinate
                            for point in associated_points
                            for coordinate in self._project_preview_point(point)
                        ),
                        overlay_key=f"associated::{associated_id}",
                        fill="#1565c0",
                        width=5,
                        dash=(3, 2),
                    )
        point = lambda point_id: self.candidate_point_store.get(
            state.selected_component_id,
            point_id,
        )
        self._set_overlay_marker(
            "selected_candidate",
            point(state.selected_candidate_point_id),
            9,
        )
        self._set_overlay_marker("formal_start", point(state.selected_start_point_id), 8)
        self._set_overlay_marker("formal_end", point(state.selected_end_point_id), 8)
        self._set_overlay_marker("pending_start", point(state.pending_start_point_id), 6)
        self._set_overlay_marker("pending_end", point(state.pending_end_point_id), 6)
        hovered_point = point(state.hovered_candidate_point_id)
        self._set_overlay_marker("hovered_candidate", hovered_point, 9)
        tooltip_id = self.preview_scene.selection_items.get("candidate_tooltip")
        if tooltip_id:
            if hovered_point is None:
                self.canvas.itemconfigure(tooltip_id, state="hidden")
            else:
                x, y = self._candidate_canvas_point(hovered_point)
                endpoint_hint = ""
                if state.mode == "idle":
                    if hovered_point.id == state.pending_start_point_id:
                        endpoint_hint = "\n點擊此藍色點：重新選擇起點"
                    elif hovered_point.id == state.pending_end_point_id:
                        endpoint_hint = "\n點擊此紅色點：重新選擇終點"
                elif state.mode == "pick_start":
                    endpoint_hint = "\n點擊：設為待套用起點"
                elif state.mode == "pick_end":
                    endpoint_hint = "\n點擊：設為待套用終點"
                self.canvas.coords(tooltip_id, x + 10, y - 10)
                self.canvas.itemconfigure(
                    tooltip_id,
                    text=(
                        f"{hovered_point.id}  {hovered_point.label}\n"
                        f"World ({hovered_point.world_point[0]:.3f}, "
                        f"{hovered_point.world_point[1]:.3f})\n"
                        f"Local ({hovered_point.local_point[0]:.3f}, "
                        f"{hovered_point.local_point[1]:.3f})"
                        f"{endpoint_hint}"
                    ),
                    state="normal",
                )
        bg_id = self.preview_scene.selection_items.get("component_tooltip_bg")
        text_id = self.preview_scene.selection_items.get("component_tooltip")
        if bg_id and text_id:
            if hovered_member is None:
                self.canvas.itemconfigure(bg_id, state="hidden")
                self.canvas.itemconfigure(text_id, state="hidden")
            else:
                width = max(self.canvas.winfo_width(), 100)
                _role, role_label = self._member_role(hovered_member)
                self.canvas.coords(bg_id, width - 330, 10, width - 10, 75)
                self.canvas.coords(text_id, width - 320, 17)
                self.canvas.itemconfigure(bg_id, state="normal")
                self.canvas.itemconfigure(
                    text_id,
                    text=(
                        f"{hovered_member.id}｜{role_label}\n"
                        f"圖層：{hovered_member.source_layer}\n"
                        "工程線來源："
                        f"{self._selection_source_label(hovered_member.selection_source)}"
                    ),
                    state="normal",
                )
        self.canvas.tag_raise("selection_overlay")
        self.performance_diagnostics.selection_overlay_updates += 1
        self.performance_diagnostics.record("selection_overlay", started_at)

    def _update_temporary_line_overlay(self) -> None:
        if self.preview_transform is None or self.preview_renderer is None:
            return
        started_at = time.perf_counter()
        self._ensure_preview_overlay_items()
        item_id = (
            self.preview_scene.temporary_line_items[0]
            if self.preview_scene.temporary_line_items
            else 0
        )
        member = self._selected_member()
        state = self.selection_state
        if not item_id or member is None:
            if item_id:
                self.canvas.itemconfigure(item_id, state="hidden")
            return
        start = self.candidate_point_store.get(
            member.id,
            state.pending_start_point_id,
        )
        end = self.candidate_point_store.get(
            member.id,
            state.pending_end_point_id,
        )
        hovered = self.candidate_point_store.get(
            member.id,
            state.hovered_candidate_point_id,
        )
        preview_start = hovered if state.mode == "pick_start" and hovered else start
        preview_end = hovered if state.mode == "pick_end" and hovered else end
        pending_changed = (
            state.pending_start_point_id != state.selected_start_point_id
            or state.pending_end_point_id != state.selected_end_point_id
            or state.mode in {"pick_start", "pick_end"}
        )
        if preview_start is None or preview_end is None or not pending_changed:
            self.canvas.itemconfigure(item_id, state="hidden")
        else:
            self.canvas.coords(
                item_id,
                *self._candidate_canvas_point(preview_start),
                *self._candidate_canvas_point(preview_end),
            )
            self.canvas.itemconfigure(item_id, state="normal")
            self.canvas.tag_raise("temporary_overlay")
        self.performance_diagnostics.temporary_overlay_updates += 1
        self.performance_diagnostics.record("temporary_overlay", started_at)

    def _draw_coordinate_axis_layer(self) -> None:
        if (
            self.result is None
            or self.preview_renderer is None
            or self.preview_view_bounds is None
        ):
            return
        renderer = self.preview_renderer
        coordinate_system = self.result.coordinate_system
        min_x, max_x, min_y, max_y = self.preview_view_bounds
        display_origin = coordinate_system.transform(
            (coordinate_system.origin_x, coordinate_system.origin_y)
        )
        if (
            min_x <= display_origin[0] <= max_x
            and min_y <= display_origin[1] <= max_y
        ):
            x_start = self._project_preview_point((min_x, display_origin[1]))
            x_end = self._project_preview_point((max_x, display_origin[1]))
            y_start = self._project_preview_point((display_origin[0], min_y))
            y_end = self._project_preview_point((display_origin[0], max_y))
            renderer.create_line(
                "coordinate_axis", *x_start, *x_end, fill="#000000", width=1
            )
            renderer.create_line(
                "coordinate_axis", *y_start, *y_end, fill="#000000", width=1
            )
            renderer.create_text(
                "coordinate_axis",
                x_end[0] - 4,
                x_end[1] - 10,
                text="X Axis",
                fill="#000000",
                anchor="e",
                font=("Arial", 9, "bold"),
            )
            renderer.create_text(
                "coordinate_axis",
                y_end[0] + 7,
                y_end[1] + 4,
                text="Y Axis",
                fill="#000000",
                anchor="nw",
                font=("Arial", 9, "bold"),
            )
        coordinate_mode = (
            "Local Coordinates"
            if coordinate_system.mode == "local"
            else "World Coordinates"
        )
        information = (
            f"Coordinate System: {coordinate_mode}\n"
            f"Origin: ({coordinate_system.origin_x:.3f}, "
            f"{coordinate_system.origin_y:.3f})\n"
            f"Zoom: {getattr(self, 'preview_zoom_factor', 1.0):.2f}x"
        )
        renderer.create_rectangle(
            "coordinate_axis",
            10,
            10,
            305,
            72,
            fill="#ffffff",
            outline="#cfd8dc",
        )
        renderer.create_text(
            "coordinate_axis",
            18,
            16,
            text=information,
            fill="#000000",
            anchor="nw",
            justify="left",
            font=("Arial", 9),
        )

    def _update_source_layer_visibility(self) -> None:
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        try:
            canvas.itemconfigure(
                "source_geometry",
                state="normal" if self.show_source_var.get() else "hidden",
            )
            canvas.itemconfigure(
                "auxiliary_geometry",
                state="normal" if self.show_auxiliary_var.get() else "hidden",
            )
            if not self.show_source_var.get():
                for handle in self.focus_handles:
                    for item_id in self.preview_scene.source_handle_items.get(
                        handle,
                        (),
                    ):
                        canvas.itemconfigure(item_id, state="normal")
        except self.tk.TclError:
            return

    def _sync_tree_selections_from_state(self) -> None:
        member_id = self.selection_state.selected_component_id
        if member_id:
            self.member_tree_selection.select(f"member_{member_id}")
        if hasattr(self, "candidate_tree_adapter"):
            self.candidate_tree_adapter.sync_selection(
                self.selection_state.selected_candidate_point_id
            )

    def _update_performance_diagnostics_display(self) -> None:
        if not hasattr(self, "performance_diagnostics_var"):
            return
        if not self.performance_diagnostics_enabled_var.get():
            self.performance_diagnostics_var.set("效能診斷：未啟用")
            return
        item_count = self.performance_diagnostics.canvas_item_count
        try:
            if getattr(self, "canvas", None) is not None:
                item_count = len(self.canvas.find_all())
        except self.tk.TclError:
            pass
        self.performance_diagnostics.canvas_item_count = item_count
        values = self.performance_diagnostics
        self.performance_diagnostics_var.set(
            "Full {0}｜Members {1}｜Candidates {2}｜Selection {3}｜"
            "Temp {4}｜Tree {5}｜Items {6}｜Pending {7}｜Calls {8}｜No-op {9}".format(
                values.full_scene_rebuilds,
                values.engineering_member_rebuilds,
                values.candidate_layer_rebuilds,
                values.selection_overlay_updates,
                values.temporary_overlay_updates,
                values.candidate_tree_rebuilds,
                values.canvas_item_count,
                "是" if self.render_scheduler.pending else "否",
                values.selection_controller_calls,
                values.idempotent_skips,
            )
        )

    def _apply(self) -> None:
        from tkinter import messagebox

        if self.result is None or not self.result.can_import or not self.coordinate_valid:
            return
        member = self._selected_member()
        if member is not None and (
            self.selection_state.pending_start_point_id
            != member.selected_start_point_id
            or self.selection_state.pending_end_point_id
            != member.selected_end_point_id
        ):
            if not messagebox.askyesno(
                "尚有未套用的工程線修正",
                "目前起終點只存在於待套用狀態。\n"
                "若繼續，Solver 將使用原本正式工程線。\n\n"
                "確定不套用本次修改並繼續匯入嗎？",
                parent=self.window,
            ):
                return
        warning_count = sum(message.severity == "warning" for message in self.result.messages)
        if warning_count and not messagebox.askyesno(
            "仍有警告",
            f"目前仍有 {warning_count} 項警告。\n建議先修正警告後再匯入。\n\n確定仍要匯入嗎？",
            parent=self.window,
        ):
            return
        self.import_mode = self.mode_var.get()
        self._save_ui_state()
        self.window.destroy()

    def _cancel(self) -> None:
        self.result = None
        self._save_ui_state()
        self.window.destroy()


__all__ = [
    "AuxiliaryComponent",
    "Beam",
    "BeamCrossing",
    "BlockInstanceInfo",
    "Brace",
    "CandidatePoint",
    "CandidatePointStore",
    "CandidateTreeAdapter",
    "Column",
    "CoordinateSystem",
    "CornerBrace",
    "DEFAULT_LAYER_MAPPING",
    "DXFImportDialog",
    "DXFImportError",
    "DXFImporter",
    "DXFImportResult",
    "EngineeringLineCandidate",
    "EntityDebugInfo",
    "GeometryTolerances",
    "LayerInfo",
    "ImportModelController",
    "PerformanceDiagnostics",
    "PreviewRenderer",
    "PreviewScene",
    "RenderDirty",
    "RenderScheduler",
    "SelectionController",
    "SelectionState",
    "ProblemRecord",
    "SourceGeometry",
    "Strut",
    "ValidationMessage",
    "ValidationOverviewItem",
    "Waler",
    "TreeSelectionSynchronizer",
    "add_cad_candidate_points",
    "apply_candidate_point_selection",
    "apply_coordinate_system",
    "attach_auxiliary_components",
    "build_problem_records",
    "build_validation_overview",
    "connect_components_to_walers",
    "coordinate_system_from_candidate",
    "fit_window_geometry_to_work_areas",
    "import_dxf",
    "normalize_project_coordinate",
    "outline_centerline",
    "parse_coordinate_origin",
    "read_dxf_layers",
    "rectangle_centerline",
    "select_engineering_line",
    "set_cad_engineering_line",
]
