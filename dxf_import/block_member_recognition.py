"""Pure whole-block geometry interpretation for component-like BIM members."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
import math
from statistics import median
from typing import Sequence

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
    _same_point,
    _unit,
)
from .models import GeometryTolerances


NUMERIC_EPSILON = 1e-9


class BlockMemberRecognitionStatus(str, Enum):
    """Mutually exclusive outcomes from whole-block geometry interpretation."""

    NOT_APPLICABLE = "not_applicable"
    RECOGNIZED = "recognized"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"


class FragmentEvidenceKind(str, Enum):
    """How a local fragment axis was derived from source geometry."""

    OUTLINE = "outline"
    RAIL_PAIR = "rail_pair"
    WEAK_LINE = "weak_line"


class _CandidateAuthorityTier(IntEnum):
    """Whole-source evidence order for contextual Strut center authority."""

    TOPOLOGY = 1
    WHOLE_ROOT_ENVELOPE = 2
    LOCAL_RAIL_PAIR = 3


@dataclass(frozen=True)
class BlockMemberPrimitive:
    """One already-WCS primitive inside a single root source scope."""

    points: tuple[Point, ...]
    closed: bool
    entity_type: str
    source_handle: str = ""
    source_width: float = 0.0

    def __post_init__(self) -> None:
        if not all(
            math.isfinite(float(coordinate))
            for point in self.points
            for coordinate in point
        ):
            raise ValueError("Block member primitive points must be finite")
        if not math.isfinite(self.source_width) or self.source_width < 0.0:
            raise ValueError("Block member primitive width must be finite and non-negative")


@dataclass(frozen=True)
class BlockMemberRecognitionInput:
    """Immutable geometry input for one root INSERT recognition invocation."""

    root_handle: str
    root_entity_type: str
    role: str
    primitives: tuple[BlockMemberPrimitive, ...]

    def __post_init__(self) -> None:
        if not self.root_handle.strip():
            raise ValueError("Root source handle is required")
        if not self.root_entity_type.strip():
            raise ValueError("Root entity type is required")
        if not self.role.strip():
            raise ValueError("Root role is required")


@dataclass(frozen=True)
class WalerSpanReference:
    """Immutable formal Waler geometry visible to downstream recognition."""

    source_handles: tuple[str, ...]
    reference_segment: tuple[Point, Point]
    boundary_segments: tuple[tuple[Point, Point], ...] = ()

    def __post_init__(self) -> None:
        handles = tuple(
            sorted(
                {
                    str(handle).strip().upper()
                    for handle in self.source_handles
                    if str(handle).strip()
                }
            )
        )
        if not handles:
            raise ValueError("Formal Waler context requires source identity")
        reference = _ordered_line(*self.reference_segment)
        if not all(
            math.isfinite(float(coordinate))
            for point in reference
            for coordinate in point
        ) or _length(*reference) <= NUMERIC_EPSILON:
            raise ValueError("Formal Waler context requires a finite segment")
        normalized_boundaries = []
        for segment in self.boundary_segments:
            boundary = _ordered_line(*segment)
            if not all(
                math.isfinite(float(coordinate))
                for point in boundary
                for coordinate in point
            ):
                raise ValueError("Formal Waler boundaries must be finite")
            if _length(*boundary) > NUMERIC_EPSILON:
                normalized_boundaries.append(boundary)
        boundaries = tuple(sorted(set(normalized_boundaries)))
        object.__setattr__(self, "source_handles", handles)
        object.__setattr__(self, "reference_segment", reference)
        object.__setattr__(self, "boundary_segments", boundaries)


@dataclass(frozen=True)
class BlockMemberRecognitionOutcome:
    """Result of interpreting one root source as one component-like member."""

    status: BlockMemberRecognitionStatus
    whole_axis: tuple[Point, Point] | None = None
    representative_width: float = 0.0
    confidence: float = 0.0
    diagnostic_code: str = ""
    accepted_fragment_count: int = 0
    selected_waler_source_handles: tuple[tuple[str, ...], ...] = ()
    waler_intersections: tuple[Point, ...] = ()

    def __post_init__(self) -> None:
        if not math.isfinite(self.representative_width) or self.representative_width < 0.0:
            raise ValueError("Representative width must be finite and non-negative")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between zero and one")
        if self.accepted_fragment_count < 0:
            raise ValueError("Accepted fragment count cannot be negative")
        normalized_waler_handles = tuple(
            tuple(sorted(str(handle).strip().upper() for handle in handles))
            for handles in self.selected_waler_source_handles
        )
        if any(not handles for handles in normalized_waler_handles):
            raise ValueError("Selected Waler identities cannot be empty")
        if not all(
            math.isfinite(float(coordinate))
            for point in self.waler_intersections
            for coordinate in point
        ):
            raise ValueError("Waler intersections must be finite")
        if len(normalized_waler_handles) != len(self.waler_intersections):
            raise ValueError("Selected Waler identities and intersections must align")
        object.__setattr__(
            self,
            "selected_waler_source_handles",
            normalized_waler_handles,
        )

        if self.status is BlockMemberRecognitionStatus.RECOGNIZED:
            if self.whole_axis is None or _length(*self.whole_axis) <= NUMERIC_EPSILON:
                raise ValueError("Recognized outcome requires a non-zero whole axis")
            if self.accepted_fragment_count <= 0:
                raise ValueError("Recognized outcome requires accepted fragments")
            if self.diagnostic_code:
                raise ValueError("Recognized outcome cannot carry a blocking diagnostic")
            object.__setattr__(self, "whole_axis", _ordered_line(*self.whole_axis))
            return

        if self.whole_axis is not None:
            raise ValueError("Only a recognized outcome can expose a whole axis")
        if self.representative_width or self.accepted_fragment_count:
            raise ValueError("Non-recognized outcomes cannot expose accepted geometry")
        if self.status in {
            BlockMemberRecognitionStatus.FAILED,
            BlockMemberRecognitionStatus.AMBIGUOUS,
        }:
            if not self.diagnostic_code.strip():
                raise ValueError("Terminal outcomes require a diagnostic code")
        elif self.diagnostic_code:
            raise ValueError("Not-applicable outcome cannot carry a blocking diagnostic")

    @classmethod
    def not_applicable(cls) -> "BlockMemberRecognitionOutcome":
        return cls(BlockMemberRecognitionStatus.NOT_APPLICABLE)

    @classmethod
    def recognized(
        cls,
        whole_axis: tuple[Point, Point],
        *,
        representative_width: float,
        confidence: float,
        accepted_fragment_count: int,
        selected_waler_source_handles: tuple[tuple[str, ...], ...] = (),
        waler_intersections: tuple[Point, ...] = (),
    ) -> "BlockMemberRecognitionOutcome":
        return cls(
            BlockMemberRecognitionStatus.RECOGNIZED,
            whole_axis=whole_axis,
            representative_width=representative_width,
            confidence=confidence,
            accepted_fragment_count=accepted_fragment_count,
            selected_waler_source_handles=selected_waler_source_handles,
            waler_intersections=waler_intersections,
        )

    @classmethod
    def failed(
        cls,
        diagnostic_code: str,
        *,
        selected_waler_source_handles: tuple[tuple[str, ...], ...] = (),
        waler_intersections: tuple[Point, ...] = (),
    ) -> "BlockMemberRecognitionOutcome":
        return cls(
            BlockMemberRecognitionStatus.FAILED,
            diagnostic_code=diagnostic_code,
            selected_waler_source_handles=selected_waler_source_handles,
            waler_intersections=waler_intersections,
        )

    @classmethod
    def ambiguous(
        cls,
        diagnostic_code: str,
        *,
        selected_waler_source_handles: tuple[tuple[str, ...], ...] = (),
        waler_intersections: tuple[Point, ...] = (),
    ) -> "BlockMemberRecognitionOutcome":
        return cls(
            BlockMemberRecognitionStatus.AMBIGUOUS,
            diagnostic_code=diagnostic_code,
            selected_waler_source_handles=selected_waler_source_handles,
            waler_intersections=waler_intersections,
        )


@dataclass(frozen=True)
class _FragmentAxis:
    axis: tuple[Point, Point]
    width: float
    kind: FragmentEvidenceKind
    source_segment_ids: tuple[int, ...]

    @property
    def is_strong(self) -> bool:
        return self.kind is not FragmentEvidenceKind.WEAK_LINE

    @property
    def support_length(self) -> float:
        return _length(*self.axis)


@dataclass(frozen=True)
class _SegmentEvidence:
    identifier: int
    segment: tuple[Point, Point]


@dataclass(frozen=True)
class _TopologyMember:
    """One source-connected component envelope inside a root INSERT."""

    axis: tuple[Point, Point]
    width: float
    points: tuple[Point, ...]
    segment_keys: tuple[tuple[Point, Point], ...]
    kind: str


@dataclass(frozen=True)
class _OrientationCluster:
    direction: Point
    fragments: tuple[_FragmentAxis, ...]
    longitudinal_support: float


@dataclass(frozen=True)
class _ComponentCandidate:
    axis: tuple[Point, Point]
    representative_width: float
    fragments: tuple[_FragmentAxis, ...]
    longitudinal_support: float
    evidence_ratio: float
    root_extent_coverage: float
    authority_tier: _CandidateAuthorityTier


@dataclass(frozen=True)
class _WalerSpanSelection:
    references: tuple[WalerSpanReference, WalerSpanReference]
    intersections: tuple[Point, Point]
    longitudinal_stations: tuple[float, float]


@dataclass(frozen=True)
class _ContextualCandidate:
    candidate: _ComponentCandidate
    span: _WalerSpanSelection


def _canonical_unit(segment: tuple[Point, Point]) -> Point | None:
    direction = _unit(*segment)
    if direction is None:
        return None
    if direction[0] < -NUMERIC_EPSILON or (
        abs(direction[0]) <= NUMERIC_EPSILON and direction[1] < 0.0
    ):
        return -direction[0], -direction[1]
    return direction


def _primitive_segments(
    primitive: BlockMemberPrimitive,
) -> tuple[tuple[Point, Point], ...]:
    points = list(primitive.points)
    if len(points) > 2 and _same_point(points[0], points[-1], NUMERIC_EPSILON):
        points.pop()
    pairs = list(zip(points, points[1:]))
    if primitive.closed and len(points) > 2:
        pairs.append((points[-1], points[0]))
    return tuple(
        _ordered_line(start, end)
        for start, end in pairs
        if _distance(start, end) > NUMERIC_EPSILON
    )


def _axis_from_outline_points(
    points: Sequence[Point],
    tolerances: GeometryTolerances,
    *,
    kind: FragmentEvidenceKind,
    source_segment_ids: tuple[int, ...],
) -> _FragmentAxis | None:
    unique_points = tuple(sorted(set(points)))
    if len(unique_points) < 3:
        return None
    center = (
        sum(point[0] for point in unique_points) / len(unique_points),
        sum(point[1] for point in unique_points) / len(unique_points),
    )
    covariance_xx = sum((point[0] - center[0]) ** 2 for point in unique_points)
    covariance_yy = sum((point[1] - center[1]) ** 2 for point in unique_points)
    covariance_xy = sum(
        (point[0] - center[0]) * (point[1] - center[1])
        for point in unique_points
    )
    if covariance_xx + covariance_yy <= NUMERIC_EPSILON:
        return None
    angle = math.atan2(
        2.0 * covariance_xy,
        covariance_xx - covariance_yy,
    ) / 2.0
    direction = _canonical_unit(
        ((0.0, 0.0), (math.cos(angle), math.sin(angle)))
    )
    if direction is None:
        return None
    normal = -direction[1], direction[0]
    along = tuple(_dot(point, direction) for point in unique_points)
    across = tuple(_dot(point, normal) for point in unique_points)
    longitudinal_start, longitudinal_end = min(along), max(along)
    transverse_start, transverse_end = min(across), max(across)
    length = longitudinal_end - longitudinal_start
    width = transverse_end - transverse_start
    if not (
        tolerances.collinear_tolerance_mm
        < width
        <= tolerances.maximum_component_width_mm
    ):
        return None
    if length < tolerances.minimum_component_length_mm:
        return None
    if length / width < tolerances.minimum_slenderness_ratio:
        return None
    transverse_center = (transverse_start + transverse_end) / 2.0
    start = (
        direction[0] * longitudinal_start + normal[0] * transverse_center,
        direction[1] * longitudinal_start + normal[1] * transverse_center,
    )
    end = (
        direction[0] * longitudinal_end + normal[0] * transverse_center,
        direction[1] * longitudinal_end + normal[1] * transverse_center,
    )
    return _FragmentAxis(
        _ordered_line(start, end),
        width,
        kind,
        tuple(sorted(source_segment_ids)),
    )


def _connected_line_contours(
    segments: Sequence[_SegmentEvidence],
    tolerances: GeometryTolerances,
) -> tuple[tuple[tuple[_SegmentEvidence, ...], tuple[Point, ...]], ...]:
    if not segments:
        return ()
    endpoints = tuple(point for item in segments for point in item.segment)
    parents = list(range(len(endpoints)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root == second_root:
            return
        if first_root < second_root:
            parents[second_root] = first_root
        else:
            parents[first_root] = second_root

    for first_index, first_point in enumerate(endpoints):
        for second_index in range(first_index + 1, len(endpoints)):
            if _same_point(
                first_point,
                endpoints[second_index],
                tolerances.endpoint_tolerance_mm,
            ):
                union(first_index, second_index)

    node_segments: dict[int, set[int]] = {}
    segment_nodes: list[tuple[int, int]] = []
    for segment_index in range(len(segments)):
        first_node = find(segment_index * 2)
        second_node = find(segment_index * 2 + 1)
        segment_nodes.append((first_node, second_node))
        node_segments.setdefault(first_node, set()).add(segment_index)
        node_segments.setdefault(second_node, set()).add(segment_index)

    node_points: dict[int, list[Point]] = {}
    for endpoint_index, point in enumerate(endpoints):
        node_points.setdefault(find(endpoint_index), []).append(point)
    canonical_points = {
        node: (
            math.fsum(sorted(point[0] for point in points)) / len(points),
            math.fsum(sorted(point[1] for point in points)) / len(points),
        )
        for node, points in node_points.items()
    }

    unseen = set(range(len(segments)))
    contours = []
    while unseen:
        seed = min(unseen)
        component = {seed}
        queue = [seed]
        unseen.remove(seed)
        while queue:
            current = queue.pop()
            for node in segment_nodes[current]:
                for neighbor in node_segments[node]:
                    if neighbor not in unseen:
                        continue
                    unseen.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        component_node_pairs = tuple(
            tuple(sorted(segment_nodes[index])) for index in sorted(component)
        )
        if (
            any(first == second for first, second in component_node_pairs)
            or len(set(component_node_pairs)) != len(component_node_pairs)
        ):
            continue

        # Remove dangling detail branches while preserving independently
        # verifiable closed boundaries.  Chords or shared-cycle junctions stay
        # invalid because their remaining nodes do not have degree two.
        active_segments = set(component)
        while True:
            active_nodes = {
                node
                for index in active_segments
                for node in segment_nodes[index]
            }
            leaf_nodes = {
                node
                for node in active_nodes
                if len(node_segments[node].intersection(active_segments)) < 2
            }
            if not leaf_nodes:
                break
            removable = {
                index
                for node in leaf_nodes
                for index in node_segments[node].intersection(active_segments)
            }
            if not removable:
                break
            active_segments.difference_update(removable)
        if not active_segments:
            continue

        remaining = set(active_segments)
        while remaining:
            cycle_seed = min(remaining)
            cycle_component = {cycle_seed}
            cycle_queue = [cycle_seed]
            remaining.remove(cycle_seed)
            while cycle_queue:
                current = cycle_queue.pop()
                for node in segment_nodes[current]:
                    for neighbor in node_segments[node].intersection(remaining):
                        remaining.remove(neighbor)
                        cycle_component.add(neighbor)
                        cycle_queue.append(neighbor)
            cycle_nodes = {
                node
                for index in cycle_component
                for node in segment_nodes[index]
            }
            if len(cycle_nodes) < 3 or any(
                len(node_segments[node].intersection(cycle_component)) != 2
                for node in cycle_nodes
            ):
                continue
            component_segments = tuple(
                segments[index] for index in sorted(cycle_component)
            )
            component_points = tuple(
                canonical_points[node] for node in sorted(cycle_nodes)
            )
            contours.append((component_segments, component_points))
    return tuple(contours)


def _canonical_segment_key(
    segment: tuple[Point, Point],
) -> tuple[Point, Point]:
    """Return a direction-independent, runtime-only segment identity."""

    return _ordered_line(*segment)


def _topology_member_from_contour(
    contour_segments: Sequence[_SegmentEvidence],
    contour_points: Sequence[Point],
    tolerances: GeometryTolerances,
    *,
    kind: str,
) -> _TopologyMember | None:
    segment_keys = tuple(
        sorted(_canonical_segment_key(item.segment) for item in contour_segments)
    )
    if len(segment_keys) < 3 or len(set(segment_keys)) != len(segment_keys):
        return None
    fragment = _axis_from_outline_points(
        contour_points,
        tolerances,
        kind=FragmentEvidenceKind.OUTLINE,
        source_segment_ids=(),
    )
    if fragment is None:
        return None
    return _TopologyMember(
        fragment.axis,
        fragment.width,
        tuple(sorted(set(contour_points))),
        segment_keys,
        kind,
    )


def _extract_topology_members(
    primitives: Sequence[BlockMemberPrimitive],
    tolerances: GeometryTolerances,
) -> tuple[_TopologyMember, ...]:
    """Extract closed source topology without unrestricted rail pairing."""

    members: list[_TopologyMember] = []
    open_segments: list[_SegmentEvidence] = []
    segment_identifier = 0

    for primitive in primitives:
        segments = _primitive_segments(primitive)
        evidence = tuple(
            _SegmentEvidence(segment_identifier + index, segment)
            for index, segment in enumerate(segments)
        )
        segment_identifier += len(segments)
        if not primitive.closed:
            open_segments.extend(evidence)
            continue
        contours = _connected_line_contours(evidence, tolerances)
        if len(contours) != 1 or len(contours[0][0]) != len(evidence):
            continue
        member = _topology_member_from_contour(
            contours[0][0],
            contours[0][1],
            tolerances,
            kind="closed_outline",
        )
        if member is not None:
            members.append(member)

    for contour_segments, contour_points in _connected_line_contours(
        open_segments,
        tolerances,
    ):
        member = _topology_member_from_contour(
            contour_segments,
            contour_points,
            tolerances,
            kind="connected_contour",
        )
        if member is not None:
            members.append(member)

    deduplicated: dict[
        tuple[tuple[Point, Point], ...],
        _TopologyMember,
    ] = {}
    for member in sorted(
        members,
        key=lambda item: (
            item.axis,
            item.width,
            item.kind,
            item.segment_keys,
        ),
    ):
        deduplicated.setdefault(member.segment_keys, member)
    return tuple(deduplicated.values())


def _paired_rail_fragment(
    first: _SegmentEvidence,
    second: _SegmentEvidence,
    tolerances: GeometryTolerances,
) -> _FragmentAxis | None:
    if (
        _angle_difference_deg(first.segment, second.segment)
        > tolerances.parallel_angle_tolerance_deg
    ):
        return None
    if (
        _projection_overlap_ratio(first.segment, second.segment)
        < tolerances.minimum_projection_overlap_ratio
    ):
        return None
    width = _line_separation(first.segment, second.segment)
    if not (
        tolerances.collinear_tolerance_mm
        < width
        <= tolerances.maximum_component_width_mm
    ):
        return None
    direction = _canonical_unit(first.segment)
    if direction is None:
        return None
    normal = -direction[1], direction[0]
    first_range = sorted(_dot(point, direction) for point in first.segment)
    second_range = sorted(_dot(point, direction) for point in second.segment)
    longitudinal_start = max(first_range[0], second_range[0])
    longitudinal_end = min(first_range[1], second_range[1])
    length = longitudinal_end - longitudinal_start
    if length < tolerances.minimum_component_length_mm:
        return None
    if length / width < tolerances.minimum_slenderness_ratio:
        return None
    transverse_center = (
        _dot(_midpoint(*first.segment), normal)
        + _dot(_midpoint(*second.segment), normal)
    ) / 2.0
    axis = _ordered_line(
        (
            direction[0] * longitudinal_start + normal[0] * transverse_center,
            direction[1] * longitudinal_start + normal[1] * transverse_center,
        ),
        (
            direction[0] * longitudinal_end + normal[0] * transverse_center,
            direction[1] * longitudinal_end + normal[1] * transverse_center,
        ),
    )
    return _FragmentAxis(
        axis,
        width,
        FragmentEvidenceKind.RAIL_PAIR,
        tuple(sorted((first.identifier, second.identifier))),
    )


def _fragments_equivalent(
    first: _FragmentAxis,
    second: _FragmentAxis,
    tolerances: GeometryTolerances,
) -> bool:
    if (
        _angle_difference_deg(first.axis, second.axis)
        > tolerances.parallel_angle_tolerance_deg
    ):
        return False
    if abs(first.width - second.width) > tolerances.width_tolerance_mm:
        return False
    direct = max(
        _distance(first.axis[0], second.axis[0]),
        _distance(first.axis[1], second.axis[1]),
    )
    reverse = max(
        _distance(first.axis[0], second.axis[1]),
        _distance(first.axis[1], second.axis[0]),
    )
    if min(direct, reverse) <= tolerances.duplicate_tolerance_mm:
        return True
    return (
        _line_separation(first.axis, second.axis)
        <= tolerances.duplicate_tolerance_mm
        and _projection_overlap_ratio(first.axis, second.axis)
        >= tolerances.minimum_projection_overlap_ratio
    )


def _extract_fragment_axes(
    primitives: Sequence[BlockMemberPrimitive],
    tolerances: GeometryTolerances,
) -> tuple[_FragmentAxis, ...]:
    fragments: list[_FragmentAxis] = []
    open_segments: list[_SegmentEvidence] = []
    segment_identifier = 0

    for primitive in primitives:
        segments = _primitive_segments(primitive)
        if primitive.closed:
            fragment = _axis_from_outline_points(
                primitive.points,
                tolerances,
                kind=FragmentEvidenceKind.OUTLINE,
                source_segment_ids=tuple(
                    range(segment_identifier, segment_identifier + len(segments))
                ),
            )
            if fragment is not None:
                fragments.append(fragment)
            segment_identifier += len(segments)
            continue
        for segment in segments:
            open_segments.append(_SegmentEvidence(segment_identifier, segment))
            segment_identifier += 1

    consumed_segment_ids: set[int] = set()
    for contour_segments, contour_points in _connected_line_contours(
        open_segments,
        tolerances,
    ):
        fragment = _axis_from_outline_points(
            contour_points,
            tolerances,
            kind=FragmentEvidenceKind.OUTLINE,
            source_segment_ids=tuple(item.identifier for item in contour_segments),
        )
        if fragment is None:
            continue
        fragments.append(fragment)
        consumed_segment_ids.update(fragment.source_segment_ids)

    remaining = tuple(
        item for item in open_segments if item.identifier not in consumed_segment_ids
    )
    pair_options: list[_FragmentAxis] = []
    for first_index, first in enumerate(remaining):
        for second in remaining[first_index + 1 :]:
            fragment = _paired_rail_fragment(first, second, tolerances)
            if fragment is not None:
                pair_options.append(fragment)
    pair_options.sort(
        key=lambda item: (
            -item.support_length,
            item.axis,
            item.width,
            item.source_segment_ids,
        )
    )
    paired_segment_ids: set[int] = set()
    for fragment in pair_options:
        if paired_segment_ids.intersection(fragment.source_segment_ids):
            continue
        fragments.append(fragment)
        paired_segment_ids.update(fragment.source_segment_ids)

    for item in remaining:
        if item.identifier in paired_segment_ids:
            continue
        fragments.append(
            _FragmentAxis(
                _ordered_line(*item.segment),
                0.0,
                FragmentEvidenceKind.WEAK_LINE,
                (item.identifier,),
            )
        )

    deduplicated: list[_FragmentAxis] = []
    for fragment in sorted(
        fragments,
        key=lambda item: (
            item.kind.value,
            item.axis,
            item.width,
            item.source_segment_ids,
        ),
    ):
        if any(
            _fragments_equivalent(fragment, existing, tolerances)
            for existing in deduplicated
        ):
            continue
        deduplicated.append(fragment)
    return tuple(deduplicated)


def _merged_interval_length(
    intervals: Sequence[tuple[float, float]],
) -> float:
    ordered = sorted(
        (min(start, end), max(start, end))
        for start, end in intervals
        if abs(end - start) > NUMERIC_EPSILON
    )
    if not ordered:
        return 0.0
    total = 0.0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end + NUMERIC_EPSILON:
            current_end = max(current_end, end)
            continue
        total += current_end - current_start
        current_start, current_end = start, end
    return total + current_end - current_start


def _mean_undirected_direction(fragments: Sequence[_FragmentAxis]) -> Point:
    weighted_cosine = 0.0
    weighted_sine = 0.0
    for fragment in fragments:
        direction = _canonical_unit(fragment.axis)
        if direction is None:
            continue
        angle = math.atan2(direction[1], direction[0])
        weight = fragment.support_length
        weighted_cosine += math.cos(2.0 * angle) * weight
        weighted_sine += math.sin(2.0 * angle) * weight
    angle = math.atan2(weighted_sine, weighted_cosine) / 2.0
    direction = _canonical_unit(
        ((0.0, 0.0), (math.cos(angle), math.sin(angle)))
    )
    if direction is None:
        raise ValueError("Orientation cluster has no non-zero fragment axis")
    return direction


def _build_orientation_clusters(
    fragments: Sequence[_FragmentAxis],
    tolerances: GeometryTolerances,
) -> tuple[_OrientationCluster, ...]:
    strong_fragments = tuple(
        sorted(
            (fragment for fragment in fragments if fragment.is_strong),
            key=lambda item: (item.axis, item.width, item.kind.value),
        )
    )
    unseen = set(range(len(strong_fragments)))
    components: list[tuple[_FragmentAxis, ...]] = []
    while unseen:
        seed = min(unseen)
        unseen.remove(seed)
        component = {seed}
        queue = [seed]
        while queue:
            current = queue.pop()
            related = [
                candidate
                for candidate in sorted(unseen)
                if _angle_difference_deg(
                    strong_fragments[current].axis,
                    strong_fragments[candidate].axis,
                )
                <= tolerances.parallel_angle_tolerance_deg
            ]
            for candidate in related:
                unseen.remove(candidate)
                component.add(candidate)
                queue.append(candidate)
        components.append(tuple(strong_fragments[index] for index in sorted(component)))

    clusters: list[_OrientationCluster] = []
    for component in components:
        direction = _mean_undirected_direction(component)
        intervals = tuple(
            tuple(sorted(_dot(point, direction) for point in fragment.axis))
            for fragment in component
        )
        clusters.append(
            _OrientationCluster(
                direction,
                component,
                _merged_interval_length(intervals),
            )
        )
    clusters.sort(
        key=lambda item: (
            -item.longitudinal_support,
            item.direction,
            tuple(fragment.axis for fragment in item.fragments),
        )
    )
    return tuple(clusters)


def _axes_equivalent(
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
        and _projection_overlap_ratio(first, second)
        >= tolerances.minimum_projection_overlap_ratio
    )


def _component_candidates(
    source: BlockMemberRecognitionInput,
    fragments: Sequence[_FragmentAxis],
    tolerances: GeometryTolerances,
) -> tuple[_ComponentCandidate, ...]:
    orientation_clusters = _build_orientation_clusters(fragments, tolerances)
    total_longitudinal_support = sum(
        cluster.longitudinal_support for cluster in orientation_clusters
    )
    if total_longitudinal_support <= NUMERIC_EPSILON:
        return ()

    weak_fragments = tuple(fragment for fragment in fragments if not fragment.is_strong)
    root_points = tuple(
        point for primitive in source.primitives for point in primitive.points
    )
    candidates: list[_ComponentCandidate] = []
    for orientation in orientation_clusters:
        direction = orientation.direction
        normal = -direction[1], direction[0]
        transverse_centers = tuple(
            _dot(_midpoint(*fragment.axis), normal)
            for fragment in orientation.fragments
        )
        unseen = set(range(len(orientation.fragments)))
        components: list[tuple[int, ...]] = []
        while unseen:
            seed = min(unseen)
            unseen.remove(seed)
            component = {seed}
            queue = [seed]
            while queue:
                current = queue.pop()
                related = [
                    candidate
                    for candidate in sorted(unseen)
                    if (
                        abs(
                            transverse_centers[current]
                            - transverse_centers[candidate]
                        )
                        <= tolerances.collinear_tolerance_mm
                        and abs(
                            orientation.fragments[current].width
                            - orientation.fragments[candidate].width
                        )
                        <= tolerances.width_tolerance_mm
                    )
                ]
                for candidate in related:
                    unseen.remove(candidate)
                    component.add(candidate)
                    queue.append(candidate)
            components.append(tuple(sorted(component)))

        for component_indices in components:
            component_fragments = tuple(
                orientation.fragments[index] for index in component_indices
            )
            representative_width = median(
                fragment.width for fragment in component_fragments
            )
            if not (
                tolerances.collinear_tolerance_mm
                < representative_width
                <= tolerances.maximum_component_width_mm
            ):
                continue
            transverse_center = median(
                transverse_centers[index] for index in component_indices
            )
            intervals = [
                tuple(sorted(_dot(point, direction) for point in fragment.axis))
                for fragment in component_fragments
            ]
            for weak in weak_fragments:
                if (
                    _angle_difference_deg(weak.axis, component_fragments[0].axis)
                    > tolerances.parallel_angle_tolerance_deg
                ):
                    continue
                weak_center = _dot(_midpoint(*weak.axis), normal)
                if (
                    abs(weak_center - transverse_center)
                    > tolerances.collinear_tolerance_mm
                ):
                    continue
                intervals.append(
                    tuple(sorted(_dot(point, direction) for point in weak.axis))
                )
            longitudinal_start = min(interval[0] for interval in intervals)
            longitudinal_end = max(interval[1] for interval in intervals)
            supported_extent = longitudinal_end - longitudinal_start
            if supported_extent < tolerances.minimum_component_length_mm:
                continue
            if (
                supported_extent / representative_width
                < tolerances.minimum_slenderness_ratio
            ):
                continue
            component_support = _merged_interval_length(
                tuple(
                    tuple(
                        sorted(_dot(point, direction) for point in fragment.axis)
                    )
                    for fragment in component_fragments
                )
            )
            evidence_ratio = component_support / total_longitudinal_support
            root_projection = tuple(_dot(point, direction) for point in root_points)
            root_extent = (
                max(root_projection) - min(root_projection)
                if root_projection
                else 0.0
            )
            root_extent_coverage = (
                min(1.0, supported_extent / root_extent)
                if root_extent > NUMERIC_EPSILON
                else 0.0
            )
            axis = _ordered_line(
                (
                    direction[0] * longitudinal_start
                    + normal[0] * transverse_center,
                    direction[1] * longitudinal_start
                    + normal[1] * transverse_center,
                ),
                (
                    direction[0] * longitudinal_end
                    + normal[0] * transverse_center,
                    direction[1] * longitudinal_end
                    + normal[1] * transverse_center,
                ),
            )
            candidates.append(
                _ComponentCandidate(
                    axis,
                    representative_width,
                    component_fragments,
                    component_support,
                    evidence_ratio,
                    root_extent_coverage,
                    _CandidateAuthorityTier.LOCAL_RAIL_PAIR,
                )
            )
    candidates.sort(
        key=lambda item: (
            -item.evidence_ratio,
            -item.root_extent_coverage,
            item.axis,
            item.representative_width,
        )
    )
    return tuple(candidates)


def _legacy_axis_covers_source(
    axis: tuple[Point, Point],
    source: BlockMemberRecognitionInput,
    tolerances: GeometryTolerances,
) -> bool:
    direction = _canonical_unit(axis)
    if direction is None:
        return False
    normal = -direction[1], direction[0]
    root_points = tuple(
        point for primitive in source.primitives for point in primitive.points
    )
    if not root_points:
        return False
    root_along = tuple(_dot(point, direction) for point in root_points)
    root_start, root_end = min(root_along), max(root_along)
    root_extent = root_end - root_start
    if root_extent <= NUMERIC_EPSILON:
        return False
    axis_range = sorted(_dot(point, direction) for point in axis)
    overlap = max(
        0.0,
        min(axis_range[1], root_end) - max(axis_range[0], root_start),
    )
    if overlap / root_extent < tolerances.minimum_projection_overlap_ratio:
        return False
    root_across = tuple(_dot(point, normal) for point in root_points)
    return (
        max(root_across) - min(root_across)
        <= tolerances.maximum_component_width_mm + tolerances.width_tolerance_mm
    )


def _has_full_span_legacy_evidence(
    source: BlockMemberRecognitionInput,
    tolerances: GeometryTolerances,
) -> bool:
    for primitive in source.primitives:
        segments = _primitive_segments(primitive)
        if not segments:
            continue
        if primitive.entity_type == "MLINE":
            axis = _ordered_line(primitive.points[0], primitive.points[-1])
            if _legacy_axis_covers_source(axis, source, tolerances):
                return True
        if not primitive.closed and len(segments) == 1:
            if _legacy_axis_covers_source(segments[0], source, tolerances):
                return True
        if primitive.closed:
            fragment = _axis_from_outline_points(
                primitive.points,
                tolerances,
                kind=FragmentEvidenceKind.OUTLINE,
                source_segment_ids=(),
            )
            if fragment is not None and _legacy_axis_covers_source(
                fragment.axis,
                source,
                tolerances,
            ):
                return True

    fragments = _extract_fragment_axes(source.primitives, tolerances)
    strong_fragments = tuple(fragment for fragment in fragments if fragment.is_strong)
    if len(strong_fragments) == 1 and _legacy_axis_covers_source(
        strong_fragments[0].axis,
        source,
        tolerances,
    ):
        return True
    return False


def _topology_axis_groups(
    members: Sequence[_TopologyMember],
    tolerances: GeometryTolerances,
) -> tuple[tuple[_TopologyMember, ...], ...]:
    ordered_members = tuple(
        sorted(
            members,
            key=lambda item: (item.axis, item.width, item.segment_keys),
        )
    )
    mutable_groups: list[list[_TopologyMember]] = []
    for member in ordered_members:
        matching_group = next(
            (
                group
                for group in mutable_groups
                if all(
                    _axes_equivalent(
                        member.axis,
                        existing.axis,
                        tolerances,
                    )
                    for existing in group
                )
            ),
            None,
        )
        if matching_group is None:
            mutable_groups.append([member])
        else:
            matching_group.append(member)
    groups = [tuple(group) for group in mutable_groups]
    groups.sort(
        key=lambda group: (
            group[0].axis,
            group[0].width,
            tuple(member.segment_keys for member in group),
        )
    )
    return tuple(groups)


def _consolidated_topology_axis(
    members: Sequence[_TopologyMember],
) -> tuple[Point, Point]:
    fragments = tuple(
        _FragmentAxis(
            member.axis,
            member.width,
            FragmentEvidenceKind.OUTLINE,
            (),
        )
        for member in members
    )
    direction = _mean_undirected_direction(fragments)
    normal = -direction[1], direction[0]
    ranges = tuple(
        tuple(sorted(_dot(point, direction) for point in member.axis))
        for member in members
    )
    longitudinal_start = min(item[0] for item in ranges)
    longitudinal_end = max(item[1] for item in ranges)
    transverse_center = median(
        _dot(_midpoint(*member.axis), normal) for member in members
    )
    return _ordered_line(
        (
            direction[0] * longitudinal_start + normal[0] * transverse_center,
            direction[1] * longitudinal_start + normal[1] * transverse_center,
        ),
        (
            direction[0] * longitudinal_end + normal[0] * transverse_center,
            direction[1] * longitudinal_end + normal[1] * transverse_center,
        ),
    )


def _topology_member_contains(
    outer: _TopologyMember,
    inner: _TopologyMember,
    tolerances: GeometryTolerances,
) -> bool:
    direction = _canonical_unit(outer.axis)
    if direction is None:
        return False
    normal = -direction[1], direction[0]
    outer_along = tuple(_dot(point, direction) for point in outer.points)
    inner_along = tuple(_dot(point, direction) for point in inner.points)
    outer_across = tuple(_dot(point, normal) for point in outer.points)
    inner_across = tuple(_dot(point, normal) for point in inner.points)
    return (
        min(outer_along)
        <= min(inner_along) + tolerances.endpoint_tolerance_mm
        and max(outer_along)
        >= max(inner_along) - tolerances.endpoint_tolerance_mm
        and min(outer_across) <= min(inner_across) + NUMERIC_EPSILON
        and max(outer_across) >= max(inner_across) - NUMERIC_EPSILON
    )


def _unique_component_envelope_width(
    members: Sequence[_TopologyMember],
    tolerances: GeometryTolerances,
) -> float:
    containers = tuple(
        member
        for member in members
        if all(
            _topology_member_contains(member, other, tolerances)
            for other in members
        )
    )
    return containers[0].width if len(containers) == 1 else 0.0


def _has_risky_extra_longitudinal_evidence(
    source: BlockMemberRecognitionInput,
    members: Sequence[_TopologyMember],
    tolerances: GeometryTolerances,
) -> bool:
    consumed_segment_keys = {
        key for member in members for key in member.segment_keys
    }
    for primitive in source.primitives:
        for segment in _primitive_segments(primitive):
            if _canonical_segment_key(segment) in consumed_segment_keys:
                continue
            for member in members:
                if (
                    _angle_difference_deg(segment, member.axis)
                    <= tolerances.parallel_angle_tolerance_deg
                    and _projection_overlap_ratio(segment, member.axis)
                    >= tolerances.minimum_projection_overlap_ratio
                    and _line_separation(segment, member.axis)
                    <= tolerances.maximum_component_width_mm
                ):
                    return True
    return False


def _recognize_topology_guarded_member(
    source: BlockMemberRecognitionInput,
    tolerances: GeometryTolerances,
) -> BlockMemberRecognitionOutcome | None:
    members = _extract_topology_members(source.primitives, tolerances)
    full_span_members = tuple(
        member
        for member in members
        if _legacy_axis_covers_source(member.axis, source, tolerances)
    )
    if not full_span_members:
        return None

    groups = _topology_axis_groups(full_span_members, tolerances)
    if len(groups) > 1:
        return BlockMemberRecognitionOutcome.ambiguous(
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES"
        )

    group = groups[0]
    if len(group) == 1 and not _has_risky_extra_longitudinal_evidence(
        source,
        members,
        tolerances,
    ):
        return None

    return BlockMemberRecognitionOutcome.recognized(
        _consolidated_topology_axis(group),
        representative_width=_unique_component_envelope_width(
            group,
            tolerances,
        ),
        confidence=1.0,
        accepted_fragment_count=len(group),
    )


def _consolidated_brace_candidate_outcome(
    candidates: Sequence[_ComponentCandidate],
    tolerances: GeometryTolerances,
) -> BlockMemberRecognitionOutcome | None:
    """Consolidate connected transverse rail bands for one fragmented Brace."""

    if len(candidates) < 2:
        return None
    direction = _canonical_unit(candidates[0].axis)
    if direction is None:
        return None
    if any(
        _angle_difference_deg(candidate.axis, candidates[0].axis)
        > tolerances.parallel_angle_tolerance_deg
        for candidate in candidates[1:]
    ):
        return None
    if any(
        _projection_overlap_ratio(candidate.axis, candidates[0].axis)
        < tolerances.minimum_projection_overlap_ratio
        for candidate in candidates[1:]
    ):
        return None

    normal = -direction[1], direction[0]
    transverse_intervals = []
    for candidate in candidates:
        width = float(candidate.representative_width)
        if not (
            tolerances.collinear_tolerance_mm
            < width
            <= tolerances.maximum_component_width_mm
        ):
            return None
        center = _dot(_midpoint(*candidate.axis), normal)
        transverse_intervals.append((center - width / 2.0, center + width / 2.0))
    transverse_intervals.sort()
    transverse_start, transverse_end = transverse_intervals[0]
    for start, end in transverse_intervals[1:]:
        if start > transverse_end + tolerances.endpoint_tolerance_mm:
            return None
        transverse_end = max(transverse_end, end)
    combined_width = transverse_end - transverse_start
    if not (
        tolerances.collinear_tolerance_mm
        < combined_width
        <= tolerances.maximum_component_width_mm
    ):
        return None

    longitudinal_ranges = tuple(
        tuple(sorted(_dot(point, direction) for point in candidate.axis))
        for candidate in candidates
    )
    longitudinal_start = min(item[0] for item in longitudinal_ranges)
    longitudinal_end = max(item[1] for item in longitudinal_ranges)
    supported_extent = longitudinal_end - longitudinal_start
    if supported_extent < tolerances.minimum_component_length_mm:
        return None
    if supported_extent / combined_width < tolerances.minimum_slenderness_ratio:
        return None

    transverse_center = (transverse_start + transverse_end) / 2.0
    axis = _ordered_line(
        (
            direction[0] * longitudinal_start + normal[0] * transverse_center,
            direction[1] * longitudinal_start + normal[1] * transverse_center,
        ),
        (
            direction[0] * longitudinal_end + normal[0] * transverse_center,
            direction[1] * longitudinal_end + normal[1] * transverse_center,
        ),
    )
    return BlockMemberRecognitionOutcome.recognized(
        axis,
        representative_width=combined_width,
        confidence=max(candidate.evidence_ratio for candidate in candidates),
        accepted_fragment_count=sum(
            len(candidate.fragments) for candidate in candidates
        ),
    )


def _longitudinal_bands(
    source: BlockMemberRecognitionInput,
    direction: Point,
    tolerances: GeometryTolerances,
) -> tuple[tuple[float, tuple[tuple[float, float], ...], float], ...]:
    """Group eligible same-root longitudinal segments by transverse station."""

    normal = -direction[1], direction[0]
    evidence: list[tuple[float, tuple[float, float]]] = []
    for primitive in source.primitives:
        for segment in _primitive_segments(primitive):
            if _length(*segment) < tolerances.minimum_component_length_mm:
                continue
            if (
                _angle_difference_deg(segment, ((0.0, 0.0), direction))
                > tolerances.parallel_angle_tolerance_deg
            ):
                continue
            station = _dot(_midpoint(*segment), normal)
            interval = tuple(sorted(_dot(point, direction) for point in segment))
            evidence.append((station, interval))
    if not evidence:
        return ()

    groups: list[list[tuple[float, tuple[float, float]]]] = []
    for item in sorted(evidence, key=lambda value: (value[0], value[1])):
        matching = next(
            (
                group
                for group in groups
                if abs(item[0] - median(entry[0] for entry in group))
                <= tolerances.collinear_tolerance_mm
            ),
            None,
        )
        if matching is None:
            groups.append([item])
        else:
            matching.append(item)

    return tuple(
        (
            median(item[0] for item in group),
            tuple(item[1] for item in group),
            _merged_interval_length(tuple(item[1] for item in group)),
        )
        for group in groups
    )


def _whole_root_envelope_candidates(
    source: BlockMemberRecognitionInput,
    tolerances: GeometryTolerances,
) -> tuple[_ComponentCandidate, ...]:
    """Build whole-root axes without greedily pairing only two local rails."""

    segment_fragments = tuple(
        _FragmentAxis(
            _ordered_line(*segment),
            0.0,
            FragmentEvidenceKind.WEAK_LINE,
            (identifier,),
        )
        for identifier, segment in enumerate(
            segment
            for primitive in source.primitives
            for segment in _primitive_segments(primitive)
            if _length(*segment) >= tolerances.minimum_component_length_mm
        )
    )
    unseen = set(range(len(segment_fragments)))
    orientation_groups: list[tuple[_FragmentAxis, ...]] = []
    while unseen:
        seed = min(unseen)
        unseen.remove(seed)
        component = {seed}
        queue = [seed]
        while queue:
            current = queue.pop()
            related = [
                candidate
                for candidate in sorted(unseen)
                if _angle_difference_deg(
                    segment_fragments[current].axis,
                    segment_fragments[candidate].axis,
                )
                <= tolerances.parallel_angle_tolerance_deg
            ]
            for candidate in related:
                unseen.remove(candidate)
                component.add(candidate)
                queue.append(candidate)
        orientation_groups.append(
            tuple(segment_fragments[index] for index in sorted(component))
        )

    root_points = tuple(
        point for primitive in source.primitives for point in primitive.points
    )
    candidates: list[_ComponentCandidate] = []
    for orientation in orientation_groups:
        direction = _mean_undirected_direction(orientation)
        bands = _longitudinal_bands(source, direction, tolerances)
        if len(bands) < 2:
            continue
        root_projection = tuple(_dot(point, direction) for point in root_points)
        if not root_projection:
            continue
        root_start, root_end = min(root_projection), max(root_projection)
        root_extent = root_end - root_start
        if root_extent < tolerances.minimum_component_length_mm:
            continue
        major_bands = tuple(
            band
            for band in bands
            if band[2] / root_extent
            >= tolerances.bim_minimum_longitudinal_evidence_ratio
        )
        if len(major_bands) < 2:
            continue
        ordered_bands = tuple(sorted(major_bands, key=lambda band: band[0]))
        compatible_windows: list[tuple[tuple[float, tuple[tuple[float, float], ...], float], ...]] = []
        for start_index in range(len(ordered_bands) - 1):
            end_index = start_index + 1
            while (
                end_index + 1 < len(ordered_bands)
                and ordered_bands[end_index + 1][0]
                - ordered_bands[start_index][0]
                <= tolerances.maximum_component_width_mm
            ):
                end_index += 1
            window = ordered_bands[start_index : end_index + 1]
            width = window[-1][0] - window[0][0]
            if (
                tolerances.collinear_tolerance_mm
                < width
                <= tolerances.maximum_component_width_mm
            ):
                compatible_windows.append(window)

        normal = -direction[1], direction[0]
        for window in compatible_windows:
            transverse_start, transverse_end = window[0][0], window[-1][0]
            width = transverse_end - transverse_start
            transverse_center = (transverse_start + transverse_end) / 2.0
            intervals = tuple(
                interval for band in window for interval in band[1]
            )
            longitudinal_start = min(interval[0] for interval in intervals)
            longitudinal_end = max(interval[1] for interval in intervals)
            supported_extent = longitudinal_end - longitudinal_start
            if supported_extent / width < tolerances.minimum_slenderness_ratio:
                continue
            coverage = min(
                1.0,
                _merged_interval_length(intervals) / root_extent,
            )
            pseudo_fragments = tuple(
                _FragmentAxis(
                    _ordered_line(
                        (
                            direction[0]
                            * min(interval[0] for interval in band[1])
                            + normal[0] * band[0],
                            direction[1]
                            * min(interval[0] for interval in band[1])
                            + normal[1] * band[0],
                        ),
                        (
                            direction[0]
                            * max(interval[1] for interval in band[1])
                            + normal[0] * band[0],
                            direction[1]
                            * max(interval[1] for interval in band[1])
                            + normal[1] * band[0],
                        ),
                    ),
                    0.0,
                    FragmentEvidenceKind.WEAK_LINE,
                    (),
                )
                for band in window
            )
            candidates.append(
                _ComponentCandidate(
                    _ordered_line(
                        (
                            direction[0] * longitudinal_start
                            + normal[0] * transverse_center,
                            direction[1] * longitudinal_start
                            + normal[1] * transverse_center,
                        ),
                        (
                            direction[0] * longitudinal_end
                            + normal[0] * transverse_center,
                            direction[1] * longitudinal_end
                            + normal[1] * transverse_center,
                        ),
                    ),
                    width,
                    pseudo_fragments,
                    sum(band[2] for band in window),
                    1.0,
                    coverage,
                    _CandidateAuthorityTier.WHOLE_ROOT_ENVELOPE,
                )
            )
    candidates.sort(
        key=lambda item: (
            -item.evidence_ratio,
            -item.root_extent_coverage,
            item.axis,
            -item.representative_width,
        )
    )
    return tuple(candidates)


def _select_waler_span(
    source: BlockMemberRecognitionInput,
    candidate: _ComponentCandidate,
    references: Sequence[WalerSpanReference],
    tolerances: GeometryTolerances,
) -> tuple[
    _WalerSpanSelection | None,
    str,
    tuple[tuple[WalerSpanReference, Point], ...],
]:
    direction = _canonical_unit(candidate.axis)
    if direction is None:
        return None, "BIM_BLOCK_WALER_SPAN_INCOMPLETE", ()
    root_points = tuple(
        point for primitive in source.primitives for point in primitive.points
    )
    if not root_points:
        return None, "BIM_BLOCK_WALER_SPAN_INCOMPLETE", ()
    source_stations = tuple(_dot(point, direction) for point in root_points)
    source_start, source_end = min(source_stations), max(source_stations)
    intersections: list[tuple[WalerSpanReference, Point, float]] = []
    for reference in references:
        point = _line_segment_intersection_point(
            candidate.axis,
            reference.reference_segment,
            tolerances.endpoint_tolerance_mm,
        )
        if point is None:
            continue
        intersections.append((reference, point, _dot(point, direction)))

    negative = sorted(
        (
            item
            for item in intersections
            if item[2] <= source_start + tolerances.endpoint_tolerance_mm
        ),
        key=lambda item: (-item[2], item[0].source_handles),
    )
    positive = sorted(
        (
            item
            for item in intersections
            if item[2] >= source_end - tolerances.endpoint_tolerance_mm
        ),
        key=lambda item: (item[2], item[0].source_handles),
    )
    observed = tuple(
        (item[0], item[1])
        for item in (
            *((negative[:1]) if negative else ()),
            *((positive[:1]) if positive else ()),
        )
    )
    if not negative or not positive:
        return None, "BIM_BLOCK_WALER_SPAN_INCOMPLETE", observed
    ambiguity_tolerance = tolerances.ambiguous_connection_delta_mm
    if (
        len(negative) > 1
        and abs(negative[0][2] - negative[1][2]) <= ambiguity_tolerance
    ) or (
        len(positive) > 1
        and abs(positive[0][2] - positive[1][2]) <= ambiguity_tolerance
    ):
        ambiguous_items = tuple(
            (item[0], item[1])
            for item in (*negative[:2], *positive[:2])
        )
        return None, "BIM_BLOCK_WALER_SPAN_AMBIGUOUS", ambiguous_items

    start_item, end_item = negative[0], positive[0]
    if start_item[0].source_handles == end_item[0].source_handles:
        return None, "BIM_BLOCK_WALER_SPAN_INCOMPLETE", observed
    return (
        _WalerSpanSelection(
            (start_item[0], end_item[0]),
            (start_item[1], end_item[1]),
            (start_item[2], end_item[2]),
        ),
        "",
        (),
    )


def _whole_root_completeness(
    source: BlockMemberRecognitionInput,
    candidate: _ComponentCandidate,
    span: _WalerSpanSelection,
    tolerances: GeometryTolerances,
    *,
    preserve_transverse_axis: bool = False,
) -> tuple[float, float] | None:
    direction = _canonical_unit(candidate.axis)
    if direction is None:
        return None
    bands = _longitudinal_bands(source, direction, tolerances)
    if len(bands) < 2:
        return None
    span_start, span_end = sorted(span.longitudinal_stations)
    span_length = span_end - span_start
    if span_length < tolerances.minimum_component_length_mm:
        return None
    normal = -direction[1], direction[0]
    candidate_center = _dot(_midpoint(*candidate.axis), normal)
    visible_bands = tuple(
        band
        for band in bands
        if abs(band[0] - candidate_center)
        <= tolerances.maximum_component_width_mm / 2.0
        + tolerances.width_tolerance_mm
    )
    major_bands = tuple(
        band
        for band in visible_bands
        if band[2] / span_length
        >= tolerances.bim_minimum_longitudinal_evidence_ratio
    )
    if len(major_bands) < 2:
        return None
    evidence_start = min(band[0] for band in major_bands)
    evidence_end = max(band[0] for band in major_bands)
    evidence_width = evidence_end - evidence_start
    if not (
        tolerances.collinear_tolerance_mm
        < evidence_width
        <= tolerances.maximum_component_width_mm
    ):
        return None
    evidence_center = (evidence_start + evidence_end) / 2.0
    if not preserve_transverse_axis:
        if (
            abs(evidence_center - candidate_center)
            > tolerances.collinear_tolerance_mm
        ):
            return None
        candidate_width = candidate.representative_width or evidence_width
        half_width = candidate_width / 2.0 + tolerances.width_tolerance_mm
        if (
            evidence_start < candidate_center - half_width
            or evidence_end > candidate_center + half_width
        ):
            return None

    clipped_intervals = []
    for _, intervals, _ in major_bands:
        # Interior gaps are a drafting/fragmentation property, not missing
        # longitudinal reach.  Once every fragment has passed the geometric
        # eligibility gates, completeness measures the supported extent of
        # each rail band rather than requiring the linework itself to be
        # continuous across the whole Waler-bounded corridor.
        clipped_start = max(min(start for start, _ in intervals), span_start)
        clipped_end = min(max(end for _, end in intervals), span_end)
        if clipped_end - clipped_start > NUMERIC_EPSILON:
            clipped_intervals.append((clipped_start, clipped_end))
    coverage = _merged_interval_length(clipped_intervals) / span_length
    if coverage < tolerances.minimum_projection_overlap_ratio:
        return None
    return min(1.0, coverage), evidence_width


def _contextual_span_key(
    contextual: _ContextualCandidate,
) -> tuple[tuple[str, ...], ...]:
    return tuple(
        reference.source_handles for reference in contextual.span.references
    )


def _contextual_center_groups(
    candidates: Sequence[_ContextualCandidate],
    tolerances: GeometryTolerances,
) -> tuple[tuple[_ContextualCandidate, ...], ...]:
    """Group equivalent centers without discarding their envelope evidence."""

    groups: list[list[_ContextualCandidate]] = []
    for contextual in sorted(
        candidates,
        key=lambda item: (
            item.candidate.authority_tier,
            _contextual_span_key(item),
            -item.candidate.evidence_ratio,
            -item.candidate.root_extent_coverage,
            item.candidate.axis,
            -item.candidate.representative_width,
        ),
    ):
        matching_group = next(
            (
                group
                for group in groups
                if contextual.candidate.authority_tier
                is group[0].candidate.authority_tier
                and _contextual_span_key(contextual)
                == _contextual_span_key(group[0])
                and all(
                    _axes_equivalent(
                        contextual.candidate.axis,
                        existing.candidate.axis,
                        tolerances,
                    )
                    for existing in group
                )
            ),
            None,
        )
        if matching_group is None:
            groups.append([contextual])
        else:
            matching_group.append(contextual)
    return tuple(tuple(group) for group in groups)


def _contextual_group_representative(
    group: Sequence[_ContextualCandidate],
) -> _ContextualCandidate:
    return min(
        group,
        key=lambda item: (
            -item.candidate.evidence_ratio,
            -item.candidate.root_extent_coverage,
            item.candidate.axis,
            -item.candidate.representative_width,
            _contextual_span_key(item),
        ),
    )


def _contextual_group_score(
    group: Sequence[_ContextualCandidate],
) -> float:
    return max(item.candidate.evidence_ratio for item in group)


def _contextual_group_coverage(
    group: Sequence[_ContextualCandidate],
) -> float:
    return max(item.candidate.root_extent_coverage for item in group)


def _numeric_geometry_equal(first: float, second: float) -> bool:
    return math.isclose(
        first,
        second,
        rel_tol=NUMERIC_EPSILON,
        abs_tol=NUMERIC_EPSILON,
    )


def _reconcile_contextual_group_width(
    group: Sequence[_ContextualCandidate],
) -> float:
    """Return the unique containing envelope width, or zero when unknown."""

    if not group:
        return 0.0
    reference = _contextual_group_representative(group)
    direction = _canonical_unit(reference.candidate.axis)
    if direction is None:
        return 0.0
    normal = -direction[1], direction[0]
    envelopes: list[tuple[float, float, float]] = []
    for contextual in group:
        width = contextual.candidate.representative_width
        if width <= NUMERIC_EPSILON:
            continue
        center = _dot(_midpoint(*contextual.candidate.axis), normal)
        envelope = (center - width / 2.0, center + width / 2.0, width)
        if any(
            _numeric_geometry_equal(envelope[0], existing[0])
            and _numeric_geometry_equal(envelope[1], existing[1])
            for existing in envelopes
        ):
            continue
        envelopes.append(envelope)
    if not envelopes:
        return 0.0
    containers = tuple(
        envelope
        for envelope in envelopes
        if all(
            envelope[0] < other[0]
            or _numeric_geometry_equal(envelope[0], other[0])
            for other in envelopes
        )
        and all(
            envelope[1] > other[1]
            or _numeric_geometry_equal(envelope[1], other[1])
            for other in envelopes
        )
    )
    return containers[0][2] if len(containers) == 1 else 0.0


def _recognize_contextual_strut(
    source: BlockMemberRecognitionInput,
    settings: GeometryTolerances,
    waler_context: Sequence[WalerSpanReference],
) -> BlockMemberRecognitionOutcome:
    source_only_outcome = _recognize_component_like_member(
        source,
        settings,
        role="strut",
    )
    source_fragments = _extract_fragment_axes(source.primitives, settings)
    strong_orientation_count = sum(
        any(fragment.is_strong for fragment in cluster.fragments)
        for cluster in _build_orientation_clusters(source_fragments, settings)
    )
    if source_only_outcome.status is BlockMemberRecognitionStatus.FAILED or (
        source_only_outcome.status is BlockMemberRecognitionStatus.AMBIGUOUS
        and strong_orientation_count > 1
    ):
        return source_only_outcome
    topology_outcome = _recognize_topology_guarded_member(source, settings)
    if topology_outcome is not None and topology_outcome.status in {
        BlockMemberRecognitionStatus.FAILED,
        BlockMemberRecognitionStatus.AMBIGUOUS,
    }:
        return topology_outcome

    fragments = source_fragments
    strong_fragments = tuple(fragment for fragment in fragments if fragment.is_strong)
    component_like = (
        topology_outcome is not None
        and topology_outcome.status is BlockMemberRecognitionStatus.RECOGNIZED
    ) or len(strong_fragments) > 1
    if not component_like:
        return BlockMemberRecognitionOutcome.not_applicable()

    hypotheses = list(_whole_root_envelope_candidates(source, settings))
    hypotheses.extend(_component_candidates(source, fragments, settings))
    if (
        topology_outcome is not None
        and topology_outcome.status is BlockMemberRecognitionStatus.RECOGNIZED
    ):
        assert topology_outcome.whole_axis is not None
        hypotheses.append(
            _ComponentCandidate(
                topology_outcome.whole_axis,
                topology_outcome.representative_width,
                tuple(strong_fragments[: topology_outcome.accepted_fragment_count]),
                _length(*topology_outcome.whole_axis),
                topology_outcome.confidence,
                1.0,
                _CandidateAuthorityTier.TOPOLOGY,
            )
        )
    if not hypotheses:
        return BlockMemberRecognitionOutcome.failed(
            "BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE"
        )

    contextual_candidates: list[_ContextualCandidate] = []
    span_failure_codes: list[str] = []
    observed_context: tuple[tuple[WalerSpanReference, Point], ...] = ()
    for candidate in hypotheses:
        span, failure_code, observed = _select_waler_span(
            source,
            candidate,
            waler_context,
            settings,
        )
        if span is None:
            span_failure_codes.append(failure_code)
            if len(observed) > len(observed_context):
                observed_context = observed
            continue
        metrics = _whole_root_completeness(
            source,
            candidate,
            span,
            settings,
            preserve_transverse_axis=(
                candidate.authority_tier
                is _CandidateAuthorityTier.TOPOLOGY
            ),
        )
        if metrics is None:
            continue
        coverage, _ = metrics
        contextual_candidates.append(
            _ContextualCandidate(
                _ComponentCandidate(
                    _ordered_line(*span.intersections),
                    candidate.representative_width,
                    candidate.fragments,
                    candidate.longitudinal_support,
                    candidate.evidence_ratio,
                    coverage,
                    candidate.authority_tier,
                ),
                span,
            )
        )

    if not contextual_candidates:
        observed_handles = tuple(
            item[0].source_handles for item in observed_context
        )
        observed_points = tuple(item[1] for item in observed_context)
        if "BIM_BLOCK_WALER_SPAN_AMBIGUOUS" in span_failure_codes:
            return BlockMemberRecognitionOutcome.ambiguous(
                "BIM_BLOCK_WALER_SPAN_AMBIGUOUS",
                selected_waler_source_handles=observed_handles,
                waler_intersections=observed_points,
            )
        if span_failure_codes and all(
            code == "BIM_BLOCK_WALER_SPAN_INCOMPLETE"
            for code in span_failure_codes
        ):
            return BlockMemberRecognitionOutcome.failed(
                "BIM_BLOCK_WALER_SPAN_INCOMPLETE",
                selected_waler_source_handles=observed_handles,
                waler_intersections=observed_points,
            )
        return BlockMemberRecognitionOutcome.failed(
            "BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE"
        )

    winner_candidates = tuple(
        item
        for item in contextual_candidates
        if item.candidate.evidence_ratio
        >= settings.bim_minimum_longitudinal_evidence_ratio
    )
    reliable_winners = tuple(
        item
        for item in winner_candidates
        if item.candidate.root_extent_coverage
        >= settings.minimum_projection_overlap_ratio
    )
    if not reliable_winners:
        return BlockMemberRecognitionOutcome.failed(
            "BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE"
        )
    authority_tier = min(
        item.candidate.authority_tier for item in reliable_winners
    )
    authority_candidates = tuple(
        item
        for item in reliable_winners
        if item.candidate.authority_tier is authority_tier
    )
    center_groups = list(
        _contextual_center_groups(authority_candidates, settings)
    )
    center_groups.sort(
        key=lambda group: (
            -_contextual_group_score(group),
            -_contextual_group_coverage(group),
            _contextual_group_representative(group).candidate.axis,
        )
    )
    best_group = center_groups[0]
    best_score = _contextual_group_score(best_group)
    conflicts = tuple(
        group
        for group in center_groups[1:]
        if abs(best_score - _contextual_group_score(group))
        <= settings.ambiguous_candidate_score_delta
    )
    if conflicts:
        return BlockMemberRecognitionOutcome.ambiguous(
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES"
        )
    best = _contextual_group_representative(best_group)
    representative_width = _reconcile_contextual_group_width(best_group)
    return BlockMemberRecognitionOutcome.recognized(
        best.candidate.axis,
        representative_width=representative_width,
        confidence=best_score,
        accepted_fragment_count=max(
            1,
            max(len(item.candidate.fragments) for item in best_group),
        ),
        selected_waler_source_handles=tuple(
            reference.source_handles for reference in best.span.references
        ),
        waler_intersections=best.span.intersections,
    )


def _recognize_component_like_member(
    source: BlockMemberRecognitionInput,
    settings: GeometryTolerances,
    *,
    role: str,
) -> BlockMemberRecognitionOutcome:
    topology_outcome = _recognize_topology_guarded_member(source, settings)
    if topology_outcome is not None:
        return topology_outcome
    if _has_full_span_legacy_evidence(source, settings):
        return BlockMemberRecognitionOutcome.not_applicable()
    fragments = _extract_fragment_axes(source.primitives, settings)
    candidates = _component_candidates(source, fragments, settings)
    winner_candidates = tuple(
        candidate
        for candidate in candidates
        if candidate.evidence_ratio
        >= settings.bim_minimum_longitudinal_evidence_ratio
    )
    if not winner_candidates:
        return BlockMemberRecognitionOutcome.not_applicable()
    reliable_winners = tuple(
        candidate
        for candidate in winner_candidates
        if candidate.root_extent_coverage
        >= settings.minimum_projection_overlap_ratio
    )
    if not reliable_winners:
        return BlockMemberRecognitionOutcome.failed(
            "BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE"
        )
    best = reliable_winners[0]
    reliable_runners = tuple(
        candidate
        for candidate in candidates
        if candidate is not best
        and candidate.root_extent_coverage
        >= settings.minimum_projection_overlap_ratio
    )
    conflicting_candidates = tuple(
        candidate
        for candidate in reliable_runners
        if (
            abs(best.evidence_ratio - candidate.evidence_ratio)
            <= settings.ambiguous_candidate_score_delta
            and not _axes_equivalent(best.axis, candidate.axis, settings)
        )
    )
    if conflicting_candidates:
        if role == "brace":
            consolidated = _consolidated_brace_candidate_outcome(
                (best, *conflicting_candidates),
                settings,
            )
            if consolidated is not None:
                return consolidated
        return BlockMemberRecognitionOutcome.ambiguous(
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES"
        )
    return BlockMemberRecognitionOutcome.recognized(
        best.axis,
        representative_width=best.representative_width,
        confidence=best.evidence_ratio,
        accepted_fragment_count=len(best.fragments),
    )


def recognize_component_like_member(
    source: BlockMemberRecognitionInput,
    tolerances: GeometryTolerances | None = None,
) -> BlockMemberRecognitionOutcome:
    """Interpret one supported root source without mutating workflow state."""

    settings = tolerances or GeometryTolerances()
    role = str(source.role or "").strip().casefold()
    if role not in {"strut", "brace"}:
        return BlockMemberRecognitionOutcome.not_applicable()
    return _recognize_component_like_member(
        source,
        settings,
        role=role,
    )


def recognize_component_like_strut(
    source: BlockMemberRecognitionInput,
    tolerances: GeometryTolerances | None = None,
    *,
    waler_context: Sequence[WalerSpanReference] | None = None,
) -> BlockMemberRecognitionOutcome:
    """Compatibility entry for the established Strut recognition contract."""

    settings = tolerances or GeometryTolerances()
    if waler_context is not None:
        return _recognize_contextual_strut(
            source,
            settings,
            tuple(waler_context),
        )
    return _recognize_component_like_member(
        source,
        settings,
        role="strut",
    )
