"""Detect reviewable double-support relationships after Strut recognition."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Sequence

from .geometry import (
    _angle_difference_deg,
    _length,
    _line_distance,
    _midpoint,
    _projection_overlap_ratio,
)
from .models import DoubleSupportCandidate, GeometryTolerances, Strut


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


__all__ = [
    "detect_double_support_candidates",
    "set_double_support_candidate_accepted",
]
