"""Pure geometry recognition for RC Walers represented by DXF HATCH bounds.

The importer owns ezdxf/OCS handling.  This module receives only immutable WCS
line segments and returns a terminal recognized/failed/ambiguous outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal, Sequence

from .geometry import Point
from .models import GeometryTolerances


Line = tuple[Point, Point]
HatchWalerStatus = Literal["recognized", "failed", "ambiguous"]

_FLOAT_EPSILON = 1e-9
HATCH_WALER_CONFIDENCE = 0.99


@dataclass(frozen=True)
class HatchBoundaryPath:
    """One HATCH boundary path expressed as unordered WCS line segments."""

    segments: tuple[Line, ...]
    is_external: bool = False
    unsupported_geometry: tuple[str, ...] = ()


@dataclass(frozen=True)
class HatchWalerSource:
    """One authoritative Waler HATCH source scope."""

    handle: str
    layer: str
    paths: tuple[HatchBoundaryPath, ...]


@dataclass(frozen=True)
class HatchWalerRecognition:
    """Terminal result for one HATCH source."""

    status: HatchWalerStatus
    code: str
    message: str
    source_handle: str
    source_layer: str
    axis: Line | None = None
    source_width: float = 0.0
    boundary_lines: tuple[Line, ...] = ()
    exterior_segments: tuple[Line, ...] = ()
    material_spec: str = "RC"
    material_spec_source: str = "auto_hatch"
    confidence: float = HATCH_WALER_CONFIDENCE


@dataclass(frozen=True)
class _ClosedLoop:
    points: tuple[Point, ...]
    source_segments: tuple[Line, ...]
    is_external: bool
    signed_area: float


def _distance(first: Point, second: Point) -> float:
    return math.hypot(second[0] - first[0], second[1] - first[1])


def _vector(line: Line) -> Point:
    return line[1][0] - line[0][0], line[1][1] - line[0][1]


def _length(line: Line) -> float:
    return _distance(*line)


def _dot(first: Point, second: Point) -> float:
    return first[0] * second[0] + first[1] * second[1]


def _cross(first: Point, second: Point) -> float:
    return first[0] * second[1] - first[1] * second[0]


def _unit(line: Line) -> Point | None:
    length = _length(line)
    if length <= _FLOAT_EPSILON:
        return None
    return (line[1][0] - line[0][0]) / length, (line[1][1] - line[0][1]) / length


def _canonical_unit(line: Line) -> Point | None:
    unit = _unit(line)
    if unit is None:
        return None
    if unit[0] < -_FLOAT_EPSILON or (
        abs(unit[0]) <= _FLOAT_EPSILON and unit[1] < 0.0
    ):
        return -unit[0], -unit[1]
    return unit


def _ordered_line(first: Point, second: Point) -> Line:
    return (first, second) if first <= second else (second, first)


def _angle_difference_deg(first: Line, second: Line) -> float:
    first_unit = _unit(first)
    second_unit = _unit(second)
    if first_unit is None or second_unit is None:
        return 180.0
    cosine = max(-1.0, min(1.0, abs(_dot(first_unit, second_unit))))
    return math.degrees(math.acos(cosine))


def _projection_overlap_ratio(first: Line, second: Line) -> float:
    axis = _canonical_unit(first)
    if axis is None:
        return 0.0
    first_values = tuple(_dot(point, axis) for point in first)
    second_values = tuple(_dot(point, axis) for point in second)
    overlap = max(
        0.0,
        min(max(first_values), max(second_values))
        - max(min(first_values), min(second_values)),
    )
    shorter = min(_length(first), _length(second))
    return overlap / shorter if shorter > _FLOAT_EPSILON else 0.0


def _cluster_endpoints(
    segments: Sequence[Line],
    tolerance: float,
) -> tuple[tuple[Point, ...], tuple[tuple[int, int], ...]]:
    raw_points = tuple(point for segment in segments for point in segment)
    parents = list(range(len(raw_points)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root = find(first)
        second_root = find(second)
        if first_root != second_root:
            parents[max(first_root, second_root)] = min(first_root, second_root)

    for first in range(len(raw_points)):
        for second in range(first + 1, len(raw_points)):
            if _distance(raw_points[first], raw_points[second]) <= tolerance:
                union(first, second)

    members: dict[int, list[Point]] = {}
    for index, point in enumerate(raw_points):
        members.setdefault(find(index), []).append(point)
    ordered_groups = sorted(
        members.values(),
        key=lambda group: min(group),
    )
    nodes = tuple(
        (
            sum(point[0] for point in group) / len(group),
            sum(point[1] for point in group) / len(group),
        )
        for group in ordered_groups
    )
    root_to_node = {
        find(raw_points.index(min(group))): node_index
        for node_index, group in enumerate(ordered_groups)
    }
    # ``raw_points.index`` above is safe for the representative but duplicate
    # coordinates can belong to the same union.  Populate every root explicitly.
    for node_index, group in enumerate(ordered_groups):
        representative = next(
            index for index, point in enumerate(raw_points) if point in group
        )
        root_to_node[find(representative)] = node_index
    edges = tuple(
        (
            root_to_node[find(index * 2)],
            root_to_node[find(index * 2 + 1)],
        )
        for index in range(len(segments))
    )
    return nodes, edges


def _closed_loop_from_path(
    path: HatchBoundaryPath,
    tolerances: GeometryTolerances,
) -> tuple[_ClosedLoop | None, str]:
    if path.unsupported_geometry:
        kinds = ", ".join(sorted(set(path.unsupported_geometry)))
        return None, f"HATCH boundary 含第一版不支援的幾何：{kinds}。"
    if len(path.segments) < 3:
        return None, "HATCH boundary 線段不足，無法形成封閉外框。"
    if any(_length(segment) <= _FLOAT_EPSILON for segment in path.segments):
        return None, "HATCH boundary 含零長度線段。"

    nodes, edges = _cluster_endpoints(
        path.segments,
        tolerances.endpoint_tolerance_mm,
    )
    if any(first == second for first, second in edges):
        return None, "HATCH boundary 端點在容差內塌縮，無法形成外框。"

    adjacency: dict[int, list[tuple[int, int]]] = {index: [] for index in range(len(nodes))}
    for edge_index, (first, second) in enumerate(edges):
        adjacency[first].append((second, edge_index))
        adjacency[second].append((first, edge_index))
    if not adjacency or any(len(neighbors) != 2 for neighbors in adjacency.values()):
        return None, "HATCH boundary 不連續或具有分岔，無法形成唯一封閉 traversal。"

    start = min(adjacency, key=lambda index: nodes[index])
    first_neighbor = min(adjacency[start], key=lambda item: nodes[item[0]])
    traversal = [start]
    visited_edges: set[int] = set()
    previous: int | None = None
    current = start
    next_node, next_edge = first_neighbor
    while True:
        if next_edge in visited_edges:
            return None, "HATCH boundary traversal 重複使用 edge。"
        visited_edges.add(next_edge)
        previous, current = current, next_node
        if current == start:
            break
        traversal.append(current)
        options = [
            item
            for item in adjacency[current]
            if item[1] not in visited_edges and item[0] != previous
        ]
        if len(options) != 1:
            return None, "HATCH boundary 無法建立唯一封閉 traversal。"
        next_node, next_edge = options[0]
    if len(visited_edges) != len(edges):
        return None, "HATCH boundary 含互不連通的 edge。"

    points = [nodes[index] for index in traversal]
    changed = True
    while changed and len(points) > 3:
        changed = False
        for index in range(len(points)):
            previous_point = points[index - 1]
            current_point = points[index]
            next_point = points[(index + 1) % len(points)]
            before = (previous_point, current_point)
            after = (current_point, next_point)
            if (
                _angle_difference_deg(before, after)
                <= tolerances.parallel_angle_tolerance_deg
                and _dot(_vector(before), _vector(after)) > 0.0
            ):
                del points[index]
                changed = True
                break

    if len(points) < 3:
        return None, "HATCH boundary 沒有可用面積。"
    signed_area = sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(points, points[1:] + points[:1])
    ) / 2.0
    if abs(signed_area) <= _FLOAT_EPSILON:
        return None, "HATCH boundary 面積為零。"
    canonical = _canonical_cycle(tuple(points))
    if _self_intersects(canonical):
        return None, "HATCH boundary 自交，無法建立單一外框。"
    return (
        _ClosedLoop(
            canonical,
            tuple(sorted(_ordered_line(*segment) for segment in path.segments)),
            path.is_external,
            signed_area,
        ),
        "",
    )


def _canonical_cycle(points: tuple[Point, ...]) -> tuple[Point, ...]:
    def rotations(values: tuple[Point, ...]) -> tuple[tuple[Point, ...], ...]:
        return tuple(values[index:] + values[:index] for index in range(len(values)))

    forward = min(rotations(points))
    backward = min(rotations(tuple(reversed(points))))
    return min(forward, backward)


def _orientation(first: Point, second: Point, third: Point) -> float:
    return _cross(
        (second[0] - first[0], second[1] - first[1]),
        (third[0] - first[0], third[1] - first[1]),
    )


def _properly_intersects(first: Line, second: Line) -> bool:
    first_a = _orientation(first[0], first[1], second[0])
    first_b = _orientation(first[0], first[1], second[1])
    second_a = _orientation(second[0], second[1], first[0])
    second_b = _orientation(second[0], second[1], first[1])
    return (
        first_a * first_b < -_FLOAT_EPSILON
        and second_a * second_b < -_FLOAT_EPSILON
    )


def _self_intersects(points: Sequence[Point]) -> bool:
    segments = tuple(zip(points, (*points[1:], points[0])))
    for first_index, first in enumerate(segments):
        for second_index in range(first_index + 1, len(segments)):
            if second_index in {
                first_index,
                (first_index + 1) % len(segments),
                (first_index - 1) % len(segments),
            }:
                continue
            if _properly_intersects(first, segments[second_index]):
                return True
    return False


def _point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if (current[1] > point[1]) != (previous[1] > point[1]):
            crossing_x = (
                (previous[0] - current[0])
                * (point[1] - current[1])
                / (previous[1] - current[1])
                + current[0]
            )
            if point[0] < crossing_x:
                inside = not inside
        previous = current
    return inside


def _select_exterior(loops: Sequence[_ClosedLoop]) -> tuple[_ClosedLoop | None, str]:
    explicitly_external = tuple(loop for loop in loops if loop.is_external)
    if len(explicitly_external) > 1:
        return None, "HATCH 含多個 external boundary，無法唯一對應一支圍令。"
    exterior = (
        explicitly_external[0]
        if explicitly_external
        else max(loops, key=lambda loop: abs(loop.signed_area))
    )
    for loop in loops:
        if loop is exterior:
            continue
        if not all(_point_in_polygon(point, exterior.points) for point in loop.points):
            return None, "HATCH 含多個互不連續外邊界，無法唯一對應一支圍令。"
    return exterior, ""


def _strip_geometry(
    loop: _ClosedLoop,
    tolerances: GeometryTolerances,
) -> tuple[Line, float, tuple[Line, Line]] | None:
    points = loop.points
    if len(points) != 4:
        return None
    edges: tuple[Line, ...] = tuple(zip(points, (*points[1:], points[0])))
    pair_options: list[tuple[float, Line, Line]] = []
    for first_index, second_index in ((0, 2), (1, 3)):
        first = edges[first_index]
        second = edges[second_index]
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
        if abs(_length(first) - _length(second)) > tolerances.width_tolerance_mm:
            continue
        pair_options.append((_length(first) + _length(second), first, second))
    if not pair_options:
        return None
    pair_options.sort(key=lambda item: item[0], reverse=True)
    _score, first_rail, second_rail = pair_options[0]
    axis_unit = _canonical_unit(first_rail)
    if axis_unit is None:
        return None
    normal = -axis_unit[1], axis_unit[0]
    longitudinal = tuple(_dot(point, axis_unit) for point in points)
    transverse = tuple(_dot(point, normal) for point in points)
    start_station = min(longitudinal)
    end_station = max(longitudinal)
    first_side = min(transverse)
    second_side = max(transverse)
    length = end_station - start_station
    width = second_side - first_side
    if (
        length < tolerances.minimum_component_length_mm
        or width <= _FLOAT_EPSILON
        or length / width < tolerances.minimum_slenderness_ratio
    ):
        return None
    center_side = (first_side + second_side) / 2.0

    def point_at(station: float, side: float) -> Point:
        return (
            axis_unit[0] * station + normal[0] * side,
            axis_unit[1] * station + normal[1] * side,
        )

    axis = _ordered_line(
        point_at(start_station, center_side),
        point_at(end_station, center_side),
    )
    boundaries = (
        _ordered_line(
            point_at(start_station, first_side),
            point_at(end_station, first_side),
        ),
        _ordered_line(
            point_at(start_station, second_side),
            point_at(end_station, second_side),
        ),
    )
    return axis, width, tuple(sorted(boundaries))


def recognize_hatch_waler(
    source: HatchWalerSource,
    tolerances: GeometryTolerances | None = None,
) -> HatchWalerRecognition:
    """Recognize one authoritative Waler HATCH source in WCS."""

    settings = tolerances or GeometryTolerances()
    if not source.paths:
        return _failure(source, "HATCH_WALER_BOUNDARY_INVALID", "HATCH 沒有 boundary path。")
    loops: list[_ClosedLoop] = []
    for path in source.paths:
        loop, reason = _closed_loop_from_path(path, settings)
        if loop is None:
            code = (
                "HATCH_WALER_UNSUPPORTED_BOUNDARY"
                if path.unsupported_geometry
                else "HATCH_WALER_BOUNDARY_INVALID"
            )
            return _failure(source, code, reason)
        loops.append(loop)
    exterior, reason = _select_exterior(loops)
    if exterior is None:
        return HatchWalerRecognition(
            "ambiguous",
            "HATCH_WALER_AMBIGUOUS_BOUNDARY",
            reason,
            source.handle,
            source.layer,
            exterior_segments=tuple(
                segment for loop in loops for segment in loop.source_segments
            ),
        )
    geometry = _strip_geometry(exterior, settings)
    if geometry is None:
        return _failure(
            source,
            "HATCH_WALER_ENGINEERING_LINE_FAILED",
            "HATCH 外邊界無法唯一建立完整直線長條圍令工程軸。",
            exterior.source_segments,
        )
    axis, width, boundaries = geometry
    return HatchWalerRecognition(
        "recognized",
        "HATCH_WALER_RECOGNIZED",
        "已由 HATCH 封閉外邊界建立 RC 圍令。",
        source.handle,
        source.layer,
        axis=axis,
        source_width=width,
        boundary_lines=boundaries,
        exterior_segments=exterior.source_segments,
    )


def _failure(
    source: HatchWalerSource,
    code: str,
    message: str,
    exterior_segments: Sequence[Line] = (),
) -> HatchWalerRecognition:
    return HatchWalerRecognition(
        "failed",
        code,
        message,
        source.handle,
        source.layer,
        exterior_segments=tuple(exterior_segments),
    )


__all__ = [
    "HATCH_WALER_CONFIDENCE",
    "HatchBoundaryPath",
    "HatchWalerRecognition",
    "HatchWalerSource",
    "recognize_hatch_waler",
]
