"""Pure operation for explicitly adopting a Waler contact line."""

from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from .candidate_points import add_cad_candidate_points, apply_candidate_point_selection
from .models import (
    DXFImportError,
    DXFImportResult,
    EngineeringLineCandidate,
    GeometryTolerances,
    ValidationMessage,
    Waler,
)
from .waler_contact_adjustment import initialize_waler_contact_review


WALER_REPAIR_REPLACED_DIAGNOSTIC_CODES = frozenset(
    {
        "WALER_ENVELOPE_AMBIGUOUS",
        "WALER_ENVELOPE_UNRESOLVED",
        "WALER_CONTACT_FACE_AMBIGUOUS",
        "WALER_CONTACT_FACE_UNRESOLVED",
    }
)
WALER_REPAIR_INPUT_KINDS = frozenset(
    {"manual_candidate_points", "cad_manual"}
)


def normalized_source_identity(handles: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(handle).strip().upper()
                for handle in handles
                if str(handle).strip()
            }
        )
    )


def is_waler_engineering_line_repair_eligible(waler: Waler) -> bool:
    """Return whether an explicit formalization/replacement is allowed."""

    if not normalized_source_identity(waler.source_handles):
        return False
    return waler.contact_face_state == "provisional" or (
        waler.contact_face_state == "formal"
        and waler.engineering_line_authority == "manual_repair"
    )


def _replace_exact_waler(
    result: DXFImportResult,
    source_identity: tuple[str, ...],
    updater,
) -> DXFImportResult:
    matches = tuple(
        waler
        for waler in result.walers
        if normalized_source_identity(waler.source_handles) == source_identity
    )
    if len(matches) != 1:
        raise DXFImportError("找不到唯一且來源相符的圍令。")
    target = matches[0]
    return replace(
        result,
        walers=tuple(
            updater(waler) if waler is target else waler
            for waler in result.walers
        ),
    )


def _is_replaced_diagnostic(
    message: ValidationMessage,
    target_identity: tuple[str, ...],
) -> bool:
    return (
        message.role == "waler"
        and message.code in WALER_REPAIR_REPLACED_DIAGNOSTIC_CODES
        and normalized_source_identity(message.source_handles) == target_identity
    )


def replace_waler_engineering_line_diagnostics(
    messages: Sequence[ValidationMessage],
    source_handles: Sequence[str],
) -> tuple[ValidationMessage, ...]:
    """Remove only raw blockers superseded by one exact manual decision."""

    identity = normalized_source_identity(source_handles)
    return tuple(
        message
        for message in messages
        if not _is_replaced_diagnostic(message, identity)
    )


def formalize_waler_engineering_line(
    result: DXFImportResult,
    source_handles: Sequence[str],
    world_start: tuple[float, float],
    world_end: tuple[float, float],
    *,
    input_kind: str,
    tolerances: GeometryTolerances | None = None,
    selected_candidate_id: str = "",
) -> DXFImportResult:
    """Adopt one validated WCS line as the Waler's formal contact face.

    The operation is immutable: validation or eligibility failure raises before
    the caller replaces its live result.  The adopted line is the contact face
    itself; no envelope boundary or outer-face selection is performed.
    """

    tolerances = tolerances or GeometryTolerances()
    identity = normalized_source_identity(source_handles)
    if not identity:
        raise DXFImportError("圍令來源 identity 不得為空。")
    if input_kind not in WALER_REPAIR_INPUT_KINDS:
        raise DXFImportError("不支援的圍令人工正式化輸入方式。")

    matches = tuple(
        waler
        for waler in result.walers
        if normalized_source_identity(waler.source_handles) == identity
    )
    if len(matches) != 1 or not is_waler_engineering_line_repair_eligible(matches[0]):
        raise DXFImportError("此圍令不可採用人工正式工程線。")
    target = matches[0]

    staged, start_id, end_id = add_cad_candidate_points(
        result,
        target.id,
        world_start,
        world_end,
        tolerances,
    )

    def grant_authority(waler: Waler) -> Waler:
        changes = {
            "contact_face_state": "formal",
            "engineering_line_authority": "manual_repair",
        }
        if (
            waler.source_width_state != "unique"
            and waler.material_spec_source == "auto_width"
        ):
            changes.update(material_spec="", material_spec_source="")
        return replace(waler, **changes)

    staged = _replace_exact_waler(staged, identity, grant_authority)
    staged = apply_candidate_point_selection(
        staged,
        target.id,
        start_id,
        end_id,
        tolerances,
        selection_source=input_kind,
    )

    def record_selection(waler: Waler) -> Waler:
        changes = {}
        if input_kind == "cad_manual":
            manual_line = EngineeringLineCandidate(
                "cad_manual_line",
                "CAD 人工指定工程線",
                (float(world_start[0]), float(world_start[1])),
                (float(world_end[0]), float(world_end[1])),
                "cad_temp",
            )
            changes.update(
                line_candidates=tuple(
                    candidate
                    for candidate in waler.line_candidates
                    if candidate.id != manual_line.id
                )
                + (manual_line,),
                selected_candidate_id=manual_line.id,
            )
        elif selected_candidate_id:
            changes["selected_candidate_id"] = selected_candidate_id
        return replace(waler, **changes) if changes else waler

    staged = _replace_exact_waler(staged, identity, record_selection)
    staged = replace(
        staged,
        messages=replace_waler_engineering_line_diagnostics(
            staged.messages,
            identity,
        ),
    )
    return initialize_waler_contact_review(
        staged,
        tolerances,
        rebuild_baselines=True,
    )
