"""Recognize engineering axes and sections from DXF primitives."""

from __future__ import annotations

from dataclasses import dataclass
import copy
import math
from typing import Any, Mapping, Sequence

from .block_member_recognition import (
    BlockMemberPrimitive,
    BlockMemberRecognitionInput,
    BlockMemberRecognitionStatus,
    WalerSpanReference,
    recognize_component_like_member,
    recognize_component_like_strut,
)
from .joist_recognition import (
    JoistContact,
    JoistContextSnapshot,
    JoistPrimitive,
    JoistRecognitionInput,
    JoistRecognitionStatus,
    recognize_bim_joist,
)
from .geometry import (
    Point,
    _angle_difference_deg,
    _cross,
    _distance,
    _dot,
    _length,
    _line_distance,
    _line_segment_intersection_point,
    _line_separation,
    _midpoint,
    _ordered_line,
    _paths_duplicate,
    _point,
    _project_onto_segment,
    _projection_overlap_ratio,
    _same_line,
    _same_point,
    _segment_distance,
    _unit,
    _vector,
)
from .models import (
    BlockInstanceInfo,
    EngineeringLineCandidate,
    GeometryTolerances,
    ValidationMessage,
)
from .waler_contact_face import (
    MemberGeometryFacts,
    WalerContactResolution,
    WalerEnvelopeFacts,
    WalerEnvelopeStatus,
    build_member_terminal_evidence,
    extract_waler_envelope_facts,
    resolve_waler_contact_faces,
)


BIM_BLOCK_WHOLE_AXIS_METHOD = "bim_block_whole_axis"
BIM_JOIST_SINGLE_AXIS_METHOD = "bim_joist_single_axis"
BIM_JOIST_PAIRED_AXIS_METHOD = "bim_joist_paired_axis"


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
    root_handle: str | None = None
    root_entity_type: str = ""


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
    material_spec: str = ""
    material_spec_source: str = ""
    selected_waler_source_handles: tuple[tuple[str, ...], ...] = ()
    waler_intersections: tuple[Point, ...] = ()
    joist_assembly_key: str = ""
    joist_axis_slot: int | None = None
    joist_contacts: tuple[JoistContact, ...] = ()
    waler_envelope_facts: tuple[WalerEnvelopeFacts, ...] = ()


@dataclass(frozen=True)
class _BlockMemberRouteResult:
    """Importer-facing result for one eligible root INSERT source scope."""

    handled: bool
    candidate: _Candidate | None = None
    messages: tuple[ValidationMessage, ...] = ()


@dataclass(frozen=True)
class _BIMJoistRouteResult:
    """Importer-facing result for one Beam-role root INSERT."""

    handled: bool
    candidates: tuple[_Candidate, ...] = ()
    messages: tuple[ValidationMessage, ...] = ()


