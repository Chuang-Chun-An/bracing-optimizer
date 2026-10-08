"""Pure CornerBrace RailTrack, body, and relationship evidence.

The body layer is deliberately independent of Waler/Strut relationships.
Relationship-dependent coverage, gaps, extensions, and classification are
computed only by :func:`assess_corner_brace_relationship`.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Sequence

from .geometry import (
    Point,
    _angle_difference_deg,
    _closest_points_between_segments,
    _distance,
    _dot,
    _length,
    _ordered_line,
    _segment_distance,
    _unit,
    _vector,
)
from .models import (
    CornerBraceBodyGeometryEvidence,
    CornerBraceBodyRelationshipAssessment,
    CornerBraceGapEvidence,
    CornerBraceGapOccluderAssignment,
    CornerBraceRailFragmentEvidence,
    CornerBraceRailTrackEvidence,
    GeometryTolerances,
)


@dataclass(frozen=True)
class CornerBraceSourceSegment:
    """One exact source segment before it enters a RailTrack hypothesis."""

    id: str
    source_handle: str
    line: tuple[Point, Point]


def canonical_direction(line: tuple[Point, Point]) -> Point | None:
    """Return a deterministic unoriented unit vector for a finite line."""

    direction = _unit(*line)
    if direction is None:
        return None
    x, y = direction
    if x < -1e-12 or (abs(x) <= 1e-12 and y < 0.0):
        x, y = -x, -y
    return (0.0 if abs(x) <= 1e-12 else x, 0.0 if abs(y) <= 1e-12 else y)


def canonical_normal(direction: Point) -> Point:
    """Return the sole normal implied by a canonical direction."""

    return (-direction[1], direction[0])


def _merged_intervals(
    intervals: Sequence[tuple[float, float]],
    seam_mm: float,
) -> tuple[tuple[float, float], ...]:
    ordered = sorted((min(a, b), max(a, b)) for a, b in intervals)
    merged: list[list[float]] = []
    for start, end in ordered:
        if not merged or start - merged[-1][1] > seam_mm:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return tuple((item[0], item[1]) for item in merged)


def _actual_union(
    intervals: Sequence[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    return _merged_intervals(intervals, 0.0)


def _stable_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest().upper()


def _q(value: float) -> float:
    return round(float(value), 6)


def build_corner_brace_rail_tracks(
    sources: Sequence[CornerBraceSourceSegment],
    tolerances: GeometryTolerances,
) -> tuple[CornerBraceRailTrackEvidence, ...]:
    """Enumerate maximal, order-independent normal-offset hypotheses."""

    finite = tuple(
        source for source in sources if _length(*source.line) > 1e-9
    )
    eligible = tuple(
        source
        for source in finite
        if _length(*source.line) >= tolerances.minimum_component_length_mm
    )
    tracks: dict[str, CornerBraceRailTrackEvidence] = {}
    for seed in eligible:
        direction = canonical_direction(seed.line)
        if direction is None:
            continue
        normal = canonical_normal(direction)
        aligned = tuple(
            source
            for source in finite
            if _angle_difference_deg(seed.line, source.line)
            <= tolerances.parallel_angle_tolerance_deg + 1e-9
        )
        projected = sorted(
            (
                _dot(source.line[0], normal),
                source.id,
                source,
            )
            for source in aligned
        )
        windows: list[tuple[CornerBraceSourceSegment, ...]] = []
        for left in range(len(projected)):
            members = tuple(
                item[2]
                for item in projected[left:]
                if item[0] - projected[left][0]
                <= tolerances.collinear_tolerance_mm
            )
            if members:
                windows.append(members)
        maximal_windows = tuple(
            members
            for members in windows
            if not any(
                set(item.id for item in members)
                < set(item.id for item in other)
                for other in windows
            )
        )
        for members in maximal_windows:
            direction_sources = tuple(
                source
                for source in eligible
                if all(
                    _angle_difference_deg(source.line, member.line)
                    <= tolerances.parallel_angle_tolerance_deg + 1e-9
                    for member in members
                )
            )
            if not direction_sources:
                continue
            representative = min(
                direction_sources,
                key=lambda source: (-_length(*source.line), source.id),
            )
            track_direction = canonical_direction(representative.line)
            if track_direction is None:
                continue
            track_normal = canonical_normal(track_direction)
            offsets = tuple(
                _dot(point, track_normal)
                for source in members
                for point in source.line
            )
            if not offsets or max(offsets) - min(offsets) > tolerances.collinear_tolerance_mm:
                continue
            mean_offset = sum(offsets) / len(offsets)
            fragments = tuple(
                sorted(
                    (
                        CornerBraceRailFragmentEvidence(
                            id=source.id,
                            source_handle=source.source_handle,
                            line=_ordered_line(*source.line),
                            normal_offset_mm=(
                                _dot(source.line[0], track_normal)
                                + _dot(source.line[1], track_normal)
                            )
                            / 2.0,
                            interval=tuple(
                                sorted(
                                    (
                                        _dot(source.line[0], track_direction),
                                        _dot(source.line[1], track_direction),
                                    )
                                )
                            ),
                        )
                        for source in members
                    ),
                    key=lambda item: item.id,
                )
            )
            intervals = tuple(fragment.interval for fragment in fragments)
            merged = _merged_intervals(intervals, tolerances.corner_brace_track_seam_mm)
            start = min(value[0] for value in intervals)
            end = max(value[1] for value in intervals)
            supporting_line = _ordered_line(
                (
                    track_direction[0] * start
                    + track_normal[0] * mean_offset,
                    track_direction[1] * start
                    + track_normal[1] * mean_offset,
                ),
                (
                    track_direction[0] * end
                    + track_normal[0] * mean_offset,
                    track_direction[1] * end
                    + track_normal[1] * mean_offset,
                ),
            )
            identity = _stable_hash(
                {
                    "fragments": [fragment.id for fragment in fragments],
                    "direction": [_q(value) for value in track_direction],
                }
            )
            tracks[identity] = CornerBraceRailTrackEvidence(
                id=identity,
                fragments=fragments,
                supporting_line=supporting_line,
                canonical_direction=track_direction,
                canonical_normal=track_normal,
                normal_offsets_mm=tuple(
                    sorted(fragment.normal_offset_mm for fragment in fragments)
                ),
                merged_intervals=merged,
            )
    return tuple(sorted(tracks.values(), key=lambda item: item.id))


def _terminal_plates(
    first: CornerBraceRailTrackEvidence,
    second: CornerBraceRailTrackEvidence,
    sources: Sequence[CornerBraceSourceSegment],
    tolerances: GeometryTolerances,
) -> tuple[tuple[Point, Point], ...]:
    selected = {
        fragment.id for track in (first, second) for fragment in track.fragments
    }
    matches: list[tuple[Point, Point]] = []
    for source in sources:
        if source.id in selected:
            continue
        if _angle_difference_deg(source.line, first.supporting_line) <= 45.0:
            continue
        endpoints = (first.supporting_line[0], first.supporting_line[1])
        other_endpoints = (second.supporting_line[0], second.supporting_line[1])
        if any(
            max(
                min(_distance(source.line[0], a), _distance(source.line[1], a)),
                min(_distance(source.line[0], b), _distance(source.line[1], b)),
            )
            <= tolerances.endpoint_tolerance_mm
            for a, b in zip(endpoints, other_endpoints)
        ):
            matches.append(_ordered_line(*source.line))
    return tuple(sorted(set(matches)))


def build_corner_brace_body_hypotheses(
    group_key: str,
    source_handles: Sequence[str],
    sources: Sequence[CornerBraceSourceSegment],
    tolerances: GeometryTolerances,
) -> tuple[CornerBraceBodyGeometryEvidence, ...]:
    """Build geometry-only two-track body hypotheses without relationship facts."""

    tracks = build_corner_brace_rail_tracks(sources, tolerances)
    bodies: dict[str, CornerBraceBodyGeometryEvidence] = {}
    for first_index, first in enumerate(tracks):
        for second in tracks[first_index + 1 :]:
            if {item.id for item in first.fragments} & {item.id for item in second.fragments}:
                continue
            if (
                _angle_difference_deg(first.supporting_line, second.supporting_line)
                > tolerances.parallel_angle_tolerance_deg + 1e-9
            ):
                continue
            first_offset = sum(first.normal_offsets_mm) / len(first.normal_offsets_mm)
            second_offset = sum(second.normal_offsets_mm) / len(second.normal_offsets_mm)
            separation = abs(second_offset - first_offset)
            if not (
                tolerances.minimum_corner_brace_rail_separation_mm < separation
                <= tolerances.maximum_corner_brace_rail_separation_mm
            ):
                continue
            direction = first.canonical_direction
            normal = first.canonical_normal
            intervals = (*first.merged_intervals, *second.merged_intervals)
            start = min(value[0] for value in intervals)
            end = max(value[1] for value in intervals)
            mid_offset = (first_offset + second_offset) / 2.0
            midline = _ordered_line(
                (
                    direction[0] * start + normal[0] * mid_offset,
                    direction[1] * start + normal[1] * mid_offset,
                ),
                (
                    direction[0] * end + normal[0] * mid_offset,
                    direction[1] * end + normal[1] * mid_offset,
                ),
            )
            ordered_tracks = tuple(
                sorted((first, second), key=lambda item: sum(item.normal_offsets_mm) / len(item.normal_offsets_mm))
            )
            signature = _stable_hash(
                {
                    "group": group_key,
                    "tracks": [item.id for item in ordered_tracks],
                    "separation": _q(separation),
                }
            )
            fragments = tuple(
                sorted(
                    (
                        fragment
                        for track in ordered_tracks
                        for fragment in track.fragments
                    ),
                    key=lambda item: item.id,
                )
            )
            bodies[signature] = CornerBraceBodyGeometryEvidence(
                signature=signature,
                group_key=group_key,
                source_handles=tuple(sorted(set(source_handles))),
                fragments=fragments,
                rail_tracks=(ordered_tracks[0], ordered_tracks[1]),
                selected_track_ids=(ordered_tracks[0].id, ordered_tracks[1].id),
                supporting_line_ids=(ordered_tracks[0].id, ordered_tracks[1].id),
                canonical_direction=direction,
                canonical_normal=normal,
                midline=midline,
                rail_separation_mm=separation,
                merged_source_intervals=(
                    ordered_tracks[0].merged_intervals,
                    ordered_tracks[1].merged_intervals,
                ),
                terminal_plate_evidence=_terminal_plates(
                    ordered_tracks[0], ordered_tracks[1], sources, tolerances
                ),
            )
    return tuple(sorted(bodies.values(), key=lambda item: item.signature))


def select_corner_brace_body_outcome(
    bodies: Sequence[CornerBraceBodyGeometryEvidence],
) -> tuple[tuple[CornerBraceBodyGeometryEvidence, ...], bool]:
    """Select a unique maximum-evidence non-overlapping body set."""

    ordered = tuple(sorted(bodies, key=lambda item: item.signature))
    fragment_sets = tuple(
        frozenset(fragment.id for fragment in body.fragments)
        for body in ordered
    )
    scores = tuple(
        sum(
            end - start
            for track in body.rail_tracks
            for start, end in _actual_union(
                tuple(fragment.interval for fragment in track.fragments)
            )
        )
        for body in ordered
    )

    # Independent conflict components are solved separately.  This preserves
    # exhaustive, order-independent selection without the former 2**N cost
    # across unrelated physical bodies in a compound INSERT.
    unseen = set(range(len(ordered)))
    components: list[tuple[int, ...]] = []
    while unseen:
        stack = [unseen.pop()]
        component: set[int] = set()
        while stack:
            index = stack.pop()
            component.add(index)
            neighbours = {
                other
                for other in tuple(unseen)
                if fragment_sets[index] & fragment_sets[other]
            }
            unseen.difference_update(neighbours)
            stack.extend(neighbours)
        components.append(tuple(sorted(component)))

    selected_indices: list[int] = []
    for component in components:
        best_count = -1
        best_score = -1.0
        best_sets: list[tuple[int, ...]] = []
        local = tuple(
            sorted(component, key=lambda index: (-scores[index], ordered[index].signature))
        )

        def search(
            position: int,
            chosen: tuple[int, ...],
            occupied: frozenset[str],
            chosen_score: float,
        ) -> None:
            nonlocal best_count, best_score, best_sets
            if len(chosen) + len(local) - position < best_count:
                return
            if position == len(local):
                normalized = tuple(sorted(chosen))
                if len(chosen) > best_count or (
                    len(chosen) == best_count
                    and chosen_score > best_score + 1e-6
                ):
                    best_count = len(chosen)
                    best_score = chosen_score
                    best_sets = [normalized]
                elif (
                    len(chosen) == best_count
                    and abs(chosen_score - best_score) <= 1e-6
                    and normalized not in best_sets
                    and len(best_sets) < 2
                ):
                    best_sets.append(normalized)
                return
            index = local[position]
            if not fragment_sets[index] & occupied:
                search(
                    position + 1,
                    (*chosen, index),
                    occupied | fragment_sets[index],
                    chosen_score + scores[index],
                )
            search(position + 1, chosen, occupied, chosen_score)

        search(0, (), frozenset(), 0.0)
        if len(best_sets) != 1 or not best_sets[0]:
            return (), bool(ordered)
        selected_indices.extend(best_sets[0])
    return tuple(ordered[index] for index in sorted(selected_indices)), False


def _clipped_union(
    intervals: Sequence[tuple[float, float]],
    start: float,
    end: float,
) -> tuple[tuple[float, float], ...]:
    clipped = (
        (max(start, a), min(end, b))
        for a, b in _actual_union(intervals)
    )
    return tuple((a, b) for a, b in clipped if b > a)


def _gap_world_line(
    track: CornerBraceRailTrackEvidence,
    interval: tuple[float, float],
) -> tuple[Point, Point]:
    offset = sum(track.normal_offsets_mm) / len(track.normal_offsets_mm)
    direction = track.canonical_direction
    normal = track.canonical_normal
    return _ordered_line(
        (
            direction[0] * interval[0] + normal[0] * offset,
            direction[1] * interval[0] + normal[1] * offset,
        ),
        (
            direction[0] * interval[1] + normal[0] * offset,
            direction[1] * interval[1] + normal[1] * offset,
        ),
    )


def _track_gaps(
    track: CornerBraceRailTrackEvidence,
    start: float,
    end: float,
    seam_mm: float,
) -> tuple[CornerBraceGapEvidence, ...]:
    union = _clipped_union(
        tuple(fragment.interval for fragment in track.fragments), start, end
    )
    ranges: list[tuple[str, tuple[float, float]]] = []
    cursor = start
    for interval_start, interval_end in union:
        if interval_start - cursor > seam_mm:
            ranges.append(("terminal" if cursor == start else "internal", (cursor, interval_start)))
        cursor = max(cursor, interval_end)
    if end - cursor > seam_mm:
        ranges.append(("terminal", (cursor, end)))
    return tuple(
        CornerBraceGapEvidence(
            rail_track_id=track.id,
            kind=kind,
            interval=interval,
            world_line=_gap_world_line(track, interval),
        )
        for kind, interval in ranges
    )


def _projected_overlap_ratio(
    reference: tuple[Point, Point],
    candidate: tuple[Point, Point],
) -> float:
    direction = _unit(*reference)
    if direction is None:
        return 0.0
    origin = reference[0]
    ref_end = _dot(_vector(origin, reference[1]), direction)
    values = sorted(_dot(_vector(origin, point), direction) for point in candidate)
    overlap = max(0.0, min(ref_end, values[1]) - max(0.0, values[0]))
    return overlap / max(ref_end, 1e-9)


def _occluders_for_gap(
    gap: CornerBraceGapEvidence,
    occluding_lines: Sequence[tuple[Point, Point]],
    tolerances: GeometryTolerances,
    terminal_plate_lines: Sequence[tuple[Point, Point]] = (),
) -> tuple[tuple[Point, Point], ...]:
    matches: list[tuple[Point, Point]] = []
    ordered_terminal_plates = {
        _ordered_line(*line) for line in terminal_plate_lines
    }
    for line in occluding_lines:
        if _length(*line) <= 1e-9:
            continue
        angle = _angle_difference_deg(gap.world_line, line)
        if angle <= tolerances.parallel_angle_tolerance_deg:
            if _segment_distance(line[0], *gap.world_line) > tolerances.collinear_tolerance_mm:
                continue
            if _projected_overlap_ratio(gap.world_line, line) < tolerances.minimum_corner_brace_parallel_occluder_overlap_ratio:
                continue
        else:
            _gap_point, _line_point, distance = (
                _closest_points_between_segments(gap.world_line, line)
            )
            ordered = _ordered_line(*line)
            is_terminal_plate = (
                gap.kind == "terminal" and ordered in ordered_terminal_plates
            )
            if distance > (
                tolerances.endpoint_tolerance_mm
                if is_terminal_plate
                else tolerances.collinear_tolerance_mm
            ):
                continue
        ordered = _ordered_line(*line)
        if ordered not in matches:
            matches.append(ordered)
    return tuple(matches)


def assess_corner_brace_relationship(
    body: CornerBraceBodyGeometryEvidence,
    *,
    waler_source_handles: Sequence[str],
    strut_source_handles: Sequence[str],
    waler_intersection: Point,
    strut_intersection: Point,
    occluding_lines: Sequence[tuple[Point, Point]],
    tolerances: GeometryTolerances,
) -> CornerBraceBodyRelationshipAssessment:
    """Evaluate one finite relationship without mutating body evidence."""

    direction = body.canonical_direction
    waler_station = _dot(waler_intersection, direction)
    strut_station = _dot(strut_intersection, direction)
    endpoint_stations = sorted((waler_station, strut_station))
    start, end = endpoint_stations
    expected_span = end - start
    coverages: list[float] = []
    gaps: list[CornerBraceGapEvidence] = []
    all_intervals: list[tuple[float, float]] = []
    source_intervals_by_track = tuple(
        tuple(fragment.interval for fragment in track.fragments)
        for track in body.rail_tracks
    )
    body_start = min(
        interval[0]
        for intervals in source_intervals_by_track
        for interval in intervals
    )
    body_end = max(
        interval[1]
        for intervals in source_intervals_by_track
        for interval in intervals
    )
    for track, source_intervals in zip(
        body.rail_tracks, source_intervals_by_track
    ):
        clipped = _clipped_union(source_intervals, start, end)
        covered = sum(b - a for a, b in clipped)
        coverages.append(covered / expected_span if expected_span > 1e-9 else 0.0)
        gaps.extend(
            _track_gaps(
                track,
                body_start,
                body_end,
                tolerances.corner_brace_track_seam_mm,
            )
        )
        all_intervals.extend(source_intervals)
    observed_start = min((item[0] for item in all_intervals), default=start)
    observed_end = max((item[1] for item in all_intervals), default=end)
    lower_extension = max(0.0, observed_start - start)
    upper_extension = max(0.0, end - observed_end)
    extensions = (
        (lower_extension, upper_extension)
        if waler_station <= strut_station
        else (upper_extension, lower_extension)
    )
    assignments = tuple(
        CornerBraceGapOccluderAssignment(
            gap=gap,
            occluder_lines=_occluders_for_gap(
                gap,
                occluding_lines,
                tolerances,
                body.terminal_plate_evidence,
            ),
        )
        for gap in gaps
    )
    slenderness = expected_span / max(body.rail_separation_mm, 1e-9)
    reasons: list[str] = []
    if expected_span <= 0.0:
        reasons.append("expected_span_not_positive")
    if slenderness < tolerances.minimum_corner_brace_expected_slenderness_ratio:
        reasons.append("expected_slenderness_below_minimum")
    for index, coverage in enumerate(coverages):
        if coverage < tolerances.minimum_corner_brace_rail_coverage_ratio:
            reasons.append(f"rail_{index + 1}_coverage_below_minimum")
    if extensions[0] > tolerances.maximum_corner_brace_axis_extension_mm:
        reasons.append("waler_end_extension_above_maximum")
    if extensions[1] > tolerances.maximum_corner_brace_axis_extension_mm:
        reasons.append("strut_end_extension_above_maximum")
    if any(not assignment.occluder_lines for assignment in assignments):
        reasons.append("gap_without_finite_occluder")
    classification = (
        "hard_invalid"
        if reasons
        else ("occluded" if gaps else "complete")
    )
    return CornerBraceBodyRelationshipAssessment(
        body_signature=body.signature,
        waler_source_handles=tuple(sorted(set(waler_source_handles))),
        strut_source_handles=tuple(sorted(set(strut_source_handles))),
        finite_intersections=(waler_intersection, strut_intersection),
        expected_span_mm=expected_span,
        expected_slenderness_ratio=slenderness,
        per_rail_union_coverage=(coverages[0], coverages[1]),
        internal_gaps=tuple(gap for gap in gaps if gap.kind == "internal"),
        terminal_gaps=tuple(gap for gap in gaps if gap.kind == "terminal"),
        gap_occluder_assignments=assignments,
        per_end_extensions_mm=extensions,
        classification=classification,
        hard_valid=not reasons,
        rejection_reasons=tuple(reasons),
    )


__all__ = [
    "CornerBraceSourceSegment",
    "assess_corner_brace_relationship",
    "build_corner_brace_body_hypotheses",
    "build_corner_brace_rail_tracks",
    "canonical_direction",
    "canonical_normal",
    "select_corner_brace_body_outcome",
]
