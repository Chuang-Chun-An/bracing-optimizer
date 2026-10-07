"""Pure DXF source-exclusion identity, safety and manual-input replay helpers."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
import hashlib
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .geometry import _distance
from .models import (
    Beam,
    Brace,
    CornerBrace,
    CornerBraceRepairProvenance,
    CornerBraceRepairReference,
    CornerBraceRepairSubjectKey,
    CoordinateSystem,
    DXFImportError,
    DXFImportResult,
    ExcludedSource,
    GeometryTolerances,
    ReviewItem,
    SourceManualOverride,
    Strut,
    Waler,
    apply_coordinate_system,
)


_COLLECTIONS = (
    ("waler", "walers"),
    ("strut", "struts"),
    ("brace", "braces"),
    ("column", "columns"),
    ("beam", "beams"),
    ("corner_brace", "corner_braces"),
)
_MANUAL_GEOMETRY_SOURCES = {"manual_candidate_points", "cad_manual"}


def normalize_source_handles(values: Sequence[Any] | Any) -> tuple[str, ...]:
    """Canonicalize DXF handles for identity, equality and persistence."""

    if isinstance(values, (str, bytes)):
        values = (values,)
    if not isinstance(values, Sequence):
        return ()
    return tuple(
        sorted(
            {
                str(value).strip().upper()
                for value in values
                if str(value).strip()
            }
        )
    )


def canonical_source_identity(role: Any, source_handles: Sequence[Any]) -> str:
    normalized_role = str(role or "").strip().lower()
    return f"{normalized_role}:{'|'.join(normalize_source_handles(source_handles))}"


def source_file_fingerprint(file_path: str | Path) -> str:
    """Return one SHA-256 scope for all exclusions belonging to a DXF file."""

    digest = hashlib.sha256()
    with Path(file_path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _normalized_strings(values: Any, *, upper: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        values = (values,)
    if not isinstance(values, Sequence):
        return ()
    normalized = {
        (str(value).strip().upper() if upper else str(value).strip())
        for value in values
        if str(value).strip()
    }
    return tuple(sorted(normalized))


def _point(value: Any) -> tuple[float, float] | None:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) < 2
    ):
        return None
    try:
        point = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    return point if all(math.isfinite(number) for number in point) else None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _repair_subject_key_from_mapping(
    value: Mapping[str, Any] | None,
) -> CornerBraceRepairSubjectKey | None:
    if not isinstance(value, Mapping):
        return None
    handles = normalize_source_handles(value.get("source_handles", ()))
    target_kind = str(value.get("target_kind", "") or "").strip().lower()
    base_geometry_key = str(value.get("base_geometry_key", "") or "").strip()
    if not handles or target_kind not in {"recognized", "unresolved"} or not base_geometry_key:
        return None
    return CornerBraceRepairSubjectKey(
        source_fingerprint=str(value.get("source_fingerprint", "") or ""),
        source_handles=handles,
        target_kind=target_kind,
        base_geometry_key=base_geometry_key,
    )


def _repair_reference_from_mapping(
    value: Mapping[str, Any] | None,
) -> CornerBraceRepairReference | None:
    if not isinstance(value, Mapping):
        return None
    key = _repair_subject_key_from_mapping(value.get("subject_key"))
    member_id = str(value.get("member_id", "") or "").strip()
    reference_class = str(value.get("reference_class", "") or "").strip()
    if key is None or not member_id or reference_class not in {
        "automatic_primary",
        "manual_repaired_secondary",
    }:
        return None
    return CornerBraceRepairReference(key, member_id, reference_class)


def _repair_provenance_from_mapping(
    value: Mapping[str, Any] | None,
) -> CornerBraceRepairProvenance | None:
    if not isinstance(value, Mapping):
        return None
    key = _repair_subject_key_from_mapping(value.get("subject_key"))
    start = _point(value.get("adopted_world_start"))
    end = _point(value.get("adopted_world_end"))
    primary_raw = value.get("automatic_primary_references", ())
    secondary_raw = value.get("manual_secondary_references", ())
    if (
        key is None
        or start is None
        or end is None
        or not isinstance(primary_raw, Sequence)
        or isinstance(primary_raw, (str, bytes))
        or not isinstance(secondary_raw, Sequence)
        or isinstance(secondary_raw, (str, bytes))
    ):
        return None
    primary = tuple(
        reference
        for raw in primary_raw
        if (reference := _repair_reference_from_mapping(raw)) is not None
    )
    secondary = tuple(
        reference
        for raw in secondary_raw
        if (reference := _repair_reference_from_mapping(raw)) is not None
    )
    selection_mode = str(
        value.get("selection_mode", "reference_template")
        or "reference_template"
    ).strip()
    body_signature = str(value.get("body_signature", "") or "").strip()
    if (
        len(primary) != len(primary_raw)
        or len(secondary) != len(secondary_raw)
    ):
        return None
    waler_identity = str(value.get("target_waler_identity", "") or "").strip()
    strut_identity = str(value.get("target_strut_identity", "") or "").strip()
    if not waler_identity or not strut_identity:
        return None
    template_keys = (
        "selected_template_reference",
        "transfer_mode",
        "reference_waler_offset_mm",
        "reference_strut_station_mm",
    )
    present_template_keys = tuple(key for key in template_keys if key in value)
    if len(present_template_keys) == len(template_keys) and all(
        value.get(key) is None or value.get(key) == ""
        for key in template_keys
    ):
        # ``asdict`` materializes optional dataclass fields.  Treat an
        # all-empty group as the original legacy-v2 absence, while any
        # partial/non-empty group remains fail-safe invalid below.
        present_template_keys = ()
    selected_template = None
    transfer_mode = ""
    waler_offset = None
    strut_station = None
    if selection_mode == "body_relationship_selection":
        selected_template = None
        transfer_mode = "body_relationship_selection"
        waler_offset = _optional_float(value.get("reference_waler_offset_mm"))
        strut_station = _optional_float(value.get("reference_strut_station_mm"))
        if (
            not body_signature
            or primary
            or secondary
            or waler_offset is None
            or strut_station is None
        ):
            return None
    elif present_template_keys:
        if len(present_template_keys) != len(template_keys):
            return None
        selected_template = _repair_reference_from_mapping(
            value.get("selected_template_reference")
        )
        transfer_mode = str(value.get("transfer_mode", "") or "").strip()
        waler_offset = _optional_float(value.get("reference_waler_offset_mm"))
        strut_station = _optional_float(value.get("reference_strut_station_mm"))
        if (
            selected_template is None
            or selected_template.reference_class != "automatic_primary"
            or selected_template not in primary
            or transfer_mode not in {"same_side", "mirrored"}
            or waler_offset is None
            or strut_station is None
            or waler_offset < 0.0
            or strut_station < 0.0
        ):
            return None
    elif not primary:
        return None
    return CornerBraceRepairProvenance(
        subject_key=key,
        adopted_world_start=start,
        adopted_world_end=end,
        target_waler_identity=waler_identity,
        target_strut_identity=strut_identity,
        automatic_primary_references=primary,
        manual_secondary_references=secondary,
        selected_template_reference=selected_template,
        transfer_mode=transfer_mode,
        reference_waler_offset_mm=waler_offset,
        reference_strut_station_mm=strut_station,
        preferred_display_id=str(value.get("preferred_display_id", "") or "").strip(),
        selection_source=str(
            value.get("selection_source", "corner_brace_repair")
            or "corner_brace_repair"
        ).strip(),
        evidence_signature=str(value.get("evidence_signature", "") or "").strip(),
        selection_mode=selection_mode,
        body_signature=body_signature,
    )


def manual_override_from_mapping(
    value: Mapping[str, Any] | None,
) -> SourceManualOverride | None:
    if not isinstance(value, Mapping):
        return None
    role = str(value.get("role", "") or "").strip().lower()
    handles = normalize_source_handles(value.get("source_handles", ()))
    if not role or not handles:
        return None
    selection_source = str(
        value.get("geometry_selection_source", "") or ""
    ).strip()
    coordinate_space = str(
        value.get("geometry_coordinate_space", "") or ""
    ).strip()
    if role != "brace" or coordinate_space != "baseline_wcs":
        coordinate_space = ""
    world_start = _point(value.get("world_start"))
    world_end = _point(value.get("world_end"))
    if selection_source not in _MANUAL_GEOMETRY_SOURCES:
        selection_source = ""
        coordinate_space = ""
        world_start = world_end = None
    elif world_start is None or world_end is None:
        selection_source = ""
        coordinate_space = ""
        world_start = world_end = None
    formalized = bool(
        value.get("waler_engineering_line_formalized", False)
        and role == "waler"
        and selection_source in _MANUAL_GEOMETRY_SOURCES
        and world_start is not None
        and world_end is not None
    )
    return SourceManualOverride(
        role=role,
        source_handles=handles,
        display_id=str(value.get("display_id", "") or "").strip(),
        has_material_spec=bool(value.get("has_material_spec", False)),
        material_spec=str(value.get("material_spec", "") or "").strip(),
        geometry_selection_source=selection_source,
        geometry_coordinate_space=coordinate_space,
        world_start=world_start,
        world_end=world_end,
        waler_engineering_line_formalized=formalized,
        has_waler_contact_input=bool(
            value.get("has_waler_contact_input", False)
        ),
        original_backfill_mm=_optional_float(value.get("original_backfill_mm")),
        adopted_backfill_mm=_optional_float(value.get("adopted_backfill_mm")),
        original_waler_width_mm=_optional_float(
            value.get("original_waler_width_mm")
        ),
        adopted_waler_width_mm=_optional_float(
            value.get("adopted_waler_width_mm")
        ),
        corner_brace_repair=_repair_provenance_from_mapping(
            value.get("corner_brace_repair")
        ),
    )


def excluded_source_from_mapping(
    value: Mapping[str, Any] | ExcludedSource,
) -> ExcludedSource | None:
    if isinstance(value, ExcludedSource):
        return value if value.role and value.source_handles else None
    if not isinstance(value, Mapping):
        return None
    role = str(value.get("role", "") or "").strip().lower()
    handles = normalize_source_handles(value.get("source_handles", ()))
    if not role or not handles:
        return None
    return ExcludedSource(
        role=role,
        source_handles=handles,
        source_layers=_normalized_strings(value.get("source_layers", ())),
        source_entity_types=_normalized_strings(
            value.get("source_entity_types", ()),
            upper=True,
        ),
        display_id_when_excluded=str(
            value.get("display_id_when_excluded", "") or ""
        ).strip(),
        reason=str(value.get("reason", "user_excluded") or "user_excluded"),
        manual_override=manual_override_from_mapping(value.get("manual_override")),
    )


def normalize_excluded_sources(
    values: Sequence[ExcludedSource | Mapping[str, Any]] | Any,
) -> tuple[ExcludedSource, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        return ()
    normalized: dict[str, ExcludedSource] = {}
    for value in values:
        item = excluded_source_from_mapping(value)
        if item is not None:
            normalized.setdefault(item.identity, item)
    return tuple(normalized[key] for key in sorted(normalized))


@dataclass(frozen=True)
class ExclusionRestoreDecision:
    excluded_sources: tuple[ExcludedSource, ...]
    fingerprint_mismatch: bool = False


def exclusions_from_review_state(
    state: Mapping[str, Any] | None,
    current_fingerprint: str,
) -> ExclusionRestoreDecision:
    if not isinstance(state, Mapping):
        return ExclusionRestoreDecision(())
    exclusions = normalize_excluded_sources(state.get("excluded_sources", ()))
    if not exclusions:
        return ExclusionRestoreDecision(())
    saved_fingerprint = str(state.get("source_fingerprint", "") or "").strip().upper()
    current = str(current_fingerprint or "").strip().upper()
    if not saved_fingerprint or saved_fingerprint != current:
        return ExclusionRestoreDecision((), fingerprint_mismatch=True)
    return ExclusionRestoreDecision(exclusions)


def review_state_matches_source(
    state: Mapping[str, Any] | None,
    current_fingerprint: str,
    current_path: str | Path,
) -> bool:
    """Use fingerprint when available, with the old path rule for legacy state."""

    if not isinstance(state, Mapping):
        return False
    saved_fingerprint = str(state.get("source_fingerprint", "") or "").strip().upper()
    current = str(current_fingerprint or "").strip().upper()
    if saved_fingerprint:
        return bool(current and saved_fingerprint == current)
    saved_path = str(state.get("source_path", "") or "").strip()
    if not saved_path:
        return False
    try:
        return Path(saved_path).resolve() == Path(current_path).resolve()
    except (OSError, ValueError):
        return saved_path == str(current_path)


@dataclass(frozen=True)
class SharedHandleConflict:
    handle: str
    owner_keys: tuple[str, ...]
    owner_labels: tuple[str, ...]


def shared_handle_conflicts(
    selected: ReviewItem,
    review_items: Sequence[ReviewItem],
    result: DXFImportResult | None = None,
) -> tuple[SharedHandleConflict, ...]:
    """Find other active Review objects that own any selected source handle."""

    selected_handles = set(normalize_source_handles(selected.source_handles))
    if not selected_handles:
        return ()
    owners: dict[str, dict[str, ReviewItem]] = defaultdict(dict)
    for item in review_items:
        if item.status not in {"recognized", "unresolved"}:
            continue
        for handle in normalize_source_handles(item.source_handles):
            if handle in selected_handles:
                owners[handle][item.key] = item

    beam_assemblies = {
        member.id: member.joist_assembly_key
        for member in (result.beams if result is not None else ())
        if member.joist_assembly_key
    }

    def paired_siblings(first: ReviewItem, second: ReviewItem) -> bool:
        if (
            first.status != "recognized"
            or second.status != "recognized"
            or first.role != "beam"
            or second.role != "beam"
            or first.member_id is None
            or second.member_id is None
        ):
            return False
        first_assembly = beam_assemblies.get(first.member_id, "")
        return bool(
            first_assembly
            and first_assembly == beam_assemblies.get(second.member_id, "")
        )
    conflicts = []
    for handle in sorted(selected_handles):
        others = {
            key: item for key, item in owners.get(handle, {}).items()
            if key != selected.key
            and not paired_siblings(selected, item)
        }
        if not others:
            continue
        conflicts.append(
            SharedHandleConflict(
                handle,
                tuple(sorted(others)),
                tuple(
                    sorted(
                        f"{item.display_id} ({item.role})"
                        for item in others.values()
                    )
                ),
            )
        )
    return tuple(conflicts)


def _member_role(member: Any) -> str:
    if isinstance(member, Waler):
        return "waler"
    if isinstance(member, Strut):
        return "strut"
    if isinstance(member, Brace):
        return "brace"
    if isinstance(member, Beam):
        return "beam"
    name = type(member).__name__.lower()
    return "corner_brace" if name == "cornerbrace" else "column"


def _all_members(result: DXFImportResult) -> tuple[Any, ...]:
    return tuple(
        member
        for _role, collection in _COLLECTIONS
        for member in getattr(result, collection)
    )


def _contact_input_is_manual(member: Any, review: Any) -> bool:
    if not isinstance(member, Waler) or review is None:
        return False
    if member.selection_source == "waler_contact_adjustment":
        return True
    displacement = review.contact_displacement
    return displacement is not None and abs(displacement) > 1e-9


def capture_member_manual_override(
    result: DXFImportResult,
    member: Any,
) -> SourceManualOverride | None:
    role = _member_role(member)
    handles = normalize_source_handles(member.source_handles)
    if not handles:
        return None
    has_material = bool(
        isinstance(member, (Waler, Strut))
        and member.material_spec_source == "manual"
    )
    geometry_source = (
        member.selection_source
        if member.selection_source in _MANUAL_GEOMETRY_SOURCES
        else ""
    )
    formalized = bool(
        isinstance(member, Waler)
        and member.engineering_line_authority == "manual_repair"
        and member.contact_face_state == "formal"
        and geometry_source
    )
    review = next(
        (
            item
            for item in result.waler_contact_reviews
            if isinstance(member, Waler) and item.waler_id == member.id
        ),
        None,
    )
    has_contact = _contact_input_is_manual(member, review)
    repair_provenance = (
        member.repair_provenance
        if isinstance(member, CornerBrace)
        else None
    )
    if not (
        has_material
        or geometry_source
        or formalized
        or has_contact
        or repair_provenance
    ):
        return None
    world_start = (member.world_start or member.start) if geometry_source else None
    world_end = (member.world_end or member.end) if geometry_source else None
    geometry_coordinate_space = ""
    if isinstance(member, Brace) and geometry_source:
        baseline = next(
            (
                item
                for item in result.brace_adjustment_baselines
                if item.brace_id == member.id
                and item.source_handles == normalize_source_handles(member.source_handles)
            ),
            None,
        )
        if baseline is not None:
            from .waler_contact_adjustment import (
                BraceRigidTranslationError,
                solve_brace_rigid_translation,
            )

            waler_by_id = {item.id: item for item in result.walers}
            review_by_id = {
                item.waler_id: item for item in result.waler_contact_reviews
            }
            try:
                distance_tolerance = max(
                    1e-6,
                    GeometryTolerances().beam_crossing_duplicate_tolerance_mm,
                )
                from_review = review_by_id[baseline.from_waler_id]
                to_review = review_by_id[baseline.to_waler_id]
                solved = solve_brace_rigid_translation(
                    baseline,
                    (
                        from_review.baseline_contact_start,
                        from_review.baseline_contact_end,
                    ),
                    (
                        to_review.baseline_contact_start,
                        to_review.baseline_contact_end,
                    ),
                    (
                        waler_by_id[baseline.from_waler_id].world_start,
                        waler_by_id[baseline.from_waler_id].world_end,
                    ),
                    (
                        waler_by_id[baseline.to_waler_id].world_start,
                        waler_by_id[baseline.to_waler_id].world_end,
                    ),
                )
                member_matches_baseline = (
                    _distance(solved.start, world_start) <= distance_tolerance
                    and _distance(solved.end, world_end) <= distance_tolerance
                )
                has_nonzero_displacement = any(
                    abs(review_by_id[waler_id].contact_displacement or 0.0)
                    > distance_tolerance
                    for waler_id in (
                        baseline.from_waler_id,
                        baseline.to_waler_id,
                    )
                )
            except (KeyError, BraceRigidTranslationError):
                member_matches_baseline = False
                has_nonzero_displacement = True
            if member_matches_baseline:
                world_start, world_end = baseline.start, baseline.end
                geometry_coordinate_space = "baseline_wcs"
            elif not has_nonzero_displacement:
                # Compatibility for callers that still commit a manual line
                # through the lower-level helper before any Waler adjustment.
                geometry_coordinate_space = "baseline_wcs"
    return SourceManualOverride(
        role=role,
        source_handles=handles,
        display_id=member.id,
        has_material_spec=has_material,
        material_spec=(member.material_spec if has_material else ""),
        geometry_selection_source=geometry_source,
        geometry_coordinate_space=geometry_coordinate_space,
        world_start=world_start,
        world_end=world_end,
        waler_engineering_line_formalized=formalized,
        has_waler_contact_input=has_contact,
        original_backfill_mm=(review.original_backfill_mm if has_contact else None),
        adopted_backfill_mm=(review.adopted_backfill_mm if has_contact else None),
        original_waler_width_mm=(
            review.original_waler_width_mm if has_contact else None
        ),
        adopted_waler_width_mm=(
            review.adopted_waler_width_mm if has_contact else None
        ),
        corner_brace_repair=repair_provenance,
    )


def capture_manual_overrides(
    result: DXFImportResult,
) -> tuple[SourceManualOverride, ...]:
    return tuple(
        override
        for member in _all_members(result)
        if (override := capture_member_manual_override(result, member)) is not None
    )


def excluded_source_from_review_item(
    item: ReviewItem,
    result: DXFImportResult,
) -> ExcludedSource:
    handles = normalize_source_handles(item.source_handles)
    if not item.role or not handles:
        raise DXFImportError("此項目沒有可安全識別的 DXF 來源，無法使用來源排除。")
    member = next(
        (candidate for candidate in _all_members(result) if candidate.id == item.member_id),
        None,
    )
    return ExcludedSource(
        role=item.role,
        source_handles=handles,
        source_layers=item.source_layers,
        source_entity_types=item.source_entity_types,
        display_id_when_excluded=item.display_id,
        reason="user_excluded",
        manual_override=(
            capture_member_manual_override(result, member)
            if member is not None
            else None
        ),
    )


def _manual_override_from_saved_member(
    role: str,
    raw: Mapping[str, Any],
    waler_review: Mapping[str, Any] | None,
) -> SourceManualOverride | None:
    handles = normalize_source_handles(raw.get("source_handles", ()))
    if not handles:
        return None
    selection_source = str(raw.get("selection_source", "") or "").strip()
    geometry_source = (
        selection_source if selection_source in _MANUAL_GEOMETRY_SOURCES else ""
    )
    world_start = _point(raw.get("world_start")) if geometry_source else None
    world_end = _point(raw.get("world_end")) if geometry_source else None
    if world_start is None or world_end is None:
        geometry_source = ""
        world_start = world_end = None
    has_material = bool(
        role in {"waler", "strut"}
        and str(raw.get("material_spec_source", "") or "") == "manual"
    )
    has_contact = False
    contact_values: dict[str, float | None] = {}
    if role == "waler" and isinstance(waler_review, Mapping):
        contact_values = {
            key: _optional_float(waler_review.get(key))
            for key in (
                "original_backfill_mm",
                "adopted_backfill_mm",
                "original_waler_width_mm",
                "adopted_waler_width_mm",
            )
        }
        values = tuple(contact_values.values())
        displacement = None
        if all(value is not None for value in values):
            displacement = (
                contact_values["adopted_backfill_mm"]
                - contact_values["original_backfill_mm"]
                + contact_values["adopted_waler_width_mm"]
                - contact_values["original_waler_width_mm"]
            )
        has_contact = bool(
            selection_source == "waler_contact_adjustment"
            or (displacement is not None and abs(displacement) > 1e-9)
        )
    repair_provenance = (
        _repair_provenance_from_mapping(raw.get("repair_provenance"))
        if role == "corner_brace"
        else None
    )
    if not (has_material or geometry_source or has_contact or repair_provenance):
        return None
    return SourceManualOverride(
        role=role,
        source_handles=handles,
        display_id=str(raw.get("id", "") or ""),
        has_material_spec=has_material,
        material_spec=str(raw.get("material_spec", "") or "").strip(),
        geometry_selection_source=geometry_source,
        world_start=world_start,
        world_end=world_end,
        has_waler_contact_input=has_contact,
        corner_brace_repair=repair_provenance,
        **contact_values,
    )


def manual_overrides_from_review_state(
    state: Mapping[str, Any] | None,
) -> tuple[SourceManualOverride, ...]:
    if not isinstance(state, Mapping):
        return ()
    if "manual_overrides" in state:
        raw_overrides = state.get("manual_overrides", ())
        if not isinstance(raw_overrides, Sequence) or isinstance(
            raw_overrides,
            (str, bytes),
        ):
            return ()
        return tuple(
            override
            for raw in raw_overrides
            if (override := manual_override_from_mapping(raw)) is not None
        )
    converted = state.get("converted")
    if not isinstance(converted, Mapping):
        return ()
    raw_reviews = state.get("waler_contact_reviews", ())
    review_by_id = {
        str(review.get("waler_id", "") or ""): review
        for review in raw_reviews
        if isinstance(review, Mapping)
    } if isinstance(raw_reviews, Sequence) and not isinstance(raw_reviews, (str, bytes)) else {}
    overrides = []
    for role, collection in _COLLECTIONS:
        raw_members = converted.get(collection, ())
        if not isinstance(raw_members, Sequence) or isinstance(raw_members, (str, bytes)):
            continue
        for raw in raw_members:
            if not isinstance(raw, Mapping):
                continue
            override = _manual_override_from_saved_member(
                role,
                raw,
                review_by_id.get(str(raw.get("id", "") or "")),
            )
            if override is not None:
                overrides.append(override)
    return tuple(overrides)


@dataclass(frozen=True)
class ManualReplayReport:
    preserved: tuple[str, ...] = ()
    needs_review: tuple[str, ...] = ()
    disabled: tuple[str, ...] = ()


def _override_labels(override: SourceManualOverride) -> tuple[str, ...]:
    display = override.display_id or canonical_source_identity(
        override.role, override.source_handles
    )
    labels = []
    if override.has_material_spec:
        labels.append(f"{display} 材料規格")
    if override.geometry_selection_source:
        if override.waler_engineering_line_formalized:
            label = "人工正式工程線"
        else:
            label = "CAD 工程線" if override.geometry_selection_source == "cad_manual" else "STEP5 工程線"
        labels.append(f"{display} {label}")
    if override.has_waler_contact_input:
        labels.append(f"{display} Waler 背填／寬度")
    if override.corner_brace_repair is not None:
        labels.append(f"{display} CornerBrace repair")
    return tuple(labels)


def manual_override_labels(
    override: SourceManualOverride,
) -> tuple[str, ...]:
    """Expose the stable per-input labels used by replay reports."""

    return _override_labels(override)


def _unique_member_for_override(
    result: DXFImportResult,
    override: SourceManualOverride,
) -> Any | None:
    matches = [
        member
        for member in _all_members(result)
        if _member_role(member) == override.role
        and normalize_source_handles(member.source_handles) == override.source_handles
    ]
    return matches[0] if len(matches) == 1 else None


def replay_manual_overrides(
    result: DXFImportResult,
    overrides: Sequence[SourceManualOverride],
    *,
    material_specs: Sequence[Mapping[str, Any]] = (),
    tolerances: GeometryTolerances | None = None,
    review_confirmations: Mapping[str, str] | None = None,
    confirmation_coordinate_system: CoordinateSystem | None = None,
) -> tuple[DXFImportResult, ManualReplayReport]:
    """Replay only explicit inputs; every relationship remains newly derived."""

    from .candidate_points import (
        add_cad_candidate_points,
        apply_candidate_point_selection,
        set_cad_engineering_line,
    )
    from .material_recognition import material_spec_options, set_member_material_spec
    from .waler_contact_adjustment import (
        apply_waler_contact_adjustment,
        initialize_waler_contact_review,
    )
    from .waler_engineering_line_repair import (
        formalize_waler_engineering_line,
    )

    tolerances = tolerances or GeometryTolerances()
    excluded_identities = {source.identity for source in result.excluded_sources}
    grouped: dict[str, list[SourceManualOverride]] = defaultdict(list)
    repair_overrides = tuple(
        override for override in overrides
        if override.corner_brace_repair is not None
    )
    for override in overrides:
        if override.corner_brace_repair is not None:
            continue
        grouped[
            canonical_source_identity(override.role, override.source_handles)
        ].append(override)
    usable = []
    preserved: list[str] = []
    needs_review: list[str] = []
    disabled: list[str] = []
    for identity, candidates in grouped.items():
        labels = tuple(label for item in candidates for label in _override_labels(item))
        if identity in excluded_identities:
            disabled.extend(labels)
        elif len(candidates) != 1:
            needs_review.extend(labels)
        else:
            usable.append(candidates[0])

    current = result

    nonzero_adjusted_waler_ids: set[str] = set()
    for candidate in usable:
        if not candidate.has_waler_contact_input:
            continue
        member = _unique_member_for_override(current, candidate)
        values = (
            candidate.original_backfill_mm,
            candidate.adopted_backfill_mm,
            candidate.original_waler_width_mm,
            candidate.adopted_waler_width_mm,
        )
        if not isinstance(member, Waler) or any(value is None for value in values):
            continue
        try:
            displacement = (
                float(candidate.adopted_backfill_mm)
                - float(candidate.original_backfill_mm)
                + float(candidate.adopted_waler_width_mm)
                - float(candidate.original_waler_width_mm)
            )
        except (TypeError, ValueError):
            continue
        if abs(displacement) > max(
            1e-6,
            tolerances.beam_crossing_duplicate_tolerance_mm,
        ):
            nonzero_adjusted_waler_ids.add(member.id)

    def replay_geometry(override: SourceManualOverride) -> None:
        nonlocal current
        if not override.geometry_selection_source:
            return
        member = _unique_member_for_override(current, override)
        label = _override_labels(override)[
            1 if override.has_material_spec else 0
        ]
        if member is None or override.world_start is None or override.world_end is None:
            needs_review.append(label)
            return
        if (
            isinstance(member, Brace)
            and override.geometry_coordinate_space != "baseline_wcs"
            and bool(
                {member.from_waler, member.to_waler}
                & nonzero_adjusted_waler_ids
            )
        ):
            needs_review.append(label)
            return
        try:
            if override.waler_engineering_line_formalized:
                staged = formalize_waler_engineering_line(
                    current,
                    override.source_handles,
                    override.world_start,
                    override.world_end,
                    input_kind=override.geometry_selection_source,
                    tolerances=tolerances,
                )
            elif override.geometry_selection_source == "cad_manual":
                staged = set_cad_engineering_line(
                    current,
                    member.id,
                    override.world_start,
                    override.world_end,
                    tolerances,
                )
            else:
                staged, start_id, end_id = add_cad_candidate_points(
                    current,
                    member.id,
                    override.world_start,
                    override.world_end,
                    tolerances,
                )
                staged = apply_candidate_point_selection(
                    staged,
                    member.id,
                    start_id,
                    end_id,
                    tolerances,
                    selection_source="manual_candidate_points",
                )
        except (DXFImportError, ValueError):
            needs_review.append(label)
            return
        current = staged
        preserved.append(label)

    # All manual geometry is replayed in baseline WCS before any dimension input.
    waler_geometry = [
        item for item in usable
        if item.role == "waler" and item.geometry_selection_source
    ]
    for override in waler_geometry:
        replay_geometry(override)

    for override in usable:
        if override.role != "waler":
            replay_geometry(override)

    if any(item.geometry_selection_source for item in usable):
        current = initialize_waler_contact_review(
            current,
            tolerances,
            rebuild_baselines=True,
        )

    for override in usable:
        if not override.has_waler_contact_input:
            continue
        member = _unique_member_for_override(current, override)
        label = next(
            text for text in _override_labels(override)
            if text.endswith("Waler 背填／寬度")
        )
        values = (
            override.original_backfill_mm,
            override.adopted_backfill_mm,
            override.original_waler_width_mm,
            override.adopted_waler_width_mm,
        )
        if not isinstance(member, Waler) or any(value is None for value in values):
            needs_review.append(label)
            continue
        try:
            staged = apply_waler_contact_adjustment(
                current,
                member.id,
                original_backfill_mm=override.original_backfill_mm,
                adopted_backfill_mm=override.adopted_backfill_mm,
                original_waler_width_mm=override.original_waler_width_mm,
                adopted_waler_width_mm=override.adopted_waler_width_mm,
                tolerances=tolerances,
            )
        except (DXFImportError, ValueError):
            needs_review.append(label)
            continue
        current = staged
        preserved.append(label)

    for override in usable:
        if not override.has_material_spec:
            continue
        member = _unique_member_for_override(current, override)
        label = _override_labels(override)[0]
        if not isinstance(member, (Waler, Strut)):
            needs_review.append(label)
            continue
        usage = "圍令" if isinstance(member, Waler) else "支撐"
        allowed = {
            value.casefold()
            for value in material_spec_options(material_specs, usage)
        }
        if (
            override.material_spec
            and allowed
            and override.material_spec.casefold() not in allowed
        ):
            needs_review.append(label)
            continue
        try:
            current = set_member_material_spec(
                current,
                member.id,
                override.material_spec,
            )
        except (DXFImportError, ValueError):
            needs_review.append(label)
            continue
        preserved.append(label)

    if repair_overrides:
        from .corner_brace_repair import (
            apply_corner_brace_repair,
            plan_corner_brace_repair,
            reconstruct_legacy_adopted_candidate,
            reconstruct_saved_template_candidate,
            repair_subject_key,
        )
        from .validation import build_problem_records, build_review_items

        pending = list(repair_overrides)
        coordinate_system = confirmation_coordinate_system or CoordinateSystem()
        while pending:
            made_progress = False
            deferred: list[SourceManualOverride] = []
            for override in pending:
                provenance = override.corner_brace_repair
                assert provenance is not None
                label = next(
                    text for text in _override_labels(override)
                    if text.endswith("CornerBrace repair")
                )
                projected = apply_coordinate_system(current, coordinate_system)
                records = build_problem_records(projected)
                items = build_review_items(projected, records)
                targets = []
                for item in items:
                    if item.role != "corner_brace":
                        continue
                    try:
                        key = repair_subject_key(current, item, tolerances)
                    except DXFImportError:
                        continue
                    if key == provenance.subject_key:
                        targets.append(item)
                if len(targets) != 1:
                    needs_review.append(label)
                    continue
                target = targets[0]
                if (
                    provenance.subject_key.target_kind == "unresolved"
                    and provenance.preferred_display_id
                    and any(
                        corner.id == provenance.preferred_display_id
                        and normalize_source_handles(corner.source_handles)
                        != provenance.subject_key.source_handles
                        for corner in current.corner_braces
                    )
                ):
                    needs_review.append(label)
                    continue
                plan = plan_corner_brace_repair(
                    current,
                    target,
                    base_revision=0,
                    review_items=items,
                    confirmations=review_confirmations,
                    confirmation_result=projected,
                    tolerances=tolerances,
                )
                if provenance.selection_mode == "body_relationship_selection":
                    matches = [
                        candidate
                        for candidate in plan.candidates
                        if candidate.selection_mode
                        == "body_relationship_selection"
                        and candidate.body_signature == provenance.body_signature
                        and canonical_source_identity(
                            "waler",
                            next(
                                waler.source_handles
                                for waler in current.walers
                                if waler.id == candidate.target_waler_id
                            ),
                        )
                        == provenance.target_waler_identity
                        and canonical_source_identity(
                            "strut",
                            next(
                                strut.source_handles
                                for strut in current.struts
                                if strut.id == candidate.target_strut_id
                            ),
                        )
                        == provenance.target_strut_identity
                        and _distance(
                            candidate.world_start,
                            provenance.adopted_world_start,
                        )
                        <= tolerances.endpoint_tolerance_mm
                        and _distance(
                            candidate.world_end,
                            provenance.adopted_world_end,
                        )
                        <= tolerances.endpoint_tolerance_mm
                    ]
                elif provenance.selected_template_reference is not None:
                    rebuilt = reconstruct_saved_template_candidate(
                        current,
                        target,
                        provenance,
                        review_items=items,
                        confirmations=review_confirmations,
                        confirmation_result=projected,
                        tolerances=tolerances,
                    )
                    matches = (
                        [rebuilt]
                        if rebuilt is not None
                        and _distance(rebuilt.world_start, provenance.adopted_world_start)
                        <= tolerances.endpoint_tolerance_mm
                        and _distance(rebuilt.world_end, provenance.adopted_world_end)
                        <= tolerances.endpoint_tolerance_mm
                        else []
                    )
                else:
                    # Legacy version-2 payloads keep their adopted world line
                    # contract.  They are validated against saved identities
                    # and references without opting into template ranking.
                    rebuilt = reconstruct_legacy_adopted_candidate(
                        current,
                        target,
                        provenance,
                        review_items=items,
                        confirmations=review_confirmations,
                        confirmation_result=projected,
                        tolerances=tolerances,
                    )
                    matches = [rebuilt] if rebuilt is not None else []
                if len(matches) != 1:
                    # A secondary repair may not have been replayed yet.  Give
                    # the dependency one deterministic later pass, but never
                    # substitute another reference.
                    if provenance.manual_secondary_references:
                        deferred.append(override)
                    else:
                        needs_review.append(label)
                    continue
                replay_plan = replace(
                    plan,
                    preferred_display_id=provenance.preferred_display_id,
                    candidates=tuple(matches),
                )
                try:
                    replayed_current, repaired_id = apply_corner_brace_repair(
                        current,
                        target,
                        replay_plan,
                        matches[0].id,
                        explicit_adoption=True,
                        tolerances=tolerances,
                    )
                except (DXFImportError, ValueError):
                    needs_review.append(label)
                    continue
                if (
                    provenance.selected_template_reference is None
                    and provenance.selection_mode
                    != "body_relationship_selection"
                ):
                    replayed_provenance = replace(
                        provenance,
                        automatic_primary_references=matches[0].primary_references,
                        manual_secondary_references=matches[0].secondary_references,
                    )
                    replayed_current = replace(
                        replayed_current,
                        corner_braces=tuple(
                            replace(corner, repair_provenance=replayed_provenance)
                            if corner.id == repaired_id
                            else corner
                            for corner in replayed_current.corner_braces
                        ),
                    )
                if (
                    provenance.preferred_display_id
                    and repaired_id != provenance.preferred_display_id
                ):
                    needs_review.append(label)
                    continue
                current = replayed_current
                preserved.append(label)
                made_progress = True
            if not deferred:
                break
            if not made_progress:
                for override in deferred:
                    label = next(
                        text for text in _override_labels(override)
                        if text.endswith("CornerBrace repair")
                    )
                    needs_review.append(label)
                break
            pending = deferred

    def unique(values: Sequence[str]) -> tuple[str, ...]:
        return tuple(dict.fromkeys(values))

    return current, ManualReplayReport(
        preserved=unique(preserved),
        needs_review=unique(needs_review),
        disabled=unique(disabled),
    )


def result_member_counts(result: DXFImportResult) -> Mapping[str, int]:
    return {role: len(getattr(result, collection)) for role, collection in _COLLECTIONS}


def result_severity_counts(result: DXFImportResult) -> Mapping[str, int]:
    return Counter(message.severity for message in result.messages)


__all__ = [
    "ExclusionRestoreDecision",
    "ManualReplayReport",
    "SharedHandleConflict",
    "canonical_source_identity",
    "capture_manual_overrides",
    "excluded_source_from_mapping",
    "excluded_source_from_review_item",
    "exclusions_from_review_state",
    "manual_overrides_from_review_state",
    "manual_override_labels",
    "normalize_excluded_sources",
    "normalize_source_handles",
    "replay_manual_overrides",
    "result_member_counts",
    "result_severity_counts",
    "review_state_matches_source",
    "shared_handle_conflicts",
    "source_file_fingerprint",
]
