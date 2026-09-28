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
    _line_segment_intersection_point,
    _midpoint,
    _ordered_line,
    _projection_overlap_ratio,
    _unit,
    _vector,
)
from .models import (
    CornerBrace,
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
class CornerBraceRepairCandidate:
    """One fully eligible, deterministic candidate safe to preview."""

    id: str
    world_start: Point
    world_end: Point
    target_waler_id: str
    target_strut_id: str
    target_strut_endpoint_name: str
    primary_references: tuple[CornerBraceRepairReference, ...]
    secondary_references: tuple[CornerBraceRepairReference, ...] = ()
    residual_axis: tuple[Point, Point] = ((0.0, 0.0), (0.0, 0.0))
    proximity_mm: float = 0.0
    diagnostics: tuple[str, ...] = ()

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
        raise DXFImportError("Only recognized or unresolved CornerBrace subjects can be repaired.")
    handles = normalize_source_handles(item.source_handles)
    if not handles:
        raise DXFImportError("CornerBrace repair requires exact DXF source handles.")
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


def _candidate_side(
    strut_line: tuple[Point, Point],
    endpoint_name: str,
    strut_point: Point,
    waler_point: Point,
) -> int:
    inward = (
        _unit(*strut_line)
        if endpoint_name == "from"
        else _unit(strut_line[1], strut_line[0])
    )
    brace = _unit(strut_point, waler_point)
    if inward is None or brace is None:
        return 0
    value = _cross(inward, brace)
    if abs(value) <= 1e-9:
        return 0
    return 1 if value > 0 else -1


def _reference_matches(
    evidence: CornerBraceReferenceEvidence,
    result: DXFImportResult,
    *,
    candidate_line: tuple[Point, Point],
    candidate_strut_line: tuple[Point, Point],
    candidate_length: float,
    candidate_side: int,
    endpoint_name: str,
    tolerances: GeometryTolerances,
) -> bool:
    reference_strut = next(
        (item for item in result.struts if item.id == evidence.connection.strut_id),
        None,
    )
    if reference_strut is None or evidence.side != candidate_side:
        return False
    reference_strut_line = _world_line(reference_strut)
    candidate_angle = _angle_difference_deg(candidate_line, candidate_strut_line)
    reference_angle = _angle_difference_deg(
        (evidence.world_start, evidence.world_end),
        reference_strut_line,
    )
    if abs(candidate_angle - reference_angle) > tolerances.parallel_angle_tolerance_deg:
        return False
    if abs(candidate_length - evidence.connection.fixed_length_mm) > tolerances.connection_tolerance_mm:
        return False
    return evidence.topology == endpoint_name


def _candidate_id(
    start: Point,
    end: Point,
    waler_id: str,
    strut_id: str,
    tolerances: GeometryTolerances,
) -> str:
    digest = _canonical_json_hash(
        {
            "line": _line_key((start, end), tolerances),
            "waler": waler_id,
            "strut": strut_id,
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
    """Plan a repair without mutating the live review result."""

    tolerances = tolerances or GeometryTolerances()
    subject_key = repair_subject_key(result, item, tolerances)
    signature = repair_subject_signature(result, item, tolerances)
    residuals = target_residual_segments(result, subject_key, tolerances)
    diagnostics: list[str] = []
    if not residuals:
        diagnostics.append("Target source has no reliable residual CornerBrace geometry.")
    axes = residual_axis_hypotheses(residuals, tolerances)
    if residuals and not axes:
        diagnostics.append("Target residual geometry has no reliable finite direction hypothesis.")
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
        diagnostics.append("No eligible automatically recognized primary CornerBrace reference exists.")

    target_member = next(
        (corner for corner in result.corner_braces if corner.id == item.member_id),
        None,
    )
    target_midpoint = (
        _midpoint(*_world_line(target_member))
        if target_member is not None
        else _midpoint(*residuals[0]) if residuals else (0.0, 0.0)
    )
    candidate_by_key: dict[tuple[str, str, str], CornerBraceRepairCandidate] = {}
    rejected_count = 0
    if axes and primary:
        waler_by_id = {waler.id: waler for waler in result.walers}
        for axis in axes:
            for strut in result.struts:
                strut_line = _world_line(strut)
                for endpoint_name, waler_id in (
                    ("from", strut.from_waler),
                    ("to", strut.to_waler),
                ):
                    waler = waler_by_id.get(waler_id)
                    if waler is None:
                        continue
                    waler_point = _line_segment_intersection_point(
                        axis,
                        _world_line(waler),
                        tolerances.endpoint_tolerance_mm,
                    )
                    strut_point = _line_segment_intersection_point(
                        axis,
                        strut_line,
                        tolerances.endpoint_tolerance_mm,
                    )
                    if waler_point is None or strut_point is None:
                        continue
                    length = _distance(waler_point, strut_point)
                    if length < tolerances.minimum_component_length_mm:
                        rejected_count += 1
                        continue
                    side = _candidate_side(
                        strut_line,
                        endpoint_name,
                        strut_point,
                        waler_point,
                    )
                    matching_primary = tuple(
                        evidence.reference
                        for evidence in primary
                        if _reference_matches(
                            evidence,
                            result,
                            candidate_line=(waler_point, strut_point),
                            candidate_strut_line=strut_line,
                            candidate_length=length,
                            candidate_side=side,
                            endpoint_name=endpoint_name,
                            tolerances=tolerances,
                        )
                    )
                    if not matching_primary:
                        rejected_count += 1
                        continue
                    matching_secondary = tuple(
                        evidence.reference
                        for evidence in secondary
                        if _reference_matches(
                            evidence,
                            result,
                            candidate_line=(waler_point, strut_point),
                            candidate_strut_line=strut_line,
                            candidate_length=length,
                            candidate_side=side,
                            endpoint_name=endpoint_name,
                            tolerances=tolerances,
                        )
                    )
                    world_start, world_end = waler_point, strut_point
                    candidate = CornerBraceRepairCandidate(
                        id=_candidate_id(world_start, world_end, waler.id, strut.id, tolerances),
                        world_start=world_start,
                        world_end=world_end,
                        target_waler_id=waler.id,
                        target_strut_id=strut.id,
                        target_strut_endpoint_name=endpoint_name,
                        primary_references=matching_primary,
                        secondary_references=matching_secondary,
                        residual_axis=axis,
                        proximity_mm=_distance(_midpoint(world_start, world_end), target_midpoint),
                        diagnostics=(
                            f"finite intersections: {waler.id} / {strut.id}",
                            f"automatic primary references: {len(matching_primary)}",
                            f"manual secondary references: {len(matching_secondary)}",
                        ),
                    )
                    if not _candidate_passes_existing_validation(result, item, candidate, tolerances):
                        rejected_count += 1
                        continue
                    key = (
                        _line_key((world_start, world_end), tolerances),
                        waler.id,
                        strut.id,
                    )
                    previous = candidate_by_key.get(key)
                    if previous is None or candidate.id < previous.id:
                        candidate_by_key[key] = candidate

    candidates = tuple(
        sorted(
            candidate_by_key.values(),
            key=lambda candidate: (
                candidate.proximity_mm,
                candidate.target_waler_id,
                candidate.target_strut_id,
                candidate.id,
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
                "Unresolved source has multiple surviving Waler/Strut relationships."
            )
    if rejected_count:
        diagnostics.append(f"Rejected hypotheses: {rejected_count}.")
    if not candidates and not diagnostics:
        diagnostics.append("No hypothesis passed all CornerBrace repair eligibility checks.")
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
        raise DXFImportError("CornerBrace repair requires explicit user adoption.")
    candidate = next((value for value in plan.candidates if value.id == candidate_id), None)
    if candidate is None:
        raise DXFImportError("The selected CornerBrace repair candidate is not eligible.")
    waler = next((value for value in result.walers if value.id == candidate.target_waler_id), None)
    strut = next((value for value in result.struts if value.id == candidate.target_strut_id), None)
    if waler is None or strut is None:
        raise DXFImportError("The repair target Waler/Strut relationship no longer exists.")
    member_id = plan.target_member_id
    if plan.target_kind == "recognized":
        existing = next((value for value in result.corner_braces if value.id == member_id), None)
        if existing is None:
            raise DXFImportError("The recognized CornerBrace repair target no longer exists.")
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
        preferred_display_id=member_id,
        evidence_signature=_canonical_json_hash(
            {
                "candidate": candidate.id,
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
        )
        corners = tuple(
            repaired if corner.id == existing.id else corner
            for corner in result.corner_braces
        )
    else:
        repaired = replace(
            _temporary_corner(result, item, candidate, member_id),
            repair_provenance=provenance,
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
    connections, connection_messages = build_corner_brace_connections(staged, tolerances)
    matching = [value for value in connections if value.corner_brace_id == member_id]
    if (
        len(matching) != 1
        or matching[0].waler_id != candidate.target_waler_id
        or matching[0].strut_id != candidate.target_strut_id
    ):
        raise DXFImportError("CornerBrace repair no longer produces the validated connection.")
    duplicate_messages = validate_duplicate_engineering_members(
        (staged.corner_braces,),
        tolerances,
    )
    if any(member_id in message.member_ids for message in duplicate_messages):
        raise DXFImportError("CornerBrace repair would create duplicate engineering geometry.")
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
    "CornerBraceRepairCandidate",
    "CornerBraceRepairPlan",
    "apply_corner_brace_repair",
    "eligible_repair_references",
    "plan_corner_brace_repair",
    "repair_subject_key",
    "repair_subject_signature",
    "residual_axis_hypotheses",
    "target_residual_segments",
]
