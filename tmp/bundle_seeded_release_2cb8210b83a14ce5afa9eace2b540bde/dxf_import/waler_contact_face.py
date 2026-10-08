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
    _line_distance,
    _line_segment_intersection_point,
    _line_separation,
    _midpoint,
    _ordered_line,
    _projection_overlap_ratio,
    _supporting_line_separation,
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
SIGNIFICANT_WALER_OVERLAP_RATIO = 0.50


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
class WalerOverlapFact:
    """One finite, source-supported overlap between distinct Waler identities."""

    source_identities: tuple[tuple[str, ...], tuple[str, ...]]
    overlap_segment: Segment
    overlap_length: float
    provisional_axis_lengths: tuple[float, float]
    overlap_ratio: float


@dataclass(frozen=True)
class WalerOverlapCompetition:
    """Direct identity provenance linking an overlap to one competition context."""

    overlap: WalerOverlapFact
    context_kind: str
    context_identity: str
    member_role: str = ""
    member_source_handles: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemberGeometryFacts:
    """Source-recognized member geometry used only for terminal relations."""

    role: str
    source_handles: tuple[str, ...]
    axis: Segment
    selected_waler_source_handles: tuple[tuple[str, ...], ...] = ()
    allow_axis_extension: bool = True


class TerminalIdentityState(str, Enum):
    """Whether a terminal relation may establish a formal member identity."""

    UNIQUE = "unique"
    COMPETING = "competing"


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
    identity_state: TerminalIdentityState = TerminalIdentityState.UNIQUE

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
    terminal_name: str = ""


@dataclass(frozen=True)
class TerminalTopologyOutcome:
    evidence: tuple[MemberTerminalEvidence, ...] = ()
    issues: tuple[TerminalTopologyIssue, ...] = ()

    @property
    def unique_evidence(self) -> tuple[MemberTerminalEvidence, ...]:
        """Canonical relation view allowed to establish member connections."""

        return tuple(
            item
            for item in self.evidence
            if item.identity_state is TerminalIdentityState.UNIQUE
        )


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
    competing_waler_source_handles: tuple[tuple[str, ...], ...] = ()
    finalization_context: str = ""
    severity: str = "error"
    unique_member_source_handles: tuple[str, ...] = ()
    ignored_competing_member_source_handles: tuple[str, ...] = ()


@dataclass(frozen=True)
class WalerContactOutcome:
    resolutions: tuple[WalerContactResolution, ...] = ()
    issues: tuple[WalerContactIssue, ...] = ()


class BraceTerminalStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class BraceTerminalVerdict:
    """Runtime-only, atomic verdict for one Brace's two Waler terminals."""

    member_source_handles: tuple[str, ...]
    status: BraceTerminalStatus
    source_axis: Segment
    formal_axis: Segment | None = None
    terminal_source_handles: tuple[
        tuple[str, tuple[str, ...], str], ...
    ] = ()
    terminal_points: tuple[tuple[str, Point], ...] = ()
    reason_codes: tuple[str, ...] = ()

    @property
    def is_resolved(self) -> bool:
        return self.status is BraceTerminalStatus.RESOLVED


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
                shared_points = tuple(
                    first_point
                    for first_point in first
                    for second_point in second
                    if _distance(first_point, second_point)
                    <= NUMERICAL_GEOMETRY_PRECISION_MM
                )
                if not shared_points:
                    continue
                if any(
                    _angle_difference_deg(connector, first)
                    > tolerances.parallel_angle_tolerance_deg
                    and _length(*connector) > tolerances.collinear_tolerance_mm
                    and any(
                        _distance(endpoint, shared_point)
                        <= NUMERICAL_GEOMETRY_PRECISION_MM
                        for endpoint in connector
                        for shared_point in shared_points
                    )
                    for connector in merged
                    if connector not in {first, second}
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
    return (
        ordered_faces[0],
        ordered_faces[1],
        provisional_axis,
        _supporting_line_separation(first, second),
    )


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
            separation = _supporting_line_separation(first, second)
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


def _recognized_component_envelope(
    segments: Sequence[Segment],
    recognized_faces: Sequence[Segment],
    source_handles: tuple[str, ...],
    component_key: str,
    tolerances: GeometryTolerances,
) -> WalerEnvelopeOutcome | None:
    """Expand a proven component pair to nearby full-span physical rails.

    This adapter is intentionally narrower than "same root INSERT": every
    longitudinal rail must belong to the already-recognized pair within the
    existing collinear tolerance.  A second nearby Waler therefore cannot be
    pulled into the envelope merely because it shares a root or direction.
    """

    core = _normalize_segments(recognized_faces)
    if len(core) != 2:
        return None
    if (
        _angle_difference_deg(core[0], core[1])
        > tolerances.parallel_angle_tolerance_deg
        or _projection_overlap_ratio(core[0], core[1])
        < tolerances.minimum_projection_overlap_ratio
    ):
        return None
    rails = []
    for segment in _merge_collinear_fragments(
        _normalize_segments(segments),
        tolerances,
    ):
        if (
            _angle_difference_deg(segment, core[0])
            > tolerances.parallel_angle_tolerance_deg
        ):
            continue
        if (
            _projection_overlap_ratio(segment, core[0])
            < tolerances.minimum_projection_overlap_ratio
        ):
            continue
        if min(_line_separation(segment, face) for face in core) > (
            tolerances.collinear_tolerance_mm
        ):
            return None
        rails.append(segment)
    if len(rails) < 2:
        return None
    axis = _unit(*core[0])
    assert axis is not None
    normal = -axis[1], axis[0]
    rails.sort(key=lambda line: (_dot(_midpoint(*line), normal), line))
    lower, upper = rails[0], rails[-1]
    if (
        _supporting_line_separation(lower, upper)
        > tolerances.maximum_component_width_mm
    ):
        return None
    return _qualified_exterior_fact(
        source_handles,
        (lower, upper),
        component_key,
        "recognized_component_envelope",
        tolerances,
    )


def extract_waler_envelope_facts(
    segments: Sequence[Segment],
    tolerances: GeometryTolerances | None = None,
    *,
    source_handles: Sequence[str] = (),
    component_key: str = "",
    qualified_exterior_faces: Sequence[Segment] | None = None,
    recognized_component_faces: Sequence[Segment] | None = None,
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
        if recognized_component_faces is not None:
            recognized = _recognized_component_envelope(
                normalized,
                recognized_component_faces,
                handles,
                component_key,
                tolerances,
            )
            if recognized is not None:
                return recognized
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


def _finite_segment(segment: Segment) -> bool:
    return all(
        math.isfinite(float(coordinate))
        for point in segment
        for coordinate in point
    )


def _has_reliable_source_supported_axis(fact: WalerEnvelopeFacts) -> bool:
    """Return whether the fact owns a finite axis backed by source evidence."""

    if not _fact_identity(fact) or not fact.evidence_segments:
        return False
    if not _finite_segment(fact.provisional_axis):
        return False
    if _length(*fact.provisional_axis) <= NUMERICAL_GEOMETRY_PRECISION_MM:
        return False
    return any(
        _finite_segment(segment)
        and _length(*segment) > NUMERICAL_GEOMETRY_PRECISION_MM
        for segment in fact.evidence_segments
    )


def _canonical_identity_pair(
    first: Sequence[str],
    second: Sequence[str],
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    first_identity = _source_identity(first)
    second_identity = _source_identity(second)
    if (
        not first_identity
        or not second_identity
        or set(first_identity) & set(second_identity)
    ):
        return None
    return tuple(sorted((first_identity, second_identity)))  # type: ignore[return-value]


def find_significant_waler_overlaps(
    walers: Sequence[WalerEnvelopeFacts],
    tolerances: GeometryTolerances | None = None,
    *,
    minimum_overlap_ratio: float = SIGNIFICANT_WALER_OVERLAP_RATIO,
) -> tuple[WalerOverlapFact, ...]:
    """Qualify finite collinear overlaps without using finalized geometry."""

    tolerances = tolerances or GeometryTolerances()
    facts: list[WalerOverlapFact] = []
    ordered_walers = tuple(
        sorted(
            (item for item in walers if _has_reliable_source_supported_axis(item)),
            key=lambda item: (
                _fact_identity(item),
                _ordered_line(*item.provisional_axis),
                item.component_key,
            ),
        )
    )
    for first_index, first in enumerate(ordered_walers):
        for second in ordered_walers[first_index + 1 :]:
            identity_pair = _canonical_identity_pair(
                first.source_handles,
                second.source_handles,
            )
            if identity_pair is None:
                continue
            first_axis = _ordered_line(*first.provisional_axis)
            second_axis = _ordered_line(*second.provisional_axis)
            if (
                _angle_difference_deg(first_axis, second_axis)
                > tolerances.parallel_angle_tolerance_deg
            ):
                continue
            if max(
                *(
                    _line_distance(point, *first_axis)
                    for point in second_axis
                ),
                *(
                    _line_distance(point, *second_axis)
                    for point in first_axis
                ),
            ) > tolerances.collinear_tolerance_mm:
                continue
            axis = _unit(*first_axis)
            if axis is None:
                continue
            first_range = _projection_range(first_axis, axis)
            second_range = _projection_range(second_axis, axis)
            overlap_low = max(first_range[0], second_range[0])
            overlap_high = min(first_range[1], second_range[1])
            overlap_length = overlap_high - overlap_low
            if overlap_length <= NUMERICAL_GEOMETRY_PRECISION_MM:
                continue
            lengths_by_identity = {
                _fact_identity(first): _length(*first_axis),
                _fact_identity(second): _length(*second_axis),
            }
            axis_lengths = tuple(
                lengths_by_identity[identity] for identity in identity_pair
            )
            denominator = min(axis_lengths)
            if denominator <= NUMERICAL_GEOMETRY_PRECISION_MM:
                continue
            overlap_ratio = overlap_length / denominator
            if overlap_ratio < minimum_overlap_ratio:
                continue
            normal = -axis[1], axis[0]
            reference_offset = sum(
                _dot(_midpoint(*line), normal)
                for line in (first_axis, second_axis)
            ) / 2.0
            overlap_segment = _ordered_line(
                (
                    axis[0] * overlap_low + normal[0] * reference_offset,
                    axis[1] * overlap_low + normal[1] * reference_offset,
                ),
                (
                    axis[0] * overlap_high + normal[0] * reference_offset,
                    axis[1] * overlap_high + normal[1] * reference_offset,
                ),
            )
            facts.append(
                WalerOverlapFact(
                    source_identities=identity_pair,
                    overlap_segment=overlap_segment,
                    overlap_length=overlap_length,
                    provisional_axis_lengths=axis_lengths,
                    overlap_ratio=overlap_ratio,
                )
            )
    return tuple(
        sorted(
            facts,
            key=lambda item: (
                item.source_identities,
                item.overlap_segment,
                item.overlap_length,
            ),
        )
    )


def find_waler_overlap_competitions(
    overlaps: Sequence[WalerOverlapFact],
    topology_issues: Sequence[TerminalTopologyIssue],
    contact_issues: Sequence[WalerContactIssue] = (),
) -> tuple[WalerOverlapCompetition, ...]:
    """Join overlap pairs only to direct same-context competing identities."""

    competitions: list[WalerOverlapCompetition] = []
    for overlap in overlaps:
        required = frozenset(overlap.source_identities)
        for issue in topology_issues:
            competing = frozenset(
                _source_identity(identity)
                for identity in issue.competing_waler_source_handles
                if _source_identity(identity)
            )
            if not issue.terminal_name or not required.issubset(competing):
                continue
            competitions.append(
                WalerOverlapCompetition(
                    overlap=overlap,
                    context_kind="terminal",
                    context_identity=issue.terminal_name,
                    member_role=issue.role,
                    member_source_handles=_source_identity(issue.source_handles),
                )
            )
        for issue in contact_issues:
            competing = frozenset(
                _source_identity(identity)
                for identity in issue.competing_waler_source_handles
                if _source_identity(identity)
            )
            if not issue.finalization_context or not required.issubset(competing):
                continue
            competitions.append(
                WalerOverlapCompetition(
                    overlap=overlap,
                    context_kind="contact_face_finalization",
                    context_identity=issue.finalization_context,
                    member_source_handles=_source_identity(
                        issue.member_source_handles
                    ),
                )
            )
    return tuple(
        sorted(
            set(competitions),
            key=lambda item: (
                item.overlap.source_identities,
                item.context_kind,
                item.context_identity,
                item.member_role,
                item.member_source_handles,
            ),
        )
    )


def _terminal_body_point(axis: Segment, terminal_name: str) -> Point:
    return axis[1] if terminal_name == "start" else axis[0]


def _direct_terminal_candidates(
    point: Point,
    member_axis: Segment,
    walers: Sequence[WalerEnvelopeFacts],
    tolerances: GeometryTolerances,
) -> tuple[tuple[float, tuple[str, ...], WalerEnvelopeFacts, Point], ...]:
    ranked = []
    for waler in walers:
        relation_lines = (
            waler.outer_faces
            if waler.has_physical_envelope
            else (waler.provisional_axis,)
        )
        distance = min(
            _segment_distance(point, *line)
            for line in relation_lines
        )
        if distance > tolerances.connection_tolerance_mm:
            continue
        intersection = _line_segment_intersection_point(
            member_axis,
            waler.provisional_axis,
            tolerances.endpoint_tolerance_mm,
        )
        if intersection is None:
            intersection = _project_onto_segment(
                point,
                *waler.provisional_axis,
            )
        ranked.append(
            (
                distance,
                _fact_identity(waler),
                waler,
                intersection,
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
        provisional_intersection = _line_segment_intersection_point(
            (point, line_end),
            waler.provisional_axis,
            tolerances.endpoint_tolerance_mm,
        )
        if provisional_intersection is None:
            continue
        relation_lines = (
            waler.outer_faces
            if waler.has_physical_envelope
            else (waler.provisional_axis,)
        )
        outward_distances = tuple(
            distance
            for line in relation_lines
            for intersection in (
                _line_segment_intersection_point(
                    (point, line_end),
                    line,
                    tolerances.endpoint_tolerance_mm,
                ),
            )
            if intersection is not None
            for distance in (
                _dot(_vector(point, intersection), outward_direction),
            )
            if distance > NUMERICAL_GEOMETRY_PRECISION_MM
        )
        if not outward_distances:
            continue
        extension_distance = min(outward_distances)
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
                provisional_intersection,
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
    identity_state: TerminalIdentityState = TerminalIdentityState.UNIQUE,
) -> MemberTerminalEvidence:
    return MemberTerminalEvidence(
        member_role=member.role,
        member_source_handles=_source_identity(member.source_handles),
        terminal_name=terminal_name,
        waler_source_handles=_fact_identity(waler),
        provisional_intersection=intersection,
        body_point=_terminal_body_point(member.axis, terminal_name),
        relation_kind=relation_kind,
        identity_state=identity_state,
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
            ranked = _direct_terminal_candidates(
                point,
                axis,
                walers,
                tolerances,
            )
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
            numerically_equal = tuple(
                item
                for item in ranked[1:]
                if item[0] - best[0] <= NUMERICAL_GEOMETRY_PRECISION_MM
            )
            if numerically_equal:
                competing = (best, *numerically_equal)
                evidence.extend(
                    _terminal_evidence(
                        member,
                        terminal_name,
                        item[2],
                        item[3],
                        relation_kind,
                        TerminalIdentityState.COMPETING,
                    )
                    for item in competing
                )
                issues.append(
                    TerminalTopologyIssue(
                        "error",
                        (
                            "AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION"
                            if relation_kind == "axis_extension"
                            else "AMBIGUOUS_WALER_CONNECTION"
                        ),
                        "構件端點對多支圍令形成數值上等價的合法關係，無法唯一決定連接。",
                        member.role,
                        _source_identity(member.source_handles),
                        tuple(item[1] for item in competing),
                        terminal_name=terminal_name,
                    )
                )
                continue
            competitors = tuple(
                item
                for item in ranked[1:]
                if item[0] - best[0] <= tolerances.ambiguous_connection_delta_mm
            )
            if competitors:
                competing = (best, *competitors)
                evidence.extend(
                    _terminal_evidence(
                        member,
                        terminal_name,
                        item[2],
                        item[3],
                        relation_kind,
                        TerminalIdentityState.COMPETING,
                    )
                    for item in competing
                )
                issues.append(
                    TerminalTopologyIssue(
                        "error",
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
                        tuple(item[1] for item in competing),
                        terminal_name=terminal_name,
                    )
                )
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
                    item.relation_kind,
                    item.identity_state.value,
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
                    item.terminal_name,
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
                    item.identity_state.value,
                    item.relation_kind,
                    item.provisional_intersection,
                    item.body_point,
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
        reliable_unique: list[tuple[int, MemberTerminalEvidence]] = []
        reliable_competing: list[tuple[int, MemberTerminalEvidence]] = []
        degenerate: list[MemberTerminalEvidence] = []
        for item in related:
            signed_component = _dot(item.body_vector, normal)
            if abs(signed_component) <= tolerances.endpoint_tolerance_mm:
                degenerate.append(item)
                continue
            target = (
                reliable_unique
                if item.identity_state is TerminalIdentityState.UNIQUE
                else reliable_competing
            )
            target.append((1 if signed_component > 0.0 else -1, item))
        authoritative = reliable_unique if reliable_unique else reliable_competing
        signs = {sign for sign, _item in authoritative}
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
                                for _sign, item in authoritative
                                for handle in item.member_source_handles
                            }
                        )
                    ),
                )
            )
            continue
        side_sign = next(iter(signs))
        conflicting_competing = tuple(
            item
            for sign, item in reliable_competing
            if reliable_unique and sign != side_sign
        )
        if conflicting_competing:
            unique_sources = tuple(
                sorted(
                    {
                        handle
                        for _sign, item in reliable_unique
                        for handle in item.member_source_handles
                    }
                )
            )
            competing_sources = tuple(
                sorted(
                    {
                        handle
                        for item in conflicting_competing
                        for handle in item.member_source_handles
                    }
                )
            )
            issues.append(
                WalerContactIssue(
                    code="WALER_COMPETING_SIDE_EVIDENCE_IGNORED",
                    message=(
                        "圍令已有可靠 unique 側向證據；方向相反的 competing "
                        "證據僅保留供追溯，不改變正式接觸面。"
                    ),
                    source_handles=identity,
                    member_source_handles=tuple(
                        sorted({*unique_sources, *competing_sources})
                    ),
                    severity="warning",
                    unique_member_source_handles=unique_sources,
                    ignored_competing_member_source_handles=competing_sources,
                )
            )
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
                tuple(item for _sign, item in authoritative),
            )
        )
    return WalerContactOutcome(tuple(resolutions), tuple(issues))


