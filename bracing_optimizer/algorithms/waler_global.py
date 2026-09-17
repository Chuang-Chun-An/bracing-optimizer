"""Deterministic exact selection across retained single-Waler candidates.

The local Waler solver remains responsible for generating and scoring each
member's candidates.  This module only selects exactly one retained candidate
per Waler.  It deliberately has no Project, GUI, inventory, or GA dependency.

Phase 1 does *not* share inventory across Walers.  "Exact" therefore means
exact within the retained candidate sets supplied by the local solver.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from bracing_optimizer.domain.material_rules import (
    DEFAULT_MATERIAL_LENGTH_RULES,
    MaterialLengthRules,
    MaterialRatioTargets,
    classify_length,
)


GLOBAL_WALER_ALGORITHM_VERSION = "waler_global_dp_v1"
GLOBAL_WALER_PRUNING_TYPE = "exact_duplicate_state_merge"
GLOBAL_WALER_LOCAL_SCORE_PRECISION = 9


@dataclass(frozen=True)
class WalerMaterialMetadata:
    short_count: int
    mid_count: int
    long_count: int
    out_count: int
    out_distance_mm: int

    @property
    def signature(self) -> tuple[int, int, int, int, int]:
        return (
            self.short_count,
            self.mid_count,
            self.long_count,
            self.out_count,
            self.out_distance_mm,
        )


@dataclass(frozen=True)
class WalerGlobalCandidate:
    waler_id: str
    candidate_rank: int
    segments: tuple[int, ...]
    joints: tuple[int, ...]
    local_score: float
    local_regret: float
    short_count: int
    mid_count: int
    long_count: int
    out_count: int
    out_distance_mm: int
    material_signature: tuple[int, int, int, int, int]
    payload: Mapping[str, object] = field(repr=False, compare=False)

    @property
    def state_delta(self) -> tuple[int, int, int, int]:
        return (
            self.short_count,
            self.mid_count,
            self.long_count,
            self.out_count,
        )


@dataclass(frozen=True)
class WalerGlobalSolution:
    selected_candidates: tuple[WalerGlobalCandidate, ...] = ()
    total_short: int = 0
    total_mid: int = 0
    total_long: int = 0
    total_out: int = 0
    total_out_distance_mm: int = 0
    short_ratio: float = 0.0
    mid_ratio: float = 0.0
    long_ratio: float = 0.0
    ratio_deviation: float = math.inf
    total_local_regret: float = 0.0
    changed_waler_count: int = 0
    objective_tuple: tuple[object, ...] = ()
    valid: bool = False
    reason: str = ""

    @property
    def changed_waler_ids(self) -> tuple[str, ...]:
        return tuple(
            candidate.waler_id
            for candidate in self.selected_candidates
            if candidate.candidate_rank != 1
        )


@dataclass(frozen=True)
class WalerGlobalDiagnostics:
    algorithm_version: str = GLOBAL_WALER_ALGORITHM_VERSION
    waler_count: int = 0
    raw_candidate_count: int = 0
    retained_candidate_count_after_signature_merge: int = 0
    transition_count: int = 0
    merged_state_count: int = 0
    cumulative_state_count: int = 0
    max_active_state_count: int = 0
    final_state_count: int = 0
    exact_search: bool = True
    pruning_type: str = GLOBAL_WALER_PRUNING_TYPE
    target_ratio: Mapping[str, float] = field(default_factory=dict)
    final_objective: tuple[object, ...] = ()
    changed_waler_ids: tuple[str, ...] = ()
    failed_waler_ids: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    shared_inventory_optimized: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "algorithm_version": self.algorithm_version,
            "waler_count": self.waler_count,
            "raw_candidate_count": self.raw_candidate_count,
            "retained_candidate_count_after_signature_merge": (
                self.retained_candidate_count_after_signature_merge
            ),
            "transition_count": self.transition_count,
            "merged_state_count": self.merged_state_count,
            "cumulative_state_count": self.cumulative_state_count,
            "max_active_state_count": self.max_active_state_count,
            "final_state_count": self.final_state_count,
            "exact_search": self.exact_search,
            "pruning_type": self.pruning_type,
            "target_ratio": dict(self.target_ratio),
            "final_objective": list(self.final_objective),
            "changed_waler_ids": list(self.changed_waler_ids),
            "failed_waler_ids": list(self.failed_waler_ids),
            "messages": list(self.messages),
            "shared_inventory_optimized": self.shared_inventory_optimized,
        }


@dataclass(frozen=True)
class _PartialPath:
    out_distance_mm: int = 0
    local_regret: float = 0.0
    changed_waler_count: int = 0
    rank_path: tuple[int, ...] = ()
    selected_candidates: tuple[WalerGlobalCandidate, ...] = ()

    @property
    def merge_key(self) -> tuple[object, ...]:
        return (
            self.out_distance_mm,
            _normalized_score(self.local_regret),
            self.changed_waler_count,
            self.rank_path,
        )


def material_out_distance(
    length: int | float,
    rules: MaterialLengthRules = DEFAULT_MATERIAL_LENGTH_RULES,
) -> int:
    """Return the distance from a material length to the target interval."""

    numeric_length = int(round(float(length)))
    if numeric_length < rules.short_min:
        return rules.short_min - numeric_length
    if numeric_length > rules.long_max:
        return numeric_length - rules.long_max
    return 0


def analyze_candidate_materials(
    segments: Sequence[int | float],
    rules: MaterialLengthRules = DEFAULT_MATERIAL_LENGTH_RULES,
) -> WalerMaterialMetadata:
    """Classify all steel segments with the shared material policy."""

    counts = {"short": 0, "mid": 0, "long": 0, "out": 0}
    out_distance_mm = 0
    for raw_length in segments:
        length = int(round(float(raw_length)))
        category = classify_length(length, rules)
        counts[category] += 1
        if category == "out":
            out_distance_mm += material_out_distance(length, rules)
    return WalerMaterialMetadata(
        short_count=counts["short"],
        mid_count=counts["mid"],
        long_count=counts["long"],
        out_count=counts["out"],
        out_distance_mm=out_distance_mm,
    )


def build_global_candidate(
    *,
    waler_id: str,
    candidate_rank: int,
    payload: Mapping[str, object],
    local_best_score: float,
    rules: MaterialLengthRules = DEFAULT_MATERIAL_LENGTH_RULES,
) -> WalerGlobalCandidate:
    """Validate and enrich one retained local-solver candidate."""

    normalized_id = str(waler_id or "").strip()
    if not normalized_id:
        raise ValueError("全域圍令候選缺少圍令編號。")
    rank = int(candidate_rank)
    if rank < 1:
        raise ValueError(f"圍令 {normalized_id} 的候選名次必須大於 0。")
    if not bool(payload.get("valid", False)):
        raise ValueError(f"圍令 {normalized_id} 候選 #{rank} 不是合法方案。")

    raw_segments = list(payload.get("segments", []) or [])
    if not raw_segments:
        raise ValueError(f"圍令 {normalized_id} 候選 #{rank} 沒有材料分段。")
    segments = tuple(int(round(float(value))) for value in raw_segments)
    if any(length <= 0 for length in segments):
        raise ValueError(f"圍令 {normalized_id} 候選 #{rank} 包含無效材料長度。")
    joints = tuple(
        int(round(float(value)))
        for value in list(payload.get("joints", []) or [])
    )
    score = float(payload.get("score", math.nan))
    base_score = float(local_best_score)
    if not math.isfinite(score) or not math.isfinite(base_score):
        raise ValueError(f"圍令 {normalized_id} 候選 #{rank} 的單支分數無效。")
    regret = score - base_score
    tolerance = 10 ** (-GLOBAL_WALER_LOCAL_SCORE_PRECISION)
    if regret < 0 and abs(regret) <= tolerance:
        regret = 0.0
    regret = max(0.0, regret)
    regret = _normalized_score(regret)

    metadata = analyze_candidate_materials(segments, rules)
    return WalerGlobalCandidate(
        waler_id=normalized_id,
        candidate_rank=rank,
        segments=segments,
        joints=joints,
        local_score=score,
        local_regret=regret,
        short_count=metadata.short_count,
        mid_count=metadata.mid_count,
        long_count=metadata.long_count,
        out_count=metadata.out_count,
        out_distance_mm=metadata.out_distance_mm,
        material_signature=metadata.signature,
        payload=dict(payload),
    )


def merge_equivalent_candidates(
    candidates: Sequence[WalerGlobalCandidate],
) -> tuple[WalerGlobalCandidate, ...]:
    """Keep the globally dominant representative of each material signature."""

    representatives: dict[
        tuple[int, int, int, int, int],
        WalerGlobalCandidate,
    ] = {}
    for candidate in sorted(candidates, key=lambda item: item.candidate_rank):
        current = representatives.get(candidate.material_signature)
        candidate_key = (
            _normalized_score(candidate.local_regret),
            candidate.candidate_rank != 1,
            candidate.candidate_rank,
        )
        current_key = (
            _normalized_score(current.local_regret),
            current.candidate_rank != 1,
            current.candidate_rank,
        ) if current is not None else None
        if current is None or candidate_key < current_key:
            representatives[candidate.material_signature] = candidate
    return tuple(sorted(
        representatives.values(),
        key=lambda item: item.candidate_rank,
    ))


def project_ratio_values(
    short_count: int,
    mid_count: int,
    long_count: int,
    targets: MaterialRatioTargets,
) -> tuple[float, float, float, float]:
    """Return aggregate ratios and deviation; Out is not a denominator."""

    classified_total = short_count + mid_count + long_count
    if classified_total <= 0:
        return 0.0, 0.0, 0.0, math.inf
    short_ratio = short_count / classified_total
    mid_ratio = mid_count / classified_total
    long_ratio = long_count / classified_total
    deviation = (
        abs(short_ratio - targets.short)
        + abs(mid_ratio - targets.mid)
        + abs(long_ratio - targets.long)
    )
    return short_ratio, mid_ratio, long_ratio, deviation


def solve_global_waler_candidates(
    candidates_by_waler: Mapping[str, Sequence[WalerGlobalCandidate]],
    targets: MaterialRatioTargets,
    *,
    waler_order: Sequence[str] | None = None,
    raw_candidate_count: int | None = None,
) -> tuple[WalerGlobalSolution, WalerGlobalDiagnostics]:
    """Select exactly one candidate per Waler by deterministic exact DP."""

    order = tuple(
        str(waler_id)
        for waler_id in (
            waler_order
            if waler_order is not None
            else sorted(candidates_by_waler)
        )
    )
    groups: dict[str, tuple[WalerGlobalCandidate, ...]] = {}
    missing = []
    calculated_raw_count = 0
    for waler_id in order:
        raw_candidates = tuple(candidates_by_waler.get(waler_id, ()) or ())
        calculated_raw_count += len(raw_candidates)
        retained = merge_equivalent_candidates(raw_candidates)
        if not retained:
            missing.append(waler_id)
        groups[waler_id] = retained

    retained_count = sum(len(group) for group in groups.values())
    base_diagnostics = {
        "waler_count": len(order),
        "raw_candidate_count": (
            calculated_raw_count
            if raw_candidate_count is None
            else int(raw_candidate_count)
        ),
        "retained_candidate_count_after_signature_merge": retained_count,
        "target_ratio": targets.as_dict(),
    }
    if not order:
        message = "沒有可供全域最佳化的圍令。"
        return (
            WalerGlobalSolution(reason=message),
            WalerGlobalDiagnostics(**base_diagnostics, messages=(message,)),
        )
    if missing:
        message = "下列圍令沒有合法候選：" + "、".join(missing)
        return (
            WalerGlobalSolution(reason=message),
            WalerGlobalDiagnostics(
                **base_diagnostics,
                failed_waler_ids=tuple(missing),
                messages=(message,),
            ),
        )

    states: dict[tuple[int, int, int, int], _PartialPath] = {
        (0, 0, 0, 0): _PartialPath()
    }
    transition_count = 0
    merged_state_count = 0
    cumulative_state_count = 1
    max_active_state_count = 1

    for waler_id in order:
        next_states: dict[tuple[int, int, int, int], _PartialPath] = {}
        for state, path in states.items():
            for candidate in groups[waler_id]:
                transition_count += 1
                next_state = tuple(
                    state[index] + candidate.state_delta[index]
                    for index in range(4)
                )
                next_path = _PartialPath(
                    out_distance_mm=(
                        path.out_distance_mm + candidate.out_distance_mm
                    ),
                    local_regret=_normalized_score(
                        path.local_regret + candidate.local_regret
                    ),
                    changed_waler_count=(
                        path.changed_waler_count
                        + (candidate.candidate_rank != 1)
                    ),
                    rank_path=path.rank_path + (candidate.candidate_rank,),
                    selected_candidates=(
                        path.selected_candidates + (candidate,)
                    ),
                )
                current = next_states.get(next_state)
                if current is not None:
                    merged_state_count += 1
                if current is None or next_path.merge_key < current.merge_key:
                    next_states[next_state] = next_path
        states = next_states
        active_count = len(states)
        cumulative_state_count += active_count
        max_active_state_count = max(max_active_state_count, active_count)

    final_options = []
    for state, path in states.items():
        short_count, mid_count, long_count, out_count = state
        ratios = project_ratio_values(
            short_count,
            mid_count,
            long_count,
            targets,
        )
        short_ratio, mid_ratio, long_ratio, deviation = ratios
        if not math.isfinite(deviation):
            continue
        objective = (
            out_count,
            path.out_distance_mm,
            deviation,
            _normalized_score(path.local_regret),
            path.changed_waler_count,
            path.rank_path,
        )
        final_options.append((
            objective,
            state,
            path,
            (short_ratio, mid_ratio, long_ratio, deviation),
        ))

    if not final_options:
        message = "所有組合都沒有可計算比例的短／中／長材料。"
        diagnostics = WalerGlobalDiagnostics(
            **base_diagnostics,
            transition_count=transition_count,
            merged_state_count=merged_state_count,
            cumulative_state_count=cumulative_state_count,
            max_active_state_count=max_active_state_count,
            final_state_count=len(states),
            messages=(message,),
        )
        return WalerGlobalSolution(reason=message), diagnostics

    objective, state, path, ratio_values = min(
        final_options,
        key=lambda item: item[0],
    )
    short_count, mid_count, long_count, out_count = state
    short_ratio, mid_ratio, long_ratio, deviation = ratio_values
    solution = WalerGlobalSolution(
        selected_candidates=path.selected_candidates,
        total_short=short_count,
        total_mid=mid_count,
        total_long=long_count,
        total_out=out_count,
        total_out_distance_mm=path.out_distance_mm,
        short_ratio=short_ratio,
        mid_ratio=mid_ratio,
        long_ratio=long_ratio,
        ratio_deviation=deviation,
        total_local_regret=path.local_regret,
        changed_waler_count=path.changed_waler_count,
        objective_tuple=objective,
        valid=True,
    )
    diagnostics = WalerGlobalDiagnostics(
        **base_diagnostics,
        transition_count=transition_count,
        merged_state_count=merged_state_count,
        cumulative_state_count=cumulative_state_count,
        max_active_state_count=max_active_state_count,
        final_state_count=len(states),
        final_objective=objective,
        changed_waler_ids=solution.changed_waler_ids,
        messages=(
            "第一版只協調保留候選的材料比例；未進行全場共用庫存扣除。",
        ),
    )
    return solution, diagnostics


def _normalized_score(value: float) -> float:
    normalized = round(float(value), GLOBAL_WALER_LOCAL_SCORE_PRECISION)
    return 0.0 if normalized == 0 else normalized


__all__ = [
    "GLOBAL_WALER_ALGORITHM_VERSION",
    "GLOBAL_WALER_PRUNING_TYPE",
    "WalerGlobalCandidate",
    "WalerGlobalDiagnostics",
    "WalerGlobalSolution",
    "WalerMaterialMetadata",
    "analyze_candidate_materials",
    "build_global_candidate",
    "material_out_distance",
    "merge_equivalent_candidates",
    "project_ratio_values",
    "solve_global_waler_candidates",
]
