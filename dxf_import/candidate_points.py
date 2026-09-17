"""Candidate-point generation, association, and model updates."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
import math
from typing import Any, Iterable, Sequence

from .geometry import (
    Point,
    _closest_points_between_segments,
    _distance,
    _dot,
    _length,
    _line_segment_intersection_point,
    _midpoint,
    _project_onto_segment,
    _same_point,
    _segment_distance,
    _segment_intersection_point,
    _segments_have_parallel_overlap,
    _unit,
    _vector,
)
from .models import (
    AuxiliaryComponent,
    Beam,
    BeamCrossing,
    Brace,
    CandidatePoint,
    Column,
    ComponentAssociation,
    CoordinateSystem,
    CornerBrace,
    DoubleSupportCandidate,
    DXFImportError,
    DXFImportResult,
    EngineeringLineCandidate,
    GeometryTolerances,
    SourceGeometry,
    Strut,
    ValidationMessage,
    Waler,
    COMPONENT_ASSOCIATION_CODES,
    CONNECTION_VALIDATION_CODES,
    ERROR_SEVERITIES,
    apply_coordinate_system,
)
from .validation import (
    _member_model_role,
    _result_members,
    candidate_point_by_id,
    validate_candidate_point_pair,
    validate_duplicate_engineering_members,
)
from .support_pairing import (
    detect_double_support_candidates,
    preserve_double_support_decisions,
)


class CandidatePointStore:
    """Canonical candidate-point repository.

    The builder-facing ``add()/points()`` API keeps the original per-component
    deduplication behaviour.  The component index is the UI-facing API: widgets
    retain only IDs and always resolve the immutable point through this store.
    """

    def __init__(self, tolerance: float) -> None:
        self.tolerance = max(float(tolerance), 1e-9)
        self._points: list[CandidatePoint] = []
        self._component_points: dict[str, tuple[CandidatePoint, ...]] = {}
        self._component_point_index: dict[
            tuple[str, str], CandidatePoint
        ] = {}

    def add(
        self,
        world_point: Point,
        *,
        point_type: str,
        label: str,
        source_handles: Sequence[str] = (),
        source_entity_types: Sequence[str] = (),
        recommended_for: Sequence[str] = (),
        score: float = 0.0,
        valid_for: Sequence[str] = ("start", "end"),
        preferred_id: str = "",
    ) -> str:
        point = float(world_point[0]), float(world_point[1])
        if not all(math.isfinite(value) for value in point):
            return ""
        for index, existing in enumerate(self._points):
            if not _same_point(existing.world_point, point, self.tolerance):
                continue
            use_new_description = score > existing.score
            merged = replace(
                existing,
                point_type=point_type if use_new_description else existing.point_type,
                label=label if use_new_description else existing.label,
                source_handles=tuple(
                    sorted({*existing.source_handles, *map(str, source_handles)})
                ),
                source_entity_types=tuple(
                    sorted(
                        {
                            *existing.source_entity_types,
                            *map(str, source_entity_types),
                        }
                    )
                ),
                recommended_for=tuple(
                    item
                    for item in ("start", "end")
                    if item in {*existing.recommended_for, *recommended_for}
                ),
                score=max(existing.score, float(score)),
                point_types=tuple(
                    dict.fromkeys(
                        (
                            *existing.point_types,
                            existing.point_type,
                            point_type,
                        )
                    )
                ),
                valid_for=tuple(
                    item
                    for item in ("start", "end")
                    if item in {*existing.valid_for, *valid_for}
                ),
            )
            self._points[index] = merged
            return merged.id
        identifier = preferred_id or f"P{len(self._points) + 1:02d}"
        used_ids = {item.id for item in self._points}
        if identifier in used_ids:
            identifier = f"P{len(self._points) + 1:02d}"
        candidate = CandidatePoint(
            id=identifier,
            world_point=point,
            local_point=point,
            point_type=point_type,
            label=label,
            source_handles=tuple(sorted(set(map(str, source_handles)))),
            source_entity_types=tuple(
                sorted(set(map(str, source_entity_types)))
            ),
            recommended_for=tuple(
                item for item in ("start", "end") if item in set(recommended_for)
            ),
            score=max(0.0, min(1.0, float(score))),
            point_types=(point_type,),
            valid_for=tuple(
                item for item in ("start", "end") if item in set(valid_for)
            ),
        )
        self._points.append(candidate)
        return identifier

    def points(self) -> tuple[CandidatePoint, ...]:
        return tuple(self._points)

    def rebuild(
        self,
        members: Iterable[Waler | Strut | Brace | AuxiliaryComponent],
    ) -> None:
        """Replace the UI index after recognition or coordinate conversion."""

        self._component_points.clear()
        self._component_point_index.clear()
        for member in members:
            self.register_component(member.id, member.candidate_points)

    def register_component(
        self,
        component_id: str,
        points: Sequence[CandidatePoint],
    ) -> None:
        identifier = str(component_id)
        candidates = tuple(
            point
            if point.component_id == identifier
            else replace(point, component_id=identifier)
            for point in points
        )
        self._component_points[identifier] = candidates
        stale_keys = [
            key for key in self._component_point_index if key[0] == identifier
        ]
        for key in stale_keys:
            del self._component_point_index[key]
        for point in candidates:
            self._component_point_index[(identifier, point.id)] = point

    def component_points(self, component_id: str) -> tuple[CandidatePoint, ...]:
        return self._component_points.get(str(component_id), ())

    def get(self, component_id: str, point_id: str) -> CandidatePoint | None:
        return self._component_point_index.get(
            (str(component_id), str(point_id))
        )

    def has_component(self, component_id: str) -> bool:
        return str(component_id) in self._component_points

    def component_ids(self) -> tuple[str, ...]:
        return tuple(self._component_points)


class CandidatePointBuilder:
    """Build engineering-relevant endpoint choices from recognition evidence."""

    def __init__(
        self,
        source_geometry: Sequence[SourceGeometry],
        walers: Sequence[Waler],
        tolerances: GeometryTolerances,
    ) -> None:
        self.source_geometry = tuple(source_geometry)
        self.walers = tuple(walers)
        self.tolerances = tolerances

    @staticmethod
    def _role(member: Waler | Strut | Brace | AuxiliaryComponent) -> str:
        if isinstance(member, Waler):
            return "waler"
        if isinstance(member, Strut):
            return "strut"
        if isinstance(member, Brace):
            return "brace"
        if isinstance(member, Column):
            return "column"
        if isinstance(member, Beam):
            return "beam"
        return "corner_brace"

    def build(
        self,
        member: Waler | Strut | Brace | AuxiliaryComponent,
    ) -> Waler | Strut | Brace | AuxiliaryComponent:
        # Endpoint choices must preserve distinct section edges; the component
        # duplicate tolerance (often 50 mm) is intentionally capped at 1 mm.
        store = CandidatePointStore(
            min(
                self.tolerances.duplicate_tolerance_mm,
                self.tolerances.endpoint_tolerance_mm,
                1.0,
            )
        )
        world_start = member.world_start or member.start
        world_end = member.world_end or member.end
        role = self._role(member)
        if isinstance(member, Waler):
            start_meta = end_meta = (
                "waler_inner_line_endpoint",
                "圍令內側線端點",
                member.source_handles,
                member.source_entity_types,
            )
        elif isinstance(member, (Strut, Brace)):
            def connected_endpoint_meta(waler_id: str) -> tuple[
                str,
                str,
                tuple[str, ...],
                tuple[str, ...],
            ]:
                waler = next(
                    (candidate for candidate in self.walers if candidate.id == waler_id),
                    None,
                )
                if waler is None:
                    return (
                        "recognized_engineering_endpoint",
                        "自動辨識工程線端點",
                        member.source_handles,
                        member.source_entity_types,
                    )
                return (
                    "waler_intersection",
                    f"與 {waler.id} 圍令內側線交點",
                    tuple(sorted({*member.source_handles, *waler.source_handles})),
                    tuple(
                        sorted(
                            {
                                *member.source_entity_types,
                                *waler.source_entity_types,
                            }
                        )
                    ),
                )

            start_meta = connected_endpoint_meta(member.from_waler)
            end_meta = connected_endpoint_meta(member.to_waler)
        else:
            start_meta = end_meta = (
                "recognized_engineering_endpoint",
                "自動辨識構件端點",
                member.source_handles,
                member.source_entity_types,
            )
        start_type, start_label, start_handles, start_entity_types = start_meta
        end_type, end_label, end_handles, end_entity_types = end_meta
        start_id = store.add(
            world_start,
            point_type=start_type,
            label=f"{start_label}（起點）",
            source_handles=start_handles,
            source_entity_types=start_entity_types,
            recommended_for=("start",),
            score=1.0,
            valid_for=("start",),
        )
        end_id = store.add(
            world_end,
            point_type=end_type,
            label=f"{end_label}（終點）",
            source_handles=end_handles,
            source_entity_types=end_entity_types,
            recommended_for=("end",),
            score=1.0,
            valid_for=("end",),
        )

        for line in member.line_candidates:
            label = line.label or "辨識候選工程線"
            point_type = (
                "waler_inner_line_endpoint"
                if isinstance(member, Waler) and line.id == member.selected_candidate_id
                else "recognized_line_endpoint"
            )
            store.add(
                line.world_start,
                point_type=point_type,
                label=f"{label}起點",
                source_handles=member.source_handles,
                source_entity_types=member.source_entity_types,
                score=0.90,
                valid_for=("start",),
            )
            store.add(
                line.world_end,
                point_type=point_type,
                label=f"{label}終點",
                source_handles=member.source_handles,
                source_entity_types=member.source_entity_types,
                score=0.90,
                valid_for=("end",),
            )

        if isinstance(member, Beam):
            for index, point in enumerate(member.world_path[1:-1], 2):
                store.add(
                    point,
                    point_type="beam_path_vertex",
                    label=f"托梁路徑轉折點 {index}",
                    source_handles=member.source_handles,
                    source_entity_types=member.source_entity_types,
                    score=0.88,
                    valid_for=(
                        ("start",)
                        if _distance(point, world_start)
                        <= _distance(point, world_end)
                        else ("end",)
                    ),
                )

        axis = _unit(world_start, world_end)
        length = _length(world_start, world_end)
        raw_options: list[
            tuple[float, Point, SourceGeometry, tuple[str, ...], str]
        ] = []
        if axis is not None:
            member_handles = set(member.source_handles)
            for geometry in self.source_geometry:
                if geometry.role != role:
                    continue
                if geometry.source_handle not in member_handles:
                    continue
                for point in geometry.points:
                    along = _dot(_vector(world_start, point), axis)
                    endpoint_distance = min(
                        _distance(point, world_start),
                        _distance(point, world_end),
                    )
                    score = (
                        0.82
                        if endpoint_distance
                        <= self.tolerances.connection_tolerance_mm
                        else 0.58
                    )
                    if along < length / 2:
                        valid_for = ("start",)
                        side_label = "起點側"
                    elif along > length / 2:
                        valid_for = ("end",)
                        side_label = "終點側"
                    else:
                        valid_for = ("start", "end")
                        side_label = "中心"
                    raw_options.append(
                        (score, point, geometry, valid_for, side_label)
                    )
        raw_options.sort(key=lambda item: (-item[0], item[1][0], item[1][1]))
        for score, point, geometry, valid_for, side_label in raw_options:
            store.add(
                point,
                point_type="source_geometry_vertex",
                label=f"原始外框頂點（{side_label}）",
                source_handles=(geometry.source_handle,),
                source_entity_types=(geometry.source_entity_type,),
                score=score,
                valid_for=valid_for,
            )

        if isinstance(member, (Strut, Brace)) and axis is not None:
            for waler in self.walers:
                direct = _segment_intersection_point(
                    (world_start, world_end),
                    (waler.world_start or waler.start, waler.world_end or waler.end),
                    self.tolerances.endpoint_tolerance_mm,
                )
                extended = direct or _line_segment_intersection_point(
                    (world_start, world_end),
                    (waler.world_start or waler.start, waler.world_end or waler.end),
                    self.tolerances.endpoint_tolerance_mm,
                )
                if extended is None:
                    continue
                along = _dot(_vector(world_start, extended), axis)
                if not (
                    -self.tolerances.connection_tolerance_mm
                    <= along
                    <= length + self.tolerances.connection_tolerance_mm
                ):
                    continue
                store.add(
                    extended,
                    point_type=(
                        "waler_intersection"
                        if direct is not None
                        else "extended_axis_waler_intersection"
                    ),
                    label=(
                        f"與 {waler.id} 圍令內側線交點"
                        if direct is not None
                        else f"長軸延伸線與 {waler.id} 圍令內側線交點"
                    ),
                    source_handles=(*member.source_handles, *waler.source_handles),
                    source_entity_types=(
                        *member.source_entity_types,
                        *waler.source_entity_types,
                    ),
                    score=0.98 if direct is not None else 0.92,
                    valid_for=(
                        ("start",)
                        if along < length / 2
                        else ("end",)
                        if along > length / 2
                        else ("start", "end")
                    ),
                )

        return replace(
            member,
            candidate_points=tuple(
                replace(point, component_id=member.id)
                for point in store.points()
            ),
            recommended_start_point_id=start_id,
            recommended_end_point_id=end_id,
            selected_start_point_id=start_id,
            selected_end_point_id=end_id,
            selection_source="auto",
        )


def build_candidate_points(
    result: DXFImportResult,
    tolerances: GeometryTolerances | None = None,
) -> DXFImportResult:
    """Populate all components from one shared candidate-point source."""

    tolerances = tolerances or GeometryTolerances()
    engineering_source_geometry = tuple(
        geometry
        for geometry in result.source_geometry
        if geometry.role not in {"continuous_wall", "auxiliary", "ignore"}
    )
    builder = CandidatePointBuilder(
        engineering_source_geometry,
        result.walers,
        tolerances,
    )
    return replace(
        result,
        walers=tuple(builder.build(member) for member in result.walers),
        struts=tuple(builder.build(member) for member in result.struts),
        braces=tuple(builder.build(member) for member in result.braces),
        columns=tuple(builder.build(member) for member in result.columns),
        beams=tuple(builder.build(member) for member in result.beams),
        corner_braces=tuple(
            builder.build(member) for member in result.corner_braces
        ),
    )


def rebuild_candidate_points_for_components(
    result: DXFImportResult,
    component_ids: Sequence[str],
    tolerances: GeometryTolerances | None = None,
    *,
    selection_source: str = "geometry_adjustment",
) -> DXFImportResult:
    """Rebuild only changed members and leave every unrelated choice untouched."""

    identifiers = {str(component_id) for component_id in component_ids}
    if not identifiers:
        return result
    tolerances = tolerances or GeometryTolerances()
    engineering_source_geometry = tuple(
        geometry
        for geometry in result.source_geometry
        if geometry.role not in {"continuous_wall", "auxiliary", "ignore"}
    )
    builder = CandidatePointBuilder(
        engineering_source_geometry,
        result.walers,
        tolerances,
    )

    def rebuild(member: Waler | Strut | Brace | AuxiliaryComponent):
        if member.id not in identifiers:
            return member
        rebuilt = builder.build(member)
        return replace(rebuilt, selection_source=selection_source)

    return replace(
        result,
        walers=tuple(rebuild(member) for member in result.walers),
        struts=tuple(rebuild(member) for member in result.struts),
        braces=tuple(rebuild(member) for member in result.braces),
        columns=tuple(rebuild(member) for member in result.columns),
        beams=tuple(rebuild(member) for member in result.beams),
        corner_braces=tuple(rebuild(member) for member in result.corner_braces),
    )


def connect_components_to_walers(
    struts: Sequence[Strut],
    braces: Sequence[Brace],
    walers: Sequence[Waler],
    tolerances: GeometryTolerances | None = None,
) -> tuple[tuple[Strut, ...], tuple[Brace, ...], tuple[ValidationMessage, ...]]:
    """Connect endpoints to the nearest finite Waler segment and snap them."""

    tolerances = tolerances or GeometryTolerances()
    messages: list[ValidationMessage] = []

    def connect(point: Point, role: str, handles: tuple[str, ...]) -> tuple[str, Point]:
        distances = sorted(
            (
                _segment_distance(point, waler.start, waler.end),
                waler.id,
                _project_onto_segment(point, waler.start, waler.end),
            )
            for waler in walers
        )
        if not distances or distances[0][0] > tolerances.connection_tolerance_mm:
            return "", point
        nearest = distances[0]
        if (
            len(distances) > 1
            and distances[1][0] <= tolerances.connection_tolerance_mm
            and distances[1][0] - nearest[0] <= tolerances.ambiguous_connection_delta_mm
        ):
            messages.append(
                ValidationMessage(
                    "warning",
                    "AMBIGUOUS_WALER_CONNECTION",
                    f"端點同時接近 {nearest[1]} 與 {distances[1][1]}，採用距離較近的 {nearest[1]}。",
                    role,
                    handles,
                )
            )
        return nearest[1], nearest[2]

    connected_struts = []
    for member in struts:
        from_waler, start = connect(member.start, "strut", member.source_handles)
        to_waler, end = connect(member.end, "strut", member.source_handles)
        connected = replace(
            member,
            start=start,
            end=end,
            world_start=start,
            world_end=end,
            local_start=start,
            local_end=end,
            from_waler=from_waler,
            to_waler=to_waler,
        )
        connected_struts.append(connected)
        count = bool(from_waler) + bool(to_waler)
        if count == 0:
            messages.append(ValidationMessage("error", "STRUT_NOT_CONNECTED", f"{member.id} 兩端皆未連接圍令。", "strut", member.source_handles))
        elif count == 1:
            messages.append(ValidationMessage("error", "STRUT_ONE_END_NOT_CONNECTED", f"{member.id} 僅一端連接圍令。", "strut", member.source_handles))

    connected_braces = []
    for member in braces:
        from_waler, start = connect(member.start, "brace", member.source_handles)
        to_waler, end = connect(member.end, "brace", member.source_handles)
        connected = replace(
            member,
            start=start,
            end=end,
            world_start=start,
            world_end=end,
            local_start=start,
            local_end=end,
            from_waler=from_waler,
            to_waler=to_waler,
        )
        connected_braces.append(connected)
        count = bool(from_waler) + bool(to_waler)
        if count == 0:
            messages.append(ValidationMessage("error", "BRACE_NOT_CONNECTED", f"{member.id} 兩端皆未連接圍令。", "brace", member.source_handles))
        elif count == 1:
            messages.append(ValidationMessage("error", "BRACE_ONE_END_NOT_CONNECTED", f"{member.id} 僅一端連接圍令。", "brace", member.source_handles))
    return tuple(connected_struts), tuple(connected_braces), tuple(messages)


def _column_association_tolerance(
    column: Column,
    strut: Strut,
    tolerances: GeometryTolerances,
) -> float:
    """Return a section-aware centreline distance for Column association."""

    base = max(0.0, tolerances.component_association_tolerance_mm)
    column_width = max(0.0, float(column.source_width or 0.0))
    strut_width = max(0.0, float(strut.source_width or 0.0))
    inferred = (
        column_width / 2.0
        + strut_width / 2.0
        + max(0.0, tolerances.column_association_clearance_mm)
    )
    maximum = max(base, tolerances.maximum_column_association_tolerance_mm)
    return min(maximum, max(base, inferred))


def _associate_components_to_struts_legacy(
    struts: Sequence[Strut],
    columns: Sequence[Column],
    beams: Sequence[Beam],
    tolerances: GeometryTolerances | None = None,
) -> tuple[
    tuple[Strut, ...],
    tuple[Column, ...],
    tuple[Beam, ...],
    tuple[ComponentAssociation, ...],
    tuple[ValidationMessage, ...],
]:
    """Assign every Column/Beam to exactly one nearest valid Strut."""

    tolerances = tolerances or GeometryTolerances()
    assignments: dict[str, dict[str, list[tuple[float, str]]]] = {
        strut.id: {"column": [], "beam": []} for strut in struts
    }
    associations: list[ComponentAssociation] = []
    messages: list[ValidationMessage] = []

    def associate_component(
        component: Column | Beam,
        role: str,
    ) -> Column | Beam:
        component_start = component.world_start or component.start
        component_end = component.world_end or component.end
        center = (
            component.world_reference_point
            if isinstance(component, Column)
            and component.world_reference_point is not None
            else _midpoint(component_start, component_end)
        )
        options: list[tuple[float, str, float, Point]] = []
        for strut in struts:
            strut_start = strut.world_start or strut.start
            strut_end = strut.world_end or strut.end
            axis = _unit(strut_start, strut_end)
            strut_length = _length(strut_start, strut_end)
            if axis is None or strut_length <= 1e-9:
                continue
            station = _dot(_vector(strut_start, center), axis)
            if not (0.0 <= station <= strut_length):
                continue
            projection = (
                strut_start[0] + axis[0] * station,
                strut_start[1] + axis[1] * station,
            )
            distance = _distance(center, projection)
            if distance > _column_association_tolerance(
                component,
                strut,
                tolerances,
            ):
                continue
            options.append((distance, strut.id, station, projection))
        options.sort(key=lambda item: (item[0], item[1]))
        if not options:
            label = "中間柱" if role == "column" else "托梁"
            messages.append(
                ValidationMessage(
                    "error",
                    f"{role.upper()}_NOT_ASSOCIATED",
                    f"{component.id} 無法在有效範圍及容差內找到所屬支撐。",
                    role,
                    component.source_handles,
                )
            )
            return replace(
                component,
                associated_strut_id="",
                association_station=None,
                association_distance=None,
                world_association_point=None,
                local_association_point=None,
            )
        distance, strut_id, station, projection = options[0]
        if (
            len(options) > 1
            and options[1][0] - distance
            <= tolerances.ambiguous_connection_delta_mm
        ):
            messages.append(
                ValidationMessage(
                    "warning",
                    "AMBIGUOUS_COMPONENT_ASSOCIATION",
                    f"{component.id} 同時接近 {strut_id} 與 {options[1][1]}，採用距離較近的 {strut_id}。",
                    role,
                    component.source_handles,
                )
            )
        assignments[strut_id][role].append((station, component.id))
        associations.append(
            ComponentAssociation(
                component.id,
                role,
                strut_id,
                station,
                distance,
                projection,
                projection,
            )
        )
        return replace(
            component,
            associated_strut_id=strut_id,
            association_station=station,
            association_distance=distance,
            world_association_point=projection,
            local_association_point=projection,
        )

    associated_columns = tuple(
        associate_component(component, "column") for component in columns
    )
    associated_beams = tuple(
        associate_component(component, "beam") for component in beams
    )

    def unique_stations(values: Sequence[tuple[float, str]]) -> tuple[float, ...]:
        stations: list[float] = []
        for station, _identifier in sorted(values):
            if not any(abs(station - existing) <= 1.0 for existing in stations):
                stations.append(station)
        return tuple(stations)

    associated_struts = []
    for strut in struts:
        column_values = sorted(assignments[strut.id]["column"])
        beam_values = sorted(assignments[strut.id]["beam"])
        associated_struts.append(
            replace(
                strut,
                associated_columns=tuple(identifier for _station, identifier in column_values),
                associated_beams=tuple(identifier for _station, identifier in beam_values),
                column_positions=unique_stations(column_values),
                beam_positions=unique_stations(beam_values),
            )
        )
    return (
        tuple(associated_struts),
        associated_columns,
        associated_beams,
        tuple(associations),
        tuple(messages),
    )


def associate_components_to_struts(
    struts: Sequence[Strut],
    columns: Sequence[Column],
    beams: Sequence[Beam],
    tolerances: GeometryTolerances | None = None,
    *,
    double_support_candidates: Sequence[DoubleSupportCandidate] = (),
) -> tuple[
    tuple[Strut, ...],
    tuple[Column, ...],
    tuple[Beam, ...],
    tuple[ComponentAssociation, ...],
    tuple[ValidationMessage, ...],
]:
    """Rebuild Column/Beam constraints from current geometry.

    A Column keeps one nearest primary association.  When that primary Strut
    has exactly one accepted double-support partner and the Column is also a
    legal option for the partner, both Struts receive independently projected
    constraints.  Merely being close to two unrelated Struts is not enough.
    """

    tolerances = tolerances or GeometryTolerances()
    assignments: dict[str, dict[str, list[tuple[float, str]]]] = {
        strut.id: {"column": [], "beam": []} for strut in struts
    }
    associations: list[ComponentAssociation] = []
    messages: list[ValidationMessage] = []
    strut_ids = set(assignments)
    accepted_memberships: dict[
        str, list[tuple[DoubleSupportCandidate, str]]
    ] = defaultdict(list)
    for candidate in double_support_candidates:
        first_id = str(candidate.first_strut_id)
        second_id = str(candidate.second_strut_id)
        if (
            not candidate.accepted
            or first_id == second_id
            or first_id not in strut_ids
            or second_id not in strut_ids
        ):
            continue
        accepted_memberships[first_id].append((candidate, second_id))
        accepted_memberships[second_id].append((candidate, first_id))

    def associate_column(component: Column) -> Column:
        center = component.world_reference_point or _midpoint(
            component.world_start or component.start,
            component.world_end or component.end,
        )
        options: list[tuple[float, str, float, Point]] = []
        for strut in struts:
            start = strut.world_start or strut.start
            end = strut.world_end or strut.end
            axis = _unit(start, end)
            length = _length(start, end)
            if axis is None or length <= 1e-9:
                continue
            station = _dot(_vector(start, center), axis)
            if not (0.0 <= station <= length):
                continue
            projection = (
                start[0] + axis[0] * station,
                start[1] + axis[1] * station,
            )
            distance = _distance(center, projection)
            if distance <= _column_association_tolerance(
                component,
                strut,
                tolerances,
            ):
                options.append((distance, strut.id, station, projection))
        options.sort(key=lambda item: (item[0], item[1]))
        if not options:
            messages.append(
                ValidationMessage(
                    "error",
                    "COLUMN_NOT_ASSOCIATED",
                    f"{component.id} 未找到有效範圍內的所屬支撐。",
                    "column",
                    component.source_handles,
                )
            )
            return replace(
                component,
                associated_strut_id="",
                association_station=None,
                association_distance=None,
                world_association_point=None,
                local_association_point=None,
            )
        distance, strut_id, station, projection = options[0]
        options_by_strut_id = {option[1]: option for option in options}
        memberships = accepted_memberships.get(strut_id, ())
        assignment_options = (options[0],)
        eligible_memberships = tuple(
            (candidate, partner_id)
            for candidate, partner_id in memberships
            if partner_id in options_by_strut_id
        )
        if len(memberships) == 1 and len(eligible_memberships) == 1:
            _candidate, partner_id = eligible_memberships[0]
            assignment_options = (
                options[0],
                options_by_strut_id[partner_id],
            )
        elif len(memberships) > 1 and eligible_memberships:
            messages.append(
                ValidationMessage(
                    "warning",
                    "AMBIGUOUS_COMPONENT_ASSOCIATION",
                    f"{component.id} 的主要支撐 {strut_id} 同時屬於多個已採用雙路群組，"
                    f"保守採用 primary 單支關聯。",
                    "column",
                    component.source_handles,
                )
            )
        elif (
            len(options) > 1
            and options[1][0] - distance
            <= tolerances.ambiguous_connection_delta_mm
        ):
            messages.append(
                ValidationMessage(
                    "warning",
                    "AMBIGUOUS_COMPONENT_ASSOCIATION",
                    f"{component.id} 同時接近 {strut_id} 與 {options[1][1]}，已採用較近的 {strut_id}。",
                    "column",
                    component.source_handles,
                )
            )
        for (
            assignment_distance,
            assignment_strut_id,
            assignment_station,
            assignment_projection,
        ) in assignment_options:
            assignments[assignment_strut_id]["column"].append(
                (assignment_station, component.id)
            )
            associations.append(
                ComponentAssociation(
                    component.id,
                    "column",
                    assignment_strut_id,
                    assignment_station,
                    assignment_distance,
                    assignment_projection,
                    assignment_projection,
                )
            )
        return replace(
            component,
            associated_strut_id=strut_id,
            association_station=station,
            association_distance=distance,
            world_association_point=projection,
            local_association_point=projection,
        )

    def associate_beam(component: Beam) -> Beam:
        path = component.world_path or (
            component.world_start or component.start,
            component.world_end or component.end,
        )
        raw_crossings: list[BeamCrossing] = []
        overlap_struts: set[str] = set()
        snapped_pairs: set[tuple[str, int]] = set()
        for segment_index, beam_segment in enumerate(zip(path, path[1:])):
            if _length(*beam_segment) <= 1e-9:
                continue
            for strut in struts:
                strut_start = strut.world_start or strut.start
                strut_end = strut.world_end or strut.end
                strut_segment = (strut_start, strut_end)
                strut_axis = _unit(*strut_segment)
                strut_length = _length(*strut_segment)
                if strut_axis is None or strut_length <= 1e-9:
                    continue
                point = _segment_intersection_point(
                    beam_segment,
                    strut_segment,
                    1e-6,
                )
                distance = 0.0
                method = "segment_intersection"
                if point is None:
                    beam_point, strut_point, distance = (
                        _closest_points_between_segments(
                            beam_segment,
                            strut_segment,
                        )
                    )
                    if _segments_have_parallel_overlap(
                        beam_segment,
                        strut_segment,
                        tolerances.parallel_angle_tolerance_deg,
                    ):
                        if (
                            distance <= tolerances.beam_crossing_tolerance_mm
                            and strut.id not in overlap_struts
                        ):
                            overlap_struts.add(strut.id)
                            messages.append(
                                ValidationMessage(
                                    "warning",
                                    "BEAM_OVERLAPS_STRUT",
                                    f"{component.id} 與 {strut.id} 平行重疊，沒有唯一交點，請人工確認。",
                                    "beam",
                                    component.source_handles,
                                )
                            )
                        continue
                    if distance > tolerances.beam_crossing_tolerance_mm:
                        continue
                    point = strut_point
                    method = "gap_snapped_intersection"
                    snapped_pairs.add((strut.id, segment_index))
                station = _dot(_vector(strut_start, point), strut_axis)
                if not (-1e-6 <= station <= strut_length + 1e-6):
                    continue
                raw_crossings.append(
                    BeamCrossing(
                        component.id,
                        strut.id,
                        point,
                        point,
                        max(0.0, min(strut_length, station)),
                        segment_index,
                        distance,
                        method,
                    )
                )

        crossings: list[BeamCrossing] = []
        for crossing in sorted(
            raw_crossings,
            key=lambda item: (
                item.beam_segment_index,
                item.strut_id,
                item.strut_station,
            ),
        ):
            duplicate = any(
                existing.strut_id == crossing.strut_id
                and _distance(existing.world_point, crossing.world_point)
                <= tolerances.beam_crossing_duplicate_tolerance_mm
                for existing in crossings
            )
            if not duplicate:
                crossings.append(crossing)

        if not crossings:
            messages.append(
                ValidationMessage(
                    "warning",
                    "BEAM_NOT_ASSOCIATED",
                    f"{component.id} 的托梁路徑未與任何支撐相交，未建立禁止點。",
                    "beam",
                    component.source_handles,
                )
            )
            return replace(
                component,
                associated_strut_id="",
                associated_strut_ids=(),
                association_station=None,
                association_distance=None,
                world_association_point=None,
                local_association_point=None,
                crossings=(),
            )

        for strut_id, segment_index in sorted(snapped_pairs):
            messages.append(
                ValidationMessage(
                    "warning",
                    "BEAM_CROSSING_SNAPPED",
                    f"{component.id} 第 {segment_index + 1} 段與 {strut_id} 有小間隙，已吸附至支撐建立禁止點。",
                    "beam",
                    component.source_handles,
                )
            )
        associated_strut_ids = tuple(
            dict.fromkeys(crossing.strut_id for crossing in crossings)
        )
        for crossing in crossings:
            assignments[crossing.strut_id]["beam"].append(
                (crossing.strut_station, component.id)
            )
            associations.append(
                ComponentAssociation(
                    component.id,
                    "beam",
                    crossing.strut_id,
                    crossing.strut_station,
                    crossing.distance,
                    crossing.world_point,
                    crossing.local_point,
                )
            )
        first = crossings[0]
        return replace(
            component,
            associated_strut_id=first.strut_id,
            associated_strut_ids=associated_strut_ids,
            association_station=first.strut_station,
            association_distance=first.distance,
            world_association_point=first.world_point,
            local_association_point=first.local_point,
            crossings=tuple(crossings),
        )

    associated_columns = tuple(associate_column(item) for item in columns)
    associated_beams = tuple(associate_beam(item) for item in beams)

    def unique_stations(values: Sequence[tuple[float, str]]) -> tuple[float, ...]:
        stations: list[float] = []
        for station, _identifier in sorted(values):
            if not any(
                abs(station - existing)
                <= tolerances.beam_crossing_duplicate_tolerance_mm
                for existing in stations
            ):
                stations.append(station)
        return tuple(stations)

    associated_struts = tuple(
        replace(
            strut,
            associated_columns=tuple(
                dict.fromkeys(
                    identifier
                    for _station, identifier in sorted(
                        assignments[strut.id]["column"]
                    )
                )
            ),
            associated_beams=tuple(
                dict.fromkeys(
                    identifier
                    for _station, identifier in sorted(
                        assignments[strut.id]["beam"]
                    )
                )
            ),
            column_positions=unique_stations(
                assignments[strut.id]["column"]
            ),
            beam_positions=unique_stations(assignments[strut.id]["beam"]),
        )
        for strut in struts
    )
    return (
        associated_struts,
        associated_columns,
        associated_beams,
        tuple(associations),
        tuple(messages),
    )


def rebuild_component_associations(
    result: DXFImportResult,
    tolerances: GeometryTolerances | None = None,
) -> DXFImportResult:
    """Rebuild every Column/Beam-derived association from current review state.

    This wrapper is safe for either world or local display coordinates.  It
    clears old association messages and replaces all derived Strut fields and
    association records in one pass, while leaving CornerBrace data alone.
    """

    tolerances = tolerances or GeometryTolerances()
    coordinate_system = result.coordinate_system
    world_result = apply_coordinate_system(result, CoordinateSystem())
    (
        struts,
        columns,
        beams,
        component_associations,
        association_messages,
    ) = associate_components_to_struts(
        world_result.struts,
        world_result.columns,
        world_result.beams,
        tolerances,
        double_support_candidates=world_result.double_support_candidates,
    )
    retained_messages = tuple(
        message
        for message in world_result.messages
        if message.code not in COMPONENT_ASSOCIATION_CODES
    )
    rebuilt_world = replace(
        world_result,
        struts=struts,
        columns=columns,
        beams=beams,
        messages=(*retained_messages, *association_messages),
        component_associations=component_associations,
        beam_crossings=tuple(
            crossing for beam in beams for crossing in beam.crossings
        ),
        coordinate_system=CoordinateSystem(),
    )
    return apply_coordinate_system(rebuilt_world, coordinate_system)


def attach_corner_braces_to_struts(
    struts: Sequence[Strut],
    walers: Sequence[Waler],
    corner_braces: Sequence[CornerBrace],
    tolerances: GeometryTolerances | None = None,
) -> tuple[Strut, ...]:
    """Map confirmed corner-brace geometry onto associated Strut fields."""

    tolerances = tolerances or GeometryTolerances()

    waler_by_id = {member.id: member for member in walers}
    corner_values: dict[str, dict[str, tuple[float, float]]] = defaultdict(dict)
    for corner in corner_braces:
        best: tuple[float, Strut, str, Waler, Point] | None = None
        for strut in struts:
            endpoint_options = (
                ("from", strut.start, strut.from_waler),
                ("to", strut.end, strut.to_waler),
            )
            for endpoint_name, _base_point, waler_id in endpoint_options:
                waler = waler_by_id.get(waler_id)
                if waler is None:
                    continue
                for waler_point, support_point in (
                    (corner.start, corner.end),
                    (corner.end, corner.start),
                ):
                    waler_distance = _segment_distance(
                        waler_point,
                        waler.start,
                        waler.end,
                    )
                    support_distance = _segment_distance(
                        support_point,
                        strut.start,
                        strut.end,
                    )
                    if max(waler_distance, support_distance) > tolerances.connection_tolerance_mm:
                        continue
                    score = waler_distance + support_distance
                    option = (score, strut, endpoint_name, waler, waler_point)
                    if best is None:
                        best = option
                    elif score < best[0]:
                        best = option
        if best is None:
            continue
        score, strut, endpoint_name, waler, waler_point = best
        axis = _unit(waler.start, waler.end)
        if axis is None:
            continue
        base_point = strut.start if endpoint_name == "from" else strut.end
        projected_waler_point = _project_onto_segment(
            waler_point,
            waler.start,
            waler.end,
        )
        delta = _dot(_vector(base_point, projected_waler_point), axis)
        direction_name = "start" if delta < 0 else "end"
        field_name = f"{endpoint_name}_brace_to_waler_{direction_name}_len"
        previous = corner_values[strut.id].get(field_name)
        if previous is None or score < previous[0]:
            # Project dimensions are expressed in whole millimetres.  DXF
            # intersections commonly retain sub-millimetre transform residue
            # (for example 1499.936 mm for a nominal 1500 mm station).
            corner_values[strut.id][field_name] = (score, round(abs(delta)))

    attached = []
    for strut in struts:
        changes: dict[str, Any] = {
            "from_brace_to_waler_start_len": 0.0,
            "from_brace_to_waler_end_len": 0.0,
            "to_brace_to_waler_start_len": 0.0,
            "to_brace_to_waler_end_len": 0.0,
        }
        for field_name, (_score, length) in corner_values.get(strut.id, {}).items():
            changes[field_name] = length
        attached.append(replace(strut, **changes))
    return tuple(attached)


def attach_auxiliary_components(
    struts: Sequence[Strut],
    walers: Sequence[Waler],
    columns: Sequence[Column],
    beams: Sequence[Beam],
    corner_braces: Sequence[CornerBrace],
    tolerances: GeometryTolerances | None = None,
) -> tuple[Strut, ...]:
    """Compatibility wrapper for association plus corner-brace attachment."""

    associated, _columns, _beams, _records, _messages = (
        associate_components_to_struts(struts, columns, beams, tolerances)
    )
    return attach_corner_braces_to_struts(
        associated,
        walers,
        corner_braces,
        tolerances,
    )


def _replace_result_member(
    result: DXFImportResult,
    member_id: str,
    updater: Any,
) -> DXFImportResult:
    found = False
    changes: dict[str, Any] = {}
    for collection_name in (
        "walers",
        "struts",
        "braces",
        "columns",
        "beams",
        "corner_braces",
    ):
        updated = []
        for member in getattr(result, collection_name):
            if member.id == member_id:
                member = updater(member)
                found = True
            updated.append(member)
        changes[collection_name] = tuple(updated)
    if not found:
        raise DXFImportError(f"找不到工程構件：{member_id}")
    return replace(result, **changes)


def apply_candidate_point_selection(
    result: DXFImportResult,
    member_id: str,
    start_point_id: str,
    end_point_id: str,
    tolerances: GeometryTolerances | None = None,
    *,
    selection_source: str = "manual_candidate_points",
) -> DXFImportResult:
    """Commit a pending pair, then rebuild connections and derived Solver rows."""

    tolerances = tolerances or GeometryTolerances()
    target = next(
        (member for member in _result_members(result) if member.id == member_id),
        None,
    )
    if target is None:
        raise DXFImportError(f"找不到工程構件：{member_id}")
    validations = validate_candidate_point_pair(
        target,
        start_point_id,
        end_point_id,
        tolerances,
        result.walers,
    )
    errors = [item for item in validations if item.severity in ERROR_SEVERITIES]
    if errors:
        raise DXFImportError(errors[0].message)
    start_point = candidate_point_by_id(target, start_point_id)
    end_point = candidate_point_by_id(target, end_point_id)
    assert start_point is not None and end_point is not None

    def restore_world(
        member: Waler | Strut | Brace | AuxiliaryComponent,
    ) -> Waler | Strut | Brace | AuxiliaryComponent:
        world_start = member.world_start or member.start
        world_end = member.world_end or member.end
        changes: dict[str, Any] = {}
        if member.id == member_id:
            world_start = start_point.world_point
            world_end = end_point.world_point
            changes.update(
                selected_start_point_id=start_point_id,
                selected_end_point_id=end_point_id,
                selection_source=selection_source,
            )
            if isinstance(member, Waler):
                changes["engineering_line_kind"] = (
                    "cad_manual" if selection_source == "cad_manual" else "manual_candidate_points"
                )
        changes.update(
            start=world_start,
            end=world_end,
            world_start=world_start,
            world_end=world_end,
            local_start=world_start,
            local_end=world_end,
        )
        if isinstance(member, Column) and member.id == member_id:
            reference_point = _midpoint(world_start, world_end)
            changes.update(
                reference_point=reference_point,
                world_reference_point=reference_point,
                local_reference_point=reference_point,
            )
        if isinstance(member, Beam):
            world_path = list(
                member.world_path or (world_start, world_end)
            )
            if member.id == member_id:
                world_path[0] = world_start
                world_path[-1] = world_end
            changes.update(
                world_path=tuple(world_path),
                local_path=tuple(world_path),
                path=tuple(world_path),
                associated_strut_ids=(),
                crossings=(),
            )
        if isinstance(member, (Strut, Brace)):
            changes.update(from_waler="", to_waler="")
        if isinstance(member, Strut):
            changes.update(
                beam_positions=(),
                column_positions=(),
                associated_columns=(),
                associated_beams=(),
                from_brace_to_waler_start_len=0.0,
                from_brace_to_waler_end_len=0.0,
                to_brace_to_waler_start_len=0.0,
                to_brace_to_waler_end_len=0.0,
            )
        if isinstance(member, (Column, Beam)):
            changes.update(
                associated_strut_id="",
                association_station=None,
                association_distance=None,
                world_association_point=None,
                local_association_point=None,
            )
        return replace(member, **changes)

    walers = tuple(restore_world(member) for member in result.walers)
    struts = tuple(restore_world(member) for member in result.struts)
    braces = tuple(restore_world(member) for member in result.braces)
    columns = tuple(restore_world(member) for member in result.columns)
    beams = tuple(restore_world(member) for member in result.beams)
    corner_braces = tuple(restore_world(member) for member in result.corner_braces)
    connected_struts, connected_braces, connection_messages = (
        connect_components_to_walers(struts, braces, walers, tolerances)
    )
    double_support_candidates = preserve_double_support_decisions(
        result.double_support_candidates,
        detect_double_support_candidates(connected_struts, tolerances),
    )
    (
        connected_struts,
        columns,
        beams,
        component_associations,
        association_messages,
    ) = associate_components_to_struts(
        connected_struts,
        columns,
        beams,
        tolerances,
        double_support_candidates=double_support_candidates,
    )
    connected_struts = attach_corner_braces_to_struts(
        connected_struts,
        walers,
        corner_braces,
        tolerances,
    )
    duplicate_messages = validate_duplicate_engineering_members(
        (
            walers,
            connected_struts,
            connected_braces,
            columns,
            beams,
            corner_braces,
        ),
        tolerances,
    )
    base_messages = tuple(
        message
        for message in result.messages
        if message.code not in CONNECTION_VALIDATION_CODES
        and message.code not in COMPONENT_ASSOCIATION_CODES
        and message.code
        not in {
            "MANUAL_LINE_SELECTION",
            "MANUAL_POINT_SELECTION",
            "CAD_MANUAL_LINE_SELECTION",
            "CANDIDATE_LINE_DIRECTION_CHANGED",
            "POSSIBLE_COMPONENT_SHORT_SIDE",
            "WALER_CANDIDATE_LINE_UNUSUAL",
            "CANDIDATE_ENDPOINT_NOT_NEAR_WALER",
            "DUPLICATE_ENGINEERING_COMPONENT",
        }
    )
    all_updated_members = (
        *walers,
        *connected_struts,
        *connected_braces,
        *columns,
        *beams,
        *corner_braces,
    )
    manual_messages = tuple(
        ValidationMessage(
            "info",
            (
                "CAD_MANUAL_LINE_SELECTION"
                if member.selection_source == "cad_manual"
                else "MANUAL_POINT_SELECTION"
            ),
            (
                f"{member.id} 已採用 CAD 人工指定工程線。"
                if member.selection_source == "cad_manual"
                else f"{member.id} 已採用候選點建立工程線。"
            ),
            _member_model_role(member),
            member.source_handles,
        )
        for member in all_updated_members
        if member.selection_source != "auto"
    )
    world_result = replace(
        result,
        walers=walers,
        struts=connected_struts,
        braces=connected_braces,
        columns=columns,
        beams=beams,
        corner_braces=corner_braces,
        messages=(
            *base_messages,
            *connection_messages,
            *association_messages,
            *duplicate_messages,
            *validations,
            *manual_messages,
        ),
        coordinate_system=CoordinateSystem(),
        component_associations=component_associations,
        beam_crossings=tuple(
            crossing for beam in beams for crossing in beam.crossings
        ),
        double_support_candidates=double_support_candidates,
    )
    return apply_coordinate_system(world_result, result.coordinate_system)


def add_cad_candidate_points(
    result: DXFImportResult,
    member_id: str,
    world_start: Point,
    world_end: Point,
    tolerances: GeometryTolerances | None = None,
) -> tuple[DXFImportResult, str, str]:
    """Add CAD Temp endpoints as candidates without committing the formal line."""

    tolerances = tolerances or GeometryTolerances()
    coordinates = (*world_start, *world_end)
    if not all(math.isfinite(float(value)) for value in coordinates):
        raise DXFImportError("CAD 指定工程線座標必須是有限數字。")
    world_start = float(world_start[0]), float(world_start[1])
    world_end = float(world_end[0]), float(world_end[1])
    if _distance(world_start, world_end) < tolerances.minimum_component_length_mm:
        raise DXFImportError("CAD 指定工程線短於系統允許的最小構件長度。")
    selected_ids: list[str] = []

    def add_points(
        member: Waler | Strut | Brace | AuxiliaryComponent,
    ) -> Waler | Strut | Brace | AuxiliaryComponent:
        store = CandidatePointStore(
            min(
                tolerances.duplicate_tolerance_mm,
                tolerances.endpoint_tolerance_mm,
                1.0,
            )
        )
        for point in member.candidate_points:
            retained_types = tuple(
                point_type
                for point_type in point.point_types
                if not point_type.startswith("cad_manual")
            )
            retained_primary = (
                point.point_type
                if not point.point_type.startswith("cad_manual")
                else (retained_types[0] if retained_types else "")
            )
            if (
                not retained_primary
                and point.id
                in {
                    member.selected_start_point_id,
                    member.selected_end_point_id,
                }
            ):
                retained_primary = "formal_engineering_endpoint"
                retained_types = (retained_primary,)
            if not retained_primary:
                continue
            stripped_cad_primary = retained_primary != point.point_type
            stored_id = store.add(
                point.world_point,
                point_type=retained_primary,
                label="既有辨識候選點" if stripped_cad_primary else point.label,
                source_handles=point.source_handles,
                source_entity_types=tuple(
                    entity_type
                    for entity_type in point.source_entity_types
                    if entity_type != "CAD_TEMP"
                ),
                recommended_for=point.recommended_for,
                score=min(point.score, 0.90) if stripped_cad_primary else point.score,
                valid_for=point.valid_for,
                preferred_id=point.id,
            )
            for extra_type in retained_types:
                if extra_type == retained_primary:
                    continue
                store.add(
                    point.world_point,
                    point_type=extra_type,
                    label=point.label,
                    source_handles=point.source_handles,
                    source_entity_types=point.source_entity_types,
                    recommended_for=point.recommended_for,
                    score=max(0.0, point.score - 1e-6),
                    valid_for=point.valid_for,
                    preferred_id=stored_id,
                )
        selected_ids.append(
            store.add(
                world_start,
                point_type="cad_manual_start",
                label="CAD 人工指定起點",
                source_handles=member.source_handles,
                source_entity_types=("CAD_TEMP",),
                score=1.0,
                valid_for=("start",),
                preferred_id="cad_manual_start",
            )
        )
        selected_ids.append(
            store.add(
                world_end,
                point_type="cad_manual_end",
                label="CAD 人工指定終點",
                source_handles=member.source_handles,
                source_entity_types=("CAD_TEMP",),
                score=1.0,
                valid_for=("end",),
                preferred_id="cad_manual_end",
            )
        )
        return replace(
            member,
            candidate_points=tuple(
                replace(point, component_id=member.id)
                for point in store.points()
            ),
        )

    updated = _replace_result_member(result, member_id, add_points)
    updated = apply_coordinate_system(updated, result.coordinate_system)
    return updated, selected_ids[0], selected_ids[1]


def select_engineering_line(
    result: DXFImportResult,
    member_id: str,
    candidate_id: str,
    tolerances: GeometryTolerances | None = None,
) -> DXFImportResult:
    """Compatibility adapter: convert a legacy line choice into two point choices."""

    target = next(
        (member for member in _result_members(result) if member.id == member_id),
        None,
    )
    if target is None:
        raise DXFImportError(f"找不到工程構件：{member_id}")
    candidate = next(
        (item for item in target.line_candidates if item.id == candidate_id),
        None,
    )
    if candidate is None:
        raise DXFImportError(f"{member_id} 沒有候選線段：{candidate_id}")
    updated, start_id, end_id = add_cad_candidate_points(
        result,
        member_id,
        candidate.world_start,
        candidate.world_end,
        tolerances,
    )
    updated = apply_candidate_point_selection(
        updated,
        member_id,
        start_id,
        end_id,
        tolerances,
        selection_source="manual_candidate_points",
    )
    return _replace_result_member(
        updated,
        member_id,
        lambda member: replace(member, selected_candidate_id=candidate_id),
    )


def set_cad_engineering_line(
    result: DXFImportResult,
    member_id: str,
    world_start: Point,
    world_end: Point,
    tolerances: GeometryTolerances | None = None,
) -> DXFImportResult:
    """Compatibility API: add CAD endpoints and immediately commit both."""

    updated, start_id, end_id = add_cad_candidate_points(
        result,
        member_id,
        world_start,
        world_end,
        tolerances,
    )
    updated = apply_candidate_point_selection(
        updated,
        member_id,
        start_id,
        end_id,
        tolerances,
        selection_source="cad_manual",
    )
    legacy_line = EngineeringLineCandidate(
        "cad_manual_line",
        "CAD 人工指定工程線",
        (float(world_start[0]), float(world_start[1])),
        (float(world_end[0]), float(world_end[1])),
        "cad_temp",
    )
    return _replace_result_member(
        updated,
        member_id,
        lambda member: replace(
            member,
            line_candidates=(
                *(
                    candidate
                    for candidate in member.line_candidates
                    if candidate.id != legacy_line.id
                ),
                legacy_line,
            ),
            selected_candidate_id=legacy_line.id,
        ),
    )