def build_brace_terminal_verdicts(
    members: Sequence[MemberGeometryFacts],
    topology: TerminalTopologyOutcome,
    contact: WalerContactOutcome,
    tolerances: GeometryTolerances | None = None,
) -> tuple[BraceTerminalVerdict, ...]:
    """Resolve Brace terminals atomically after Waler contact faces finalize.

    Terminal evidence remains an input to Waler contact-face selection even
    when this later member-level verdict is unresolved.  This function never
    feeds its result back into ``resolve_waler_contact_faces``.
    """

    tolerances = tolerances or GeometryTolerances()
    resolutions = {
        _source_identity(item.source_handles): item
        for item in contact.resolutions
    }
    evidence_by_member: dict[
        tuple[str, ...], list[MemberTerminalEvidence]
    ] = defaultdict(list)
    for item in topology.unique_evidence:
        if item.member_role == "brace":
            evidence_by_member[_source_identity(item.member_source_handles)].append(
                item
            )
    issues_by_member: dict[tuple[str, ...], list[TerminalTopologyIssue]] = (
        defaultdict(list)
    )
    for item in topology.issues:
        if item.role == "brace" and item.severity in {"error", "critical"}:
            issues_by_member[_source_identity(item.source_handles)].append(item)

    verdicts: list[BraceTerminalVerdict] = []
    for member in sorted(
        (item for item in members if item.role == "brace"),
        key=lambda item: (
            _source_identity(item.source_handles),
            _ordered_line(*item.axis),
        ),
    ):
        identity = _source_identity(member.source_handles)
        source_axis = _ordered_line(*member.axis)
        evidence = tuple(
            sorted(
                evidence_by_member.get(identity, ()),
                key=lambda item: (
                    item.terminal_name,
                    _source_identity(item.waler_source_handles),
                    item.relation_kind,
                ),
            )
        )
        reasons = {
            issue.code for issue in issues_by_member.get(identity, ())
        }
        by_terminal = {
            terminal_name: tuple(
                item for item in evidence if item.terminal_name == terminal_name
            )
            for terminal_name in ("start", "end")
        }
        evidence_count = sum(bool(items) for items in by_terminal.values())
        if any(len(items) != 1 for items in by_terminal.values()):
            reasons.add(
                "BRACE_NOT_CONNECTED"
                if evidence_count == 0
                else "BRACE_ONE_END_NOT_CONNECTED"
            )

        ordered_evidence = tuple(
            by_terminal[name][0]
            for name in ("start", "end")
            if len(by_terminal[name]) == 1
        )
        waler_identities = tuple(
            _source_identity(item.waler_source_handles)
            for item in ordered_evidence
        )
        if len(waler_identities) == 2 and waler_identities[0] == waler_identities[1]:
            reasons.add("BRACE_SAME_WALER_CONNECTION")

        terminal_points: list[tuple[str, Point]] = []
        terminal_sources: list[tuple[str, tuple[str, ...], str]] = []
        if not reasons:
            for item in ordered_evidence:
                waler_identity = _source_identity(item.waler_source_handles)
                resolution = resolutions.get(waler_identity)
                if resolution is None or not _finite_segment(resolution.selected_face):
                    reasons.add("WALER_CONTACT_FACE_UNRESOLVED")
                    continue
                intersection = _line_segment_intersection_point(
                    source_axis,
                    resolution.selected_face,
                    tolerances.endpoint_tolerance_mm,
                )
                if intersection is None or not all(
                    math.isfinite(float(coordinate)) for coordinate in intersection
                ):
                    reasons.add("WALER_CONTACT_FINALIZE_FAILED")
                    continue
                terminal_points.append((item.terminal_name, intersection))
                terminal_sources.append(
                    (item.terminal_name, waler_identity, item.relation_kind)
                )

        formal_axis: Segment | None = None
        if not reasons and len(terminal_points) == 2:
            points = dict(terminal_points)
            formal_axis = _ordered_line(points["start"], points["end"])
            if (
                not _finite_segment(formal_axis)
                or _length(*formal_axis) < tolerances.minimum_component_length_mm
            ):
                formal_axis = None
                reasons.add("WALER_CONTACT_FINALIZE_FAILED")

        resolved = not reasons and formal_axis is not None
        verdicts.append(
            BraceTerminalVerdict(
                member_source_handles=identity,
                status=(
                    BraceTerminalStatus.RESOLVED
                    if resolved
                    else BraceTerminalStatus.UNRESOLVED
                ),
                source_axis=source_axis,
                formal_axis=formal_axis if resolved else None,
                terminal_source_handles=(
                    tuple(sorted(terminal_sources)) if resolved else ()
                ),
                terminal_points=(tuple(sorted(terminal_points)) if resolved else ()),
                reason_codes=tuple(sorted(reasons)),
            )
        )
    return tuple(verdicts)


__all__ = [
    "BraceTerminalStatus",
    "BraceTerminalVerdict",
    "MemberGeometryFacts",
    "MemberTerminalEvidence",
    "NUMERICAL_GEOMETRY_PRECISION_MM",
    "SIGNIFICANT_WALER_OVERLAP_RATIO",
    "TerminalTopologyIssue",
    "TerminalTopologyOutcome",
    "TerminalIdentityState",
    "WalerContactIssue",
    "WalerContactOutcome",
    "WalerContactResolution",
    "WalerEnvelopeFacts",
    "WalerEnvelopeOutcome",
    "WalerEnvelopeStatus",
    "WalerOverlapCompetition",
    "WalerOverlapFact",
    "build_member_terminal_evidence",
    "build_brace_terminal_verdicts",
    "extract_waler_envelope_facts",
    "find_significant_waler_overlaps",
    "find_waler_overlap_competitions",
    "resolve_waler_contact_faces",
]
