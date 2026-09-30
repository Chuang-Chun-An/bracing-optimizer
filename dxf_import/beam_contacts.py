"""Pure finite-contact geometry shared by Beam and BIM Joist recognition."""

from __future__ import annotations

from .geometry import (
    Point,
    _angle_difference_deg,
    _dot,
    _length,
    _segment_intersection_point,
    _unit,
    _vector,
)


BEAM_MEMBER_PERPENDICULAR_TOLERANCE_DEG = 5.0


def finite_perpendicular_contact(
    subject_segment: tuple[Point, Point],
    member_segment: tuple[Point, Point],
    *,
    angle_tolerance_deg: float = BEAM_MEMBER_PERPENDICULAR_TOLERANCE_DEG,
) -> tuple[Point, float] | None:
    """Return a real finite intersection and station on ``member_segment``.

    Shared finite endpoints are valid intersections.  Infinite-line
    projections, nearest points, and finite gaps are deliberately excluded.
    """

    if (
        abs(90.0 - _angle_difference_deg(subject_segment, member_segment))
        > angle_tolerance_deg
    ):
        return None
    point = _segment_intersection_point(subject_segment, member_segment, 1e-6)
    if point is None:
        return None
    member_direction = _unit(*member_segment)
    member_length = _length(*member_segment)
    if member_direction is None or member_length <= 1e-9:
        return None
    station = _dot(_vector(member_segment[0], point), member_direction)
    if not (-1e-6 <= station <= member_length + 1e-6):
        return None
    return point, max(0.0, min(member_length, station))


__all__ = [
    "BEAM_MEMBER_PERPENDICULAR_TOLERANCE_DEG",
    "finite_perpendicular_contact",
]
