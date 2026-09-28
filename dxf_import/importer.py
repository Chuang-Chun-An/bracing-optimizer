"""DXF file reading and conversion into engineering models."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    import ezdxf
    from ezdxf.disassemble import recursive_decompose as _recursive_decompose
    from ezdxf.lldxf.const import BOUNDARY_PATH_EXTERNAL
    from ezdxf.math import Vec3
except ImportError:  # pragma: no cover - only a broken installation
    ezdxf = None
    _recursive_decompose = None
    BOUNDARY_PATH_EXTERNAL = 1
    Vec3 = None

from .candidate_points import (
    attach_auxiliary_components,
    attach_corner_braces_to_struts,
    build_candidate_points,
    connect_components_to_walers,
    associate_components_to_struts,
)
from .geometry import (
    Point,
    _angle_difference_deg,
    _distance,
    _dot,
    _length,
    _line_distance,
    _midpoint,
    _point,
    _same_point,
    _unit,
)
from .models import (
    AuxiliaryComponent,
    Beam,
    BeamCrossing,
    BlockInstanceInfo,
    Brace,
    Column,
    CoordinateSystem,
    CornerBrace,
    DXFImportError,
    DXFImportResult,
    ExcludedSource,
    EntityDebugInfo,
    GeometryTolerances,
    LayerInfo,
    SourceGeometry,
    SourceText,
    Strut,
    ValidationMessage,
    Waler,
    apply_coordinate_system,
)
from .source_exclusion import (
    normalize_excluded_sources,
    source_file_fingerprint,
)
from .recognition import (
    _Candidate,
    _GeometryGroup,
    _Primitive,
    _candidate_from_group,
    _characterize_waler_candidate_envelope,
    _build_waler_span_context,
    _corner_brace_candidates_from_group,
    _deduplicate_candidates,
    _engineering_line_candidates,
    _finalize_contextual_strut_waler_spans,
    _mline_center_path,
    _refine_corner_brace_axis_intersections,
    _route_bim_joist_block,
    _route_component_like_member_block,
    _route_component_like_strut_block,
    _resolve_waler_contact_geometry,
)
from .joist_recognition import (
    JoistColumnStationReference,
    JoistContextSnapshot,
    JoistMemberReference,
)
from .hatch_waler_recognition import (
    HatchBoundaryPath,
    HatchWalerRecognition,
    HatchWalerSource,
    recognize_hatch_waler,
)
from .validation import validate_duplicate_engineering_members
from .support_pairing import detect_double_support_candidates
from .waler_contact_adjustment import initialize_waler_contact_review
from .material_recognition import recognize_result_material_specs
from .waler_contact_face import extract_waler_envelope_facts


def _lwpolyline_world_vertices(entity: Any) -> list[Point]:
    """Return LWPOLYLINE vertices normalized from entity OCS to WCS."""

    return [_point(vertex) for vertex in entity.vertices_in_wcs()]


def _polyline_world_vertices(entity: Any) -> list[Point]:
    """Return 2D/3D POLYLINE vertices in WCS using ezdxf semantics."""

    return [_point(vertex) for vertex in entity.points_in_wcs()]


def _solid_trace_world_vertices(entity: Any) -> list[Point]:
    """Return graphical SOLID/TRACE vertices normalized from OCS to WCS."""

    return [_point(vertex) for vertex in entity.wcs_vertices()]


def _segment_is_hatch_boundary_evidence(
    segment: tuple[Point, Point],
    hatch_boundaries: Sequence[tuple[Point, Point]],
    tolerances: GeometryTolerances,
) -> bool:
    """Return whether a complete segment matches a HATCH exterior chain."""

    axis = _unit(*segment)
    segment_length = _length(*segment)
    if axis is None or segment_length <= 0.0:
        return False
    intervals: list[tuple[float, float]] = []
    for boundary in hatch_boundaries:
        if (
            _angle_difference_deg(segment, boundary)
            > tolerances.parallel_angle_tolerance_deg
        ):
            continue
        if max(
            _line_distance(boundary[0], *segment),
            _line_distance(boundary[1], *segment),
        ) > tolerances.collinear_tolerance_mm:
            continue
        stations = tuple(
            _dot(
                (point[0] - segment[0][0], point[1] - segment[0][1]),
                axis,
            )
            for point in boundary
        )
        intervals.append((min(stations), max(stations)))
    if not intervals:
        return False

    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1] + tolerances.endpoint_tolerance_mm:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    required_ratio = tolerances.minimum_projection_overlap_ratio
    for start, end in merged:
        overlap = max(0.0, min(segment_length, end) - max(0.0, start))
        chain_length = end - start
        if chain_length <= 0.0:
            continue
        if (
            overlap / segment_length >= required_ratio
            and overlap / chain_length >= required_ratio
            and start <= tolerances.endpoint_tolerance_mm
            and end >= segment_length - tolerances.endpoint_tolerance_mm
        ):
            return True
    return False


def _group_is_hatch_boundary_evidence(
    group: _GeometryGroup,
    hatch_boundary_scopes: Sequence[Sequence[tuple[Point, Point]]],
    tolerances: GeometryTolerances,
) -> bool:
    """Claim only top-level LINE/POLYLINE geometry fully matching HATCH edges."""

    if str(group.root_entity_type).strip().upper() not in {
        "LINE",
        "LWPOLYLINE",
        "POLYLINE",
    }:
        return False
    if not group.primitives:
        return False
    segments = tuple(
        segment
        for primitive in group.primitives
        for segment in primitive.segments()
    )
    return bool(segments) and all(
        any(
            _segment_is_hatch_boundary_evidence(
                segment,
                hatch_boundaries,
                tolerances,
            )
            for hatch_boundaries in hatch_boundary_scopes
        )
        for segment in segments
    )


class DXFImporter:
    """Read one DXF and recognize component-level engineering-line candidates.

    Raw DXF entities may use OCS or block-local coordinates.  All primitives
    and ``SourceGeometry`` leaving this importer boundary are normalized to
    WCS.  Project-local coordinates are a separate, later presentation step.
    """

    GEOMETRY_TYPES = {
        "LINE",
        "LWPOLYLINE",
        "POLYLINE",
        "MLINE",
        "SOLID",
        "TRACE",
        "INSERT",
    }
    TEXT_TYPES = {"TEXT", "MTEXT", "ATTRIB", "ATTDEF"}

    def __init__(
        self,
        file_path: str | Path,
        *,
        tolerances: GeometryTolerances | None = None,
        geometry_tolerance: float | None = None,
    ):
        self.file_path = Path(file_path)
        self.tolerances = tolerances or GeometryTolerances()
        if geometry_tolerance is not None:
            self.tolerances = replace(
                self.tolerances,
                endpoint_tolerance_mm=max(float(geometry_tolerance), 1e-9),
            )
        self._document: Any = None
        self._source_fingerprint = ""

    def read(self) -> "DXFImporter":
        if ezdxf is None:
            raise DXFImportError("尚未安裝 ezdxf；請先安裝專案相依套件。")
        if not self.file_path.is_file():
            raise DXFImportError(f"找不到 DXF 檔案：{self.file_path}")
        try:
            self._document = ezdxf.readfile(str(self.file_path))
            self._source_fingerprint = source_file_fingerprint(self.file_path)
        except Exception as exc:
            raise DXFImportError(f"無法讀取 DXF：{exc}") from exc
        return self

    @property
    def document(self) -> Any:
        if self._document is None:
            self.read()
        return self._document

    @property
    def layer_names(self) -> tuple[str, ...]:
        return tuple(layer.dxf.name for layer in self.document.layers)

    @property
    def source_fingerprint(self) -> str:
        if not self._source_fingerprint:
            self.read()
        return self._source_fingerprint

    def layer_information(self) -> tuple[LayerInfo, ...]:
        counts: dict[str, Counter[str]] = defaultdict(Counter)
        for entity in self.document.modelspace():
            counts[str(entity.dxf.layer)][entity.dxftype()] += 1
        return tuple(
            LayerInfo(name, sum(counts[name].values()), dict(sorted(counts[name].items())))
            for name in self.layer_names
        )

    def entities_on_layer(self, layer_name: str) -> tuple[Any, ...]:
        if layer_name not in self.layer_names:
            raise DXFImportError(f"DXF 中沒有圖層「{layer_name}」。")
        return tuple(
            entity
            for entity in self.document.modelspace()
            if str(entity.dxf.layer) == layer_name
        )

    def convert(
        self,
        *,
        strut_layer: str | None = None,
        waler_layer: str | None = None,
        brace_layer: str | None = None,
        layer_roles: Mapping[str, str] | None = None,
        endpoint_tolerance: float | None = None,
        coordinate_system: CoordinateSystem | None = None,
        material_specs: Sequence[Mapping[str, Any]] = (),
        excluded_sources: Sequence[ExcludedSource | Mapping[str, Any]] = (),
    ) -> DXFImportResult:
        tolerances = self.tolerances
        if endpoint_tolerance is not None:
            tolerances = replace(
                tolerances,
                connection_tolerance_mm=max(float(endpoint_tolerance), 0.0),
            )
        engineering_roles = (
            "waler",
            "strut",
            "brace",
            "corner_brace",
            "column",
            "beam",
        )
        preview_only_roles = ("continuous_wall", "auxiliary")
        supported_roles = (*engineering_roles, *preview_only_roles)
        if layer_roles is None:
            legacy = {
                "waler": waler_layer,
                "strut": strut_layer,
                "brace": brace_layer,
            }
            if any(not layer for layer in legacy.values()):
                raise DXFImportError("請先完成圖層用途分類")
            layer_classification = {
                str(layer): role for role, layer in legacy.items() if layer
            }
        else:
            unknown_layers = sorted(set(layer_roles).difference(self.layer_names))
            if unknown_layers:
                raise DXFImportError(
                    f"DXF 中沒有圖層：{', '.join(unknown_layers)}"
                )
            invalid_roles = sorted(
                {
                    role
                    for role in layer_roles.values()
                    if role not in {*supported_roles, "ignore"}
                }
            )
            if invalid_roles:
                raise DXFImportError(
                    f"不支援的圖層用途：{', '.join(invalid_roles)}"
                )
            layer_classification = {
                layer: layer_roles.get(layer, "ignore")
                for layer in self.layer_names
            }
        missing = sorted(
            layer
            for layer in layer_classification
            if layer not in self.layer_names
        )
        if missing:
            raise DXFImportError(f"DXF 中沒有圖層：{', '.join(missing)}")
        selected = {
            role: tuple(
                layer
                for layer in self.layer_names
                if layer_classification.get(layer) == role
            )
            for role in supported_roles
        }
        missing_required = [
            role for role in ("waler", "strut") if not selected[role]
        ]
        if missing_required:
            labels = {"waler": "圍令", "strut": "支撐"}
            raise DXFImportError(
                "請至少指定一個"
                + "、".join(labels[role] for role in missing_required)
                + "圖層"
            )

        debug: list[EntityDebugInfo] = []
        messages: list[ValidationMessage] = []
        source_geometry: list[SourceGeometry] = []
        source_texts: list[SourceText] = []
        source_counts: dict[str, int] = {}
        candidates_by_role: dict[str, list[_Candidate]] = {}
        waler_context = ()
        joist_context = JoistContextSnapshot()
        contextual_geometry_finalized = False
        normalized_exclusions = normalize_excluded_sources(excluded_sources)
        excluded_handles_by_role: dict[str, set[str]] = defaultdict(set)
        for excluded in normalized_exclusions:
            excluded_handles_by_role[excluded.role].update(excluded.source_handles)

        for role in engineering_roles:
            if role == "beam":
                messages.extend(
                    _resolve_waler_contact_geometry(
                        candidates_by_role,
                        tolerances,
                    )
                )
                joist_context = self._build_joist_context(
                    candidates_by_role,
                    tolerances,
                )
                contextual_geometry_finalized = True
            layers = selected[role]
            role_candidates: list[_Candidate] = []
            source_counts[role] = 0
            role_group_count = 0
            active_group_count = 0
            excluded_group_count = 0
            for layer in layers:
                entities = self.entities_on_layer(layer)
                source_counts[role] += len(entities)
                debug_start = len(debug)
                hatch_entities = (
                    tuple(
                        entity
                        for entity in entities
                        if entity.dxftype() == "HATCH"
                    )
                    if role == "waler"
                    else ()
                )
                general_entities = (
                    tuple(
                        entity
                        for entity in entities
                        if entity.dxftype() != "HATCH"
                    )
                    if hatch_entities
                    else entities
                )
                hatch_boundary_scopes: list[
                    tuple[tuple[Point, Point], ...]
                ] = []
                groups = self._geometry_groups(
                    role,
                    layer,
                    general_entities,
                    debug,
                    source_geometry,
                )
                excluded_handles = excluded_handles_by_role.get(role, set())
                for hatch in hatch_entities:
                    source = self._extract_hatch_waler_source(
                        hatch,
                        layer,
                        source_geometry,
                    )
                    outcome = recognize_hatch_waler(source, tolerances)
                    if outcome.exterior_segments:
                        hatch_boundary_scopes.append(outcome.exterior_segments)
                    role_group_count += 1
                    normalized_handle = source.handle.strip().upper()
                    if normalized_handle in excluded_handles:
                        excluded_group_count += 1
                        debug.append(
                            EntityDebugInfo(
                                role,
                                layer,
                                "HATCH",
                                source.handle,
                                "excluded",
                                "info",
                                detail="HATCH RC 圍令來源已依 Review 決策排除。",
                            )
                        )
                        continue
                    active_group_count += 1
                    debug.append(
                        EntityDebugInfo(
                            role,
                            layer,
                            "HATCH",
                            source.handle,
                            "read",
                            "info" if outcome.status == "recognized" else "error",
                            detail=outcome.message,
                        )
                    )
                    if outcome.status == "recognized":
                        role_candidates.append(
                            self._candidate_from_hatch_waler(outcome, tolerances)
                        )
                    else:
                        messages.append(
                            ValidationMessage(
                                "error",
                                outcome.code,
                                outcome.message,
                                "waler",
                                (source.handle,),
                            )
                        )

                claimed_groups = tuple(
                    group
                    for group in groups
                    if _group_is_hatch_boundary_evidence(
                        group,
                        hatch_boundary_scopes,
                        tolerances,
                    )
                )
                if claimed_groups:
                    claimed_handles = {
                        str(handle)
                        for group in claimed_groups
                        for handle in group.handles
                    }
                    groups = [group for group in groups if group not in claimed_groups]
                    for index in range(debug_start, len(debug)):
                        item = debug[index]
                        if item.handle in claimed_handles and item.status == "read":
                            debug[index] = replace(
                                item,
                                status="boundary_evidence",
                                detail=(
                                    "此幾何與 Waler HATCH 外框等價；保留為預覽證據，"
                                    "不再進入一般構件辨識。"
                                ),
                            )

                beam_bim_scope = False
                if role == "beam":
                    scope_routes = tuple(
                        _route_bim_joist_block(
                            group,
                            tolerances,
                            joist_context,
                        )
                        for group in groups
                    )
                    beam_bim_scope = any(
                        route.handled
                        and (
                            route.candidates
                            or not route.messages
                            or any(
                                message.code != "BIM_JOIST_DETAIL_IGNORED"
                                for message in route.messages
                            )
                        )
                        for route in scope_routes
                    )

                role_group_count += len(groups)
                if excluded_handles:
                    active_groups = []
                    for group in groups:
                        group_handles = {
                            str(handle).strip().upper()
                            for handle in group.handles
                            if str(handle).strip()
                        }
                        if group_handles.intersection(excluded_handles):
                            excluded_group_count += 1
                            continue
                        active_groups.append(group)
                    groups = active_groups
                active_group_count += len(groups)
                ignored_text = sum(
                    item.status == "ignored"
                    and item.entity_type in self.TEXT_TYPES
                    for item in debug[debug_start:]
                )
                if ignored_text:
                    messages.append(
                        ValidationMessage(
                            "info",
                            "TEXT_SKIPPED",
                            f"已略過 {ignored_text} 個 DXF 文字圖元；文字不參與構件辨識。",
                            role,
                        )
                    )
                general_groups: list[_GeometryGroup] = []
                for group in groups:
                    if role == "beam" and beam_bim_scope:
                        joist_route = _route_bim_joist_block(
                            group,
                            tolerances,
                            joist_context,
                        )
                        if joist_route.handled:
                            messages.extend(joist_route.messages)
                            role_candidates.extend(joist_route.candidates)
                            continue
                    block_route = (
                        _route_component_like_strut_block(
                            group,
                            tolerances,
                            waler_context=waler_context,
                        )
                        if role == "strut"
                        else _route_component_like_member_block(
                            group,
                            tolerances,
                        )
                    )
                    if not block_route.handled:
                        general_groups.append(group)
                        continue
                    messages.extend(block_route.messages)
                    if block_route.candidate is not None:
                        role_candidates.append(block_route.candidate)

                groups = self._merge_related_line_groups(
                    general_groups,
                    tolerances,
                )
                for group in groups:
                    if role == "corner_brace":
                        corner_candidates, corner_messages = (
                            _corner_brace_candidates_from_group(
                                group,
                                tolerances,
                            )
                        )
                        messages.extend(corner_messages)
                        if corner_candidates:
                            role_candidates.extend(corner_candidates)
                            continue
                    candidate, candidate_messages = _candidate_from_group(
                        group,
                        role,
                        tolerances,
                    )
                    messages.extend(candidate_messages)
                    if candidate is None:
                        has_points = any(
                            primitive.points for primitive in group.primitives
                        )
                        has_nonzero_segment = any(
                            primitive.segments() for primitive in group.primitives
                        )
                        if has_points and not has_nonzero_segment:
                            messages.append(
                                ValidationMessage(
                                    "critical",
                                    "ZERO_LENGTH_COMPONENT",
                                    "來源幾何全部為零長度。",
                                    role,
                                    tuple(sorted(group.handles)),
                                )
                            )
                        code = f"{role.upper()}_RECOGNITION_FAILED"
                        engineering_line_code = (
                            "WALER_ENGINEERING_LINE_FAILED"
                            if role == "waler"
                            else f"{role.upper()}_CENTERLINE_FAILED"
                        )
                        handles = tuple(sorted(group.handles))
                        messages.append(
                            ValidationMessage(
                                "error",
                                code,
                                "幾何群組無法可靠辨識為單一工程構件。",
                                role,
                                handles,
                            )
                        )
                        messages.append(
                            ValidationMessage(
                                "error",
                                engineering_line_code,
                                (
                                    "圍令幾何群組無法建立可靠內側工程線。"
                                    if role == "waler"
                                    else "幾何群組無法建立可靠中心線。"
                                ),
                                role,
                                handles,
                            )
                        )
                        continue
                    if role == "waler":
                        messages.extend(
                            _characterize_waler_candidate_envelope(
                                candidate,
                                group,
                                tolerances,
                            )
                        )
                    component_length = (
                        sum(
                            _length(start, end)
                            for start, end in zip(
                                candidate.path_points,
                                candidate.path_points[1:],
                            )
                        )
                        if candidate.path_points
                        else _length(candidate.start, candidate.end)
                    )
                    if component_length <= 1e-9:
                        messages.append(
                            ValidationMessage(
                                "critical",
                                "ZERO_LENGTH_COMPONENT",
                                "辨識結果為零長度。",
                                role,
                                tuple(sorted(candidate.handles)),
                            )
                        )
                        continue
                    if component_length < tolerances.minimum_component_length_mm:
                        messages.append(
                            ValidationMessage(
                                "error",
                                "COMPONENT_TOO_SHORT",
                                f"構件長度 {component_length:.1f} 小於允許值。",
                                role,
                                tuple(sorted(candidate.handles)),
                            )
                        )
                        continue
                    role_candidates.append(candidate)
            deduplicated, duplicate_messages = _deduplicate_candidates(role_candidates, role, tolerances)
            messages.extend(duplicate_messages)
            candidates_by_role[role] = deduplicated
            if role == "waler":
                waler_context = _build_waler_span_context(deduplicated)
            all_geometry_explicitly_excluded = bool(
                role_group_count
                and not active_group_count
                and excluded_group_count == role_group_count
            )
            if layers and not deduplicated and not all_geometry_explicitly_excluded:
                messages.append(ValidationMessage("critical", f"{role.upper()}_RECOGNITION_FAILED", f"{role} 圖層沒有可匯入的工程構件。", role))

        # Preview-only roles retain source geometry while intentionally bypassing
        # recognition, candidate points, connections, associations and Solver.
        for role in preview_only_roles:
            source_counts[role] = 0
            for layer in selected[role]:
                entities = self.entities_on_layer(layer)
                source_counts[role] += len(entities)
                if role == "auxiliary":
                    self._collect_auxiliary_source_texts(
                        layer,
                        entities,
                        source_texts,
                        debug,
                    )
                self._geometry_groups(
                    role,
                    layer,
                    entities,
                    debug,
                    source_geometry,
                )

        if not contextual_geometry_finalized:
            messages.extend(
                _resolve_waler_contact_geometry(
                    candidates_by_role,
                    tolerances,
                )
            )
        self._validate_one_model_per_source(candidates_by_role, messages)
        walers = tuple(self._make_waler(index, candidate) for index, candidate in enumerate(candidates_by_role["waler"], 1))
        struts = tuple(self._make_strut(index, candidate) for index, candidate in enumerate(candidates_by_role["strut"], 1))
        braces = tuple(self._make_brace(index, candidate) for index, candidate in enumerate(candidates_by_role["brace"], 1))
        columns = tuple(
            self._make_auxiliary(Column, "C", "column", index, candidate)
            for index, candidate in enumerate(candidates_by_role["column"], 1)
        )
        beam_candidates = list(candidates_by_role["beam"])
        bim_positions = [
            index
            for index, candidate in enumerate(beam_candidates)
            if candidate.joist_assembly_key
        ]
        ordered_bim = iter(
            sorted(
                (beam_candidates[index] for index in bim_positions),
                key=lambda candidate: (
                    candidate.start,
                    candidate.end,
                    candidate.joist_axis_slot
                    if candidate.joist_axis_slot is not None
                    else -1,
                ),
            )
        )
        for index in bim_positions:
            beam_candidates[index] = next(ordered_bim)
        candidates_by_role["beam"] = beam_candidates
        beams = tuple(
            self._make_auxiliary(Beam, "BM", "beam", index, candidate)
            for index, candidate in enumerate(beam_candidates, 1)
        )
        corner_braces = tuple(
            self._make_auxiliary(
                CornerBrace,
                "CB",
                "corner_brace",
                index,
                candidate,
            )
            for index, candidate in enumerate(
                candidates_by_role["corner_brace"],
                1,
            )
        )
        struts, braces, connection_messages = connect_components_to_walers(struts, braces, walers, tolerances)
        double_support_candidates = detect_double_support_candidates(
            struts,
            tolerances,
        )
        (
            struts,
            columns,
            beams,
            component_associations,
            association_messages,
        ) = associate_components_to_struts(
            struts,
            columns,
            beams,
            tolerances,
            double_support_candidates=double_support_candidates,
        )
        struts = attach_corner_braces_to_struts(
            struts,
            walers,
            corner_braces,
            tolerances,
        )
        messages.extend(connection_messages)
        messages.extend(association_messages)
        final_debug = self._finalize_debug(
            debug,
            (*walers, *struts, *braces, *columns, *beams, *corner_braces),
        )
        world_result = DXFImportResult(
            str(self.file_path.resolve()),
            self.layer_names,
            selected,
            self.layer_information(),
            walers,
            struts,
            braces,
            final_debug,
            tuple(messages),
            source_counts,
            tuple(source_geometry),
            tuple(source_texts),
            columns=columns,
            beams=beams,
            corner_braces=corner_braces,
            layer_classification=layer_classification,
            component_associations=component_associations,
            beam_crossings=tuple(
                crossing for beam in beams for crossing in beam.crossings
            ),
            double_support_candidates=double_support_candidates,
            source_fingerprint=self.source_fingerprint,
            excluded_sources=normalized_exclusions,
        )
        world_result = recognize_result_material_specs(
            world_result,
            material_specs,
            tolerance_mm=tolerances.material_width_tolerance_mm,
        )
        world_result = build_candidate_points(world_result, tolerances)
        world_result = initialize_waler_contact_review(world_result, tolerances)
        return apply_coordinate_system(
            world_result,
            coordinate_system or CoordinateSystem(),
        )

    def _collect_auxiliary_source_texts(
        self,
        layer: str,
        entities: Sequence[Any],
        source_texts: list[SourceText],
        debug: list[EntityDebugInfo],
    ) -> None:
        """Collect displayed text recursively without exposing it to recognition."""

        if _recursive_decompose is None:
            return
        for entity in entities:
            root_handle = str(
                getattr(entity.dxf, "handle", "")
                or f"NO_HANDLE_TEXT_{len(source_texts)}"
            )
            try:
                leaves = list(_recursive_decompose((entity,)))
                leaves.extend(self._unbound_nested_attdefs(entity))
                for leaf in leaves:
                    entity_type = leaf.dxftype()
                    if entity_type not in self.TEXT_TYPES:
                        continue
                    text = self._source_text_content(leaf)
                    position = self._source_text_position(leaf)
                    if not text or position is None:
                        continue
                    source_texts.append(
                        SourceText(
                            role="auxiliary",
                            source_handle=root_handle,
                            text=text,
                            position=position,
                            height=self._source_text_height(leaf),
                            rotation=self._source_text_rotation(leaf),
                            source_layer=layer,
                            source_entity_type=entity_type,
                        )
                    )
            except Exception as exc:
                debug.append(
                    EntityDebugInfo(
                        "auxiliary",
                        layer,
                        entity.dxftype(),
                        root_handle,
                        "preview_failed",
                        "warning",
                        detail=f"Unable to read preview text: {exc}",
                    )
                )

    def _unbound_nested_attdefs(self, entity: Any) -> list[Any]:
        """Return nested ATTDEF defaults that have no displayed ATTRIB."""

        if entity.dxftype() != "INSERT":
            return []
        result: list[Any] = []
        attached_tags = {
            str(getattr(attrib.dxf, "tag", "")).casefold()
            for attrib in getattr(entity, "attribs", ())
        }
        block = entity.block()
        if block is not None:
            transform = entity.matrix44()
            for child in block:
                if child.dxftype() != "ATTDEF":
                    continue
                tag = str(getattr(child.dxf, "tag", "")).casefold()
                if tag in attached_tags:
                    continue
                copy = child.copy()
                copy.transform(transform)
                result.append(copy)
        try:
            virtual_entities = entity.virtual_entities()
            for child in virtual_entities:
                if child.dxftype() == "INSERT":
                    result.extend(self._unbound_nested_attdefs(child))
        except Exception:
            pass
        return result

    @staticmethod
    def _source_text_content(entity: Any) -> str:
        if entity.dxftype() == "MTEXT":
            plain_text = getattr(entity, "plain_text", None)
            value = plain_text() if callable(plain_text) else entity.dxf.text
        else:
            value = getattr(entity.dxf, "text", "")
        return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()

    @staticmethod
    def _source_text_position(entity: Any) -> Point | None:
        get_placement = getattr(entity, "get_placement", None)
        if callable(get_placement):
            try:
                _alignment, point, _second_point = get_placement()
                return _point(point)
            except (AttributeError, TypeError, ValueError):
                pass
        insert = getattr(entity.dxf, "insert", None)
        return None if insert is None else _point(insert)

    @staticmethod
    def _source_text_height(entity: Any) -> float:
        attribute = "char_height" if entity.dxftype() == "MTEXT" else "height"
        try:
            return max(
                float(getattr(entity.dxf, attribute, 0.0) or 0.0),
                0.0,
            )
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _source_text_rotation(entity: Any) -> float:
        get_rotation = getattr(entity, "get_rotation", None)
        try:
            if callable(get_rotation):
                return float(get_rotation())
            return float(getattr(entity.dxf, "rotation", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _hatch_point_to_wcs(entity: Any, point: Any) -> Point:
        elevation = float(getattr(entity.dxf.elevation, "z", 0.0) or 0.0)
        if Vec3 is None:  # pragma: no cover - guarded by the importer dependency
            raise DXFImportError("尚未安裝 ezdxf；無法解析 HATCH boundary。")
        world = entity.ocs().to_wcs(
            Vec3(float(point[0]), float(point[1]), elevation)
        )
        return _point(world)

    @classmethod
    def _extract_hatch_waler_source(
        cls,
        entity: Any,
        layer: str,
        source_geometry: list[SourceGeometry],
    ) -> HatchWalerSource:
        """Translate one top-level Waler HATCH boundary from OCS to WCS."""

        handle = str(getattr(entity.dxf, "handle", "") or "NO_HANDLE_HATCH")
        paths: list[HatchBoundaryPath] = []
        for boundary_path in entity.paths:
            segments: list[tuple[Point, Point]] = []
            unsupported: list[str] = []
            path_name = type(boundary_path).__name__
            if path_name == "EdgePath":
                for edge in boundary_path.edges:
                    if type(edge).__name__ != "LineEdge":
                        unsupported.append(type(edge).__name__)
                        continue
                    segments.append(
                        (
                            cls._hatch_point_to_wcs(entity, edge.start),
                            cls._hatch_point_to_wcs(entity, edge.end),
                        )
                    )
            elif path_name == "PolylinePath":
                vertices = tuple(boundary_path.vertices)
                if any(abs(float(vertex[2])) > 0.0 for vertex in vertices):
                    unsupported.append("PolylineBulge")
                points = tuple(
                    cls._hatch_point_to_wcs(entity, vertex)
                    for vertex in vertices
                )
                segments.extend(zip(points, points[1:]))
                if bool(boundary_path.is_closed) and len(points) > 2:
                    segments.append((points[-1], points[0]))
            else:
                unsupported.append(path_name)

            for start, end in segments:
                source_geometry.append(
                    SourceGeometry(
                        "waler",
                        handle,
                        (start, end),
                        False,
                        layer,
                        "HATCH",
                    )
                )
            paths.append(
                HatchBoundaryPath(
                    tuple(segments),
                    is_external=bool(
                        int(getattr(boundary_path, "path_type_flags", 0))
                        & BOUNDARY_PATH_EXTERNAL
                    ),
                    unsupported_geometry=tuple(sorted(set(unsupported))),
                )
            )
        return HatchWalerSource(handle, layer, tuple(paths))

    @staticmethod
    def _candidate_from_hatch_waler(
        outcome: HatchWalerRecognition,
        tolerances: GeometryTolerances,
    ) -> _Candidate:
        if outcome.status != "recognized" or outcome.axis is None:
            raise ValueError("Only a recognized HATCH Waler can become a candidate")
        source_points = tuple(
            dict.fromkeys(
                point
                for segment in outcome.exterior_segments
                for point in segment
            )
        )
        envelope = extract_waler_envelope_facts(
            outcome.boundary_lines,
            tolerances,
            source_handles=(outcome.source_handle,),
            component_key=f"waler:{outcome.source_handle}",
            qualified_exterior_faces=outcome.boundary_lines,
            provenance_kind="hatch_exterior",
        )
        return _Candidate(
            outcome.axis[0],
            outcome.axis[1],
            "hatch_rc_outline_axis",
            True,
            outcome.source_width,
            outcome.confidence,
            outcome.source_layer,
            {outcome.source_handle},
            {"HATCH"},
            [],
            {f"waler:{outcome.source_handle}"},
            [],
            boundary_lines=outcome.boundary_lines,
            recognized_axis=outcome.axis,
            source_points=source_points,
            material_spec=outcome.material_spec,
            material_spec_source=outcome.material_spec_source,
            waler_envelope_facts=envelope.facts,
        )

    def _geometry_groups(
        self,
        role: str,
        layer: str,
        entities: Sequence[Any],
        debug: list[EntityDebugInfo],
        source_geometry: list[SourceGeometry],
    ) -> list[_GeometryGroup]:
        groups: list[_GeometryGroup] = []
        ignored_text = 0
        for entity in entities:
            handle = str(getattr(entity.dxf, "handle", "") or f"NO_HANDLE_{len(groups)}")
            group = _GeometryGroup(
                key=f"{role}:{handle}",
                role=role,
                layer=layer,
                primitives=[],
                handles={handle},
                entity_types=set(),
                block_instances=[],
                root_handle=handle,
                root_entity_type=entity.dxftype(),
            )
            if entity.dxftype() in self.TEXT_TYPES:
                ignored_text += 1
                debug.append(
                    EntityDebugInfo(
                        role,
                        layer,
                        entity.dxftype(),
                        handle,
                        "preview_only" if role == "auxiliary" else "ignored",
                        "info",
                        detail=(
                            "文字僅保留於輔助底稿預覽，不參與構件辨識。"
                            if role == "auxiliary"
                            else "文字不參與構件辨識。"
                        ),
                    )
                )
                continue
            self._extract_entity(entity, group, debug, source_geometry, handle)
            if group.primitives or entity.dxftype() in self.GEOMETRY_TYPES:
                groups.append(group)
        if ignored_text:
            debug.append(
                EntityDebugInfo(
                    role,
                    layer,
                    "TEXT_SUMMARY",
                    "",
                    "preview_only" if role == "auxiliary" else "ignored",
                    "info",
                    detail=(
                        f"共保留 {ignored_text} 個頂層文字供輔助底稿預覽。"
                        if role == "auxiliary"
                        else f"共略過 {ignored_text} 個 DXF 文字圖元。"
                    ),
                )
            )
        return groups

    def _extract_entity(
        self,
        entity: Any,
        group: _GeometryGroup,
        debug: list[EntityDebugInfo],
        source_geometry: list[SourceGeometry],
        root_handle: str,
        block_name: str = "",
    ) -> None:
        entity_type = entity.dxftype()
        if group.root_handle is None and not group.root_entity_type:
            group.root_handle = root_handle
            group.root_entity_type = entity_type
        group.handles.add(root_handle)
        if entity_type in self.TEXT_TYPES:
            debug.append(
                EntityDebugInfo(
                    group.role,
                    group.layer,
                    entity_type,
                    root_handle,
                    "preview_only" if group.role == "auxiliary" else "ignored",
                    "info",
                    block_instance=block_name,
                    detail=(
                        "文字僅保留於輔助底稿預覽，不參與構件辨識。"
                        if group.role == "auxiliary"
                        else "文字不參與構件辨識。"
                    ),
                )
            )
            return
        group.entity_types.add(entity_type)
        try:
            if entity_type == "INSERT":
                info = BlockInstanceInfo(
                    root_handle,
                    str(entity.dxf.name),
                    _point(entity.dxf.insert),
                    float(entity.dxf.rotation),
                    float(entity.dxf.xscale),
                    float(entity.dxf.yscale),
                )
                group.block_instances.append(info)
                debug.append(EntityDebugInfo(group.role, group.layer, entity_type, root_handle, "expanded", "info", block_instance=info.block_name, detail="virtual_entities 已套用 insertion/rotation/scale 完整座標轉換。"))
                for child in entity.virtual_entities():
                    self._extract_entity(child, group, debug, source_geometry, root_handle, info.block_name)
                return
            points: list[Point]
            closed = False
            source_width = 0.0
            if entity_type == "LINE":
                points = [_point(entity.dxf.start), _point(entity.dxf.end)]
            elif entity_type == "LWPOLYLINE":
                points = _lwpolyline_world_vertices(entity)
                closed = bool(entity.closed)
            elif entity_type == "POLYLINE":
                points = _polyline_world_vertices(entity)
                closed = bool(entity.is_closed)
            elif entity_type == "MLINE":
                points, source_width = _mline_center_path(entity)
                is_closed = getattr(entity, "is_closed", False)
                closed = bool(is_closed() if callable(is_closed) else is_closed)
            elif entity_type in {"SOLID", "TRACE"}:
                points = _solid_trace_world_vertices(entity)
                closed = True
            else:
                debug.append(EntityDebugInfo(group.role, group.layer, entity_type, root_handle, "unsupported", "info", block_instance=block_name, detail="非直線工程幾何，已略過。"))
                return
            if len(points) > 2 and _same_point(points[0], points[-1], 1e-6):
                points.pop()
                closed = True
            primitive = _Primitive(
                points,
                closed,
                entity_type,
                root_handle,
                source_width,
            )
            group.primitives.append(primitive)
            if entity_type == "MLINE":
                # Recognition uses the computed ordered centre path, while the
                # gray DXF underlay should still look like the original MLINE
                # rails/end caps shown in CAD.
                virtual_count = 0
                for child in entity.virtual_entities():
                    if child.dxftype() != "LINE":
                        continue
                    source_geometry.append(
                        SourceGeometry(
                            group.role,
                            root_handle,
                            (
                                _point(child.dxf.start),
                                _point(child.dxf.end),
                            ),
                            False,
                            group.layer,
                            "MLINE",
                        )
                    )
                    virtual_count += 1
                if not virtual_count:
                    source_geometry.append(
                        SourceGeometry(
                            group.role,
                            root_handle,
                            tuple(points),
                            closed,
                            group.layer,
                            entity_type,
                        )
                    )
            else:
                source_geometry.append(
                    SourceGeometry(
                        group.role,
                        root_handle,
                        tuple(points),
                        closed,
                        group.layer,
                        entity_type,
                    )
                )
            debug.append(
                EntityDebugInfo(
                    group.role,
                    group.layer,
                    entity_type,
                    root_handle,
                    "read",
                    "info",
                    block_instance=block_name,
                    detail=(
                        f"已由 MLINE 外緣計算構件中線；寬度約 {source_width:.3f}。"
                        if entity_type == "MLINE"
                        else ""
                    ),
                )
            )
        except Exception as exc:
            debug.append(EntityDebugInfo(group.role, group.layer, entity_type, root_handle, "error", "error", block_instance=block_name, detail=str(exc)))

    @staticmethod
    def _merge_related_line_groups(
        groups: Sequence[_GeometryGroup],
        tolerances: GeometryTolerances,
    ) -> list[_GeometryGroup]:
        line_groups = [
            group
            for group in groups
            if (
                str(group.root_entity_type).strip().upper() != "INSERT"
                and len(group.primitives) == 1
                and group.primitives[0].entity_type == "LINE"
            )
        ]
        others = [group for group in groups if group not in line_groups]
        unseen = set(range(len(line_groups)))
        while unseen:
            seed = unseen.pop()
            component = {seed}
            queue = [seed]
            while queue:
                current = queue.pop()
                current_line = line_groups[current].primitives[0].segments()[0]
                related = []
                for candidate in list(unseen):
                    candidate_line = line_groups[candidate].primitives[0].segments()[0]
                    endpoints_touch = any(
                        _same_point(a, b, tolerances.endpoint_tolerance_mm)
                        for a in current_line
                        for b in candidate_line
                    )
                    # Separate parallel LINE entities may already be valid
                    # engineering centrelines.  Merge them only when endpoint
                    # connectivity supplies the missing outline/end-cap
                    # evidence; INSERT children are already in one group.
                    if endpoints_touch:
                        related.append(candidate)
                for candidate in related:
                    unseen.remove(candidate)
                    component.add(candidate)
                    queue.append(candidate)
            if len(component) == 1:
                others.append(line_groups[seed])
                continue
            merged_groups = [line_groups[index] for index in component]
            merged = _GeometryGroup(
                key="+".join(sorted(group.key for group in merged_groups)),
                role=merged_groups[0].role,
                layer=merged_groups[0].layer,
                primitives=[
                    primitive
                    for group in merged_groups
                    for primitive in group.primitives
                ],
                handles=set().union(*(group.handles for group in merged_groups)),
                entity_types=set().union(
                    *(group.entity_types for group in merged_groups)
                ),
                block_instances=[
                    instance
                    for group in merged_groups
                    for instance in group.block_instances
                ],
                root_handle=None,
                root_entity_type="LINE",
            )
            others.append(merged)
        return others

    @staticmethod
    def _validate_one_model_per_source(
        candidates_by_role: Mapping[str, Sequence[_Candidate]],
        messages: list[ValidationMessage],
    ) -> None:
        for role, candidates in candidates_by_role.items():
            owners: dict[str, list[_Candidate]] = defaultdict(list)
            for candidate in candidates:
                for handle in candidate.handles:
                    owners[handle].append(candidate)
            for handle, source_candidates in owners.items():
                count = len(source_candidates)
                if count <= 1:
                    continue
                if role == "corner_brace" and all(
                    candidate.recognition_method
                    in {
                        "connection_plate_midpoints",
                        "connection_face_midpoints",
                        "brace_centerline_intersections",
                    }
                    for candidate in source_candidates
                ):
                    # A fabrication INSERT legitimately contains the left and
                    # right corner braces around one Strut.
                    continue
                if (
                    role == "beam"
                    and count == 2
                    and len(
                        {
                            candidate.joist_assembly_key
                            for candidate in source_candidates
                        }
                    )
                    == 1
                    and "" not in {
                        candidate.joist_assembly_key
                        for candidate in source_candidates
                    }
                    and {
                        candidate.joist_axis_slot
                        for candidate in source_candidates
                    }
                    == {0, 1}
                ):
                    continue
                messages.append(
                    ValidationMessage(
                        "critical",
                        "MULTIPLE_MODELS_FROM_ONE_SOURCE",
                        f"來源 {handle} 產生 {count} 個工程模型。",
                        role,
                        (handle,),
                    )
                )

    @classmethod
    def _build_joist_context(
        cls,
        candidates_by_role: Mapping[str, Sequence[_Candidate]],
        tolerances: GeometryTolerances,
    ) -> JoistContextSnapshot:
        """Freeze formal upstream geometry before Beam recognition starts."""

        struts = tuple(
            cls._make_strut(index, candidate)
            for index, candidate in enumerate(
                candidates_by_role.get("strut", ()),
                1,
            )
        )
        braces = tuple(
            cls._make_brace(index, candidate)
            for index, candidate in enumerate(
                candidates_by_role.get("brace", ()),
                1,
            )
        )
        columns = tuple(
            cls._make_auxiliary(Column, "C", "column", index, candidate)
            for index, candidate in enumerate(
                candidates_by_role.get("column", ()),
                1,
            )
        )
        _struts, associated_columns, _beams, _associations, _messages = (
            associate_components_to_struts(
                struts,
                columns,
                (),
                tolerances,
            )
        )
        return JoistContextSnapshot(
            struts=tuple(
                JoistMemberReference(
                    strut.id,
                    strut.world_start or strut.start,
                    strut.world_end or strut.end,
                    strut.source_handles,
                    strut.source_width,
                )
                for strut in struts
            ),
            braces=tuple(
                JoistMemberReference(
                    brace.id,
                    brace.world_start or brace.start,
                    brace.world_end or brace.end,
                    brace.source_handles,
                    brace.source_width,
                )
                for brace in braces
            ),
            column_stations=tuple(
                JoistColumnStationReference(
                    column.id,
                    column.associated_strut_id,
                    float(column.association_station),
                )
                for column in associated_columns
                if column.associated_strut_id
                and column.association_station is not None
            ),
        )

    @staticmethod
    def _make_waler(index: int, candidate: _Candidate) -> Waler:
        line_candidates = _engineering_line_candidates("waler", candidate)
        return Waler(
            f"W{index}", candidate.start, candidate.end, candidate.layer,
            tuple(sorted(candidate.handles)), tuple(sorted(candidate.entity_types)),
            candidate.recognition_method, candidate.centerline_computed,
            candidate.source_width, candidate.confidence,
            tuple(dict.fromkeys(candidate.warnings)), tuple(candidate.block_instances),
            line_candidates=line_candidates,
            selected_candidate_id=line_candidates[0].id,
            material_spec=candidate.material_spec,
            material_spec_source=candidate.material_spec_source,
        )

    @staticmethod
    def _make_strut(index: int, candidate: _Candidate) -> Strut:
        line_candidates = _engineering_line_candidates("strut", candidate)
        return Strut(
            f"S{index}", candidate.start, candidate.end, candidate.layer,
            tuple(sorted(candidate.handles)), tuple(sorted(candidate.entity_types)),
            candidate.recognition_method, candidate.centerline_computed,
            candidate.source_width, "", "", candidate.confidence,
            tuple(dict.fromkeys(candidate.warnings)), tuple(candidate.block_instances),
            line_candidates=line_candidates,
            selected_candidate_id=line_candidates[0].id,
        )

    @staticmethod
    def _make_brace(index: int, candidate: _Candidate) -> Brace:
        line_candidates = _engineering_line_candidates("brace", candidate)
        return Brace(
            f"B{index}", candidate.start, candidate.end, candidate.layer,
            tuple(sorted(candidate.handles)), tuple(sorted(candidate.entity_types)),
            candidate.recognition_method, candidate.centerline_computed,
            candidate.source_width, "", "", candidate.confidence,
            tuple(dict.fromkeys(candidate.warnings)), tuple(candidate.block_instances),
            line_candidates=line_candidates,
            selected_candidate_id=line_candidates[0].id,
        )

    @staticmethod
    def _make_auxiliary(
        component_type: type[AuxiliaryComponent],
        prefix: str,
        role: str,
        index: int,
        candidate: _Candidate,
    ) -> AuxiliaryComponent:
        line_candidates = _engineering_line_candidates(role, candidate)
        reference_point = candidate.reference_point or _midpoint(
            candidate.start,
            candidate.end,
        )
        beam_path_changes: dict[str, Any] = {}
        if issubclass(component_type, Beam):
            world_path = candidate.path_points or (
                candidate.start,
                candidate.end,
            )
            beam_id = f"{prefix}{index}"
            beam_path_changes = {
                "world_path": tuple(world_path),
                "local_path": tuple(world_path),
                "path": tuple(world_path),
                "joist_assembly_key": candidate.joist_assembly_key,
                "joist_axis_slot": candidate.joist_axis_slot,
                "crossings": tuple(
                    BeamCrossing(
                        beam_id,
                        contact.member_id,
                        contact.point,
                        contact.point,
                        contact.member_station,
                        0,
                        _distance(contact.source_contact_point, contact.point),
                        contact.recognition_method,
                        contact.source_contact_point,
                        contact.source_contact_point,
                    )
                    for contact in candidate.joist_contacts
                    if contact.member_role == "strut"
                ),
            }
        return component_type(
            f"{prefix}{index}",
            candidate.start,
            candidate.end,
            candidate.layer,
            tuple(sorted(candidate.handles)),
            tuple(sorted(candidate.entity_types)),
            candidate.recognition_method,
            candidate.centerline_computed,
            candidate.source_width,
            candidate.confidence,
            tuple(dict.fromkeys(candidate.warnings)),
            tuple(candidate.block_instances),
            line_candidates=line_candidates,
            selected_candidate_id=line_candidates[0].id,
            reference_point=reference_point,
            world_reference_point=reference_point,
            local_reference_point=reference_point,
            **beam_path_changes,
        )

    @staticmethod
    def _finalize_debug(
        debug: Sequence[EntityDebugInfo],
        members: Sequence[Waler | Strut | Brace | AuxiliaryComponent],
    ) -> tuple[EntityDebugInfo, ...]:
        outputs: dict[tuple[str, str], list[str]] = defaultdict(list)
        for member in members:
            if isinstance(member, Waler):
                role = "waler"
            elif isinstance(member, Strut):
                role = "strut"
            elif isinstance(member, Brace):
                role = "brace"
            elif isinstance(member, Column):
                role = "column"
            elif isinstance(member, Beam):
                role = "beam"
            else:
                role = "corner_brace"
            for handle in member.source_handles:
                outputs[(role, handle)].append(member.id)
        result = []
        for item in debug:
            ids = tuple(dict.fromkeys(outputs.get((item.role, item.handle), ())))
            status = "converted" if ids and item.status in {"read", "expanded"} else item.status
            result.append(replace(item, status=status, output_ids=ids))
        return tuple(result)


def read_dxf_layers(file_path: str | Path) -> list[str]:
    return list(DXFImporter(file_path).read().layer_names)


def import_dxf(
    file_path: str | Path,
    *,
    strut_layer: str | None = None,
    waler_layer: str | None = None,
    brace_layer: str | None = None,
    layer_roles: Mapping[str, str] | None = None,
    endpoint_tolerance: float | None = None,
    tolerances: GeometryTolerances | None = None,
    coordinate_system: CoordinateSystem | None = None,
    material_specs: Sequence[Mapping[str, Any]] = (),
    excluded_sources: Sequence[ExcludedSource | Mapping[str, Any]] = (),
) -> DXFImportResult:
    return DXFImporter(file_path, tolerances=tolerances).read().convert(
        strut_layer=strut_layer,
        waler_layer=waler_layer,
        brace_layer=brace_layer,
        layer_roles=layer_roles,
        endpoint_tolerance=endpoint_tolerance,
        coordinate_system=coordinate_system,
        material_specs=material_specs,
        excluded_sources=excluded_sources,
    )


Y1A_LAYER_MAPPING = {
    "L-SITE-WALL": "連續壁",
    "ES-圍令L1H350x350": "圍令",
    "ES-LH350x350": "支撐",
    "ES-大斜撐_支撐350x350": "斜撐",
    "!T1 (站體)_角撐": "角撐",
    "ES-中間樁NO": "中間柱",
    "ES-C250x90": "托梁",
    "DIM-軸線U": "輔助線",
    "DIM-軸線X": "輔助線",
}

Y29_LAYER_MAPPING = {
    "圍令": "圍令",
    "支撐": "支撐",
    "斜撐": "斜撐",
    "細線": "連續壁",
    "s": "中間柱",
    "S-GRID": "輔助線",
    "S-GRID-IDEN": "輔助線",
    "壓梁": "托梁",
    "壓樑": "托梁",
    "角撐": "角撐",
}

Y05_LAYER_MAPPING = {
    "I-WALL": "連續壁",
    "0": "連續壁",
    "圍令": "圍令",
    "支撐": "支撐",
    "托梁": "托梁",
    "斜撐": "斜撐",
    "S-BEAM": "角撐",
    "S-GRID": "輔助線",
    "S-GRID-IDEN": "輔助線",
    "S-COLS": "中間柱",
}

# Backwards-compatible name for the original Y1A defaults.  The import dialog
# uses default_layer_mapping_for_file() so these defaults never leak to an
# unrelated DXF merely because it contains the same layer name.
DEFAULT_LAYER_MAPPING = Y1A_LAYER_MAPPING

LAYER_MAPPING_BY_FILENAME = {
    "y1a擋土支撐簡化版.dxf": Y1A_LAYER_MAPPING,
    "y29_test.dxf": Y29_LAYER_MAPPING,
    "670-co-y05-fw-圖紙 - 005 - y05站 安全支撐系統 第一層支撐平面圖.dxf": Y05_LAYER_MAPPING,
}


def default_layer_mapping_for_file(file_path: str | Path) -> Mapping[str, str]:
    """Return exact filename-scoped layer defaults, or no defaults."""

    return LAYER_MAPPING_BY_FILENAME.get(Path(file_path).name.casefold(), {})
