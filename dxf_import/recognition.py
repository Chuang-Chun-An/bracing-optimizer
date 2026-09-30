"""Recognize engineering axes and sections from DXF primitives."""

from __future__ import annotations

from dataclasses import dataclass
import copy
import math
from typing import Any, Mapping, MutableMapping, Sequence

from .block_member_recognition import (
    BlockMemberPrimitive,
    BlockMemberRecognitionInput,
    BlockMemberRecognitionStatus,
    WalerSpanReference,
    brace_body_width_is_eligible,
    brace_outline_centerline,
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
    _closest_points_between_segments,
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
    CornerBraceBodyGeometryEvidence,
    CornerBraceBodyRelationshipAssessment,
    EngineeringLineCandidate,
    GeometryTolerances,
    StrutTerminalTopology,
    ValidationMessage,
)
from .corner_brace_recognition import (
    CornerBraceSourceSegment,
    assess_corner_brace_relationship,
    build_corner_brace_body_hypotheses,
    select_corner_brace_body_outcome,
)
from .waler_contact_face import (
    BraceTerminalVerdict,
    MemberGeometryFacts,
    TerminalIdentityState,
    WalerContactResolution,
    WalerEnvelopeFacts,
    WalerEnvelopeStatus,
    build_brace_terminal_verdicts,
    build_member_terminal_evidence,
    extract_waler_envelope_facts,
    find_significant_waler_overlaps,
    find_waler_overlap_competitions,
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
    waler_terminal_source_handles: tuple[
        tuple[str, tuple[str, ...], str], ...
    ] = ()
    waler_terminal_blocked: bool = False
    brace_terminal_verdict: BraceTerminalVerdict | None = None
    waler_terminal_topology: tuple[StrutTerminalTopology, ...] = ()
    waler_contact_face_state: str = "provisional"
    selected_rail_lines: tuple[tuple[Point, Point], ...] = ()
    corner_brace_candidate_kind: str = ""
    corner_brace_group_key: str = ""
    corner_brace_evidence: tuple[str, ...] = ()
    corner_brace_body_evidence: CornerBraceBodyGeometryEvidence | None = None
    corner_brace_relationship_assessments: tuple[
        CornerBraceBodyRelationshipAssessment, ...
    ] = ()
    corner_brace_occluding_lines: tuple[tuple[Point, Point], ...] = ()
    corner_brace_body_resolution: str = "unique"


@dataclass(frozen=True)
class _CornerBraceRailHypothesis:
    """Measured rail-pair evidence before it becomes a formal candidate."""

    first_index: int
    second_index: int
    first: tuple[Point, Point]
    second: tuple[Point, Point]
    separation: float
    projection_overlap_ratio: float
    length_ratio: float
    start_plate: tuple[int, tuple[Point, Point], float] | None = None
    end_plate: tuple[int, tuple[Point, Point], float] | None = None
    score: float = 0.0
    occlusion_evidence: tuple[tuple[Point, Point], ...] = ()
    rejection_reasons: tuple[str, ...] = ()

    @property
    def selected_rail_lines(self) -> tuple[tuple[Point, Point], ...]:
        return tuple(
            sorted(
                (
                    _ordered_line(*self.first),
                    _ordered_line(*self.second),
                )
            )
        )


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
        "BRACE_BODY_WIDTH_TOO_SMALL": (
            "BIM 斜撐已量得本體寬度，但寬度未嚴格大於 250.0 mm，"
            "因此未建立正式斜撐。"
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


def _corner_brace_rail_separation(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
) -> float:
    """Return the symmetric perpendicular distance between supporting lines.

    CornerBrace material width is a line-to-line measurement.  Finite rail
    overhangs therefore must not increase the value as they do in the generic
    segment-separation helper.
    """

    return (
        _line_distance(_midpoint(*first), *second)
        + _line_distance(_midpoint(*second), *first)
    ) / 2.0


def _legacy_corner_brace_candidates_from_group(
    group: _GeometryGroup,
    tolerances: GeometryTolerances,
    *,
    external_occluding_lines: Sequence[tuple[Point, Point]] = (),
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
    rejected: list[tuple[float, tuple[str, ...]]] = []

    def connecting_plates(
        first_point: Point,
        second_point: Point,
        excluded: set[int],
    ) -> tuple[tuple[int, tuple[Point, Point], float], ...]:
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
        return tuple(
            (index, segment, error)
            for error, index, segment in sorted(
                matches,
                key=lambda item: (
                    item[0],
                    _ordered_line(*item[2]),
                    item[1],
                ),
            )
        )

    def aligned_pair(
        first: tuple[Point, Point],
        second: tuple[Point, Point],
    ) -> tuple[tuple[Point, Point], tuple[Point, Point]]:
        direct_error = _distance(first[0], second[0]) + _distance(
            first[1],
            second[1],
        )
        reverse_error = _distance(first[0], second[1]) + _distance(
            first[1],
            second[0],
        )
        aligned_second = (
            second
            if direct_error <= reverse_error
            else (second[1], second[0])
        )
        return first, aligned_second

    def hypotheses_equivalent(
        first: _CornerBraceRailHypothesis,
        second: _CornerBraceRailHypothesis,
    ) -> bool:
        # CornerBrace block definitions commonly repeat the same rail/end
        # plate with small drafting offsets.  D4 treats these as geometric
        # equivalents using the existing endpoint tolerance, before any
        # splittability/ambiguity decision; ordering or score must not choose
        # between them.
        tolerance = tolerances.endpoint_tolerance_mm
        first_rails = first.selected_rail_lines
        second_rails = second.selected_rail_lines
        rails_equal = (
            _same_line(first_rails[0], second_rails[0], tolerance)
            and _same_line(first_rails[1], second_rails[1], tolerance)
        ) or (
            _same_line(first_rails[0], second_rails[1], tolerance)
            and _same_line(first_rails[1], second_rails[0], tolerance)
        )
        if not rails_equal:
            return False

        def plate_lines(
            hypothesis: _CornerBraceRailHypothesis,
        ) -> tuple[tuple[Point, Point], ...]:
            return tuple(
                _ordered_line(*plate[1])
                for plate in (hypothesis.start_plate, hypothesis.end_plate)
                if plate is not None
            )

        first_plates = plate_lines(first)
        second_plates = plate_lines(second)
        return len(first_plates) == len(second_plates) and all(
            any(_same_line(line, other, tolerance) for other in second_plates)
            for line in first_plates
        )

    def deduplicate_hypotheses(
        hypotheses: Sequence[_CornerBraceRailHypothesis],
    ) -> list[_CornerBraceRailHypothesis]:
        unique: list[_CornerBraceRailHypothesis] = []
        for hypothesis in sorted(
            hypotheses,
            key=lambda item: (
                item.selected_rail_lines,
                -item.separation,
                -item.length_ratio,
            ),
        ):
            if not any(
                hypotheses_equivalent(hypothesis, existing)
                for existing in unique
            ):
                unique.append(hypothesis)
        return unique

    def hypothesis_conflicts(
        first: _CornerBraceRailHypothesis,
        second: _CornerBraceRailHypothesis,
    ) -> bool:
        first_rails = {first.first_index, first.second_index}
        second_rails = {second.first_index, second.second_index}
        if first_rails.intersection(second_rails):
            return True
        first_plates = {
            plate[0]
            for plate in (first.start_plate, first.end_plate)
            if plate is not None
        }
        second_plates = {
            plate[0]
            for plate in (second.start_plate, second.end_plate)
            if plate is not None
        }
        return bool(first_plates.intersection(second_plates))

    def unique_splittable_set(
        hypotheses: Sequence[_CornerBraceRailHypothesis],
    ) -> tuple[list[_CornerBraceRailHypothesis], bool]:
        ordered = list(hypotheses)
        best_size = -1
        best_sets: list[tuple[int, ...]] = []

        def search(index: int, chosen: tuple[int, ...]) -> None:
            nonlocal best_size, best_sets
            if len(chosen) + len(ordered) - index < best_size:
                return
            if index == len(ordered):
                size = len(chosen)
                if size > best_size:
                    best_size = size
                    best_sets = [chosen]
                elif size == best_size:
                    best_sets.append(chosen)
                return
            search(index + 1, chosen)
            candidate = ordered[index]
            if not any(
                hypothesis_conflicts(candidate, ordered[selected_index])
                for selected_index in chosen
            ):
                search(index + 1, (*chosen, index))

        search(0, ())
        nonempty_sets = [item for item in best_sets if item]
        if not nonempty_sets:
            return [], False
        unique_sets = tuple(dict.fromkeys(nonempty_sets))
        if len(unique_sets) != 1:
            return [], True
        return [ordered[index] for index in unique_sets[0]], False

    def source_points() -> tuple[Point, ...]:
        return tuple(
            dict.fromkeys(
                point
                for primitive in group.primitives
                for point in primitive.points
            )
        )

    def candidate_from_hypothesis(
        hypothesis: _CornerBraceRailHypothesis,
        *,
        kind: str,
    ) -> _Candidate:
        if kind == "complete":
            assert hypothesis.start_plate is not None
            assert hypothesis.end_plate is not None
            start, end = _ordered_line(
                _midpoint(*hypothesis.start_plate[1]),
                _midpoint(*hypothesis.end_plate[1]),
            )
            recognition_method = "connection_plate_midpoints"
            confidence = 0.99
        else:
            axis = _rail_pair_midline(
                hypothesis.first,
                hypothesis.second,
            )
            assert axis is not None
            start, end = axis
            recognition_method = "occluded_parallel_rails"
            confidence = 0.90
        plates = tuple(
            _ordered_line(*plate[1])
            for plate in (hypothesis.start_plate, hypothesis.end_plate)
            if plate is not None
        )
        boundary_lines = tuple(
            dict.fromkeys(
                (
                    *hypothesis.selected_rail_lines,
                    *plates,
                    *hypothesis.occlusion_evidence,
                )
            )
        )
        return _Candidate(
            start,
            end,
            recognition_method,
            True,
            hypothesis.separation,
            confidence,
            group.layer,
            set(group.handles),
            set(group.entity_types),
            list(group.block_instances),
            {
                f"{group.key}:corner_brace:"
                f"{hypothesis.first_index}:{hypothesis.second_index}"
            },
            [],
            boundary_lines,
            recognized_axis=(start, end),
            reference_point=_midpoint(start, end),
            source_points=source_points(),
            selected_rail_lines=hypothesis.selected_rail_lines,
            corner_brace_candidate_kind=kind,
            corner_brace_group_key=group.key,
            corner_brace_evidence=(
                f"rail_separation_mm={hypothesis.separation:.6f}",
                (
                    "projection_overlap_ratio="
                    f"{hypothesis.projection_overlap_ratio:.6f}"
                ),
                f"rail_length_ratio={hypothesis.length_ratio:.6f}",
                *hypothesis.rejection_reasons,
                *(
                    ("terminal_occlusion_evidence=finite",)
                    if hypothesis.occlusion_evidence
                    else ()
                ),
            ),
        )

    def unresolved_message(
        reasons: Sequence[str],
        widths: Sequence[float],
    ) -> ValidationMessage:
        width_text = (
            ", ".join(f"{value:.3f}" for value in sorted(set(widths)))
            if widths
            else "none"
        )
        reason_text = ", ".join(dict.fromkeys(reasons)) or "no_legal_hypothesis"
        return ValidationMessage(
            "error",
            "CORNER_BRACE_RAIL_CANDIDATE_UNRESOLVED",
            (
                "角撐本體 rail 無唯一合法解；"
                f"evaluated_widths_mm=[{width_text}]；reasons=[{reason_text}]。"
            ),
            "corner_brace",
            tuple(sorted(group.handles)),
        )

    complete: list[_CornerBraceRailHypothesis] = []
    fallback_pairs: list[_CornerBraceRailHypothesis] = []

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
            separation = _corner_brace_rail_separation(first, second)
            if not (
                tolerances.collinear_tolerance_mm
                < separation
                <= tolerances.maximum_component_width_mm
            ):
                continue
            overlap_ratio = _projection_overlap_ratio(first, second)
            length_ratio = min(first_length, second_length) / max(
                first_length,
                second_length,
            )
            pair_reasons: list[str] = []
            if (
                separation
                <= tolerances.minimum_corner_brace_rail_separation_mm
            ):
                pair_reasons.append("rail_separation_not_above_minimum")
            if (
                min(first_length, second_length)
                / max(separation, 1e-9)
                < tolerances.minimum_slenderness_ratio
            ):
                pair_reasons.append("rail_slenderness_below_minimum")
            equal_length = abs(first_length - second_length) <= max(
                tolerances.width_tolerance_mm,
                max(first_length, second_length) * 0.05,
            )
            aligned_first, aligned_second = aligned_pair(first, second)
            excluded = {first_index, second_index}
            start_plates = connecting_plates(
                aligned_first[0],
                aligned_second[0],
                excluded,
            )
            end_plates = connecting_plates(
                aligned_first[1],
                aligned_second[1],
                excluded,
            )
            if not start_plates:
                pair_reasons.append("complete_start_plate_missing")
            if not end_plates:
                pair_reasons.append("complete_end_plate_missing")
            eligible_complete_pair = not pair_reasons
            if eligible_complete_pair:
                for start_plate in start_plates:
                    for end_plate in end_plates:
                        if start_plate[0] == end_plate[0]:
                            continue
                        start_midpoint = _midpoint(*start_plate[1])
                        end_midpoint = _midpoint(*end_plate[1])
                        if (
                            _length(start_midpoint, end_midpoint)
                            < tolerances.minimum_component_length_mm
                        ):
                            continue
                        complete.append(
                            _CornerBraceRailHypothesis(
                                first_index=first_index,
                                second_index=second_index,
                                first=aligned_first,
                                second=aligned_second,
                                separation=separation,
                                projection_overlap_ratio=overlap_ratio,
                                length_ratio=length_ratio,
                                start_plate=start_plate,
                                end_plate=end_plate,
                                score=(
                                    first_length
                                    + second_length
                                    - start_plate[2]
                                    - end_plate[2]
                                ),
                                rejection_reasons=(
                                    (
                                        "complete_parallel_rail_closed_traversal"
                                        if equal_length
                                        else "complete_mitered_closed_traversal"
                                    ),
                                ),
                            )
                        )
            else:
                rejected.append((separation, tuple(pair_reasons)))
            fallback_pairs.append(
                _CornerBraceRailHypothesis(
                    first_index=first_index,
                    second_index=second_index,
                    first=aligned_first,
                    second=aligned_second,
                    separation=separation,
                    projection_overlap_ratio=overlap_ratio,
                    length_ratio=length_ratio,
                    start_plate=start_plates[0] if start_plates else None,
                    end_plate=end_plates[0] if end_plates else None,
                    rejection_reasons=tuple(pair_reasons),
                )
            )

    complete = deduplicate_hypotheses(complete)
    if complete:
        selected_complete, ambiguous = unique_splittable_set(complete)
        if ambiguous:
            return [], [
                unresolved_message(
                    ("complete_candidate_evidence_ambiguous",),
                    tuple(item.separation for item in complete),
                )
            ]
        return [
            candidate_from_hypothesis(item, kind="complete")
            for item in selected_complete
        ], []

    def missing_continuations(
        hypothesis: _CornerBraceRailHypothesis,
    ) -> tuple[tuple[Point, tuple[Point, Point]], ...]:
        first = hypothesis.first
        second = hypothesis.second
        if _length(*first) >= _length(*second):
            long_rail, short_rail = first, second
        else:
            long_rail, short_rail = second, first
        axis = _unit(*long_rail)
        if axis is None:
            return ()
        long_length = _length(*long_rail)
        short_points = sorted(
            (
                _dot(_vector(long_rail[0], point), axis),
                point,
            )
            for point in short_rail
        )
        corridors: list[tuple[Point, tuple[Point, Point]]] = []
        start_gap = max(0.0, short_points[0][0])
        end_gap = max(0.0, long_length - short_points[1][0])
        if start_gap > tolerances.endpoint_tolerance_mm:
            terminal = short_points[0][1]
            ideal = (
                terminal[0] - axis[0] * start_gap,
                terminal[1] - axis[1] * start_gap,
            )
            corridors.append((terminal, (ideal, terminal)))
        if end_gap > tolerances.endpoint_tolerance_mm:
            terminal = short_points[1][1]
            ideal = (
                terminal[0] + axis[0] * end_gap,
                terminal[1] + axis[1] * end_gap,
            )
            corridors.append((terminal, (terminal, ideal)))
        if corridors:
            return tuple(corridors)

        # Equal-length rails can still lose one terminal plate.  In that case
        # the finite neighborhood immediately inward from the missing plate is
        # the only admissible occlusion corridor.
        neighborhood = tolerances.endpoint_tolerance_mm
        if hypothesis.start_plate is None:
            terminal = short_rail[0]
            corridors.append(
                (
                    terminal,
                    (
                        terminal,
                        (
                            terminal[0] + axis[0] * neighborhood,
                            terminal[1] + axis[1] * neighborhood,
                        ),
                    ),
                )
            )
        if hypothesis.end_plate is None:
            terminal = short_rail[1]
            corridors.append(
                (
                    terminal,
                    (
                        terminal,
                        (
                            terminal[0] - axis[0] * neighborhood,
                            terminal[1] - axis[1] * neighborhood,
                        ),
                    ),
                )
            )
        return tuple(corridors)

    occluded: list[_CornerBraceRailHypothesis] = []
    finite_external = tuple(
        line for line in external_occluding_lines if _length(*line) > 1e-9
    )
    for pair in fallback_pairs:
        reasons: list[str] = []
        if (
            pair.separation
            <= tolerances.minimum_corner_brace_rail_separation_mm
        ):
            reasons.append("rail_separation_not_above_minimum")
        if (
            pair.length_ratio
            < tolerances.minimum_corner_brace_occluded_rail_length_ratio
        ):
            reasons.append("occluded_rail_length_ratio_below_minimum")
        if (
            min(_length(*pair.first), _length(*pair.second))
            / max(pair.separation, 1e-9)
            < tolerances.minimum_slenderness_ratio
        ):
            reasons.append("rail_slenderness_below_minimum")
        if pair.start_plate is None and pair.end_plate is None:
            reasons.append("connection_plate_evidence_missing")
        corridors = missing_continuations(pair)
        if not corridors:
            reasons.append("terminal_occlusion_corridor_missing")
        excluded_indices = {pair.first_index, pair.second_index}
        excluded_indices.update(
            plate[0]
            for plate in (pair.start_plate, pair.end_plate)
            if plate is not None
        )
        possible_occluders = tuple(
            segment
            for index, segment in enumerate(segments)
            if index not in excluded_indices and _length(*segment) > 1e-9
        ) + finite_external
        evidence: list[tuple[Point, Point]] = []
        for terminal, corridor in corridors:
            for line in possible_occluders:
                corridor_point, line_point, distance = (
                    _closest_points_between_segments(corridor, line)
                )
                if distance > tolerances.collinear_tolerance_mm:
                    continue
                if (
                    _distance(corridor_point, terminal)
                    > tolerances.connection_tolerance_mm
                ):
                    continue
                if not any(
                    _same_line(
                        _ordered_line(*line),
                        _ordered_line(*existing),
                    )
                    for existing in evidence
                ):
                    evidence.append(_ordered_line(*line))
        if not evidence:
            reasons.append("terminal_occlusion_evidence_missing")
        if reasons:
            rejected.append((pair.separation, tuple(reasons)))
            continue
        occluded.append(
            _CornerBraceRailHypothesis(
                first_index=pair.first_index,
                second_index=pair.second_index,
                first=pair.first,
                second=pair.second,
                separation=pair.separation,
                projection_overlap_ratio=pair.projection_overlap_ratio,
                length_ratio=pair.length_ratio,
                start_plate=pair.start_plate,
                end_plate=pair.end_plate,
                occlusion_evidence=tuple(evidence),
            )
        )

    occluded = deduplicate_hypotheses(occluded)
    if occluded:
        # Finite Waler/Strut association is intentionally deferred until all
        # engineering roles are staged.  The refinement step resolves this
        # group atomically and rejects zero or multiple surviving hypotheses.
        return [
            candidate_from_hypothesis(item, kind="occluded")
            for item in occluded
        ], []

    reasons = tuple(
        reason
        for _width, item_reasons in rejected
        for reason in item_reasons
    )
    widths = tuple(width for width, _item_reasons in rejected)
    return [], [unresolved_message(reasons, widths)]


def _corner_brace_candidates_from_group(
    group: _GeometryGroup,
    tolerances: GeometryTolerances,
    *,
    external_occluding_lines: Sequence[tuple[Point, Point]] = (),
) -> tuple[list[_Candidate], list[ValidationMessage]]:
    """Recognize CornerBrace bodies from order-independent RailTracks.

    This definition intentionally supersedes the legacy finite-line pair
    implementation above while the migration remains reviewable in one
    change.  No Waler/Strut relationship fact is computed here.
    """

    sources: list[CornerBraceSourceSegment] = []
    for primitive_index, primitive in enumerate(group.primitives):
        for segment_index, segment in enumerate(primitive.segments()):
            if _length(*segment) <= 1e-9:
                continue
            sources.append(
                CornerBraceSourceSegment(
                    id=(
                        f"{primitive.source_handle}:"
                        f"{primitive_index}:{segment_index}"
                    ),
                    source_handle=primitive.source_handle,
                    line=_ordered_line(*segment),
                )
            )
    bodies = build_corner_brace_body_hypotheses(
        group.key,
        tuple(sorted(group.handles)),
        tuple(sources),
        tolerances,
    )
    selected, ambiguous = select_corner_brace_body_outcome(bodies)
    body_messages: list[ValidationMessage] = []
    if not selected:
        reason = (
            "multiple_body_hypotheses"
            if ambiguous
            else "zero_body_hypotheses"
        )
        body_messages = [
            ValidationMessage(
                "error",
                "CORNER_BRACE_BODY_UNRESOLVED",
                (
                    "角撐本體無法唯一辨識；"
                    f"body_hypothesis_count={len(bodies)}；"
                    f"reason={reason}。"
                ),
                "corner_brace",
                tuple(sorted(group.handles)),
            )
        ]
        if not ambiguous:
            return [], body_messages
        selected = bodies

    source_points = tuple(
        dict.fromkeys(
            point
            for primitive in group.primitives
            for point in primitive.points
        )
    )
    candidates: list[_Candidate] = []
    for body in selected:
        selected_fragment_ids = {
            fragment.id for fragment in body.fragments
        }
        occluding_lines = tuple(
            dict.fromkeys(
                (
                    *(
                        source.line
                        for source in sources
                        if source.id not in selected_fragment_ids
                    ),
                    *(
                        _ordered_line(*line)
                        for line in external_occluding_lines
                        if _length(*line) > 1e-9
                    ),
                )
            )
        )
        boundary_lines = tuple(
            dict.fromkeys(
                (
                    *(track.supporting_line for track in body.rail_tracks),
                    *body.terminal_plate_evidence,
                    *occluding_lines,
                )
            )
        )
        candidates.append(
            _Candidate(
                start=body.midline[0],
                end=body.midline[1],
                recognition_method="corner_brace_body_tracks",
                centerline_computed=True,
                source_width=body.rail_separation_mm,
                confidence=0.95,
                layer=group.layer,
                handles=set(group.handles),
                entity_types=set(group.entity_types),
                block_instances=list(group.block_instances),
                source_keys={
                    f"{group.key}:corner_brace_body:{body.signature}"
                },
                warnings=[],
                boundary_lines=boundary_lines,
                recognized_axis=body.midline,
                reference_point=_midpoint(*body.midline),
                source_points=source_points,
                selected_rail_lines=tuple(
                    track.supporting_line for track in body.rail_tracks
                ),
                corner_brace_candidate_kind="body",
                corner_brace_group_key=group.key,
                corner_brace_evidence=(
                    f"body_signature={body.signature}",
                    f"rail_separation_mm={body.rail_separation_mm:.6f}",
                    f"terminal_plate_count={len(body.terminal_plate_evidence)}",
                ),
                corner_brace_body_evidence=body,
                corner_brace_occluding_lines=occluding_lines,
                corner_brace_body_resolution=(
                    "multiple" if ambiguous else "unique"
                ),
            )
        )
    return candidates, body_messages


def _candidate_from_group(
    group: _GeometryGroup,
    role: str,
    tolerances: GeometryTolerances,
) -> tuple[_Candidate | None, list[ValidationMessage]]:
    def brace_width_message(
        measured_widths: Sequence[float],
        *,
        unreliable: bool = False,
    ) -> ValidationMessage:
        width_text = ", ".join(
            f"{width:.6f}" for width in sorted(set(measured_widths))
        )
        if unreliable and not width_text:
            detail = "封閉外框無法由兩條外側支承邊可靠量得本體寬度"
        else:
            detail = (
                f"實測本體寬度 [{width_text or 'unknown'}] mm 未嚴格大於 "
                f"{tolerances.minimum_brace_body_width_mm:.1f} mm"
            )
        return ValidationMessage(
            "error",
            (
                "BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE"
                if unreliable and not width_text
                else "BRACE_BODY_WIDTH_TOO_SMALL"
            ),
            f"斜撐{detail}，未建立正式工程線。",
            "brace",
            tuple(sorted(group.handles)),
        )

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
        if role == "brace" and not brace_body_width_is_eligible(
            primitive.source_width,
            tolerances,
        ):
            return None, [brace_width_message((primitive.source_width,))]
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
    rejected_brace_widths: list[float] = []
    unreliable_brace_outline = False
    for primitive in group.primitives:
        if primitive.closed:
            if role == "brace":
                brace_candidate = brace_outline_centerline(
                    primitive.points,
                    tolerances,
                )
                if brace_candidate is None:
                    unreliable_brace_outline = True
                    continue
                if not brace_body_width_is_eligible(
                    brace_candidate[2],
                    tolerances,
                ):
                    rejected_brace_widths.append(brace_candidate[2])
                    continue
                outline_candidates.append(brace_candidate)
                continue
            candidate = outline_centerline(primitive.points, tolerances)
            if candidate is not None:
                axis_line = candidate[0], candidate[1]
                outline_candidates.append(
                    (*candidate, _outline_long_boundary_lines(primitive, axis_line, tolerances))
                )

    segments = [
        segment
        for primitive in group.primitives
        if role != "brace" or not primitive.closed
        for segment in primitive.segments()
    ]
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
            if role == "brace" and not brace_body_width_is_eligible(
                separation,
                tolerances,
            ):
                rejected_brace_widths.append(separation)
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

    if role == "brace" and (
        rejected_brace_widths or unreliable_brace_outline
    ):
        messages.append(
            brace_width_message(
                rejected_brace_widths,
                unreliable=unreliable_brace_outline,
            )
        )
        return None, messages

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
    recognized_component_faces = (
        candidate.boundary_lines
        if (
            qualified_faces is None
            and str(group.root_entity_type).strip().upper() == "INSERT"
            and candidate.recognition_method == "parallel_edges_midline"
        )
        else None
    )
    outcome = extract_waler_envelope_facts(
        raw_segments,
        tolerances,
        source_handles=tuple(sorted(group.handles)),
        component_key=group.key,
        qualified_exterior_faces=qualified_faces,
        recognized_component_faces=recognized_component_faces,
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
    brace_verdicts: Sequence[BraceTerminalVerdict] = (),
) -> list[ValidationMessage]:
    """Atomically update staged Waler faces and related member terminals."""

    resolution_by_identity = {
        _normalized_source_identity(item.source_handles): item
        for item in resolutions
    }
    for candidate in candidates_by_role.get("waler", ()):
        candidate.waler_contact_face_state = "provisional"
        identity = _normalized_source_identity(candidate.handles)
        resolution = resolution_by_identity.get(identity)
        if resolution is None:
            continue
        candidate.start, candidate.end = resolution.selected_face
        candidate.centerline_computed = False
        candidate.waler_contact_face_state = "formal"

    evidence_by_member: dict[
        tuple[str, tuple[str, ...]], list[Any]
    ] = {}
    for item in terminal_evidence:
        if item.identity_state is not TerminalIdentityState.UNIQUE:
            continue
        evidence_by_member.setdefault(
            (item.member_role, _normalized_source_identity(item.member_source_handles)),
            [],
        ).append(item)

    messages: list[ValidationMessage] = []
    for candidate in candidates_by_role.get("strut", ()):
        role = "strut"
        identity = _normalized_source_identity(candidate.handles)
        evidence = evidence_by_member.get((role, identity), ())
        if not evidence:
            continue
        resolved_evidence = tuple(
            item
            for item in evidence
            if _normalized_source_identity(item.waler_source_handles)
            in resolution_by_identity
        )
        candidate.waler_terminal_source_handles = tuple(
            sorted(
                (
                    item.terminal_name,
                    _normalized_source_identity(item.waler_source_handles),
                    item.relation_kind,
                )
                for item in resolved_evidence
            )
        )
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
        if failed or _length(*staged_line) < tolerances.minimum_component_length_mm:
            candidate.waler_terminal_blocked = True
            messages.append(
                ValidationMessage(
                    "error",
                    (
                        "BIM_BLOCK_WALER_FINALIZE_FAILED"
                        if candidate.selected_waler_source_handles
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

    verdict_by_member = {
        _normalized_source_identity(item.member_source_handles): item
        for item in brace_verdicts
    }
    for candidate in candidates_by_role.get("brace", ()):
        identity = _normalized_source_identity(candidate.handles)
        verdict = verdict_by_member.get(identity)
        candidate.brace_terminal_verdict = verdict
        candidate.waler_terminal_source_handles = ()
        candidate.waler_intersections = ()
        if verdict is None:
            candidate.waler_terminal_blocked = True
            messages.append(
                ValidationMessage(
                    "critical",
                    "BRACE_TERMINAL_VERDICT_MISSING",
                    "斜撐正式匯入流程缺少 member-level terminal verdict。",
                    "brace",
                    tuple(sorted(candidate.handles)),
                )
            )
            continue
        if not verdict.is_resolved:
            candidate.waler_terminal_blocked = True
            for code in verdict.reason_codes:
                message = {
                    "BRACE_NOT_CONNECTED": "斜撐兩端皆未唯一連接圍令。",
                    "BRACE_ONE_END_NOT_CONNECTED": "斜撐僅一端唯一連接圍令，整支斜撐維持未解析。",
                    "BRACE_SAME_WALER_CONNECTION": "斜撐兩端連接同一圍令，整支斜撐連接無效。",
                    "WALER_CONTACT_FINALIZE_FAILED": "斜撐軸線無法與兩端正式圍令接觸面建立合法有限交點。",
                }.get(code)
                if message is None:
                    continue
                messages.append(
                    ValidationMessage(
                        "error",
                        code,
                        message,
                        "brace",
                        tuple(sorted(candidate.handles)),
                    )
                )
            continue
        assert verdict.formal_axis is not None
        candidate.start, candidate.end = verdict.formal_axis
        candidate.waler_terminal_source_handles = verdict.terminal_source_handles
        candidate.waler_intersections = tuple(
            point for _terminal_name, point in verdict.terminal_points
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
    for candidate in candidates_by_role.get("strut", ()):
        identity = _normalized_source_identity(candidate.handles)
        resolved = (
            StrutTerminalTopology(
                terminal_name=item.terminal_name,
                waler_source_handles=_normalized_source_identity(
                    item.waler_source_handles
                ),
            )
            for item in topology.unique_evidence
            if item.member_role == "strut"
            and _normalized_source_identity(item.member_source_handles)
            == identity
        )
        unresolved = (
            StrutTerminalTopology(
                terminal_name=item.terminal_name,
                reason_code=item.code,
                competing_waler_source_handles=tuple(
                    sorted(
                        _normalized_source_identity(waler_identity)
                        for waler_identity in item.competing_waler_source_handles
                    )
                ),
                message=item.message,
            )
            for item in topology.issues
            if item.role == "strut"
            and _normalized_source_identity(item.source_handles) == identity
        )
        candidate.waler_terminal_topology = tuple(
            sorted(
                (*resolved, *unresolved),
                key=lambda item: (
                    item.terminal_name,
                    item.reason_code,
                    item.waler_source_handles,
                    item.competing_waler_source_handles,
                ),
            )
        )
    contact = resolve_waler_contact_faces(
        envelope_facts,
        topology.evidence,
        tolerances,
    )
    brace_verdicts = build_brace_terminal_verdicts(
        member_facts,
        topology,
        contact,
        tolerances,
    )
    overlaps = find_significant_waler_overlaps(
        envelope_facts,
        tolerances,
    )
    overlap_competitions = find_waler_overlap_competitions(
        overlaps,
        topology.issues,
        contact.issues,
    )
    messages = [
        ValidationMessage(
            "warning",
            "WALER_SOURCE_OVERLAP",
            (
                "圍令來源 "
                f"{' / '.join(overlap.source_identities[0])} 與 "
                f"{' / '.join(overlap.source_identities[1])} 的 source-supported "
                "provisional axes 有重大共線重疊："
                f"有限重疊長度 {overlap.overlap_length:.3f} mm，"
                f"占較短 provisional axis {overlap.overlap_ratio:.1%}，"
                f"重疊段 {overlap.overlap_segment}。"
                "此 warning 不自動選擇、排除或合併來源。"
            ),
            "waler",
            tuple(
                handle
                for identity in overlap.source_identities
                for handle in identity
            ),
        )
        for overlap in overlaps
    ]
    resolved_brace_terminals = {
        (verdict.member_source_handles, terminal_name, waler_identity)
        for verdict in brace_verdicts
        if verdict.is_resolved
        for terminal_name, waler_identity, _relation_kind
        in verdict.terminal_source_handles
    }
    messages.extend(
        ValidationMessage(
            "error",
            "WALER_OVERLAP_COMPETITION",
            (
                "重大重疊圍令來源 "
                f"{' / '.join(competition.overlap.source_identities[0])} 與 "
                f"{' / '.join(competition.overlap.source_identities[1])} "
                f"同時是同一 {competition.context_kind} "
                f"{competition.context_identity} 的實際競爭 identities"
                + (
                    "（受影響構件來源："
                    f"{' / '.join(competition.member_source_handles)}）"
                    if competition.member_source_handles
                    else ""
                )
                + "。Review 維持阻擋；active sources 變更後會重新辨識，"
                "系統不推薦 winner。"
            ),
            "waler",
            tuple(
                dict.fromkeys(
                    (
                        *(
                            handle
                            for identity in competition.overlap.source_identities
                            for handle in identity
                        ),
                        *competition.member_source_handles,
                    )
                )
            ),
        )
        for competition in overlap_competitions
    )
    messages.extend(
        ValidationMessage(
            item.severity,
            item.code,
            (
                f"{item.role} terminal {item.terminal_name} "
                f"({'axis_extension' if item.code == 'AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION' else 'direct'}) "
                "無法唯一決定 Waler identities "
                f"{', '.join('/'.join(identity) for identity in item.competing_waler_source_handles)}；"
                f"{item.message}"
                if item.terminal_name
                else item.message
            ),
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
    )
    messages.extend(
        ValidationMessage(
            "info",
            "BRACE_AXIS_EXTENDED_TO_WALER",
            "斜撐來源軸已沿端部向外延伸至已辨識圍令的正式接觸面。",
            "brace",
            tuple(
                dict.fromkeys(
                    (*item.member_source_handles, *item.waler_source_handles)
                )
            ),
        )
        for item in topology.unique_evidence
        if item.member_role == "brace"
        and item.relation_kind == "axis_extension"
        and (
            _normalized_source_identity(item.member_source_handles),
            item.terminal_name,
            _normalized_source_identity(item.waler_source_handles),
        )
        in resolved_brace_terminals
    )
    messages.extend(
        ValidationMessage(
            item.severity,
            item.code,
            (
                item.message
                + (
                    " unique 構件來源："
                    f"{' / '.join(item.unique_member_source_handles)}；"
                    "忽略的 competing 構件來源："
                    f"{' / '.join(item.ignored_competing_member_source_handles)}。"
                    if item.code == "WALER_COMPETING_SIDE_EVIDENCE_IGNORED"
                    else ""
                )
            ),
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
    blocked_members = {
        (item.role, _normalized_source_identity(item.source_handles))
        for item in topology.issues
        if item.severity in {"error", "critical"}
    }
    blocked_member_handles = {
        handle
        for item in contact.issues
        for handle in item.member_source_handles
        if item.severity in {"error", "critical"}
    }
    for role in ("strut", "brace"):
        for candidate in staged.get(role, ()):
            identity = _normalized_source_identity(candidate.handles)
            candidate.waler_terminal_blocked = (
                (role, identity) in blocked_members
                or bool(set(identity) & blocked_member_handles)
            )
    try:
        messages.extend(
            _apply_terminal_resolutions(
                staged,
                contact.resolutions,
                topology.unique_evidence,
                tolerances,
                brace_verdicts,
            )
        )
        messages.extend(
            _refine_corner_brace_axis_intersections(staged, tolerances)
        )
    except Exception as exc:
        for candidate in candidates_by_role.get("waler", ()):
            candidate.waler_contact_face_state = "provisional"
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


def _rail_pair_midline(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
) -> tuple[Point, Point] | None:
    """Return a deterministic midline while preserving rail correspondence."""

    first_axis = _unit(*first)
    if first_axis is None or _unit(*second) is None:
        return None
    second_start, second_end = second
    if _dot(_vector(*second), first_axis) < 0.0:
        second_start, second_end = second_end, second_start
    center_axis = _ordered_line(
        _midpoint(first[0], second_start),
        _midpoint(first[1], second_end),
    )
    return center_axis if _length(*center_axis) > 1e-9 else None


def _corner_brace_center_axis(
    candidate: _Candidate,
    tolerances: GeometryTolerances,
) -> tuple[Point, Point] | None:
    """Return the midline of the recognition-selected body rails."""

    if len(candidate.selected_rail_lines) == 2:
        center_axis = _rail_pair_midline(*candidate.selected_rail_lines)
        if (
            center_axis is None
            or _length(*center_axis) < tolerances.minimum_component_length_mm
        ):
            return None
        return center_axis

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
    center_axis = _rail_pair_midline(first, second)
    if center_axis is None:
        return None
    if _length(*center_axis) < tolerances.minimum_component_length_mm:
        return None
    return center_axis


def _refine_corner_brace_axis_intersections_legacy(
    candidates_by_role: MutableMapping[str, Sequence[_Candidate]],
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
    corner_candidates = tuple(candidates_by_role.get("corner_brace", ()))
    messages: list[ValidationMessage] = []

    formal_candidates = tuple(
        candidate
        for candidate in corner_candidates
        if candidate.corner_brace_candidate_kind
        and len(candidate.selected_rail_lines) == 2
    )

    def formal_relationships(
        candidate: _Candidate,
    ) -> tuple[
        tuple[_Candidate, _Candidate, Point, Point],
        ...,
    ]:
        brace_axis = _corner_brace_center_axis(candidate, tolerances)
        if brace_axis is None:
            return ()
        relationships: list[
            tuple[_Candidate, _Candidate, Point, Point]
        ] = []
        for preliminary_waler, preliminary_strut in (
            (candidate.start, candidate.end),
            (candidate.end, candidate.start),
        ):
            waler_options: list[tuple[_Candidate, Point]] = []
            for waler in walers:
                contact = _line_segment_intersection_point(
                    brace_axis,
                    (waler.start, waler.end),
                    tolerances.endpoint_tolerance_mm,
                )
                if contact is None:
                    continue
                if (
                    _distance(contact, preliminary_waler)
                    > tolerances.maximum_brace_axis_extension_mm
                ):
                    continue
                waler_options.append(
                    (
                        waler,
                        _project_onto_segment(
                            contact,
                            waler.start,
                            waler.end,
                        ),
                    )
                )
            strut_options: list[tuple[_Candidate, Point]] = []
            for strut in struts:
                contact = _line_segment_intersection_point(
                    brace_axis,
                    (strut.start, strut.end),
                    tolerances.endpoint_tolerance_mm,
                )
                if contact is None:
                    continue
                if (
                    _distance(contact, preliminary_strut)
                    > tolerances.maximum_brace_axis_extension_mm
                ):
                    continue
                strut_options.append(
                    (
                        strut,
                        _project_onto_segment(
                            contact,
                            strut.start,
                            strut.end,
                        ),
                    )
                )
            for waler, waler_contact in waler_options:
                for strut, strut_contact in strut_options:
                    relationship = (
                        waler,
                        strut,
                        waler_contact,
                        strut_contact,
                    )
                    if not any(
                        _normalized_source_identity(existing[0].handles)
                        == _normalized_source_identity(waler.handles)
                        and _normalized_source_identity(existing[1].handles)
                        == _normalized_source_identity(strut.handles)
                        and _same_point(
                            existing[2],
                            waler_contact,
                            tolerances.beam_crossing_duplicate_tolerance_mm,
                        )
                        and _same_point(
                            existing[3],
                            strut_contact,
                            tolerances.beam_crossing_duplicate_tolerance_mm,
                        )
                        for existing in relationships
                    ):
                        relationships.append(relationship)
        return tuple(relationships)

    def formal_unresolved_message(
        candidates: Sequence[_Candidate],
        reason: str,
        relationships: Sequence[
            tuple[_Candidate, _Candidate, Point, Point]
        ] = (),
    ) -> ValidationMessage:
        handles = tuple(
            sorted(
                {
                    handle
                    for candidate in candidates
                    for handle in candidate.handles
                }
            )
        )
        widths = ", ".join(
            f"{candidate.source_width:.3f}"
            for candidate in sorted(
                candidates,
                key=lambda item: (
                    item.source_width,
                    tuple(sorted(item.handles)),
                ),
            )
        )
        selected_rails = "; ".join(
            "|".join(
                (
                    f"({line[0][0]:.3f},{line[0][1]:.3f})"
                    f"->({line[1][0]:.3f},{line[1][1]:.3f})"
                )
                for line in candidate.selected_rail_lines
            )
            for candidate in candidates
        )
        body_evidence = ", ".join(
            dict.fromkeys(
                evidence
                for candidate in candidates
                for evidence in candidate.corner_brace_evidence
            )
        )
        competing_walers = tuple(
            sorted(
                {
                    "|".join(_normalized_source_identity(relationship[0].handles))
                    for relationship in relationships
                }
            )
        )
        competing_struts = tuple(
            sorted(
                {
                    "|".join(_normalized_source_identity(relationship[1].handles))
                    for relationship in relationships
                }
            )
        )
        if len(competing_walers) > 1:
            summary = (
                "已辨識完整斜切角撐幾何，但存在多個有效圍令關聯。"
                "請排除重複圍令來源後重新辨識。"
            )
        else:
            summary = "角撐本體已辨識，但無唯一合法有限 Waler／Strut 關聯。"
        return ValidationMessage(
            "error",
            "CORNER_BRACE_RAIL_CANDIDATE_UNRESOLVED",
            (
                f"{summary}；body_status=recognized；"
                f"evaluated_widths_mm=[{widths or 'none'}]；"
                f"selected_rails=[{selected_rails or 'none'}]；"
                f"body_evidence=[{body_evidence or 'none'}]；"
                "competing_waler_source_handles=["
                f"{', '.join(competing_walers) or 'none'}]；"
                "competing_strut_source_handles=["
                f"{', '.join(competing_struts) or 'none'}]；"
                f"reasons=[{reason}]。"
            ),
            "corner_brace",
            handles,
        )

    if formal_candidates:
        retained_formal: list[_Candidate] = []
        complete_candidates = tuple(
            candidate
            for candidate in formal_candidates
            if candidate.corner_brace_candidate_kind == "complete"
        )
        for candidate in complete_candidates:
            relationships = formal_relationships(candidate)
            if len(relationships) != 1:
                messages.append(
                    formal_unresolved_message(
                        (candidate,),
                        (
                            "finite_member_relationship_missing"
                            if not relationships
                            else "finite_member_relationship_ambiguous"
                        ),
                        relationships,
                    )
                )
                continue
            waler, strut, waler_contact, strut_contact = relationships[0]
            refined_line = _ordered_line(waler_contact, strut_contact)
            if _length(*refined_line) < tolerances.minimum_component_length_mm:
                messages.append(
                    formal_unresolved_message(
                        (candidate,),
                        "refined_axis_too_short",
                        relationships,
                    )
                )
                continue
            candidate.start, candidate.end = refined_line
            candidate.recognized_axis = refined_line
            candidate.reference_point = _midpoint(*refined_line)
            candidate.recognition_method = "brace_centerline_intersections"
            candidate.corner_brace_evidence = (
                *candidate.corner_brace_evidence,
                "waler_source_handles="
                + "|".join(sorted(waler.handles)),
                "strut_source_handles="
                + "|".join(sorted(strut.handles)),
            )
            retained_formal.append(candidate)

        occluded_by_group: dict[str, list[_Candidate]] = {}
        for candidate in formal_candidates:
            if candidate.corner_brace_candidate_kind == "occluded":
                occluded_by_group.setdefault(
                    candidate.corner_brace_group_key,
                    [],
                ).append(candidate)
        for candidates in occluded_by_group.values():
            resolved: list[
                tuple[_Candidate, _Candidate, _Candidate, Point, Point]
            ] = []
            ambiguous_relationship = False
            evaluated_relationships: list[
                tuple[_Candidate, _Candidate, Point, Point]
            ] = []
            for candidate in candidates:
                relationships = formal_relationships(candidate)
                evaluated_relationships.extend(relationships)
                if len(relationships) > 1:
                    ambiguous_relationship = True
                elif len(relationships) == 1:
                    waler, strut, waler_contact, strut_contact = (
                        relationships[0]
                    )
                    if (
                        _length(waler_contact, strut_contact)
                        >= tolerances.minimum_component_length_mm
                    ):
                        resolved.append(
                            (
                                candidate,
                                waler,
                                strut,
                                waler_contact,
                                strut_contact,
                            )
                        )
            if len(resolved) != 1 or ambiguous_relationship:
                messages.append(
                    formal_unresolved_message(
                        candidates,
                        (
                            "finite_member_relationship_missing"
                            if not resolved and not ambiguous_relationship
                            else "fallback_candidate_or_relationship_ambiguous"
                        ),
                        evaluated_relationships,
                    )
                )
                continue
            candidate, waler, strut, waler_contact, strut_contact = resolved[0]
            refined_line = _ordered_line(waler_contact, strut_contact)
            candidate.start, candidate.end = refined_line
            candidate.recognized_axis = refined_line
            candidate.reference_point = _midpoint(*refined_line)
            # The method remains stable so Review and persistence can
            # distinguish automatic occluded-rail recognition from repair.
            candidate.recognition_method = "occluded_parallel_rails"
            candidate.corner_brace_evidence = (
                *candidate.corner_brace_evidence,
                "waler_source_handles="
                + "|".join(sorted(waler.handles)),
                "strut_source_handles="
                + "|".join(sorted(strut.handles)),
            )
            retained_formal.append(candidate)

        legacy_candidates = [
            candidate
            for candidate in corner_candidates
            if candidate not in formal_candidates
        ]
        candidates_by_role["corner_brace"] = [
            *legacy_candidates,
            *retained_formal,
        ]

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
        if (
            candidate.corner_brace_candidate_kind
            and len(candidate.selected_rail_lines) == 2
        ):
            continue
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


def _refine_corner_brace_axis_intersections(
    candidates_by_role: MutableMapping[str, Sequence[_Candidate]],
    tolerances: GeometryTolerances,
) -> list[ValidationMessage]:
    """Assess immutable bodies against every exact finite member identity."""

    corner_candidates = tuple(candidates_by_role.get("corner_brace", ()))
    structured = tuple(
        candidate
        for candidate in corner_candidates
        if candidate.corner_brace_body_evidence is not None
    )
    legacy = tuple(
        candidate
        for candidate in corner_candidates
        if candidate.corner_brace_body_evidence is None
    )
    body_unresolved = tuple(
        candidate
        for candidate in structured
        if candidate.corner_brace_body_resolution != "unique"
    )
    assessable = tuple(
        candidate
        for candidate in structured
        if candidate.corner_brace_body_resolution == "unique"
    )
    messages: list[ValidationMessage] = []
    if legacy:
        legacy_roles: dict[str, Sequence[_Candidate]] = dict(candidates_by_role)
        legacy_roles["corner_brace"] = legacy
        messages.extend(
            _refine_corner_brace_axis_intersections_legacy(
                legacy_roles,
                tolerances,
            )
        )
        legacy = tuple(legacy_roles.get("corner_brace", ()))
    if not structured:
        candidates_by_role["corner_brace"] = list(legacy)
        return messages

    walers = tuple(candidates_by_role.get("waler", ()))
    struts = tuple(candidates_by_role.get("strut", ()))
    retained: list[_Candidate] = []
    evidence_candidates: list[_Candidate] = list(body_unresolved)
    for candidate in assessable:
        body = candidate.corner_brace_body_evidence
        assert body is not None
        observed_stations = tuple(
            station
            for track in body.rail_tracks
            for fragment in track.fragments
            for station in fragment.interval
        )
        plausible_start = min(observed_stations) - tolerances.maximum_corner_brace_axis_extension_mm
        plausible_end = max(observed_stations) + tolerances.maximum_corner_brace_axis_extension_mm
        body_points = tuple(
            point
            for track in body.rail_tracks
            for fragment in track.fragments
            for point in fragment.line
        )
        corridor = tolerances.collinear_tolerance_mm
        body_bounds = (
            min(point[0] for point in body_points) - corridor,
            min(point[1] for point in body_points) - corridor,
            max(point[0] for point in body_points) + corridor,
            max(point[1] for point in body_points) + corridor,
        )

        def near_body(line: tuple[Point, Point]) -> bool:
            line_bounds = (
                min(line[0][0], line[1][0]),
                min(line[0][1], line[1][1]),
                max(line[0][0], line[1][0]),
                max(line[0][1], line[1][1]),
            )
            return not (
                line_bounds[2] < body_bounds[0]
                or line_bounds[0] > body_bounds[2]
                or line_bounds[3] < body_bounds[1]
                or line_bounds[1] > body_bounds[3]
            )

        nearby_component_lines = tuple(
            dict.fromkeys(
                _ordered_line(*line)
                for role in ("waler", "strut", "brace", "column", "beam")
                for member in candidates_by_role.get(role, ())
                for line in (
                    *member.boundary_lines,
                    member.recognized_axis or (member.start, member.end),
                )
                if _length(*line) > 1e-9 and near_body(line)
            )
        )
        waler_contacts: list[tuple[_Candidate, Point]] = []
        for waler in walers:
            contact = _line_segment_intersection_point(
                body.midline,
                (waler.start, waler.end),
                tolerances.endpoint_tolerance_mm,
            )
            if contact is None:
                continue
            contact = _project_onto_segment(contact, waler.start, waler.end)
            station = _dot(contact, body.canonical_direction)
            if plausible_start <= station <= plausible_end:
                waler_contacts.append((waler, contact))
        strut_contacts: list[tuple[_Candidate, Point]] = []
        for strut in struts:
            contact = _line_segment_intersection_point(
                body.midline,
                (strut.start, strut.end),
                tolerances.endpoint_tolerance_mm,
            )
            if contact is None:
                continue
            contact = _project_onto_segment(contact, strut.start, strut.end)
            station = _dot(contact, body.canonical_direction)
            if plausible_start <= station <= plausible_end:
                strut_contacts.append((strut, contact))
        relationships: list[
            tuple[
                _Candidate,
                _Candidate,
                Point,
                Point,
                CornerBraceBodyRelationshipAssessment,
            ]
        ] = []
        for waler, waler_contact in waler_contacts:
            for strut, strut_contact in strut_contacts:
                if _same_point(
                    waler_contact,
                    strut_contact,
                    tolerances.beam_crossing_duplicate_tolerance_mm,
                ):
                    continue
                assessment = assess_corner_brace_relationship(
                    body,
                    waler_source_handles=_normalized_source_identity(
                        waler.handles
                    ),
                    strut_source_handles=_normalized_source_identity(
                        strut.handles
                    ),
                    waler_intersection=waler_contact,
                    strut_intersection=strut_contact,
                    occluding_lines=tuple(
                        dict.fromkeys(
                            (
                                *candidate.corner_brace_occluding_lines,
                                *nearby_component_lines,
                                _ordered_line(waler.start, waler.end),
                                _ordered_line(strut.start, strut.end),
                            )
                        )
                    ),
                    tolerances=tolerances,
                )
                relationships.append(
                    (
                        waler,
                        strut,
                        waler_contact,
                        strut_contact,
                        assessment,
                    )
                )
        unique_relationships: dict[
            tuple[tuple[str, ...], tuple[str, ...], Point, Point],
            tuple[
                _Candidate,
                _Candidate,
                Point,
                Point,
                CornerBraceBodyRelationshipAssessment,
            ],
        ] = {}
        for relationship in relationships:
            key = (
                _normalized_source_identity(relationship[0].handles),
                _normalized_source_identity(relationship[1].handles),
                relationship[2],
                relationship[3],
            )
            unique_relationships[key] = relationship
        relationships = list(unique_relationships.values())
        candidate.corner_brace_relationship_assessments = tuple(
            item[4]
            for item in sorted(
                relationships,
                key=lambda item: (
                    _normalized_source_identity(item[0].handles),
                    _normalized_source_identity(item[1].handles),
                    item[2],
                    item[3],
                ),
            )
        )
        evidence_candidates.append(candidate)
        hard_valid = [item for item in relationships if item[4].hard_valid]
        if len(hard_valid) != 1:
            reason = (
                "zero_hard_valid_relationships"
                if not hard_valid
                else "multiple_hard_valid_relationships"
            )
            messages.append(
                ValidationMessage(
                    "error",
                    "CORNER_BRACE_RELATIONSHIP_UNRESOLVED",
                    (
                        "角撐本體已辨識，但沒有唯一合法的有限 Waler／Strut 關係；"
                        f"body_signature={body.signature}；"
                        f"assessment_count={len(relationships)}；"
                        f"hard_valid_count={len(hard_valid)}；"
                        f"reason={reason}。"
                    ),
                    "corner_brace",
                    tuple(sorted(candidate.handles)),
                )
            )
            continue
        waler, strut, waler_contact, strut_contact, assessment = hard_valid[0]
        refined_line = _ordered_line(waler_contact, strut_contact)
        candidate.start, candidate.end = refined_line
        candidate.recognized_axis = refined_line
        candidate.reference_point = _midpoint(*refined_line)
        candidate.corner_brace_candidate_kind = assessment.classification
        candidate.recognition_method = (
            "corner_brace_complete_tracks"
            if assessment.classification == "complete"
            else "occluded_parallel_rails"
        )
        candidate.corner_brace_evidence = (
            *candidate.corner_brace_evidence,
            "waler_source_handles=" + "|".join(sorted(waler.handles)),
            "strut_source_handles=" + "|".join(sorted(strut.handles)),
            f"coverage_rail_1={assessment.per_rail_union_coverage[0]:.6f}",
            f"coverage_rail_2={assessment.per_rail_union_coverage[1]:.6f}",
        )
        retained.append(candidate)

    candidates_by_role["corner_brace"] = [*legacy, *retained]
    # Import conversion reads this private channel to preserve evidence for
    # both recognized and unresolved bodies without creating formal members.
    candidates_by_role["corner_brace_evidence"] = evidence_candidates
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
            selected_rail_number = next(
                (
                    index
                    for index, rail in enumerate(
                        candidate.selected_rail_lines,
                        1,
                    )
                    if _same_line(ordered, _ordered_line(*rail))
                ),
                None,
            )
            lines.append(
                (
                    ordered,
                    (
                        "外側線"
                        if role == "waler"
                        else (
                            f"角撐本體 rail {selected_rail_number}"
                            if role == "corner_brace"
                            and selected_rail_number is not None
                            else ""
                        )
                    ),
                    (
                        "recognized_corner_brace_rail"
                        if role == "corner_brace"
                        and selected_rail_number is not None
                        else "recognized_boundary"
                    ),
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
