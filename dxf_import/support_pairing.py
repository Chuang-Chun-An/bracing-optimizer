"""Detect reviewable double-support relationships after Strut recognition."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any, Mapping, Sequence

from .geometry import (
    _angle_difference_deg,
    _length,
    _line_distance,
    _midpoint,
    _projection_overlap_ratio,
)
from .models import (
    DXFImportResult,
    DoubleSupportCandidate,
    GeometryTolerances,
    Strut,
)


DoubleSupportSourceIdentity = tuple[tuple[str, ...], tuple[str, ...]]


def _strut_source_identity(strut: Strut) -> tuple[str, ...] | None:
    handles = tuple(
        sorted(
            {
                str(handle).strip().upper()
                for handle in strut.source_handles
                if str(handle).strip()
            }
        )
    )
    return handles or None


def double_support_candidate_identity(
    result: DXFImportResult,
    candidate: DoubleSupportCandidate,
) -> DoubleSupportSourceIdentity | None:
    """Identify a physical pair by both Struts' normalized DXF handles."""

    strut_by_id = {strut.id: strut for strut in result.struts}
    first = strut_by_id.get(candidate.first_strut_id)
    second = strut_by_id.get(candidate.second_strut_id)
    if first is None or second is None:
        return None
    first_identity = _strut_source_identity(first)
    second_identity = _strut_source_identity(second)
    if first_identity is None or second_identity is None:
        return None
    return tuple(sorted((first_identity, second_identity)))


def double_support_decisions_from_review_state(
    state: Mapping[str, Any] | None,
) -> dict[DoubleSupportSourceIdentity, bool]:
    """Read only explicit accepted/rejected decisions from review JSON."""

    if not isinstance(state, Mapping):
        return {}
    raw_items = state.get("double_support_decisions", ())
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        return {}
    decisions: dict[DoubleSupportSourceIdentity, bool] = {}
    conflicts: set[DoubleSupportSourceIdentity] = set()
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            continue
        first = _normalized_handle_identity(raw.get("first_source_handles", ()))
        second = _normalized_handle_identity(raw.get("second_source_handles", ()))
        if first is None or second is None:
            continue
        identity = tuple(sorted((first, second)))
        accepted = bool(raw.get("accepted", False))
        if identity in decisions and decisions[identity] != accepted:
            conflicts.add(identity)
        else:
            decisions[identity] = accepted
    for identity in conflicts:
        decisions.pop(identity, None)
    return decisions


def _normalized_handle_identity(values: Any) -> tuple[str, ...] | None:
    if isinstance(values, (str, bytes)):
        values = (values,)
    if not isinstance(values, Sequence):
        return None
    handles = tuple(
        sorted(
            {
                str(value).strip().upper()
                for value in values
                if str(value).strip()
            }
        )
    )
    return handles or None


def serialize_double_support_decisions(
    decisions: Mapping[DoubleSupportSourceIdentity, bool],
) -> list[dict[str, Any]]:
    """Return deterministic JSON for explicit double-support decisions."""

    return [
        {
            "first_source_handles": list(identity[0]),
            "second_source_handles": list(identity[1]),
            "accepted": bool(accepted),
        }
        for identity, accepted in sorted(decisions.items())
    ]


def apply_double_support_decisions(
    result: DXFImportResult,
    decisions: Mapping[DoubleSupportSourceIdentity, bool],
) -> tuple[DoubleSupportCandidate, ...]:
    """Replay saved pair decisions onto newly detected candidates."""

    candidate_by_identity = {
        identity: candidate
        for candidate in result.double_support_candidates
        if (identity := double_support_candidate_identity(result, candidate))
        is not None
    }
    updated = tuple(result.double_support_candidates)
    # Reject first, then accept through the existing one-to-one rule.
    for accepted in (False, True):
        for identity, decision in sorted(decisions.items()):
            candidate = candidate_by_identity.get(identity)
            if candidate is None or decision != accepted:
                continue
            updated = set_double_support_candidate_accepted(
                updated,
                candidate.id,
                accepted,
            )
    return updated


