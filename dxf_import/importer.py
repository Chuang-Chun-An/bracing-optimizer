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
except ImportError:  # pragma: no cover - only a broken installation
    ezdxf = None
    _recursive_decompose = None

from .candidate_points import (
    attach_auxiliary_components,
    attach_corner_braces_to_struts,
    build_candidate_points,
    connect_components_to_walers,
    associate_components_to_struts,
)
from .geometry import (
    Point,
    _distance,
    _length,
    _midpoint,
    _point,
    _same_point,
)
from .models import (
    AuxiliaryComponent,
    Beam,
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
    _corner_brace_candidates_from_group,
    _deduplicate_candidates,
    _engineering_line_candidates,
    _mline_center_path,
    _refine_corner_brace_axis_intersections,
    _select_waler_inner_lines,
)
from .validation import validate_duplicate_engineering_members
from .support_pairing import detect_double_support_candidates
from .waler_contact_adjustment import initialize_waler_contact_review
from .material_recognition import recognize_result_material_specs


def _lwpolyline_world_vertices(entity: Any) -> list[Point]:
    """Return LWPOLYLINE vertices normalized from entity OCS to WCS."""

    return [_point(vertex) for vertex in entity.vertices_in_wcs()]


def _polyline_world_vertices(entity: Any) -> list[Point]:
    """Return 2D/3D POLYLINE vertices in WCS using ezdxf semantics."""

    return [_point(vertex) for vertex in entity.points_in_wcs()]


def _solid_trace_world_vertices(entity: Any) -> list[Point]:
    """Return graphical SOLID/TRACE vertices normalized from OCS to WCS."""

    return [_point(vertex) for vertex in entity.wcs_vertices()]


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
            "column",
            "beam",
            "corner_brace",
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
        normalized_exclusions = normalize_excluded_sources(excluded_sources)
        excluded_handles_by_role: dict[str, set[str]] = defaultdict(set)
        for excluded in normalized_exclusions:
            excluded_handles_by_role[excluded.role].update(excluded.source_handles)

        for role in engineering_roles:
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
                groups = self._geometry_groups(
                    role,
                    layer,
                    entities,
                    debug,
                    source_geometry,
                )
                role_group_count += len(groups)
                excluded_handles = excluded_handles_by_role.get(role, set())
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
                groups = self._merge_related_line_groups(groups, tolerances)
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

        _select_waler_inner_lines(candidates_by_role)
        messages.extend(
            _refine_corner_brace_axis_intersections(
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
        beams = tuple(
            self._make_auxiliary(Beam, "BM", "beam", index, candidate)
            for index, candidate in enumerate(candidates_by_role["beam"], 1)
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
                f"{role}:{handle}", role, layer, [], {handle}, set(), []
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
        line_groups = [group for group in groups if len(group.primitives) == 1 and group.primitives[0].entity_type == "LINE"]
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
                "+".join(sorted(group.key for group in merged_groups)),
                merged_groups[0].role,
                merged_groups[0].layer,
                [primitive for group in merged_groups for primitive in group.primitives],
                set().union(*(group.handles for group in merged_groups)),
                set().union(*(group.entity_types for group in merged_groups)),
                [instance for group in merged_groups for instance in group.block_instances],
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
                messages.append(
                    ValidationMessage(
                        "critical",
                        "MULTIPLE_MODELS_FROM_ONE_SOURCE",
                        f"來源 {handle} 產生 {count} 個工程模型。",
                        role,
                        (handle,),
                    )
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
            beam_path_changes = {
                "world_path": tuple(world_path),
                "local_path": tuple(world_path),
                "path": tuple(world_path),
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

# Backwards-compatible name for the original Y1A defaults.  The import dialog
# uses default_layer_mapping_for_file() so these defaults never leak to an
# unrelated DXF merely because it contains the same layer name.
DEFAULT_LAYER_MAPPING = Y1A_LAYER_MAPPING

LAYER_MAPPING_BY_FILENAME = {
    "y1a擋土支撐簡化版.dxf": Y1A_LAYER_MAPPING,
    "y29_test.dxf": Y29_LAYER_MAPPING,
}


def default_layer_mapping_for_file(file_path: str | Path) -> Mapping[str, str]:
    """Return exact filename-scoped layer defaults, or no defaults."""

    return LAYER_MAPPING_BY_FILENAME.get(Path(file_path).name.casefold(), {})