def _route_bim_joist_block(
    group: _GeometryGroup,
    tolerances: GeometryTolerances,
    context: JoistContextSnapshot,
) -> _BIMJoistRouteResult:
    """Translate a pure BIM Joist outcome without fallback guessing."""

    root_handle = str(group.root_handle or "").strip()
    if (
        group.role != "beam"
        or str(group.root_entity_type).strip().upper() != "INSERT"
        or not root_handle
    ):
        return _BIMJoistRouteResult(False)
    source = JoistRecognitionInput(
        root_handle,
        "INSERT",
        "beam",
        tuple(
            JoistPrimitive(
                tuple(primitive.points),
                primitive.closed,
                primitive.entity_type,
                primitive.source_handle,
                primitive.source_width,
            )
            for primitive in group.primitives
        ),
    )
    outcome = recognize_bim_joist(source, context, tolerances)
    if outcome.status is JoistRecognitionStatus.NOT_APPLICABLE:
        return _BIMJoistRouteResult(False)
    if outcome.status in {
        JoistRecognitionStatus.RECOGNIZED_SINGLE,
        JoistRecognitionStatus.RECOGNIZED_PAIR,
    }:
        method = (
            BIM_JOIST_PAIRED_AXIS_METHOD
            if outcome.status is JoistRecognitionStatus.RECOGNIZED_PAIR
            else BIM_JOIST_SINGLE_AXIS_METHOD
        )
        source_points = tuple(
            dict.fromkeys(
                point
                for primitive in group.primitives
                for point in primitive.points
            )
        )
        candidates = tuple(
            _Candidate(
                axis.start,
                axis.end,
                method,
                True,
                axis.source_width,
                1.0,
                group.layer,
                {root_handle},
                set(group.entity_types),
                list(group.block_instances),
                {f"{group.key}:joist-axis:{axis.slot}"},
                [],
                recognized_axis=axis.segment,
                path_points=axis.segment,
                source_points=source_points,
                joist_assembly_key=root_handle,
                joist_axis_slot=axis.slot,
                joist_contacts=tuple(
                    contact
                    for contact in outcome.contacts
                    if contact.axis_slot == axis.slot
                ),
            )
            for axis in outcome.axes
        )
        return _BIMJoistRouteResult(True, candidates)

    if (
        outcome.diagnostic_code == "BIM_JOIST_WHOLE_SOURCE_AXIS_FAILED"
        and not outcome.axes
    ):
        # A Beam-layer fabrication detail sharing the parent INSERT layer is
        # not itself an unresolved Joist.  It remains visible as source
        # geometry but must not fall through to generic line recognition.
        return _BIMJoistRouteResult(
            True,
            messages=(
                ValidationMessage(
                    "info",
                    "BIM_JOIST_DETAIL_IGNORED",
                    "Beam 圖層圖塊未形成完整 C 型托梁拓樸，保留為來源細節且不建立托梁。",
                    "beam",
                    (root_handle,),
                ),
            ),
        )
    severity = (
        "critical"
        if outcome.status is JoistRecognitionStatus.AMBIGUOUS
        else "error"
    )
    return _BIMJoistRouteResult(
        True,
        messages=(
            ValidationMessage(
                severity,
                outcome.diagnostic_code or "BIM_JOIST_RECOGNITION_FAILED",
                "BIM 托梁無法由完整來源幾何與正式上游構件唯一建立工程結果。",
                "beam",
                (root_handle,),
            ),
        ),
    )


def _route_component_like_member_block_with(
    group: _GeometryGroup,
    tolerances: GeometryTolerances,
    recognizer,
    *,
    waler_context: Sequence[WalerSpanReference] | None = None,
) -> _BlockMemberRouteResult:
    """Translate one eligible root recognition outcome into importer data."""

    root_handle = str(group.root_handle or "").strip()
    if (
        str(group.root_entity_type).strip().upper() != "INSERT"
        or not root_handle
    ):
        return _BlockMemberRouteResult(False)

    source = BlockMemberRecognitionInput(
        root_handle=root_handle,
        root_entity_type="INSERT",
        role=group.role,
        primitives=tuple(
            BlockMemberPrimitive(
                points=tuple(primitive.points),
                closed=primitive.closed,
                entity_type=primitive.entity_type,
                source_handle=primitive.source_handle,
                source_width=primitive.source_width,
            )
            for primitive in group.primitives
        ),
    )
    outcome = (
        recognizer(source, tolerances)
        if waler_context is None
        else recognizer(
            source,
            tolerances,
            waler_context=tuple(waler_context),
        )
    )
    if outcome.status is BlockMemberRecognitionStatus.NOT_APPLICABLE:
        return _BlockMemberRouteResult(False)
    if outcome.status is BlockMemberRecognitionStatus.RECOGNIZED:
        assert outcome.whole_axis is not None
        candidate = _Candidate(
            *outcome.whole_axis,
            BIM_BLOCK_WHOLE_AXIS_METHOD,
            True,
            outcome.representative_width,
            outcome.confidence,
            group.layer,
            {root_handle},
            set(group.entity_types),
            list(group.block_instances),
            {group.key},
            [],
            recognized_axis=outcome.whole_axis,
            source_points=tuple(
                dict.fromkeys(
                    point
                    for primitive in group.primitives
                    for point in primitive.points
                )
            ),
            selected_waler_source_handles=(
                outcome.selected_waler_source_handles
            ),
            waler_intersections=outcome.waler_intersections,
        )
        return _BlockMemberRouteResult(True, candidate)

    member_label = "支撐" if group.role == "strut" else "斜撐"
    descriptions = {
        "BIM_BLOCK_CONFLICTING_WHOLE_AXES": (
            f"BIM 圖塊同時支持多個互相衝突的完整{member_label}軸，"
            "無法可靠決定單一工程線。"
        ),
        "BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE": (
            f"BIM 圖塊具有{member_label}構件特徵，"
            "但無法由來源幾何可靠重建完整工程線。"
        ),
        "BIM_BLOCK_WALER_SPAN_INCOMPLETE": (
            "BIM 支撐軸線無法在來源幾何兩側各找到一支有限圍令，"
            "因此未建立正式支撐。"
        ),
        "BIM_BLOCK_WALER_SPAN_AMBIGUOUS": (
            "BIM 支撐軸線同側有距離相近的多支合法圍令，"
            "無法唯一決定支撐跨度。"
        ),
    }
    diagnostic_code = outcome.diagnostic_code
    contextual_handles = tuple(
        dict.fromkeys(
            handle
            for identity in outcome.selected_waler_source_handles
            for handle in identity
        )
    )
    contextual_suffix = (
        f"（候選圍令來源：{', '.join(contextual_handles)}）"
        if contextual_handles
        else ""
    )
    return _BlockMemberRouteResult(
        True,
        messages=(
            ValidationMessage(
                "error",
                diagnostic_code,
                descriptions.get(
                    diagnostic_code,
                    f"BIM 圖塊無法可靠辨識為單一完整{member_label}構件。",
                )
                + contextual_suffix,
                group.role,
                (root_handle,),
            ),
        ),
    )


