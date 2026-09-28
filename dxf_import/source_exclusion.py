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
    if (
        not primary
        or len(primary) != len(primary_raw)
        or len(secondary) != len(secondary_raw)
    ):
        return None
    waler_identity = str(value.get("target_waler_identity", "") or "").strip()
    strut_identity = str(value.get("target_strut_identity", "") or "").strip()
    if not waler_identity or not strut_identity:
        return None
    return CornerBraceRepairProvenance(
        subject_key=key,
        adopted_world_start=start,
        adopted_world_end=end,
        target_waler_identity=waler_identity,
        target_strut_identity=strut_identity,
        automatic_primary_references=primary,
        manual_secondary_references=secondary,
        preferred_display_id=str(value.get("preferred_display_id", "") or "").strip(),
        selection_source=str(
            value.get("selection_source", "corner_brace_repair")
            or "corner_brace_repair"
        ).strip(),
        evidence_signature=str(value.get("evidence_signature", "") or "").strip(),
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
    world_start = _point(value.get("world_start"))
    world_end = _point(value.get("world_end"))
    if selection_source not in _MANUAL_GEOMETRY_SOURCES:
        selection_source = ""
        world_start = world_end = None
    elif world_start is None or world_end is None:
        selection_source = ""
        world_start = world_end = None
    return SourceManualOverride(
        role=role,
        source_handles=handles,
        display_id=str(value.get("display_id", "") or "").strip(),
        has_material_spec=bool(value.get("has_material_spec", False)),
        material_spec=str(value.get("material_spec", "") or "").strip(),
        geometry_selection_source=selection_source,
        world_start=world_start,
        world_end=world_end,
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
    if not (has_material or geometry_source or has_contact or repair_provenance):
        return None
    return SourceManualOverride(
        role=role,
        source_handles=handles,
        display_id=member.id,
        has_material_spec=has_material,
        material_spec=(member.material_spec if has_material else ""),
        geometry_selection_source=geometry_source,
        world_start=(member.world_start or member.start) if geometry_source else None,
        world_end=(member.world_end or member.end) if geometry_source else None,
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
        try:
            if override.geometry_selection_source == "cad_manual":
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

    # A manually chosen Waler line defines the baseline used by contact inputs.
    waler_geometry = [
        item for item in usable
        if item.role == "waler" and item.geometry_selection_source
    ]
    for override in waler_geometry:
        replay_geometry(override)
    if waler_geometry:
        current = initialize_waler_contact_review(current, tolerances)

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
        if override.role != "waler":
            replay_geometry(override)

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
                saved_primary = {
                    reference.subject_key
                    for reference in provenance.automatic_primary_references
                }
                saved_secondary = {
                    reference.subject_key
                    for reference in provenance.manual_secondary_references
                }
                matches = []
                for candidate in plan.candidates:
                    waler = next(
                        (member for member in current.walers if member.id == candidate.target_waler_id),
                        None,
                    )
                    strut = next(
                        (member for member in current.struts if member.id == candidate.target_strut_id),
                        None,
                    )
                    if waler is None or strut is None:
                        continue
                    if (
                        canonical_source_identity("waler", waler.source_handles)
                        != provenance.target_waler_identity
                        or canonical_source_identity("strut", strut.source_handles)
                        != provenance.target_strut_identity
                    ):
                        continue
                    if (
                        _distance(candidate.world_start, provenance.adopted_world_start)
                        > tolerances.endpoint_tolerance_mm
                        or _distance(candidate.world_end, provenance.adopted_world_end)
                        > tolerances.endpoint_tolerance_mm
                    ):
                        continue
                    candidate_primary = {
                        reference.subject_key for reference in candidate.primary_references
                    }
                    candidate_secondary = {
                        reference.subject_key for reference in candidate.secondary_references
                    }
                    if not saved_primary or not saved_primary.issubset(candidate_primary):
                        continue
                    if not saved_secondary.issubset(candidate_secondary):
                        continue
                    matches.append(candidate)
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
