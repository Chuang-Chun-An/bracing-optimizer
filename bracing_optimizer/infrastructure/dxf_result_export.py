"""Build a clean DXF containing imported engineering geometry and solved results."""

from __future__ import annotations

import math
import os
import re
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import ezdxf
from ezdxf.audit import AuditError
from ezdxf.lldxf import validator
from ezdxf.math import Matrix44


APP_ID = "SUPPORT_DISTRIBUTION_UV"
CLEAN_EXPORT_MARKER = "clean_dxf_export_v1"
RESULT_EXPORT_MARKER = "dxf_result_export_v1"
DIMSTYLE_NAME = "SUPPORT_SEGMENT"
JACK_BLOCK_NAME = "SUPPORT_JACK"
RESULT_WALER_LAYER = "SD_RESULT_WALER"
RESULT_SUPPORT_LAYER = "SD_RESULT_SUPPORT"
CLEAN_DXF_VERSION = "R2018"
CLEAN_DXF_ACAD_VERSION = "AC1032"
DRAWING_UNITS = "mm"
INSUNITS_MILLIMETERS = 4
WORLD_COORDINATE_TOLERANCE_MM = 0.1
BACKGROUND_ROLES = (
    "waler",
    "strut",
    "brace",
    "corner_brace",
    "column",
    "beam",
    "auxiliary",
)
DEFAULT_JACK_ASSET = (
    Path(__file__).resolve().parents[2] / "assets" / "dxf" / "jack_symbol.dxf"
)

_HANDLE_RE = re.compile(r"\(#([0-9A-F]+)\)", re.IGNORECASE)
_OWNER_RE = re.compile(r"owner handle #([0-9A-F]+)", re.IGNORECASE)
_RAW_POINTER_CODES = (
    frozenset(range(320, 370))
    | frozenset(range(390, 400))
    | frozenset({480, 481, 1005})
)
_CONVERTED_ROLE_KEYS = (
    ("walers", "waler"),
    ("struts", "strut"),
    ("braces", "brace"),
    ("corner_braces", "corner_brace"),
    ("columns", "column"),
    ("beams", "beam"),
)


class DXFResultExportError(ValueError):
    """Raised when a clean result DXF cannot be built safely."""


class DXFExportValidationError(DXFResultExportError):
    """Raised when the staged clean DXF cannot be safely delivered."""

    def __init__(
        self,
        message: str,
        *,
        temporary_path: Path | None = None,
        final_audit: "DXFAuditSummary | None" = None,
    ) -> None:
        super().__init__(message)
        self.temporary_path = temporary_path
        self.final_audit = final_audit


@dataclass(frozen=True)
class ExportPiece:
    kind: str
    length: float


@dataclass(frozen=True)
class MemberExportPlan:
    member_id: str
    role: str
    pieces: tuple[ExportPiece, ...]
    gap: float = 0.0
    result_id: str = ""


@dataclass(frozen=True)
class MemberBinding:
    member_id: str
    role: str
    layer: str
    world_start: tuple[float, float]
    world_end: tuple[float, float]


@dataclass(frozen=True)
class DXFExportOptions:
    dimension_offset_mm: float = 650.0
    dimension_text_height_mm: float = 250.0
    dimension_arrow_size_mm: float = 150.0
    annotate_gap: bool = True


@dataclass(frozen=True)
class DXFAuditIssue:
    disposition: str
    code: int
    issue_type: str
    message: str
    handle: str | None = None
    owner_handle: str | None = None
    entity_type: str | None = None


@dataclass(frozen=True)
class DXFAuditSummary:
    errors: tuple[DXFAuditIssue, ...] = ()
    fixes: tuple[DXFAuditIssue, ...] = ()
    error_types: tuple[tuple[str, int], ...] = ()
    fix_types: tuple[tuple[str, int], ...] = ()

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def fix_count(self) -> int:
        return len(self.fixes)

    def error_type_summary(self) -> str:
        return "、".join(
            f"{issue_type} {count}項" for issue_type, count in self.error_types
        ) or "無"

    def fix_type_summary(self) -> str:
        return "、".join(
            f"{issue_type} {count}項" for issue_type, count in self.fix_types
        ) or "無"


@dataclass(frozen=True)
class LayerNameFallback:
    role: str
    original_name: str
    output_name: str
    reason: str


