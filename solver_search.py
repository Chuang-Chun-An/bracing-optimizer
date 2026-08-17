"""Central search policy and diagnostics for the Waler and Support solvers.

This module deliberately has no Tkinter, ``wales`` or ``support`` imports.  It
contains developer-owned search settings and pure decision helpers so the GUI,
the algorithms and tests all use the same policy without creating import
cycles.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SEARCH_INSUFFICIENT = "SEARCH_INSUFFICIENT"
CANDIDATE_INSUFFICIENT = "CANDIDATE_INSUFFICIENT"
ENGINEERING_CONSTRAINT_LIMITED = "ENGINEERING_CONSTRAINT_LIMITED"
SCORING_PREFERENCE = "SCORING_PREFERENCE"
NO_ISSUE = "NONE"


@dataclass(frozen=True)
class WalerSearchStage:
    name: str
    generations: int
    population_size: int
    random_seed: int


@dataclass(frozen=True)
class SupportGlobalSearchStage:
    name: str
    beam_width: int


@dataclass(frozen=True)
class SolverSearchPolicy:
    """Developer-owned settings for automatic Solver search."""

    policy_id: str
    policy_version: int
    waler_search_stages: Tuple[WalerSearchStage, ...]
    support_global_search_stages: Tuple[SupportGlobalSearchStage, ...]
    stability_window: int
    minimum_valid_solution_count: int
    minimum_unique_solution_count: int
    score_improvement_tolerance: float
    score_comparison_precision: int
    support_phase1_length_combination_count: int
    support_phase1_retained_candidate_count: int
    support_phase1_random_seed: int
    support_phase1_jack_bucket_size: int
    support_phase1_candidates_per_jack_bucket: int
    scoring_pattern_dominance_threshold: float

    @property
    def cache_token(self) -> Tuple[str, int]:
        return self.policy_id, self.policy_version


DEFAULT_SEARCH_POLICY = SolverSearchPolicy(
    policy_id="solver_auto_search",
    policy_version=1,
    waler_search_stages=(
        # STANDARD preserves the former production GUI defaults.
        WalerSearchStage("STANDARD", generations=10, population_size=120, random_seed=42),
        WalerSearchStage("ENHANCED", generations=30, population_size=180, random_seed=137),
        WalerSearchStage("DEEP", generations=60, population_size=240, random_seed=271),
    ),
    support_global_search_stages=(
        # Support Phase 2 is deterministic; only Beam width is increased.
        SupportGlobalSearchStage("STANDARD", beam_width=100),
        SupportGlobalSearchStage("ENHANCED", beam_width=250),
        SupportGlobalSearchStage("DEEP", beam_width=500),
    ),
    stability_window=5,
    minimum_valid_solution_count=3,
    minimum_unique_solution_count=3,
    score_improvement_tolerance=0.001,
    score_comparison_precision=6,
    support_phase1_length_combination_count=100,
    support_phase1_retained_candidate_count=100,
    support_phase1_random_seed=42,
    support_phase1_jack_bucket_size=100,
    support_phase1_candidates_per_jack_bucket=2,
    scoring_pattern_dominance_threshold=0.70,
)


@dataclass
class SolverDiagnostics:
    solver_type: str
    search_status: str = "completed"
    search_stage: str = ""
    legal_solution_found: bool = False
    infeasibility_proven: bool = False
    search_limit_reached: bool = False
    search_was_escalated: bool = False
    result_is_stable: bool = False
    candidate_count: int = 0
    valid_candidate_count: int = 0
    retained_candidate_count: int = 0
    unique_solution_count: int = 0
    best_score_history: List[float] = field(default_factory=list)
    escalation_reasons: List[str] = field(default_factory=list)
    stopping_reason: str = ""
    main_issue_category: str = NO_ISSUE
    main_issue_message: str = ""
    secondary_issue_categories: List[str] = field(default_factory=list)
    issue_counts: Dict[str, int] = field(default_factory=dict)
    affected_component_ids: List[str] = field(default_factory=list)
    component_candidate_counts: Dict[str, int] = field(default_factory=dict)
    policy_id: str = DEFAULT_SEARCH_POLICY.policy_id
    policy_version: int = DEFAULT_SEARCH_POLICY.policy_version
    stage_records: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> Optional["SolverDiagnostics"]:
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            return None
        known_fields = cls.__dataclass_fields__
        payload = {
            key: value[key]
            for key in known_fields
            if key in value
        }
        try:
            return cls(**payload)
        except (TypeError, ValueError):
            return None


@dataclass(frozen=True)
class SearchStageAssessment:
    should_escalate: bool
    result_is_stable: bool
    reasons: Tuple[str, ...]
    stopping_reason: str


def _rounded_score(value: float, precision: int) -> float:
    return round(float(value), max(0, int(precision)))


def relative_score_improvement(old_score: float, new_score: float) -> float:
    """Return positive relative improvement for a minimization score."""

    old_value = float(old_score)
    new_value = float(new_score)
    return max(0.0, (old_value - new_value) / max(abs(old_value), 1.0))


def score_history_is_stable(
    best_score_history: Sequence[float],
    policy: SolverSearchPolicy = DEFAULT_SEARCH_POLICY,
) -> bool:
    """Check whether the best score changed less than policy tolerance."""

    window = max(2, int(policy.stability_window))
    if len(best_score_history) < window:
        return False
    recent = [
        _rounded_score(value, policy.score_comparison_precision)
        for value in best_score_history[-window:]
    ]
    return (
        relative_score_improvement(recent[0], min(recent))
        <= policy.score_improvement_tolerance
    )


def assess_waler_stage(
    *,
    valid_solution_count: int,
    unique_solution_count: int,
    best_score_history: Sequence[float],
    is_last_stage: bool,
    policy: SolverSearchPolicy = DEFAULT_SEARCH_POLICY,
) -> SearchStageAssessment:
    legal_found = int(valid_solution_count) > 0
    stable = legal_found and score_history_is_stable(best_score_history, policy)
    reasons: List[str] = []
    if not legal_found:
        reasons.append("尚未找到合法方案")
    if legal_found and int(valid_solution_count) < policy.minimum_valid_solution_count:
        reasons.append("合法方案數低於政策門檻")
    if legal_found and int(unique_solution_count) < policy.minimum_unique_solution_count:
        reasons.append("合法且唯一方案數低於政策門檻")
    if legal_found and not stable:
        reasons.append("最佳分數在搜尋尾段仍未穩定")

    if is_last_stage:
        return SearchStageAssessment(
            should_escalate=False,
            result_is_stable=stable,
            reasons=tuple(reasons),
            stopping_reason=(
                "結果已穩定且方案數充足"
                if not reasons
                else "已達最大搜尋階段"
            ),
        )
    if reasons:
        return SearchStageAssessment(True, stable, tuple(reasons), "進入下一搜尋階段")
    return SearchStageAssessment(False, True, (), "結果已穩定且方案數充足")


def assess_support_stage(
    *,
    legal_solution_found: bool,
    unique_solution_count: int,
    stage_best_scores: Sequence[float],
    pruning_was_active: bool,
    is_last_stage: bool,
    policy: SolverSearchPolicy = DEFAULT_SEARCH_POLICY,
) -> SearchStageAssessment:
    """Assess deterministic Support Beam Search without Seed repetitions.

    An unpruned Beam is exhaustive for the retained Phase 1 candidates.  When
    pruning occurred, a second width is used to compare scores; equal scores
    within policy tolerance are considered stable.
    """

    stable = False
    if legal_solution_found:
        if not pruning_was_active:
            stable = True
        elif len(stage_best_scores) >= 2:
            stable = (
                relative_score_improvement(stage_best_scores[-2], stage_best_scores[-1])
                <= policy.score_improvement_tolerance
            )

    reasons: List[str] = []
    if not legal_solution_found:
        reasons.append("尚未找到合法全域方案")
    if legal_solution_found and int(unique_solution_count) < policy.minimum_unique_solution_count:
        reasons.append("合法且唯一的全域方案數低於政策門檻")
    if legal_solution_found and not stable:
        reasons.append("目前搜尋寬度仍可能影響最佳結果")

    if is_last_stage:
        return SearchStageAssessment(
            False,
            stable,
            tuple(reasons),
            "結果已穩定且方案數充足" if not reasons else "已達最大搜尋階段",
        )
    if reasons:
        return SearchStageAssessment(True, stable, tuple(reasons), "進入下一搜尋階段")
    return SearchStageAssessment(False, True, (), "結果已穩定且方案數充足")


def _number_signature(value: Any, precision: int) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        rounded = round(float(value), max(0, int(precision)))
        return int(rounded) if rounded.is_integer() else rounded
    return value


def waler_solution_signature(item: Dict[str, Any], precision: int = 6) -> Tuple[Any, ...]:
    return (
        tuple(_number_signature(value, precision) for value in item.get("segments", []) or []),
        tuple(_number_signature(value, precision) for value in item.get("joints", []) or []),
        _number_signature(item.get("tail_adjustment", 0), precision),
        _number_signature(item.get("gap", 0), precision),
    )


def support_plan_signature(plan: Any, precision: int = 6) -> Tuple[Any, ...]:
    return (
        str(getattr(plan, "support_id", "") or ""),
        tuple(
            (str(kind), _number_signature(length, precision))
            for kind, length in (getattr(plan, "pieces", []) or [])
        ),
        tuple(_number_signature(value, precision) for value in (getattr(plan, "joints", []) or [])),
        _number_signature(getattr(plan, "gap", 0), precision),
        _number_signature(getattr(plan, "jack_center", 0), precision),
        int(getattr(plan, "jack_region_id", 0) or 0),
    )


def support_solution_signature(solution: Any, precision: int = 6) -> Tuple[Any, ...]:
    return tuple(
        support_plan_signature(plan, precision)
        for plan in (getattr(solution, "plans", []) or [])
    )


def merge_waler_results(
    results: Iterable[Dict[str, Any]],
    *,
    limit: int = 5,
    precision: int = 6,
) -> List[Dict[str, Any]]:
    values = list(results)
    if any(bool(item.get("valid")) for item in values):
        values = [item for item in values if bool(item.get("valid"))]
    unique: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for item in values:
        signature = waler_solution_signature(item, precision)
        current = unique.get(signature)
        if current is None or float(item.get("score", float("inf"))) < float(current.get("score", float("inf"))):
            unique[signature] = item
    ordered = sorted(
        unique.values(),
        key=lambda item: (
            _rounded_score(item.get("score", float("inf")), precision),
            waler_solution_signature(item, precision),
        ),
    )
    return ordered[: max(0, int(limit))]


def select_best_support_solution(
    solutions: Iterable[Any],
    *,
    precision: int = 6,
) -> Optional[Any]:
    values = list(solutions)
    if not values:
        return None
    if any(bool(getattr(item, "valid", False)) for item in values):
        values = [item for item in values if bool(getattr(item, "valid", False))]
    unique: Dict[Tuple[Any, ...], Any] = {}
    for item in values:
        signature = support_solution_signature(item, precision)
        current = unique.get(signature)
        if current is None or float(getattr(item, "total_score", float("inf"))) < float(getattr(current, "total_score", float("inf"))):
            unique[signature] = item
    return min(
        unique.values(),
        key=lambda item: (
            _rounded_score(getattr(item, "total_score", float("inf")), precision),
            support_solution_signature(item, precision),
        ),
    )
