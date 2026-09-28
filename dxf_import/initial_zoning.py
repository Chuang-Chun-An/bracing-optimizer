"""Pure initial-Zoning suggestion for completed DXF review results.

The operation consumes final reviewed world geometry.  It neither mutates
recognition state nor owns Project Zoning after the rows enter Main.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Iterable, Sequence

from bracing_optimizer.domain.project_domain import LineSegment, Point
from bracing_optimizer.domain.support_adjacency import (
    build_axis_fact,
    validate_support_axes,
)

from .geometry import _distance, _dot, _line_distance, _unit
from .models import DXFImportResult, GeometryTolerances, Strut, Waler


INITIAL_ZONING_TOPOLOGY_AMBIGUOUS = "INITIAL_ZONING_TOPOLOGY_AMBIGUOUS"
INITIAL_ZONING_TOPOLOGY_CONFLICT = "INITIAL_ZONING_TOPOLOGY_CONFLICT"


@dataclass(frozen=True)
class InitialZoningDiagnostic:
    code: str
    member_ids: tuple[str, ...]
    message: str


@dataclass(frozen=True)
class InitialZoningOutcome:
    result: DXFImportResult
    assignments: tuple[tuple[str, str], ...]
    diagnostics: tuple[InitialZoningDiagnostic, ...]


@dataclass(frozen=True)
class _WalerSegment:
    member_id: str
    start: tuple[float, float]
    end: tuple[float, float]


@dataclass(frozen=True)
class _InitialUnit:
    member_ids: tuple[str, ...]
    members: tuple[Strut, ...]
    representative: tuple[float, float]
    topology: tuple[int, int] | None
    topology_conflict: bool = False


def assign_initial_zoning(
    result: DXFImportResult,
    *,
    existing_zonings: Sequence[str] = (),
    tolerances: GeometryTolerances | None = None,
) -> InitialZoningOutcome:
    """Assign suggestions without changing recognition membership or geometry."""

    tolerances = tolerances or GeometryTolerances()
    chain_by_waler = _continuous_waler_chains(result.walers, tolerances)
    units = _build_units(result, chain_by_waler)
    groups, diagnostics = _initial_groups(units)
    zone_names = _allocate_zone_names(len(groups), existing_zonings)
    zoning_by_member = {
        member_id: zoning
        for group, zoning in zip(groups, zone_names)
        for unit in group
        for member_id in unit.member_ids
    }
    updated = replace(
        result,
        struts=tuple(
            replace(member, initial_zoning=zoning_by_member.get(member.id, ""))
            for member in result.struts
        ),
    )
    assignments = tuple(
        sorted(zoning_by_member.items(), key=lambda item: (item[1], item[0]))
    )
    return InitialZoningOutcome(
        result=updated,
        assignments=assignments,
        diagnostics=tuple(diagnostics),
    )


def _continuous_waler_chains(
    walers: Sequence[Waler],
    tolerances: GeometryTolerances,
) -> dict[str, int]:
    segments = tuple(
        _WalerSegment(
            member_id=member.id,
            start=_world_line(member)[0],
            end=_world_line(member)[1],
        )
        for member in walers
    )
    parents = list(range(len(segments)))

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = root(first), root(second)
        if first_root != second_root:
            parents[max(first_root, second_root)] = min(first_root, second_root)

    for index, first in enumerate(segments):
        for second_index in range(index + 1, len(segments)):
            if _waler_segments_connect(first, segments[second_index], tolerances):
                union(index, second_index)

    components: dict[int, list[_WalerSegment]] = {}
    for index, segment in enumerate(segments):
        components.setdefault(root(index), []).append(segment)
    ordered_components = sorted(components.values(), key=_chain_geometry_key)
    chain_number_by_root = {
        root(segments.index(component[0])): number
        for number, component in enumerate(ordered_components, start=1)
    }
    return {
        segment.member_id: chain_number_by_root[root(index)]
        for index, segment in enumerate(segments)
    }


def _waler_segments_connect(
    first: _WalerSegment,
    second: _WalerSegment,
    tolerances: GeometryTolerances,
) -> bool:
    first_unit = _unit(first.start, first.end)
    second_unit = _unit(second.start, second.end)
    if first_unit is None or second_unit is None:
        return False
    dot = abs(_dot(first_unit, second_unit))
    angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
    if angle > tolerances.parallel_angle_tolerance_deg:
        return False
    if max(
        _line_distance(first.start, second.start, second.end),
        _line_distance(first.end, second.start, second.end),
        _line_distance(second.start, first.start, first.end),
        _line_distance(second.end, first.start, first.end),
    ) > tolerances.collinear_tolerance_mm:
        return False
    first_range = _projection_range(first, first_unit)
    second_range = _projection_range(second, first_unit)
    overlaps = min(first_range[1], second_range[1]) >= max(
        first_range[0], second_range[0]
    )
    endpoints_connect = min(
        _distance(first_point, second_point)
        for first_point in (first.start, first.end)
        for second_point in (second.start, second.end)
    ) <= tolerances.endpoint_tolerance_mm
    return overlaps or endpoints_connect


def _projection_range(
    segment: _WalerSegment,
    axis: tuple[float, float],
) -> tuple[float, float]:
    values = (_dot(segment.start, axis), _dot(segment.end, axis))
    return min(values), max(values)


def _chain_geometry_key(segments: Sequence[_WalerSegment]) -> tuple[object, ...]:
    lines = sorted(_ordered_world_line(item.start, item.end) for item in segments)
    return lines[0], lines[-1], len(lines)


def _build_units(
    result: DXFImportResult,
    chain_by_waler: dict[str, int],
) -> tuple[_InitialUnit, ...]:
    members = {member.id: member for member in result.struts}
    accepted_pairs = sorted(
        (
            tuple(sorted((candidate.first_strut_id, candidate.second_strut_id)))
            for candidate in result.double_support_candidates
            if candidate.accepted
            and candidate.first_strut_id in members
            and candidate.second_strut_id in members
        ),
        key=lambda pair: tuple(_strut_geometry_key(members[item]) for item in pair),
    )
    grouped: set[str] = set()
    units: list[_InitialUnit] = []
    for first_id, second_id in accepted_pairs:
        if first_id in grouped or second_id in grouped or first_id == second_id:
            continue
        pair = (members[first_id], members[second_id])
        units.append(_make_unit(pair, chain_by_waler))
        grouped.update((first_id, second_id))
    for member in result.struts:
        if member.id not in grouped:
            units.append(_make_unit((member,), chain_by_waler))
    return tuple(sorted(units, key=_unit_geometry_key))


def _make_unit(
    members: Sequence[Strut],
    chain_by_waler: dict[str, int],
) -> _InitialUnit:
    ordered = tuple(sorted(members, key=_strut_geometry_key))
    midpoints = tuple(_midpoint(*_world_line(member)) for member in ordered)
    representative = (
        math.fsum(point[0] for point in midpoints) / len(midpoints),
        math.fsum(point[1] for point in midpoints) / len(midpoints),
    )
    signatures = {
        signature
        for member in ordered
        if (signature := _topology_signature(member, chain_by_waler)) is not None
    }
    topology = next(iter(signatures)) if len(signatures) == 1 else None
    return _InitialUnit(
        member_ids=tuple(member.id for member in ordered),
        members=ordered,
        representative=representative,
        topology=topology,
        topology_conflict=len(signatures) > 1,
    )


def _topology_signature(
    member: Strut,
    chain_by_waler: dict[str, int],
) -> tuple[int, int] | None:
    first = chain_by_waler.get(member.from_waler)
    second = chain_by_waler.get(member.to_waler)
    if first is None or second is None:
        return None
    return tuple(sorted((first, second)))


def _initial_groups(
    units: Sequence[_InitialUnit],
) -> tuple[list[list[_InitialUnit]], list[InitialZoningDiagnostic]]:
    families = _eligibility_families(units)
    groups: list[list[_InitialUnit]] = []
    diagnostics: list[InitialZoningDiagnostic] = []
    for family in families:
        direction = _common_direction(family)
        if direction is None:
            groups.extend([[unit] for unit in family])
            continue
        row_direction = (-direction[1], direction[0])
        ordered = sorted(
            family,
            key=lambda unit: _transverse_key(unit, row_direction),
        )
        ambiguous = _ambiguous_unknown_indexes(ordered)
        current: list[_InitialUnit] = []
        for index, unit in enumerate(ordered):
            if unit.topology_conflict:
                if current:
                    groups.append(current)
                    current = []
                groups.append([unit])
                diagnostics.append(InitialZoningDiagnostic(
                    code=INITIAL_ZONING_TOPOLOGY_CONFLICT,
                    member_ids=unit.member_ids,
                    message="雙路支撐兩 lane 的圍令拓樸不同，已保守地獨立分組。",
                ))
                continue
            if index in ambiguous:
                if current:
                    groups.append(current)
                    current = []
                groups.append([unit])
                diagnostics.append(InitialZoningDiagnostic(
                    code=INITIAL_ZONING_TOPOLOGY_AMBIGUOUS,
                    member_ids=unit.member_ids,
                    message="支撐位於兩個不同圍令拓樸群組之間，已保守地獨立分組。",
                ))
                continue
            if current and not _can_extend_run(current, unit):
                groups.append(current)
                current = []
            if current and _has_intervening_unit(
                current[-1], unit, units, row_direction
            ):
                groups.append(current)
                current = []
            current.append(unit)
        if current:
            groups.append(current)
    groups.sort(key=_group_geometry_key)
    return groups, diagnostics


def _eligibility_families(
    units: Sequence[_InitialUnit],
) -> list[list[_InitialUnit]]:
    pending = list(sorted(units, key=_unit_axis_key))
    families: list[list[_InitialUnit]] = []
    while pending:
        family = [pending.pop(0)]
        remainder = []
        for unit in pending:
            if _units_geometry_eligible((*family, unit)):
                family.append(unit)
            else:
                remainder.append(unit)
        families.append(family)
        pending = remainder
    return families


def _units_geometry_eligible(units: Sequence[_InitialUnit]) -> bool:
    for index, first in enumerate(units):
        for second in units[index + 1:]:
            for first_member in first.members:
                for second_member in second.members:
                    result = validate_support_axes((
                        _axis_fact(first_member),
                        _axis_fact(second_member),
                    ))
                    if not result.is_valid:
                        return False
    return all(
        _axis_fact(member).direction is not None
        for unit in units
        for member in unit.members
    )


def _can_extend_run(current: Sequence[_InitialUnit], unit: _InitialUnit) -> bool:
    if unit.topology_conflict or any(item.topology_conflict for item in current):
        return False
    if not _units_geometry_eligible((*current, unit)):
        return False
    known = {item.topology for item in current if item.topology is not None}
    return unit.topology is None or not known or unit.topology in known


def _ambiguous_unknown_indexes(units: Sequence[_InitialUnit]) -> set[int]:
    result: set[int] = set()
    for index, unit in enumerate(units):
        if unit.topology is not None or unit.topology_conflict:
            continue
        left = next(
            (candidate for candidate in reversed(units[:index]) if candidate.topology),
            None,
        )
        right = next(
            (candidate for candidate in units[index + 1:] if candidate.topology),
            None,
        )
        if (
            left is not None
            and right is not None
            and left.topology != right.topology
            and _units_geometry_eligible((left, unit))
            and _units_geometry_eligible((unit, right))
        ):
            result.add(index)
    return result


def _has_intervening_unit(
    first: _InitialUnit,
    second: _InitialUnit,
    all_units: Sequence[_InitialUnit],
    row_direction: tuple[float, float],
) -> bool:
    first_projection = _project(first.representative, row_direction)
    second_projection = _project(second.representative, row_direction)
    lower, upper = sorted((first_projection, second_projection))
    for candidate in all_units:
        if candidate is first or candidate is second:
            continue
        projection = _project(candidate.representative, row_direction)
        if lower < projection < upper:
            return True
    return False


def _common_direction(
    units: Sequence[_InitialUnit],
) -> tuple[float, float] | None:
    axes = tuple(
        _axis_fact(member)
        for unit in units
        for member in unit.members
    )
    # Shared lanes are an initial-grouping ordering exception, so derive the
    # family direction from deterministic physical axes without validating
    # the two lanes against each other here.
    valid = tuple(axis for axis in axes if axis.direction is not None)
    if not valid:
        return None
    doubled_cosine = math.fsum(
        axis.direction[0] ** 2 - axis.direction[1] ** 2 for axis in valid
    )
    doubled_sine = math.fsum(
        2.0 * axis.direction[0] * axis.direction[1] for axis in valid
    )
    if math.hypot(doubled_cosine, doubled_sine) <= 1e-12:
        return None
    angle = 0.5 * math.atan2(doubled_sine, doubled_cosine)
    direction = (math.cos(angle), math.sin(angle))
    if direction[0] < 0 or (abs(direction[0]) <= 1e-12 and direction[1] < 0):
        direction = (-direction[0], -direction[1])
    return direction


def _axis_fact(member: Strut):
    start, end = _world_line(member)
    return build_axis_fact(
        member.id,
        LineSegment(Point(*start), Point(*end)),
    )


def _allocate_zone_names(count: int, existing: Sequence[str]) -> tuple[str, ...]:
    used = {str(value).strip() for value in existing if str(value).strip()}
    result: list[str] = []
    number = 1
    while len(result) < count:
        candidate = f"DXF-Z{number}"
        number += 1
        if candidate in used:
            continue
        used.add(candidate)
        result.append(candidate)
    return tuple(result)


def _world_line(member: Waler | Strut):
    return (
        tuple(member.world_start or member.start),
        tuple(member.world_end or member.end),
    )


def _midpoint(
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[float, float]:
    return (start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0


def _ordered_world_line(start, end):
    return (start, end) if start <= end else (end, start)


def _strut_geometry_key(member: Strut) -> tuple[object, ...]:
    start, end = _world_line(member)
    return _ordered_world_line(start, end), tuple(sorted(member.source_handles))


def _unit_geometry_key(unit: _InitialUnit) -> tuple[object, ...]:
    return (
        unit.representative,
        tuple(_strut_geometry_key(member) for member in unit.members),
    )


def _unit_axis_key(unit: _InitialUnit) -> tuple[object, ...]:
    directions = [
        fact.direction
        for fact in (_axis_fact(member) for member in unit.members)
        if fact.direction is not None
    ]
    angle = min(
        (math.atan2(direction[1], direction[0]) for direction in directions),
        default=math.inf,
    )
    lengths = sorted(
        _axis_fact(member).length for member in unit.members
    )
    return angle, tuple(lengths), _unit_geometry_key(unit)


def _transverse_key(
    unit: _InitialUnit,
    row_direction: tuple[float, float],
) -> tuple[object, ...]:
    return _project(unit.representative, row_direction), _unit_geometry_key(unit)


def _group_geometry_key(group: Sequence[_InitialUnit]) -> tuple[object, ...]:
    return min(_unit_geometry_key(unit) for unit in group)


def _project(point, direction):
    return float(point[0]) * direction[0] + float(point[1]) * direction[1]


__all__ = [
    "INITIAL_ZONING_TOPOLOGY_AMBIGUOUS",
    "INITIAL_ZONING_TOPOLOGY_CONFLICT",
    "InitialZoningDiagnostic",
    "InitialZoningOutcome",
    "assign_initial_zoning",
]
