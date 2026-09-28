"""Pure geometry rules for Support zoning adjacency.

This module owns engineering geometry meaning only.  It deliberately knows
nothing about Project rows, solver candidates, UI state, or DXF provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

from bracing_optimizer.domain.project_domain import LineSegment, Point


PARALLEL_ANGLE_TOLERANCE_DEG = 5.0
LENGTH_TOLERANCE_MM = 5.0
PROJECTION_TIE_TOLERANCE_MM = 1.0

ZERO_LENGTH_EPSILON_MM = 1e-9
NUMERIC_EPSILON = 1e-9

ZONING_ZERO_LENGTH_AXIS = "ZONING_ZERO_LENGTH_AXIS"
ZONING_ANGLE_OUT_OF_TOLERANCE = "ZONING_ANGLE_OUT_OF_TOLERANCE"
ZONING_LENGTH_OUT_OF_TOLERANCE = "ZONING_LENGTH_OUT_OF_TOLERANCE"
ZONING_PROJECTION_TIE = "ZONING_PROJECTION_TIE"


@dataclass(frozen=True)
class SupportAxisFact:
    """Normalized physical-axis facts for one Strut."""

    member_id: str
    axis: LineSegment
    length: float
    direction: tuple[float, float] | None
    midpoint: Point


@dataclass(frozen=True)
class SupportGeometryIssue:
    """Structured, presentation-neutral zoning geometry failure."""

    code: str
    zoning: str
    member_ids: tuple[str, ...]
    actual_value: float | None = None
    tolerance: float | None = None
    unit_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SupportDirectionResult:
    """Full-group direction semantics plus validation failures."""

    axes: tuple[SupportAxisFact, ...]
    common_direction: tuple[float, float] | None
    row_direction: tuple[float, float] | None
    issues: tuple[SupportGeometryIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class SupportProjectionFact:
    unit_id: str
    member_ids: tuple[str, ...]
    representative_position: Point
    projection: float


@dataclass(frozen=True)
class SupportProjectionResult:
    projections: tuple[SupportProjectionFact, ...]
    issues: tuple[SupportGeometryIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues


def axis_midpoint(axis: LineSegment) -> Point:
    return Point(
        (float(axis.start.x) + float(axis.end.x)) / 2.0,
        (float(axis.start.y) + float(axis.end.y)) / 2.0,
    )


def build_axis_fact(member_id: str, axis: LineSegment) -> SupportAxisFact:
    dx = float(axis.end.x) - float(axis.start.x)
    dy = float(axis.end.y) - float(axis.start.y)
    length = math.hypot(dx, dy)
    direction = None
    if length > ZERO_LENGTH_EPSILON_MM:
        direction = _canonical_direction(dx / length, dy / length)
    return SupportAxisFact(
        member_id=str(member_id),
        axis=axis,
        length=length,
        direction=direction,
        midpoint=axis_midpoint(axis),
    )


def validate_support_axes(
    axes: Iterable[SupportAxisFact],
    *,
    zoning: str = "",
    angle_tolerance_deg: float = PARALLEL_ANGLE_TOLERANCE_DEG,
    length_tolerance_mm: float = LENGTH_TOLERANCE_MM,
) -> SupportDirectionResult:
    """Validate all physical pairs and derive a deterministic common axis."""

    facts = tuple(axes)
    issues: list[SupportGeometryIssue] = []
    valid_facts = []
    for fact in facts:
        if fact.direction is None:
            issues.append(SupportGeometryIssue(
                code=ZONING_ZERO_LENGTH_AXIS,
                zoning=str(zoning),
                member_ids=(fact.member_id,),
                actual_value=fact.length,
                tolerance=ZERO_LENGTH_EPSILON_MM,
            ))
        else:
            valid_facts.append(fact)

    ordered = sorted(valid_facts, key=_axis_geometry_key)
    for index, first in enumerate(ordered):
        for second in ordered[index + 1:]:
            angle = undirected_angle_degrees(first.direction, second.direction)
            member_ids = tuple(sorted((first.member_id, second.member_id)))
            if angle > float(angle_tolerance_deg) + NUMERIC_EPSILON:
                issues.append(SupportGeometryIssue(
                    code=ZONING_ANGLE_OUT_OF_TOLERANCE,
                    zoning=str(zoning),
                    member_ids=member_ids,
                    actual_value=angle,
                    tolerance=float(angle_tolerance_deg),
                ))
            length_difference = abs(first.length - second.length)
            if length_difference > float(length_tolerance_mm) + NUMERIC_EPSILON:
                issues.append(SupportGeometryIssue(
                    code=ZONING_LENGTH_OUT_OF_TOLERANCE,
                    zoning=str(zoning),
                    member_ids=member_ids,
                    actual_value=length_difference,
                    tolerance=float(length_tolerance_mm),
                ))

    common_direction = _undirected_axial_mean(ordered) if ordered else None
    row_direction = (
        (-common_direction[1], common_direction[0])
        if common_direction is not None
        else None
    )
    return SupportDirectionResult(
        axes=facts,
        common_direction=common_direction,
        row_direction=row_direction,
        issues=tuple(sorted(issues, key=_issue_key)),
    )


def project_support_units(
    units: Sequence[tuple[str, Sequence[str], Point]],
    row_direction: tuple[float, float],
    *,
    zoning: str = "",
    tie_tolerance_mm: float = PROJECTION_TIE_TOLERANCE_MM,
) -> SupportProjectionResult:
    """Project units and reject ambiguous transverse positions."""

    rx, ry = row_direction
    facts = tuple(
        SupportProjectionFact(
            unit_id=str(unit_id),
            member_ids=tuple(str(item) for item in member_ids),
            representative_position=position,
            projection=float(position.x) * rx + float(position.y) * ry,
        )
        for unit_id, member_ids, position in units
    )
    geometry_order = tuple(sorted(facts, key=_projection_geometry_key))
    issues: list[SupportGeometryIssue] = []
    for index, first in enumerate(geometry_order):
        for second in geometry_order[index + 1:]:
            difference = abs(first.projection - second.projection)
            if difference <= float(tie_tolerance_mm) + NUMERIC_EPSILON:
                issues.append(SupportGeometryIssue(
                    code=ZONING_PROJECTION_TIE,
                    zoning=str(zoning),
                    member_ids=tuple(sorted(first.member_ids + second.member_ids)),
                    unit_ids=tuple(sorted((first.unit_id, second.unit_id))),
                    actual_value=difference,
                    tolerance=float(tie_tolerance_mm),
                ))
    if issues:
        return SupportProjectionResult(
            projections=geometry_order,
            issues=tuple(sorted(issues, key=_issue_key)),
        )
    return SupportProjectionResult(projections=geometry_order, issues=())


def undirected_angle_degrees(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    dot = abs(first[0] * second[0] + first[1] * second[1])
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def _canonical_direction(x: float, y: float) -> tuple[float, float]:
    if x < -NUMERIC_EPSILON or (
        abs(x) <= NUMERIC_EPSILON and y < -NUMERIC_EPSILON
    ):
        x, y = -x, -y
    if abs(x) <= NUMERIC_EPSILON:
        x = 0.0
    if abs(y) <= NUMERIC_EPSILON:
        y = 0.0
    return x, y


def _undirected_axial_mean(
    axes: Sequence[SupportAxisFact],
) -> tuple[float, float] | None:
    if not axes:
        return None
    angles = [math.atan2(fact.direction[1], fact.direction[0]) for fact in axes]
    cosine = math.fsum(math.cos(2.0 * angle) for angle in angles)
    sine = math.fsum(math.sin(2.0 * angle) for angle in angles)
    if math.hypot(cosine, sine) <= NUMERIC_EPSILON:
        return None
    angle = 0.5 * math.atan2(sine, cosine)
    return _canonical_direction(math.cos(angle), math.sin(angle))


def _axis_geometry_key(fact: SupportAxisFact) -> tuple[object, ...]:
    endpoints = sorted((fact.axis.start.as_tuple(), fact.axis.end.as_tuple()))
    return endpoints[0], endpoints[1], fact.length, fact.member_id


def _projection_geometry_key(fact: SupportProjectionFact) -> tuple[object, ...]:
    return (
        fact.projection,
        fact.representative_position.x,
        fact.representative_position.y,
        tuple(sorted(fact.member_ids)),
    )


def _issue_key(issue: SupportGeometryIssue) -> tuple[object, ...]:
    return issue.code, issue.member_ids, issue.unit_ids


__all__ = [
    "LENGTH_TOLERANCE_MM",
    "PARALLEL_ANGLE_TOLERANCE_DEG",
    "PROJECTION_TIE_TOLERANCE_MM",
    "SupportAxisFact",
    "SupportDirectionResult",
    "SupportGeometryIssue",
    "SupportProjectionFact",
    "SupportProjectionResult",
    "ZONING_ANGLE_OUT_OF_TOLERANCE",
    "ZONING_LENGTH_OUT_OF_TOLERANCE",
    "ZONING_PROJECTION_TIE",
    "ZONING_ZERO_LENGTH_AXIS",
    "axis_midpoint",
    "build_axis_fact",
    "project_support_units",
    "undirected_angle_degrees",
    "validate_support_axes",
]