def detect_double_support_candidates(
    struts: Sequence[Strut],
    tolerances: GeometryTolerances | None = None,
) -> tuple[DoubleSupportCandidate, ...]:
    """Return deterministic, one-click-review candidates near the 1000 mm rule.

    Individual Struts remain independent DXF components.  This pass only
    infers their relationship after endpoints and Waler connections are known.
    """

    tolerances = tolerances or GeometryTolerances()
    raw: list[DoubleSupportCandidate] = []
    for first_index, first in enumerate(struts):
        first_line = (
            first.world_start or first.start,
            first.world_end or first.end,
        )
        first_length = _length(*first_line)
        if first_length <= 0 or not first.from_waler or not first.to_waler:
            continue
        for second in struts[first_index + 1 :]:
            if not second.from_waler or not second.to_waler:
                continue
            if {first.from_waler, first.to_waler} != {
                second.from_waler,
                second.to_waler,
            }:
                continue
            second_line = (
                second.world_start or second.start,
                second.world_end or second.end,
            )
            second_length = _length(*second_line)
            if second_length <= 0:
                continue
            angle_difference = _angle_difference_deg(first_line, second_line)
            if angle_difference > tolerances.parallel_angle_tolerance_deg:
                continue
            spacing = (
                _line_distance(_midpoint(*second_line), *first_line)
                + _line_distance(_midpoint(*first_line), *second_line)
            ) / 2
            spacing_delta = abs(
                spacing - tolerances.double_support_spacing_mm
            )
            if spacing_delta > tolerances.double_support_spacing_tolerance_mm:
                continue
            overlap_ratio = _projection_overlap_ratio(first_line, second_line)
            if overlap_ratio < tolerances.double_support_overlap_ratio:
                continue
            length_difference = abs(first_length - second_length)
            if length_difference > tolerances.double_support_length_tolerance_mm:
                continue

            spacing_score = 1.0 - (
                spacing_delta
                / max(tolerances.double_support_spacing_tolerance_mm, 1e-9)
            )
            angle_score = 1.0 - (
                angle_difference
                / max(tolerances.parallel_angle_tolerance_deg, 1e-9)
            )
            overlap_score = (
                overlap_ratio - tolerances.double_support_overlap_ratio
            ) / max(1.0 - tolerances.double_support_overlap_ratio, 1e-9)
            length_score = 1.0 - (
                length_difference
                / max(tolerances.double_support_length_tolerance_mm, 1e-9)
            )
            confidence = max(
                0.0,
                min(
                    1.0,
                    0.45 * spacing_score
                    + 0.20 * angle_score
                    + 0.20 * overlap_score
                    + 0.15 * length_score,
                ),
            )
            raw.append(DoubleSupportCandidate(
                id="",
                first_strut_id=first.id,
                second_strut_id=second.id,
                centerline_spacing=spacing,
                angle_difference_deg=angle_difference,
                overlap_ratio=overlap_ratio,
                length_difference=length_difference,
                confidence=confidence,
            ))

    raw.sort(
        key=lambda candidate: (
            candidate.first_strut_id,
            candidate.second_strut_id,
        )
    )
    occurrences = Counter(
        member_id
        for candidate in raw
        for member_id in (
            candidate.first_strut_id,
            candidate.second_strut_id,
        )
    )
    results = []
    for index, candidate in enumerate(raw, start=1):
        ambiguous = any(
            occurrences[member_id] > 1
            for member_id in (
                candidate.first_strut_id,
                candidate.second_strut_id,
            )
        )
        results.append(replace(
            candidate,
            id=f"DG{index}",
            accepted=not ambiguous,
            ambiguous=ambiguous,
            warnings=(
                ("同一支撐存在多個可能配對，必須人工選擇。",)
                if ambiguous
                else ()
            ),
        ))
    return tuple(results)


def set_double_support_candidate_accepted(
    candidates: Sequence[DoubleSupportCandidate],
    candidate_id: str,
    accepted: bool,
) -> tuple[DoubleSupportCandidate, ...]:
    """Accept one candidate while preserving one-to-one membership."""

    target = next(
        (candidate for candidate in candidates if candidate.id == candidate_id),
        None,
    )
    if target is None:
        return tuple(candidates)
    occupied = {target.first_strut_id, target.second_strut_id}
    updated = []
    for candidate in candidates:
        shares_member = bool(occupied.intersection({
            candidate.first_strut_id,
            candidate.second_strut_id,
        }))
        if candidate.id == candidate_id:
            updated.append(replace(candidate, accepted=bool(accepted)))
        elif accepted and shares_member:
            updated.append(replace(candidate, accepted=False))
        else:
            updated.append(candidate)
    return tuple(updated)


def preserve_double_support_decisions(
    previous: Sequence[DoubleSupportCandidate],
    detected: Sequence[DoubleSupportCandidate],
) -> tuple[DoubleSupportCandidate, ...]:
    """Carry accepted/rejected review decisions across a geometry rebuild.

    This helper is for an in-place geometry rebuild where the recognized
    Strut identities remain stable.  A pair that no longer passes detection
    is not kept; a newly detected pair retains the detector's default state.
    """

    accepted_by_pair = {
        frozenset((item.first_strut_id, item.second_strut_id)): item.accepted
        for item in previous
    }
    return tuple(
        replace(
            item,
            accepted=accepted_by_pair.get(
                frozenset((item.first_strut_id, item.second_strut_id)),
                item.accepted,
            ),
        )
        for item in detected
    )


def preserve_double_support_result_decisions(
    previous: DXFImportResult,
    detected: DXFImportResult,
) -> tuple[DoubleSupportCandidate, ...]:
    """Carry review decisions across re-recognition by DXF source identity.

    Source exclusion may renumber S1/S2-style IDs.  Matching the normalized
    source-handle sets of both members prevents an old decision from being
    applied to a different physical pair that happens to reuse those IDs.
    """

    decisions: dict[tuple[tuple[str, ...], tuple[str, ...]], bool] = {}
    conflicting_identities: set[
        tuple[tuple[str, ...], tuple[str, ...]]
    ] = set()
    for candidate in previous.double_support_candidates:
        identity = double_support_candidate_identity(previous, candidate)
        if identity is None:
            continue
        if identity in decisions and decisions[identity] != candidate.accepted:
            conflicting_identities.add(identity)
        else:
            decisions[identity] = candidate.accepted
    for identity in conflicting_identities:
        decisions.pop(identity, None)

    return tuple(
        replace(
            candidate,
            accepted=decisions.get(identity, candidate.accepted),
        )
        if (
            identity := double_support_candidate_identity(detected, candidate)
        ) is not None
        else candidate
        for candidate in detected.double_support_candidates
    )


__all__ = [
    "DoubleSupportSourceIdentity",
    "apply_double_support_decisions",
    "detect_double_support_candidates",
    "double_support_candidate_identity",
    "double_support_decisions_from_review_state",
    "preserve_double_support_decisions",
    "preserve_double_support_result_decisions",
    "serialize_double_support_decisions",
    "set_double_support_candidate_accepted",
]
