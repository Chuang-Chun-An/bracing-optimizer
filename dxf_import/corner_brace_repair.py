"""Pure planning and staged application for manual CornerBrace repair.

The automatic recognizer intentionally does not import this module.  Repair is
an explicit STEP4 review operation: exact residual DXF geometry creates axis
hypotheses, existing confirmed engineering members provide consistency
evidence, and only finite Waler/Strut intersections become preview candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from .candidate_points import (
    attach_corner_braces_to_struts,
    rebuild_candidate_points_for_components,
)
from .geometry import (
    Point,
    _angle_difference_deg,
    _cross,
    _distance,
    _dot,
    _length,
    _midpoint,
    _ordered_line,
    _projection_overlap_ratio,
    _segment_distance,
    _segment_intersection_point,
    _unit,
    _vector,
)
from .models import (
    CornerBrace,
    CornerBraceBodyRelationshipAssessment,
    CornerBraceConnection,
    CornerBraceRepairProvenance,
    CornerBraceRepairReference,
    CornerBraceRepairSubjectKey,
    DXFImportError,
    DXFImportResult,
    GeometryTolerances,
    ReviewItem,
    SourceGeometry,
)
from .review_confirmation import review_item_is_confirmed
from .source_exclusion import canonical_source_identity, normalize_source_handles
from .validation import validate_duplicate_engineering_members
from .waler_contact_adjustment import build_corner_brace_connections


REPAIR_SELECTION_SOURCE = "corner_brace_repair"
REPAIR_RECOGNITION_METHOD = "manual_corner_brace_repair"
PRIMARY_REFERENCE = "automatic_primary"
SECONDARY_REFERENCE = "manual_repaired_secondary"


@dataclass(frozen=True)
class CornerBraceReferenceEvidence:
    """Current, fully validated evidence from one existing CornerBrace."""

    reference: CornerBraceRepairReference
    connection: CornerBraceConnection
    world_start: Point
    world_end: Point
    side: int
    topology: str


@dataclass(frozen=True)
class TargetRepairAnchor:
    """One exact-source point that spatially validates a transferred line."""

    point: Point
    kind: str
    source_handle: str


@dataclass(frozen=True)
class TargetRepairEvidence:
    """Deterministic direction and position evidence from the exact target."""

    direction_hypotheses: tuple[tuple[Point, Point], ...]
    positional_anchors: tuple[TargetRepairAnchor, ...]
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class CornerBraceLocalTemplate:
    """World-independent local dimensions extracted from one primary."""

    reference: CornerBraceRepairReference
    topology: str
    side: int
    waler_offset_mm: float
    strut_station_mm: float
    fixed_length_mm: float
    relationship_waler_id: str
    relationship_strut_id: str


@dataclass(frozen=True)
class TargetRelationshipFrame:
    """Finite Waler/Strut frame for one target endpoint relationship."""

    waler_id: str
    strut_id: str
    endpoint_name: str
    origin: Point
    inward: Point
    waler_axis: Point
    waler_line: tuple[Point, Point]
    strut_line: tuple[Point, Point]


@dataclass(frozen=True)
class CornerBraceRepairCandidate:
    """One fully eligible, deterministic candidate safe to preview."""

    id: str
    world_start: Point
    world_end: Point
    target_waler_id: str
    target_strut_id: str
    target_strut_endpoint_name: str
    template_reference: CornerBraceRepairReference | None
    transfer_mode: str
    reference_waler_offset_mm: float
    reference_strut_station_mm: float
    reference_fixed_length_mm: float
    target_evidence: TargetRepairEvidence
    matched_direction: tuple[Point, Point]
    positional_anchor: Point
    primary_references: tuple[CornerBraceRepairReference, ...]
    secondary_references: tuple[CornerBraceRepairReference, ...] = ()
    residual_axis: tuple[Point, Point] = ((0.0, 0.0), (0.0, 0.0))
    proximity_mm: float = 0.0
    diagnostics: tuple[str, ...] = ()
    selection_mode: str = "reference_template"
    body_signature: str = ""
    relationship_assessment: CornerBraceBodyRelationshipAssessment | None = None

    @property
    def fixed_length_mm(self) -> float:
        return _distance(self.world_start, self.world_end)


@dataclass(frozen=True)
class CornerBraceRepairPlan:
    """Immutable preview result.  Rejections never appear as candidates."""

    base_revision: int
    subject_key: CornerBraceRepairSubjectKey
    subject_signature: str
    target_kind: str
    target_member_id: str
    preferred_display_id: str
    residual_segments: tuple[tuple[Point, Point], ...]
    candidates: tuple[CornerBraceRepairCandidate, ...]
    diagnostics: tuple[str, ...] = ()
    selection_mode: str = "reference_template"


def _quantization(tolerances: GeometryTolerances) -> float:
    return max(
        min(tolerances.collinear_tolerance_mm, tolerances.duplicate_tolerance_mm),
        1e-6,
    )


def _quantized_point(point: Point, tolerances: GeometryTolerances) -> tuple[int, int]:
    quantum = _quantization(tolerances)
    return round(point[0] / quantum), round(point[1] / quantum)


def _line_key(line: tuple[Point, Point], tolerances: GeometryTolerances) -> str:
    start, end = _ordered_line(*line)
    return json.dumps(
        (_quantized_point(start, tolerances), _quantized_point(end, tolerances)),
        separators=(",", ":"),
    )


def _canonical_json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def _world_line(member: Any) -> tuple[Point, Point]:
    return member.world_start or member.start, member.world_end or member.end


def _source_segments(
    geometry: SourceGeometry,
    tolerances: GeometryTolerances,
) -> tuple[tuple[Point, Point], ...]:
    points = tuple(geometry.points)
    pairs = list(zip(points, points[1:]))
    if geometry.closed and len(points) > 2:
        pairs.append((points[-1], points[0]))
    minimum = max(tolerances.minimum_component_length_mm, tolerances.collinear_tolerance_mm)
    return tuple(
        _ordered_line(start, end)
        for start, end in pairs
        if _length(start, end) >= minimum
    )


def _exact_source_geometry(
    result: DXFImportResult,
    source_handles: Sequence[str],
) -> tuple[SourceGeometry, ...]:
    handles = set(normalize_source_handles(source_handles))
    return tuple(
        geometry
        for geometry in result.source_geometry
        if geometry.role == "corner_brace"
        and str(geometry.source_handle).strip().upper() in handles
    )


def _base_geometry_key(
    result: DXFImportResult,
    item: ReviewItem,
    tolerances: GeometryTolerances,
) -> str:
    if item.member_id:
        member = next(
            (candidate for candidate in result.corner_braces if candidate.id == item.member_id),
            None,
        )
        if member is not None:
            return _line_key(_world_line(member), tolerances)
    geometry = _exact_source_geometry(result, item.source_handles)
    segment_keys = sorted(
        _line_key(segment, tolerances)
        for source in geometry
        for segment in _source_segments(source, tolerances)
    )
    # Unresolved ReviewItem keys are a presentation projection and may be
    # rebuilt with a different prefix after Pause/Resume.  Exact source
    # geometry is the durable discriminator at this boundary.
    return _canonical_json_hash({"segments": segment_keys})


def repair_subject_key(
    result: DXFImportResult,
    item: ReviewItem,
    tolerances: GeometryTolerances | None = None,
) -> CornerBraceRepairSubjectKey:
    """Create the exact source + base-geometry identity for one review row."""

    tolerances = tolerances or GeometryTolerances()
    if item.role != "corner_brace" or item.status not in {"recognized", "unresolved"}:
        raise DXFImportError("只有已辨識或待處理的角撐項目可進行修補。")
    handles = normalize_source_handles(item.source_handles)
    if not handles:
        raise DXFImportError("角撐修補需要明確的 DXF 來源控制碼。")
    target_kind = "recognized" if item.status == "recognized" else "unresolved"
    return CornerBraceRepairSubjectKey(
        source_fingerprint=result.source_fingerprint,
        source_handles=handles,
        target_kind=target_kind,
        base_geometry_key=_base_geometry_key(result, item, tolerances),
    )


def repair_subject_signature(
    result: DXFImportResult,
    item: ReviewItem,
    tolerances: GeometryTolerances | None = None,
) -> str:
    """Hash the current target evidence used to reject stale plans."""

    tolerances = tolerances or GeometryTolerances()
    key = repair_subject_key(result, item, tolerances)
    geometry = _exact_source_geometry(result, item.source_handles)
    payload = {
        "subject": {
            "source_fingerprint": key.source_fingerprint,
            "source_handles": key.source_handles,
            "target_kind": key.target_kind,
            "base_geometry_key": key.base_geometry_key,
        },
        "source_geometry": [
            {
                "handle": source.source_handle,
                "closed": source.closed,
                "segments": sorted(
                    _line_key(segment, tolerances)
                    for segment in _source_segments(source, tolerances)
                ),
            }
            for source in sorted(geometry, key=lambda value: value.source_handle)
        ],
    }
    return _canonical_json_hash(payload)


def target_residual_segments(
    result: DXFImportResult,
    subject_key: CornerBraceRepairSubjectKey,
    tolerances: GeometryTolerances | None = None,
) -> tuple[tuple[Point, Point], ...]:
    """Return deterministic residual segments from only the exact target source."""

    tolerances = tolerances or GeometryTolerances()
    values: dict[str, tuple[Point, Point]] = {}
    for geometry in _exact_source_geometry(result, subject_key.source_handles):
        for segment in _source_segments(geometry, tolerances):
            values[_line_key(segment, tolerances)] = segment
    return tuple(values[key] for key in sorted(values))


def _mid_axis(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
) -> tuple[Point, Point] | None:
    axis = _unit(*first)
    if axis is None:
        return None
    if _dot(axis, _vector(*second)) < 0:
        second = second[1], second[0]
    origin = first[0]
    normal = (-axis[1], axis[0])
    offsets = [_dot(_vector(origin, point), normal) for point in second]
    offset = sum(offsets) / len(offsets) / 2.0
    projections = [_dot(_vector(origin, point), axis) for point in (*first, *second)]
    start_projection, end_projection = min(projections), max(projections)
    start = (
        origin[0] + axis[0] * start_projection + normal[0] * offset,
        origin[1] + axis[1] * start_projection + normal[1] * offset,
    )
    end = (
        origin[0] + axis[0] * end_projection + normal[0] * offset,
        origin[1] + axis[1] * end_projection + normal[1] * offset,
    )
    return _ordered_line(start, end)


def residual_axis_hypotheses(
    residual_segments: Sequence[tuple[Point, Point]],
    tolerances: GeometryTolerances | None = None,
) -> tuple[tuple[Point, Point], ...]:
    """Build finite direction hypotheses without assuming a material width."""

    tolerances = tolerances or GeometryTolerances()
    hypotheses: dict[str, tuple[Point, Point]] = {
        _line_key(segment, tolerances): _ordered_line(*segment)
        for segment in residual_segments
    }
    for index, first in enumerate(residual_segments):
        for second in residual_segments[index + 1 :]:
            if _angle_difference_deg(first, second) > tolerances.parallel_angle_tolerance_deg:
                continue
            if _projection_overlap_ratio(first, second) < tolerances.minimum_projection_overlap_ratio:
                continue
            separation = abs(
                _cross(
                    _unit(*first) or (0.0, 0.0),
                    _vector(first[0], second[0]),
                )
            )
            if not (
                tolerances.collinear_tolerance_mm < separation
                <= tolerances.maximum_component_width_mm
            ):
                continue
            middle = _mid_axis(first, second)
            if middle is not None:
                hypotheses[_line_key(middle, tolerances)] = middle
    return tuple(hypotheses[key] for key in sorted(hypotheses))


def extract_target_repair_evidence(
    result: DXFImportResult,
    subject_key: CornerBraceRepairSubjectKey,
    tolerances: GeometryTolerances | None = None,
) -> TargetRepairEvidence:
    """Extract exact-source direction hypotheses and positional anchors.

    Closed outlines may provide a plate-like positional anchor but never an
    axis direction.  Open residual corridors provide their deterministic
    longest direction segments and midpoint anchors.  This deliberately does
    not inspect nearby members or layer-only evidence.
    """

    tolerances = tolerances or GeometryTolerances()
    directions: dict[str, tuple[Point, Point]] = {}
    anchors: dict[tuple[int, int, str], TargetRepairAnchor] = {}
    for geometry in sorted(
        _exact_source_geometry(result, subject_key.source_handles),
        key=lambda value: (
            str(value.source_handle).upper(),
            value.closed,
            tuple(value.points),
        ),
    ):
        segments = _source_segments(geometry, tolerances)
        handle = str(geometry.source_handle).strip().upper()
        if geometry.closed and len(geometry.points) >= 3:
            points = tuple(geometry.points)
            center = (
                sum(point[0] for point in points) / len(points),
                sum(point[1] for point in points) / len(points),
            )
            key = (*_quantized_point(center, tolerances), "plate")
            anchors[key] = TargetRepairAnchor(center, "plate", handle)
            continue
        if not segments:
            continue
        longest = max(_length(*segment) for segment in segments)
        reliable = tuple(
            segment
            for segment in segments
            if longest - _length(*segment) <= tolerances.endpoint_tolerance_mm
        )
        for hypothesis in residual_axis_hypotheses(reliable, tolerances):
            directions[_line_key(hypothesis, tolerances)] = hypothesis
        for segment in reliable:
            point = _midpoint(*segment)
            key = (*_quantized_point(point, tolerances), "corridor")
            anchors[key] = TargetRepairAnchor(point, "corridor", handle)
    diagnostics: list[str] = []
    if not directions:
        diagnostics.append("目標來源沒有可靠的方向證據。")
    if not anchors:
        diagnostics.append("目標來源沒有定位錨點證據。")
    return TargetRepairEvidence(
        direction_hypotheses=tuple(directions[key] for key in sorted(directions)),
        positional_anchors=tuple(anchors[key] for key in sorted(anchors)),
        diagnostics=tuple(diagnostics),
    )


def _relationship_frame(
    waler: Any,
    strut: Any,
    endpoint_name: str,
    tolerances: GeometryTolerances,
) -> TargetRelationshipFrame | None:
    waler_line = _world_line(waler)
    strut_line = _world_line(strut)
    origin = _segment_intersection_point(
        waler_line,
        strut_line,
        tolerances.endpoint_tolerance_mm,
    )
    if origin is None:
        return None
    inward = (
        _unit(*strut_line)
        if endpoint_name == "from"
        else _unit(strut_line[1], strut_line[0])
    )
    waler_axis = _unit(*waler_line)
    if inward is None or waler_axis is None:
        return None
    return TargetRelationshipFrame(
        waler_id=waler.id,
        strut_id=strut.id,
        endpoint_name=endpoint_name,
        origin=origin,
        inward=inward,
        waler_axis=waler_axis,
        waler_line=waler_line,
        strut_line=strut_line,
    )


def extract_corner_brace_local_template(
    result: DXFImportResult,
    evidence: CornerBraceReferenceEvidence,
    tolerances: GeometryTolerances | None = None,
) -> CornerBraceLocalTemplate | None:
    """Convert one valid automatic primary connection into local values."""

    tolerances = tolerances or GeometryTolerances()
    connection = evidence.connection
    waler = next((value for value in result.walers if value.id == connection.waler_id), None)
    strut = next((value for value in result.struts if value.id == connection.strut_id), None)
    if waler is None or strut is None:
        return None
    frame = _relationship_frame(
        waler,
        strut,
        connection.strut_endpoint_name,
        tolerances,
    )
    if frame is None:
        return None
    if (
        _segment_distance(connection.baseline_waler_attachment, *frame.waler_line)
        > tolerances.endpoint_tolerance_mm
        or _segment_distance(connection.baseline_strut_attachment, *frame.strut_line)
        > tolerances.endpoint_tolerance_mm
    ):
        return None
    waler_vector = _vector(frame.origin, connection.baseline_waler_attachment)
    strut_vector = _vector(frame.origin, connection.baseline_strut_attachment)
    offset = abs(_dot(waler_vector, frame.waler_axis))
    station = _dot(strut_vector, frame.inward)
    side_value = _cross(frame.inward, waler_vector)
    side = 0 if abs(side_value) <= 1e-9 else (1 if side_value > 0 else -1)
    values = (offset, station, connection.fixed_length_mm)
    if (
        side == 0
        or not all(math.isfinite(value) for value in values)
        or offset < 0.0
        or station < -tolerances.endpoint_tolerance_mm
        or connection.fixed_length_mm <= 0.0
    ):
        return None
    return CornerBraceLocalTemplate(
        reference=evidence.reference,
        topology=evidence.topology,
        side=side,
        waler_offset_mm=offset,
        strut_station_mm=max(0.0, station),
        fixed_length_mm=connection.fixed_length_mm,
        relationship_waler_id=connection.waler_id,
        relationship_strut_id=connection.strut_id,
    )


def transfer_corner_brace_template(
    frame: TargetRelationshipFrame,
    template: CornerBraceLocalTemplate,
    transfer_mode: str,
    tolerances: GeometryTolerances | None = None,
) -> tuple[Point, Point] | None:
    """Map local offset/station into a finite target frame without snapping."""

    tolerances = tolerances or GeometryTolerances()
    if transfer_mode not in {"same_side", "mirrored"}:
        return None
    desired_side = template.side if transfer_mode == "same_side" else -template.side
    choices = (
        (
            frame.origin[0] + frame.waler_axis[0] * template.waler_offset_mm,
            frame.origin[1] + frame.waler_axis[1] * template.waler_offset_mm,
        ),
        (
            frame.origin[0] - frame.waler_axis[0] * template.waler_offset_mm,
            frame.origin[1] - frame.waler_axis[1] * template.waler_offset_mm,
        ),
    )
    waler_point = next(
        (
            point
            for point in choices
            if (1 if _cross(frame.inward, _vector(frame.origin, point)) > 0 else -1)
            == desired_side
        ),
        None,
    )
    strut_point = (
        frame.origin[0] + frame.inward[0] * template.strut_station_mm,
        frame.origin[1] + frame.inward[1] * template.strut_station_mm,
    )
    if waler_point is None:
        return None
    if (
        _segment_distance(waler_point, *frame.waler_line) > tolerances.endpoint_tolerance_mm
        or _segment_distance(strut_point, *frame.strut_line) > tolerances.endpoint_tolerance_mm
    ):
        return None
    return waler_point, strut_point


def _validate_target_evidence(
    line: tuple[Point, Point],
    evidence: TargetRepairEvidence,
    tolerances: GeometryTolerances,
) -> tuple[tuple[Point, Point], TargetRepairAnchor] | None:
    directions = tuple(
        value
        for value in evidence.direction_hypotheses
        if _angle_difference_deg(line, value) <= tolerances.parallel_angle_tolerance_deg
    )
    anchors = tuple(
        value
        for value in evidence.positional_anchors
        if _segment_distance(value.point, *line) <= tolerances.connection_tolerance_mm
    )
    if not directions or not anchors:
        return None
    return (
        min(directions, key=lambda value: _line_key(value, tolerances)),
        min(
            anchors,
            key=lambda value: (
                _segment_distance(value.point, *line),
                _quantized_point(value.point, tolerances),
                value.kind,
            ),
        ),
    )


def _connection_by_corner(
    result: DXFImportResult,
) -> dict[str, CornerBraceConnection]:
    grouped: dict[str, list[CornerBraceConnection]] = {}
    for connection in result.corner_brace_connections:
        grouped.setdefault(connection.corner_brace_id, []).append(connection)
    return {
        member_id: values[0]
        for member_id, values in grouped.items()
        if len(values) == 1
    }


def _connection_side(
    result: DXFImportResult,
    connection: CornerBraceConnection,
) -> int:
    strut = next((item for item in result.struts if item.id == connection.strut_id), None)
    if strut is None:
        return 0
    strut_start, strut_end = _world_line(strut)
    if connection.strut_endpoint_name == "from":
        inward = _unit(strut_start, strut_end)
    else:
        inward = _unit(strut_end, strut_start)
    brace = _unit(connection.baseline_strut_attachment, connection.baseline_waler_attachment)
    if inward is None or brace is None:
        return 0
    value = _cross(inward, brace)
    if abs(value) <= 1e-9:
        return 0
    return 1 if value > 0 else -1


def eligible_repair_references(
    result: DXFImportResult,
    review_items: Sequence[ReviewItem],
    confirmations: Mapping[str, str] | None,
    *,
    confirmation_result: DXFImportResult | None = None,
    requires_review_subjects: Sequence[str] = (),
    excluded_member_id: str = "",
    tolerances: GeometryTolerances | None = None,
) -> tuple[tuple[CornerBraceReferenceEvidence, ...], tuple[CornerBraceReferenceEvidence, ...]]:
    """Classify current references; repaired members can never become primary."""

    tolerances = tolerances or GeometryTolerances()
    excluded_identities = {source.identity for source in result.excluded_sources}
    requires_review = {str(value) for value in requires_review_subjects}
    connections = _connection_by_corner(result)
    review_by_member = {
        item.member_id: item
        for item in review_items
        if item.member_id and item.role == "corner_brace" and item.status == "recognized"
    }
    primary: list[CornerBraceReferenceEvidence] = []
    secondary: list[CornerBraceReferenceEvidence] = []
    for corner in result.corner_braces:
        if corner.id == excluded_member_id:
            continue
        connection = connections.get(corner.id)
        if connection is None:
            continue
        source_identity = canonical_source_identity("corner_brace", corner.source_handles)
        if source_identity in excluded_identities:
            continue
        side = _connection_side(result, connection)
        if side == 0:
            continue
        if corner.repair_provenance is None:
            if corner.selection_source not in {"auto", "recognized", "geometry"}:
                continue
            key = CornerBraceRepairSubjectKey(
                source_fingerprint=result.source_fingerprint,
                source_handles=corner.source_handles,
                target_kind="recognized",
                base_geometry_key=_line_key(_world_line(corner), tolerances),
            )
            reference_class = PRIMARY_REFERENCE
        else:
            provenance = corner.repair_provenance
            item = review_by_member.get(corner.id)
            stable_key = _subject_token(provenance.subject_key)
            if (
                corner.selection_source != REPAIR_SELECTION_SOURCE
                or item is None
                or stable_key in requires_review
                or not provenance.automatic_primary_references
                or not review_item_is_confirmed(
                    confirmation_result or result,
                    item,
                    confirmations,
                )
            ):
                continue
            key = provenance.subject_key
            reference_class = SECONDARY_REFERENCE
        evidence = CornerBraceReferenceEvidence(
            reference=CornerBraceRepairReference(key, corner.id, reference_class),
            connection=connection,
            world_start=_world_line(corner)[0],
            world_end=_world_line(corner)[1],
            side=side,
            topology=connection.strut_endpoint_name,
        )
        (primary if reference_class == PRIMARY_REFERENCE else secondary).append(evidence)
    sort_key = lambda item: (_subject_token(item.reference.subject_key), item.reference.member_id)
    return tuple(sorted(primary, key=sort_key)), tuple(sorted(secondary, key=sort_key))


def _subject_token(key: CornerBraceRepairSubjectKey) -> str:
    return _canonical_json_hash(
        {
            "fingerprint": key.source_fingerprint,
            "handles": key.source_handles,
            "kind": key.target_kind,
            "geometry": key.base_geometry_key,
        }
    )


def _candidate_id(
    start: Point,
    end: Point,
    waler_id: str,
    strut_id: str,
    template_reference: CornerBraceRepairReference,
    transfer_mode: str,
    waler_offset_mm: float,
    strut_station_mm: float,
    tolerances: GeometryTolerances,
) -> str:
    digest = _canonical_json_hash(
        {
            "line": _line_key((start, end), tolerances),
            "waler": waler_id,
            "strut": strut_id,
            "template": _subject_token(template_reference.subject_key),
            "mode": transfer_mode,
            "offset": round(waler_offset_mm, 6),
            "station": round(strut_station_mm, 6),
        }
    )
    return f"CBR-{digest[:12]}"


def _temporary_corner(
    result: DXFImportResult,
    item: ReviewItem,
    candidate: CornerBraceRepairCandidate,
    member_id: str,
) -> CornerBrace:
    existing = next(
        (corner for corner in result.corner_braces if corner.id == item.member_id),
        None,
    )
    if existing is not None:
        return replace(
            existing,
            start=candidate.world_start,
            end=candidate.world_end,
            world_start=candidate.world_start,
            world_end=candidate.world_end,
            local_start=candidate.world_start,
            local_end=candidate.world_end,
        )
    geometry = _exact_source_geometry(result, item.source_handles)
    return CornerBrace(
        id=member_id,
        start=candidate.world_start,
        end=candidate.world_end,
        source_layer=next((source.source_layer for source in geometry if source.source_layer), ""),
        source_handles=normalize_source_handles(item.source_handles),
        source_entity_types=tuple(
            sorted({source.source_entity_type for source in geometry if source.source_entity_type})
        ),
        recognition_method=REPAIR_RECOGNITION_METHOD,
        centerline_computed=True,
        source_width=0.0,
        confidence=1.0,
        world_start=candidate.world_start,
        world_end=candidate.world_end,
        local_start=candidate.world_start,
        local_end=candidate.world_end,
        selection_source=REPAIR_SELECTION_SOURCE,
    )


def _candidate_passes_existing_validation(
    result: DXFImportResult,
    item: ReviewItem,
    candidate: CornerBraceRepairCandidate,
    tolerances: GeometryTolerances,
) -> bool:
    member_id = item.member_id or "__CORNER_BRACE_REPAIR_PREVIEW__"
    temporary = _temporary_corner(result, item, candidate, member_id)
    corners = tuple(
        temporary if corner.id == item.member_id else corner
        for corner in result.corner_braces
    )
    if item.member_id is None:
        corners = (*corners, temporary)
    staged = replace(result, corner_braces=corners)
    connections, messages = build_corner_brace_connections(staged, tolerances)
    matching = [connection for connection in connections if connection.corner_brace_id == member_id]
    if len(matching) != 1:
        return False
    connection = matching[0]
    if connection.waler_id != candidate.target_waler_id or connection.strut_id != candidate.target_strut_id:
        return False
    if any(member_id in message.member_ids for message in messages):
        return False
    duplicate_messages = validate_duplicate_engineering_members((corners,), tolerances)
    return not any(member_id in message.member_ids for message in duplicate_messages)


def plan_corner_brace_repair(
    result: DXFImportResult,
    item: ReviewItem,
    *,
    base_revision: int,
    review_items: Sequence[ReviewItem] = (),
    confirmations: Mapping[str, str] | None = None,
    confirmation_result: DXFImportResult | None = None,
    requires_review_subjects: Sequence[str] = (),
    tolerances: GeometryTolerances | None = None,
) -> CornerBraceRepairPlan:
    """Plan compatible automatic-primary local-template transfers."""

    tolerances = tolerances or GeometryTolerances()
    subject_key = repair_subject_key(result, item, tolerances)
    signature = repair_subject_signature(result, item, tolerances)
    residuals = target_residual_segments(result, subject_key, tolerances)
    matching_bodies = tuple(
        body
        for body in result.corner_brace_body_evidence
        if normalize_source_handles(body.source_handles)
        == subject_key.source_handles
    )
    if subject_key.target_kind == "unresolved" and len(matching_bodies) == 1:
        body = matching_bodies[0]
        assessments = tuple(
            assessment
            for assessment in result.corner_brace_relationship_assessments
            if assessment.body_signature == body.signature
            and assessment.hard_valid
        )
        walers_by_identity: dict[tuple[str, ...], list[Any]] = {}
        struts_by_identity: dict[tuple[str, ...], list[Any]] = {}
        for waler in result.walers:
            walers_by_identity.setdefault(
                normalize_source_handles(waler.source_handles), []
            ).append(waler)
        for strut in result.struts:
            struts_by_identity.setdefault(
                normalize_source_handles(strut.source_handles), []
            ).append(strut)
        relationship_candidates: list[CornerBraceRepairCandidate] = []
        rejected_relationships = 0
        for assessment in assessments:
            walers = walers_by_identity.get(
                normalize_source_handles(assessment.waler_source_handles), []
            )
            struts = struts_by_identity.get(
                normalize_source_handles(assessment.strut_source_handles), []
            )
            if len(walers) != 1 or len(struts) != 1:
                rejected_relationships += 1
                continue
            waler, strut = walers[0], struts[0]
            waler_point, strut_point = assessment.finite_intersections
            strut_line = _world_line(strut)
            endpoint_name = (
                "from"
                if _distance(strut_point, strut_line[0])
                <= _distance(strut_point, strut_line[1])
                else "to"
            )
            candidate_id = _canonical_json_hash(
                {
                    "mode": "body_relationship_selection",
                    "body": body.signature,
                    "waler": assessment.waler_source_handles,
                    "strut": assessment.strut_source_handles,
                    "points": assessment.finite_intersections,
                }
            )
            relationship_candidates.append(
                CornerBraceRepairCandidate(
                    id=candidate_id,
                    world_start=waler_point,
                    world_end=strut_point,
                    target_waler_id=waler.id,
                    target_strut_id=strut.id,
                    target_strut_endpoint_name=endpoint_name,
                    template_reference=None,
                    transfer_mode="body_relationship_selection",
                    reference_waler_offset_mm=(
                        assessment.per_end_extensions_mm[0]
                    ),
                    reference_strut_station_mm=(
                        assessment.per_end_extensions_mm[1]
                    ),
                    reference_fixed_length_mm=assessment.expected_span_mm,
                    target_evidence=TargetRepairEvidence(
                        direction_hypotheses=(body.midline,),
                        positional_anchors=(),
                        diagnostics=(),
                    ),
                    matched_direction=body.midline,
                    positional_anchor=_midpoint(waler_point, strut_point),
                    primary_references=(),
                    residual_axis=body.midline,
                    diagnostics=(
                        f"本體：{body.signature}",
                        f"關係：{waler.id} / {strut.id}",
                        "兩軌覆蓋率："
                        f"{assessment.per_rail_union_coverage[0]:.3f} / "
                        f"{assessment.per_rail_union_coverage[1]:.3f}",
                        "兩端延伸："
                        f"{assessment.per_end_extensions_mm[0]:.3f} / "
                        f"{assessment.per_end_extensions_mm[1]:.3f} mm",
                    ),
                    selection_mode="body_relationship_selection",
                    body_signature=body.signature,
                    relationship_assessment=assessment,
                )
            )
        if relationship_candidates:
            relationship_candidates.sort(
                key=lambda candidate: (
                    normalize_source_handles(
                        candidate.relationship_assessment.waler_source_handles
                    ),
                    normalize_source_handles(
                        candidate.relationship_assessment.strut_source_handles
                    ),
                    candidate.id,
                )
            )
            diagnostics = [
                "角撐本體唯一；請明確選擇一組合法 Waler／Strut 關係。"
            ]
            if rejected_relationships:
                diagnostics.append(
                    f"因 active identity 不唯一而拒絕：{rejected_relationships} 組。"
                )
            return CornerBraceRepairPlan(
                base_revision=base_revision,
                subject_key=subject_key,
                subject_signature=signature,
                target_kind=subject_key.target_kind,
                target_member_id=item.member_id or "",
                preferred_display_id=item.member_id or "",
                residual_segments=residuals,
                candidates=tuple(relationship_candidates),
                diagnostics=tuple(diagnostics),
                selection_mode="body_relationship_selection",
            )
    target_evidence = extract_target_repair_evidence(result, subject_key, tolerances)
    diagnostics: list[str] = list(target_evidence.diagnostics)
    primary, secondary = eligible_repair_references(
        result,
        review_items,
        confirmations,
        confirmation_result=confirmation_result,
        requires_review_subjects=requires_review_subjects,
        excluded_member_id=item.member_id or "",
        tolerances=tolerances,
    )
    if not primary:
        diagnostics.append("沒有符合條件的自動辨識角撐可作為主要參考。")

    templates: list[tuple[CornerBraceReferenceEvidence, CornerBraceLocalTemplate]] = []
    for evidence in primary:
        template = extract_corner_brace_local_template(result, evidence, tolerances)
        if template is not None:
            templates.append((evidence, template))
    if primary and not templates:
        diagnostics.append("沒有任何自動主要參考可建立有效的有限局部模板。")

    waler_by_id = {waler.id: waler for waler in result.walers}
    reference_members = {corner.id: corner for corner in result.corner_braces}
    options_by_relationship: dict[
        tuple[str, str],
        list[tuple[int, float, CornerBraceRepairCandidate]],
    ] = {}
    rejected_count = 0
    if target_evidence.direction_hypotheses and target_evidence.positional_anchors and templates:
        for strut in result.struts:
            for endpoint_name, waler_id in (("from", strut.from_waler), ("to", strut.to_waler)):
                waler = waler_by_id.get(waler_id)
                if waler is None:
                    continue
                frame = _relationship_frame(waler, strut, endpoint_name, tolerances)
                if frame is None:
                    continue
                target_angle = _angle_difference_deg(frame.waler_line, frame.strut_line)
                for reference_evidence, template in templates:
                    if template.topology != endpoint_name:
                        rejected_count += 1
                        continue
                    reference_waler = waler_by_id.get(template.relationship_waler_id)
                    reference_strut = next(
                        (value for value in result.struts if value.id == template.relationship_strut_id),
                        None,
                    )
                    reference_member = reference_members.get(template.reference.member_id)
                    if reference_waler is None or reference_strut is None or reference_member is None:
                        rejected_count += 1
                        continue
                    reference_angle = _angle_difference_deg(
                        _world_line(reference_waler),
                        _world_line(reference_strut),
                    )
                    if abs(reference_angle - target_angle) > tolerances.parallel_angle_tolerance_deg:
                        rejected_count += 1
                        continue
                    for transfer_mode in ("same_side", "mirrored"):
                        transferred = transfer_corner_brace_template(
                            frame,
                            template,
                            transfer_mode,
                            tolerances,
                        )
                        if transferred is None:
                            rejected_count += 1
                            continue
                        world_start, world_end = transferred
                        if _distance(world_start, world_end) < tolerances.minimum_component_length_mm:
                            rejected_count += 1
                            continue
                        validation = _validate_target_evidence(
                            transferred,
                            target_evidence,
                            tolerances,
                        )
                        if validation is None:
                            rejected_count += 1
                            continue
                        matched_direction, anchor = validation
                        matching_secondary = tuple(
                            evidence.reference
                            for evidence in secondary
                            if evidence.topology == endpoint_name
                        )
                        same_relationship = (
                            template.relationship_waler_id == waler.id
                            and template.relationship_strut_id == strut.id
                        )
                        if same_relationship and transfer_mode == "mirrored":
                            tier = 0
                        elif template.relationship_strut_id != strut.id:
                            tier = 1
                        else:
                            tier = 2
                        proximity = _distance(
                            anchor.point,
                            _midpoint(*_world_line(reference_member)),
                        )
                        candidate = CornerBraceRepairCandidate(
                            id=_candidate_id(
                                world_start,
                                world_end,
                                waler.id,
                                strut.id,
                                template.reference,
                                transfer_mode,
                                template.waler_offset_mm,
                                template.strut_station_mm,
                                tolerances,
                            ),
                            world_start=world_start,
                            world_end=world_end,
                            target_waler_id=waler.id,
                            target_strut_id=strut.id,
                            target_strut_endpoint_name=endpoint_name,
                            template_reference=template.reference,
                            transfer_mode=transfer_mode,
                            reference_waler_offset_mm=template.waler_offset_mm,
                            reference_strut_station_mm=template.strut_station_mm,
                            reference_fixed_length_mm=template.fixed_length_mm,
                            target_evidence=target_evidence,
                            matched_direction=matched_direction,
                            positional_anchor=anchor.point,
                            primary_references=(template.reference,),
                            secondary_references=matching_secondary,
                            residual_axis=matched_direction,
                            proximity_mm=proximity,
                            diagnostics=(
                                f"局部模板移植：{waler.id} / {strut.id}",
                                f"選用模板：{template.reference.member_id}",
                                "移植方式已通過檢核",
                                "目標方向與定位錨點均有效",
                                "參考固定長度僅供稽核與診斷",
                            ),
                        )
                        if not _candidate_passes_existing_validation(result, item, candidate, tolerances):
                            rejected_count += 1
                            continue
                        options_by_relationship.setdefault((waler.id, strut.id), []).append(
                            (tier, proximity, candidate)
                        )

    selected: list[tuple[int, float, CornerBraceRepairCandidate]] = []
    for relationship in sorted(options_by_relationship):
        options = options_by_relationship[relationship]
        best_tier = min(value[0] for value in options)
        tier_options = [value for value in options if value[0] == best_tier]
        nearest = min(value[1] for value in tier_options)
        ambiguous = [
            value
            for value in tier_options
            if value[1] - nearest <= tolerances.ambiguous_connection_delta_mm
        ]
        equivalent: dict[str, list[tuple[int, float, CornerBraceRepairCandidate]]] = {}
        for value in ambiguous:
            key = _line_key((value[2].world_start, value[2].world_end), tolerances)
            equivalent.setdefault(key, []).append(value)
        for key in sorted(equivalent):
            values = sorted(
                equivalent[key],
                key=lambda value: (
                    value[1],
                    _subject_token(value[2].template_reference.subject_key),
                    value[2].transfer_mode,
                    value[2].id,
                ),
            )
            chosen = values[0]
            supporting = tuple(
                sorted(
                    {value[2].template_reference for value in values},
                    key=lambda reference: (
                        _subject_token(reference.subject_key),
                        reference.member_id,
                    ),
                )
            )
            selected.append((chosen[0], chosen[1], replace(chosen[2], primary_references=supporting)))

    candidates = tuple(
        value[2]
        for value in sorted(
            selected,
            key=lambda value: (
                value[0],
                value[1],
                value[2].target_waler_id,
                value[2].target_strut_id,
                _subject_token(value[2].template_reference.subject_key),
                value[2].id,
            ),
        )
    )
    if subject_key.target_kind == "unresolved" and candidates:
        relationships = {
            (candidate.target_waler_id, candidate.target_strut_id)
            for candidate in candidates
        }
        if len(relationships) != 1:
            rejected_count += len(candidates)
            candidates = ()
            diagnostics.append(
                "待處理來源存在多組仍有效的圍令／支撐關係。"
            )
    if rejected_count:
        diagnostics.append(f"已拒絕假設：{rejected_count} 個。")
    if not candidates and not diagnostics:
        diagnostics.append("沒有任何假設通過全部角撐修補資格檢核。")
    return CornerBraceRepairPlan(
        base_revision=base_revision,
        subject_key=subject_key,
        subject_signature=signature,
        target_kind=subject_key.target_kind,
        target_member_id=item.member_id or "",
        preferred_display_id=item.member_id or "",
        residual_segments=residuals,
        candidates=candidates,
        diagnostics=tuple(diagnostics),
    )


def reconstruct_saved_template_candidate(
    result: DXFImportResult,
    item: ReviewItem,
    provenance: CornerBraceRepairProvenance,
    *,
    review_items: Sequence[ReviewItem] = (),
    confirmations: Mapping[str, str] | None = None,
    confirmation_result: DXFImportResult | None = None,
    requires_review_subjects: Sequence[str] = (),
    tolerances: GeometryTolerances | None = None,
) -> CornerBraceRepairCandidate | None:
    """Rebuild a new-format replay candidate from its saved template truth.

    Ranking is intentionally not consulted: replay must never substitute a
    currently nearer reference for the explicitly adopted template.
    """

    tolerances = tolerances or GeometryTolerances()
    selected = provenance.selected_template_reference
    if (
        selected is None
        or provenance.transfer_mode not in {"same_side", "mirrored"}
        or provenance.reference_waler_offset_mm is None
        or provenance.reference_strut_station_mm is None
    ):
        return None
    primary, secondary = eligible_repair_references(
        result,
        review_items,
        confirmations,
        confirmation_result=confirmation_result,
        requires_review_subjects=requires_review_subjects,
        excluded_member_id=item.member_id or "",
        tolerances=tolerances,
    )
    primary_by_reference = {evidence.reference: evidence for evidence in primary}
    selected_evidence = primary_by_reference.get(selected)
    if selected_evidence is None:
        return None
    if any(reference not in primary_by_reference for reference in provenance.automatic_primary_references):
        return None
    extracted = extract_corner_brace_local_template(result, selected_evidence, tolerances)
    if extracted is None:
        return None
    if (
        abs(extracted.waler_offset_mm - provenance.reference_waler_offset_mm)
        > tolerances.endpoint_tolerance_mm
        or abs(extracted.strut_station_mm - provenance.reference_strut_station_mm)
        > tolerances.endpoint_tolerance_mm
    ):
        return None
    target_walers = tuple(
        value
        for value in result.walers
        if canonical_source_identity("waler", value.source_handles)
        == provenance.target_waler_identity
    )
    target_struts = tuple(
        value
        for value in result.struts
        if canonical_source_identity("strut", value.source_handles)
        == provenance.target_strut_identity
    )
    if len(target_walers) != 1 or len(target_struts) != 1:
        return None
    waler, strut = target_walers[0], target_struts[0]
    endpoint_names = tuple(
        name
        for name, waler_id in (("from", strut.from_waler), ("to", strut.to_waler))
        if waler_id == waler.id
    )
    if len(endpoint_names) != 1 or extracted.topology != endpoint_names[0]:
        return None
    frame = _relationship_frame(waler, strut, endpoint_names[0], tolerances)
    if frame is None:
        return None
    reference_waler = next(
        (value for value in result.walers if value.id == extracted.relationship_waler_id),
        None,
    )
    reference_strut = next(
        (value for value in result.struts if value.id == extracted.relationship_strut_id),
        None,
    )
    if reference_waler is None or reference_strut is None:
        return None
    if abs(
        _angle_difference_deg(_world_line(reference_waler), _world_line(reference_strut))
        - _angle_difference_deg(frame.waler_line, frame.strut_line)
    ) > tolerances.parallel_angle_tolerance_deg:
        return None
    saved_template = replace(
        extracted,
        waler_offset_mm=provenance.reference_waler_offset_mm,
        strut_station_mm=provenance.reference_strut_station_mm,
    )
    transferred = transfer_corner_brace_template(
        frame,
        saved_template,
        provenance.transfer_mode,
        tolerances,
    )
    if transferred is None:
        return None
    target_evidence = extract_target_repair_evidence(
        result,
        provenance.subject_key,
        tolerances,
    )
    validation = _validate_target_evidence(transferred, target_evidence, tolerances)
    if validation is None:
        return None
    matched_direction, anchor = validation
    current_secondary = {evidence.reference for evidence in secondary}
    if any(reference not in current_secondary for reference in provenance.manual_secondary_references):
        return None
    candidate = CornerBraceRepairCandidate(
        id=_candidate_id(
            transferred[0],
            transferred[1],
            waler.id,
            strut.id,
            selected,
            provenance.transfer_mode,
            provenance.reference_waler_offset_mm,
            provenance.reference_strut_station_mm,
            tolerances,
        ),
        world_start=transferred[0],
        world_end=transferred[1],
        target_waler_id=waler.id,
        target_strut_id=strut.id,
        target_strut_endpoint_name=endpoint_names[0],
        template_reference=selected,
        transfer_mode=provenance.transfer_mode,
        reference_waler_offset_mm=provenance.reference_waler_offset_mm,
        reference_strut_station_mm=provenance.reference_strut_station_mm,
        reference_fixed_length_mm=extracted.fixed_length_mm,
        target_evidence=target_evidence,
        matched_direction=matched_direction,
        positional_anchor=anchor.point,
        primary_references=provenance.automatic_primary_references,
        secondary_references=provenance.manual_secondary_references,
        residual_axis=matched_direction,
        proximity_mm=0.0,
        diagnostics=(
            "已依保存的選用模板重建",
            f"選用模板：{selected.member_id}",
            "移植方式已依保存資料重建",
        ),
    )
    return (
        candidate
        if _candidate_passes_existing_validation(result, item, candidate, tolerances)
        else None
    )


def reconstruct_legacy_adopted_candidate(
    result: DXFImportResult,
    item: ReviewItem,
    provenance: CornerBraceRepairProvenance,
    *,
    review_items: Sequence[ReviewItem] = (),
    confirmations: Mapping[str, str] | None = None,
    confirmation_result: DXFImportResult | None = None,
    tolerances: GeometryTolerances | None = None,
) -> CornerBraceRepairCandidate | None:
    """Validate a legacy version-2 adopted line without template ranking."""

    tolerances = tolerances or GeometryTolerances()
    if provenance.selected_template_reference is not None:
        return None
    primary, secondary = eligible_repair_references(
        result,
        review_items,
        confirmations,
        confirmation_result=confirmation_result,
        excluded_member_id=item.member_id or "",
        tolerances=tolerances,
    )
    primary_by_reference = {evidence.reference: evidence for evidence in primary}
    secondary_references = {evidence.reference for evidence in secondary}
    if (
        not provenance.automatic_primary_references
        or any(
            reference not in primary_by_reference
            for reference in provenance.automatic_primary_references
        )
        or any(
            reference not in secondary_references
            for reference in provenance.manual_secondary_references
        )
    ):
        return None
    walers = tuple(
        value
        for value in result.walers
        if canonical_source_identity("waler", value.source_handles)
        == provenance.target_waler_identity
    )
    struts = tuple(
        value
        for value in result.struts
        if canonical_source_identity("strut", value.source_handles)
        == provenance.target_strut_identity
    )
    if len(walers) != 1 or len(struts) != 1:
        return None
    waler, strut = walers[0], struts[0]
    endpoint_names = tuple(
        name
        for name, waler_id in (("from", strut.from_waler), ("to", strut.to_waler))
        if waler_id == waler.id
    )
    if len(endpoint_names) != 1:
        return None
    endpoints = None
    for waler_point, strut_point in (
        (provenance.adopted_world_start, provenance.adopted_world_end),
        (provenance.adopted_world_end, provenance.adopted_world_start),
    ):
        if (
            _segment_distance(waler_point, *_world_line(waler))
            <= tolerances.endpoint_tolerance_mm
            and _segment_distance(strut_point, *_world_line(strut))
            <= tolerances.endpoint_tolerance_mm
        ):
            endpoints = (waler_point, strut_point)
            break
    if endpoints is None:
        return None
    evidence = extract_target_repair_evidence(result, provenance.subject_key, tolerances)
    validation = _validate_target_evidence(endpoints, evidence, tolerances)
    if validation is None:
        return None
    matched_direction, anchor = validation
    selected = provenance.automatic_primary_references[0]
    selected_evidence = primary_by_reference[selected]
    candidate = CornerBraceRepairCandidate(
        id=_candidate_id(
            endpoints[0],
            endpoints[1],
            waler.id,
            strut.id,
            selected,
            "legacy_adopted",
            0.0,
            0.0,
            tolerances,
        ),
        world_start=endpoints[0],
        world_end=endpoints[1],
        target_waler_id=waler.id,
        target_strut_id=strut.id,
        target_strut_endpoint_name=endpoint_names[0],
        template_reference=selected,
        transfer_mode="legacy_adopted",
        reference_waler_offset_mm=0.0,
        reference_strut_station_mm=0.0,
        reference_fixed_length_mm=selected_evidence.connection.fixed_length_mm,
        target_evidence=evidence,
        matched_direction=matched_direction,
        positional_anchor=anchor.point,
        primary_references=provenance.automatic_primary_references,
        secondary_references=provenance.manual_secondary_references,
        residual_axis=matched_direction,
        proximity_mm=0.0,
        diagnostics=("舊版已採用世界座標線檢核",),
    )
    return (
        candidate
        if _candidate_passes_existing_validation(result, item, candidate, tolerances)
        else None
    )


def _next_corner_brace_id(result: DXFImportResult, preferred: str = "") -> str:
    used = {corner.id for corner in result.corner_braces}
    if preferred and preferred not in used:
        return preferred
    numbers = [
        int(match.group(1))
        for value in used
        if (match := re.fullmatch(r"CB(\d+)", value, re.IGNORECASE))
    ]
    candidate = max(numbers, default=0) + 1
    while f"CB{candidate}" in used:
        candidate += 1
    return f"CB{candidate}"


def _identity_for_member(role: str, member: Any) -> str:
    return canonical_source_identity(role, member.source_handles)


def _selected_relationship_connection(
    member_id: str,
    candidate: CornerBraceRepairCandidate,
    waler: Any,
    strut: Any,
) -> CornerBraceConnection:
    """Build the exact connection explicitly selected in Preview."""

    waler_line = _world_line(waler)
    strut_line = _world_line(strut)
    corner_line = (candidate.world_start, candidate.world_end)
    if _segment_distance(corner_line[0], *waler_line) <= _segment_distance(
        corner_line[1], *waler_line
    ):
        corner_waler_endpoint_name = "start"
        waler_attachment, strut_attachment = corner_line
    else:
        corner_waler_endpoint_name = "end"
        strut_attachment, waler_attachment = corner_line
    endpoint_name = candidate.target_strut_endpoint_name
    strut_base = strut_line[0] if endpoint_name == "from" else strut_line[1]
    inward = (
        _unit(strut_line[0], strut_line[1])
        if endpoint_name == "from"
        else _unit(strut_line[1], strut_line[0])
    )
    waler_axis = _unit(*waler_line)
    if inward is None or waler_axis is None:
        raise DXFImportError("所選角撐關係包含零長度構件。")
    strut_length = _length(*strut_line)
    hole_station = _dot(_vector(strut_base, strut_attachment), inward)
    if hole_station < -1e-6 or hole_station > strut_length + 1e-6:
        raise DXFImportError("所選角撐關係的支撐交點已超出有限線段。")
    return CornerBraceConnection(
        corner_brace_id=member_id,
        waler_id=waler.id,
        strut_id=strut.id,
        strut_endpoint_name=endpoint_name,
        corner_waler_endpoint_name=corner_waler_endpoint_name,
        baseline_waler_attachment=waler_attachment,
        baseline_strut_attachment=strut_attachment,
        strut_hole_station_mm=max(0.0, min(strut_length, hole_station)),
        fixed_length_mm=_distance(waler_attachment, strut_attachment),
        baseline_waler_station_mm=_dot(
            _vector(waler_line[0], waler_attachment), waler_axis
        ),
    )


def apply_corner_brace_repair(
    result: DXFImportResult,
    item: ReviewItem,
    plan: CornerBraceRepairPlan,
    candidate_id: str,
    *,
    explicit_adoption: bool,
    tolerances: GeometryTolerances | None = None,
) -> tuple[DXFImportResult, str]:
    """Apply one already revalidated candidate to a new immutable result."""

    tolerances = tolerances or GeometryTolerances()
    if not explicit_adoption:
        raise DXFImportError("角撐修補需要使用者明確採用。")
    candidate = next((value for value in plan.candidates if value.id == candidate_id), None)
    if candidate is None:
        raise DXFImportError("所選角撐修補候選不符合資格。")
    waler = next((value for value in result.walers if value.id == candidate.target_waler_id), None)
    strut = next((value for value in result.struts if value.id == candidate.target_strut_id), None)
    if waler is None or strut is None:
        raise DXFImportError("修補目標的圍令／支撐關係已不存在。")
    member_id = plan.target_member_id
    if plan.target_kind == "recognized":
        existing = next((value for value in result.corner_braces if value.id == member_id), None)
        if existing is None:
            raise DXFImportError("已辨識的角撐修補目標已不存在。")
    else:
        existing = None
        member_id = _next_corner_brace_id(result, plan.preferred_display_id)
    provenance = CornerBraceRepairProvenance(
        subject_key=plan.subject_key,
        adopted_world_start=candidate.world_start,
        adopted_world_end=candidate.world_end,
        target_waler_identity=_identity_for_member("waler", waler),
        target_strut_identity=_identity_for_member("strut", strut),
        automatic_primary_references=candidate.primary_references,
        manual_secondary_references=candidate.secondary_references,
        selected_template_reference=candidate.template_reference,
        transfer_mode=candidate.transfer_mode,
        reference_waler_offset_mm=candidate.reference_waler_offset_mm,
        reference_strut_station_mm=candidate.reference_strut_station_mm,
        preferred_display_id=member_id,
        evidence_signature=_canonical_json_hash(
            {
                "candidate": candidate.id,
                "selected_template": (
                    _subject_token(candidate.template_reference.subject_key)
                    if candidate.template_reference is not None
                    else ""
                ),
                "selected_template_member": (
                    candidate.template_reference.member_id
                    if candidate.template_reference is not None
                    else ""
                ),
                "transfer_mode": candidate.transfer_mode,
                "selection_mode": candidate.selection_mode,
                "body_signature": candidate.body_signature,
                "waler_offset_mm": round(candidate.reference_waler_offset_mm, 6),
                "strut_station_mm": round(candidate.reference_strut_station_mm, 6),
                "primary": [
                    _subject_token(reference.subject_key)
                    for reference in candidate.primary_references
                ],
                "secondary": [
                    _subject_token(reference.subject_key)
                    for reference in candidate.secondary_references
                ],
            }
        ),
        selection_mode=candidate.selection_mode,
        body_signature=candidate.body_signature,
    )
    body_evidence = next(
        (
            body
            for body in result.corner_brace_body_evidence
            if body.signature == candidate.body_signature
        ),
        None,
    )
    evidence_changes = (
        {
            "body_geometry_evidence": body_evidence,
            "relationship_assessment": candidate.relationship_assessment,
        }
        if candidate.selection_mode == "body_relationship_selection"
        else {}
    )
    if existing is not None:
        repaired = replace(
            existing,
            start=candidate.world_start,
            end=candidate.world_end,
            world_start=candidate.world_start,
            world_end=candidate.world_end,
            local_start=candidate.world_start,
            local_end=candidate.world_end,
            recognition_method=REPAIR_RECOGNITION_METHOD,
            selection_source=REPAIR_SELECTION_SOURCE,
            repair_provenance=provenance,
            **evidence_changes,
        )
        corners = tuple(
            repaired if corner.id == existing.id else corner
            for corner in result.corner_braces
        )
    else:
        repaired = replace(
            _temporary_corner(result, item, candidate, member_id),
            repair_provenance=provenance,
            **evidence_changes,
        )
        corners = (*result.corner_braces, repaired)

    target_handles = set(plan.subject_key.source_handles)
    retained_messages = tuple(
        message
        for message in result.messages
        if not (
            message.role == "corner_brace"
            and (
                member_id in message.member_ids
                or target_handles.intersection(normalize_source_handles(message.source_handles))
            )
        )
    )
    staged = replace(result, corner_braces=corners, messages=retained_messages)
    staged = rebuild_candidate_points_for_components(
        staged,
        (member_id,),
        tolerances,
        selection_source=REPAIR_SELECTION_SOURCE,
    )
    struts = attach_corner_braces_to_struts(
        staged.struts,
        staged.walers,
        staged.corner_braces,
        tolerances,
    )
    staged = replace(staged, struts=struts)
    if candidate.selection_mode == "body_relationship_selection":
        selected_connection = _selected_relationship_connection(
            member_id, candidate, waler, strut
        )
        connections = (
            *(
                connection
                for connection in result.corner_brace_connections
                if connection.corner_brace_id != member_id
            ),
            selected_connection,
        )
        connection_messages = ()
    else:
        connections, connection_messages = build_corner_brace_connections(
            staged, tolerances
        )
    matching = [value for value in connections if value.corner_brace_id == member_id]
    if (
        len(matching) != 1
        or matching[0].waler_id != candidate.target_waler_id
        or matching[0].strut_id != candidate.target_strut_id
    ):
        raise DXFImportError("角撐修補已無法產生通過檢核的連接關係。")
    duplicate_messages = validate_duplicate_engineering_members(
        (staged.corner_braces,),
        tolerances,
    )
    if any(member_id in message.member_ids for message in duplicate_messages):
        raise DXFImportError("角撐修補會建立重複的工程幾何。")
    staged = replace(
        staged,
        corner_brace_connections=connections,
        messages=(*retained_messages, *connection_messages, *duplicate_messages),
    )
    return staged, member_id


__all__ = [
    "PRIMARY_REFERENCE",
    "REPAIR_RECOGNITION_METHOD",
    "REPAIR_SELECTION_SOURCE",
    "SECONDARY_REFERENCE",
    "CornerBraceReferenceEvidence",
    "CornerBraceLocalTemplate",
    "CornerBraceRepairCandidate",
    "CornerBraceRepairPlan",
    "TargetRelationshipFrame",
    "TargetRepairAnchor",
    "TargetRepairEvidence",
    "apply_corner_brace_repair",
    "eligible_repair_references",
    "extract_corner_brace_local_template",
    "extract_target_repair_evidence",
    "plan_corner_brace_repair",
    "reconstruct_saved_template_candidate",
    "reconstruct_legacy_adopted_candidate",
    "repair_subject_key",
    "repair_subject_signature",
    "residual_axis_hypotheses",
    "target_residual_segments",
    "transfer_corner_brace_template",
]