@dataclass(frozen=True)
class DXFExportReport:
    output_path: str
    member_count: int
    dimension_count: int
    jack_count: int
    waler_count: int
    strut_count: int
    dxf_version: str
    coordinate_units: str
    coordinate_mode: str
    background_layer_count: int
    background_segment_count: int
    background_counts: tuple[tuple[str, int], ...]
    result_waler_count: int
    result_support_count: int
    final_audit: DXFAuditSummary
    actual_dimension_count: int
    actual_jack_count: int
    layer_name_fallbacks: tuple[LayerNameFallback, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def merge_guidance(self) -> str:
        return (
            "本檔為乾淨的支撐配置成果DXF，使用原始世界座標建立。"
            "可由AutoCAD或progeCAD以Insert、Xref或貼到原始座標方式合併回原始DWG。"
            "目標圖面單位確認為毫米後，請避免額外縮放、旋轉或人工位移。"
        )


@dataclass(frozen=True)
class _BackgroundSegment:
    role: str
    original_layer: str
    world_start: tuple[float, float]
    world_end: tuple[float, float]
    source_kind: str
    source_id: str


@dataclass(frozen=True)
class _PreparedBackgroundSegment:
    index: int
    role: str
    original_layer: str
    output_layer: str
    world_start: tuple[float, float]
    world_end: tuple[float, float]
    source_kind: str
    source_id: str


@dataclass(frozen=True)
class _ExpectedResultEntity:
    role: str
    member_id: str
    item_type: str
    index: int
    output_layer: str
    point1: tuple[float, float]
    point2: tuple[float, float] | None = None
    display_text: str | None = None


@dataclass(frozen=True)
class _CleanValidationResult:
    final_audit: DXFAuditSummary
    actual_dimension_count: int
    actual_jack_count: int


def _number(value: Any, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DXFResultExportError(f"{field_name} 必須是數字") from exc
    if not math.isfinite(number):
        raise DXFResultExportError(f"{field_name} 必須是有限數字")
    return number


def _point(value: Any, field_name: str) -> tuple[float, float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DXFResultExportError(f"{field_name} 缺少有效座標")
    if len(value) < 2:
        raise DXFResultExportError(f"{field_name} 缺少有效座標")
    return _number(value[0], f"{field_name}.X"), _number(value[1], f"{field_name}.Y")


def _row_points(
    row: Mapping[str, Any],
) -> tuple[tuple[float, float], tuple[float, float]]:
    return (
        (
            _number(row.get("StartX"), "StartX"),
            _number(row.get("StartY"), "StartY"),
        ),
        (
            _number(row.get("EndX"), "EndX"),
            _number(row.get("EndY"), "EndY"),
        ),
    )


def _endpoint_error(
    row_line: tuple[tuple[float, float], tuple[float, float]],
    candidate_line: tuple[tuple[float, float], tuple[float, float]],
) -> float:
    return min(
        math.dist(row_line[0], candidate_line[0])
        + math.dist(row_line[1], candidate_line[1]),
        math.dist(row_line[0], candidate_line[1])
        + math.dist(row_line[1], candidate_line[0]),
    )


def _coordinate_data(
    dxf_import_state: Mapping[str, Any],
) -> tuple[str, float, float]:
    coordinate = dxf_import_state.get("coordinate_system")
    if not isinstance(coordinate, Mapping):
        raise DXFResultExportError("缺少DXF世界座標轉換資訊")
    mode = str(coordinate.get("mode", "")).strip().lower()
    if mode not in {"world", "local"}:
        raise DXFResultExportError(f"不支援的DXF座標模式：{mode or '空白'}")
    origin_x = _number(coordinate.get("origin_x", 0.0), "DXF origin_x")
    origin_y = _number(coordinate.get("origin_y", 0.0), "DXF origin_y")
    return mode, origin_x, origin_y


def _local_to_world(
    point: tuple[float, float],
    coordinate: tuple[str, float, float],
) -> tuple[float, float]:
    mode, origin_x, origin_y = coordinate
    if mode == "local":
        return point[0] + origin_x, point[1] + origin_y
    return point


def _member_world_line(
    item: Mapping[str, Any],
    coordinate: tuple[str, float, float],
    field_name: str,
) -> tuple[tuple[float, float], tuple[float, float]]:
    if item.get("world_start") is not None and item.get("world_end") is not None:
        return (
            _point(item.get("world_start"), f"{field_name}.world_start"),
            _point(item.get("world_end"), f"{field_name}.world_end"),
        )
    if item.get("local_start") is not None and item.get("local_end") is not None:
        return (
            _local_to_world(
                _point(item.get("local_start"), f"{field_name}.local_start"),
                coordinate,
            ),
            _local_to_world(
                _point(item.get("local_end"), f"{field_name}.local_end"),
                coordinate,
            ),
        )
    start = _point(item.get("start"), f"{field_name}.start")
    end = _point(item.get("end"), f"{field_name}.end")
    return _local_to_world(start, coordinate), _local_to_world(end, coordinate)


def build_member_bindings(
    dxf_import_state: Mapping[str, Any],
    walers: Sequence[Mapping[str, Any]],
    struts: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], MemberBinding]:
    """Map Solver rows to confirmed imported members using precise world geometry."""

    converted = dxf_import_state.get("converted")
    if not isinstance(converted, Mapping):
        raise DXFResultExportError("專案未保存可用的DXF工程模型")
    coordinate = _coordinate_data(dxf_import_state)
    bindings: dict[tuple[str, str], MemberBinding] = {}
    specs = (
        ("waler", "walers", "WalerID", walers),
        ("strut", "struts", "StrutID", struts),
    )
    for role, converted_key, id_field, rows in specs:
        candidates = [
            item
            for item in converted.get(converted_key, ())
            if isinstance(item, Mapping)
        ]
        row_items = []
        for row in rows:
            member_id = str(row.get(id_field, "") or "").strip()
            if member_id:
                row_items.append((member_id, _row_points(row)))
        candidate_active_lines = [
            (
                _point(item.get("start"), f"{converted_key}[{index}].start"),
                _point(item.get("end"), f"{converted_key}[{index}].end"),
            )
            for index, item in enumerate(candidates)
        ]
        candidate_world_lines = [
            _member_world_line(item, coordinate, f"{converted_key}[{index}]")
            for index, item in enumerate(candidates)
        ]

        pair_options = sorted(
            (
                _endpoint_error(row_line, candidate_line),
                row_index,
                candidate_index,
            )
            for row_index, (_member_id, row_line) in enumerate(row_items)
            for candidate_index, candidate_line in enumerate(candidate_active_lines)
        )
        row_matches: dict[int, int] = {}
        used_candidates: set[int] = set()
        for error, row_index, candidate_index in pair_options:
            if error > 100.0:
                break
            if row_index in row_matches or candidate_index in used_candidates:
                continue
            row_matches[row_index] = candidate_index
            used_candidates.add(candidate_index)

        for row_index, (member_id, row_line) in enumerate(row_items):
            candidate_index = row_matches.get(row_index)
            # An ID identifies the Solver result only after geometry has
            # matched.  It must never authorize reuse of stale world points.
            if candidate_index is None:
                continue
            candidate = candidates[candidate_index]
            layer = str(candidate.get("source_layer", "") or "").strip()
            active_start, active_end = candidate_active_lines[candidate_index]
            world_start, world_end = candidate_world_lines[candidate_index]
            direct = math.dist(row_line[0], active_start) + math.dist(
                row_line[1], active_end
            )
            reverse = math.dist(row_line[0], active_end) + math.dist(
                row_line[1], active_start
            )
            if reverse < direct:
                world_start, world_end = world_end, world_start
            if math.dist(world_start, world_end) <= 1e-9:
                raise DXFResultExportError(f"{member_id} 起終點不可相同")
            bindings[(role, member_id)] = MemberBinding(
                member_id,
                role,
                layer,
                world_start,
                world_end,
            )
    return bindings


def _ensure_dimstyle(document, options: DXFExportOptions) -> None:
    style = (
        document.dimstyles.get(DIMSTYLE_NAME)
        if DIMSTYLE_NAME in document.dimstyles
        else document.dimstyles.new(DIMSTYLE_NAME)
    )
    style.dxf.dimtxt = options.dimension_text_height_mm
    style.dxf.dimasz = options.dimension_arrow_size_mm
    style.dxf.dimdec = 0
    style.dxf.dimgap = max(50.0, options.dimension_text_height_mm * 0.3)
    style.dxf.dimexo = 100.0
    style.dxf.dimexe = 150.0


def _ensure_appid(document) -> None:
    if APP_ID not in document.appids:
        document.appids.new(APP_ID)


def _ensure_jack_block(document, jack_asset_path: Path) -> None:
    if JACK_BLOCK_NAME in document.blocks:
        return
    if not jack_asset_path.is_file():
        raise DXFResultExportError(f"找不到千斤頂DXF資產：{jack_asset_path}")
    asset_document = ezdxf.readfile(jack_asset_path)
    try:
        asset_block = asset_document.blocks.get(JACK_BLOCK_NAME)
    except ezdxf.DXFKeyError as exc:
        raise DXFResultExportError(
            f"千斤頂DXF資產缺少圖塊：{JACK_BLOCK_NAME}"
        ) from exc

    target_block = document.blocks.new(JACK_BLOCK_NAME, base_point=(0, 0, 0))
    block_attribs = {"layer": "0", "color": 256, "linetype": "BYLAYER"}
    for entity in asset_block:
        if entity.dxftype() == "LINE":
            target_block.add_line(
                entity.dxf.start,
                entity.dxf.end,
                dxfattribs=block_attribs,
            )
        elif entity.dxftype() == "CIRCLE":
            target_block.add_circle(
                entity.dxf.center,
                entity.dxf.radius,
                dxfattribs=block_attribs,
            )
        else:
            raise DXFResultExportError(
                f"千斤頂DXF資產含不支援實體：{entity.dxftype()}"
            )


def _station_point(binding: MemberBinding, station: float) -> tuple[float, float]:
    dx = binding.world_end[0] - binding.world_start[0]
    dy = binding.world_end[1] - binding.world_start[1]
    length = math.hypot(dx, dy)
    return (
        binding.world_start[0] + dx / length * station,
        binding.world_start[1] + dy / length * station,
    )


def _local_station_point(
    binding: MemberBinding,
    station: float,
) -> tuple[float, float]:
    """Return a station in member-local coordinates near the origin."""

    dx = binding.world_end[0] - binding.world_start[0]
    dy = binding.world_end[1] - binding.world_start[1]
    length = math.hypot(dx, dy)
    return dx / length * station, dy / length * station


def _transform_rendered_dimension_to_world(
    dimension,
    binding: MemberBinding,
) -> None:
    """Translate a fully rendered local DIMENSION and its block to WCS.

    ``Dimension.transform()`` transforms the DIMENSION definition points and
    its private anonymous geometry block together.  Therefore LINE, MTEXT,
    SOLID and INSERT primitives (plus POINT/ARC/TEXT when emitted by another
    arrow or style) cannot be left behind in local coordinates.
    """

    entity = dimension.dimension
    geometry = entity.dxf.get("geometry")
    if not geometry or geometry not in entity.doc.blocks:
        raise DXFResultExportError("Local Dimension render未建立匿名Block")
    if entity.dxf.hasattr("insert"):
        raise DXFResultExportError("不支援共用匿名Block的Dimension轉換")
    rendered_entities = tuple(entity.doc.blocks.get(geometry))
    if not rendered_entities:
        raise DXFResultExportError("Local Dimension匿名Block內容為空")
    entity.transform(
        Matrix44.translate(
            binding.world_start[0],
            binding.world_start[1],
            0.0,
        )
    )


def _set_result_xdata(
    entity,
    plan: MemberExportPlan,
    item_type: str,
    index: int,
) -> None:
    entity.set_xdata(
        APP_ID,
        [
            (1000, RESULT_EXPORT_MARKER),
            (1000, plan.role),
            (1000, plan.member_id),
            (1000, plan.result_id),
            (1000, item_type),
            (1071, index),
        ],
    )


def _add_dimension(
    modelspace,
    binding: MemberBinding,
    plan: MemberExportPlan,
    start_station: float,
    end_station: float,
    text: str,
    index: int,
    options: DXFExportOptions,
    output_layer: str,
) -> None:
    # All construction and rendering is intentionally performed in a member-
    # local coordinate system.  Rendering near-vertical DIMENSION entities at
    # large WCS coordinates causes catastrophic cancellation in ezdxf's ray
    # intersection calculations and corrupts the anonymous block text.
    dimension = modelspace.add_aligned_dim(
        p1=_local_station_point(binding, start_station),
        p2=_local_station_point(binding, end_station),
        distance=options.dimension_offset_mm,
        text=text,
        dimstyle=DIMSTYLE_NAME,
        dxfattribs={"layer": output_layer, "color": 256},
    )
    dimension.render()
    _transform_rendered_dimension_to_world(dimension, binding)
    _set_result_xdata(dimension.dimension, plan, "dimension", index)


def _normalize_plans(plans: Iterable[MemberExportPlan]) -> tuple[MemberExportPlan, ...]:
    normalized = []
    owners: dict[tuple[str, str], list[str]] = {}
    for plan in plans:
        member_id = str(plan.member_id).strip()
        role = str(plan.role).strip().lower()
        if not member_id:
            raise DXFResultExportError("匯出構件不可缺少編號")
        key = (role, member_id)
        owners.setdefault(key, []).append(str(plan.result_id or "未命名方案"))
        if role not in {"waler", "strut"}:
            raise DXFResultExportError(f"不支援的匯出構件類型：{role}")
        if not plan.pieces:
            raise DXFResultExportError(f"{member_id} 沒有可匯出的配置分段")
        normalized_pieces = tuple(
            ExportPiece(
                str(piece.kind).strip().lower(),
                _number(piece.length, f"{member_id} 分段長度"),
            )
            for piece in plan.pieces
        )
        unsupported = sorted(
            {piece.kind for piece in normalized_pieces}
            - {"steel", "shim", "jack"}
        )
        if unsupported:
            raise DXFResultExportError(
                f"{member_id} 含不支援的分段類型：{', '.join(unsupported)}"
            )
        if any(piece.length <= 0 for piece in normalized_pieces):
            raise DXFResultExportError(f"{member_id} 的分段長度必須大於0")
        gap = _number(plan.gap, f"{member_id} 餘量")
        if gap < 0:
            raise DXFResultExportError(f"{member_id} 的餘量不可小於0")
        normalized.append(
            MemberExportPlan(
                member_id,
                role,
                normalized_pieces,
                gap,
                str(plan.result_id),
            )
        )
    conflicts = [
        f"{role} {member_id}: {', '.join(result_ids)}"
        for (role, member_id), result_ids in owners.items()
        if len(result_ids) > 1
    ]
    if conflicts:
        raise DXFResultExportError(
            "同一構件不可同時匯出多個方案：\n" + "\n".join(conflicts)
        )
    return tuple(normalized)


def _segment_key(segment: _BackgroundSegment) -> tuple[Any, ...]:
    scale = 1.0 / WORLD_COORDINATE_TOLERANCE_MM

    def point_key(point):
        return round(point[0] * scale), round(point[1] * scale)

    first = point_key(segment.world_start)
    second = point_key(segment.world_end)
    ordered = (first, second) if first <= second else (second, first)
    return segment.role, segment.original_layer.casefold(), *ordered


def _append_segment(
    output: list[_BackgroundSegment],
    seen: set[tuple[Any, ...]],
    segment: _BackgroundSegment,
) -> None:
    if math.dist(segment.world_start, segment.world_end) <= 1e-9:
        return
    key = _segment_key(segment)
    if key not in seen:
        seen.add(key)
        output.append(segment)


def _extract_background_segments(
    dxf_import_state: Mapping[str, Any],
) -> tuple[_BackgroundSegment, ...]:
    """Use saved world geometry plus confirmed final engineering lines only."""

    coordinate = _coordinate_data(dxf_import_state)
    output: list[_BackgroundSegment] = []
    seen: set[tuple[Any, ...]] = set()
    source_geometry = dxf_import_state.get("source_geometry") or ()
    if not isinstance(source_geometry, Sequence):
        raise DXFResultExportError("dxf_import_state.source_geometry 格式錯誤")
    for geometry_index, item in enumerate(source_geometry):
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role", "")).strip().lower()
        if role not in BACKGROUND_ROLES:
            continue
        layer = str(item.get("source_layer", "") or "").strip()
        points_value = item.get("points") or ()
        if not isinstance(points_value, Sequence) or len(points_value) < 2:
            continue
        points = tuple(
            _point(point, f"source_geometry[{geometry_index}].points")
            for point in points_value
        )
        source_id = str(item.get("source_handle", "") or geometry_index)
        pairs = list(zip(points, points[1:]))
        if bool(item.get("closed")) and math.dist(points[-1], points[0]) > 1e-9:
            pairs.append((points[-1], points[0]))
        for start, end in pairs:
            _append_segment(
                output,
                seen,
                _BackgroundSegment(
                    role,
                    layer,
                    start,
                    end,
                    "source_geometry",
                    source_id,
                ),
            )

    converted = dxf_import_state.get("converted")
    if not isinstance(converted, Mapping):
        raise DXFResultExportError("專案未保存人工確認後的正式工程模型")
    for converted_key, role in _CONVERTED_ROLE_KEYS:
        items = converted.get(converted_key) or ()
        if not isinstance(items, Sequence):
            raise DXFResultExportError(f"converted.{converted_key} 格式錯誤")
        for member_index, item in enumerate(items):
            if not isinstance(item, Mapping):
                continue
            member_id = str(item.get("id", "") or f"{role}-{member_index + 1}")
            layer = str(item.get("source_layer", "") or "").strip()
            world_points: tuple[tuple[float, float], ...]
            if role == "beam" and item.get("world_path"):
                world_points = tuple(
                    _point(point, f"converted.beams[{member_index}].world_path")
                    for point in item.get("world_path")
                )
            elif role == "beam" and item.get("local_path"):
                world_points = tuple(
                    _local_to_world(
                        _point(point, f"converted.beams[{member_index}].local_path"),
                        coordinate,
                    )
                    for point in item.get("local_path")
                )
            else:
                world_points = _member_world_line(
                    item,
                    coordinate,
                    f"converted.{converted_key}[{member_index}]",
                )
            if len(world_points) < 2:
                raise DXFResultExportError(f"{member_id} 缺少完整工程線")
            for start, end in zip(world_points, world_points[1:]):
                _append_segment(
                    output,
                    seen,
                    _BackgroundSegment(
                        role,
                        layer,
                        start,
                        end,
                        "confirmed_engineering_model",
                        member_id,
                    ),
                )
    if not output:
        raise DXFResultExportError("工程模型沒有可重建的底圖線段")
    return tuple(output)


def _validate_import_state(dxf_import_state: Mapping[str, Any]) -> None:
    if not isinstance(dxf_import_state, Mapping):
        raise DXFResultExportError("尚未匯入DXF工程模型")
    _coordinate_data(dxf_import_state)
    converted = dxf_import_state.get("converted")
    if not isinstance(converted, Mapping):
        raise DXFResultExportError("舊版專案缺少dxf_import_state構件綁定")
    blocking = [
        item
        for item in dxf_import_state.get("validation_messages", ()) or ()
        if isinstance(item, Mapping)
        and str(item.get("severity", "")).lower() in {"error", "critical"}
    ]
    if blocking:
        messages = [
            str(item.get("message") or item.get("code") or "工程線尚未確認")
            for item in blocking[:10]
        ]
        raise DXFResultExportError(
            "部分DXF構件仍需要人工確認，禁止匯出：\n" + "\n".join(messages)
        )


def _fallback_layer_name(role: str, used_names: set[str]) -> str:
    base = f"SD_BASE_{role.upper()}"
    candidate = base
    index = 2
    while candidate.casefold() in used_names:
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def _prepare_background_layers(
    document,
    segments: Sequence[_BackgroundSegment],
) -> tuple[tuple[_PreparedBackgroundSegment, ...], tuple[LayerNameFallback, ...]]:
    used_names = {str(layer.dxf.name).casefold() for layer in document.layers}
    used_names.update({RESULT_WALER_LAYER.casefold(), RESULT_SUPPORT_LAYER.casefold()})
    mappings: dict[tuple[str, str], str] = {}
    fallbacks: list[LayerNameFallback] = []
    prepared = []
    for index, segment in enumerate(segments, start=1):
        original = segment.original_layer.strip()
        mapping_key = (segment.role, original)
        output_layer = mappings.get(mapping_key)
        if output_layer is None:
            valid = (
                bool(original)
                and len(original) <= 255
                and validator.is_valid_layer_name(original)
                and original.casefold()
                not in {RESULT_WALER_LAYER.casefold(), RESULT_SUPPORT_LAYER.casefold()}
            )
            if valid:
                output_layer = original
            else:
                reason = (
                    "圖層名稱為空"
                    if not original
                    else "圖層名稱非法、過長或與成果層衝突"
                )
                output_layer = _fallback_layer_name(segment.role, used_names)
                fallbacks.append(
                    LayerNameFallback(segment.role, original, output_layer, reason)
                )
            mappings[mapping_key] = output_layer
            used_names.add(output_layer.casefold())
            if output_layer not in document.layers:
                document.layers.add(
                    output_layer,
                    dxfattribs={"color": 7, "linetype": "Continuous"},
                )
        prepared.append(
            _PreparedBackgroundSegment(
                index,
                segment.role,
                segment.original_layer,
                output_layer,
                segment.world_start,
                segment.world_end,
                segment.source_kind,
                segment.source_id,
            )
        )
    return tuple(prepared), tuple(fallbacks)


def _set_background_xdata(entity, segment: _PreparedBackgroundSegment) -> None:
    entity.set_xdata(
        APP_ID,
        [
            (1000, CLEAN_EXPORT_MARKER),
            (1000, "background"),
            (1000, segment.role),
            (1000, segment.output_layer),
            (1000, segment.source_kind),
            (1000, segment.source_id),
            (1071, segment.index),
        ],
    )


def _draw_background(
    document,
    segments: Sequence[_PreparedBackgroundSegment],
) -> None:
    modelspace = document.modelspace()
    for segment in segments:
        entity = modelspace.add_line(
            segment.world_start,
            segment.world_end,
            dxfattribs={
                "layer": segment.output_layer,
                "color": 256,
                "linetype": "BYLAYER",
            },
        )
        _set_background_xdata(entity, segment)


def _new_clean_document(options: DXFExportOptions):
    document = ezdxf.new(CLEAN_DXF_VERSION, setup=True)
    document.header["$INSUNITS"] = INSUNITS_MILLIMETERS
    document.header["$MEASUREMENT"] = 1
    _ensure_appid(document)
    _ensure_dimstyle(document, options)
    document.layers.add(
        RESULT_WALER_LAYER,
        dxfattribs={"color": 1, "linetype": "Continuous"},
    )
    document.layers.add(
        RESULT_SUPPORT_LAYER,
        dxfattribs={"color": 3, "linetype": "Continuous"},
    )
    return document


def _result_layer(role: str) -> str:
    return RESULT_WALER_LAYER if role == "waler" else RESULT_SUPPORT_LAYER


def _draw_results(
    document,
    plans: Sequence[MemberExportPlan],
    bindings: Mapping[tuple[str, str], MemberBinding],
    options: DXFExportOptions,
) -> tuple[tuple[_ExpectedResultEntity, ...], int, int]:
    if any(
        piece.kind == "jack" for plan in plans for piece in plan.pieces
    ):
        _ensure_jack_block(document, DEFAULT_JACK_ASSET)
    modelspace = document.modelspace()
    expected: list[_ExpectedResultEntity] = []
    dimension_count = 0
    jack_count = 0
    for plan in plans:
        binding = bindings[(plan.role, plan.member_id)]
        output_layer = _result_layer(plan.role)
        station = 0.0
        angle = math.degrees(
            math.atan2(
                binding.world_end[1] - binding.world_start[1],
                binding.world_end[0] - binding.world_start[0],
            )
        )
        for index, piece in enumerate(plan.pieces, start=1):
            next_station = station + piece.length
            if piece.kind == "jack":
                point = _station_point(binding, station)
                insert = modelspace.add_blockref(
                    JACK_BLOCK_NAME,
                    point,
                    dxfattribs={
                        "layer": output_layer,
                        "rotation": angle,
                        "xscale": piece.length / 600.0,
                        "yscale": 1.0,
                        "color": 256,
                    },
                )
                _set_result_xdata(insert, plan, "jack", index)
                expected.append(
                    _ExpectedResultEntity(
                        plan.role,
                        plan.member_id,
                        "jack",
                        index,
                        output_layer,
                        point,
                    )
                )
                jack_count += 1
            else:
                point1 = _station_point(binding, station)
                point2 = _station_point(binding, next_station)
                text = "<>" if piece.kind == "steel" else "調整塊 <>"
                _add_dimension(
                    modelspace,
                    binding,
                    plan,
                    station,
                    next_station,
                    text,
                    index,
                    options,
                    output_layer,
                )
                expected.append(
                    _ExpectedResultEntity(
                        plan.role,
                        plan.member_id,
                        "dimension",
                        index,
                        output_layer,
                        point1,
                        point2,
                        text.replace("<>", f"{piece.length:.0f}", 1),
                    )
                )
                dimension_count += 1
            station = next_station
        if options.annotate_gap and plan.gap > 0:
            index = len(plan.pieces) + 1
            point1 = _station_point(binding, station)
            point2 = _station_point(binding, station + plan.gap)
            _add_dimension(
                modelspace,
                binding,
                plan,
                station,
                station + plan.gap,
                "餘量 <>",
                index,
                options,
                output_layer,
            )
            expected.append(
                _ExpectedResultEntity(
                    plan.role,
                    plan.member_id,
                    "dimension",
                    index,
                    output_layer,
                    point1,
                    point2,
                    f"餘量 {plan.gap:.0f}",
                )
            )
            dimension_count += 1
    return tuple(expected), dimension_count, jack_count


def _xdata_values(entity) -> tuple[Any, ...]:
    if not entity.has_xdata(APP_ID):
        return ()
    try:
        return tuple(tag.value for tag in entity.get_xdata(APP_ID))
    except ezdxf.DXFError:
        return ()


def _validate_background(
    document,
    expected: Sequence[_PreparedBackgroundSegment],
) -> None:
    actual: dict[int, Any] = {}
    for entity in document.modelspace():
        values = _xdata_values(entity)
        if len(values) < 7 or values[:2] != (
            CLEAN_EXPORT_MARKER,
            "background",
        ):
            continue
        try:
            index = int(values[6])
        except (TypeError, ValueError):
            raise DXFExportValidationError("底圖實體含無效輸出索引")
        if index in actual:
            raise DXFExportValidationError(f"底圖實體索引重複：{index}")
        actual[index] = entity
    if len(actual) != len(expected):
        raise DXFExportValidationError(
            f"底圖線段實際 {len(actual)}／預期 {len(expected)}"
        )
    for segment in expected:
        entity = actual.get(segment.index)
        if entity is None or entity.dxftype() != "LINE":
            raise DXFExportValidationError(
                f"底圖線段 {segment.index} 遺失或類型錯誤"
            )
        if entity.dxf.layer != segment.output_layer:
            raise DXFExportValidationError(
                f"底圖線段 {segment.index} 圖層錯誤：{entity.dxf.layer}"
            )
        start = tuple(entity.dxf.start)[:2]
        end = tuple(entity.dxf.end)[:2]
        direct = max(
            math.dist(start, segment.world_start),
            math.dist(end, segment.world_end),
        )
        reverse = max(
            math.dist(start, segment.world_end),
            math.dist(end, segment.world_start),
        )
        if min(direct, reverse) > WORLD_COORDINATE_TOLERANCE_MM:
            raise DXFExportValidationError(
                f"底圖線段 {segment.index} 世界座標驗證失敗"
            )


def _result_key(values: Sequence[Any]) -> tuple[str, str, str, int] | None:
    if len(values) < 6 or values[0] != RESULT_EXPORT_MARKER:
        return None
    try:
        index = int(values[5])
    except (TypeError, ValueError):
        return None
    return str(values[1]), str(values[2]), str(values[4]), index


def _validate_results(
    document,
    expected: Sequence[_ExpectedResultEntity],
) -> tuple[int, int]:
    actual: dict[tuple[str, str, str, int], Any] = {}
    for entity in document.modelspace():
        key = _result_key(_xdata_values(entity))
        if key is None:
            continue
        if key in actual:
            raise DXFExportValidationError(f"成果實體索引重複：{key}")
        actual[key] = entity
    if len(actual) != len(expected):
        raise DXFExportValidationError(
            f"配置成果實際 {len(actual)}／預期 {len(expected)}"
        )
    dimension_count = 0
    jack_count = 0
    for item in expected:
        key = (item.role, item.member_id, item.item_type, item.index)
        entity = actual.get(key)
        expected_type = "DIMENSION" if item.item_type == "dimension" else "INSERT"
        if entity is None or entity.dxftype() != expected_type:
            raise DXFExportValidationError(f"配置成果遺失或類型錯誤：{key}")
        if entity.dxf.layer != item.output_layer:
            raise DXFExportValidationError(
                f"配置成果圖層錯誤：{key} 位於 {entity.dxf.layer}"
            )
        if item.item_type == "dimension":
            dimension_count += 1
            geometry = entity.dxf.get("geometry")
            if not geometry or geometry not in document.blocks:
                raise DXFExportValidationError(
                    f"Dimension缺少匿名Block：{entity.dxf.handle}"
                )
            point1 = tuple(entity.dxf.defpoint2)[:2]
            point2 = tuple(entity.dxf.defpoint3)[:2]
            if (
                math.dist(point1, item.point1) > WORLD_COORDINATE_TOLERANCE_MM
                or item.point2 is None
                or math.dist(point2, item.point2) > WORLD_COORDINATE_TOLERANCE_MM
            ):
                raise DXFExportValidationError(
                    f"Dimension世界座標驗證失敗：{entity.dxf.handle}"
                )
            expected_measurement = math.dist(item.point1, item.point2)
            if (
                abs(float(entity.get_measurement()) - expected_measurement)
                > WORLD_COORDINATE_TOLERANCE_MM
            ):
                raise DXFExportValidationError(
                    f"Dimension量測值驗證失敗：{entity.dxf.handle}"
                )
            rendered_text = [
                str(block_entity.dxf.get("text", ""))
                for block_entity in document.blocks.get(geometry)
                if block_entity.dxftype() in {"MTEXT", "TEXT"}
            ]
            if item.display_text is None or item.display_text not in rendered_text:
                raise DXFExportValidationError(
                    f"Dimension顯示值驗證失敗：{entity.dxf.handle}，"
                    f"實際={rendered_text}，預期={item.display_text}"
                )
        else:
            jack_count += 1
            if entity.dxf.get("name") != JACK_BLOCK_NAME:
                raise DXFExportValidationError("Jack INSERT使用錯誤Block definition")
            if (
                math.dist(tuple(entity.dxf.insert)[:2], item.point1)
                > WORLD_COORDINATE_TOLERANCE_MM
            ):
                raise DXFExportValidationError(
                    f"Jack世界座標驗證失敗：{entity.dxf.handle}"
                )
    if jack_count:
        if JACK_BLOCK_NAME not in document.blocks:
            raise DXFExportValidationError(f"缺少Jack Block：{JACK_BLOCK_NAME}")
        if not list(document.blocks.get(JACK_BLOCK_NAME)):
            raise DXFExportValidationError(f"Jack Block內容為空：{JACK_BLOCK_NAME}")
    return dimension_count, jack_count


def _audit_issue_type(code: int) -> str:
    try:
        return AuditError(code).name
    except ValueError:
        return f"AUDIT_CODE_{code}"


def _audit_summary(document) -> DXFAuditSummary:
    ownership = {
        handle: (entity.dxftype(), entity.dxf.get("owner"))
        for handle, entity in document.entitydb.items()
        if entity is not None and entity.is_alive
    }
    auditor = document.audit()

    def convert(issue, disposition):
        message = str(issue.message)
        entity = getattr(issue, "entity", None)
        handle = entity.dxf.get("handle") if entity is not None else None
        if not handle:
            match = _HANDLE_RE.search(message)
            handle = match.group(1).upper() if match else None
        entity_type, owner = ownership.get(handle, (None, None))
        if not owner:
            match = _OWNER_RE.search(message)
            owner = match.group(1).upper() if match else None
        code = int(issue.code)
        return DXFAuditIssue(
            disposition,
            code,
            _audit_issue_type(code),
            message,
            handle,
            owner,
            entity_type,
        )

    errors = tuple(convert(issue, "error") for issue in auditor.errors)
    fixes = tuple(convert(issue, "fix") for issue in auditor.fixes)
    return DXFAuditSummary(
        errors,
        fixes,
        tuple(sorted(Counter(issue.issue_type for issue in errors).items())),
        tuple(sorted(Counter(issue.issue_type for issue in fixes).items())),
    )


def _raw_dxf_records(path: Path) -> list[list[tuple[int, str]]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    pairs: list[tuple[int, str]] = []
    for index in range(0, len(lines) - 1, 2):
        try:
            code = int(lines[index].strip())
        except ValueError as exc:
            raise DXFExportValidationError(
                f"DXF group code格式錯誤，行號 {index + 1}"
            ) from exc
        pairs.append((code, lines[index + 1].strip()))
    records: list[list[tuple[int, str]]] = []
    record: list[tuple[int, str]] = []
    for pair in pairs:
        if pair[0] == 0 and record:
            records.append(record)
            record = []
        record.append(pair)
    if record:
        records.append(record)
    return records


def _validate_raw_handle_references(path: Path, document) -> None:
    defined = {
        str(handle).upper()
        for handle, entity in document.entitydb.items()
        if entity is not None and entity.is_alive
    }
    invalid = []
    for record in _raw_dxf_records(path):
        entity_type = next((value for code, value in record if code == 0), "?")
        handle = next(
            (value.upper() for code, value in record if code in {5, 105}),
            None,
        )
        for code, value in record:
            pointer = value.upper()
            if (
                code in _RAW_POINTER_CODES
                and pointer not in {"", "0"}
                and pointer not in defined
            ):
                invalid.append((entity_type, handle, code, pointer))
    if invalid:
        examples = ", ".join(
            f"{entity_type}(#{handle}) code {code}→#{pointer}"
            for entity_type, handle, code, pointer in invalid[:10]
        )
        raise DXFExportValidationError(
            f"成果DXF含 {len(invalid)} 個懸空Handle reference：{examples}"
        )


def _validate_clean_structure(path: Path, document) -> None:
    layer_records = [
        entity
        for entity in document.entitydb.values()
        if entity is not None and entity.is_alive and entity.dxftype() == "LAYER"
    ]
    duplicates = [
        name
        for name, count in Counter(
            str(entity.dxf.name).casefold() for entity in layer_records
        ).items()
        if count > 1
    ]
    if duplicates:
        raise DXFExportValidationError(
            "成果DXF含同名重複Layer records：" + ", ".join(duplicates)
        )
    xrecords = [entity for entity in document.objects if entity.dxftype() == "XRECORD"]
    if xrecords:
        raise DXFExportValidationError(
            f"乾淨成果DXF不應含XRecord，目前共有 {len(xrecords)} 個"
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    forbidden = [
        token
        for token in ("_LAYISO_STATE", "ADSK_XREC_LAYER_RECONCILED")
        if token in text
    ]
    if forbidden:
        raise DXFExportValidationError(
            "成果DXF意外帶入原圖歷史資料：" + ", ".join(forbidden)
        )
    _validate_raw_handle_references(path, document)


def _unique_sibling_temp_path(output_path: Path) -> Path:
    temp_stem = output_path.stem[:48] or "clean-dxf-export"
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{temp_stem}.",
        suffix=".clean-export.tmp.dxf",
        dir=output_path.parent,
    )
    os.close(descriptor)
    return Path(raw_path)


def _save_clean_document(document, path: Path) -> None:
    """Single failure-injection point; document is always newly created."""

    document.saveas(path)


def _replace_validated_file(temporary_path: Path, output_path: Path) -> None:
    os.replace(temporary_path, output_path)


def _validation_failure(
    reason: str,
    temporary_path: Path,
    audit: DXFAuditSummary | None = None,
    cause: Exception | None = None,
) -> DXFExportValidationError:
    lines = [
        "乾淨DXF匯出未完成，原正式輸出檔未被覆蓋。",
        f"原因：{reason}",
        f"診斷暫存檔：{temporary_path}",
    ]
    if audit is not None:
        lines.append(
            f"Audit：{audit.error_count}項錯誤、{audit.fix_count}項修復"
        )
    error = DXFExportValidationError(
        "\n".join(lines),
        temporary_path=temporary_path,
        final_audit=audit,
    )
    if cause is not None:
        error.__cause__ = cause
    return error


def _write_clean_export(
    document,
    output_path: Path,
    background: Sequence[_PreparedBackgroundSegment],
    expected_results: Sequence[_ExpectedResultEntity],
) -> _CleanValidationResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = _unique_sibling_temp_path(output_path)
    try:
        _save_clean_document(document, temporary_path)
        if not temporary_path.is_file() or temporary_path.stat().st_size <= 0:
            raise DXFExportValidationError("暫存DXF不存在或大小為0")
    except Exception as exc:
        raise _validation_failure(
            f"暫存DXF寫入失敗：{exc}",
            temporary_path,
            cause=exc,
        )
    audit = None
    try:
        reread = ezdxf.readfile(temporary_path)
        audit = _audit_summary(reread)
        if audit.error_count or audit.fix_count:
            raise DXFExportValidationError(
                "新建Clean Document的Audit不是0，視為Export Pipeline錯誤；"
                f"errors={audit.error_count}, fixes={audit.fix_count}"
            )
        _validate_clean_structure(temporary_path, reread)
        _validate_background(reread, background)
        dimension_count, jack_count = _validate_results(
            reread,
            expected_results,
        )
    except Exception as exc:
        raise _validation_failure(
            f"最終驗證失敗：{exc}",
            temporary_path,
            audit,
            exc,
        )
    try:
        _replace_validated_file(temporary_path, output_path)
    except Exception as exc:
        raise _validation_failure(
            f"正式檔交易式替換失敗：{exc}",
            temporary_path,
            audit,
            exc,
        )
    try:
        temporary_path.unlink(missing_ok=True)
    except OSError:
        pass
    return _CleanValidationResult(audit, dimension_count, jack_count)


def export_results_to_dxf(
    dxf_import_state: Mapping[str, Any],
    output_path: str | Path,
    plans: Iterable[MemberExportPlan],
    bindings: Mapping[tuple[str, str], MemberBinding],
    *,
    options: DXFExportOptions | None = None,
) -> DXFExportReport:
    """Create a new clean DXF from saved world geometry and solved results."""

    _validate_import_state(dxf_import_state)
    options = options or DXFExportOptions()
    output_path = Path(output_path).resolve()
    normalized_plans = _normalize_plans(plans)
    if not normalized_plans:
        raise DXFResultExportError("尚未產生或選取可見的Solver配置結果")
    missing = [
        f"{plan.role} {plan.member_id}"
        for plan in normalized_plans
        if (plan.role, plan.member_id) not in bindings
    ]
    if missing:
        raise DXFResultExportError(
            "下列配置結果缺少人工確認後的工程線綁定：\n" + "\n".join(missing)
        )
    for plan in normalized_plans:
        binding = bindings[(plan.role, plan.member_id)]
        drawing_length = math.dist(binding.world_start, binding.world_end)
        configured_length = sum(piece.length for piece in plan.pieces) + plan.gap
        tolerance = max(2.0, drawing_length * 0.0001)
        if drawing_length <= 1e-9:
            raise DXFResultExportError(f"{plan.member_id} 的工程線長度為0")
        if abs(configured_length - drawing_length) > tolerance:
            raise DXFResultExportError(
                f"{plan.member_id} 的配置總長 {configured_length:g} mm 與 "
                f"工程線長 {drawing_length:g} mm 不一致，無法正確放置標註"
            )

    background_segments = _extract_background_segments(dxf_import_state)
    document = _new_clean_document(options)
    prepared_background, fallbacks = _prepare_background_layers(
        document,
        background_segments,
    )
    _draw_background(document, prepared_background)
    expected_results, dimension_count, jack_count = _draw_results(
        document,
        normalized_plans,
        bindings,
        options,
    )
    validation = _write_clean_export(
        document,
        output_path,
        prepared_background,
        expected_results,
    )
    coordinate_mode, _origin_x, _origin_y = _coordinate_data(dxf_import_state)
    background_counts = tuple(
        sorted(Counter(item.role for item in prepared_background).items())
    )
    background_layers = {item.output_layer for item in prepared_background}
    result_waler_count = sum(plan.role == "waler" for plan in normalized_plans)
    result_support_count = len(normalized_plans) - result_waler_count
    warnings = tuple(
        f"{item.role} 原圖層「{item.original_name or '<空白>'}」改用「{item.output_name}」：{item.reason}"
        for item in fallbacks
    )
    return DXFExportReport(
        output_path=str(output_path),
        member_count=len(normalized_plans),
        dimension_count=dimension_count,
        jack_count=jack_count,
        waler_count=result_waler_count,
        strut_count=result_support_count,
        dxf_version=f"{CLEAN_DXF_VERSION} ({CLEAN_DXF_ACAD_VERSION})",
        coordinate_units=DRAWING_UNITS,
        coordinate_mode=coordinate_mode,
        background_layer_count=len(background_layers),
        background_segment_count=len(prepared_background),
        background_counts=background_counts,
        result_waler_count=result_waler_count,
        result_support_count=result_support_count,
        final_audit=validation.final_audit,
        actual_dimension_count=validation.actual_dimension_count,
        actual_jack_count=validation.actual_jack_count,
        layer_name_fallbacks=fallbacks,
        warnings=warnings,
    )


__all__ = [
    "APP_ID",
    "BACKGROUND_ROLES",
    "CLEAN_DXF_ACAD_VERSION",
    "CLEAN_DXF_VERSION",
    "DIMSTYLE_NAME",
    "DRAWING_UNITS",
    "DXFAuditIssue",
    "DXFAuditSummary",
    "DXFExportOptions",
    "DXFExportReport",
    "DXFExportValidationError",
    "DXFResultExportError",
    "ExportPiece",
    "JACK_BLOCK_NAME",
    "LayerNameFallback",
    "MemberBinding",
    "MemberExportPlan",
    "RESULT_SUPPORT_LAYER",
    "RESULT_WALER_LAYER",
    "WORLD_COORDINATE_TOLERANCE_MM",
    "build_member_bindings",
    "export_results_to_dxf",
]
