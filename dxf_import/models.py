"""Immutable engineering models produced by DXF import."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field, replace
import math
from typing import Any, Mapping, Sequence

from .geometry import Point, _midpoint


ERROR_SEVERITIES = {"error", "critical"}
CONNECTION_VALIDATION_CODES = {
    "AMBIGUOUS_WALER_CONNECTION",
    "AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION",
    "BRACE_AXIS_EXTENDED_TO_WALER",
    "BRACE_SAME_WALER_CONNECTION",
    "STRUT_NOT_CONNECTED",
    "STRUT_ONE_END_NOT_CONNECTED",
    "BRACE_NOT_CONNECTED",
    "BRACE_ONE_END_NOT_CONNECTED",
}
COMPONENT_ASSOCIATION_CODES = {
    "COLUMN_NOT_ASSOCIATED",
    "BEAM_NOT_ASSOCIATED",
    "AMBIGUOUS_COMPONENT_ASSOCIATION",
    "COLUMN_ASSOCIATION_MANUALLY_RESOLVED",
    "COLUMN_ASSOCIATION_REQUIRES_REVIEW",
    "BEAM_CROSSING_SNAPPED",
    "BEAM_OVERLAPS_STRUT",
}


class DXFImportError(RuntimeError):
    """Raised when a DXF cannot be read or a blocked result is exported."""


@dataclass(frozen=True)
class GeometryTolerances:
    """All geometry/recognition tolerances, in drawing units (normally mm)."""

    endpoint_tolerance_mm: float = 50.0
    parallel_angle_tolerance_deg: float = 2.0
    width_tolerance_mm: float = 50.0
    collinear_tolerance_mm: float = 25.0
    duplicate_tolerance_mm: float = 50.0
    minimum_component_length_mm: float = 100.0
    connection_tolerance_mm: float = 250.0
    # Maximum automatic outward-axis extension used by Brace-to-Waler and
    # CornerBrace selected-rail-axis terminal recognition/finalization.  This
    # is recognition tuning, not the shared endpoint connection tolerance or
    # an engineering member-design rule.
    maximum_brace_axis_extension_mm: float = 600.0
    component_association_tolerance_mm: float = 250.0
    # Columns are commonly drawn beside a Strut centreline because both are
    # represented by their physical H-section footprints.  Their association
    # tolerance is therefore derived from both section widths plus this
    # installation/drafting allowance, while the maximum prevents an
    # unrelated distant Strut from being selected.
    column_association_clearance_mm: float = 150.0
    maximum_column_association_tolerance_mm: float = 750.0
    beam_crossing_tolerance_mm: float = 100.0
    beam_crossing_duplicate_tolerance_mm: float = 1.0
    ambiguous_connection_delta_mm: float = 25.0
    maximum_component_width_mm: float = 600.0
    minimum_slenderness_ratio: float = 1.5
    minimum_projection_overlap_ratio: float = 0.8
    # Engineering hard constraint for any Brace axis derived from a measured
    # physical body.  Equality is intentionally illegal; this value is not a
    # geometric matching tolerance and must not be softened by epsilon.
    minimum_brace_body_width_mm: float = 250.0
    # Formal CornerBrace material rule.  This is not Solver tuning: an
    # automatic CornerBrace must preserve two selected body rails whose
    # perpendicular separation is strictly greater than this value.
    minimum_corner_brace_rail_separation_mm: float = 250.0
    maximum_corner_brace_rail_separation_mm: float = 600.0
    minimum_corner_brace_expected_slenderness_ratio: float = 3.0
    corner_brace_track_seam_mm: float = 50.0
    minimum_corner_brace_rail_coverage_ratio: float = 0.5
    minimum_corner_brace_parallel_occluder_overlap_ratio: float = 0.5
    maximum_corner_brace_axis_extension_mm: float = 600.0
    # Deprecated compatibility input for pre-redesign callers.  The active
    # CornerBrace route uses per-rail expected-span coverage above instead.
    minimum_corner_brace_occluded_rail_length_ratio: float = 0.75
    ambiguous_candidate_score_delta: float = 0.03
    # Synthetic BIM characterization uses two equally supported conflicting
    # whole-axis clusters as the ambiguity boundary.  Requiring at least half
    # of the de-duplicated strong longitudinal evidence keeps both candidates
    # eligible for ambiguity, while a minority direction cannot win alone.
    # This is recognition tuning, not an engineering/member-design rule.
    bim_minimum_longitudinal_evidence_ratio: float = 0.5
    double_support_spacing_mm: float = 1000.0
    double_support_spacing_tolerance_mm: float = 150.0
    double_support_overlap_ratio: float = 0.9
    double_support_length_tolerance_mm: float = 250.0
    material_width_tolerance_mm: float = 1.0


@dataclass(frozen=True)
class BlockInstanceInfo:
    handle: str
    block_name: str
    insertion_point: Point
    rotation: float
    xscale: float
    yscale: float


@dataclass(frozen=True)
class ValidationMessage:
    severity: str
    code: str
    message: str
    role: str = ""
    source_handles: tuple[str, ...] = ()
    member_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CornerBraceRailFragmentEvidence:
    """One exact finite source fragment used by a CornerBrace rail track."""

    id: str
    source_handle: str
    line: tuple[Point, Point]
    normal_offset_mm: float
    interval: tuple[float, float]


@dataclass(frozen=True)
class CornerBraceRailTrackEvidence:
    """Order-independent collinear fragment hypothesis for one body rail."""

    id: str
    fragments: tuple[CornerBraceRailFragmentEvidence, ...]
    supporting_line: tuple[Point, Point]
    canonical_direction: Point
    canonical_normal: Point
    normal_offsets_mm: tuple[float, ...]
    merged_intervals: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class CornerBraceBodyGeometryEvidence:
    """Immutable geometry-only evidence; relationship facts are forbidden."""

    signature: str
    group_key: str
    source_handles: tuple[str, ...]
    fragments: tuple[CornerBraceRailFragmentEvidence, ...]
    rail_tracks: tuple[CornerBraceRailTrackEvidence, CornerBraceRailTrackEvidence]
    selected_track_ids: tuple[str, str]
    supporting_line_ids: tuple[str, str]
    canonical_direction: Point
    canonical_normal: Point
    midline: tuple[Point, Point]
    rail_separation_mm: float
    merged_source_intervals: tuple[
        tuple[tuple[float, float], ...],
        tuple[tuple[float, float], ...],
    ]
    terminal_plate_evidence: tuple[tuple[Point, Point], ...] = ()


@dataclass(frozen=True)
class CornerBraceGapEvidence:
    """One material absence longer than the accepted RailTrack seam."""

    rail_track_id: str
    kind: str
    interval: tuple[float, float]
    world_line: tuple[Point, Point]

    @property
    def length_mm(self) -> float:
        return max(0.0, self.interval[1] - self.interval[0])


@dataclass(frozen=True)
class CornerBraceGapOccluderAssignment:
    """Finite source lines that explain one and only one measured gap."""

    gap: CornerBraceGapEvidence
    occluder_lines: tuple[tuple[Point, Point], ...]


@dataclass(frozen=True)
class CornerBraceBodyRelationshipAssessment:
    """Relationship-dependent validation of one immutable body hypothesis."""

    body_signature: str
    waler_source_handles: tuple[str, ...]
    strut_source_handles: tuple[str, ...]
    finite_intersections: tuple[Point, Point]
    expected_span_mm: float
    expected_slenderness_ratio: float
    per_rail_union_coverage: tuple[float, float]
    internal_gaps: tuple[CornerBraceGapEvidence, ...]
    terminal_gaps: tuple[CornerBraceGapEvidence, ...]
    gap_occluder_assignments: tuple[CornerBraceGapOccluderAssignment, ...]
    per_end_extensions_mm: tuple[float, float]
    classification: str
    hard_valid: bool
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class EngineeringLineCandidate:
    """Legacy/internal line evidence used to derive endpoint candidates."""

    id: str
    label: str
    world_start: Point
    world_end: Point
    source: str


@dataclass(frozen=True)
class CandidatePoint:
    """One exact world-coordinate point offered for a member endpoint."""

    id: str
    world_point: Point
    local_point: Point
    point_type: str
    label: str
    source_handles: tuple[str, ...] = ()
    source_entity_types: tuple[str, ...] = ()
    recommended_for: tuple[str, ...] = ()
    score: float = 0.0
    point_types: tuple[str, ...] = ()
    valid_for: tuple[str, ...] = ("start", "end")
    component_id: str = ""


@dataclass(frozen=True)
class CoordinateSystem:
    mode: str = "world"
    origin_x: float = 0.0
    origin_y: float = 0.0
    source: str = "cad_world"

    def __post_init__(self) -> None:
        if self.mode not in {"world", "local"}:
            raise ValueError(f"不支援的座標系統模式：{self.mode}")
        if not math.isfinite(self.origin_x) or not math.isfinite(self.origin_y):
            raise ValueError("座標原點必須是有限數字")

    def transform(self, point: Point) -> Point:
        if self.mode == "local":
            return point[0] - self.origin_x, point[1] - self.origin_y
        return point


def parse_coordinate_origin(origin_x: str, origin_y: str) -> tuple[float, float]:
    """Validate coordinate-entry text using the user-facing error contract."""

    if not str(origin_x).strip() or not str(origin_y).strip():
        raise DXFImportError("請輸入原點座標")
    try:
        x_value, y_value = float(origin_x), float(origin_y)
    except (TypeError, ValueError) as exc:
        raise DXFImportError("原點座標格式錯誤") from exc
    if not math.isfinite(x_value) or not math.isfinite(y_value):
        raise DXFImportError("原點座標格式錯誤")
    return x_value, y_value


def coordinate_system_from_candidate(candidate: CandidatePoint) -> CoordinateSystem:
    """Use one explicitly selected DXF point as the exact local origin."""

    return CoordinateSystem(
        "local",
        float(candidate.world_point[0]),
        float(candidate.world_point[1]),
        "selected_candidate_point",
    )


def normalize_project_coordinate(value: Any) -> int:
    """Normalize a Solver-facing drawing coordinate to the nearest millimetre."""

    number = float(value)
    return math.floor(number + 0.5) if number >= 0 else math.ceil(number - 0.5)


@dataclass(frozen=True)
class Waler:
    id: str
    start: Point
    end: Point
    source_layer: str
    source_handles: tuple[str, ...]
    source_entity_types: tuple[str, ...]
    recognition_method: str
    centerline_computed: bool
    source_width: float
    confidence: float
    warnings: tuple[str, ...] = ()
    block_instances: tuple[BlockInstanceInfo, ...] = ()
    engineering_line_kind: str = "inner_line"
    world_start: Point | None = None
    world_end: Point | None = None
    local_start: Point | None = None
    local_end: Point | None = None
    line_candidates: tuple[EngineeringLineCandidate, ...] = ()
    selected_candidate_id: str = ""
    candidate_points: tuple[CandidatePoint, ...] = ()
    recommended_start_point_id: str = ""
    recommended_end_point_id: str = ""
    selected_start_point_id: str = ""
    selected_end_point_id: str = ""
    selection_source: str = "auto"
    material_spec: str = ""
    material_spec_source: str = ""
    contact_face_state: str = "formal"

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_start", self.start if self.world_start is None else self.world_start)
        object.__setattr__(self, "world_end", self.end if self.world_end is None else self.world_end)
        object.__setattr__(self, "local_start", self.start if self.local_start is None else self.local_start)
        object.__setattr__(self, "local_end", self.end if self.local_end is None else self.local_end)
        if self.contact_face_state not in {"formal", "provisional"}:
            raise ValueError(
                "Unsupported Waler contact-face state: "
                f"{self.contact_face_state}"
            )

    @property
    def source_type(self) -> str:
        return "+".join(self.source_entity_types)

    @property
    def has_formal_contact_face(self) -> bool:
        return self.contact_face_state == "formal"

    def to_project_row(self) -> dict[str, Any]:
        recognition = f"DXF {self.recognition_method} ({self.confidence:.0%})"
        return {
            "WalerID": self.id,
            "StartX": self.start[0],
            "StartY": self.start[1],
            "EndX": self.end[0],
            "EndY": self.end[1],
            "material_spec": self.material_spec,
            "Remark": recognition,
        }


@dataclass(frozen=True)
class StrutTerminalTopology:
    """Structured Waler qualification for one recognized Strut terminal."""

    terminal_name: str
    waler_source_handles: tuple[str, ...] = ()
    reason_code: str = ""
    competing_waler_source_handles: tuple[tuple[str, ...], ...] = ()
    message: str = ""


@dataclass(frozen=True)
class Strut:
    id: str
    start: Point
    end: Point
    source_layer: str
    source_handles: tuple[str, ...]
    source_entity_types: tuple[str, ...]
    recognition_method: str
    centerline_computed: bool
    source_width: float
    from_waler: str
    to_waler: str
    confidence: float
    warnings: tuple[str, ...] = ()
    block_instances: tuple[BlockInstanceInfo, ...] = ()
    world_start: Point | None = None
    world_end: Point | None = None
    local_start: Point | None = None
    local_end: Point | None = None
    line_candidates: tuple[EngineeringLineCandidate, ...] = ()
    selected_candidate_id: str = ""
    candidate_points: tuple[CandidatePoint, ...] = ()
    recommended_start_point_id: str = ""
    recommended_end_point_id: str = ""
    selected_start_point_id: str = ""
    selected_end_point_id: str = ""
    selection_source: str = "auto"
    beam_positions: tuple[float, ...] = ()
    column_positions: tuple[float, ...] = ()
    associated_columns: tuple[str, ...] = ()
    associated_beams: tuple[str, ...] = ()
    from_brace_to_waler_start_len: float = 0.0
    from_brace_to_waler_end_len: float = 0.0
    to_brace_to_waler_start_len: float = 0.0
    to_brace_to_waler_end_len: float = 0.0
    material_spec: str = ""
    material_spec_source: str = ""
    initial_zoning: str = ""
    source_axis_supported: bool = True
    terminal_topology_authoritative: bool = False
    terminal_topology: tuple[StrutTerminalTopology, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_start", self.start if self.world_start is None else self.world_start)
        object.__setattr__(self, "world_end", self.end if self.world_end is None else self.world_end)
        object.__setattr__(self, "local_start", self.start if self.local_start is None else self.local_start)
        object.__setattr__(self, "local_end", self.end if self.local_end is None else self.local_end)

    @property
    def source_type(self) -> str:
        return "+".join(self.source_entity_types)

    def to_project_row(self, *, reverse: bool = False) -> dict[str, Any]:
        def position_text(values: Sequence[float]) -> str:
            return ",".join(f"{value:g}" for value in values)

        start, end = (self.end, self.start) if reverse else (self.start, self.end)
        from_waler, to_waler = (
            (self.to_waler, self.from_waler)
            if reverse
            else (self.from_waler, self.to_waler)
        )
        beam_positions = self.beam_positions
        column_positions = self.column_positions
        from_brace_lengths = (
            self.from_brace_to_waler_start_len,
            self.from_brace_to_waler_end_len,
        )
        to_brace_lengths = (
            self.to_brace_to_waler_start_len,
            self.to_brace_to_waler_end_len,
        )
        if reverse:
            total_length = math.dist(self.start, self.end)
            beam_positions = tuple(
                sorted(total_length - value for value in self.beam_positions)
            )
            column_positions = tuple(
                sorted(total_length - value for value in self.column_positions)
            )
            from_brace_lengths, to_brace_lengths = (
                to_brace_lengths,
                from_brace_lengths,
            )

        return {
            "StrutID": self.id,
            "FromWaler": from_waler,
            "ToWaler": to_waler,
            "StartX": start[0],
            "StartY": start[1],
            "EndX": end[0],
            "EndY": end[1],
            "material_spec": self.material_spec,
            "BeamPositions": position_text(beam_positions),
            "ColumnPositions": position_text(column_positions),
            "AssociatedColumnIDs": ",".join(self.associated_columns),
            "AssociatedBeamIDs": ",".join(self.associated_beams),
            "FromBraceToWalerStartLen": from_brace_lengths[0],
            "FromBraceToWalerEndLen": from_brace_lengths[1],
            "ToBraceToWalerStartLen": to_brace_lengths[0],
            "ToBraceToWalerEndLen": to_brace_lengths[1],
            "TargetJackRegion": 2,
            "Zoning": self.initial_zoning or "DXF",
        }


@dataclass(frozen=True)
class Brace:
    id: str
    start: Point
    end: Point
    source_layer: str
    source_handles: tuple[str, ...]
    source_entity_types: tuple[str, ...]
    recognition_method: str
    centerline_computed: bool
    source_width: float
    from_waler: str
    to_waler: str
    confidence: float
    warnings: tuple[str, ...] = ()
    block_instances: tuple[BlockInstanceInfo, ...] = ()
    world_start: Point | None = None
    world_end: Point | None = None
    local_start: Point | None = None
    local_end: Point | None = None
    line_candidates: tuple[EngineeringLineCandidate, ...] = ()
    selected_candidate_id: str = ""
    candidate_points: tuple[CandidatePoint, ...] = ()
    recommended_start_point_id: str = ""
    recommended_end_point_id: str = ""
    selected_start_point_id: str = ""
    selected_end_point_id: str = ""
    selection_source: str = "auto"

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_start", self.start if self.world_start is None else self.world_start)
        object.__setattr__(self, "world_end", self.end if self.world_end is None else self.world_end)
        object.__setattr__(self, "local_start", self.start if self.local_start is None else self.local_start)
        object.__setattr__(self, "local_end", self.end if self.local_end is None else self.local_end)

    @property
    def source_type(self) -> str:
        return "+".join(self.source_entity_types)

    @property
    def has_formal_connection(self) -> bool:
        """Whether this Brace owns one complete, distinct Waler pair."""

        return bool(
            self.from_waler
            and self.to_waler
            and self.from_waler != self.to_waler
        )

    def to_project_row(self) -> dict[str, Any]:
        return {
            "BraceID": self.id,
            "FromWaler": self.from_waler,
            "ToWaler": self.to_waler,
            "StartX": self.start[0],
            "StartY": self.start[1],
            "EndX": self.end[0],
            "EndY": self.end[1],
        }


@dataclass(frozen=True)
class AuxiliaryComponent:
    """Recognized non-Solver linear component retained in the import model."""

    id: str
    start: Point
    end: Point
    source_layer: str
    source_handles: tuple[str, ...]
    source_entity_types: tuple[str, ...]
    recognition_method: str
    centerline_computed: bool
    source_width: float
    confidence: float
    warnings: tuple[str, ...] = ()
    block_instances: tuple[BlockInstanceInfo, ...] = ()
    world_start: Point | None = None
    world_end: Point | None = None
    local_start: Point | None = None
    local_end: Point | None = None
    line_candidates: tuple[EngineeringLineCandidate, ...] = ()
    selected_candidate_id: str = ""
    candidate_points: tuple[CandidatePoint, ...] = ()
    recommended_start_point_id: str = ""
    recommended_end_point_id: str = ""
    selected_start_point_id: str = ""
    selected_end_point_id: str = ""
    selection_source: str = "auto"
    associated_strut_id: str = ""
    association_station: float | None = None
    association_distance: float | None = None
    world_association_point: Point | None = None
    local_association_point: Point | None = None
    reference_point: Point | None = None
    world_reference_point: Point | None = None
    local_reference_point: Point | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "world_start", self.start if self.world_start is None else self.world_start)
        object.__setattr__(self, "world_end", self.end if self.world_end is None else self.world_end)
        object.__setattr__(self, "local_start", self.start if self.local_start is None else self.local_start)
        object.__setattr__(self, "local_end", self.end if self.local_end is None else self.local_end)
        default_reference = _midpoint(self.start, self.end)
        object.__setattr__(
            self,
            "reference_point",
            default_reference if self.reference_point is None else self.reference_point,
        )
        object.__setattr__(
            self,
            "world_reference_point",
            default_reference
            if self.world_reference_point is None
            else self.world_reference_point,
        )
        object.__setattr__(
            self,
            "local_reference_point",
            default_reference
            if self.local_reference_point is None
            else self.local_reference_point,
        )

    def to_project_row(self) -> dict[str, Any]:
        return {
            "ID": self.id,
            "StartX": self.start[0],
            "StartY": self.start[1],
            "EndX": self.end[0],
            "EndY": self.end[1],
            "SourceLayer": self.source_layer,
            "AssociatedStrutID": self.associated_strut_id,
            "AssociationStation": self.association_station,
            "AssociationDistance": self.association_distance,
            "ReferenceX": self.reference_point[0] if self.reference_point else None,
            "ReferenceY": self.reference_point[1] if self.reference_point else None,
        }


@dataclass(frozen=True)
class Column(AuxiliaryComponent):
    """DXF-classified intermediate-column engineering line.

    ``associated_strut_id`` remains the primary association used for
    review/UI provenance (nearest automatically, first selected when manually
    resolved). An accepted double-support pair or an explicit manual choice
    may contain this Column in both Struts' derived association fields.
    """


@dataclass(frozen=True)
class BeamCrossing:
    """One physical crossing between a bearer-beam path and a Strut."""

    beam_id: str
    strut_id: str
    world_point: Point
    local_point: Point
    strut_station: float
    beam_segment_index: int
    distance: float = 0.0
    recognition_method: str = "segment_intersection"
    world_source_contact_point: Point | None = None
    local_source_contact_point: Point | None = None


@dataclass(frozen=True)
class BeamBraceContact:
    """One direct finite contact between a Beam path and a formal Brace."""

    beam_id: str
    brace_id: str
    world_point: Point
    local_point: Point
    beam_segment_index: int
    recognition_method: str = "finite_segment_intersection"


@dataclass(frozen=True)
class Beam(AuxiliaryComponent):
    """Bearer beam retained as an ordered path instead of one chord."""

    world_path: tuple[Point, ...] = ()
    local_path: tuple[Point, ...] = ()
    path: tuple[Point, ...] = ()
    associated_strut_ids: tuple[str, ...] = ()
    crossings: tuple[BeamCrossing, ...] = ()
    brace_contacts: tuple[BeamBraceContact, ...] = ()
    joist_assembly_key: str = ""
    joist_axis_slot: int | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        default_path = (self.world_start, self.world_end)
        world_path = self.world_path or default_path
        local_path = self.local_path or world_path
        active_path = self.path or world_path
        object.__setattr__(self, "world_path", tuple(world_path))
        object.__setattr__(self, "local_path", tuple(local_path))
        object.__setattr__(self, "path", tuple(active_path))

    def to_project_row(self) -> dict[str, Any]:
        row = super().to_project_row()
        row.update(
            Path=[list(point) for point in self.path],
            WorldPath=[list(point) for point in self.world_path],
            LocalPath=[list(point) for point in self.local_path],
            AssociatedStrutIDs=",".join(self.associated_strut_ids),
            Crossings=[asdict(crossing) for crossing in self.crossings],
        )
        return row


@dataclass(frozen=True)
class CornerBraceRepairSubjectKey:
    """Stable identity for one repairable CornerBrace source subject.

    Source handles alone are insufficient because one compound INSERT may
    produce more than one CornerBrace.  ``base_geometry_key`` is therefore a
    canonical, tolerance-quantized discriminator derived from the subject's
    original geometry.  The key deliberately contains no UI label.
    """

    source_fingerprint: str
    source_handles: tuple[str, ...]
    target_kind: str
    base_geometry_key: str
    role: str = "corner_brace"

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_fingerprint", str(self.source_fingerprint).strip().upper())
        object.__setattr__(self, "source_handles", _normalized_source_handles(self.source_handles))
        object.__setattr__(self, "target_kind", str(self.target_kind).strip().lower())
        object.__setattr__(self, "base_geometry_key", str(self.base_geometry_key).strip())
        object.__setattr__(self, "role", "corner_brace")


@dataclass(frozen=True)
class CornerBraceRepairReference:
    """Auditable identity and class of one adopted repair reference."""

    subject_key: CornerBraceRepairSubjectKey
    member_id: str
    reference_class: str


@dataclass(frozen=True)
class CornerBraceRepairProvenance:
    """Replayable evidence for one explicitly adopted CornerBrace repair."""

    subject_key: CornerBraceRepairSubjectKey
    adopted_world_start: Point
    adopted_world_end: Point
    target_waler_identity: str
    target_strut_identity: str
    automatic_primary_references: tuple[CornerBraceRepairReference, ...]
    manual_secondary_references: tuple[CornerBraceRepairReference, ...] = ()
    selected_template_reference: CornerBraceRepairReference | None = None
    transfer_mode: str = ""
    reference_waler_offset_mm: float | None = None
    reference_strut_station_mm: float | None = None
    preferred_display_id: str = ""
    selection_source: str = "corner_brace_repair"
    evidence_signature: str = ""
    selection_mode: str = "reference_template"
    body_signature: str = ""


@dataclass(frozen=True)
class CornerBrace(AuxiliaryComponent):
    """DXF-classified corner-brace engineering line."""

    repair_provenance: CornerBraceRepairProvenance | None = None
    body_geometry_evidence: CornerBraceBodyGeometryEvidence | None = None
    relationship_assessment: CornerBraceBodyRelationshipAssessment | None = None


@dataclass(frozen=True)
class LayerInfo:
    name: str
    entity_count: int
    entity_types: Mapping[str, int]


@dataclass(frozen=True)
class EntityDebugInfo:
    role: str
    layer: str
    entity_type: str
    handle: str
    status: str
    severity: str = "info"
    output_ids: tuple[str, ...] = ()
    block_instance: str = ""
    detail: str = ""


@dataclass(frozen=True)
class SourceGeometry:
    role: str
    source_handle: str
    points: tuple[Point, ...]
    closed: bool
    source_layer: str = ""
    source_entity_type: str = ""


@dataclass(frozen=True)
class SourceText:
    """Preview-only text retained from an auxiliary DXF layer."""

    role: str
    source_handle: str
    text: str
    position: Point
    height: float = 0.0
    rotation: float = 0.0
    source_layer: str = ""
    source_entity_type: str = ""


@dataclass(frozen=True)
class ComponentAssociation:
    """One confirmed Column/Beam constraint relation to a Solver strut."""

    component_id: str
    component_role: str
    strut_id: str
    station: float
    distance: float
    world_projection_point: Point
    local_projection_point: Point


@dataclass(frozen=True)
class ProblemRecord:
    severity: str
    code: str
    component: str
    description: str
    role: str
    source_handles: tuple[str, ...]
    member_ids: tuple[str, ...]


def _normalized_source_handles(values: Sequence[Any]) -> tuple[str, ...]:
    """Return the canonical DXF-handle representation used by review state."""

    return tuple(
        sorted(
            {
                str(value).strip().upper()
                for value in values
                if str(value).strip()
            }
        )
    )


@dataclass(frozen=True)
class SourceManualOverride:
    """Only replayable user input for one exact DXF source group."""

    role: str
    source_handles: tuple[str, ...]
    display_id: str = ""
    has_material_spec: bool = False
    material_spec: str = ""
    geometry_selection_source: str = ""
    world_start: Point | None = None
    world_end: Point | None = None
    has_waler_contact_input: bool = False
    original_backfill_mm: float | None = None
    adopted_backfill_mm: float | None = None
    original_waler_width_mm: float | None = None
    adopted_waler_width_mm: float | None = None
    corner_brace_repair: CornerBraceRepairProvenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", str(self.role).strip().lower())
        object.__setattr__(
            self,
            "source_handles",
            _normalized_source_handles(self.source_handles),
        )


@dataclass(frozen=True)
class ColumnAssociationDecision:
    """A source-bound human choice of one or two Struts for a Column."""

    column_source_handles: tuple[str, ...]
    candidate_strut_sources: tuple[tuple[str, ...], tuple[str, ...]]
    selected_strut_sources: tuple[tuple[str, ...], ...]
    source_fingerprint: str
    column_display_id: str = ""

    def __post_init__(self) -> None:
        column_source = _normalized_source_handles(self.column_source_handles)
        candidate_sources = tuple(
            _normalized_source_handles(source) for source in self.candidate_strut_sources
        )
        selected_sources = tuple(
            _normalized_source_handles(source) for source in self.selected_strut_sources
        )
        if (
            not column_source
            or len(candidate_sources) != 2
            or not all(candidate_sources)
            or candidate_sources[0] == candidate_sources[1]
            or not selected_sources
            or len(set(selected_sources)) != len(selected_sources)
            or not set(selected_sources).issubset(candidate_sources)
        ):
            raise ValueError("Invalid source-bound Column association decision")
        object.__setattr__(self, "column_source_handles", column_source)
        object.__setattr__(
            self,
            "candidate_strut_sources",
            tuple(sorted(candidate_sources)),
        )
        object.__setattr__(
            self,
            "selected_strut_sources",
            tuple(sorted(selected_sources)),
        )
        object.__setattr__(
            self,
            "source_fingerprint",
            str(self.source_fingerprint).strip().upper(),
        )


@dataclass(frozen=True)
class ExcludedSource:
    """Persistent user decision to omit one exact DXF source group."""

    role: str
    source_handles: tuple[str, ...]
    source_layers: tuple[str, ...] = ()
    source_entity_types: tuple[str, ...] = ()
    display_id_when_excluded: str = ""
    reason: str = "user_excluded"
    manual_override: SourceManualOverride | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", str(self.role).strip().lower())
        object.__setattr__(
            self,
            "source_handles",
            _normalized_source_handles(self.source_handles),
        )
        object.__setattr__(
            self,
            "source_layers",
            tuple(sorted({str(value).strip() for value in self.source_layers if str(value).strip()})),
        )
        object.__setattr__(
            self,
            "source_entity_types",
            tuple(
                sorted(
                    {
                        str(value).strip().upper()
                        for value in self.source_entity_types
                        if str(value).strip()
                    }
                )
            ),
        )
        object.__setattr__(
            self,
            "display_id_when_excluded",
            str(self.display_id_when_excluded).strip(),
        )
        object.__setattr__(self, "reason", str(self.reason).strip() or "user_excluded")

    @property
    def identity(self) -> str:
        return f"{self.role}:{'|'.join(self.source_handles)}"


@dataclass(frozen=True)
class ReviewItem:
    """Immutable STEP3/STEP4 projection of one reviewable DXF object."""

    key: str
    display_id: str
    role: str
    status: str
    member_id: str | None
    source_handles: tuple[str, ...]
    source_layers: tuple[str, ...]
    source_entity_types: tuple[str, ...]
    selection_source: str
    problems: tuple[ProblemRecord, ...]
    highest_severity: str
    exclusion_reason: str = ""
    display_id_before_exclusion: str = ""

    @property
    def problem_count(self) -> int:
        return len(self.problems)


@dataclass
class SelectionState:
    """Single source of truth for all non-Solver import interactions."""

    selected_component_id: str = ""
    hovered_component_id: str = ""
    mode: str = "idle"
    selected_candidate_point_id: str = ""
    selected_candidate_source: str = ""
    hovered_candidate_point_id: str = ""
    preview_candidate_point_id: str = ""
    selected_start_point_id: str = ""
    selected_end_point_id: str = ""
    pending_start_point_id: str = ""
    pending_end_point_id: str = ""
    selection_source: str = "programmatic"
    pending_selection_source: str = "auto"
    pick_baseline_start_point_id: str = ""
    pick_baseline_end_point_id: str = ""
    revision: int = 0


@dataclass(frozen=True)
class ValidationOverviewItem:
    level: str
    text: str


@dataclass(frozen=True)
class DoubleSupportQualificationIssue:
    """Why a geometry-qualified pair is not yet formally eligible."""

    code: str
    member_id: str
    member_source_handles: tuple[str, ...]
    terminal_name: str
    competing_waler_source_handles: tuple[tuple[str, ...], ...] = ()
    message: str = ""


@dataclass(frozen=True)
class DoubleSupportCandidate:
    """Reviewable DXF inference that two physical struts share one layout."""

    id: str
    first_strut_id: str
    second_strut_id: str
    centerline_spacing: float
    angle_difference_deg: float
    overlap_ratio: float
    length_difference: float
    confidence: float
    accepted: bool = True
    ambiguous: bool = False
    warnings: tuple[str, ...] = ()
    qualification_status: str = "eligible"
    issues: tuple[DoubleSupportQualificationIssue, ...] = ()

    def __post_init__(self) -> None:
        if self.qualification_status not in {
            "eligible",
            "pending_waler",
            "incompatible_waler",
        }:
            raise ValueError(
                "Unsupported double-support qualification status: "
                f"{self.qualification_status}"
            )
        if self.qualification_status != "eligible" and self.accepted:
            object.__setattr__(self, "accepted", False)

    @property
    def is_formally_accepted(self) -> bool:
        """Return whether this pair may produce formal engineering effects."""

        return self.qualification_status == "eligible" and self.accepted


@dataclass(frozen=True)
class WalerContactReviewState:
    """DXF-review-only baseline and adopted contact dimensions for one Waler."""

    waler_id: str
    baseline_contact_start: Point
    baseline_contact_end: Point
    support_normal_world: Point | None
    original_backfill_mm: float | None = None
    adopted_backfill_mm: float | None = None
    original_waler_width_mm: float | None = None
    adopted_waler_width_mm: float | None = None
    waler_outer_start: Point | None = None
    waler_outer_end: Point | None = None
    continuous_wall_inner_start: Point | None = None
    continuous_wall_inner_end: Point | None = None
    continuous_wall_source_handle: str = ""
    backfill_recognition_method: str = ""

    @property
    def contact_displacement(self) -> float | None:
        values = (
            self.original_backfill_mm,
            self.adopted_backfill_mm,
            self.original_waler_width_mm,
            self.adopted_waler_width_mm,
        )
        if any(value is None for value in values):
            return None
        assert all(value is not None for value in values)
        return (
            self.adopted_backfill_mm
            - self.original_backfill_mm
            + self.adopted_waler_width_mm
            - self.original_waler_width_mm
        )


@dataclass(frozen=True)
class CornerBraceConnection:
    """Stable DXF-review association used when a Waler contact line moves."""

    corner_brace_id: str
    waler_id: str
    strut_id: str
    strut_endpoint_name: str
    corner_waler_endpoint_name: str
    baseline_waler_attachment: Point
    baseline_strut_attachment: Point
    strut_hole_station_mm: float
    fixed_length_mm: float
    baseline_waler_station_mm: float


@dataclass(frozen=True)
class DXFImportResult:
    """Serializable result of recognition, validation and connection analysis."""

    source_path: str
    layer_names: tuple[str, ...]
    selected_layers: Mapping[str, tuple[str, ...]]
    layer_info: tuple[LayerInfo, ...]
    walers: tuple[Waler, ...]
    struts: tuple[Strut, ...]
    braces: tuple[Brace, ...]
    entity_debug: tuple[EntityDebugInfo, ...]
    messages: tuple[ValidationMessage, ...]
    source_entity_counts: Mapping[str, int]
    source_geometry: tuple[SourceGeometry, ...] = ()
    source_texts: tuple[SourceText, ...] = ()
    coordinate_system: CoordinateSystem = CoordinateSystem()
    columns: tuple[Column, ...] = ()
    beams: tuple[Beam, ...] = ()
    corner_braces: tuple[CornerBrace, ...] = ()
    layer_classification: Mapping[str, str] = field(default_factory=dict)
    component_associations: tuple[ComponentAssociation, ...] = ()
    beam_crossings: tuple[BeamCrossing, ...] = ()
    double_support_candidates: tuple[DoubleSupportCandidate, ...] = ()
    waler_contact_reviews: tuple[WalerContactReviewState, ...] = ()
    corner_brace_connections: tuple[CornerBraceConnection, ...] = ()
    corner_brace_body_evidence: tuple[CornerBraceBodyGeometryEvidence, ...] = ()
    corner_brace_relationship_assessments: tuple[
        CornerBraceBodyRelationshipAssessment, ...
    ] = ()
    source_fingerprint: str = ""
    excluded_sources: tuple[ExcludedSource, ...] = ()

    def with_initial_zoning(
        self,
        existing_zonings: Sequence[str] = (),
        *,
        tolerances: GeometryTolerances | None = None,
    ) -> DXFImportResult:
        """Return reviewed geometry with deterministic initial Zoning values.

        This operation is intentionally explicit: recognition and review do
        not call it.  The Project application boundary invokes it only after
        the user completes the review and immediately before row mapping.
        """

        from .initial_zoning import assign_initial_zoning

        return assign_initial_zoning(
            self,
            existing_zonings=existing_zonings,
            tolerances=tolerances or GeometryTolerances(),
        ).result

    @property
    def can_import(self) -> bool:
        return not any(message.severity in ERROR_SEVERITIES for message in self.messages)

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(
            f"{item.code}: {item.message}"
            for item in self.messages
            if item.severity in {"warning", "error", "critical"}
        )

    def summary(self) -> dict[str, Any]:
        method_counts = Counter(
            member.recognition_method
            for member in (
                *self.walers,
                *self.struts,
                *self.braces,
                *self.columns,
                *self.beams,
                *self.corner_braces,
            )
        )

        def connection_counts(members: Sequence[Strut | Brace]) -> tuple[int, int, int]:
            fully = sum(bool(member.from_waler and member.to_waler) for member in members)
            partial = sum(bool(member.from_waler) ^ bool(member.to_waler) for member in members)
            return fully, partial, len(members) - fully - partial

        full_s, partial_s, none_s = connection_counts(self.struts)
        full_b, partial_b, none_b = connection_counts(self.braces)
        severities = Counter(message.severity for message in self.messages)
        failed_codes = {
            "WALER_ENGINEERING_LINE_FAILED",
            "STRUT_CENTERLINE_FAILED",
            "BRACE_CENTERLINE_FAILED",
            "WALER_RECOGNITION_FAILED",
            "STRUT_RECOGNITION_FAILED",
            "BRACE_RECOGNITION_FAILED",
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES",
            "BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE",
            "BIM_JOIST_CONFLICTING_WHOLE_AXES",
            "BIM_JOIST_PAIR_AMBIGUOUS",
            "BIM_JOIST_PAIR_SPACING_INVALID",
            "BIM_JOIST_PAIR_UNPAIRED",
            "BIM_JOIST_RECOGNITION_FAILED",
            "BIM_JOIST_SINGLE_NO_BRACE_CONTACT",
            "BIM_JOIST_SINGLE_STRUT_OBLIGATION",
            "BIM_JOIST_STRUT_FACE_CONTACT_AMBIGUOUS",
            "BIM_JOIST_TERMINAL_CONTEXT_DRIFT",
            "BIM_JOIST_TERMINAL_RESIDUAL_AMBIGUOUS",
            "BIM_JOIST_WHOLE_SOURCE_AXIS_FAILED",
        }
        return {
            "selected_layers": dict(self.selected_layers),
            "source_entities": dict(self.source_entity_counts),
            "recognized_components": {
                "walers": len(self.walers),
                "struts": len(self.struts),
                "braces": len(self.braces),
                "columns": len(self.columns),
                "beams": len(self.beams),
                "corner_braces": len(self.corner_braces),
            },
            "excluded_sources": len(self.excluded_sources),
            "auxiliary_geometry": sum(
                geometry.role == "auxiliary"
                for geometry in self.source_geometry
            ),
            "continuous_wall_geometry": sum(
                geometry.role == "continuous_wall"
                for geometry in self.source_geometry
            ),
            "centerlines": {
                "existing": method_counts["existing_centerline"],
                "computed": sum(
                    member.centerline_computed
                    for member in (
                        *self.walers,
                        *self.struts,
                        *self.braces,
                        *self.columns,
                        *self.beams,
                        *self.corner_braces,
                    )
                ),
                "failed": sum(message.code in failed_codes for message in self.messages),
            },
            "connection_status": {
                "fully_connected_struts": full_s,
                "partially_connected_struts": partial_s,
                "unconnected_struts": none_s,
                "fully_connected_braces": full_b,
                "partially_connected_braces": partial_b,
                "unconnected_braces": none_b,
            },
            "messages": {
                "info": severities["info"],
                "warning": severities["warning"],
                "error": severities["error"],
                "critical": severities["critical"],
            },
            "can_import": self.can_import,
            "double_support_groups": sum(
                candidate.is_formally_accepted
                for candidate in self.double_support_candidates
            ),
        }

    def to_project_rows(
        self,
        existing_rows: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """Return 1 mm-normalized Solver rows; keep the DXF model full precision."""

        if not self.can_import:
            codes = sorted({item.code for item in self.messages if item.severity in ERROR_SEVERITIES})
            raise DXFImportError(f"DXF 轉換含阻擋錯誤，無法匯入：{', '.join(codes)}")
        existing_rows = existing_rows or {}
        used = {
            "walers": {str(row.get("WalerID", "")) for row in existing_rows.get("walers", ())},
            "struts": {str(row.get("StrutID", "")) for row in existing_rows.get("struts", ())},
            "braces": {str(row.get("BraceID", "")) for row in existing_rows.get("braces", ())},
        }

        def allocate(table: str, prefix: str, count: int) -> list[str]:
            result: list[str] = []
            number = 1
            while len(result) < count:
                candidate = f"{prefix}{number}"
                number += 1
                if candidate not in used[table]:
                    used[table].add(candidate)
                    result.append(candidate)
            return result

        def normalize_row_coordinates(row: dict[str, Any]) -> dict[str, Any]:
            for field_name in (
                "StartX",
                "StartY",
                "EndX",
                "EndY",
                "ReferenceX",
                "ReferenceY",
            ):
                value = row.get(field_name)
                if value is not None and value != "":
                    row[field_name] = normalize_project_coordinate(value)
            return row

        waler_ids = allocate("walers", "W", len(self.walers))
        strut_ids = allocate("struts", "S", len(self.struts))
        formal_braces = tuple(
            member for member in self.braces if member.has_formal_connection
        )
        brace_ids = allocate("braces", "B", len(formal_braces))
        id_map = {old.id: new for old, new in zip(self.walers, waler_ids)}
        strut_id_map = {old.id: new for old, new in zip(self.struts, strut_ids)}
        used_group_ids = {
            str(row.get("SharedLayoutGroup", "") or "").strip()
            for row in existing_rows.get("struts", ())
            if str(row.get("SharedLayoutGroup", "") or "").strip()
        }
        next_group_number = 1

        def allocate_group_id() -> str:
            nonlocal next_group_number
            while f"G{next_group_number}" in used_group_ids:
                next_group_number += 1
            group_id = f"G{next_group_number}"
            used_group_ids.add(group_id)
            next_group_number += 1
            return group_id

        shared_group_by_strut_id: dict[str, str] = {}
        for candidate in self.double_support_candidates:
            if not candidate.is_formally_accepted:
                continue
            if (
                candidate.first_strut_id in shared_group_by_strut_id
                or candidate.second_strut_id in shared_group_by_strut_id
            ):
                continue
            group_id = allocate_group_id()
            shared_group_by_strut_id[candidate.first_strut_id] = group_id
            shared_group_by_strut_id[candidate.second_strut_id] = group_id
        canonical_connections_by_group: dict[str, tuple[str, str]] = {}
        walers = []
        for member, identifier in zip(self.walers, waler_ids):
            row = normalize_row_coordinates(member.to_project_row())
            row["WalerID"] = identifier
            walers.append(row)
        struts = []
        for member, identifier in zip(self.struts, strut_ids):
            group_id = shared_group_by_strut_id.get(member.id, "")
            reverse_to_group_direction = False
            if group_id:
                canonical = canonical_connections_by_group.setdefault(
                    group_id,
                    (member.from_waler, member.to_waler),
                )
                reverse_to_group_direction = (
                    canonical == (member.to_waler, member.from_waler)
                    and member.from_waler != member.to_waler
                )
            row = normalize_row_coordinates(
                member.to_project_row(reverse=reverse_to_group_direction)
            )
            row.update(
                StrutID=identifier,
                SharedLayoutGroup=group_id,
                FromWaler=id_map.get(row["FromWaler"], row["FromWaler"]),
                ToWaler=id_map.get(row["ToWaler"], row["ToWaler"]),
            )
            struts.append(row)
        braces = []
        for member, identifier in zip(formal_braces, brace_ids):
            row = normalize_row_coordinates(member.to_project_row())
            row.update(
                BraceID=identifier,
                FromWaler=id_map.get(member.from_waler, member.from_waler),
                ToWaler=id_map.get(member.to_waler, member.to_waler),
            )
            braces.append(row)

        def auxiliary_rows(
            members: Sequence[AuxiliaryComponent],
        ) -> list[dict[str, Any]]:
            rows = []
            for member in members:
                row = normalize_row_coordinates(member.to_project_row())
                row["AssociatedStrutID"] = strut_id_map.get(
                    member.associated_strut_id,
                    member.associated_strut_id,
                )
                if isinstance(member, Beam):
                    row["AssociatedStrutIDs"] = ",".join(
                        strut_id_map.get(strut_id, strut_id)
                        for strut_id in member.associated_strut_ids
                    )
                    row["Crossings"] = [
                        {
                            **asdict(crossing),
                            "strut_id": strut_id_map.get(
                                crossing.strut_id,
                                crossing.strut_id,
                            ),
                        }
                        for crossing in member.crossings
                    ]
                rows.append(row)
            return rows

        return {
            "walers": walers,
            "struts": struts,
            "braces": braces,
            "columns": auxiliary_rows(self.columns),
            "beams": auxiliary_rows(self.beams),
            "corner_braces": auxiliary_rows(self.corner_braces),
        }

    def to_debug_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "coordinate_system": asdict(self.coordinate_system),
            "source_path": self.source_path,
            "source_fingerprint": self.source_fingerprint,
            "layer_names": list(self.layer_names),
            "selected_layers": dict(self.selected_layers),
            "layer_classification": dict(self.layer_classification),
            "layer_assignments": [
                {
                    "layer_name": layer_name,
                    "layer_type": layer_type,
                }
                for layer_name, layer_type in self.layer_classification.items()
            ],
            "layer_info": [asdict(item) for item in self.layer_info],
            "converted": {
                "walers": [asdict(item) for item in self.walers],
                "struts": [asdict(item) for item in self.struts],
                "braces": [asdict(item) for item in self.braces],
                "columns": [asdict(item) for item in self.columns],
                "beams": [asdict(item) for item in self.beams],
                "corner_braces": [asdict(item) for item in self.corner_braces],
            },
            "validation_messages": [asdict(item) for item in self.messages],
            "component_associations": [
                asdict(item) for item in self.component_associations
            ],
            "beam_crossings": [asdict(item) for item in self.beam_crossings],
            "double_support_candidates": [
                asdict(item) for item in self.double_support_candidates
            ],
            "waler_contact_reviews": [
                asdict(item) for item in self.waler_contact_reviews
            ],
            "corner_brace_connections": [
                asdict(item) for item in self.corner_brace_connections
            ],
            "corner_brace_body_evidence": [
                asdict(item) for item in self.corner_brace_body_evidence
            ],
            "corner_brace_relationship_assessments": [
                asdict(item)
                for item in self.corner_brace_relationship_assessments
            ],
            "entities": [asdict(item) for item in self.entity_debug],
            "source_geometry": [asdict(item) for item in self.source_geometry],
            "excluded_sources": [asdict(item) for item in self.excluded_sources],
        }


def apply_coordinate_system(
    result: DXFImportResult,
    coordinate_system: CoordinateSystem,
) -> DXFImportResult:
    """Create transformed engineering models while preserving all world data."""

    def transform_member(
        member: Waler | Strut | Brace | AuxiliaryComponent,
    ) -> Waler | Strut | Brace | AuxiliaryComponent:
        world_start = member.world_start or member.start
        world_end = member.world_end or member.end
        local_start = coordinate_system.transform(world_start)
        local_end = coordinate_system.transform(world_end)
        active_start = local_start if coordinate_system.mode == "local" else world_start
        active_end = local_end if coordinate_system.mode == "local" else world_end
        candidate_points = tuple(
            replace(
                candidate,
                local_point=coordinate_system.transform(candidate.world_point),
            )
            for candidate in member.candidate_points
        )
        world_association_point = getattr(member, "world_association_point", None)
        local_association_point = (
            coordinate_system.transform(world_association_point)
            if world_association_point is not None
            else None
        )
        association_changes = (
            {
                "local_association_point": local_association_point,
                "reference_point": (
                    coordinate_system.transform(member.world_reference_point)
                    if coordinate_system.mode == "local"
                    and member.world_reference_point is not None
                    else member.world_reference_point
                ),
                "local_reference_point": (
                    coordinate_system.transform(member.world_reference_point)
                    if member.world_reference_point is not None
                    else None
                ),
            }
            if isinstance(member, AuxiliaryComponent)
            else {}
        )
        if isinstance(member, Beam):
            world_path = member.world_path or (world_start, world_end)
            local_path = tuple(
                coordinate_system.transform(point) for point in world_path
            )
            association_changes.update(
                world_path=world_path,
                local_path=local_path,
                path=(
                    local_path
                    if coordinate_system.mode == "local"
                    else world_path
                ),
                crossings=tuple(
                    replace(
                        crossing,
                        local_point=coordinate_system.transform(
                            crossing.world_point
                        ),
                        local_source_contact_point=(
                            coordinate_system.transform(
                                crossing.world_source_contact_point
                            )
                            if crossing.world_source_contact_point is not None
                            else None
                        ),
                    )
                    for crossing in member.crossings
                ),
                brace_contacts=tuple(
                    replace(
                        contact,
                        local_point=coordinate_system.transform(
                            contact.world_point
                        ),
                    )
                    for contact in member.brace_contacts
                ),
            )
        return replace(
            member,
            start=active_start,
            end=active_end,
            world_start=world_start,
            world_end=world_end,
            local_start=local_start,
            local_end=local_end,
            candidate_points=candidate_points,
            **association_changes,
        )

    component_associations = tuple(
        replace(
            association,
            local_projection_point=coordinate_system.transform(
                association.world_projection_point
            ),
        )
        for association in result.component_associations
    )
    beam_crossings = tuple(
        replace(
            crossing,
            local_point=coordinate_system.transform(crossing.world_point),
            local_source_contact_point=(
                coordinate_system.transform(crossing.world_source_contact_point)
                if crossing.world_source_contact_point is not None
                else None
            ),
        )
        for crossing in result.beam_crossings
    )

    return replace(
        result,
        walers=tuple(transform_member(member) for member in result.walers),
        struts=tuple(transform_member(member) for member in result.struts),
        braces=tuple(transform_member(member) for member in result.braces),
        columns=tuple(transform_member(member) for member in result.columns),
        beams=tuple(transform_member(member) for member in result.beams),
        corner_braces=tuple(
            transform_member(member) for member in result.corner_braces
        ),
        component_associations=component_associations,
        beam_crossings=beam_crossings,
        coordinate_system=coordinate_system,
    )
