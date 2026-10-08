"""Pure Brace endpoint-to-Waler connection resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from .geometry import (
    Point,
    _dot,
    _line_segment_intersection_point,
    _project_onto_segment,
    _segment_distance,
    _unit,
    _vector,
)
from .models import Brace, GeometryTolerances, Waler


BraceEndpointStatus = Literal["direct", "axis_extension", "missing", "ambiguous"]


@dataclass(frozen=True)
class BraceWalerIntersection:
    """One outward-ray intersection with a finite formal Waler segment."""

    waler_id: str
    point: Point
    extension_distance: float
    waler_source_handles: tuple[str, ...]
    waler_source_entity_types: tuple[str, ...]


@dataclass(frozen=True)
class BraceEndpointResolution:
    """Resolved connection state for one physical Brace endpoint."""

    endpoint_name: Literal["start", "end"]
    original_point: Point
    status: BraceEndpointStatus
    adopted_point: Point
    waler_id: str = ""
    extension_distance: float = 0.0
    competing_waler_ids: tuple[str, ...] = ()
    waler_source_handles: tuple[str, ...] = ()
    waler_source_entity_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class BraceConnectionResolution:
    """Complete, deterministic resolution for both Brace endpoints."""

    start: BraceEndpointResolution
    end: BraceEndpointResolution
    same_waler: bool = False


def _waler_line(waler: Waler) -> tuple[Point, Point]:
    return waler.world_start or waler.start, waler.world_end or waler.end


def _geometry_key(waler: Waler) -> tuple[Point, Point, str]:
    start, end = _waler_line(waler)
    ordered = (start, end) if start <= end else (end, start)
    return ordered[0], ordered[1], waler.id


def outward_waler_intersections(
    origin: Point,
    outward_direction: Point,
    walers: Sequence[Waler],
    tolerances: GeometryTolerances,
) -> tuple[BraceWalerIntersection, ...]:
    """Enumerate eligible finite-Waler intersections on an outward Brace ray."""

    line_end = (
        origin[0] + outward_direction[0],
        origin[1] + outward_direction[1],
    )
    candidates: list[tuple[float, tuple[Point, Point, str], BraceWalerIntersection]] = []
    for waler in walers:
        intersection = _line_segment_intersection_point(
            (origin, line_end),
            _waler_line(waler),
            tolerances.endpoint_tolerance_mm,
        )
        if intersection is None:
            continue
        extension_distance = _dot(
            _vector(origin, intersection),
            outward_direction,
        )
        if extension_distance <= 0.0:
            continue
        if extension_distance > tolerances.maximum_brace_axis_extension_mm:
            continue
        candidate = BraceWalerIntersection(
            waler_id=waler.id,
            point=intersection,
            extension_distance=extension_distance,
            waler_source_handles=waler.source_handles,
            waler_source_entity_types=waler.source_entity_types,
        )
        candidates.append((extension_distance, _geometry_key(waler), candidate))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return tuple(item[2] for item in candidates)


def _direct_resolution(
    endpoint_name: Literal["start", "end"],
    point: Point,
    walers: Sequence[Waler],
    tolerances: GeometryTolerances,
) -> BraceEndpointResolution | None:
    ranked = sorted(
        (
            _segment_distance(point, *_waler_line(waler)),
            waler.id,
            waler,
        )
        for waler in walers
    )
    if not ranked or ranked[0][0] > tolerances.connection_tolerance_mm:
        return None
    distance, _key, nearest = ranked[0]
    competing = tuple(
        item[2].id
        for item in ranked[1:]
        if item[0] <= tolerances.connection_tolerance_mm
        and item[0] - distance <= tolerances.ambiguous_connection_delta_mm
    )
    return BraceEndpointResolution(
        endpoint_name=endpoint_name,
        original_point=point,
        status="direct",
        adopted_point=_project_onto_segment(point, *_waler_line(nearest)),
        waler_id=nearest.id,
        competing_waler_ids=competing,
        waler_source_handles=nearest.source_handles,
        waler_source_entity_types=nearest.source_entity_types,
    )


def _resolve_endpoint(
    endpoint_name: Literal["start", "end"],
    point: Point,
    outward_direction: Point | None,
    walers: Sequence[Waler],
    tolerances: GeometryTolerances,
    *,
    allow_extension: bool,
) -> BraceEndpointResolution:
    direct = _direct_resolution(endpoint_name, point, walers, tolerances)
    if direct is not None:
        return direct
    if outward_direction is None or not allow_extension:
        return BraceEndpointResolution(endpoint_name, point, "missing", point)

    intersections = outward_waler_intersections(
        point,
        outward_direction,
        walers,
        tolerances,
    )
    if not intersections:
        return BraceEndpointResolution(endpoint_name, point, "missing", point)
    nearest = intersections[0]
    competing = tuple(
        item.waler_id
        for item in intersections[1:]
        if item.extension_distance - nearest.extension_distance
        <= tolerances.ambiguous_connection_delta_mm
    )
    if competing:
        return BraceEndpointResolution(
            endpoint_name,
            point,
            "ambiguous",
            point,
            competing_waler_ids=(nearest.waler_id, *competing),
        )
    return BraceEndpointResolution(
        endpoint_name=endpoint_name,
        original_point=point,
        status="axis_extension",
        adopted_point=nearest.point,
        waler_id=nearest.waler_id,
        extension_distance=nearest.extension_distance,
        waler_source_handles=nearest.waler_source_handles,
        waler_source_entity_types=nearest.waler_source_entity_types,
    )


def resolve_brace_waler_connection(
    brace: Brace,
    walers: Sequence[Waler],
    tolerances: GeometryTolerances | None = None,
) -> BraceConnectionResolution:
    """Resolve direct and outward-axis connections without mutating models."""

    tolerances = tolerances or GeometryTolerances()
    start = brace.world_start or brace.start
    end = brace.world_end or brace.end
    start_to_end = _unit(start, end)
    allow_extension = brace.selection_source == "auto"
    start_resolution = _resolve_endpoint(
        "start",
        start,
        None if start_to_end is None else (-start_to_end[0], -start_to_end[1]),
        walers,
        tolerances,
        allow_extension=allow_extension,
    )
    end_resolution = _resolve_endpoint(
        "end",
        end,
        start_to_end,
        walers,
        tolerances,
        allow_extension=allow_extension,
    )
    same_waler = bool(
        start_resolution.waler_id
        and start_resolution.waler_id == end_resolution.waler_id
    )
    return BraceConnectionResolution(
        start=start_resolution,
        end=end_resolution,
        same_waler=same_waler,
    )


__all__ = [
    "BraceConnectionResolution",
    "BraceEndpointResolution",
    "BraceWalerIntersection",
    "outward_waler_intersections",
    "resolve_brace_waler_connection",
]