def _route_component_like_member_block(
    group: _GeometryGroup,
    tolerances: GeometryTolerances,
) -> _BlockMemberRouteResult:
    """Route one supported Strut or Brace root INSERT by its own role."""

    if group.role not in {"strut", "brace"}:
        return _BlockMemberRouteResult(False)
    return _route_component_like_member_block_with(
        group,
        tolerances,
        recognize_component_like_member,
    )


def _route_component_like_strut_block(
    group: _GeometryGroup,
    tolerances: GeometryTolerances,
    *,
    waler_context: Sequence[WalerSpanReference] | None = None,
) -> _BlockMemberRouteResult:
    """Compatibility wrapper for the established Strut-only router."""

    if group.role != "strut":
        return _BlockMemberRouteResult(False)
    return _route_component_like_member_block_with(
        group,
        tolerances,
        recognize_component_like_strut,
        waler_context=waler_context,
    )


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

    # A straight MLINE already carries its physical rail spacing.  Preserve
    # that width for material recognition and expose both rails so a Waler can
    # select its support-side contact face and opposite outer face.
    straight_mlines = [
        primitive
        for primitive in group.primitives
        if (
            primitive.entity_type == "MLINE"
            and len(primitive.points) == 2
            and primitive.source_width > 0.0
        )
    ]
    if len(straight_mlines) == 1:
        primitive = straight_mlines[0]
        start, end = _ordered_line(*primitive.points)
        axis = _unit(start, end)
        if axis is not None:
            normal = -axis[1], axis[0]
            half_width = primitive.source_width / 2.0
            boundaries = tuple(
                _ordered_line(
                    (
                        start[0] + normal[0] * offset,
                        start[1] + normal[1] * offset,
                    ),
                    (
                        end[0] + normal[0] * offset,
                        end[1] + normal[1] * offset,
                    ),
                )
                for offset in (-half_width, half_width)
            )
            return (
                _Candidate(
                    start,
                    end,
                    "mline_center_path",
                    True,
                    primitive.source_width,
                    0.99,
                    group.layer,
                    set(group.handles),
                    set(group.entity_types),
                    list(group.block_instances),
                    {group.key},
                    [],
                    boundaries,
                    recognized_axis=(start, end),
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


def _characterize_waler_candidate_envelope(
    candidate: _Candidate,
    group: _GeometryGroup,
    tolerances: GeometryTolerances,
) -> list[ValidationMessage]:
    """Attach pre-collapse Waler envelope facts without selecting contact side."""

    raw_segments = tuple(
        segment
        for primitive in group.primitives
        for segment in primitive.segments()
    )
    qualified_faces = (
        candidate.boundary_lines
        if candidate.recognition_method == "mline_center_path"
        else None
    )
    outcome = extract_waler_envelope_facts(
        raw_segments,
        tolerances,
        source_handles=tuple(sorted(group.handles)),
        component_key=group.key,
        qualified_exterior_faces=qualified_faces,
        provenance_kind=(
            "mline_exterior"
            if qualified_faces is not None
            else "connected_contour"
        ),
    )
    if outcome.status in {
        WalerEnvelopeStatus.UNRESOLVED,
        WalerEnvelopeStatus.AMBIGUOUS,
    }:
        return [
            ValidationMessage(
                "error",
                outcome.code,
                outcome.message,
                "waler",
                tuple(sorted(group.handles)),
            )
        ]
    if len(outcome.facts) != 1:
        return [
            ValidationMessage(
                "error",
                "WALER_ENVELOPE_AMBIGUOUS",
                "同一來源可分離出多個完整圍令構件，但無法在既有單一來源模型中唯一提交。",
                "waler",
                tuple(sorted(group.handles)),
            )
        ]

    fact = outcome.facts[0]
    candidate.start, candidate.end = fact.provisional_axis
    candidate.recognized_axis = fact.provisional_axis
    candidate.boundary_lines = fact.outer_faces
    candidate.source_width = fact.source_width
    candidate.waler_envelope_facts = (fact,)
    return []


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
            BIM_JOIST_PAIRED_AXIS_METHOD: 6,
            BIM_JOIST_SINGLE_AXIS_METHOD: 6,
            BIM_BLOCK_WHOLE_AXIS_METHOD: 5,
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
                if not (
                    BIM_BLOCK_WHOLE_AXIS_METHOD
                    in {item.recognition_method, candidate.recognition_method}
                    and item.source_keys.isdisjoint(candidate.source_keys)
                )
                and _lines_duplicate(
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


def _normalized_source_identity(handles: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(handle).strip().upper()
                for handle in handles
                if str(handle).strip()
            }
        )
    )


def _apply_terminal_resolutions(
    candidates_by_role: dict[str, list[_Candidate]],
    resolutions: Sequence[WalerContactResolution],
    terminal_evidence: Sequence[Any],
    tolerances: GeometryTolerances,
) -> list[ValidationMessage]:
    """Atomically update staged Waler faces and related member terminals."""

    resolution_by_identity = {
        _normalized_source_identity(item.source_handles): item
        for item in resolutions
    }
    for candidate in candidates_by_role.get("waler", ()):
        identity = _normalized_source_identity(candidate.handles)
        resolution = resolution_by_identity.get(identity)
        if resolution is None:
            continue
        candidate.start, candidate.end = resolution.selected_face
        candidate.centerline_computed = False
        candidate.recognition_method = (
            "existing_inner_line"
            if resolution.side_sign == 0
            else "inner_boundary_line"
        )

    evidence_by_member: dict[
        tuple[str, tuple[str, ...]], list[Any]
    ] = {}
    for item in terminal_evidence:
        evidence_by_member.setdefault(
            (item.member_role, _normalized_source_identity(item.member_source_handles)),
            [],
        ).append(item)

    messages: list[ValidationMessage] = []
    for role in ("strut", "brace"):
        for candidate in candidates_by_role.get(role, ()):
            identity = _normalized_source_identity(candidate.handles)
            evidence = evidence_by_member.get((role, identity), ())
            if not evidence:
                continue
            source_axis = candidate.recognized_axis or (
                candidate.start,
                candidate.end,
            )
            staged_points = {
                "start": candidate.start,
                "end": candidate.end,
            }
            failed = False
            for item in evidence:
                resolution = resolution_by_identity.get(
                    _normalized_source_identity(item.waler_source_handles)
                )
                if resolution is None:
                    failed = True
                    continue
                intersection = _line_segment_intersection_point(
                    source_axis,
                    resolution.selected_face,
                    tolerances.endpoint_tolerance_mm,
                )
                if intersection is None:
                    failed = True
                    continue
                staged_points[item.terminal_name] = intersection
            staged_line = _ordered_line(
                staged_points["start"],
                staged_points["end"],
            )
            if (
                failed
                or _length(*staged_line)
                < tolerances.minimum_component_length_mm
            ):
                messages.append(
                    ValidationMessage(
                        "error",
                        (
                            "BIM_BLOCK_WALER_FINALIZE_FAILED"
                            if role == "strut"
                            and candidate.selected_waler_source_handles
                            else "WALER_CONTACT_FINALIZE_FAILED"
                        ),
                        "構件已選定的圍令接觸面無法與來源工程軸建立有效交點。",
                        role,
                        tuple(sorted(candidate.handles)),
                    )
                )
                continue
            candidate.start, candidate.end = staged_line
            candidate.waler_intersections = tuple(
                staged_points[name]
                for name in ("start", "end")
                if name in {item.terminal_name for item in evidence}
            )
    return messages


def _resolve_waler_contact_geometry(
    candidates_by_role: dict[str, list[_Candidate]],
    tolerances: GeometryTolerances,
) -> list[ValidationMessage]:
    """Stage terminal topology, contact resolution, and canonical geometry."""

    envelope_facts = tuple(
        fact
        for candidate in candidates_by_role.get("waler", ())
        for fact in candidate.waler_envelope_facts
    )
    member_facts = tuple(
        MemberGeometryFacts(
            role=role,
            source_handles=_normalized_source_identity(candidate.handles),
            axis=candidate.recognized_axis
            or _ordered_line(candidate.start, candidate.end),
            selected_waler_source_handles=(
                candidate.selected_waler_source_handles
                if role == "strut"
                else ()
            ),
            allow_axis_extension=True,
        )
        for role in ("strut", "brace")
        for candidate in candidates_by_role.get(role, ())
    )
    topology = build_member_terminal_evidence(
        member_facts,
        envelope_facts,
        tolerances,
    )
    contact = resolve_waler_contact_faces(
        envelope_facts,
        topology.evidence,
        tolerances,
    )
    messages = [
        ValidationMessage(
            item.severity,
            item.code,
            item.message,
            item.role,
            tuple(
                dict.fromkeys(
                    (
                        *item.source_handles,
                        *(
                            handle
                            for identity in item.competing_waler_source_handles
                            for handle in identity
                        ),
                    )
                )
            ),
        )
        for item in topology.issues
    ]
    messages.extend(
        ValidationMessage(
            "error",
            item.code,
            item.message,
            "waler",
            tuple(
                dict.fromkeys(
                    (*item.source_handles, *item.member_source_handles)
                )
            ),
        )
        for item in contact.issues
    )

    staged = copy.deepcopy(candidates_by_role)
    try:
        messages.extend(
            _apply_terminal_resolutions(
                staged,
                contact.resolutions,
                topology.evidence,
                tolerances,
            )
        )
        messages.extend(
            _refine_corner_brace_axis_intersections(staged, tolerances)
        )
    except Exception as exc:
        messages.append(
            ValidationMessage(
                "critical",
                "WALER_CONTACT_FINALIZE_FAILED",
                f"圍令接觸面 staged finalization 失敗：{exc}",
                "waler",
            )
        )
        return messages

    candidates_by_role.clear()
    candidates_by_role.update(staged)
    return messages


def _build_waler_span_context(
    candidates: Sequence[_Candidate],
) -> tuple[WalerSpanReference, ...]:
    """Freeze formal Waler candidates for the downstream Strut stage.

    The snapshot contains only candidates that survived Waler recognition and
    de-duplication.  Excluded, unresolved, and preview-only geometry therefore
    cannot enter contextual Strut recognition.
    """

    references: list[WalerSpanReference] = []
    for candidate in candidates:
        source_handles = tuple(
            sorted(
                str(handle).strip().upper()
                for handle in candidate.handles
                if str(handle).strip()
            )
        )
        if not source_handles:
            continue
        reference_segment = candidate.recognized_axis or (
            candidate.start,
            candidate.end,
        )
        references.append(
            WalerSpanReference(
                source_handles=source_handles,
                reference_segment=reference_segment,
                boundary_segments=tuple(candidate.boundary_lines),
            )
        )
    return tuple(
        sorted(
            references,
            key=lambda item: (
                item.source_handles,
                item.reference_segment,
                item.boundary_segments,
            ),
        )
    )


def _finalize_contextual_strut_waler_spans(
    candidates_by_role: dict[str, list[_Candidate]],
    tolerances: GeometryTolerances,
) -> list[ValidationMessage]:
    """Move contextual Strut endpoints onto the selected canonical Waler faces.

    Recognition selects immutable Waler source identities.  This later stage
    resolves those same identities after ``_select_waler_inner_lines`` has
    chosen the engineering contact face; it never substitutes another Waler.
    """

    walers_by_identity = {
        tuple(
            sorted(
                str(handle).strip().upper()
                for handle in candidate.handles
                if str(handle).strip()
            )
        ): candidate
        for candidate in candidates_by_role.get("waler", ())
    }
    retained: list[_Candidate] = []
    messages: list[ValidationMessage] = []
    for candidate in candidates_by_role.get("strut", ()):
        selected = candidate.selected_waler_source_handles
        if not selected:
            retained.append(candidate)
            continue
        axis = candidate.recognized_axis or (candidate.start, candidate.end)
        finalized_points: list[Point] = []
        finalization_failed = len(selected) != 2
        for identity in selected:
            normalized_identity = tuple(
                sorted(
                    str(handle).strip().upper()
                    for handle in identity
                    if str(handle).strip()
                )
            )
            waler = walers_by_identity.get(normalized_identity)
            if waler is None:
                finalization_failed = True
                continue
            intersection = _line_segment_intersection_point(
                axis,
                (waler.start, waler.end),
                tolerances.endpoint_tolerance_mm,
            )
            if intersection is None:
                finalization_failed = True
                continue
            finalized_points.append(intersection)
        if (
            finalization_failed
            or len(finalized_points) != 2
            or _distance(*finalized_points)
            < tolerances.minimum_component_length_mm
        ):
            related_handles = {
                str(handle).strip().upper()
                for handle in candidate.handles
                if str(handle).strip()
            }
            contextual_handles = tuple(
                dict.fromkeys(
                    handle for identity in selected for handle in identity
                )
            )
            messages.append(
                ValidationMessage(
                    "error",
                    "BIM_BLOCK_WALER_FINALIZE_FAILED",
                    "BIM 支撐已選定的圍令在接觸面定案後無法維持有效交點，"
                    "因此未建立正式支撐。"
                    + (
                        f"（候選圍令來源：{', '.join(contextual_handles)}）"
                        if contextual_handles
                        else ""
                    ),
                    "strut",
                    tuple(sorted(related_handles)),
                )
            )
            continue
        final_axis = _ordered_line(*finalized_points)
        candidate.start, candidate.end = final_axis
        candidate.recognized_axis = final_axis
        candidate.waler_intersections = final_axis
        retained.append(candidate)
    candidates_by_role["strut"] = retained
    return messages


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
    """Move reliable corner-brace axes to their member intersections.

    Connection-plate and parallel-edge recognition can both retain the two
    original longitudinal rails.  Their midline, rather than the preliminary
    endpoints, is extended to the selected Waler inner line and Strut
    centreline.  Legacy connection-plate candidates retain their established
    face-midpoint fallback when no reliable rail midline is available.
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
        legacy_connection_plate = (
            candidate.recognition_method == "connection_plate_midpoints"
        )
        brace_axis = _corner_brace_center_axis(candidate, tolerances)
        if brace_axis is None and not legacy_connection_plate:
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
        if (
            legacy_connection_plate
            and (waler_contact is None or strut_contact is None)
        ):
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
                    (
                        "角撐連接板無法建立圍令端與支撐端接觸中點。"
                        if legacy_connection_plate
                        else "角撐中心軸無法同時與圍令內線及支撐中心線建立有效有限交點。"
                    ),
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
        refined_line = _ordered_line(
            waler_contact,
            strut_contact,
        )
        if (
            recognition_method == "brace_centerline_intersections"
            and _length(*refined_line) < tolerances.minimum_component_length_mm
        ):
            messages.append(
                ValidationMessage(
                    "error",
                    "CORNER_BRACE_CONNECTION_POINT_FAILED",
                    "角撐中心軸校正後的工程長度過短。",
                    "corner_brace",
                    tuple(sorted(candidate.handles)),
                )
            )
            continue
        candidate.start, candidate.end = refined_line
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
