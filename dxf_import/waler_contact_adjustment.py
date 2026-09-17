"""Pure planning and atomic apply for DXF-review Waler contact adjustments."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .candidate_points import (
    associate_components_to_struts,
    rebuild_candidate_points_for_components,
)
from .geometry import (
    Point,
    _angle_difference_deg,
    _distance,
    _dot,
    _length,
    _line_segment_intersection_point,
    _midpoint,
    _projection_overlap_ratio,
    _segment_distance,
    _unit,
    _vector,
    circle_segment_intersection_points,
)
from .models import (
    COMPONENT_ASSOCIATION_CODES,
    AuxiliaryComponent,
    Brace,
    Column,
    CoordinateSystem,
    CornerBrace,
    CornerBraceConnection,
    DXFImportError,
    DXFImportResult,
    GeometryTolerances,
    Strut,
    ValidationMessage,
    Waler,
    WalerContactReviewState,
    apply_coordinate_system,
)
from .support_pairing import (
    detect_double_support_candidates,
    preserve_double_support_decisions,
)
from .validation import validate_duplicate_engineering_members


ADJUSTMENT_VALIDATION_CODES = {
    "WALER_CONTACT_ADJUSTED",
    "WALER_CONTACT_BASELINE_CHANGED",
    "WALER_SUPPORT_SIDE_UNKNOWN",
    "INVALID_WALER_CONTACT_VALUE",
    "STRUT_WALER_INTERSECTION_FAILED",
    "BRACE_STATION_INVALID",
    "CORNER_BRACE_CONNECTION_INVALID",
    "CORNER_BRACE_INTERSECTION_FAILED",
    "CORNER_BRACE_INTERSECTION_AMBIGUOUS",
    "CORNER_BRACE_DERIVED_FIELD_CONFLICT",
}


@dataclass(frozen=True)
class StrutAdjustment:
    member_id: str
    endpoint_name: str
    old_member: Strut
    new_member: Strut


@dataclass(frozen=True)
class BraceAdjustment:
    member_id: str
    endpoint_name: str
    waler_station_mm: float
    old_member: Brace
    new_member: Brace


@dataclass(frozen=True)
class CornerBraceAdjustment:
    member_id: str
    strut_id: str
    strut_hole_station_mm: float
    fixed_length_mm: float
    old_waler_station_mm: float
    new_waler_station_mm: float
    old_member: CornerBrace
    new_member: CornerBrace


@dataclass(frozen=True)
class WalerContactAdjustmentPlan:
    waler_id: str
    contact_displacement: float
    review_state: WalerContactReviewState
    old_waler: Waler
    new_waler: Waler
    strut_changes: tuple[StrutAdjustment, ...]
    brace_changes: tuple[BraceAdjustment, ...]
    corner_brace_changes: tuple[CornerBraceAdjustment, ...]
    changed_column_ids: tuple[str, ...]
    changed_beam_ids: tuple[str, ...]
    messages: tuple[ValidationMessage, ...]
    proposed_result: DXFImportResult

    @property
    def can_apply(self) -> bool:
        return self.proposed_result.can_import and not any(
            message.severity in {"error", "critical"}
            for message in self.messages
        )


@dataclass(frozen=True)
class WalerBackfillMeasurement:
    """Auditable face-to-face backfill measurement read from DXF geometry."""

    thickness_mm: float
    waler_outer_line: tuple[Point, Point]
    continuous_wall_inner_line: tuple[Point, Point]
    continuous_wall_source_handle: str


def _world_line(member: Waler | Strut | Brace | AuxiliaryComponent) -> tuple[Point, Point]:
    return member.world_start or member.start, member.world_end or member.end


def _with_world_line(
    member: Waler | Strut | Brace | CornerBrace,
    start: Point,
    end: Point,
):
    changes: dict[str, Any] = {
        "start": start,
        "end": end,
        "world_start": start,
        "world_end": end,
        "local_start": start,
        "local_end": end,
    }
    if isinstance(member, AuxiliaryComponent):
        midpoint = _midpoint(start, end)
        changes.update(
            reference_point=midpoint,
            world_reference_point=midpoint,
            local_reference_point=midpoint,
        )
    return replace(member, **changes)


def _same_directed_line(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
    tolerance: float,
) -> bool:
    return (
        _distance(first[0], second[0]) <= tolerance
        and _distance(first[1], second[1]) <= tolerance
    )


def _member_evidence(
    member: Strut | Brace,
    waler_id: str,
) -> tuple[tuple[Point, Point], ...]:
    start, end = _world_line(member)
    evidence: list[tuple[Point, Point]] = []
    if member.from_waler == waler_id:
        evidence.append((start, end))
    if member.to_waler == waler_id:
        evidence.append((end, start))
    return tuple(evidence)


def support_side_normal(
    waler: Waler,
    struts: Sequence[Strut],
    braces: Sequence[Brace],
    tolerances: GeometryTolerances | None = None,
) -> Point | None:
    """Infer the physical support side without relying on Waler orientation."""

    tolerances = tolerances or GeometryTolerances()
    waler_start, waler_end = _world_line(waler)
    axis = _unit(waler_start, waler_end)
    if axis is None:
        return None
    left_normal = (-axis[1], axis[0])
    minimum_normal_ratio = math.sin(
        math.radians(max(0.0, tolerances.parallel_angle_tolerance_deg))
    )
    signed_evidence: list[float] = []
    for members in (struts, braces):
        for member in members:
            for attachment, other in _member_evidence(member, waler.id):
                direction = _unit(attachment, other)
                if direction is None:
                    continue
                normal_component = _dot(direction, left_normal)
                if abs(normal_component) <= minimum_normal_ratio:
                    continue
                signed_evidence.append(normal_component)
    if not signed_evidence:
        return None
    signs = {1 if value > 0.0 else -1 for value in signed_evidence}
    if len(signs) != 1:
        return None
    sign = signs.pop()
    return left_normal[0] * sign, left_normal[1] * sign


def _source_segments(points: Sequence[Point], closed: bool) -> tuple[tuple[Point, Point], ...]:
    segments = [
        (start, end)
        for start, end in zip(points, points[1:])
        if _distance(start, end) > 1e-9
    ]
    if closed and len(points) > 2 and _distance(points[-1], points[0]) > 1e-9:
        segments.append((points[-1], points[0]))
    return tuple(segments)


def _waler_outer_line(
    waler: Waler,
    support_normal: Point,
    tolerances: GeometryTolerances,
) -> tuple[Point, Point] | None:
    """Select the recognized Waler face opposite the support side."""

    baseline = _world_line(waler)
    options: list[tuple[float, tuple[Point, Point]]] = []
    for candidate in waler.line_candidates:
        if candidate.source != "recognized_boundary":
            continue
        line = candidate.world_start, candidate.world_end
        if (
            _angle_difference_deg(baseline, line)
            > tolerances.parallel_angle_tolerance_deg
            or _projection_overlap_ratio(baseline, line)
            < tolerances.minimum_projection_overlap_ratio
        ):
            continue
        offsets = tuple(
            _dot(_vector(baseline[0], point), support_normal)
            for point in line
        )
        if max(offsets) >= -1e-6:
            continue
        separation = -sum(offsets) / 2.0
        if separation > (
            tolerances.maximum_component_width_mm
            + tolerances.width_tolerance_mm
        ):
            continue
        options.append((separation, line))
    if not options:
        return None
    expected = (
        float(waler.source_width)
        if math.isfinite(float(waler.source_width))
        and float(waler.source_width) > 0.0
        else None
    )
    options.sort(
        key=lambda item: (
            abs(item[0] - expected) if expected is not None else -item[0],
            item[1],
        )
    )
    return options[0][1]


def detect_waler_backfill_from_geometry(
    result: DXFImportResult,
    waler: Waler,
    support_normal: Point | None,
    tolerances: GeometryTolerances | None = None,
) -> WalerBackfillMeasurement | None:
    """Measure the gap from Waler outer face to continuous-wall inner face."""

    tolerances = tolerances or GeometryTolerances()
    if support_normal is None:
        return None
    outer = _waler_outer_line(waler, support_normal, tolerances)
    if outer is None:
        return None
    options: list[tuple[float, float, tuple[Point, Point], str]] = []
    for geometry in result.source_geometry:
        if geometry.role != "continuous_wall":
            continue
        for line in _source_segments(geometry.points, geometry.closed):
            if (
                _angle_difference_deg(outer, line)
                > tolerances.parallel_angle_tolerance_deg
            ):
                continue
            overlap = _projection_overlap_ratio(outer, line)
            if overlap < tolerances.minimum_projection_overlap_ratio:
                continue
            offsets = tuple(
                _dot(_vector(outer[0], point), support_normal)
                for point in line
            )
            # The retaining wall must be on the side opposite the supports.
            if max(offsets) > 1e-6:
                continue
            if abs(offsets[0] - offsets[1]) > tolerances.width_tolerance_mm:
                continue
            thickness = max(0.0, -sum(offsets) / 2.0)
            options.append((thickness, -overlap, line, geometry.source_handle))
    if not options:
        return None
    thickness, _overlap_rank, wall_line, handle = min(options)
    return WalerBackfillMeasurement(
        thickness_mm=thickness,
        waler_outer_line=outer,
        continuous_wall_inner_line=wall_line,
        continuous_wall_source_handle=handle,
    )


def build_corner_brace_connections(
    result: DXFImportResult,
    tolerances: GeometryTolerances | None = None,
) -> tuple[tuple[CornerBraceConnection, ...], tuple[ValidationMessage, ...]]:
    """Build stable, unique CornerBrace bindings from confirmed DXF geometry."""

    tolerances = tolerances or GeometryTolerances()
    waler_by_id = {member.id: member for member in result.walers}
    connections: list[CornerBraceConnection] = []
    messages: list[ValidationMessage] = []
    for corner in result.corner_braces:
        corner_start, corner_end = _world_line(corner)
        options: list[
            tuple[
                float,
                Strut,
                str,
                Waler,
                str,
                Point,
                Point,
            ]
        ] = []
        for strut in result.struts:
            strut_start, strut_end = _world_line(strut)
            for endpoint_name, waler_id in (
                ("from", strut.from_waler),
                ("to", strut.to_waler),
            ):
                waler = waler_by_id.get(waler_id)
                if waler is None:
                    continue
                waler_start, waler_end = _world_line(waler)
                for corner_waler_endpoint_name, waler_point, strut_point in (
                    ("start", corner_start, corner_end),
                    ("end", corner_end, corner_start),
                ):
                    waler_distance = _segment_distance(
                        waler_point, waler_start, waler_end
                    )
                    strut_distance = _segment_distance(
                        strut_point, strut_start, strut_end
                    )
                    if max(waler_distance, strut_distance) > tolerances.connection_tolerance_mm:
                        continue
                    options.append(
                        (
                            waler_distance + strut_distance,
                            strut,
                            endpoint_name,
                            waler,
                            corner_waler_endpoint_name,
                            waler_point,
                            strut_point,
                        )
                    )
        options.sort(key=lambda item: (item[0], item[1].id, item[2], item[4]))
        if not options:
            messages.append(
                ValidationMessage(
                    "warning",
                    "CORNER_BRACE_CONNECTION_INVALID",
                    f"{corner.id} 無法唯一確認圍令與支撐接點。",
                    "corner_brace",
                    corner.source_handles,
                )
            )
            continue
        best = options[0]
        if (
            len(options) > 1
            and options[1][0] - best[0]
            <= tolerances.ambiguous_connection_delta_mm
        ):
            messages.append(
                ValidationMessage(
                    "warning",
                    "CORNER_BRACE_CONNECTION_INVALID",
                    f"{corner.id} 的圍令／支撐配對有歧義。",
                    "corner_brace",
                    corner.source_handles,
                )
            )
            continue
        (
            _score,
            strut,
            endpoint_name,
            waler,
            corner_waler_endpoint_name,
            waler_attachment,
            strut_attachment,
        ) = best
        strut_start, strut_end = _world_line(strut)
        if endpoint_name == "from":
            strut_base = strut_start
            strut_axis = _unit(strut_start, strut_end)
        else:
            strut_base = strut_end
            strut_axis = _unit(strut_end, strut_start)
        waler_start, waler_end = _world_line(waler)
        waler_axis = _unit(waler_start, waler_end)
        if strut_axis is None or waler_axis is None:
            messages.append(
                ValidationMessage(
                    "warning",
                    "CORNER_BRACE_CONNECTION_INVALID",
                    f"{corner.id} 的關聯構件為零長度。",
                    "corner_brace",
                    corner.source_handles,
                )
            )
            continue
        hole_station = _dot(_vector(strut_base, strut_attachment), strut_axis)
        strut_length = _length(strut_start, strut_end)
        fixed_length = _distance(waler_attachment, strut_attachment)
        if (
            hole_station < -tolerances.endpoint_tolerance_mm
            or hole_station > strut_length + tolerances.endpoint_tolerance_mm
            or not math.isfinite(fixed_length)
            or fixed_length <= 0.0
        ):
            messages.append(
                ValidationMessage(
                    "warning",
                    "CORNER_BRACE_CONNECTION_INVALID",
                    f"{corner.id} 的支撐孔位或實測長度無效。",
                    "corner_brace",
                    corner.source_handles,
                )
            )
            continue
        connections.append(
            CornerBraceConnection(
                corner_brace_id=corner.id,
                waler_id=waler.id,
                strut_id=strut.id,
                strut_endpoint_name=endpoint_name,
                corner_waler_endpoint_name=corner_waler_endpoint_name,
                baseline_waler_attachment=waler_attachment,
                baseline_strut_attachment=strut_attachment,
                strut_hole_station_mm=max(0.0, min(strut_length, hole_station)),
                fixed_length_mm=fixed_length,
                baseline_waler_station_mm=_dot(
                    _vector(waler_start, waler_attachment), waler_axis
                ),
            )
        )
    return tuple(connections), tuple(messages)


def initialize_waler_contact_review(
    result: DXFImportResult,
    tolerances: GeometryTolerances | None = None,
) -> DXFImportResult:
    """Capture immutable DXF baselines after recognition and connection work."""

    tolerances = tolerances or GeometryTolerances()
    reviews = []
    for waler in result.walers:
        normal = support_side_normal(
            waler, result.struts, result.braces, tolerances
        )
        backfill = detect_waler_backfill_from_geometry(
            result, waler, normal, tolerances
        )
        width = (
            float(waler.source_width)
            if math.isfinite(float(waler.source_width))
            and float(waler.source_width) > 0.0
            else None
        )
        reviews.append(
            WalerContactReviewState(
                waler_id=waler.id,
                baseline_contact_start=_world_line(waler)[0],
                baseline_contact_end=_world_line(waler)[1],
                support_normal_world=normal,
                original_backfill_mm=(
                    backfill.thickness_mm if backfill is not None else None
                ),
                adopted_backfill_mm=(
                    backfill.thickness_mm if backfill is not None else None
                ),
                original_waler_width_mm=width,
                adopted_waler_width_mm=width,
                waler_outer_start=(
                    backfill.waler_outer_line[0]
                    if backfill is not None
                    else None
                ),
                waler_outer_end=(
                    backfill.waler_outer_line[1]
                    if backfill is not None
                    else None
                ),
                continuous_wall_inner_start=(
                    backfill.continuous_wall_inner_line[0]
                    if backfill is not None
                    else None
                ),
                continuous_wall_inner_end=(
                    backfill.continuous_wall_inner_line[1]
                    if backfill is not None
                    else None
                ),
                continuous_wall_source_handle=(
                    backfill.continuous_wall_source_handle
                    if backfill is not None
                    else ""
                ),
                backfill_recognition_method=(
                    "waler_outer_to_continuous_wall_inner"
                    if backfill is not None
                    else ""
                ),
            )
        )
    connections, _messages = build_corner_brace_connections(result, tolerances)
    return replace(
        result,
        waler_contact_reviews=tuple(reviews),
        corner_brace_connections=connections,
    )


def _validated_dimension(
    value: Any,
    label: str,
    *,
    strictly_positive: bool,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DXFImportError(f"{label}必須是有效數值。") from exc
    if not math.isfinite(number):
        raise DXFImportError(f"{label}必須是有限數值。")
    if number < 0.0 or (strictly_positive and number <= 0.0):
        rule = "大於 0" if strictly_positive else "大於或等於 0"
        raise DXFImportError(f"{label}必須{rule}。")
    return number


def _angle_deg(start: Point, end: Point) -> float:
    direction = _vector(start, end)
    return math.degrees(math.atan2(direction[1], direction[0]))


def _angle_change(first: tuple[Point, Point], second: tuple[Point, Point]) -> float:
    first_axis = _unit(*first)
    second_axis = _unit(*second)
    if first_axis is None or second_axis is None:
        return math.inf
    cosine = max(-1.0, min(1.0, _dot(first_axis, second_axis)))
    return math.degrees(math.acos(cosine))


def _select_corner_brace_intersection(
    intersections: Sequence[Point],
    *,
    new_waler_start: Point,
    new_waler_axis: Point,
    baseline_waler_station_mm: float,
    baseline_direction: tuple[Point, Point],
    new_hole: Point,
    tolerance: float,
) -> tuple[float, Point] | None:
    """Select by station first, direction second, or report unresolved ambiguity."""

    station_options = [
        (
            _dot(_vector(new_waler_start, point), new_waler_axis),
            point,
        )
        for point in intersections
    ]
    if not station_options:
        return None
    station_options.sort(
        key=lambda item: abs(item[0] - baseline_waler_station_mm)
    )
    if len(station_options) == 1:
        return station_options[0]
    first_delta = abs(station_options[0][0] - baseline_waler_station_mm)
    second_delta = abs(station_options[1][0] - baseline_waler_station_mm)
    if abs(first_delta - second_delta) > tolerance:
        return station_options[0]
    direction_ranked = sorted(
        station_options[:2],
        key=lambda item: _angle_change(baseline_direction, (new_hole, item[1])),
    )
    first_angle = _angle_change(
        baseline_direction, (new_hole, direction_ranked[0][1])
    )
    second_angle = _angle_change(
        baseline_direction, (new_hole, direction_ranked[1][1])
    )
    if abs(first_angle - second_angle) <= 1e-9:
        return None
    return direction_ranked[0]


def _replace_by_id(items: Sequence[Any], replacements: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(replacements.get(item.id, item) for item in items)


def _corner_field_updates(
    struts: Sequence[Strut],
    walers: Sequence[Waler],
    corner_braces: Sequence[CornerBrace],
    connections: Sequence[CornerBraceConnection],
) -> tuple[tuple[Strut, ...], tuple[ValidationMessage, ...]]:
    strut_by_id = {item.id: item for item in struts}
    waler_by_id = {item.id: item for item in walers}
    corner_by_id = {item.id: item for item in corner_braces}
    values: dict[str, dict[str, tuple[str, float]]] = {}
    messages: list[ValidationMessage] = []
    for connection in connections:
        strut = strut_by_id.get(connection.strut_id)
        waler = waler_by_id.get(connection.waler_id)
        corner = corner_by_id.get(connection.corner_brace_id)
        if strut is None or waler is None or corner is None:
            continue
        waler_axis = _unit(*_world_line(waler))
        if waler_axis is None:
            continue
        base = _world_line(strut)[0 if connection.strut_endpoint_name == "from" else 1]
        corner_line = _world_line(corner)
        attachment = corner_line[
            0 if connection.corner_waler_endpoint_name == "start" else 1
        ]
        delta = _dot(_vector(base, attachment), waler_axis)
        side = "start" if delta < 0.0 else "end"
        field_name = f"{connection.strut_endpoint_name}_brace_to_waler_{side}_len"
        member_values = values.setdefault(strut.id, {})
        if field_name in member_values:
            previous_id, _previous_value = member_values[field_name]
            field_label = {
                "from_brace_to_waler_start_len": "起點角撐長度（往圍令起點）",
                "from_brace_to_waler_end_len": "起點角撐長度（往圍令終點）",
                "to_brace_to_waler_start_len": "終點角撐長度（往圍令起點）",
                "to_brace_to_waler_end_len": "終點角撐長度（往圍令終點）",
            }.get(field_name, field_name)
            messages.append(
                ValidationMessage(
                    "error",
                    "CORNER_BRACE_DERIVED_FIELD_CONFLICT",
                    f"{strut.id} 的{field_label}同時對應 {previous_id} 與 {corner.id}。",
                    "corner_brace",
                    corner.source_handles,
                )
            )
            continue
        member_values[field_name] = (corner.id, round(abs(delta)))

    updated: list[Strut] = []
    for strut in struts:
        changes: dict[str, float] = {
            "from_brace_to_waler_start_len": 0.0,
            "from_brace_to_waler_end_len": 0.0,
            "to_brace_to_waler_start_len": 0.0,
            "to_brace_to_waler_end_len": 0.0,
        }
        for field_name, (_corner_id, value) in values.get(strut.id, {}).items():
            changes[field_name] = value
        updated.append(replace(strut, **changes))
    return tuple(updated), tuple(messages)


def plan_waler_contact_adjustment(
    result: DXFImportResult,
    waler_id: str,
    *,
    original_backfill_mm: Any,
    adopted_backfill_mm: Any,
    original_waler_width_mm: Any,
    adopted_waler_width_mm: Any,
    tolerances: GeometryTolerances | None = None,
) -> WalerContactAdjustmentPlan:
    """Build a complete proposal without mutating the supplied result."""

    tolerances = tolerances or GeometryTolerances()
    original_coordinate_system = result.coordinate_system
    world_result = apply_coordinate_system(result, CoordinateSystem())
    waler = next((item for item in world_result.walers if item.id == waler_id), None)
    review = next(
        (item for item in world_result.waler_contact_reviews if item.waler_id == waler_id),
        None,
    )
    if waler is None or review is None:
        raise DXFImportError(f"找不到圍令接觸位置檢核資料：{waler_id}")

    original_backfill = _validated_dimension(
        original_backfill_mm, "圖面背填厚度", strictly_positive=False
    )
    adopted_backfill = _validated_dimension(
        adopted_backfill_mm, "採用背填厚度", strictly_positive=False
    )
    original_width = _validated_dimension(
        original_waler_width_mm, "圖面圍令寬度", strictly_positive=True
    )
    adopted_width = _validated_dimension(
        adopted_waler_width_mm, "採用圍令寬度", strictly_positive=True
    )
    proposed_review = replace(
        review,
        original_backfill_mm=original_backfill,
        adopted_backfill_mm=adopted_backfill,
        original_waler_width_mm=original_width,
        adopted_waler_width_mm=adopted_width,
    )
    displacement = proposed_review.contact_displacement
    assert displacement is not None

    messages: list[ValidationMessage] = []
    normal = review.support_normal_world
    if normal is None or _unit((0.0, 0.0), normal) is None:
        messages.append(
            ValidationMessage(
                "error",
                "WALER_SUPPORT_SIDE_UNKNOWN",
                f"{waler_id} 缺少一致且可靠的支撐側證據。",
                "waler",
                waler.source_handles,
            )
        )
        normal = (0.0, 0.0)

    previous_displacement = review.contact_displacement or 0.0
    expected_current = (
        (
            review.baseline_contact_start[0] + normal[0] * previous_displacement,
            review.baseline_contact_start[1] + normal[1] * previous_displacement,
        ),
        (
            review.baseline_contact_end[0] + normal[0] * previous_displacement,
            review.baseline_contact_end[1] + normal[1] * previous_displacement,
        ),
    )
    baseline_tolerance = max(1e-6, tolerances.beam_crossing_duplicate_tolerance_mm)
    if not _same_directed_line(_world_line(waler), expected_current, baseline_tolerance):
        messages.append(
            ValidationMessage(
                "error",
                "WALER_CONTACT_BASELINE_CHANGED",
                f"{waler_id} 的正式幾何已不符合保存的接觸基準線。",
                "waler",
                waler.source_handles,
            )
        )

    new_start = (
        review.baseline_contact_start[0] + normal[0] * displacement,
        review.baseline_contact_start[1] + normal[1] * displacement,
    )
    new_end = (
        review.baseline_contact_end[0] + normal[0] * displacement,
        review.baseline_contact_end[1] + normal[1] * displacement,
    )
    new_waler = _with_world_line(waler, new_start, new_end)

    strut_replacements: dict[str, Strut] = {}
    strut_changes: list[StrutAdjustment] = []
    for strut in world_result.struts:
        start, end = _world_line(strut)
        affected = []
        if strut.from_waler == waler_id:
            affected.append("start")
        if strut.to_waler == waler_id:
            affected.append("end")
        if not affected:
            continue
        updated_start, updated_end = start, end
        for endpoint_name in affected:
            intersection = _line_segment_intersection_point(
                (start, end), (new_start, new_end), baseline_tolerance
            )
            if intersection is None:
                messages.append(
                    ValidationMessage(
                        "error",
                        "STRUT_WALER_INTERSECTION_FAILED",
                        f"{strut.id} 的中心線無法與調整後 {waler_id} 有限線段相交。",
                        "strut",
                        strut.source_handles,
                    )
                )
                continue
            if endpoint_name == "start":
                updated_start = intersection
            else:
                updated_end = intersection
        if _length(updated_start, updated_end) <= baseline_tolerance:
            messages.append(
                ValidationMessage(
                    "error",
                    "STRUT_WALER_INTERSECTION_FAILED",
                    f"{strut.id} 調整後成為零長度。",
                    "strut",
                    strut.source_handles,
                )
            )
            continue
        updated = _with_world_line(strut, updated_start, updated_end)
        strut_replacements[strut.id] = updated
        strut_changes.append(
            StrutAdjustment(strut.id, "+".join(affected), strut, updated)
        )

    proposed_struts = _replace_by_id(world_result.struts, strut_replacements)

    brace_replacements: dict[str, Brace] = {}
    brace_changes: list[BraceAdjustment] = []
    old_waler_start, old_waler_end = _world_line(waler)
    old_waler_axis = _unit(old_waler_start, old_waler_end)
    new_waler_axis = _unit(new_start, new_end)
    if old_waler_axis is not None and new_waler_axis is not None:
        for brace in world_result.braces:
            start, end = _world_line(brace)
            affected = []
            if brace.from_waler == waler_id:
                affected.append("start")
            if brace.to_waler == waler_id:
                affected.append("end")
            if not affected:
                continue
            updated_start, updated_end = start, end
            stations: list[float] = []
            for endpoint_name in affected:
                attachment = start if endpoint_name == "start" else end
                station = _dot(_vector(old_waler_start, attachment), old_waler_axis)
                if not (
                    -baseline_tolerance
                    <= station
                    <= _length(old_waler_start, old_waler_end) + baseline_tolerance
                ):
                    messages.append(
                        ValidationMessage(
                            "error",
                            "BRACE_STATION_INVALID",
                            f"{brace.id} 在 {waler_id} 的既有接點位置超出有限線段。",
                            "brace",
                            brace.source_handles,
                        )
                    )
                    continue
                new_attachment = (
                    new_start[0] + new_waler_axis[0] * station,
                    new_start[1] + new_waler_axis[1] * station,
                )
                if endpoint_name == "start":
                    updated_start = new_attachment
                else:
                    updated_end = new_attachment
                stations.append(station)
            if not stations:
                continue
            updated = _with_world_line(brace, updated_start, updated_end)
            brace_replacements[brace.id] = updated
            brace_changes.append(
                BraceAdjustment(
                    brace.id,
                    "+".join(affected),
                    stations[0],
                    brace,
                    updated,
                )
            )
    proposed_braces = _replace_by_id(world_result.braces, brace_replacements)

    corner_by_id = {item.id: item for item in world_result.corner_braces}
    current_strut_by_id = {item.id: item for item in world_result.struts}
    proposed_strut_by_id = {item.id: item for item in proposed_struts}
    corner_replacements: dict[str, CornerBrace] = {}
    corner_changes: list[CornerBraceAdjustment] = []
    target_connections = tuple(
        item
        for item in world_result.corner_brace_connections
        if item.waler_id == waler_id
    )
    nearby_unbound = [
        corner
        for corner in world_result.corner_braces
        if corner.id not in {item.corner_brace_id for item in world_result.corner_brace_connections}
        and min(
            _segment_distance(point, old_waler_start, old_waler_end)
            for point in _world_line(corner)
        )
        <= tolerances.connection_tolerance_mm
    ]
    for corner in nearby_unbound:
        messages.append(
            ValidationMessage(
                "error",
                "CORNER_BRACE_CONNECTION_INVALID",
                f"{corner.id} 位於 {waler_id} 附近，但沒有唯一角撐連接關係。",
                "corner_brace",
                corner.source_handles,
            )
        )

    for connection in target_connections:
        corner = corner_by_id.get(connection.corner_brace_id)
        strut = proposed_strut_by_id.get(connection.strut_id)
        if corner is None or strut is None:
            messages.append(
                ValidationMessage(
                    "error",
                    "CORNER_BRACE_CONNECTION_INVALID",
                    f"{connection.corner_brace_id} 的固定關聯構件不存在。",
                    "corner_brace",
                )
            )
            continue
        current_strut = current_strut_by_id.get(connection.strut_id)
        if current_strut is not None:
            current_strut_start, current_strut_end = _world_line(current_strut)
            if connection.strut_endpoint_name == "from":
                current_base = current_strut_start
                current_inward = _unit(current_strut_start, current_strut_end)
            else:
                current_base = current_strut_end
                current_inward = _unit(current_strut_end, current_strut_start)
            current_corner_line = _world_line(corner)
            current_q = current_corner_line[
                0 if connection.corner_waler_endpoint_name == "start" else 1
            ]
            current_p = current_corner_line[
                1 if connection.corner_waler_endpoint_name == "start" else 0
            ]
            expected_current_p = (
                (
                    current_base[0]
                    + current_inward[0] * connection.strut_hole_station_mm,
                    current_base[1]
                    + current_inward[1] * connection.strut_hole_station_mm,
                )
                if current_inward is not None
                else current_base
            )
            if (
                current_inward is None
                or _distance(current_p, expected_current_p) > baseline_tolerance
                or _segment_distance(
                    current_q, old_waler_start, old_waler_end
                )
                > baseline_tolerance
                or abs(
                    _distance(current_p, current_q)
                    - connection.fixed_length_mm
                )
                > baseline_tolerance
            ):
                messages.append(
                    ValidationMessage(
                        "error",
                        "CORNER_BRACE_CONNECTION_INVALID",
                        f"{corner.id} 的正式幾何已不符合保存的角撐連接關係。",
                        "corner_brace",
                        corner.source_handles,
                    )
                )
        strut_start, strut_end = _world_line(strut)
        if connection.strut_endpoint_name == "from":
            strut_base = strut_start
            inward_axis = _unit(strut_start, strut_end)
        else:
            strut_base = strut_end
            inward_axis = _unit(strut_end, strut_start)
        strut_length = _length(strut_start, strut_end)
        if (
            inward_axis is None
            or connection.strut_hole_station_mm > strut_length + baseline_tolerance
        ):
            messages.append(
                ValidationMessage(
                    "error",
                    "CORNER_BRACE_CONNECTION_INVALID",
                    f"{corner.id} 的固定支撐孔位已超出調整後支撐。",
                    "corner_brace",
                    corner.source_handles,
                )
            )
            continue
        hole = (
            strut_base[0] + inward_axis[0] * connection.strut_hole_station_mm,
            strut_base[1] + inward_axis[1] * connection.strut_hole_station_mm,
        )
        intersections = circle_segment_intersection_points(
            hole,
            connection.fixed_length_mm,
            new_start,
            new_end,
            baseline_tolerance,
        )
        if not intersections:
            messages.append(
                ValidationMessage(
                    "error",
                    "CORNER_BRACE_INTERSECTION_FAILED",
                    f"{corner.id}：依固定支撐孔位與原角撐實際長度，"
                    "無法與調整後圍令相交。",
                    "corner_brace",
                    corner.source_handles,
                )
            )
            continue
        selected_intersection = (
            _select_corner_brace_intersection(
                intersections,
                new_waler_start=new_start,
                new_waler_axis=new_waler_axis,
                baseline_waler_station_mm=connection.baseline_waler_station_mm,
                baseline_direction=(
                    connection.baseline_strut_attachment,
                    connection.baseline_waler_attachment,
                ),
                new_hole=hole,
                tolerance=baseline_tolerance,
            )
            if new_waler_axis is not None
            else None
        )
        if selected_intersection is None:
            messages.append(
                ValidationMessage(
                    "error",
                    "CORNER_BRACE_INTERSECTION_AMBIGUOUS",
                    f"{corner.id} 與調整後圍令有兩個無法唯一判斷的交點。",
                    "corner_brace",
                    corner.source_handles,
                )
            )
            continue
        chosen_station, chosen = selected_intersection
        old_corner_start, old_corner_end = _world_line(corner)
        if connection.corner_waler_endpoint_name == "start":
            new_corner_start, new_corner_end = chosen, hole
        else:
            new_corner_start, new_corner_end = hole, chosen
        updated = _with_world_line(corner, new_corner_start, new_corner_end)
        corner_replacements[corner.id] = updated
        corner_changes.append(
            CornerBraceAdjustment(
                corner.id,
                strut.id,
                connection.strut_hole_station_mm,
                connection.fixed_length_mm,
                connection.baseline_waler_station_mm,
                chosen_station,
                corner,
                updated,
            )
        )
    proposed_corners = _replace_by_id(
        world_result.corner_braces, corner_replacements
    )

    proposed_walers = _replace_by_id(world_result.walers, {waler_id: new_waler})
    proposed_struts, corner_field_messages = _corner_field_updates(
        proposed_struts,
        proposed_walers,
        proposed_corners,
        world_result.corner_brace_connections,
    )
    messages.extend(corner_field_messages)
    double_support = preserve_double_support_decisions(
        world_result.double_support_candidates,
        detect_double_support_candidates(proposed_struts, tolerances),
    )
    (
        proposed_struts,
        proposed_columns,
        proposed_beams,
        component_associations,
        association_messages,
    ) = associate_components_to_struts(
        proposed_struts,
        world_result.columns,
        world_result.beams,
        tolerances,
        double_support_candidates=double_support,
    )
    messages.extend(association_messages)
    duplicate_messages = validate_duplicate_engineering_members(
        (
            proposed_walers,
            proposed_struts,
            proposed_braces,
            proposed_columns,
            proposed_beams,
            proposed_corners,
        ),
        tolerances,
    )
    messages.extend(duplicate_messages)
    messages.append(
        ValidationMessage(
            "info",
            "WALER_CONTACT_ADJUSTED",
            f"{waler_id} 接觸線由基準線平行調整 {displacement:+.3f} mm。",
            "waler",
            waler.source_handles,
        )
    )
    review_states = tuple(
        proposed_review if item.waler_id == waler_id else item
        for item in world_result.waler_contact_reviews
    )
    retained_messages = tuple(
        message
        for message in world_result.messages
        if message.code not in COMPONENT_ASSOCIATION_CODES
        and message.code not in ADJUSTMENT_VALIDATION_CODES
        and message.code != "DUPLICATE_ENGINEERING_COMPONENT"
    )
    proposed_world_result = replace(
        world_result,
        walers=proposed_walers,
        struts=proposed_struts,
        braces=proposed_braces,
        columns=proposed_columns,
        beams=proposed_beams,
        corner_braces=proposed_corners,
        messages=(*retained_messages, *messages),
        component_associations=component_associations,
        beam_crossings=tuple(
            crossing for beam in proposed_beams for crossing in beam.crossings
        ),
        double_support_candidates=double_support,
        waler_contact_reviews=review_states,
    )
    changed_ids = {
        waler_id,
        *(item.member_id for item in strut_changes),
        *(item.member_id for item in brace_changes),
        *(item.member_id for item in corner_changes),
    }
    proposed_world_result = rebuild_candidate_points_for_components(
        proposed_world_result,
        tuple(changed_ids),
        tolerances,
        selection_source="waler_contact_adjustment",
    )
    proposed_result = apply_coordinate_system(
        proposed_world_result, original_coordinate_system
    )
    changed_column_ids = tuple(
        old.id
        for old, new in zip(world_result.columns, proposed_columns)
        if old != new
    )
    changed_beam_ids = tuple(
        old.id
        for old, new in zip(world_result.beams, proposed_beams)
        if old != new
    )
    return WalerContactAdjustmentPlan(
        waler_id=waler_id,
        contact_displacement=displacement,
        review_state=proposed_review,
        old_waler=waler,
        new_waler=new_waler,
        strut_changes=tuple(strut_changes),
        brace_changes=tuple(brace_changes),
        corner_brace_changes=tuple(corner_changes),
        changed_column_ids=changed_column_ids,
        changed_beam_ids=changed_beam_ids,
        messages=tuple(messages),
        proposed_result=proposed_result,
    )


def apply_waler_contact_adjustment(
    result: DXFImportResult,
    waler_id: str,
    *,
    original_backfill_mm: Any,
    adopted_backfill_mm: Any,
    original_waler_width_mm: Any,
    adopted_waler_width_mm: Any,
    tolerances: GeometryTolerances | None = None,
) -> DXFImportResult:
    """Re-plan from the formal result and atomically return the complete result."""

    plan = plan_waler_contact_adjustment(
        result,
        waler_id,
        original_backfill_mm=original_backfill_mm,
        adopted_backfill_mm=adopted_backfill_mm,
        original_waler_width_mm=original_waler_width_mm,
        adopted_waler_width_mm=adopted_waler_width_mm,
        tolerances=tolerances,
    )
    errors = [
        message
        for message in plan.messages
        if message.severity in {"error", "critical"}
    ]
    if not plan.can_apply:
        if not errors:
            errors = [
                message
                for message in plan.proposed_result.messages
                if message.severity in {"error", "critical"}
            ]
        if not errors:
            raise DXFImportError("圍令接觸位置調整未通過檢核。")
        raise DXFImportError(errors[0].message)
    return plan.proposed_result


def restore_waler_contact_review_from_debug(
    result: DXFImportResult,
    debug_state: Mapping[str, Any] | None,
    tolerances: GeometryTolerances | None = None,
) -> DXFImportResult:
    """Restore adopted review values only when the saved state is for this DXF."""

    if not isinstance(debug_state, Mapping):
        return result
    saved_source = str(debug_state.get("source_path", "") or "")
    try:
        same_source = Path(saved_source).resolve() == Path(result.source_path).resolve()
    except (OSError, ValueError):
        same_source = saved_source == result.source_path
    if not same_source:
        return result
    raw_reviews = debug_state.get("waler_contact_reviews", ())
    if not isinstance(raw_reviews, Sequence) or isinstance(raw_reviews, (str, bytes)):
        return result
    current = result
    for raw in raw_reviews:
        if not isinstance(raw, Mapping):
            continue
        waler_id = str(raw.get("waler_id", "") or "")
        review = next(
            (item for item in current.waler_contact_reviews if item.waler_id == waler_id),
            None,
        )
        if review is None:
            continue
        baseline_start = raw.get("baseline_contact_start")
        baseline_end = raw.get("baseline_contact_end")
        try:
            saved_line = (
                (float(baseline_start[0]), float(baseline_start[1])),
                (float(baseline_end[0]), float(baseline_end[1])),
            )
        except (TypeError, ValueError, IndexError):
            continue
        if not _same_directed_line(
            saved_line,
            (review.baseline_contact_start, review.baseline_contact_end),
            1e-6,
        ):
            continue
        values = {
            "original_backfill_mm": raw.get("original_backfill_mm"),
            "adopted_backfill_mm": raw.get("adopted_backfill_mm"),
            "original_waler_width_mm": raw.get("original_waler_width_mm"),
            "adopted_waler_width_mm": raw.get("adopted_waler_width_mm"),
        }
        if any(value is None for value in values.values()):
            restored_review = replace(review, **values)
            current = replace(
                current,
                waler_contact_reviews=tuple(
                    restored_review if item.waler_id == waler_id else item
                    for item in current.waler_contact_reviews
                ),
            )
            continue
        try:
            current = apply_waler_contact_adjustment(
                current,
                waler_id,
                tolerances=tolerances,
                **values,
            )
        except DXFImportError:
            continue
    return current


def format_adjustment_plan(plan: WalerContactAdjustmentPlan) -> str:
    """Return compact engineer-facing Preview details."""

    lines = [
        f"{plan.waler_id} 接觸位置調整：{plan.contact_displacement:+.3f} mm",
        "",
        "支撐",
    ]
    for change in plan.strut_changes:
        old_line = _world_line(change.old_member)
        new_line = _world_line(change.new_member)
        lines.append(
            f"{change.member_id} "
            f"{'起點' if change.endpoint_name == 'start' else '終點'}："
            f"長度 {_length(*old_line):.3f} → {_length(*new_line):.3f} mm"
        )
    lines.extend(("", "斜撐"))
    for change in plan.brace_changes:
        old_line = _world_line(change.old_member)
        new_line = _world_line(change.new_member)
        lines.extend(
            (
                change.member_id,
                f"圍令位置：{change.waler_station_mm:.3f} → {change.waler_station_mm:.3f} mm",
                f"長度：{_length(*old_line):.3f} → {_length(*new_line):.3f} mm",
                f"角度：{_angle_deg(*old_line):.3f}° → {_angle_deg(*new_line):.3f}°",
            )
        )
    lines.extend(("", "角撐"))
    for change in plan.corner_brace_changes:
        old_line = _world_line(change.old_member)
        new_line = _world_line(change.new_member)
        lines.extend(
            (
                change.member_id,
                f"支撐孔位：{change.strut_hole_station_mm:.3f} → {change.strut_hole_station_mm:.3f} mm",
                f"實測固定長度：{change.fixed_length_mm:.3f} → {change.fixed_length_mm:.3f} mm",
                f"圍令位置：{change.old_waler_station_mm:.3f} → {change.new_waler_station_mm:.3f} mm",
                f"角度：{_angle_deg(*old_line):.3f}° → {_angle_deg(*new_line):.3f}°",
            )
        )
    if plan.messages:
        severity_labels = {
            "success": "正常",
            "info": "資訊",
            "warning": "警告",
            "error": "錯誤",
            "critical": "嚴重錯誤",
        }
        lines.extend(("", "檢核結果"))
        lines.extend(
            f"[{severity_labels.get(message.severity, message.severity)}] {message.message}"
            for message in plan.messages
        )
    return "\n".join(lines)


__all__ = [
    "BraceAdjustment",
    "CornerBraceAdjustment",
    "StrutAdjustment",
    "WalerContactAdjustmentPlan",
    "WalerBackfillMeasurement",
    "apply_waler_contact_adjustment",
    "build_corner_brace_connections",
    "detect_waler_backfill_from_geometry",
    "format_adjustment_plan",
    "initialize_waler_contact_review",
    "plan_waler_contact_adjustment",
    "restore_waler_contact_review_from_debug",
    "support_side_normal",
]
