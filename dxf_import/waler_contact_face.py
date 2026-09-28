"""Pure Waler envelope facts and terminal contact-face resolution.

This module owns runtime-only DXF recognition facts.  It deliberately has no
Presentation, Project, persistence, or Solver dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from collections import defaultdict, deque
import math
from typing import Iterable, Sequence

from .geometry import (
    Point,
    _angle_difference_deg,
    _distance,
    _dot,
    _length,
    _line_segment_intersection_point,
    _line_separation,
    _midpoint,
    _ordered_line,
    _projection_overlap_ratio,
    _projection_range,
    _project_onto_segment,
    _segment_distance,
    _unit,
    _vector,
)
from .models import GeometryTolerances


Segment = tuple[Point, Point]

# This is numerical normalization for repeated transformed DXF vertices, not
# a recognition tolerance.  In particular, the 19 mm W7 detail-to-outer-face
# distance must never be collapsed as floating-point duplication.
NUMERICAL_GEOMETRY_PRECISION_MM = 1e-6


class WalerEnvelopeStatus(str, Enum):
    RECOGNIZED = "recognized"
    SINGLE_LINE = "single_line"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class WalerEnvelopeFacts:
    """Source-supported provisional axis and physical outer faces."""

    component_key: str
    source_handles: tuple[str, ...]
    provisional_axis: Segment
    outer_faces: tuple[Segment, ...]
    source_width: float
    evidence_segments: tuple[Segment, ...]
    provenance_kind: str = "connected_contour"

    @property
    def has_physical_envelope(self) -> bool:
        return len(self.outer_faces) == 2 and self.source_width > 0.0


@dataclass(frozen=True)
class WalerEnvelopeOutcome:
    status: WalerEnvelopeStatus
    facts: tuple[WalerEnvelopeFacts, ...] = ()
    code: str = ""
    message: str = ""


@dataclass(frozen=True)
class MemberGeometryFacts:
    """Source-recognized member geometry used only for terminal relations."""

    role: str
    source_handles: tuple[str, ...]
    axis: Segment
    selected_waler_source_handles: tuple[tuple[str, ...], ...] = ()
    allow_axis_extension: bool = True


@dataclass(frozen=True)
class MemberTerminalEvidence:
    """One established member-terminal relation to a provisional Waler."""

    member_role: str
    member_source_handles: tuple[str, ...]
    terminal_name: str
    waler_source_handles: tuple[str, ...]
    provisional_intersection: Point
    body_point: Point
    relation_kind: str

    @property
    def body_vector(self) -> Point:
        return _vector(self.provisional_intersection, self.body_point)


@dataclass(frozen=True)
class TerminalTopologyIssue:
    severity: str
    code: str
    message: str
    role: str
    source_handles: tuple[str, ...]
    competing_waler_source_handles: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class TerminalTopologyOutcome:
    evidence: tuple[MemberTerminalEvidence, ...] = ()
    issues: tuple[TerminalTopologyIssue, ...] = ()


@dataclass(frozen=True)
class WalerContactResolution:
    source_handles: tuple[str, ...]
    selected_face: Segment
    provisional_axis: Segment
    side_sign: int
    supporting_evidence: tuple[MemberTerminalEvidence, ...] = ()


@dataclass(frozen=True)
class WalerContactIssue:
    code: str
    message: str
    source_handles: tuple[str, ...]
    member_source_handles: tuple[str, ...] = ()


@dataclass(frozen=True)
class WalerContactOutcome:
    resolutions: tuple[WalerContactResolution, ...] = ()
    issues: tuple[WalerContactIssue, ...] = ()


@dataclass(frozen=True)
class _EnvelopeHypothesis:
    fact: WalerEnvelopeFacts
    evidence_indices: frozenset[int]
    longitudinal_range: tuple[float, float]
    transverse_range: tuple[float, float]


def _normalized_segment(segment: Segment) -> Segment:
    return _ordered_line(
        (float(segment[0][0]), float(segment[0][1])),
        (float(segment[1][0]), float(segment[1][1])),
    )


def _segments_equivalent(first: Segment, second: Segment) -> bool:
    return (
        max(_distance(first[0], second[0]), _distance(first[1], second[1]))
        <= NUMERICAL_GEOMETRY_PRECISION_MM
        or max(_distance(first[0], second[1]), _distance(first[1], second[0]))
        <= NUMERICAL_GEOMETRY_PRECISION_MM
    )


def _normalize_segments(segments: Iterable[Segment]) -> tuple[Segment, ...]:
    normalized: list[Segment] = []
    for raw in segments:
        segment = _normalized_segment(raw)
        if _length(*segment) <= NUMERICAL_GEOMETRY_PRECISION_MM:
            continue
        if any(_segments_equivalent(segment, existing) for existing in normalized):
            continue
        normalized.append(segment)
    return tuple(sorted(normalized))


def _merge_collinear_fragments(
    segments: Sequence[Segment],
    tolerances: GeometryTolerances,
) -> tuple[Segment, ...]:
    """Merge split source rails without collapsing nearby physical rails."""

    merged = list(segments)
    changed = True
    while changed:
        changed = False
        for first_index, first in enumerate(merged):
            axis = _unit(*first)
            if axis is None:
                continue
            first_range = _projection_range(first, axis)
            for second_index in range(first_index + 1, len(merged)):
                second = merged[second_index]
                if (
                    _angle_difference_deg(first, second)
                    > tolerances.parallel_angle_tolerance_deg
                ):
                    continue
                if not any(
                    _distance(first_point, second_point)
                    <= NUMERICAL_GEOMETRY_PRECISION_MM
                    for first_point in first
                    for second_point in second
                ):
                    continue
                if any(
                    abs(
                        (point[0] - first[0][0]) * (-axis[1])
                        + (point[1] - first[0][1]) * axis[0]
                    )
                    > tolerances.collinear_tolerance_mm
                    for point in second
                ):
                    continue
                second_range = _projection_range(second, axis)
                gap = max(
                    first_range[0], second_range[0]
                ) - min(first_range[1], second_range[1])
                if gap > tolerances.endpoint_tolerance_mm:
                    continue
                points = (*first, *second)
                start = min(points, key=lambda point: (_dot(point, axis), point))
                end = max(points, key=lambda point: (_dot(point, axis), point))
                merged[first_index] = _ordered_line(start, end)
                del merged[second_index]
                changed = True
                break
            if changed:
                break
    return _normalize_segments(merged)


def _node_for_point(nodes: list[Point], point: Point) -> int:
    for index, existing in enumerate(nodes):
        if _distance(existing, point) <= NUMERICAL_GEOMETRY_PRECISION_MM:
            return index
    nodes.append(point)
    return len(nodes) - 1


def _connector_path(
    start: Point,
    end: Point,
    segments: Sequence[Segment],
    rail_direction: Segment,
    tolerances: GeometryTolerances,
) -> frozenset[int] | None:
    """Return transverse connector evidence between two rail endpoints."""

    nodes: list[Point] = []
    edges: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for index, segment in enumerate(segments):
        if (
            _angle_difference_deg(segment, rail_direction)
            <= tolerances.parallel_angle_tolerance_deg
        ):
            continue
        first = _node_for_point(nodes, segment[0])
        second = _node_for_point(nodes, segment[1])
        edges[first].append((second, index))
        edges[second].append((first, index))

    start_nodes = [
        index
        for index, point in enumerate(nodes)
        if _distance(point, start) <= NUMERICAL_GEOMETRY_PRECISION_MM
    ]
    end_nodes = {
        index
        for index, point in enumerate(nodes)
        if _distance(point, end) <= NUMERICAL_GEOMETRY_PRECISION_MM
    }
    if not start_nodes or not end_nodes:
        return None

    queue = deque((node, frozenset()) for node in start_nodes)
    visited = set(start_nodes)
    while queue:
        node, used = queue.popleft()
        if node in end_nodes:
            return used
        for target, edge_index in sorted(edges.get(node, ())):
            if target in visited:
                continue
            visited.add(target)
            queue.append((target, used | {edge_index}))
    return None


def _aligned_endpoints(first: Segment, second: Segment) -> tuple[Point, Point, Point, Point]:
    axis = _unit(*first)
    assert axis is not None
    first_ordered = tuple(sorted(first, key=lambda point: _dot(point, axis)))
    second_ordered = tuple(sorted(second, key=lambda point: _dot(point, axis)))
    return first_ordered[0], first_ordered[1], second_ordered[0], second_ordered[1]


def _canonical_pair(first: Segment, second: Segment) -> tuple[Segment, Segment, Segment, float]:
    axis = _unit(*first)
    assert axis is not None
    first_start, first_end, second_start, second_end = _aligned_endpoints(first, second)
    provisional_axis = _ordered_line(
        _midpoint(first_start, second_start),
        _midpoint(first_end, second_end),
    )
    canonical_axis = _unit(*provisional_axis)
    assert canonical_axis is not None
    normal = -canonical_axis[1], canonical_axis[0]
    ordered_faces = tuple(
        sorted(
            (_ordered_line(*first), _ordered_line(*second)),
            key=lambda line: _dot(_midpoint(*line), normal),
        )
    )
    return ordered_faces[0], ordered_faces[1], provisional_axis, _line_separation(first, second)


def _make_hypotheses(
    segments: Sequence[Segment],
    source_handles: tuple[str, ...],
    component_key: str,
    tolerances: GeometryTolerances,
) -> list[_EnvelopeHypothesis]:
    hypotheses: list[_EnvelopeHypothesis] = []
    for first_index, first in enumerate(segments):
        if _length(*first) < tolerances.minimum_component_length_mm:
            continue
        for second_index in range(first_index + 1, len(segments)):
            second = segments[second_index]
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
                tolerances.collinear_tolerance_mm < separation
                <= tolerances.maximum_component_width_mm
            ):
                continue
            first_low, first_high, second_low, second_high = _aligned_endpoints(
                first,
                second,
            )
            low_path = _connector_path(
                first_low,
                second_low,
                segments,
                first,
                tolerances,
            )
            high_path = _connector_path(
                first_high,
                second_high,
                segments,
                first,
                tolerances,
            )
            if low_path is None or high_path is None:
                continue

            lower_face, upper_face, axis, width = _canonical_pair(first, second)
            axis_unit = _unit(*axis)
            assert axis_unit is not None
            normal = -axis_unit[1], axis_unit[0]
            evidence_indices = frozenset(
                {first_index, second_index} | set(low_path) | set(high_path)
            )
            fact = WalerEnvelopeFacts(
                component_key=component_key,
                source_handles=source_handles,
                provisional_axis=axis,
                outer_faces=(lower_face, upper_face),
                source_width=width,
                evidence_segments=tuple(segments[index] for index in sorted(evidence_indices)),
            )
            longitudinal_values = (
                *_projection_range(lower_face, axis_unit),
                *_projection_range(upper_face, axis_unit),
            )
            transverse_values = tuple(
                _dot(point, normal)
                for line in (lower_face, upper_face)
                for point in line
            )
            hypotheses.append(
                _EnvelopeHypothesis(
                    fact=fact,
                    evidence_indices=evidence_indices,
                    longitudinal_range=(
                        min(longitudinal_values),
                        max(longitudinal_values),
                    ),
                    transverse_range=(
                        min(transverse_values),
                        max(transverse_values),
                    ),
                )
            )
    return hypotheses


def _range_contains(
    outer: tuple[float, float],
    inner: tuple[float, float],
) -> bool:
    return (
        outer[0] <= inner[0] + NUMERICAL_GEOMETRY_PRECISION_MM
        and outer[1] >= inner[1] - NUMERICAL_GEOMETRY_PRECISION_MM
    )


def _positive_overlap(
    first: tuple[float, float],
    second: tuple[float, float],
) -> bool:
    return (
        min(first[1], second[1]) - max(first[0], second[0])
        > NUMERICAL_GEOMETRY_PRECISION_MM
    )


def _select_component_hypotheses(
    hypotheses: Sequence[_EnvelopeHypothesis],
    tolerances: GeometryTolerances,
) -> tuple[tuple[_EnvelopeHypothesis, ...], bool]:
    retained: list[_EnvelopeHypothesis] = []
    for candidate in sorted(
        hypotheses,
        key=lambda item: (
            -item.fact.source_width,
            item.fact.provisional_axis,
            item.fact.outer_faces,
        ),
    ):
        if any(
            _range_contains(existing.longitudinal_range, candidate.longitudinal_range)
            and _range_contains(existing.transverse_range, candidate.transverse_range)
            for existing in retained
        ):
            continue
        retained.append(candidate)

    ambiguous = False
    for index, first in enumerate(retained):
        for second in retained[index + 1 :]:
            if (
                _angle_difference_deg(
                    first.fact.provisional_axis,
                    second.fact.provisional_axis,
                )
                > tolerances.parallel_angle_tolerance_deg
            ):
                continue
            if not _positive_overlap(first.longitudinal_range, second.longitudinal_range):
                continue
            if not _positive_overlap(first.transverse_range, second.transverse_range):
                continue
            ambiguous = True
    retained.sort(
        key=lambda item: (
            item.fact.provisional_axis,
            item.fact.outer_faces,
            item.fact.source_handles,
        )
    )
    return tuple(retained), ambiguous


def _qualified_exterior_fact(
    source_handles: tuple[str, ...],
    boundary_faces: Sequence[Segment],
    component_key: str,
    provenance_kind: str,
    tolerances: GeometryTolerances,
) -> WalerEnvelopeOutcome:
    faces = _normalize_segments(boundary_faces)
    if len(faces) == 1:
        return WalerEnvelopeOutcome(
            WalerEnvelopeStatus.SINGLE_LINE,
            (
                WalerEnvelopeFacts(
                    component_key,
                    source_handles,
                    faces[0],
                    (faces[0],),
                    0.0,
                    faces,
                    provenance_kind,
                ),
            ),
        )
    if len(faces) != 2 or (
        _angle_difference_deg(faces[0], faces[1])
        > tolerances.parallel_angle_tolerance_deg
    ):
        return WalerEnvelopeOutcome(
            WalerEnvelopeStatus.UNRESOLVED,
            code="WALER_ENVELOPE_UNRESOLVED",
            message="來源無法建立唯一且完整的圍令外框。",
        )
    lower, upper, axis, width = _canonical_pair(faces[0], faces[1])
    return WalerEnvelopeOutcome(
        WalerEnvelopeStatus.RECOGNIZED,
        (
            WalerEnvelopeFacts(
                component_key,
                source_handles,
                axis,
                (lower, upper),
                width,
                faces,
                provenance_kind,
            ),
        ),
    )


def extract_waler_envelope_facts(
    segments: Sequence[Segment],
    tolerances: GeometryTolerances | None = None,
    *,
    source_handles: Sequence[str] = (),
    component_key: str = "",
    qualified_exterior_faces: Sequence[Segment] | None = None,
    provenance_kind: str = "connected_contour",
) -> WalerEnvelopeOutcome:
    """Build deterministic Waler envelopes before local pair collapse.

    ``qualified_exterior_faces`` is reserved for source routes which already
    prove an exterior component boundary (currently HATCH and MLINE).  General
    LINE/POLYLINE evidence must prove two end connectors around each rail pair.
    """

    tolerances = tolerances or GeometryTolerances()
    handles = tuple(sorted({str(handle).strip().upper() for handle in source_handles if str(handle).strip()}))
    if qualified_exterior_faces is not None:
        return _qualified_exterior_fact(
            handles,
            qualified_exterior_faces,
            component_key,
            provenance_kind,
            tolerances,
        )

    normalized = _merge_collinear_fragments(
        _normalize_segments(segments),
        tolerances,
    )
    if len(normalized) == 1:
        line = normalized[0]
        return WalerEnvelopeOutcome(
            WalerEnvelopeStatus.SINGLE_LINE,
            (
                WalerEnvelopeFacts(
                    component_key,
                    handles,
                    line,
                    (line,),
                    0.0,
                    normalized,
                    "single_line",
                ),
            ),
        )
    hypotheses = _make_hypotheses(
        normalized,
        handles,
        component_key,
        tolerances,
    )
    if not hypotheses:
        return WalerEnvelopeOutcome(
            WalerEnvelopeStatus.UNRESOLVED,
            code="WALER_ENVELOPE_UNRESOLVED",
            message="來源幾何未能證明唯一完整的圍令外框。",
        )
    retained, ambiguous = _select_component_hypotheses(hypotheses, tolerances)
    if ambiguous:
        return WalerEnvelopeOutcome(
            WalerEnvelopeStatus.AMBIGUOUS,
            tuple(item.fact for item in retained),
            "WALER_ENVELOPE_AMBIGUOUS",
            "來源幾何同時支持多個互相重疊的完整圍令外框。",
        )
    return WalerEnvelopeOutcome(
        WalerEnvelopeStatus.RECOGNIZED,
        tuple(item.fact for item in retained),
    )


def _source_identity(handles: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(handle).strip().upper()
                for handle in handles
                if str(handle).strip()
            }
        )
    )


def _fact_identity(fact: WalerEnvelopeFacts) -> tuple[str, ...]:
    return _source_identity(fact.source_handles)


def _terminal_body_point(axis: Segment, terminal_name: str) -> Point:
    return axis[1] if terminal_name == "start" else axis[0]


def _direct_terminal_candidates(
    point: Point,
    walers: Sequence[WalerEnvelopeFacts],
    tolerances: GeometryTolerances,
) -> tuple[tuple[float, tuple[str, ...], WalerEnvelopeFacts, Point], ...]:
    ranked = []
    for waler in walers:
        distance = _segment_distance(point, *waler.provisional_axis)
        if distance > tolerances.connection_tolerance_mm:
            continue
        ranked.append(
            (
                distance,
                _fact_identity(waler),
                waler,
                _project_onto_segment(point, *waler.provisional_axis),
            )
        )
    return tuple(sorted(ranked, key=lambda item: (item[0], item[1], item[3])))


def _extension_terminal_candidates(
    point: Point,
    outward_direction: Point,
    walers: Sequence[WalerEnvelopeFacts],
    tolerances: GeometryTolerances,
) -> tuple[tuple[float, tuple[str, ...], WalerEnvelopeFacts, Point], ...]:
    line_end = point[0] + outward_direction[0], point[1] + outward_direction[1]
    ranked = []
    for waler in walers:
        intersection = _line_segment_intersection_point(
            (point, line_end),
            waler.provisional_axis,
            tolerances.endpoint_tolerance_mm,
        )
        if intersection is None:
            continue
        extension_distance = _dot(_vector(point, intersection), outward_direction)
        if not (
            NUMERICAL_GEOMETRY_PRECISION_MM < extension_distance
            <= tolerances.maximum_brace_axis_extension_mm
        ):
            continue
        ranked.append(
            (
                extension_distance,
                _fact_identity(waler),
                waler,
                intersection,
            )
        )
    return tuple(sorted(ranked, key=lambda item: (item[0], item[1], item[3])))


def _selected_identity_candidate(
    identity: tuple[str, ...],
    axis: Segment,
    walers_by_identity: dict[tuple[str, ...], WalerEnvelopeFacts],
    tolerances: GeometryTolerances,
) -> tuple[WalerEnvelopeFacts, Point] | None:
    waler = walers_by_identity.get(_source_identity(identity))
    if waler is None:
        return None
    intersection = _line_segment_intersection_point(
        axis,
        waler.provisional_axis,
        tolerances.endpoint_tolerance_mm,
    )
    if intersection is None:
        return None
    return waler, intersection


def _terminal_evidence(
    member: MemberGeometryFacts,
    terminal_name: str,
    waler: WalerEnvelopeFacts,
    intersection: Point,
    relation_kind: str,
) -> MemberTerminalEvidence:
    return MemberTerminalEvidence(
        member_role=member.role,
        member_source_handles=_source_identity(member.source_handles),
        terminal_name=terminal_name,
        waler_source_handles=_fact_identity(waler),
        provisional_intersection=intersection,
        body_point=_terminal_body_point(member.axis, terminal_name),
        relation_kind=relation_kind,
    )


def build_member_terminal_evidence(
    members: Sequence[MemberGeometryFacts],
    walers: Sequence[WalerEnvelopeFacts],
    tolerances: GeometryTolerances | None = None,
) -> TerminalTopologyOutcome:
    """Establish terminal identities without changing recognized member axes."""

    tolerances = tolerances or GeometryTolerances()
    walers_by_identity = {_fact_identity(waler): waler for waler in walers}
    evidence: list[MemberTerminalEvidence] = []
    issues: list[TerminalTopologyIssue] = []
    for member in sorted(
        members,
        key=lambda item: (
            item.role,
            _source_identity(item.source_handles),
            _ordered_line(*item.axis),
        ),
    ):
        axis = _ordered_line(*member.axis)
        direction = _unit(*axis)
        if direction is None:
            issues.append(
                TerminalTopologyIssue(
                    "error",
                    "WALER_CONTACT_FACE_UNRESOLVED",
                    "構件軸線為零長度，無法判斷圍令接觸側。",
                    member.role,
                    _source_identity(member.source_handles),
                )
            )
            continue

        selected = tuple(
            _source_identity(identity)
            for identity in member.selected_waler_source_handles
        )
        if selected:
            resolved_selected = []
            for identity in selected:
                result = _selected_identity_candidate(
                    identity,
                    axis,
                    walers_by_identity,
                    tolerances,
                )
                if result is None:
                    issues.append(
                        TerminalTopologyIssue(
                            "error",
                            "WALER_CONTACT_FACE_UNRESOLVED",
                            "已選定的圍令來源無法與構件軸線建立 provisional 交點。",
                            member.role,
                            _source_identity(member.source_handles),
                            (identity,),
                        )
                    )
                    continue
                resolved_selected.append(result)
            for waler, intersection in resolved_selected:
                terminal_name = min(
                    ("start", "end"),
                    key=lambda name: (
                        _distance(intersection, axis[0] if name == "start" else axis[1]),
                        name,
                    ),
                )
                evidence.append(
                    _terminal_evidence(
                        member,
                        terminal_name,
                        waler,
                        intersection,
                        "selected_source_identity",
                    )
                )
            continue

        for terminal_name, point, outward in (
            ("start", axis[0], (-direction[0], -direction[1])),
            ("end", axis[1], direction),
        ):
            ranked = _direct_terminal_candidates(point, walers, tolerances)
            relation_kind = "direct"
            if not ranked and member.role == "brace" and member.allow_axis_extension:
                ranked = _extension_terminal_candidates(
                    point,
                    outward,
                    walers,
                    tolerances,
                )
                relation_kind = "axis_extension"
            if not ranked:
                continue
            best = ranked[0]
            competitors = tuple(
                item[1]
                for item in ranked[1:]
                if item[0] - best[0] <= tolerances.ambiguous_connection_delta_mm
            )
            if competitors:
                issues.append(
                    TerminalTopologyIssue(
                        (
                            "error"
                            if relation_kind == "axis_extension"
                            else "warning"
                        ),
                        (
                            "AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION"
                            if relation_kind == "axis_extension"
                            else "AMBIGUOUS_WALER_CONNECTION"
                        ),
                        (
                            "斜撐端點沿軸線延伸時同時符合多個 provisional 圍令來源，"
                            "無法唯一建立接觸關係。"
                            if relation_kind == "axis_extension"
                            else "構件端點同時接近多個 provisional 圍令來源，採用距離較近者。"
                        ),
                        member.role,
                        _source_identity(member.source_handles),
                        (best[1], *competitors),
                    )
                )
                if relation_kind == "axis_extension":
                    continue
            evidence.append(
                _terminal_evidence(
                    member,
                    terminal_name,
                    best[2],
                    best[3],
                    relation_kind,
                )
            )
    return TerminalTopologyOutcome(
        tuple(
            sorted(
                evidence,
                key=lambda item: (
                    item.waler_source_handles,
                    item.member_role,
                    item.member_source_handles,
                    item.terminal_name,
                ),
            )
        ),
        tuple(
            sorted(
                issues,
                key=lambda item: (
                    item.code,
                    item.severity,
                    item.role,
                    item.source_handles,
                    item.competing_waler_source_handles,
                ),
            )
        ),
    )


def _face_offset(face: Segment, normal: Point) -> float:
    return _dot(_midpoint(*face), normal)


def resolve_waler_contact_faces(
    walers: Sequence[WalerEnvelopeFacts],
    evidence: Sequence[MemberTerminalEvidence],
    tolerances: GeometryTolerances | None = None,
) -> WalerContactOutcome:
    """Select the support-side outer face for every Waler envelope."""

    tolerances = tolerances or GeometryTolerances()
    by_waler: dict[tuple[str, ...], list[MemberTerminalEvidence]] = defaultdict(list)
    for item in evidence:
        by_waler[_source_identity(item.waler_source_handles)].append(item)

    resolutions: list[WalerContactResolution] = []
    issues: list[WalerContactIssue] = []
    for waler in sorted(
        walers,
        key=lambda item: (
            _fact_identity(item),
            item.component_key,
            item.provisional_axis,
        ),
    ):
        identity = _fact_identity(waler)
        related = tuple(
            sorted(
                by_waler.get(identity, ()),
                key=lambda item: (
                    item.member_role,
                    item.member_source_handles,
                    item.terminal_name,
                ),
            )
        )
        if not waler.has_physical_envelope:
            resolutions.append(
                WalerContactResolution(
                    identity,
                    waler.outer_faces[0],
                    waler.provisional_axis,
                    0,
                    related,
                )
            )
            continue

        axis = _unit(*waler.provisional_axis)
        assert axis is not None
        normal = -axis[1], axis[0]
        reliable: list[tuple[int, MemberTerminalEvidence]] = []
        degenerate: list[MemberTerminalEvidence] = []
        for item in related:
            signed_component = _dot(item.body_vector, normal)
            if abs(signed_component) <= tolerances.endpoint_tolerance_mm:
                degenerate.append(item)
                continue
            reliable.append((1 if signed_component > 0.0 else -1, item))
        signs = {sign for sign, _item in reliable}
        if not signs:
            issues.append(
                WalerContactIssue(
                    "WALER_CONTACT_FACE_UNRESOLVED",
                    "圍令已有完整外框，但沒有可靠的相關支撐／斜撐側向證據。",
                    identity,
                    tuple(
                        sorted(
                            {
                                handle
                                for item in degenerate
                                for handle in item.member_source_handles
                            }
                        )
                    ),
                )
            )
            continue
        if len(signs) > 1:
            issues.append(
                WalerContactIssue(
                    "WALER_CONTACT_FACE_AMBIGUOUS",
                    "同一圍令的可靠構件證據同時指向外框兩側。",
                    identity,
                    tuple(
                        sorted(
                            {
                                handle
                                for _sign, item in reliable
                                for handle in item.member_source_handles
                            }
                        )
                    ),
                )
            )
            continue
        side_sign = next(iter(signs))
        selected = (
            max(waler.outer_faces, key=lambda face: _face_offset(face, normal))
            if side_sign > 0
            else min(waler.outer_faces, key=lambda face: _face_offset(face, normal))
        )
        resolutions.append(
            WalerContactResolution(
                identity,
                _ordered_line(*selected),
                waler.provisional_axis,
                side_sign,
                tuple(item for _sign, item in reliable),
            )
        )
    return WalerContactOutcome(tuple(resolutions), tuple(issues))


__all__ = [
    "MemberGeometryFacts",
    "MemberTerminalEvidence",
    "NUMERICAL_GEOMETRY_PRECISION_MM",
    "TerminalTopologyIssue",
    "TerminalTopologyOutcome",
    "WalerContactIssue",
    "WalerContactOutcome",
    "WalerContactResolution",
    "WalerEnvelopeFacts",
    "WalerEnvelopeOutcome",
    "WalerEnvelopeStatus",
    "build_member_terminal_evidence",
    "extract_waler_envelope_facts",
    "resolve_waler_contact_faces",
]
