"""Data-only planning for changed-content paused DXF Review recovery.

This module deliberately has no Tkinter dependency.  It owns the transient
recovery contract and, in later stages, the candidate-based matching/replay
orchestration.  A recovery object is never durable Project truth by itself.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .models import SourceManualOverride
from .source_exclusion import (
    canonical_source_identity,
    manual_override_labels,
    normalize_source_handles,
)


CRITICAL_MEMBER_ROLES = ("waler", "strut", "brace")
_ROLE_COLLECTIONS = {
    "waler": "walers",
    "strut": "struts",
    "brace": "braces",
}
class RecoveryCategory(str, Enum):
    PRESERVED = "preserved"
    REQUIRES_REVIEW = "requires_review"
    DISABLED = "disabled"


class ReviewRecoveryStatus(str, Enum):
    COMPATIBLE_RECOVERY_AVAILABLE = "COMPATIBLE_RECOVERY_AVAILABLE"
    INCOMPATIBLE_SOURCE = "INCOMPATIBLE_SOURCE"
    VALIDATION_FAILED = "VALIDATION_FAILED"


@dataclass(frozen=True)
class RecoverySummaryEntry:
    category: RecoveryCategory
    subject_kind: str
    label: str
    reason_code: str
    description: str

    def __post_init__(self) -> None:
        category = self.category
        if not isinstance(category, RecoveryCategory):
            category = RecoveryCategory(str(category).strip().lower())
            object.__setattr__(self, "category", category)
        for field_name in ("subject_kind", "label", "reason_code", "description"):
            value = str(getattr(self, field_name, "") or "").strip()
            if not value:
                raise ValueError(f"Recovery summary {field_name} 不得為空。")
            object.__setattr__(self, field_name, value)


@dataclass(frozen=True)
class RecoverySummary:
    entries: tuple[RecoverySummaryEntry, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))

    @property
    def counts(self) -> Mapping[RecoveryCategory, int]:
        values = {category: 0 for category in RecoveryCategory}
        for entry in self.entries:
            values[entry.category] += 1
        return MappingProxyType(values)

    def entries_for(
        self,
        category: RecoveryCategory | str,
    ) -> tuple[RecoverySummaryEntry, ...]:
        normalized = (
            category
            if isinstance(category, RecoveryCategory)
            else RecoveryCategory(str(category).strip().lower())
        )
        return tuple(entry for entry in self.entries if entry.category == normalized)


@dataclass(frozen=True)
class CriticalMemberMatch:
    role: str
    saved_id: str
    candidate_id: str
    saved_index: int
    candidate_index: int
    match_kind: str
    geometry_error_mm: float
    saved_handles: tuple[str, ...]
    candidate_handles: tuple[str, ...]


@dataclass(frozen=True)
class CriticalMemberAddition:
    role: str
    candidate_id: str
    candidate_index: int
    candidate_handles: tuple[str, ...]


@dataclass(frozen=True)
class CriticalMemberMatchResult:
    matches: tuple[CriticalMemberMatch, ...] = ()
    missing_saved_ids: tuple[str, ...] = ()
    ambiguous_saved_ids: tuple[str, ...] = ()
    additions: tuple[CriticalMemberAddition, ...] = ()

    @property
    def compatible(self) -> bool:
        return not self.missing_saved_ids and not self.ambiguous_saved_ids


@dataclass(frozen=True)
class ManualOverrideRebindResult:
    rebound: tuple[SourceManualOverride, ...] = ()
    requires_review_labels: tuple[str, ...] = ()


def critical_member_identity_map(
    matches: Sequence[CriticalMemberMatch],
) -> Mapping[str, tuple[str, ...]]:
    """Return old critical source identity to candidate handle identity."""

    rebound: dict[str, tuple[str, ...]] = {}
    conflicts: set[str] = set()
    for match in matches:
        identity = canonical_source_identity(match.role, match.saved_handles)
        candidate_handles = normalize_source_handles(match.candidate_handles)
        if not match.saved_handles or not candidate_handles:
            continue
        if identity in rebound and rebound[identity] != candidate_handles:
            conflicts.add(identity)
        else:
            rebound[identity] = candidate_handles
    for identity in conflicts:
        rebound.pop(identity, None)
    return MappingProxyType(rebound)


def rebind_manual_overrides(
    overrides: Sequence[SourceManualOverride],
    matches: Sequence[CriticalMemberMatch],
) -> ManualOverrideRebindResult:
    """Retarget saved manual inputs only through unique critical matches."""

    identity_map = critical_member_identity_map(matches)
    rebound: list[SourceManualOverride] = []
    requires_review: list[str] = []
    for override in overrides:
        identity = canonical_source_identity(
            override.role,
            override.source_handles,
        )
        candidate_handles = identity_map.get(identity)
        if candidate_handles is None:
            requires_review.extend(manual_override_labels(override))
            continue
        rebound.append(
            replace(
                override,
                source_handles=candidate_handles,
            )
        )
    return ManualOverrideRebindResult(
        rebound=tuple(rebound),
        requires_review_labels=tuple(dict.fromkeys(requires_review)),
    )


@dataclass(frozen=True)
class _MemberView:
    role: str
    index: int
    identifier: str
    source_layer: str
    source_handles: tuple[str, ...]
    line: tuple[tuple[float, float], tuple[float, float]] | None


def _member_value(member: Any, name: str, default: Any = None) -> Any:
    if isinstance(member, Mapping):
        return member.get(name, default)
    return getattr(member, name, default)


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


def _member_line(
    member: Any,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    for start_name, end_name in (
        ("world_start", "world_end"),
        ("start", "end"),
        ("local_start", "local_end"),
    ):
        start = _point(_member_value(member, start_name))
        end = _point(_member_value(member, end_name))
        if start is not None and end is not None:
            return start, end
    return None


def _line_error_mm(
    first: tuple[tuple[float, float], tuple[float, float]],
    second: tuple[tuple[float, float], tuple[float, float]],
) -> float:
    def distance(left: tuple[float, float], right: tuple[float, float]) -> float:
        return math.hypot(left[0] - right[0], left[1] - right[1])

    return min(
        max(distance(first[0], second[0]), distance(first[1], second[1])),
        max(distance(first[0], second[1]), distance(first[1], second[0])),
    )


def _member_view(role: str, index: int, member: Any) -> _MemberView:
    identifier = str(
        _member_value(member, "id", f"{role}:{index + 1}")
        or f"{role}:{index + 1}"
    )
    return _MemberView(
        role=role,
        index=index,
        identifier=identifier,
        source_layer=str(_member_value(member, "source_layer", "") or ""),
        source_handles=normalize_source_handles(
            _member_value(member, "source_handles", ())
        ),
        line=_member_line(member),
    )


def _saved_members_by_role(
    saved_state: Mapping[str, Any],
) -> dict[str, tuple[Any, ...]]:
    converted = saved_state.get("converted") or {}
    if not isinstance(converted, Mapping):
        converted = {}
    return {
        role: tuple(
            item
            for item in converted.get(collection_name, ()) or ()
            if isinstance(item, Mapping)
        )
        for role, collection_name in _ROLE_COLLECTIONS.items()
    }


def _candidate_members_by_role(candidate_result: Any) -> dict[str, tuple[Any, ...]]:
    return {
        role: tuple(_member_value(candidate_result, collection_name, ()) or ())
        for role, collection_name in _ROLE_COLLECTIONS.items()
    }


def match_critical_members(
    saved_state: Mapping[str, Any],
    candidate_result: Any,
    *,
    geometry_tolerance_mm: float,
    ambiguity_tolerance_mm: float,
) -> CriticalMemberMatchResult:
    """Match every saved critical member to one unused same-role candidate.

    World-line geometry first bounds every acceptable option. Within that
    qualified set, shared handles outrank same-layer and changed-layer
    evidence. The existing inclusive tolerance and ambiguity boundaries are
    supplied by the composition root. Candidate-only members are additions.
    """

    geometry_tolerance = float(geometry_tolerance_mm)
    ambiguity_tolerance = float(ambiguity_tolerance_mm)
    if geometry_tolerance < 0 or ambiguity_tolerance < 0:
        raise ValueError("Matching tolerances must be non-negative.")

    saved_by_role = _saved_members_by_role(saved_state)
    candidate_by_role = _candidate_members_by_role(candidate_result)
    matches: list[CriticalMemberMatch] = []
    missing: list[str] = []
    ambiguous: list[str] = []
    additions: list[CriticalMemberAddition] = []

    for role in CRITICAL_MEMBER_ROLES:
        saved_views = tuple(
            _member_view(role, index, member)
            for index, member in enumerate(saved_by_role[role])
        )
        candidate_views = tuple(
            _member_view(role, index, member)
            for index, member in enumerate(candidate_by_role[role])
        )
        unused = set(range(len(candidate_views)))

        for saved in saved_views:
            options: list[tuple[int, float, int]] = []
            saved_handles = set(saved.source_handles)
            if saved.line is not None:
                for candidate_index in unused:
                    candidate = candidate_views[candidate_index]
                    if candidate.line is None:
                        continue
                    error = _line_error_mm(saved.line, candidate.line)
                    if error <= geometry_tolerance:
                        evidence_priority = (
                            0
                            if saved_handles.intersection(candidate.source_handles)
                            else (
                                1
                                if saved.source_layer == candidate.source_layer
                                else 2
                            )
                        )
                        options.append((evidence_priority, error, candidate_index))

            options.sort(key=lambda option: (option[0], option[1], option[2]))
            if not options:
                missing.append(saved.identifier)
                continue

            best_priority, best_error, candidate_index = options[0]
            equally_good = tuple(
                option
                for option in options
                if option[0] == best_priority
                and (
                    option[1] == best_error
                    or (
                        math.isfinite(option[1])
                        and math.isfinite(best_error)
                        and abs(option[1] - best_error) <= ambiguity_tolerance
                    )
                    or (math.isinf(option[1]) and math.isinf(best_error))
                )
            )
            if len(equally_good) > 1:
                ambiguous.append(saved.identifier)
                continue

            candidate = candidate_views[candidate_index]
            unused.remove(candidate_index)
            match_kind = (
                "shared_handle"
                if best_priority == 0
                else (
                    "geometry"
                    if best_priority == 1
                    else "geometry_layer_changed"
                )
            )
            matches.append(
                CriticalMemberMatch(
                    role=role,
                    saved_id=saved.identifier,
                    candidate_id=candidate.identifier,
                    saved_index=saved.index,
                    candidate_index=candidate.index,
                    match_kind=match_kind,
                    geometry_error_mm=(
                        best_error if math.isfinite(best_error) else 0.0
                    ),
                    saved_handles=saved.source_handles,
                    candidate_handles=candidate.source_handles,
                )
            )

        for candidate_index in sorted(unused):
            candidate = candidate_views[candidate_index]
            additions.append(
                CriticalMemberAddition(
                    role=role,
                    candidate_id=candidate.identifier,
                    candidate_index=candidate.index,
                    candidate_handles=candidate.source_handles,
                )
            )

    return CriticalMemberMatchResult(
        matches=tuple(matches),
        missing_saved_ids=tuple(missing),
        ambiguous_saved_ids=tuple(ambiguous),
        additions=tuple(additions),
    )


@dataclass(frozen=True)
class ReviewRecoveryStage:
    candidate_path: Path
    candidate_fingerprint: str
    base_state_token: str
    recovered_state: Mapping[str, Any]
    world_result: Any
    summary: RecoverySummary

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_path", Path(self.candidate_path).resolve())
        object.__setattr__(
            self,
            "candidate_fingerprint",
            str(self.candidate_fingerprint or "").strip().upper(),
        )
        object.__setattr__(
            self,
            "base_state_token",
            str(self.base_state_token or "").strip().upper(),
        )
        object.__setattr__(
            self,
            "recovered_state",
            MappingProxyType(copy.deepcopy(dict(self.recovered_state))),
        )

    def copy_recovered_state(self) -> dict[str, Any]:
        return copy.deepcopy(dict(self.recovered_state))


@dataclass(frozen=True)
class ReviewRecoveryPlan:
    stage: ReviewRecoveryStage
    member_matches: tuple[CriticalMemberMatch, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "member_matches", tuple(self.member_matches))


@dataclass(frozen=True)
class ReviewRecoveryResult:
    status: ReviewRecoveryStatus
    plan: ReviewRecoveryPlan | None
    summary: RecoverySummary
    detail_lines: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        status = self.status
        if not isinstance(status, ReviewRecoveryStatus):
            status = ReviewRecoveryStatus(str(status).strip().upper())
            object.__setattr__(self, "status", status)
        object.__setattr__(
            self,
            "detail_lines",
            tuple(str(line) for line in self.detail_lines if str(line)),
        )
        if status == ReviewRecoveryStatus.COMPATIBLE_RECOVERY_AVAILABLE:
            if self.plan is None:
                raise ValueError("Compatible recovery result 必須包含 plan。")
        elif self.plan is not None:
            raise ValueError("失敗的 recovery result 不得包含可提交 plan。")


__all__ = [
    "CRITICAL_MEMBER_ROLES",
    "CriticalMemberAddition",
    "CriticalMemberMatch",
    "CriticalMemberMatchResult",
    "ManualOverrideRebindResult",
    "RecoveryCategory",
    "RecoverySummary",
    "RecoverySummaryEntry",
    "ReviewRecoveryPlan",
    "ReviewRecoveryResult",
    "ReviewRecoveryStage",
    "ReviewRecoveryStatus",
    "critical_member_identity_map",
    "match_critical_members",
    "rebind_manual_overrides",
]
