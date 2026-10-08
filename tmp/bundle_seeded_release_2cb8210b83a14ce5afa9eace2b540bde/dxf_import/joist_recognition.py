"""Pure whole-source recognition for BIM bearer-beam (Joist) INSERTs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Sequence

from .beam_contacts import (
    BEAM_MEMBER_PERPENDICULAR_TOLERANCE_DEG,
    finite_perpendicular_contact,
)
from .geometry import (
    Point,
    _angle_difference_deg,
    _distance,
    _dot,
    _length,
    _line_segment_intersection_point,
    _ordered_line,
    _segment_intersection_point,
    _unit,
    _vector,
)
from .models import GeometryTolerances


JOIST_PAIR_NOMINAL_STATION_SPACING_MM = 518.0
JOIST_PAIR_STATION_SPACING_TOLERANCE_MM = 5.0
JOIST_PAIR_COLUMN_MIDPOINT_TOLERANCE_MM = 2.0
JOIST_STRUT_FACE_CONTACT_TOLERANCE_MM = 25.0
JOIST_COLUMN_TERMINAL_WINDOW_MM = 700.0
JOIST_TERMINAL_RAIL_BAND_QUORUM = 2

# These topology values describe the confirmed Y05 double-C source shape.
# They are recognition evidence, not material or Solver design rules.
JOIST_ENVELOPE_WIDTH_MIN_MM = 60.0
JOIST_ENVELOPE_WIDTH_MAX_MM = 120.0
JOIST_LONGITUDINAL_OFFSET_CLUSTER_TOLERANCE_MM = 2.0
JOIST_MINIMUM_LONGITUDINAL_LENGTH_RATIO = 0.20
JOIST_PERPENDICULAR_TOLERANCE_DEG = (
    BEAM_MEMBER_PERPENDICULAR_TOLERANCE_DEG
)


class JoistRecognitionStatus(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    RECOGNIZED_SINGLE = "recognized_single"
    RECOGNIZED_PAIR = "recognized_pair"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class JoistPrimitive:
    points: tuple[Point, ...]
    closed: bool
    entity_type: str
    source_handle: str
    source_width: float = 0.0

    def segments(self) -> tuple[tuple[Point, Point], ...]:
        pairs = list(zip(self.points, self.points[1:]))
        if self.closed and len(self.points) > 2:
            pairs.append((self.points[-1], self.points[0]))
        return tuple(pair for pair in pairs if _length(*pair) > 1e-9)


@dataclass(frozen=True)
class JoistRecognitionInput:
    root_handle: str
    root_entity_type: str
    role: str
    primitives: tuple[JoistPrimitive, ...]


@dataclass(frozen=True)
class JoistMemberReference:
    id: str
    start: Point
    end: Point
    source_handles: tuple[str, ...] = ()
    source_width: float = 0.0


@dataclass(frozen=True)
class JoistColumnStationReference:
    id: str
    strut_id: str
    station: float


@dataclass(frozen=True)
class JoistContextSnapshot:
    struts: tuple[JoistMemberReference, ...] = ()
    braces: tuple[JoistMemberReference, ...] = ()
    column_stations: tuple[JoistColumnStationReference, ...] = ()


@dataclass(frozen=True)
class JoistAxis:
    start: Point
    end: Point
    source_width: float
    slot: int

    @property
    def segment(self) -> tuple[Point, Point]:
        return self.start, self.end


@dataclass(frozen=True)
class JoistContact:
    axis_slot: int
    member_role: str
    member_id: str
    point: Point
    member_station: float
    source_contact_point: Point
    recognition_method: str = "finite_segment_intersection"


@dataclass(frozen=True)
class JoistPairRelation:
    strut_id: str
    column_id: str
    first_station: float
    second_station: float
    spacing: float
    midpoint_error: float


@dataclass(frozen=True)
class JoistRecognitionOutcome:
    status: JoistRecognitionStatus
    axes: tuple[JoistAxis, ...] = ()
    contacts: tuple[JoistContact, ...] = ()
    pair_relations: tuple[JoistPairRelation, ...] = ()
    diagnostic_code: str = ""


@dataclass(frozen=True)
class _LongitudinalEvidence:
    offset: float
    minimum_station: float
    maximum_station: float


@dataclass(frozen=True)
class _TerminalRecoverySeed:
    strut_id: str
    column_id: str
    column_point: Point
    endpoint_index: int


@dataclass(frozen=True)
class _TerminalBandEndpoint:
    band_index: int
    station: float


def pair_spacing_is_eligible(actual_spacing: float) -> bool:
    return (
        abs(actual_spacing - JOIST_PAIR_NOMINAL_STATION_SPACING_MM)
        <= JOIST_PAIR_STATION_SPACING_TOLERANCE_MM
    )


def column_midpoint_is_eligible(
    first_station: float,
    second_station: float,
    column_station: float,
) -> bool:
    midpoint = (first_station + second_station) / 2.0
    return (
        abs(midpoint - column_station)
        <= JOIST_PAIR_COLUMN_MIDPOINT_TOLERANCE_MM
    )


def _canonical_direction(segment: tuple[Point, Point]) -> Point | None:
    direction = _unit(*segment)
    if direction is None:
        return None
    if direction[0] < -1e-12 or (
        abs(direction[0]) <= 1e-12 and direction[1] < 0.0
    ):
        return -direction[0], -direction[1]
    return direction


def _cluster_longitudinal_evidence(
    source: JoistRecognitionInput,
    tolerances: GeometryTolerances,
) -> tuple[Point, tuple[_LongitudinalEvidence, ...], bool] | None:
    segments = tuple(
        segment
        for primitive in source.primitives
        for segment in primitive.segments()
    )
    if not segments:
        return None
    longest = max(segments, key=lambda segment: _length(*segment))
    maximum_length = _length(*longest)
    if maximum_length < tolerances.minimum_component_length_mm:
        return None
    minimum_length = max(
        tolerances.minimum_component_length_mm,
        maximum_length * JOIST_MINIMUM_LONGITUDINAL_LENGTH_RATIO,
    )
    strong_segments = tuple(
        segment for segment in segments if _length(*segment) >= minimum_length
    )
    orientation_clusters: list[list[tuple[Point, Point]]] = []
    for segment in sorted(
        strong_segments,
        key=lambda item: (
            -_length(*item),
            _ordered_line(*item),
        ),
    ):
        matching = next(
            (
                cluster
                for cluster in orientation_clusters
                if _angle_difference_deg(segment, cluster[0])
                <= tolerances.parallel_angle_tolerance_deg
            ),
            None,
        )
        if matching is None:
            orientation_clusters.append([segment])
        else:
            matching.append(segment)
    orientation_clusters.sort(
        key=lambda cluster: sum(_length(*segment) for segment in cluster),
        reverse=True,
    )
    if not orientation_clusters:
        return None
    strongest_support = sum(
        _length(*segment) for segment in orientation_clusters[0]
    )
    ambiguous = any(
        sum(_length(*segment) for segment in cluster)
        >= strongest_support * tolerances.bim_minimum_longitudinal_evidence_ratio
        for cluster in orientation_clusters[1:]
    )
    direction = _canonical_direction(orientation_clusters[0][0])
    if direction is None:
        return None
    normal = -direction[1], direction[0]
    evidence: list[tuple[float, float, float]] = []
    reference = ((0.0, 0.0), direction)
    for segment in segments:
        if _length(*segment) < minimum_length:
            continue
        if (
            _angle_difference_deg(segment, reference)
            > tolerances.parallel_angle_tolerance_deg
        ):
            continue
        offset = _dot(segment[0], normal) + _dot(
            _vector(segment[0], segment[1]), normal
        ) / 2.0
        stations = (_dot(segment[0], direction), _dot(segment[1], direction))
        evidence.append((offset, min(stations), max(stations)))
    if not evidence:
        return None

    clusters: list[list[tuple[float, float, float]]] = []
    for item in sorted(evidence):
        if (
            not clusters
            or abs(item[0] - sum(row[0] for row in clusters[-1]) / len(clusters[-1]))
            > JOIST_LONGITUDINAL_OFFSET_CLUSTER_TOLERANCE_MM
        ):
            clusters.append([item])
        else:
            clusters[-1].append(item)
    results = tuple(
        _LongitudinalEvidence(
            sum(item[0] for item in cluster) / len(cluster),
            min(item[1] for item in cluster),
            max(item[2] for item in cluster),
        )
        for cluster in clusters
    )
    return direction, results, ambiguous


def _axis_from_evidence(
    direction: Point,
    evidence: Sequence[_LongitudinalEvidence],
    *,
    slot: int,
    minimum_station: float | None = None,
    maximum_station: float | None = None,
) -> JoistAxis:
    normal = -direction[1], direction[0]
    offset = (evidence[0].offset + evidence[-1].offset) / 2.0
    if minimum_station is None:
        minimum_station = min(item.minimum_station for item in evidence)
    if maximum_station is None:
        maximum_station = max(item.maximum_station for item in evidence)
    start = (
        direction[0] * minimum_station + normal[0] * offset,
        direction[1] * minimum_station + normal[1] * offset,
    )
    end = (
        direction[0] * maximum_station + normal[0] * offset,
        direction[1] * maximum_station + normal[1] * offset,
    )
    start, end = _ordered_line(start, end)
    return JoistAxis(
        start,
        end,
        abs(evidence[-1].offset - evidence[0].offset),
        slot,
    )


def _source_axes(
    source: JoistRecognitionInput,
    tolerances: GeometryTolerances,
) -> tuple[tuple[JoistAxis, ...] | None, str]:
    clustered = _cluster_longitudinal_evidence(source, tolerances)
    if clustered is None:
        return None, "BIM_JOIST_WHOLE_SOURCE_AXIS_FAILED"
    direction, evidence, ambiguous = clustered
    if ambiguous:
        return None, "BIM_JOIST_CONFLICTING_WHOLE_AXES"
    # Confirmed C-family roots expose six stable longitudinal offset rails.
    # L-angle details expose one or two and therefore cannot become Joists.
    if len(evidence) != 6:
        return None, "BIM_JOIST_WHOLE_SOURCE_AXIS_FAILED"
    first_envelope = evidence[:3]
    second_envelope = evidence[3:]
    first_width = first_envelope[-1].offset - first_envelope[0].offset
    second_width = second_envelope[-1].offset - second_envelope[0].offset
    whole_minimum_station = min(item.minimum_station for item in evidence)
    whole_maximum_station = max(item.maximum_station for item in evidence)
    first_axis = _axis_from_evidence(
        direction,
        first_envelope,
        slot=0,
        minimum_station=whole_minimum_station,
        maximum_station=whole_maximum_station,
    )
    second_axis = _axis_from_evidence(
        direction,
        second_envelope,
        slot=1,
        minimum_station=whole_minimum_station,
        maximum_station=whole_maximum_station,
    )
    axis_separation = abs(
        (second_envelope[0].offset + second_envelope[-1].offset) / 2.0
        - (first_envelope[0].offset + first_envelope[-1].offset) / 2.0
    )
    double_c_topology = all(
        JOIST_ENVELOPE_WIDTH_MIN_MM <= width <= JOIST_ENVELOPE_WIDTH_MAX_MM
        for width in (first_width, second_width)
    )
    if double_c_topology and pair_spacing_is_eligible(axis_separation):
        return (first_axis, second_axis), ""

    whole_axis = _axis_from_evidence(direction, evidence, slot=0)
    if not (
        tolerances.minimum_component_length_mm
        <= _length(*whole_axis.segment)
        and whole_axis.source_width <= tolerances.maximum_component_width_mm
    ):
        return None, "BIM_JOIST_WHOLE_SOURCE_AXIS_FAILED"
    return (whole_axis,), ""


def _column_point_for_relation(
    context: JoistContextSnapshot,
    relation: JoistPairRelation,
) -> Point | None:
    struts = tuple(item for item in context.struts if item.id == relation.strut_id)
    columns = tuple(
        item
        for item in context.column_stations
        if item.id == relation.column_id and item.strut_id == relation.strut_id
    )
    if len(struts) != 1 or len(columns) != 1:
        return None
    direction = _unit(struts[0].start, struts[0].end)
    if direction is None:
        return None
    return (
        struts[0].start[0] + direction[0] * columns[0].station,
        struts[0].start[1] + direction[1] * columns[0].station,
    )


def _axis_endpoint_index(axis: JoistAxis, point: Point) -> int | None:
    distances = (_distance(axis.start, point), _distance(axis.end, point))
    closest = min(range(2), key=distances.__getitem__)
    if distances[closest] > 1e-6:
        return None
    return closest


def _terminal_recovery_seeds(
    axes: Sequence[JoistAxis],
    contacts: Sequence[JoistContact],
    relations: Sequence[JoistPairRelation],
    context: JoistContextSnapshot,
) -> tuple[_TerminalRecoverySeed, ...]:
    axes_by_slot = {axis.slot: axis for axis in axes}
    seeds: list[_TerminalRecoverySeed] = []
    for relation in relations:
        endpoint_contacts = tuple(
            contact
            for contact in contacts
            if contact.member_role == "strut"
            and contact.member_id == relation.strut_id
            and contact.recognition_method == "endpoint_face_contact"
        )
        if {item.axis_slot for item in endpoint_contacts} != {0, 1}:
            continue
        endpoint_indices = tuple(
            _axis_endpoint_index(
                axes_by_slot[contact.axis_slot],
                contact.source_contact_point,
            )
            for contact in endpoint_contacts
        )
        if None in endpoint_indices or len(set(endpoint_indices)) != 1:
            continue
        column_point = _column_point_for_relation(context, relation)
        if column_point is None:
            continue
        seeds.append(
            _TerminalRecoverySeed(
                relation.strut_id,
                relation.column_id,
                column_point,
                int(endpoint_indices[0]),
            )
        )
    return tuple(
        sorted(
            seeds,
            key=lambda item: (
                item.strut_id,
                item.column_id,
                item.endpoint_index,
            ),
        )
    )


def _terminal_interpretations(
    endpoints: Sequence[_TerminalBandEndpoint],
    *,
    outward_sign: float,
    tolerance: float,
) -> tuple[float, ...]:
    ordered = tuple(sorted(endpoints, key=lambda item: (item.station, item.band_index)))
    candidate_groups: list[tuple[_TerminalBandEndpoint, ...]] = []
    for start_index, first in enumerate(ordered):
        group = tuple(
            item
            for item in ordered[start_index:]
            if item.station - first.station <= tolerance + 1e-9
        )
        if len({item.band_index for item in group}) < JOIST_TERMINAL_RAIL_BAND_QUORUM:
            continue
        candidate_groups.append(group)

    maximal_groups: list[tuple[_TerminalBandEndpoint, ...]] = []
    for group in candidate_groups:
        key = frozenset((item.band_index, round(item.station, 9)) for item in group)
        if any(
            key
            < frozenset(
                (item.band_index, round(item.station, 9))
                for item in other
            )
            for other in candidate_groups
        ):
            continue
        if group not in maximal_groups:
            maximal_groups.append(group)

    stations = {
        (
            min(item.station for item in group)
            if outward_sign < 0.0
            else max(item.station for item in group)
        )
        for group in maximal_groups
    }
    return tuple(sorted(stations))


def _axis_with_terminal_station(
    axis: JoistAxis,
    direction: Point,
    endpoint_index: int,
    terminal_station: float,
) -> JoistAxis:
    normal = -direction[1], direction[0]
    offset = _dot(axis.start, normal)
    terminal = (
        direction[0] * terminal_station + normal[0] * offset,
        direction[1] * terminal_station + normal[1] * offset,
    )
    start, end = (
        _ordered_line(terminal, axis.end)
        if endpoint_index == 0
        else _ordered_line(axis.start, terminal)
    )
    return JoistAxis(start, end, axis.source_width, axis.slot)


def _recover_column_terminal_axes(
    source: JoistRecognitionInput,
    base_axes: Sequence[JoistAxis],
    preliminary_contacts: Sequence[JoistContact],
    preliminary_relations: Sequence[JoistPairRelation],
    context: JoistContextSnapshot,
    tolerances: GeometryTolerances,
) -> tuple[tuple[JoistAxis, ...], str, bool]:
    clustered = _cluster_longitudinal_evidence(source, tolerances)
    if clustered is None:
        return tuple(base_axes), "", False
    direction, rail_evidence, _ambiguous = clustered
    if len(base_axes) != 2 or len(rail_evidence) != 6:
        return tuple(base_axes), "", False
    seeds = _terminal_recovery_seeds(
        base_axes,
        preliminary_contacts,
        preliminary_relations,
        context,
    )
    if not seeds:
        return tuple(base_axes), "", False

    axes_by_slot = {axis.slot: axis for axis in base_axes}
    reference = ((0.0, 0.0), direction)
    normal = -direction[1], direction[0]
    recovered = False
    for seed in seeds:
        outward_sign = -1.0 if seed.endpoint_index == 0 else 1.0
        column_station = _dot(seed.column_point, direction)
        endpoints: list[_TerminalBandEndpoint] = []
        for primitive in source.primitives:
            for segment in primitive.segments():
                if (
                    _angle_difference_deg(segment, reference)
                    > tolerances.parallel_angle_tolerance_deg
                ):
                    continue
                offset = (
                    _dot(segment[0], normal) + _dot(segment[1], normal)
                ) / 2.0
                matching_bands = tuple(
                    index
                    for index, evidence in enumerate(rail_evidence)
                    if abs(offset - evidence.offset)
                    <= JOIST_LONGITUDINAL_OFFSET_CLUSTER_TOLERANCE_MM
                )
                if len(matching_bands) != 1:
                    continue
                band_index = matching_bands[0]
                sibling_slot = 0 if band_index < 3 else 1
                base_axis = axes_by_slot[sibling_slot]
                base_endpoint = (
                    base_axis.start
                    if seed.endpoint_index == 0
                    else base_axis.end
                )
                base_signed_projection = outward_sign * (
                    _dot(base_endpoint, direction) - column_station
                )
                endpoint_stations = tuple(_dot(point, direction) for point in segment)
                signed_projections = tuple(
                    outward_sign * (station - column_station)
                    for station in endpoint_stations
                )
                far_index = max(range(2), key=signed_projections.__getitem__)
                far_signed_projection = signed_projections[far_index]
                if not (
                    -1e-9
                    <= far_signed_projection
                    <= JOIST_COLUMN_TERMINAL_WINDOW_MM + 1e-9
                ):
                    continue
                if far_signed_projection <= base_signed_projection + 1e-9:
                    continue
                endpoints.append(
                    _TerminalBandEndpoint(
                        band_index,
                        endpoint_stations[far_index],
                    )
                )

        interpretations = tuple(
            _terminal_interpretations(
                tuple(item for item in endpoints if item.band_index in band_range),
                outward_sign=outward_sign,
                tolerance=tolerances.endpoint_tolerance_mm,
            )
            for band_range in (range(0, 3), range(3, 6))
        )
        if any(len(items) > 1 for items in interpretations):
            return (
                tuple(axes_by_slot[index] for index in sorted(axes_by_slot)),
                "BIM_JOIST_TERMINAL_RESIDUAL_AMBIGUOUS",
                recovered,
            )
        if any(not items for items in interpretations):
            continue
        first_station = interpretations[0][0]
        second_station = interpretations[1][0]
        if abs(second_station - first_station) > tolerances.endpoint_tolerance_mm + 1e-9:
            return (
                tuple(axes_by_slot[index] for index in sorted(axes_by_slot)),
                "BIM_JOIST_TERMINAL_RESIDUAL_AMBIGUOUS",
                recovered,
            )
        axes_by_slot[0] = _axis_with_terminal_station(
            axes_by_slot[0],
            direction,
            seed.endpoint_index,
            first_station,
        )
        axes_by_slot[1] = _axis_with_terminal_station(
            axes_by_slot[1],
            direction,
            seed.endpoint_index,
            second_station,
        )
        recovered = True

    return (
        tuple(axes_by_slot[index] for index in sorted(axes_by_slot)),
        "",
        recovered,
    )


def _finite_perpendicular_contact(
    axis: JoistAxis,
    member: JoistMemberReference,
) -> tuple[Point, float] | None:
    return finite_perpendicular_contact(
        axis.segment,
        (member.start, member.end),
        angle_tolerance_deg=JOIST_PERPENDICULAR_TOLERANCE_DEG,
    )


def _endpoint_face_contact(
    axis: JoistAxis,
    member: JoistMemberReference,
    endpoint_index: int,
) -> tuple[Point, Point, float] | None:
    """Relate a source endpoint on a Strut face to its centreline.

    The returned engineering point lies on the finite Strut centreline.  The
    Joist axis itself is deliberately not extended: its terminal endpoint is
    retained as source-contact provenance.
    """

    if not math.isfinite(member.source_width) or member.source_width <= 0.0:
        return None
    member_segment = (member.start, member.end)
    if (
        abs(90.0 - _angle_difference_deg(axis.segment, member_segment))
        > JOIST_PERPENDICULAR_TOLERANCE_DEG
    ):
        return None
    point = _line_segment_intersection_point(axis.segment, member_segment, 1e-6)
    if point is None:
        return None
    direction = _unit(*axis.segment)
    member_direction = _unit(*member_segment)
    if direction is None or member_direction is None:
        return None
    axis_length = _length(*axis.segment)
    intersection_station = _dot(_vector(axis.start, point), direction)
    if endpoint_index == 0:
        if intersection_station > 1e-6:
            return None
        projection_distance = -intersection_station
        source_point = axis.start
    else:
        if intersection_station < axis_length - 1e-6:
            return None
        projection_distance = intersection_station - axis_length
        source_point = axis.end
    if (
        abs(projection_distance - member.source_width / 2.0)
        > JOIST_STRUT_FACE_CONTACT_TOLERANCE_MM
    ):
        return None
    member_station = _dot(_vector(member.start, point), member_direction)
    member_length = _length(*member_segment)
    if not (-1e-6 <= member_station <= member_length + 1e-6):
        return None
    return (
        source_point,
        point,
        max(0.0, min(member_length, member_station)),
    )


def _contacts(
    axes: Sequence[JoistAxis],
    members: Sequence[JoistMemberReference],
    role: str,
) -> tuple[tuple[JoistContact, ...], str]:
    results: list[JoistContact] = []
    for axis in axes:
        direct_member_ids: set[str] = set()
        for member in members:
            contact = _finite_perpendicular_contact(axis, member)
            if contact is None:
                continue
            point, station = contact
            direct_member_ids.add(member.id)
            results.append(
                JoistContact(
                    axis.slot,
                    role,
                    member.id,
                    point,
                    station,
                    point,
                )
            )
        if role != "strut":
            continue
        for endpoint_index in (0, 1):
            eligible = tuple(
                (member, contact)
                for member in members
                if member.id not in direct_member_ids
                and (
                    contact := _endpoint_face_contact(
                        axis,
                        member,
                        endpoint_index,
                    )
                )
                is not None
            )
            if len(eligible) > 1:
                return (), "BIM_JOIST_STRUT_FACE_CONTACT_AMBIGUOUS"
            if not eligible:
                continue
            member, (source_point, point, station) = eligible[0]
            results.append(
                JoistContact(
                    axis.slot,
                    role,
                    member.id,
                    point,
                    station,
                    source_point,
                    "endpoint_face_contact",
                )
            )
    return tuple(
        sorted(
            results,
            key=lambda item: (
                item.member_role,
                item.member_id,
                item.axis_slot,
                item.member_station,
            ),
        )
    ), ""


def _pair_relations(
    contacts: Sequence[JoistContact],
    context: JoistContextSnapshot,
) -> tuple[tuple[JoistPairRelation, ...], str]:
    by_strut: dict[str, dict[int, JoistContact]] = {}
    for contact in contacts:
        if contact.member_role != "strut":
            continue
        by_strut.setdefault(contact.member_id, {})[contact.axis_slot] = contact
    complete = {
        strut_id: axis_contacts
        for strut_id, axis_contacts in by_strut.items()
        if set(axis_contacts) == {0, 1}
    }
    if not complete:
        return (), "BIM_JOIST_PAIR_UNPAIRED"
    relations: list[JoistPairRelation] = []
    for strut_id, axis_contacts in sorted(complete.items()):
        first = axis_contacts[0]
        second = axis_contacts[1]
        spacing = abs(second.member_station - first.member_station)
        if not pair_spacing_is_eligible(spacing):
            return (), "BIM_JOIST_PAIR_SPACING_INVALID"
        lower, upper = sorted((first.member_station, second.member_station))
        eligible_columns = tuple(
            column
            for column in context.column_stations
            if column.strut_id == strut_id
            and lower < column.station < upper
            and column_midpoint_is_eligible(lower, upper, column.station)
        )
        if not eligible_columns:
            return (), "BIM_JOIST_PAIR_UNPAIRED"
        if len(eligible_columns) > 1:
            return (), "BIM_JOIST_PAIR_AMBIGUOUS"
        column = eligible_columns[0]
        relations.append(
            JoistPairRelation(
                strut_id,
                column.id,
                lower,
                upper,
                spacing,
                (lower + upper) / 2.0 - column.station,
            )
        )
    return tuple(relations), ""


def _evaluate_pair_axes(
    axes: Sequence[JoistAxis],
    context: JoistContextSnapshot,
) -> tuple[
    tuple[JoistContact, ...],
    tuple[JoistPairRelation, ...],
    str,
]:
    strut_contacts, contact_diagnostic = _contacts(
        axes,
        context.struts,
        "strut",
    )
    if contact_diagnostic:
        return (), (), contact_diagnostic
    brace_contacts, _ = _contacts(axes, context.braces, "brace")
    contacts = (*strut_contacts, *brace_contacts)
    relations, relation_diagnostic = _pair_relations(contacts, context)
    return tuple(contacts), relations, relation_diagnostic


def _pair_failure_status(diagnostic_code: str) -> JoistRecognitionStatus:
    if diagnostic_code in {
        "BIM_JOIST_PAIR_AMBIGUOUS",
        "BIM_JOIST_STRUT_FACE_CONTACT_AMBIGUOUS",
        "BIM_JOIST_TERMINAL_RESIDUAL_AMBIGUOUS",
        "BIM_JOIST_TERMINAL_CONTEXT_DRIFT",
    }:
        return JoistRecognitionStatus.AMBIGUOUS
    return JoistRecognitionStatus.FAILED


def _pair_identity(
    relations: Sequence[JoistPairRelation],
) -> frozenset[tuple[str, str]]:
    return frozenset((item.strut_id, item.column_id) for item in relations)


def recognize_bim_joist(
    source: JoistRecognitionInput,
    context: JoistContextSnapshot,
    tolerances: GeometryTolerances | None = None,
) -> JoistRecognitionOutcome:
    """Recognize one Beam-role root INSERT without mutable importer state."""

    tolerances = tolerances or GeometryTolerances()
    if source.root_entity_type.upper() != "INSERT" or source.role != "beam":
        return JoistRecognitionOutcome(JoistRecognitionStatus.NOT_APPLICABLE)
    axes, axis_diagnostic = _source_axes(source, tolerances)
    if axes is None:
        return JoistRecognitionOutcome(
            (
                JoistRecognitionStatus.AMBIGUOUS
                if axis_diagnostic == "BIM_JOIST_CONFLICTING_WHOLE_AXES"
                else JoistRecognitionStatus.FAILED
            ),
            diagnostic_code=axis_diagnostic,
        )
    if len(axes) == 2:
        base_contacts, base_relations, diagnostic_code = _evaluate_pair_axes(
            axes,
            context,
        )
        if diagnostic_code:
            return JoistRecognitionOutcome(
                _pair_failure_status(diagnostic_code),
                axes,
                base_contacts,
                diagnostic_code=diagnostic_code,
            )
        finalized_axes, recovery_diagnostic, recovered = (
            _recover_column_terminal_axes(
                source,
                axes,
                base_contacts,
                base_relations,
                context,
                tolerances,
            )
        )
        if recovery_diagnostic:
            return JoistRecognitionOutcome(
                JoistRecognitionStatus.AMBIGUOUS,
                diagnostic_code=recovery_diagnostic,
            )
        if recovered:
            final_contacts, final_relations, final_diagnostic = (
                _evaluate_pair_axes(finalized_axes, context)
            )
            if final_diagnostic:
                if final_diagnostic == "BIM_JOIST_PAIR_UNPAIRED":
                    fallback_contacts, fallback_relations, fallback_diagnostic = (
                        _evaluate_pair_axes(axes, context)
                    )
                    if not fallback_diagnostic:
                        return JoistRecognitionOutcome(
                            JoistRecognitionStatus.RECOGNIZED_PAIR,
                            axes,
                            fallback_contacts,
                            fallback_relations,
                        )
                return JoistRecognitionOutcome(
                    JoistRecognitionStatus.AMBIGUOUS,
                    diagnostic_code="BIM_JOIST_TERMINAL_CONTEXT_DRIFT",
                )
            base_identity = _pair_identity(base_relations)
            final_identity = _pair_identity(final_relations)
            if final_identity != base_identity:
                if final_identity < base_identity:
                    fallback_contacts, fallback_relations, fallback_diagnostic = (
                        _evaluate_pair_axes(axes, context)
                    )
                    if not fallback_diagnostic:
                        return JoistRecognitionOutcome(
                            JoistRecognitionStatus.RECOGNIZED_PAIR,
                            axes,
                            fallback_contacts,
                            fallback_relations,
                        )
                return JoistRecognitionOutcome(
                    JoistRecognitionStatus.AMBIGUOUS,
                    diagnostic_code="BIM_JOIST_TERMINAL_CONTEXT_DRIFT",
                )
            axes = finalized_axes
            base_contacts = final_contacts
            base_relations = final_relations
        return JoistRecognitionOutcome(
            JoistRecognitionStatus.RECOGNIZED_PAIR,
            axes,
            base_contacts,
            base_relations,
        )
    strut_contacts, contact_diagnostic = _contacts(
        axes,
        context.struts,
        "strut",
    )
    if contact_diagnostic:
        return JoistRecognitionOutcome(
            JoistRecognitionStatus.AMBIGUOUS,
            axes,
            diagnostic_code=contact_diagnostic,
        )
    brace_contacts, _ = _contacts(axes, context.braces, "brace")
    contacts = (*strut_contacts, *brace_contacts)
    if brace_contacts and not strut_contacts:
        return JoistRecognitionOutcome(
            JoistRecognitionStatus.RECOGNIZED_SINGLE,
            axes,
            tuple(contacts),
        )
    return JoistRecognitionOutcome(
        JoistRecognitionStatus.FAILED,
        axes,
        tuple(contacts),
        diagnostic_code=(
            "BIM_JOIST_SINGLE_STRUT_OBLIGATION"
            if strut_contacts
            else "BIM_JOIST_SINGLE_NO_BRACE_CONTACT"
        ),
    )


__all__ = [
    "JOIST_COLUMN_TERMINAL_WINDOW_MM",
    "JOIST_PAIR_COLUMN_MIDPOINT_TOLERANCE_MM",
    "JOIST_PAIR_NOMINAL_STATION_SPACING_MM",
    "JOIST_PAIR_STATION_SPACING_TOLERANCE_MM",
    "JOIST_STRUT_FACE_CONTACT_TOLERANCE_MM",
    "JoistAxis",
    "JoistColumnStationReference",
    "JoistContact",
    "JoistContextSnapshot",
    "JoistMemberReference",
    "JoistPairRelation",
    "JoistPrimitive",
    "JoistRecognitionInput",
    "JoistRecognitionOutcome",
    "JoistRecognitionStatus",
    "column_midpoint_is_eligible",
    "pair_spacing_is_eligible",
    "recognize_bim_joist",
]
