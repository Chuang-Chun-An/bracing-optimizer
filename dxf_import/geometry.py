"""Low-level two-dimensional geometry helpers for DXF import."""

from __future__ import annotations

import math
from typing import Any, Sequence


Point = tuple[float, float]


def _point(value: Any) -> Point:
    return float(value[0]), float(value[1])


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


def circle_segment_intersection_points(
    center: Point,
    radius: float,
    segment_start: Point,
    segment_end: Point,
    tolerance: float = 1e-6,
) -> tuple[Point, ...]:
    """Return deterministic intersections of a circle and a finite segment."""

    values = (*center, radius, *segment_start, *segment_end, tolerance)
    if not all(math.isfinite(float(value)) for value in values):
        return ()
    radius = float(radius)
    tolerance = max(0.0, float(tolerance))
    if radius <= tolerance:
        return ()
    direction = _vector(segment_start, segment_end)
    length_sq = _dot(direction, direction)
    if length_sq <= tolerance * tolerance:
        return ()

    relative = _vector(center, segment_start)
    a = length_sq
    b = 2.0 * _dot(relative, direction)
    c = _dot(relative, relative) - radius * radius
    discriminant = b * b - 4.0 * a * c
    discriminant_tolerance = tolerance * max(a, radius * radius, 1.0)
    if discriminant < -discriminant_tolerance:
        return ()

    if abs(discriminant) <= discriminant_tolerance:
        ratios = (-b / (2.0 * a),)
    else:
        root = math.sqrt(max(0.0, discriminant))
        ratios = ((-b - root) / (2.0 * a), (-b + root) / (2.0 * a))

    margin = tolerance / max(math.sqrt(length_sq), 1e-12)
    intersections: list[tuple[float, Point]] = []
    for ratio in ratios:
        if not (-margin <= ratio <= 1.0 + margin):
            continue
        clamped = min(1.0, max(0.0, ratio))
        point = (
            segment_start[0] + clamped * direction[0],
            segment_start[1] + clamped * direction[1],
        )
        if not any(_same_point(point, existing, tolerance) for _, existing in intersections):
            intersections.append((clamped, point))
    intersections.sort(key=lambda item: item[0])
    return tuple(point for _, point in intersections)


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
