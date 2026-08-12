from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import Counter, defaultdict
import random
import math

import wales

# =========================================================
# dataclass 定義
# =========================================================

@dataclass
class SupportConfig:
    support_id: str
    total_length: int
    pile_centers: List[int]
    waler_centers: List[int]
    target_jack_region: int = 2
    material_spec: str = ""


@dataclass
class SupportPlan:
    support_id: str
    pieces: List[Tuple[str, int]]
    joints: List[int]
    gap: int
    jack_center: float
    jack_region_id: int
    score: float
    valid: bool
    pile_centers: List[int] = field(default_factory=list)
    waler_centers: List[int] = field(default_factory=list)
    reason: str = ""
    breakdown: Dict[str, float] = field(default_factory=dict)
    material_spec: str = ""
    selection_reason: str = ""


def get_support_config_key(config: SupportConfig) -> Tuple[int, Tuple[int, ...], Tuple[int, ...], int]:
    return (
        config.total_length,
        tuple(config.pile_centers),
        tuple(config.waler_centers),
        config.target_jack_region,
    )


def clone_plan_with_support_id(
    plan: SupportPlan,
    support_id: str,
    material_spec: Optional[str] = None,
) -> SupportPlan:
    return SupportPlan(
        support_id=support_id,
        pieces=list(plan.pieces),
        joints=list(plan.joints),
        gap=plan.gap,
        jack_center=plan.jack_center,
        jack_region_id=plan.jack_region_id,
        score=plan.score,
        valid=plan.valid,
        pile_centers=list(plan.pile_centers),
        waler_centers=list(plan.waler_centers),
        reason=plan.reason,
        breakdown=dict(plan.breakdown),
        material_spec=plan.material_spec if material_spec is None else str(material_spec or ""),
        selection_reason=getattr(plan, "selection_reason", ""),
    )


@dataclass
class GlobalSolution:
    plans: List[SupportPlan]
    total_score: float
    valid: bool
    reason: str = ""
    single_score_total: float = 0.0
    jack_region_penalty: float = 0.0
    material_ratio_penalty: float = 0.0
    material_ratio_analysis: Dict[str, object] = field(default_factory=dict)
    material_ratio_targets: Dict[str, float] = field(default_factory=dict)
    material_ratio_weight: float = 0.0
    material_concentration_penalty: float = 0.0
    material_concentration_analysis: Dict[str, object] = field(default_factory=dict)
    material_concentration_threshold: float = 0.0
    material_concentration_weight: float = 0.0
    min_jack_distance: Optional[float] = None


# =========================================================
# 基本參數
# =========================================================

STEEL_LENGTHS = [
    1000, 1500, 2000, 2500, 3000, 3500,
    4000, 4500, 5000, 5500, 6000,
    6500, 7000, 7500, 8000, 8500,
    9000, 9500, 10000
]

JACK_SPACING = 500
JACK_LENGTH = 600
SHIM_LENGTHS = [0, 100, 150, 200, 300]

MAX_GAP = 150
TARGET_GAP = 80

MIN_END_CLEAR = 1600
PILE_FORBIDDEN_HALF = 830
WALER_FORBIDDEN_HALF = 550

MIN_JACK_DISTANCE_BETWEEN_SUPPORTS = JACK_SPACING
SUPPORT_MATERIAL_RATIO_WEIGHT = 10_000
SUPPORT_MATERIAL_CONCENTRATION_THRESHOLD = 0.25
SUPPORT_MATERIAL_CONCENTRATION_WEIGHT = 0.0
SUPPORT_DEFAULT_SHORT_MATERIAL_RATIO = 38
SUPPORT_DEFAULT_MID_MATERIAL_RATIO = 40
SUPPORT_DEFAULT_LONG_MATERIAL_RATIO = 22
SUPPORT_CANDIDATE_CACHE_SCHEMA_VERSION = 6
SUPPORT_CANDIDATE_SELECTION_VERSION = "phase1_material_style_v5"
SUPPORT_MIN_GAP = 0
SUPPORT_SHORT_STEEL_THRESHOLD = 4000
SUPPORT_SHORT_STEEL_PENALTY_WEIGHT = 8000
SUPPORT_JOINT_PENALTY_WEIGHT = 1200
SUPPORT_GAP_PENALTY_WEIGHT = 20
SUPPORT_JACK_EDGE_CLEARANCE = 2500
SUPPORT_JACK_EDGE_PENALTY = 5000
SUPPORT_INVALID_BASE_PENALTY = 1_000_000
SUPPORT_INVALID_FORBIDDEN_JOINT_WEIGHT = 100_000
SUPPORT_INVALID_GAP_WEIGHT = 1000
SUPPORT_DP_MAX_STATES_PER_SUM = 60
SUPPORT_DP_MAX_STEEL_PIECES = 20
SUPPORT_ORDER_FIRST_SHORT_PENALTY = 40.0
SUPPORT_ORDER_LAST_SHORT_PENALTY = 20.0
SUPPORT_ORDER_LAST_TWO_SHORT_PENALTY = 10.0
SUPPORT_ORDER_EACH_SHORT_PENALTY = 2.0
SUPPORT_PHASE1_LAYOUT_BEAM_WIDTH = 50
SUPPORT_PHASE1_MAX_LAYOUTS_PER_COMBO = 20
SUPPORT_DEFAULT_MIN_PROCESSED_STEEL_COMBINATIONS = 60
SUPPORT_DEFAULT_MIN_CANDIDATE_POOL_SIZE = 80
SUPPORT_DEFAULT_MIN_UNIQUE_JACK_CENTERS = 6
SUPPORT_DEFAULT_MIN_NO_UNDER_4000_CANDIDATES = 10
SUPPORT_DEFAULT_MIN_UNIQUE_MATERIAL_STYLES = 8
SUPPORT_DEFAULT_JACK_CENTER_BUCKET_SIZE = 100
SUPPORT_DEFAULT_FINAL_CANDIDATE_COUNT = 100
SUPPORT_DEFAULT_MIN_CANDIDATES_PER_JACK_BUCKET = 2
SUPPORT_DEFAULT_MIN_CANDIDATES_PER_MATERIAL_STYLE = 2
SUPPORT_DEFAULT_MIN_RETAINED_NO_UNDER_4000_CANDIDATES = 20
SUPPORT_LENGTH_COMBINATION_SELECTION_STRATEGY = "material_style_v1"
SUPPORT_LENGTH_COMBINATION_SCORE_QUOTA = 40
SUPPORT_LENGTH_COMBINATION_MIN_PER_MATERIAL_STYLE = 1

# Debug
DEBUG = False

logger = None


def _stable_cache_number(value):
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return format(value, ".12g")
    return value


def _stable_number_tuple(values) -> Tuple[object, ...]:
    return tuple(
        _stable_cache_number(value)
        for value in values
    )


def build_support_candidate_cache_key(
    config: SupportConfig,
    *,
    max_length_combinations: int,
    min_candidates: Optional[int] = None,
    final_candidate_count: Optional[int] = None,
    beam_width: int,
    max_layouts_per_combo: int,
    min_processed_steel_combinations: int = SUPPORT_DEFAULT_MIN_PROCESSED_STEEL_COMBINATIONS,
    min_candidate_pool_size: int = SUPPORT_DEFAULT_MIN_CANDIDATE_POOL_SIZE,
    min_unique_jack_centers: int = SUPPORT_DEFAULT_MIN_UNIQUE_JACK_CENTERS,
    min_no_under_4000_candidates: int = SUPPORT_DEFAULT_MIN_NO_UNDER_4000_CANDIDATES,
    min_unique_material_styles: int = SUPPORT_DEFAULT_MIN_UNIQUE_MATERIAL_STYLES,
    min_candidates_per_jack_bucket: int = SUPPORT_DEFAULT_MIN_CANDIDATES_PER_JACK_BUCKET,
    min_candidates_per_material_style: int = SUPPORT_DEFAULT_MIN_CANDIDATES_PER_MATERIAL_STYLE,
    min_retained_no_under_4000_candidates: int = SUPPORT_DEFAULT_MIN_RETAINED_NO_UNDER_4000_CANDIDATES,
    candidate_selection_version: str = SUPPORT_CANDIDATE_SELECTION_VERSION,
    length_combination_selection_strategy: str = SUPPORT_LENGTH_COMBINATION_SELECTION_STRATEGY,
    jack_center_bucket_size: Optional[float] = SUPPORT_DEFAULT_JACK_CENTER_BUCKET_SIZE,
) -> Tuple[object, ...]:
    """Build a stable key for Phase 1 support candidate generation.

    Phase 2-only settings such as material ratio weight and global beam width
    are intentionally excluded.
    """
    if final_candidate_count is None:
        final_candidate_count = (
            SUPPORT_DEFAULT_FINAL_CANDIDATE_COUNT
            if min_candidates is None
            else min_candidates
        )

    return (
        ("schema", SUPPORT_CANDIDATE_CACHE_SCHEMA_VERSION),
        ("selection_version", str(candidate_selection_version)),
        ("config", (
            ("total_length", _stable_cache_number(config.total_length)),
            ("pile_centers", tuple(sorted(_stable_number_tuple(config.pile_centers)))),
            ("waler_centers", tuple(sorted(_stable_number_tuple(config.waler_centers)))),
            ("target_jack_region", int(config.target_jack_region)),
        )),
        ("materials", (
            ("steel_lengths", tuple(sorted(_stable_number_tuple(STEEL_LENGTHS)))),
            ("shim_lengths", tuple(sorted(_stable_number_tuple(SHIM_LENGTHS)))),
            ("jack_length", _stable_cache_number(JACK_LENGTH)),
        )),
        ("gap_rules", (
            ("min_gap", _stable_cache_number(SUPPORT_MIN_GAP)),
            ("max_gap", _stable_cache_number(MAX_GAP)),
            ("target_gap", _stable_cache_number(TARGET_GAP)),
        )),
        ("forbidden_zone_rules", (
            ("min_end_clear", _stable_cache_number(MIN_END_CLEAR)),
            ("pile_forbidden_half", _stable_cache_number(PILE_FORBIDDEN_HALF)),
            ("waler_forbidden_half", _stable_cache_number(WALER_FORBIDDEN_HALF)),
        )),
        ("jack_region_rules", (
            ("algorithm", "sorted_pile_interval_v1"),
            ("jack_center_bucket_size", _stable_cache_number(jack_center_bucket_size)),
        )),
        ("single_score_rules", (
            ("short_steel_threshold", _stable_cache_number(SUPPORT_SHORT_STEEL_THRESHOLD)),
            ("short_steel_penalty_weight", _stable_cache_number(SUPPORT_SHORT_STEEL_PENALTY_WEIGHT)),
            ("joint_penalty_weight", _stable_cache_number(SUPPORT_JOINT_PENALTY_WEIGHT)),
            ("gap_penalty_weight", _stable_cache_number(SUPPORT_GAP_PENALTY_WEIGHT)),
            ("jack_edge_clearance", _stable_cache_number(SUPPORT_JACK_EDGE_CLEARANCE)),
            ("jack_edge_penalty", _stable_cache_number(SUPPORT_JACK_EDGE_PENALTY)),
            ("invalid_base_penalty", _stable_cache_number(SUPPORT_INVALID_BASE_PENALTY)),
            ("invalid_forbidden_joint_weight", _stable_cache_number(SUPPORT_INVALID_FORBIDDEN_JOINT_WEIGHT)),
            ("invalid_gap_weight", _stable_cache_number(SUPPORT_INVALID_GAP_WEIGHT)),
            ("order_first_short_penalty", _stable_cache_number(SUPPORT_ORDER_FIRST_SHORT_PENALTY)),
            ("order_last_short_penalty", _stable_cache_number(SUPPORT_ORDER_LAST_SHORT_PENALTY)),
            ("order_last_two_short_penalty", _stable_cache_number(SUPPORT_ORDER_LAST_TWO_SHORT_PENALTY)),
            ("order_each_short_penalty", _stable_cache_number(SUPPORT_ORDER_EACH_SHORT_PENALTY)),
        )),
        ("dp_rules", (
            ("max_states_per_sum", _stable_cache_number(SUPPORT_DP_MAX_STATES_PER_SUM)),
            ("max_steel_pieces", _stable_cache_number(SUPPORT_DP_MAX_STEEL_PIECES)),
        )),
        ("phase1_limits", (
            ("max_length_combinations", int(max_length_combinations)),
            ("min_processed_steel_combinations", int(min_processed_steel_combinations)),
            ("min_candidate_pool_size", int(min_candidate_pool_size)),
            ("min_unique_jack_centers", int(min_unique_jack_centers)),
            ("min_no_under_4000_candidates", int(min_no_under_4000_candidates)),
            ("min_unique_material_styles", int(min_unique_material_styles)),
            ("final_candidate_count", int(final_candidate_count)),
            ("beam_search_layout_beam_width", int(beam_width)),
            ("max_layouts_per_combo", int(max_layouts_per_combo)),
            ("length_combination_selection_strategy", str(length_combination_selection_strategy)),
        )),
        ("candidate_selection_rules", (
            ("min_candidates_per_jack_bucket", int(min_candidates_per_jack_bucket)),
            ("min_candidates_per_material_style", int(min_candidates_per_material_style)),
            (
                "min_retained_no_under_4000_candidates",
                int(min_retained_no_under_4000_candidates),
            ),
        )),
    )


def jack_center_bucket(
    jack_center: float,
    bucket_size: float = SUPPORT_DEFAULT_JACK_CENTER_BUCKET_SIZE,
) -> int:
    bucket = float(bucket_size)
    if not math.isfinite(bucket) or bucket <= 0:
        raise ValueError("jack_center_bucket_size 必須大於 0。")

    value = float(jack_center)
    if not math.isfinite(value):
        raise ValueError("jack_center 必須是有效數字。")

    scaled = value / bucket
    nearest_integer = round(scaled)
    if abs(scaled - nearest_integer) <= 1e-9:
        scaled = float(nearest_integer)
    return math.floor(scaled)


def steel_pattern_from_pieces(pieces: List[Tuple[str, int]]) -> Tuple[int, ...]:
    return tuple(
        sorted(
            int(length)
            for kind, length in pieces
            if str(kind).lower() == "steel"
        )
    )


def steel_pattern_from_plan(plan: SupportPlan) -> Tuple[int, ...]:
    return steel_pattern_from_pieces(getattr(plan, "pieces", []) or [])


def material_style_from_lengths(
    steel_lengths: List[int],
    material_ratio_targets: Optional[Dict[str, float]] = None,
) -> Tuple[int, int, int, int]:
    cfg = _waler_length_classification_config(
        material_ratio_targets or default_material_ratio_targets(),
        SUPPORT_MATERIAL_RATIO_WEIGHT,
    )
    counts = {"short": 0, "mid": 0, "long": 0}
    normalized_lengths = [int(length) for length in steel_lengths]
    for length in normalized_lengths:
        category = wales.classify_length(int(length), cfg)
        if category in counts:
            counts[category] += 1
    return (
        max(normalized_lengths) if normalized_lengths else 0,
        counts["short"],
        counts["mid"],
        counts["long"],
    )


def material_style_from_pieces(pieces: List[Tuple[str, int]]) -> Tuple[int, int, int, int]:
    return material_style_from_lengths(
        [
            int(length)
            for kind, length in pieces
            if str(kind).lower() == "steel"
        ]
    )


def material_style_from_plan(plan: SupportPlan) -> Tuple[int, int, int, int]:
    return material_style_from_pieces(getattr(plan, "pieces", []) or [])


def material_style_from_combo(combo: Dict[str, object]) -> Tuple[int, int, int, int]:
    return material_style_from_lengths(combo_steel_lengths(combo))


def plan_has_no_under_4000_steel(plan: SupportPlan) -> bool:
    return not any(
        str(kind).lower() == "steel" and int(length) < SUPPORT_SHORT_STEEL_THRESHOLD
        for kind, length in getattr(plan, "pieces", []) or []
    )


def combo_steel_lengths(combo: Dict[str, object]) -> List[int]:
    return [int(length) for length in combo.get("steel_lengths", []) or []]


def combo_signature(combo: Dict[str, object]) -> Tuple[Tuple[int, ...], int, int]:
    return (
        tuple(combo_steel_lengths(combo)),
        int(combo.get("shim", 0) or 0),
        int(combo.get("gap", 0) or 0),
    )


def combo_count_steel_length(combo: Dict[str, object], target_length: int) -> int:
    return sum(1 for length in combo_steel_lengths(combo) if length == int(target_length))


def combo_under_4000_count(combo: Dict[str, object]) -> int:
    return sum(1 for length in combo_steel_lengths(combo) if length < SUPPORT_SHORT_STEEL_THRESHOLD)


def combo_sort_key(combo: Dict[str, object], original_index: int = 0) -> Tuple[object, ...]:
    lengths = combo_steel_lengths(combo)
    return (
        float(combo.get("score", 0.0) or 0.0),
        combo_under_4000_count(combo),
        material_style_from_lengths(lengths),
        len(lengths),
        max(lengths) if lengths else 0,
        tuple(lengths),
        int(combo.get("shim", 0) or 0),
        int(combo.get("gap", 0) or 0),
        int(original_index),
    )


def _add_combo_to_selection(
    combo: Dict[str, object],
    *,
    reason: str,
    selected: List[Dict[str, object]],
    selected_signatures: set,
    selection_counts: Counter[str],
) -> bool:
    signature = combo_signature(combo)
    if signature in selected_signatures:
        return False
    selected_signatures.add(signature)
    copied = dict(combo)
    copied.setdefault("combination_selection_reason", reason)
    selected.append(copied)
    selection_counts[reason] += 1
    return True


def select_diverse_length_combinations(
    combinations: List[Dict[str, object]],
    max_combinations: int,
    *,
    strategy: str = SUPPORT_LENGTH_COMBINATION_SELECTION_STRATEGY,
    score_quota: int = SUPPORT_LENGTH_COMBINATION_SCORE_QUOTA,
    min_per_material_style: int = SUPPORT_LENGTH_COMBINATION_MIN_PER_MATERIAL_STYLE,
) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    max_combinations = max(0, int(max_combinations))
    if strategy == "score_top" or max_combinations <= 0:
        score_sorted = list(combinations)
        score_sorted.sort(key=lambda combo: float(combo.get("score", 0.0) or 0.0))
        selected = [dict(combo) for combo in score_sorted[:max_combinations]]
        return selected, {
            "strategy": strategy,
            "selection_counts": {"score_top": len(selected)},
            "total_combination_count": len(combinations),
            "selected_combination_count": len(selected),
        }

    indexed = list(enumerate(combinations))
    indexed.sort(key=lambda item: combo_sort_key(item[1], item[0]))

    selected: List[Dict[str, object]] = []
    selected_signatures = set()
    selection_counts: Counter[str] = Counter()

    def add_from_pool(pool: List[Tuple[int, Dict[str, object]]], quota: int, reason: str) -> None:
        for _index, combo in pool:
            if len(selected) >= max_combinations or selection_counts[reason] >= max(0, int(quota)):
                break
            _add_combo_to_selection(
                combo,
                reason=reason,
                selected=selected,
                selected_signatures=selected_signatures,
                selection_counts=selection_counts,
            )

    add_from_pool(indexed, score_quota, "score_quota")

    material_style_groups: Dict[Tuple[int, int, int, int], List[Tuple[int, Dict[str, object]]]] = defaultdict(list)
    for item in indexed:
        material_style_groups[material_style_from_combo(item[1])].append(item)
    for style in sorted(material_style_groups):
        if len(selected) >= max_combinations:
            break
        retained = 0
        for _index, combo in material_style_groups[style]:
            if len(selected) >= max_combinations or retained >= max(0, int(min_per_material_style)):
                break
            if _add_combo_to_selection(
                combo,
                reason="material_style_representative",
                selected=selected,
                selected_signatures=selected_signatures,
                selection_counts=selection_counts,
            ):
                retained += 1

    for _index, combo in indexed:
        if len(selected) >= max_combinations:
            break
        _add_combo_to_selection(
            combo,
            reason="score_fill",
            selected=selected,
            selected_signatures=selected_signatures,
            selection_counts=selection_counts,
        )

    selected.sort(key=lambda combo: combo_sort_key(combo, 0))
    selected = selected[:max_combinations]
    diagnostics = {
        "strategy": strategy,
        "selection_counts": dict(selection_counts),
        "total_combination_count": len(combinations),
        "selected_combination_count": len(selected),
        "material_style_count_before_selection": len({
            material_style_from_combo(combo)
            for combo in combinations
        }),
        "material_style_count_after_selection": len({
            material_style_from_combo(combo)
            for combo in selected
        }),
        "max_steel_length_distribution_before_selection": dict(sorted(Counter(
            max(combo_steel_lengths(combo)) if combo_steel_lengths(combo) else 0
            for combo in combinations
        ).items())),
        "max_steel_length_distribution_after_selection": dict(sorted(Counter(
            max(combo_steel_lengths(combo)) if combo_steel_lengths(combo) else 0
            for combo in selected
        ).items())),
        "material_style_distribution_before_selection": dict(sorted(Counter(
            material_style_from_combo(combo)
            for combo in combinations
        ).items())),
        "material_style_distribution_after_selection": dict(sorted(Counter(
            material_style_from_combo(combo)
            for combo in selected
        ).items())),
    }
    return selected, diagnostics


def _candidate_sort_key(plan: SupportPlan, original_index: int = 0) -> Tuple[object, ...]:
    return (
        float(getattr(plan, "score", 0.0) or 0.0),
        _stable_cache_number(getattr(plan, "jack_center", 0.0) or 0.0),
        int(getattr(plan, "jack_region_id", 0) or 0),
        steel_pattern_from_plan(plan),
        tuple(getattr(plan, "pieces", []) or []),
        tuple(getattr(plan, "joints", []) or []),
        int(getattr(plan, "gap", 0) or 0),
        int(original_index),
    )


def support_candidate_statistics(
    plans: List[SupportPlan],
    jack_center_bucket_size: float = SUPPORT_DEFAULT_JACK_CENTER_BUCKET_SIZE,
) -> Dict[str, int]:
    valid_plans = [plan for plan in plans if plan.valid and not plan.reason]
    exact_jack_centers = {
        _stable_cache_number(getattr(plan, "jack_center", 0.0) or 0.0)
        for plan in valid_plans
    }
    jack_buckets = {
        jack_center_bucket(
            getattr(plan, "jack_center", 0.0) or 0.0,
            jack_center_bucket_size,
        )
        for plan in valid_plans
    }
    steel_patterns = {
        steel_pattern_from_plan(plan)
        for plan in valid_plans
    }
    material_styles = {
        material_style_from_plan(plan)
        for plan in valid_plans
    }
    max_length_distribution = Counter(
        material_style_from_plan(plan)[0]
        for plan in valid_plans
    )
    histogram_distribution = Counter(
        material_style_from_plan(plan)[1:]
        for plan in valid_plans
    )
    return {
        "valid_candidate_count": len(valid_plans),
        "unique_jack_center_count": len(exact_jack_centers),
        "jack_bucket_count": len(jack_buckets),
        "unique_steel_pattern_count": len(steel_patterns),
        "material_style_count": len(material_styles),
        "max_steel_length_distribution": dict(sorted(max_length_distribution.items())),
        "material_histogram_distribution": dict(sorted(histogram_distribution.items())),
        "no_under_4000_count": sum(
            1
            for plan in valid_plans
            if plan_has_no_under_4000_steel(plan)
        ),
    }


def steel_order_from_plan(plan: SupportPlan) -> Tuple[int, ...]:
    return tuple(
        int(length)
        for kind, length in getattr(plan, "pieces", []) or []
        if str(kind).lower() == "steel"
    )


def layout_signature(plan: SupportPlan) -> Tuple[object, ...]:
    return (
        tuple(getattr(plan, "pieces", []) or []),
        _stable_cache_number(getattr(plan, "jack_center", 0.0) or 0.0),
        tuple(getattr(plan, "joints", []) or []),
        int(getattr(plan, "gap", 0) or 0),
    )


def jack_shim_order_signature(plan: SupportPlan) -> Tuple[Tuple[int, str, int], ...]:
    return tuple(
        (index, str(kind).lower(), int(length))
        for index, (kind, length) in enumerate(getattr(plan, "pieces", []) or [])
        if str(kind).lower() in {"jack", "shim"}
    )


def under_4000_steel_count_in_plan(plan: SupportPlan) -> int:
    return sum(
        1
        for kind, length in getattr(plan, "pieces", []) or []
        if str(kind).lower() == "steel"
        and int(length) < SUPPORT_SHORT_STEEL_THRESHOLD
    )


def _steel_category_count_tuple(
    plan: SupportPlan,
    material_ratio_targets: Optional[Dict[str, float]] = None,
) -> Tuple[int, int, int]:
    cfg = _waler_length_classification_config(
        material_ratio_targets or default_material_ratio_targets(),
        SUPPORT_MATERIAL_RATIO_WEIGHT,
    )
    counts = {"short": 0, "mid": 0, "long": 0}
    for kind, length in getattr(plan, "pieces", []) or []:
        if str(kind).lower() != "steel":
            continue
        category = wales.classify_length(int(length), cfg)
        if category in counts:
            counts[category] += 1
    return counts["short"], counts["mid"], counts["long"]


def jack_center_group_diagnostics(
    plans: List[SupportPlan],
) -> List[Dict[str, object]]:
    valid_plans = [plan for plan in plans if plan.valid and not plan.reason]
    groups: Dict[object, List[SupportPlan]] = {}
    for plan in valid_plans:
        center = _stable_cache_number(getattr(plan, "jack_center", 0.0) or 0.0)
        groups.setdefault(center, []).append(plan)

    rows: List[Dict[str, object]] = []
    for center in sorted(groups):
        group = sorted(groups[center], key=lambda plan: _candidate_sort_key(plan))
        rows.append({
            "jack_center": center,
            "candidate_count": len(group),
            "lowest_single_score": float(group[0].score) if group else None,
            "has_no_under_4000_candidate": any(
                plan_has_no_under_4000_steel(plan)
                for plan in group
            ),
        })
    return rows


def support_candidate_benchmark_summary(
    *,
    config: SupportConfig,
    combination_count: int,
    diagnostics: Dict[str, object],
    candidate_pool: List[SupportPlan],
    returned_candidates: List[SupportPlan],
    material_ratio_targets: Optional[Dict[str, float]] = None,
    jack_center_bucket_size: float = SUPPORT_DEFAULT_JACK_CENTER_BUCKET_SIZE,
) -> Dict[str, object]:
    valid_pool = [plan for plan in candidate_pool if plan.valid and not plan.reason]
    valid_returned = [
        plan
        for plan in returned_candidates
        if plan.valid and not plan.reason
    ]
    processed_combinations = int(diagnostics.get("combinations_processed", 0) or 0)
    before_stats = support_candidate_statistics(valid_pool, jack_center_bucket_size)
    after_stats = support_candidate_statistics(valid_returned, jack_center_bucket_size)
    return {
        "support_id": config.support_id,
        "steel_combination_count": int(combination_count),
        "processed_steel_combination_count": processed_combinations,
        "raw_layout_count": int(diagnostics.get("layouts_generated", 0) or 0),
        "valid_layout_count": int(diagnostics.get("valid_before_region", 0) or 0),
        "candidate_count_before_topn": len(valid_pool),
        "candidate_count_after_topn": len(valid_returned),
        "before_topn": before_stats,
        "after_topn": after_stats,
        "jack_center_groups_before_topn": jack_center_group_diagnostics(valid_pool),
        "jack_center_groups_after_topn": jack_center_group_diagnostics(valid_returned),
        "no_under_4000_count_before_topn": before_stats["no_under_4000_count"],
        "no_under_4000_count_after_topn": after_stats["no_under_4000_count"],
        "unique_steel_pattern_count_before_topn": before_stats["unique_steel_pattern_count"],
        "unique_steel_pattern_count_after_topn": after_stats["unique_steel_pattern_count"],
        "unique_steel_order_count_before_topn": len({
            steel_order_from_plan(plan)
            for plan in valid_pool
        }),
        "unique_steel_order_count_after_topn": len({
            steel_order_from_plan(plan)
            for plan in valid_returned
        }),
        "steel_category_count_pattern_count_before_topn": len({
            _steel_category_count_tuple(plan, material_ratio_targets)
            for plan in valid_pool
        }),
        "steel_category_count_pattern_count_after_topn": len({
            _steel_category_count_tuple(plan, material_ratio_targets)
            for plan in valid_returned
        }),
        "layouts_truncated_by_max_layouts_per_combo": int(
            diagnostics.get("layouts_truncated_by_limit", 0) or 0
        ),
        "unexplored_steel_combination_count": max(
            0,
            int(combination_count) - processed_combinations,
        ),
    }


def _add_candidate_to_selection(
    plan: SupportPlan,
    *,
    reason: str,
    selected: List[SupportPlan],
    selected_ids: set,
    selection_counts: Counter,
) -> bool:
    identity = id(plan)
    if identity in selected_ids:
        return False
    selected_ids.add(identity)
    setattr(plan, "selection_reason", reason)
    selected.append(plan)
    selection_counts[reason] += 1
    return True


def _round_robin_select(
    group_keys: List[object],
    groups: Dict[object, List[Tuple[int, SupportPlan]]],
    *,
    per_group_target,
    capacity: int,
    reason: str,
    selected: List[SupportPlan],
    selected_ids: set,
    selection_counts: Counter,
) -> None:
    progress = True
    while len(selected) < capacity and progress:
        progress = False
        for key in group_keys:
            if len(selected) >= capacity:
                break
            current_target = per_group_target(key)
            chosen_for_group = sum(
                1
                for plan in selected
                if id(plan) in {id(item_plan) for _idx, item_plan in groups.get(key, [])}
            )
            if chosen_for_group >= current_target:
                continue
            for _original_index, plan in groups.get(key, []):
                if id(plan) in selected_ids:
                    continue
                if _add_candidate_to_selection(
                    plan,
                    reason=reason,
                    selected=selected,
                    selected_ids=selected_ids,
                    selection_counts=selection_counts,
                ):
                    progress = True
                break


def _eligible_layout_sort_key(
    plan: SupportPlan,
    *,
    jack_bucket_counts: Optional[Counter] = None,
    steel_order_counts: Optional[Counter] = None,
    jack_center_bucket_size: float = SUPPORT_DEFAULT_JACK_CENTER_BUCKET_SIZE,
) -> Tuple[object, ...]:
    bucket = jack_center_bucket(plan.jack_center, jack_center_bucket_size)
    steel_order = steel_order_from_plan(plan)
    jack_bucket_counts = jack_bucket_counts or Counter()
    steel_order_counts = steel_order_counts or Counter()
    return (
        float(plan.score),
        under_4000_steel_count_in_plan(plan),
        int(jack_bucket_counts.get(bucket, 0)),
        int(steel_order_counts.get(steel_order, 0)),
        len(getattr(plan, "joints", []) or []),
        abs(int(getattr(plan, "gap", 0) or 0)),
        layout_signature(plan),
    )


def _add_layout_to_selection(
    plan: SupportPlan,
    *,
    reason: str,
    selected: List[SupportPlan],
    selected_ids: set,
    selection_counts: Counter,
) -> bool:
    signature = layout_signature(plan)
    if signature in selected_ids:
        return False
    selected_ids.add(signature)
    setattr(plan, "layout_selection_reason", reason)
    selected.append(plan)
    selection_counts[reason] += 1
    return True


def _layout_detail(plan: SupportPlan, *, discarded_stage: str = "", rank: Optional[int] = None) -> Dict[str, object]:
    return {
        "layout_signature": layout_signature(plan),
        "steel_order": steel_order_from_plan(plan),
        "jack_shim_order": jack_shim_order_signature(plan),
        "shim_length": sum(
            int(length)
            for kind, length in getattr(plan, "pieces", []) or []
            if str(kind).lower() == "shim"
        ),
        "jack_center": plan.jack_center,
        "joint_positions": list(plan.joints),
        "remainder": plan.gap,
        "single_score": plan.score,
        "score_breakdown": dict(plan.breakdown),
        "under_4000_count": under_4000_steel_count_in_plan(plan),
        "discarded_stage": discarded_stage,
        "discarded_rank": rank,
        "pieces": list(plan.pieces),
    }


def select_diverse_eligible_layouts(
    eligible_layouts: List[SupportPlan],
    max_layouts_per_combo: int,
    jack_center_bucket_size: float = SUPPORT_DEFAULT_JACK_CENTER_BUCKET_SIZE,
    diagnostics: Optional[Dict[str, object]] = None,
) -> List[SupportPlan]:
    max_layouts_per_combo = max(0, int(max_layouts_per_combo))
    jack_center_bucket(0, jack_center_bucket_size)
    sorted_eligible = sorted(
        eligible_layouts,
        key=lambda plan: _eligible_layout_sort_key(
            plan,
            jack_center_bucket_size=jack_center_bucket_size,
        ),
    )

    selection_counts: Counter[str] = Counter()
    if len(sorted_eligible) <= max_layouts_per_combo:
        for plan in sorted_eligible:
            setattr(plan, "layout_selection_reason", "eligible_all_kept")
        selection_counts["eligible_all_kept"] = len(sorted_eligible)
        if diagnostics is not None:
            diagnostics["layout_selection_counts"] = dict(selection_counts)
            diagnostics["discarded_legal_target_layout_details"] = []
        return sorted_eligible

    selected: List[SupportPlan] = []
    selected_ids = set()

    bucket_groups: Dict[int, List[SupportPlan]] = defaultdict(list)
    for plan in sorted_eligible:
        bucket_groups[
            jack_center_bucket(plan.jack_center, jack_center_bucket_size)
        ].append(plan)

    for bucket in sorted(bucket_groups):
        if len(selected) >= max_layouts_per_combo:
            break
        _add_layout_to_selection(
            bucket_groups[bucket][0],
            reason="jack_bucket_best",
            selected=selected,
            selected_ids=selected_ids,
            selection_counts=selection_counts,
        )

    for bucket in sorted(bucket_groups):
        if len(selected) >= max_layouts_per_combo:
            break
        no_under_candidates = [
            plan
            for plan in bucket_groups[bucket]
            if plan_has_no_under_4000_steel(plan)
        ]
        if not no_under_candidates:
            continue
        _add_layout_to_selection(
            no_under_candidates[0],
            reason="jack_bucket_no_under_4000_best",
            selected=selected,
            selected_ids=selected_ids,
            selection_counts=selection_counts,
        )

    steel_order_groups: Dict[Tuple[int, ...], List[SupportPlan]] = defaultdict(list)
    for plan in sorted_eligible:
        steel_order_groups[steel_order_from_plan(plan)].append(plan)
    for steel_order in sorted(steel_order_groups):
        if len(selected) >= max_layouts_per_combo:
            break
        _add_layout_to_selection(
            steel_order_groups[steel_order][0],
            reason="steel_order_best",
            selected=selected,
            selected_ids=selected_ids,
            selection_counts=selection_counts,
        )

    jack_shim_groups: Dict[Tuple[Tuple[int, str, int], ...], List[SupportPlan]] = defaultdict(list)
    for plan in sorted_eligible:
        jack_shim_groups[jack_shim_order_signature(plan)].append(plan)
    for signature in sorted(jack_shim_groups):
        if len(selected) >= max_layouts_per_combo:
            break
        _add_layout_to_selection(
            jack_shim_groups[signature][0],
            reason="jack_shim_order_best",
            selected=selected,
            selected_ids=selected_ids,
            selection_counts=selection_counts,
        )

    current_bucket_counts = Counter(
        jack_center_bucket(plan.jack_center, jack_center_bucket_size)
        for plan in selected
    )
    current_steel_order_counts = Counter(
        steel_order_from_plan(plan)
        for plan in selected
    )
    fill_candidates = sorted(
        sorted_eligible,
        key=lambda plan: _eligible_layout_sort_key(
            plan,
            jack_bucket_counts=current_bucket_counts,
            steel_order_counts=current_steel_order_counts,
            jack_center_bucket_size=jack_center_bucket_size,
        ),
    )
    for plan in fill_candidates:
        if len(selected) >= max_layouts_per_combo:
            break
        if _add_layout_to_selection(
            plan,
            reason="score_diversity_fill",
            selected=selected,
            selected_ids=selected_ids,
            selection_counts=selection_counts,
        ):
            current_bucket_counts[
                jack_center_bucket(plan.jack_center, jack_center_bucket_size)
            ] += 1
            current_steel_order_counts[steel_order_from_plan(plan)] += 1

    selected.sort(
        key=lambda plan: _eligible_layout_sort_key(
            plan,
            jack_center_bucket_size=jack_center_bucket_size,
        )
    )

    if diagnostics is not None:
        selected_signatures = {layout_signature(plan) for plan in selected}
        discarded = [
            plan
            for plan in sorted_eligible
            if layout_signature(plan) not in selected_signatures
        ]
        diagnostics["layout_selection_counts"] = dict(selection_counts)
        diagnostics["discarded_legal_target_layout_details"] = [
            _layout_detail(
                plan,
                discarded_stage="eligible_diversity_trim",
                rank=rank,
            )
            for rank, plan in enumerate(discarded, start=1)
        ]
    return selected


def select_diverse_top_candidates(
    candidates: List[SupportPlan],
    *,
    final_candidate_count: int = SUPPORT_DEFAULT_FINAL_CANDIDATE_COUNT,
    jack_center_bucket_size: float = SUPPORT_DEFAULT_JACK_CENTER_BUCKET_SIZE,
    min_candidates_per_jack_bucket: int = SUPPORT_DEFAULT_MIN_CANDIDATES_PER_JACK_BUCKET,
    min_candidates_per_material_style: int = SUPPORT_DEFAULT_MIN_CANDIDATES_PER_MATERIAL_STYLE,
    min_retained_no_under_4000_candidates: int = SUPPORT_DEFAULT_MIN_RETAINED_NO_UNDER_4000_CANDIDATES,
) -> Tuple[List[SupportPlan], Dict[str, object]]:
    final_candidate_count = max(0, int(final_candidate_count))
    min_candidates_per_jack_bucket = max(0, int(min_candidates_per_jack_bucket))
    min_candidates_per_material_style = max(0, int(min_candidates_per_material_style))
    min_retained_no_under_4000_candidates = max(
        0,
        int(min_retained_no_under_4000_candidates),
    )
    jack_center_bucket(0, jack_center_bucket_size)

    valid_candidates = [
        (index, plan)
        for index, plan in enumerate(candidates)
        if plan.valid and not plan.reason
    ]
    valid_candidates.sort(key=lambda item: _candidate_sort_key(item[1], item[0]))

    selected: List[SupportPlan] = []
    selected_ids = set()
    selection_counts: Counter[str] = Counter()

    bucket_groups: Dict[int, List[Tuple[int, SupportPlan]]] = {}
    for item in valid_candidates:
        _index, plan = item
        bucket = jack_center_bucket(plan.jack_center, jack_center_bucket_size)
        bucket_groups.setdefault(bucket, []).append(item)
    bucket_keys = sorted(bucket_groups)
    _round_robin_select(
        bucket_keys,
        bucket_groups,
        per_group_target=lambda _key: min_candidates_per_jack_bucket,
        capacity=final_candidate_count,
        reason="jack_bucket_guarantee",
        selected=selected,
        selected_ids=selected_ids,
        selection_counts=selection_counts,
    )

    material_style_groups: Dict[Tuple[int, int, int, int], List[Tuple[int, SupportPlan]]] = {}
    for item in valid_candidates:
        _index, plan = item
        material_style_groups.setdefault(material_style_from_plan(plan), []).append(item)
    material_style_keys = sorted(material_style_groups)

    def selected_count_for_material_style(style: Tuple[int, int, int, int]) -> int:
        return sum(
            1
            for plan in selected
            if material_style_from_plan(plan) == style
        )

    _round_robin_select(
        [
            style
            for style in material_style_keys
            if selected_count_for_material_style(style) < min_candidates_per_material_style
        ],
        material_style_groups,
        per_group_target=lambda style: min_candidates_per_material_style,
        capacity=final_candidate_count,
        reason="material_style_guarantee",
        selected=selected,
        selected_ids=selected_ids,
        selection_counts=selection_counts,
    )

    selected_no_under_count = sum(
        1
        for plan in selected
        if plan_has_no_under_4000_steel(plan)
    )
    if selected_no_under_count < min_retained_no_under_4000_candidates:
        for _index, plan in valid_candidates:
            if len(selected) >= final_candidate_count:
                break
            if id(plan) in selected_ids:
                continue
            if not plan_has_no_under_4000_steel(plan):
                continue
            _add_candidate_to_selection(
                plan,
                reason="no_under_4000_guarantee",
                selected=selected,
                selected_ids=selected_ids,
                selection_counts=selection_counts,
            )
            selected_no_under_count += 1
            if selected_no_under_count >= min_retained_no_under_4000_candidates:
                break

    for _index, plan in valid_candidates:
        if len(selected) >= final_candidate_count:
            break
        _add_candidate_to_selection(
            plan,
            reason="score_fill",
            selected=selected,
            selected_ids=selected_ids,
            selection_counts=selection_counts,
        )

    selected_with_index = [
        (index, plan)
        for index, plan in enumerate(candidates)
        if id(plan) in selected_ids
    ]
    selected_with_index.sort(key=lambda item: _candidate_sort_key(item[1], item[0]))
    final_candidates = [plan for _index, plan in selected_with_index[:final_candidate_count]]

    diagnostics = {
        "selection_strategy": SUPPORT_CANDIDATE_SELECTION_VERSION,
        "selection_counts": {
            "selected_by_jack_bucket_guarantee": selection_counts["jack_bucket_guarantee"],
            "selected_by_material_style_guarantee": selection_counts["material_style_guarantee"],
            "selected_by_no_under_4000_guarantee": selection_counts["no_under_4000_guarantee"],
            "selected_by_score_fill": selection_counts["score_fill"],
        },
        "before_selection": support_candidate_statistics(
            [plan for _index, plan in valid_candidates],
            jack_center_bucket_size,
        ),
        "after_selection": support_candidate_statistics(
            final_candidates,
            jack_center_bucket_size,
        ),
    }
    diagnostics.update(diagnostics["selection_counts"])
    return final_candidates, diagnostics


def set_logger(func) -> None:
    """Set the callback that receives all Support Solver messages."""
    global logger
    logger = func


def log(*args) -> None:
    """Send a message to the configured logger without writing to stdout."""
    if logger is not None:
        logger(*args)


def display_piece_kind(kind: str) -> str:
    return {
        "steel": "鋼材",
        "shim": "調整塊",
        "jack": "千斤頂",
    }.get(str(kind).lower(), str(kind))


def format_pieces_for_display(pieces: List[Tuple[str, int]]) -> str:
    return ", ".join(
        f"{display_piece_kind(kind)}:{length}"
        for kind, length in pieces
    )


def material_spec_label(material_spec: str) -> str:
    text = str(material_spec or "").strip()
    return text if text else "未填材料"


def material_usage_by_spec(plans: List[SupportPlan]) -> Dict[str, Counter[int]]:
    usage: Dict[str, Counter[int]] = {}
    for plan in plans:
        spec = material_spec_label(getattr(plan, "material_spec", ""))
        counter = usage.setdefault(spec, Counter())
        for _kind, length in plan.pieces:
            counter[int(length)] += 1
    return usage


def format_material_usage_by_spec(plans: List[SupportPlan]) -> str:
    usage = material_usage_by_spec(plans)
    if not usage:
        return "無資料"
    sections = []
    for spec in sorted(usage):
        lines = [f"=== {spec} ==="]
        for length, count in sorted(usage[spec].items()):
            lines.append(f"{length} mm × {count}")
        sections.append("\n".join(lines))
    return "\n".join(sections)


def print_summary(
    context: str,
    metrics: Dict[str, object],
) -> None:
    header = f"【摘要】{context}"

    lines = [header]
    for key, value in metrics.items():
        lines.append(f"{key}: {value}")

    width = max(len(line) for line in lines) + 4
    border_top = "╔" + "═" * (width - 2) + "╗"
    border_mid = "╠" + "═" * (width - 2) + "╣"
    border_bot = "╚" + "═" * (width - 2) + "╝"

    log(border_top)
    log(f"║ {header.ljust(width - 4)} ║")
    log(border_mid)
    for line in lines[1:]:
        log(f"║ {line.ljust(width - 4)} ║")
    log(border_bot)
    log("")


def print_global_summary(solution: GlobalSolution) -> None:
    pattern_summary = pattern_diversity_summary(solution.plans)
    min_jack_distance = getattr(solution, "min_jack_distance", None)
    if min_jack_distance is None:
        jack_centers = sorted(float(plan.jack_center) for plan in solution.plans)
        if len(jack_centers) > 1:
            min_jack_distance = min(
                jack_centers[index] - jack_centers[index - 1]
                for index in range(1, len(jack_centers))
            )
    min_distance_text = (
        "無資料" if min_jack_distance is None else f"{float(min_jack_distance):.0f} mm"
    )
    valid_count = sum(plan.valid and not plan.reason for plan in solution.plans)
    single_score_total = float(
        getattr(solution, "single_score_total", sum(plan.score for plan in solution.plans))
    )
    log(
        f"全域搭配完成｜{'合法' if solution.valid else '不合法'} "
        f"{valid_count}/{len(solution.plans)} 支｜單體分數 {single_score_total:.0f}｜"
        f"最小Jack距離 {min_distance_text}｜"
        f"Pattern {pattern_summary['pattern_kind_count']} 種，"
        f"最多重複 {pattern_summary['max_pattern_usage']} 次"
    )
    if solution.reason:
        log(f"  [注意] {solution.reason}")


def build_positions(pieces: List[Tuple[str, int]]) -> List[int]:
    """
    將 pieces 轉成累積座標。
    例如 pieces: steel 5000, jack 600, steel 4000
    回傳節點位置: [0, 5000, 5600, 9600]
    """
    positions = [0]
    acc = 0
    for _, length in pieces:
        acc += length
        positions.append(acc)
    return positions


def get_joint_positions(pieces: List[Tuple[str, int]]) -> List[int]:
    """
    接頭位置定義為 piece 與 piece 之間的交界。
    不含起點 0，不含終點。
    """
    positions = build_positions(pieces)
    return positions[1:-1]


def get_jack_center(pieces: List[Tuple[str, int]]) -> float:
    acc = 0
    for kind, length in pieces:
        start = acc
        end = acc + length
        if kind == "jack":
            return (start + end) / 2
        acc = end
    return -1



def forbidden_zones(config: SupportConfig) -> List[Tuple[int, int, str]]:
    zones = []

    zones.append((0, MIN_END_CLEAR, "left_end"))
    zones.append((config.total_length - MIN_END_CLEAR, config.total_length, "right_end"))

    for p in config.pile_centers:
        zones.append((p - PILE_FORBIDDEN_HALF, p + PILE_FORBIDDEN_HALF, "pile"))

    for w in config.waler_centers:
        zones.append((w - WALER_FORBIDDEN_HALF, w + WALER_FORBIDDEN_HALF, "waler"))

    return zones


def check_joint_forbidden(joint: int, config: SupportConfig) -> bool:
    """
    True 表示此 joint 落入禁止區。
    """
    for z_start, z_end, _ in forbidden_zones(config):
        if z_start <= joint <= z_end:
            return True
    return False


def count_forbidden_joints(joints: List[int], config: SupportConfig) -> int:
    return sum(1 for j in joints if check_joint_forbidden(j, config))


# =========================================================
# 單支支撐評分
# =========================================================

def evaluate_single_support(
    config: SupportConfig,
    pieces: List[Tuple[str, int]],
    allow_invalid: bool = False
) -> SupportPlan:
    total_used = sum(length for _, length in pieces)
    gap = config.total_length - total_used

    joints = get_joint_positions(pieces)
    jack_count = sum(1 for kind, _ in pieces if kind == "jack")
    jack_center = get_jack_center(pieces)
    jack_region_id = get_jack_region_id(jack_center, config.pile_centers)

    valid = True
    reasons = []

    if jack_count != 1:
        valid = False
        reasons.append("千斤頂數量不是 1")

    if not (SUPPORT_MIN_GAP <= gap <= MAX_GAP):
        valid = False
        reasons.append(f"餘長(mm) 不合法: {gap}")

    forbidden_count = count_forbidden_joints(joints, config)
    if forbidden_count > 0:
        valid = False
        reasons.append(f"{forbidden_count} 個接頭落入禁止區")

    for kind, length in pieces:
        if kind == "steel" and length not in STEEL_LENGTHS:
            valid = False
            reasons.append(f"鋼材長度不合法: {length}")

    # -----------------------------
    # 軟限制評分：分數越小越好
    # -----------------------------
    score = 0.0

    steel_lengths = [length for kind, length in pieces if kind == "steel"]
    short_steel_count = sum(1 for x in steel_lengths if x < SUPPORT_SHORT_STEEL_THRESHOLD)

    short_penalty = short_steel_count * SUPPORT_SHORT_STEEL_PENALTY_WEIGHT
    joint_penalty = len(joints) * SUPPORT_JOINT_PENALTY_WEIGHT
    gap_penalty = abs(gap - TARGET_GAP) * SUPPORT_GAP_PENALTY_WEIGHT

    score += short_penalty
    score += joint_penalty
    score += gap_penalty

    # jack 不希望在端部區域
    jack_edge_penalty = 0
    if jack_center < SUPPORT_JACK_EDGE_CLEARANCE or jack_center > config.total_length - SUPPORT_JACK_EDGE_CLEARANCE:
        jack_edge_penalty = SUPPORT_JACK_EDGE_PENALTY
        score += jack_edge_penalty

    invalid_penalty = 0
    if not valid:
        invalid_penalty = (
            SUPPORT_INVALID_BASE_PENALTY
            + forbidden_count * SUPPORT_INVALID_FORBIDDEN_JOINT_WEIGHT
            + max(0, SUPPORT_MIN_GAP - gap) * SUPPORT_INVALID_GAP_WEIGHT
            + max(0, gap - MAX_GAP) * SUPPORT_INVALID_GAP_WEIGHT
        )
        score += invalid_penalty

    breakdown = {
        "short_penalty": float(short_penalty),
        "joint_penalty": float(joint_penalty),
        "gap_penalty": float(gap_penalty),
        "jack_edge_penalty": float(jack_edge_penalty),
        "invalid_penalty": float(invalid_penalty),
    }

    return SupportPlan(
        support_id=config.support_id,
        pieces=pieces,
        joints=joints,
        gap=gap,
        jack_center=jack_center,
        jack_region_id=jack_region_id,
        score=score,
        valid=valid or allow_invalid,
        pile_centers=list(config.pile_centers),
        waler_centers=list(config.waler_centers),
        reason="; ".join(reasons),
        breakdown=breakdown,
        material_spec=str(config.material_spec or ""),
    )


# =========================================================
# Phase 1：單支支撐候選方案生成
# =========================================================

def _keep_top_candidates(
    candidates: List[Tuple[float, Tuple[int, ...], int]],
    limit: int,
) -> List[Tuple[float, Tuple[int, ...], int]]:
    candidates.sort(key=lambda item: item[0])
    unique: Dict[Tuple[int, ...], bool] = {}
    kept: List[Tuple[float, Tuple[int, ...], int]] = []

    for score, seq, short_count in candidates:
        if seq in unique:
            continue
        unique[seq] = True
        kept.append((score, seq, short_count))
        if len(kept) >= limit:
            break

    return kept


def calculate_length_combination_prescore(
    steel_lengths: List[int],
    shim: int,
    gap: int,
) -> float:
    """Score a material combination with the known single-support rules.

    Jack position, forbidden joints, and jack-edge clearance are layout-dependent
    and are therefore left for ``evaluate_single_support``.
    """
    short_steel_count = sum(
        1
        for length in steel_lengths
        if int(length) < SUPPORT_SHORT_STEEL_THRESHOLD
    )
    piece_count = len(steel_lengths) + 1 + (1 if int(shim) > 0 else 0)
    joint_count = max(0, piece_count - 1)
    return float(
        short_steel_count * SUPPORT_SHORT_STEEL_PENALTY_WEIGHT
        + joint_count * SUPPORT_JOINT_PENALTY_WEIGHT
        + abs(int(gap) - TARGET_GAP) * SUPPORT_GAP_PENALTY_WEIGHT
    )


def _steel_order_state_penalty(sequence: Tuple[int, ...]) -> float:
    penalty = 0.0
    if not sequence:
        return penalty

    if sequence[0] < SUPPORT_SHORT_STEEL_THRESHOLD:
        penalty += SUPPORT_ORDER_FIRST_SHORT_PENALTY
    if sequence[-1] < SUPPORT_SHORT_STEEL_THRESHOLD:
        penalty += SUPPORT_ORDER_LAST_SHORT_PENALTY
    if (
        len(sequence) > 1
        and sequence[-2] < SUPPORT_SHORT_STEEL_THRESHOLD
        and sequence[-1] < SUPPORT_SHORT_STEEL_THRESHOLD
    ):
        penalty += SUPPORT_ORDER_LAST_TWO_SHORT_PENALTY
    penalty += (
        sum(1 for length in sequence if length < SUPPORT_SHORT_STEEL_THRESHOLD)
        * SUPPORT_ORDER_EACH_SHORT_PENALTY
    )
    return penalty


def generate_length_combinations_dp(
    config: SupportConfig,
    max_combinations: int = 100,
    max_states_per_sum: int = SUPPORT_DP_MAX_STATES_PER_SUM,
    max_steel_pieces: int = SUPPORT_DP_MAX_STEEL_PIECES,
    selection_strategy: str = SUPPORT_LENGTH_COMBINATION_SELECTION_STRATEGY,
    diagnostics_out: Optional[Dict[str, object]] = None,
) -> List[Dict[str, object]]:
    """
    用 DP 產生鋼材長度組合，保留前 N 名。
    回傳格式：
    [
      {"steel_lengths": [...], "shim": ..., "gap": ..., "score": ...},
      ...
    ]
    """
    max_steel_sum = config.total_length - JACK_LENGTH - min(SHIM_LENGTHS)
    if max_steel_sum < 0:
        return []

    dp: Dict[int, List[Tuple[float, Tuple[int, ...], int]]] = {
        0: [(0.0, (), 0)]
    }

    for steel in STEEL_LENGTHS:
        for total in range(steel, max_steel_sum + 1):
            if total - steel not in dp:
                continue

            candidates = dp[total - steel]
            if not candidates:
                continue

            updated = dp.get(total, [])[:]
            for base_score, seq, short_count in candidates:
                if seq and seq[-1] > steel:
                    continue
                if len(seq) >= max_steel_pieces:
                    continue

                new_seq = seq + (steel,)
                new_short = short_count + (1 if steel < SUPPORT_SHORT_STEEL_THRESHOLD else 0)
                new_score = calculate_length_combination_prescore(
                    list(new_seq),
                    shim=0,
                    gap=TARGET_GAP,
                )
                updated.append((new_score, new_seq, new_short))

            dp[total] = _keep_top_candidates(updated, max_states_per_sum)

    results: List[Dict[str, object]] = []
    seen: Dict[Tuple[Tuple[int, ...], int, int], bool] = {}

    for shim in SHIM_LENGTHS:
        for gap in range(SUPPORT_MIN_GAP, MAX_GAP + 1):
            steel_target = config.total_length - JACK_LENGTH - shim - gap
            if steel_target < 0:
                continue

            for _score, seq, _ in dp.get(steel_target, []):
                key = (seq, shim, gap)
                if key in seen:
                    continue
                seen[key] = True

                total_score = calculate_length_combination_prescore(
                    list(seq),
                    shim=shim,
                    gap=gap,
                )
                results.append({
                    "steel_lengths": list(seq),
                    "shim": shim,
                    "gap": gap,
                    "score": total_score,
                })

    results.sort(key=lambda item: combo_sort_key(item, 0))
    selected, selection_diagnostics = select_diverse_length_combinations(
        results,
        max_combinations,
        strategy=selection_strategy,
    )
    if diagnostics_out is not None:
        diagnostics_out.clear()
        diagnostics_out.update(selection_diagnostics)
        diagnostics_out["all_combinations_sample"] = [
            dict(combo)
            for combo in results[:20]
        ]
        diagnostics_out["selected_combinations_sample"] = [
            dict(combo)
            for combo in selected[:20]
        ]
    return selected


def beam_search_steel_orders(
    steel_lengths: List[int],
    beam_width: int = 50,
    max_orders: int = 50,
    diagnostics: Optional[Dict[str, object]] = None,
) -> List[List[int]]:
    initial_state = (0.0, (), Counter(steel_lengths))
    beam: List[Tuple[float, Tuple[int, ...], Counter[int]]] = [initial_state]
    completed: List[Tuple[float, Tuple[int, ...]]] = []

    while beam:
        next_beam: List[Tuple[float, Tuple[int, ...], Counter[int]]] = []

        for score, sequence, remaining in beam:
            if not remaining:
                completed.append((score, sequence))
                continue

            for steel in sorted(remaining):
                next_sequence = sequence + (steel,)
                next_remaining = remaining.copy()
                next_remaining[steel] -= 1
                if next_remaining[steel] == 0:
                    del next_remaining[steel]

                next_score = score + _steel_order_state_penalty(next_sequence)
                next_beam.append((next_score, next_sequence, next_remaining))

        if not next_beam:
            break

        if diagnostics is not None:
            diagnostics["raw_partial_state_count"] = diagnostics.get(
                "raw_partial_state_count",
                0,
            ) + len(next_beam)
            diagnostics["pruned_partial_state_count"] = diagnostics.get(
                "pruned_partial_state_count",
                0,
            ) + max(0, len(next_beam) - beam_width)

        next_beam.sort(key=lambda item: item[0])
        beam = next_beam[:beam_width]

    completed.sort(key=lambda item: item[0])
    return [list(sequence) for _, sequence in completed[:max_orders]]


def beam_search_layout(
    config: SupportConfig,
    steel_lengths: List[int],
    shim: int,
    gap: int,
    beam_width: int = 50,
    max_layouts: int = 50,
    diagnostics: Optional[Dict[str, object]] = None,
) -> List[SupportPlan]:
    local_diagnostics: Dict[str, object] = {}
    steel_orders = beam_search_steel_orders(
        steel_lengths,
        beam_width=beam_width,
        max_orders=beam_width,
        diagnostics=local_diagnostics,
    )

    candidates: List[SupportPlan] = []
    seen: Dict[Tuple[Tuple[str, int], ...], bool] = {}

    for order in steel_orders:
        steel_pieces = [("steel", length) for length in order]

        if shim > 0:
            for shim_pos in range(len(steel_pieces) + 1):
                pieces_with_shim = steel_pieces[:]
                pieces_with_shim.insert(shim_pos, ("shim", shim))

                for jack_pos in range(len(pieces_with_shim) + 1):
                    pieces = pieces_with_shim[:]
                    pieces.insert(jack_pos, ("jack", JACK_LENGTH))
                    key = tuple(pieces)
                    if key in seen:
                        continue
                    seen[key] = True
                    plan = evaluate_single_support(config, pieces)
                    candidates.append(plan)
        else:
            for jack_pos in range(len(steel_pieces) + 1):
                pieces = steel_pieces[:]
                pieces.insert(jack_pos, ("jack", JACK_LENGTH))
                key = tuple(pieces)
                if key in seen:
                    continue
                seen[key] = True
                plan = evaluate_single_support(config, pieces)
                candidates.append(plan)

    eligible_layouts = [
        plan
        for plan in candidates
        if plan.valid
        and not plan.reason
        and plan.jack_region_id == config.target_jack_region
    ]
    no_under_eligible_count = sum(
        1
        for plan in eligible_layouts
        if plan_has_no_under_4000_steel(plan)
    )
    selection_diagnostics: Dict[str, object] = {}
    selected_layouts = select_diverse_eligible_layouts(
        eligible_layouts,
        max_layouts_per_combo=max_layouts,
        jack_center_bucket_size=SUPPORT_DEFAULT_JACK_CENTER_BUCKET_SIZE,
        diagnostics=selection_diagnostics,
    )

    complete_legal_layout_count = sum(
        plan.valid and not plan.reason
        for plan in candidates
    )
    discarded_legal_target_count = max(0, len(eligible_layouts) - len(selected_layouts))
    discarded_selected_signatures = {
        layout_signature(plan)
        for plan in selected_layouts
    }
    discarded_legal_target_no_under_count = sum(
        1
        for plan in eligible_layouts
        if layout_signature(plan) not in discarded_selected_signatures
        and plan_has_no_under_4000_steel(plan)
    )

    if diagnostics is not None:
        combo_record = {
            "steel_lengths": tuple(steel_lengths),
            "shim": shim,
            "gap": gap,
            "raw_complete_layout_count": len(candidates),
            "raw_partial_state_count": int(local_diagnostics.get("raw_partial_state_count", 0) or 0),
            "pruned_partial_state_count": int(local_diagnostics.get("pruned_partial_state_count", 0) or 0),
            "complete_layout_before_validation_count": len(candidates),
            "complete_legal_layout_count": int(complete_legal_layout_count),
            "target_region_legal_layout_count": len(eligible_layouts),
            "target_region_legal_no_under_4000_count": int(no_under_eligible_count),
            "selected_by_max_layouts_per_combo_count": len(selected_layouts),
            "selected_legal_target_region_count": len(selected_layouts),
            "discarded_legal_target_region_count": discarded_legal_target_count,
            "discarded_legal_target_region_no_under_4000_count": discarded_legal_target_no_under_count,
            "layout_selection_counts": dict(selection_diagnostics.get("layout_selection_counts", {}) or {}),
            "discarded_legal_target_layout_details": list(
                selection_diagnostics.get("discarded_legal_target_layout_details", [])
                or []
            ),
        }
        diagnostics.setdefault("per_combo_layout_diagnostics", []).append(combo_record)
        diagnostics["layouts_generated"] = diagnostics.get("layouts_generated", 0) + len(candidates)
        diagnostics["raw_complete_layout_count"] = diagnostics.get("raw_complete_layout_count", 0) + len(candidates)
        diagnostics["raw_partial_state_count"] = diagnostics.get("raw_partial_state_count", 0) + combo_record["raw_partial_state_count"]
        diagnostics["pruned_partial_state_count"] = diagnostics.get("pruned_partial_state_count", 0) + combo_record["pruned_partial_state_count"]
        diagnostics["complete_layout_before_validation_count"] = diagnostics.get("complete_layout_before_validation_count", 0) + len(candidates)
        diagnostics["complete_legal_layout_count"] = diagnostics.get("complete_legal_layout_count", 0) + complete_legal_layout_count
        diagnostics["target_region_legal_layout_count"] = diagnostics.get("target_region_legal_layout_count", 0) + len(eligible_layouts)
        diagnostics["target_region_legal_no_under_4000_count"] = diagnostics.get("target_region_legal_no_under_4000_count", 0) + no_under_eligible_count
        diagnostics["selected_by_max_layouts_per_combo_count"] = diagnostics.get("selected_by_max_layouts_per_combo_count", 0) + len(selected_layouts)
        diagnostics["selected_legal_target_region_count"] = diagnostics.get("selected_legal_target_region_count", 0) + len(selected_layouts)
        diagnostics["discarded_legal_target_region_count"] = diagnostics.get("discarded_legal_target_region_count", 0) + discarded_legal_target_count
        diagnostics["discarded_legal_target_region_no_under_4000_count"] = diagnostics.get("discarded_legal_target_region_no_under_4000_count", 0) + discarded_legal_target_no_under_count
        diagnostics["layouts_before_limit"] = diagnostics.get("layouts_before_limit", 0) + len(candidates)
        diagnostics["layouts_truncated_by_limit"] = diagnostics.get(
            "layouts_truncated_by_limit",
            0,
        ) + discarded_legal_target_count
        diagnostics["region_matched"] = diagnostics.get("region_matched", 0) + sum(
            plan.jack_region_id == config.target_jack_region
            for plan in candidates
        )
        diagnostics["valid_before_region"] = diagnostics.get("valid_before_region", 0) + complete_legal_layout_count
        diagnostics["valid_region_matched"] = diagnostics.get("valid_region_matched", 0) + len(eligible_layouts)

    return selected_layouts


def _invalid_reason_statistics(plans: List[SupportPlan]) -> Counter[str]:
    statistics: Counter[str] = Counter()
    for plan in plans:
        if plan.valid and not plan.reason:
            continue
        for reason in (part.strip() for part in plan.reason.split(";") if part.strip()):
            reason_lower = reason.lower()
            if "接頭落入禁止區" in reason:
                label = "接頭落入禁止區"
            elif "餘長" in reason:
                label = "餘長不合法"
            elif "jack 數量" in reason_lower or "千斤頂數量" in reason:
                label = "千斤頂數量錯誤"
            else:
                label = reason
            statistics[label] += 1
    return statistics


def _merged_forbidden_intervals(config: SupportConfig) -> List[Tuple[int, int]]:
    intervals = sorted(
        (max(0, start), min(config.total_length, end))
        for start, end, _ in forbidden_zones(config)
        if end >= 0 and start <= config.total_length
    )
    merged: List[Tuple[int, int]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
    return merged


def _log_support_candidate_diagnostics(
    config: SupportConfig,
    max_steel_combination_count: int,
    combination_count: int,
    target_valid_candidate_count: int,
    diagnostics: Dict[str, object],
    candidates: List[SupportPlan],
    retained_layouts: List[SupportPlan],
    returned_candidates: List[SupportPlan],
) -> None:
    valid_candidates = [plan for plan in candidates if plan.valid and not plan.reason]
    returned_valid_count = sum(
        plan.valid and not plan.reason
        for plan in returned_candidates
    )
    min_candidate_pool_size = int(
        diagnostics.get("min_candidate_pool_size", target_valid_candidate_count)
    )
    final_candidate_count = int(
        diagnostics.get("final_candidate_count", target_valid_candidate_count)
    )
    benchmark = dict(diagnostics.get("candidate_benchmark", {}) or {})
    processed = int(diagnostics.get("combinations_processed", 0) or 0)
    selected_combinations = int(combination_count or max_steel_combination_count)
    raw_layout_count = int(benchmark.get("raw_layout_count", diagnostics.get("layouts_generated", 0)) or 0)
    legal_layout_count = int(benchmark.get("valid_layout_count", diagnostics.get("valid_before_region", 0)) or 0)
    target_region_count = int(benchmark.get("candidate_count_before_topn", len(valid_candidates)) or 0)
    before_stats = dict(benchmark.get("before_topn", {}) or diagnostics.get("before_selection", {}) or {})
    after_stats = dict(benchmark.get("after_topn", {}) or diagnostics.get("after_selection", {}) or {})
    selection_counts = dict(diagnostics.get("selection_counts", {}) or {})
    jack_selected = int(selection_counts.get("selected_by_jack_bucket_guarantee", 0) or 0)
    material_selected = int(selection_counts.get("selected_by_material_style_guarantee", 0) or 0)
    score_selected = int(selection_counts.get("selected_by_score_fill", 0) or 0)
    best_single_score = min((plan.score for plan in valid_candidates), default=None)
    retained_scores = [float(plan.score) for plan in returned_candidates]
    highest_retained_score = max(retained_scores, default=None)
    candidates_sufficient = returned_valid_count >= final_candidate_count

    warnings: List[str] = []
    if processed < selected_combinations:
        warnings.append(f"只處理 {processed}/{selected_combinations} 組材料組合")
    if legal_layout_count == 0:
        warnings.append("沒有配置通過幾何與禁止區檢查")
    elif target_region_count == 0:
        warnings.append("合法配置全部被目標 Jack 區域排除")
    if not candidates_sufficient:
        warnings.append(f"最終候選不足（{returned_valid_count}/{final_candidate_count}）")
    if returned_valid_count and jack_selected / returned_valid_count > 0.70:
        warnings.append("Jack 位置保障占比超過 70%，候選可能過度集中於位置多樣性")
    if returned_valid_count and score_selected == 0:
        warnings.append("沒有名額由單體分數補入，請留意保障規則是否占滿候選")
    status = "正常" if not warnings else ("不足" if not candidates_sufficient else "注意")
    best_text = "無" if best_single_score is None else f"{best_single_score:.0f}"
    highest_text = "無" if highest_retained_score is None else f"{highest_retained_score:.0f}"
    log(
        f"{config.support_id}｜材料組合 {processed}/{selected_combinations}｜"
        f"配置 {raw_layout_count} → 合法 {legal_layout_count} → 目標區域 {target_region_count}｜"
        f"候選 {len(valid_candidates)} → {returned_valid_count}｜最佳分數 {best_text}｜{status}"
    )
    log(
        f"  保留來源：Jack位置 {jack_selected}、材料型態 {material_selected}、"
        f"分數補入 {score_selected}；保留後 Jack區間 {after_stats.get('jack_bucket_count', 0)}、"
        f"Pattern {after_stats.get('unique_steel_pattern_count', 0)}；"
        f"保留分數 {best_text}～{highest_text}"
    )
    for warning in warnings:
        log(f"  [注意] {warning}")

    if DEBUG:
        log(
            f"  [詳細] 候選池：Jack中心 {before_stats.get('unique_jack_center_count', 0)}、"
            f"Jack區間 {before_stats.get('jack_bucket_count', 0)}、"
            f"Pattern {before_stats.get('unique_steel_pattern_count', 0)}、"
            f"材料型態 {before_stats.get('material_style_count', 0)}"
        )
        log(f"  [詳細] 組合處理結果：{diagnostics.get('stop_reason', '無')}")


def log_support_candidate_diagnostics(
    config: SupportConfig,
    diagnostic_record: Dict[str, object],
) -> None:
    """Log a previously collected Phase 1 diagnostic record for a cached config."""
    _log_support_candidate_diagnostics(
        config=config,
        max_steel_combination_count=int(
            diagnostic_record.get("max_steel_combination_count", 0)
        ),
        combination_count=int(diagnostic_record.get("combination_count", 0)),
        target_valid_candidate_count=int(
            diagnostic_record.get("target_valid_candidate_count", 0)
        ),
        diagnostics=dict(diagnostic_record.get("diagnostics", {})),
        candidates=list(diagnostic_record.get("candidates", [])),
        retained_layouts=list(diagnostic_record.get("retained_layouts", [])),
        returned_candidates=list(diagnostic_record.get("returned_candidates", [])),
    )


def generate_single_support_candidates(
    config: SupportConfig,
    min_candidates: int = SUPPORT_DEFAULT_FINAL_CANDIDATE_COUNT,
    max_length_combinations: int = 100,
    beam_width: int = SUPPORT_PHASE1_LAYOUT_BEAM_WIDTH,
    max_layouts_per_combo: int = SUPPORT_PHASE1_MAX_LAYOUTS_PER_COMBO,
    min_valid_candidates: Optional[int] = None,
    random_seed: Optional[int] = None,
    diagnostics_out: Optional[Dict[str, object]] = None,
    min_processed_steel_combinations: int = SUPPORT_DEFAULT_MIN_PROCESSED_STEEL_COMBINATIONS,
    min_candidate_pool_size: Optional[int] = None,
    min_unique_jack_centers: int = SUPPORT_DEFAULT_MIN_UNIQUE_JACK_CENTERS,
    min_no_under_4000_candidates: int = SUPPORT_DEFAULT_MIN_NO_UNDER_4000_CANDIDATES,
    min_unique_material_styles: int = SUPPORT_DEFAULT_MIN_UNIQUE_MATERIAL_STYLES,
    jack_center_bucket_size: float = SUPPORT_DEFAULT_JACK_CENTER_BUCKET_SIZE,
    min_candidates_per_jack_bucket: int = SUPPORT_DEFAULT_MIN_CANDIDATES_PER_JACK_BUCKET,
    min_candidates_per_material_style: int = SUPPORT_DEFAULT_MIN_CANDIDATES_PER_MATERIAL_STYLE,
    min_retained_no_under_4000_candidates: int = SUPPORT_DEFAULT_MIN_RETAINED_NO_UNDER_4000_CANDIDATES,
    final_candidate_count: Optional[int] = None,
    length_combination_selection_strategy: str = SUPPORT_LENGTH_COMBINATION_SELECTION_STRATEGY,
) -> List[SupportPlan]:
    if random_seed is not None:
        random.seed(random_seed)

    if final_candidate_count is None:
        final_candidate_count = min_candidates
    if min_candidate_pool_size is None:
        min_candidate_pool_size = (
            min_valid_candidates
            if min_valid_candidates is not None
            else SUPPORT_DEFAULT_MIN_CANDIDATE_POOL_SIZE
        )
    min_processed_steel_combinations = max(0, int(min_processed_steel_combinations))
    min_candidate_pool_size = max(0, int(min_candidate_pool_size))
    min_unique_jack_centers = max(0, int(min_unique_jack_centers))
    min_no_under_4000_candidates = max(0, int(min_no_under_4000_candidates))
    min_unique_material_styles = max(0, int(min_unique_material_styles))
    min_candidates_per_jack_bucket = max(0, int(min_candidates_per_jack_bucket))
    min_candidates_per_material_style = max(0, int(min_candidates_per_material_style))
    min_retained_no_under_4000_candidates = max(
        0,
        int(min_retained_no_under_4000_candidates),
    )
    final_candidate_count = max(0, int(final_candidate_count))
    jack_center_bucket(jack_center=0, bucket_size=jack_center_bucket_size)

    combination_diagnostics: Dict[str, object] = {}
    combinations = generate_length_combinations_dp(
        config,
        max_combinations=max_length_combinations,
        selection_strategy=length_combination_selection_strategy,
        diagnostics_out=combination_diagnostics,
    )

    candidates: List[SupportPlan] = []
    retained_layouts: List[SupportPlan] = []
    seen: Dict[Tuple[Tuple[str, int], ...], bool] = {}
    valid_count = 0
    jack_center_buckets = set()
    no_under_4000_candidate_count = 0
    steel_patterns = set()
    material_styles = set()
    diagnostics: Dict[str, object] = {
        "min_processed_steel_combinations": min_processed_steel_combinations,
        "min_candidate_pool_size": min_candidate_pool_size,
        "min_unique_jack_centers": min_unique_jack_centers,
        "min_no_under_4000_candidates": min_no_under_4000_candidates,
        "min_unique_material_styles": min_unique_material_styles,
        "jack_center_bucket_size": jack_center_bucket_size,
        "final_candidate_count": final_candidate_count,
        "min_candidates_per_jack_bucket": min_candidates_per_jack_bucket,
        "min_candidates_per_material_style": min_candidates_per_material_style,
        "min_retained_no_under_4000_candidates": min_retained_no_under_4000_candidates,
        "length_combination_selection_strategy": length_combination_selection_strategy,
        "length_combination_selection": dict(combination_diagnostics),
    }

    for combo in combinations:
        diagnostics["combinations_processed"] = diagnostics.get("combinations_processed", 0) + 1
        layouts = beam_search_layout(
            config,
            combo["steel_lengths"],
            combo["shim"],
            combo["gap"],
            beam_width=beam_width,
            max_layouts=max_layouts_per_combo,
            diagnostics=diagnostics,
        )
        retained_layouts.extend(layouts)
        diagnostics["layouts_retained"] = diagnostics.get("layouts_retained", 0) + len(layouts)

        for plan in layouts:
            if plan.jack_region_id != config.target_jack_region:
                continue
            diagnostics["region_matched_retained"] = diagnostics.get("region_matched_retained", 0) + 1
            key = tuple(plan.pieces)
            if key in seen:
                continue
            seen[key] = True
            candidates.append(plan)
            if plan.valid and not plan.reason:
                valid_count += 1
                jack_center_buckets.add(
                    jack_center_bucket(
                        plan.jack_center,
                        jack_center_bucket_size,
                    )
                )
                if not any(
                    str(kind).lower() == "steel"
                    and int(length) < SUPPORT_SHORT_STEEL_THRESHOLD
                    for kind, length in plan.pieces
                ):
                    no_under_4000_candidate_count += 1
                steel_patterns.add(steel_pattern_from_plan(plan))
                material_styles.add(material_style_from_plan(plan))

        diagnostics["unique_jack_center_buckets"] = len(jack_center_buckets)
        diagnostics["no_under_4000_candidates"] = no_under_4000_candidate_count
        diagnostics["unique_steel_patterns"] = len(steel_patterns)
        diagnostics["unique_material_styles"] = len(material_styles)
        diagnostics["candidate_pool_valid_count"] = valid_count

    candidates.sort(key=lambda x: x.score)
    final_valid_plans = [plan for plan in candidates if plan.valid and not plan.reason]
    returned_candidates, selection_diagnostics = select_diverse_top_candidates(
        final_valid_plans,
        final_candidate_count=final_candidate_count,
        jack_center_bucket_size=jack_center_bucket_size,
        min_candidates_per_jack_bucket=min_candidates_per_jack_bucket,
        min_candidates_per_material_style=min_candidates_per_material_style,
        min_retained_no_under_4000_candidates=min_retained_no_under_4000_candidates,
    )
    if not returned_candidates:
        returned_candidates = candidates[:final_candidate_count]
    diagnostics.setdefault("stop_reason", "已完整處理選入的鋼材組合")
    diagnostics["unique_jack_center_buckets"] = len(jack_center_buckets)
    diagnostics["no_under_4000_candidates"] = no_under_4000_candidate_count
    diagnostics["unique_steel_patterns"] = len(steel_patterns)
    diagnostics["unique_material_styles"] = len(material_styles)
    diagnostics["candidate_pool_valid_count"] = valid_count
    diagnostics.update(selection_diagnostics)
    candidate_benchmark = support_candidate_benchmark_summary(
        config=config,
        combination_count=len(combinations),
        diagnostics=diagnostics,
        candidate_pool=final_valid_plans,
        returned_candidates=returned_candidates,
        jack_center_bucket_size=jack_center_bucket_size,
    )
    diagnostics["candidate_benchmark"] = candidate_benchmark

    diagnostic_record: Dict[str, object] = {
        "max_steel_combination_count": max_length_combinations,
        "combination_count": len(combinations),
        "target_valid_candidate_count": final_candidate_count,
        "final_candidate_count": final_candidate_count,
        "min_candidate_pool_size": min_candidate_pool_size,
        "diagnostics": dict(diagnostics),
        "candidates": list(candidates),
        "retained_layouts": sorted(retained_layouts, key=lambda plan: plan.score)[:10],
        "returned_candidates": list(returned_candidates),
    }
    if diagnostics_out is not None:
        diagnostics_out.clear()
        diagnostics_out.update(diagnostic_record)
    log_support_candidate_diagnostics(config, diagnostic_record)

    return returned_candidates


# =========================================================
# Phase 2：多支支撐整體最佳化
# =========================================================

def default_material_ratio_targets() -> Dict[str, float]:
    return normalize_material_ratio_targets(
        SUPPORT_DEFAULT_SHORT_MATERIAL_RATIO,
        SUPPORT_DEFAULT_MID_MATERIAL_RATIO,
        SUPPORT_DEFAULT_LONG_MATERIAL_RATIO,
    )


def normalize_material_ratio_targets(
    short_ratio: float,
    mid_ratio: float,
    long_ratio: float,
) -> Dict[str, float]:
    values = [float(short_ratio), float(mid_ratio), float(long_ratio)]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("材料比例必須是有效數字。")
    if any(value < 0 for value in values):
        raise ValueError("材料比例不可小於 0。")
    total = sum(values)
    if total <= 0:
        raise ValueError("材料比例總和必須大於 0。")
    return {
        "short": values[0] / total,
        "mid": values[1] / total,
        "long": values[2] / total,
    }


def _waler_length_classification_config(targets: Dict[str, float], weight: float) -> wales.Config:
    cfg = wales.Config(total_length=0, support_points=[])
    cfg.short_segment_ratio_target = float(targets.get("short", 0.0))
    cfg.mid_segment_ratio_target = float(targets.get("mid", 0.0))
    cfg.long_segment_ratio_target = float(targets.get("long", 0.0))
    cfg.ratio_penalty_weight = float(weight)
    return cfg


def support_steel_lengths(plans: List[SupportPlan]) -> List[int]:
    lengths: List[int] = []
    for plan in plans:
        for kind, length in getattr(plan, "pieces", []) or []:
            if str(kind).lower() == "steel":
                lengths.append(int(length))
    return lengths


def calculate_material_ratio_analysis(
    plans: List[SupportPlan],
    material_ratio_targets: Optional[Dict[str, float]] = None,
    material_ratio_weight: float = SUPPORT_MATERIAL_RATIO_WEIGHT,
) -> Dict[str, object]:
    targets = dict(material_ratio_targets or default_material_ratio_targets())
    weight = float(material_ratio_weight)
    cfg = _waler_length_classification_config(targets, weight)
    steel_lengths = support_steel_lengths(plans)
    counts = {"short": 0, "mid": 0, "long": 0}
    out_count = 0
    for length in steel_lengths:
        category = wales.classify_length(length, cfg)
        if category in counts:
            counts[category] += 1
        else:
            out_count += 1

    classified_total = sum(counts.values())
    if classified_total > 0:
        actual_ratios = {
            key: counts[key] / classified_total
            for key in counts
        }
    else:
        actual_ratios = {key: 0.0 for key in counts}

    ratio_deviation = sum(
        abs(actual_ratios[key] - float(targets.get(key, 0.0)))
        for key in counts
    )
    penalty = ratio_deviation * weight
    return {
        "counts": counts,
        "ratios": actual_ratios,
        "targets": targets,
        "ratio_deviation": ratio_deviation,
        "penalty": penalty,
        "weight": weight,
        "classified_total": classified_total,
        "total_steel_count": len(steel_lengths),
        "out_count": out_count,
    }


def calculate_material_concentration_analysis(
    plans: List[SupportPlan],
    material_concentration_threshold: float = SUPPORT_MATERIAL_CONCENTRATION_THRESHOLD,
    material_concentration_weight: float = SUPPORT_MATERIAL_CONCENTRATION_WEIGHT,
) -> Dict[str, object]:
    threshold = float(material_concentration_threshold)
    weight = float(material_concentration_weight)
    if threshold < 0:
        raise ValueError("material_concentration_threshold must be >= 0")

    steel_lengths = support_steel_lengths(plans)
    total_steel_count = len(steel_lengths)
    usage_counter: Counter[int] = Counter(steel_lengths)
    spec_breakdown: Dict[int, Dict[str, float]] = {}
    penalty = 0.0

    for spec in sorted(STEEL_LENGTHS):
        count = int(usage_counter.get(int(spec), 0))
        ratio = count / total_steel_count if total_steel_count else 0.0
        excess = max(0.0, ratio - threshold)
        spec_penalty = excess * weight
        penalty += spec_penalty
        spec_breakdown[int(spec)] = {
            "count": count,
            "ratio": ratio,
            "excess": excess,
            "penalty": spec_penalty,
        }

    return {
        "spec_usage": dict(sorted((int(k), int(v)) for k, v in usage_counter.items())),
        "spec_breakdown": spec_breakdown,
        "total_steel_count": total_steel_count,
        "threshold": threshold,
        "weight": weight,
        "penalty": penalty,
    }


def summarize_global_solution_scores(
    plans: List[SupportPlan],
    material_ratio_targets: Optional[Dict[str, float]] = None,
    material_ratio_weight: float = SUPPORT_MATERIAL_RATIO_WEIGHT,
    material_concentration_threshold: float = SUPPORT_MATERIAL_CONCENTRATION_THRESHOLD,
    material_concentration_weight: float = SUPPORT_MATERIAL_CONCENTRATION_WEIGHT,
) -> Dict[str, object]:
    single_score_total = sum(float(getattr(plan, "score", 0.0) or 0.0) for plan in plans)
    jack_region_penalty = 0.0
    min_jack_distance: Optional[float] = None
    valid_pairs = True
    for prev_plan, curr_plan in zip(plans, plans[1:]):
        distance = abs(float(getattr(prev_plan, "jack_center", 0.0) or 0.0) - float(getattr(curr_plan, "jack_center", 0.0) or 0.0))
        min_jack_distance = distance if min_jack_distance is None else min(min_jack_distance, distance)
        ok, penalty = pair_penalty(prev_plan, curr_plan)
        if not ok:
            valid_pairs = False
        else:
            jack_region_penalty += float(penalty)

    material_ratio_analysis = calculate_material_ratio_analysis(
        plans,
        material_ratio_targets=material_ratio_targets,
        material_ratio_weight=material_ratio_weight,
    )
    material_ratio_penalty = float(material_ratio_analysis["penalty"])
    material_concentration_analysis = calculate_material_concentration_analysis(
        plans,
        material_concentration_threshold=material_concentration_threshold,
        material_concentration_weight=material_concentration_weight,
    )
    material_concentration_penalty = float(material_concentration_analysis["penalty"])
    total_score = (
        single_score_total
        + jack_region_penalty
        + material_ratio_penalty
        + material_concentration_penalty
    )
    return {
        "single_score_total": single_score_total,
        "jack_region_penalty": jack_region_penalty,
        "material_ratio_penalty": material_ratio_penalty,
        "material_ratio_analysis": material_ratio_analysis,
        "material_ratio_targets": dict(material_ratio_analysis["targets"]),
        "material_ratio_weight": float(material_ratio_analysis["weight"]),
        "material_concentration_penalty": material_concentration_penalty,
        "material_concentration_analysis": material_concentration_analysis,
        "material_concentration_threshold": float(material_concentration_analysis["threshold"]),
        "material_concentration_weight": float(material_concentration_analysis["weight"]),
        "min_jack_distance": min_jack_distance,
        "total_score": total_score,
        "valid_pairs": valid_pairs,
    }


def make_global_solution(
    plans: List[SupportPlan],
    *,
    material_ratio_targets: Optional[Dict[str, float]] = None,
    material_ratio_weight: float = SUPPORT_MATERIAL_RATIO_WEIGHT,
    material_concentration_threshold: float = SUPPORT_MATERIAL_CONCENTRATION_THRESHOLD,
    material_concentration_weight: float = SUPPORT_MATERIAL_CONCENTRATION_WEIGHT,
    valid: Optional[bool] = None,
    reason: str = "",
) -> GlobalSolution:
    score_summary = summarize_global_solution_scores(
        plans,
        material_ratio_targets=material_ratio_targets,
        material_ratio_weight=material_ratio_weight,
        material_concentration_threshold=material_concentration_threshold,
        material_concentration_weight=material_concentration_weight,
    )
    solution_valid = (
        all(plan.valid and not plan.reason for plan in plans)
        and bool(score_summary["valid_pairs"])
        if valid is None
        else bool(valid)
    )
    return GlobalSolution(
        plans=list(plans),
        total_score=float(score_summary["total_score"]),
        valid=solution_valid,
        reason=reason,
        single_score_total=float(score_summary["single_score_total"]),
        jack_region_penalty=float(score_summary["jack_region_penalty"]),
        material_ratio_penalty=float(score_summary["material_ratio_penalty"]),
        material_ratio_analysis=dict(score_summary["material_ratio_analysis"]),
        material_ratio_targets=dict(score_summary["material_ratio_targets"]),
        material_ratio_weight=float(score_summary["material_ratio_weight"]),
        material_concentration_penalty=float(score_summary["material_concentration_penalty"]),
        material_concentration_analysis=dict(score_summary["material_concentration_analysis"]),
        material_concentration_threshold=float(score_summary["material_concentration_threshold"]),
        material_concentration_weight=float(score_summary["material_concentration_weight"]),
        min_jack_distance=score_summary["min_jack_distance"],
    )


def count_under_4000_steel_in_plans(plans: List[SupportPlan]) -> int:
    return sum(
        1
        for plan in plans
        for kind, length in getattr(plan, "pieces", []) or []
        if str(kind).lower() == "steel"
        and int(length) < SUPPORT_SHORT_STEEL_THRESHOLD
    )


def count_steel_length_in_plans(plans: List[SupportPlan], target_length: int) -> int:
    return sum(
        1
        for plan in plans
        for kind, length in getattr(plan, "pieces", []) or []
        if str(kind).lower() == "steel"
        and int(length) == int(target_length)
    )


def support_pattern_counts(plans: List[SupportPlan]) -> Counter[Tuple[int, ...]]:
    return Counter(steel_pattern_from_plan(plan) for plan in plans)


def pattern_concentration(pattern_counts: Counter[Tuple[int, ...]]) -> int:
    return sum(int(count) * int(count) for count in pattern_counts.values())


def pattern_diversity_summary(plans: List[SupportPlan]) -> Dict[str, object]:
    counts = support_pattern_counts(plans)
    return {
        "pattern_kind_count": len(counts),
        "max_pattern_usage": max(counts.values(), default=0),
        "pattern_concentration": pattern_concentration(counts),
        "pattern_usage": [
            {
                "pattern": list(pattern),
                "count": int(count),
            }
            for pattern, count in sorted(
                counts.items(),
                key=lambda item: (-int(item[1]), item[0]),
            )
        ],
    }


def _pattern_tie_break_key(
    total_score: float,
    pattern_counts: Counter[Tuple[int, ...]],
    selected_indices: List[int],
) -> Tuple[float, int, int, Tuple[int, ...]]:
    return (
        float(total_score),
        max(pattern_counts.values(), default=0),
        pattern_concentration(pattern_counts),
        tuple(int(index) for index in selected_indices),
    )


def _beam_state_plans(state) -> List[SupportPlan]:
    if len(state) >= 7:
        return state[5]
    return state[3]


def _beam_state_snapshot(
    beam: List[Tuple],
) -> Dict[str, object]:
    terminal_jack_counts: Counter[object] = Counter()
    under_4000_distribution: Counter[int] = Counter()
    max_pattern_usage_distribution: Counter[int] = Counter()
    pattern_concentration_distribution: Counter[int] = Counter()
    for state in beam:
        plans = _beam_state_plans(state)
        if plans:
            terminal_jack_counts[
                _stable_cache_number(plans[-1].jack_center)
            ] += 1
        under_4000_distribution[count_under_4000_steel_in_plans(plans)] += 1
        pattern_summary = pattern_diversity_summary(plans)
        max_pattern_usage_distribution[int(pattern_summary["max_pattern_usage"])] += 1
        pattern_concentration_distribution[int(pattern_summary["pattern_concentration"])] += 1

    state_count = len(beam)
    dominant_terminal_jack_center = None
    dominant_terminal_jack_ratio = 0.0
    if state_count and terminal_jack_counts:
        dominant_terminal_jack_center, dominant_count = max(
            terminal_jack_counts.items(),
            key=lambda item: (item[1], item[0]),
        )
        dominant_terminal_jack_ratio = dominant_count / state_count

    return {
        "state_count": state_count,
        "terminal_jack_center_count": len(terminal_jack_counts),
        "terminal_jack_center_distribution": dict(
            sorted(terminal_jack_counts.items())
        ),
        "under_4000_state_distribution": dict(
            sorted(under_4000_distribution.items())
        ),
        "max_pattern_usage_state_distribution": dict(
            sorted(max_pattern_usage_distribution.items())
        ),
        "pattern_concentration_state_distribution": dict(
            sorted(pattern_concentration_distribution.items())
        ),
        "terminal_jack_center_over_50_percent": (
            dominant_terminal_jack_ratio > 0.5
        ),
        "dominant_terminal_jack_center": dominant_terminal_jack_center,
        "dominant_terminal_jack_ratio": dominant_terminal_jack_ratio,
    }


def global_solution_result_summary(solution: GlobalSolution) -> Dict[str, object]:
    plans = list(getattr(solution, "plans", []) or [])
    short_penalty = sum(
        float(plan.breakdown.get("short_penalty", 0.0) or 0.0)
        for plan in plans
    )
    joint_penalty = sum(
        float(plan.breakdown.get("joint_penalty", 0.0) or 0.0)
        for plan in plans
    )
    gap_penalty = sum(
        float(plan.breakdown.get("gap_penalty", 0.0) or 0.0)
        for plan in plans
    )
    ratio_analysis = dict(getattr(solution, "material_ratio_analysis", {}) or {})
    concentration_analysis = dict(getattr(solution, "material_concentration_analysis", {}) or {})
    steel_lengths = support_steel_lengths(plans)
    material_specs = {
        str(getattr(plan, "material_spec", "") or "").strip()
        for plan in plans
    }
    material_specs.discard("")
    min_distance = getattr(solution, "min_jack_distance", None)
    return {
        "total_score": float(getattr(solution, "total_score", 0.0) or 0.0),
        "single_score_total": float(getattr(solution, "single_score_total", 0.0) or 0.0),
        "short_steel_penalty": short_penalty,
        "joint_penalty": joint_penalty,
        "gap_penalty": gap_penalty,
        "jack_region_penalty": float(getattr(solution, "jack_region_penalty", 0.0) or 0.0),
        "material_ratio_penalty": float(getattr(solution, "material_ratio_penalty", 0.0) or 0.0),
        "material_concentration_penalty": float(getattr(solution, "material_concentration_penalty", 0.0) or 0.0),
        "material_concentration_spec_usage": dict(concentration_analysis.get("spec_usage", {}) or {}),
        "material_concentration_threshold": float(getattr(solution, "material_concentration_threshold", 0.0) or 0.0),
        "material_concentration_weight": float(getattr(solution, "material_concentration_weight", 0.0) or 0.0),
        "steel_3500_count": count_steel_length_in_plans(plans, 3500),
        "under_4000_steel_count": count_under_4000_steel_in_plans(plans),
        "material_ratio_counts": dict(ratio_analysis.get("counts", {}) or {}),
        "material_ratio_values": dict(ratio_analysis.get("ratios", {}) or {}),
        "distinct_steel_length_count": len(set(steel_lengths)),
        "distinct_material_spec_count": len(material_specs),
        **pattern_diversity_summary(plans),
        "min_adjacent_jack_distance": min_distance,
        "min_adjacent_jack_distance_margin": (
            None
            if min_distance is None
            else float(min_distance) - MIN_JACK_DISTANCE_BETWEEN_SUPPORTS
        ),
    }


def pair_penalty(prev: SupportPlan, curr: SupportPlan) -> Tuple[bool, float]:
    """
    回傳：
    - 是否符合相鄰 jack 間距硬限制
    - pair 軟限制懲罰
    """
    distance = abs(prev.jack_center - curr.jack_center)

    if distance < MIN_JACK_DISTANCE_BETWEEN_SUPPORTS:
        return False, 1_000_000

    penalty = 0.0

    # 儘量讓 jack 在相同 region
    if prev.jack_region_id != curr.jack_region_id:
        penalty += 3000 * abs(prev.jack_region_id - curr.jack_region_id)

    return True, penalty


def build_global_solution(
    candidates_by_support: List[List[SupportPlan]],
    beam_width: int = 80,
    material_ratio_targets: Optional[Dict[str, float]] = None,
    material_ratio_weight: float = SUPPORT_MATERIAL_RATIO_WEIGHT,
    material_concentration_threshold: float = SUPPORT_MATERIAL_CONCENTRATION_THRESHOLD,
    material_concentration_weight: float = SUPPORT_MATERIAL_CONCENTRATION_WEIGHT,
    diagnostics_out: Optional[Dict[str, object]] = None,
) -> GlobalSolution:
    """
    使用 beam search 選出整體解。
    避免所有組合暴力枚舉。
    """

    log(f"全域最佳化開始：支撐數量={len(candidates_by_support)}")

    phase2_diagnostics: Dict[str, object] = {
        "beam_width": int(beam_width),
        "support_count": len(candidates_by_support),
        "steps": [],
    }

    if not candidates_by_support:
        solution = make_global_solution(
            [],
            material_ratio_targets=material_ratio_targets,
            material_ratio_weight=material_ratio_weight,
            material_concentration_threshold=material_concentration_threshold,
            material_concentration_weight=material_concentration_weight,
            valid=False,
            reason="沒有候選資料",
        )
        phase2_diagnostics["result_summary"] = global_solution_result_summary(solution)
        if diagnostics_out is not None:
            diagnostics_out.clear()
            diagnostics_out.update(phase2_diagnostics)
        print_global_summary(solution)
        return solution

    ratio_targets = dict(material_ratio_targets or default_material_ratio_targets())

    # beam item:
    # (sort_key, total_score, single_score_total, jack_region_penalty,
    #  pattern_counts, plans, candidate_indices)
    beam: List[Tuple[
        Tuple[float, int, int, Tuple[int, ...]],
        float,
        float,
        float,
        Counter[Tuple[int, ...]],
        List[SupportPlan],
        List[int],
    ]] = []
    for candidate_index, plan in enumerate(candidates_by_support[0]):
        single_score_total = float(plan.score)
        material_ratio_analysis = calculate_material_ratio_analysis(
            [plan],
            material_ratio_targets=ratio_targets,
            material_ratio_weight=material_ratio_weight,
        )
        material_concentration_analysis = calculate_material_concentration_analysis(
            [plan],
            material_concentration_threshold=material_concentration_threshold,
            material_concentration_weight=material_concentration_weight,
        )
        total_score = (
            single_score_total
            + float(material_ratio_analysis["penalty"])
            + float(material_concentration_analysis["penalty"])
        )
        pattern_counts = support_pattern_counts([plan])
        selected_indices = [candidate_index]
        beam.append((
            _pattern_tie_break_key(total_score, pattern_counts, selected_indices),
            total_score,
            single_score_total,
            0.0,
            pattern_counts,
            [plan],
            selected_indices,
        ))

    beam.sort(key=lambda x: x[0])
    initial_generated_count = len(beam)
    beam = beam[:beam_width]
    phase2_diagnostics["steps"].append({
        "support_index": 0,
        "support_id": (
            candidates_by_support[0][0].support_id
            if candidates_by_support[0]
            else ""
        ),
        "beam_state_count_before_adding_support": 0,
        "generated_state_count": initial_generated_count,
        "beam_state_count_after_pruning": len(beam),
        **_beam_state_snapshot(beam),
    })

    for support_idx in range(1, len(candidates_by_support)):
        new_beam: List[Tuple[
            Tuple[float, int, int, Tuple[int, ...]],
            float,
            float,
            float,
            Counter[Tuple[int, ...]],
            List[SupportPlan],
            List[int],
        ]] = []
        beam_state_count_before = len(beam)

        for (
            _sort_key,
            _current_score,
            single_score_total,
            jack_region_penalty,
            pattern_counts,
            selected_plans,
            selected_indices,
        ) in beam:
            prev_plan = selected_plans[-1]

            for candidate_index, candidate in enumerate(candidates_by_support[support_idx]):
                ok, penalty = pair_penalty(prev_plan, candidate)

                if not ok:
                    continue

                new_plans = selected_plans + [candidate]
                new_indices = selected_indices + [candidate_index]
                new_single_score_total = single_score_total + float(candidate.score)
                new_jack_region_penalty = jack_region_penalty + float(penalty)
                material_ratio_analysis = calculate_material_ratio_analysis(
                    new_plans,
                    material_ratio_targets=ratio_targets,
                    material_ratio_weight=material_ratio_weight,
                )
                material_concentration_analysis = calculate_material_concentration_analysis(
                    new_plans,
                    material_concentration_threshold=material_concentration_threshold,
                    material_concentration_weight=material_concentration_weight,
                )
                new_score = (
                    new_single_score_total
                    + new_jack_region_penalty
                    + float(material_ratio_analysis["penalty"])
                    + float(material_concentration_analysis["penalty"])
                )
                new_pattern_counts = pattern_counts.copy()
                new_pattern_counts[steel_pattern_from_plan(candidate)] += 1
                sort_key = _pattern_tie_break_key(
                    new_score,
                    new_pattern_counts,
                    new_indices,
                )
                new_beam.append((
                    sort_key,
                    new_score,
                    new_single_score_total,
                    new_jack_region_penalty,
                    new_pattern_counts,
                    new_plans,
                    new_indices,
                ))

        new_beam.sort(key=lambda x: x[0])
        generated_state_count = len(new_beam)
        beam = new_beam[:beam_width]
        phase2_diagnostics["steps"].append({
            "support_index": support_idx,
            "support_id": (
                candidates_by_support[support_idx][0].support_id
                if candidates_by_support[support_idx]
                else ""
            ),
            "beam_state_count_before_adding_support": beam_state_count_before,
            "generated_state_count": generated_state_count,
            "beam_state_count_after_pruning": len(beam),
            **_beam_state_snapshot(beam),
        })

        if not beam:
            solution = fallback_global_solution(
                candidates_by_support,
                material_ratio_targets=ratio_targets,
                material_ratio_weight=material_ratio_weight,
                material_concentration_threshold=material_concentration_threshold,
                material_concentration_weight=material_concentration_weight,
            )
            phase2_diagnostics["selected_candidate_indices"] = []
            phase2_diagnostics["adjacent_jack_distances"] = [
                abs(curr.jack_center - prev.jack_center)
                for prev, curr in zip(solution.plans, solution.plans[1:])
            ]
            phase2_diagnostics["result_summary"] = global_solution_result_summary(solution)
            if diagnostics_out is not None:
                diagnostics_out.clear()
                diagnostics_out.update(phase2_diagnostics)
            print_global_summary(solution)
            return solution

    (
        _best_sort_key,
        _best_score,
        _single_score_total,
        _jack_region_penalty,
        _best_pattern_counts,
        best_plans,
        best_candidate_indices,
    ) = beam[0]
    solution = make_global_solution(
        best_plans,
        material_ratio_targets=ratio_targets,
        material_ratio_weight=material_ratio_weight,
        material_concentration_threshold=material_concentration_threshold,
        material_concentration_weight=material_concentration_weight,
        reason="",
    )
    phase2_diagnostics["selected_candidate_indices"] = list(best_candidate_indices)
    phase2_diagnostics["selected_candidates"] = [
        {
            "support_id": plan.support_id,
            "candidate_index": index,
            "pieces": list(plan.pieces),
            "jack_center": plan.jack_center,
            "score": plan.score,
            "steel_pattern": steel_pattern_from_plan(plan),
        }
        for index, plan in zip(best_candidate_indices, best_plans)
    ]
    phase2_diagnostics["adjacent_jack_distances"] = [
        abs(curr.jack_center - prev.jack_center)
        for prev, curr in zip(solution.plans, solution.plans[1:])
    ]
    phase2_diagnostics["result_summary"] = global_solution_result_summary(solution)
    if diagnostics_out is not None:
        diagnostics_out.clear()
        diagnostics_out.update(phase2_diagnostics)
    print_global_summary(solution)
    return solution


def fallback_global_solution(
    candidates_by_support: List[List[SupportPlan]],
    material_ratio_targets: Optional[Dict[str, float]] = None,
    material_ratio_weight: float = SUPPORT_MATERIAL_RATIO_WEIGHT,
    material_concentration_threshold: float = SUPPORT_MATERIAL_CONCENTRATION_THRESHOLD,
    material_concentration_weight: float = SUPPORT_MATERIAL_CONCENTRATION_WEIGHT,
) -> GlobalSolution:
    """
    若 Phase 2 找不到完全符合 jack 間距的組合，
    則選每支支撐單體分數最低者，並標記為 fallback。
    """
    plans = []

    for candidates in candidates_by_support:
        if candidates:
            plans.append(min(candidates, key=lambda x: x.score))

    solution = make_global_solution(
        plans,
        material_ratio_targets=material_ratio_targets,
        material_ratio_weight=material_ratio_weight,
        material_concentration_threshold=material_concentration_threshold,
        material_concentration_weight=material_concentration_weight,
        valid=False,
        reason="找不到完全符合相鄰 jack 間距的整體解，已回傳 fallback",
    )
    solution.total_score += 5_000_000
    return solution


# =========================================================
# 輸出工具

def get_jack_region_id(jack_center: float, pile_centers: List[int]) -> int:
    """根據 pile_centers 定義區域，確定 jack_center 所在的區間。

    無樁時回傳 1；若 jack_center < 0 回傳 -1。
    區域編號從 1 開始。
    """
    if jack_center < 0:
        return -1

    if not pile_centers:
        return 1

    sorted_piles = sorted(pile_centers)
    if jack_center < sorted_piles[0]:
        return 1

    for i in range(len(sorted_piles) - 1):
        if sorted_piles[i] <= jack_center < sorted_piles[i + 1]:
            return i + 2

    return len(sorted_piles) + 1


def print_plan(plan: SupportPlan) -> None:
    pieces_str = format_pieces_for_display(plan.pieces)
    valid_str = "是" if plan.valid and not plan.reason else "否"
    log(f"    分數: {plan.score:.1f} | 合法: {valid_str} | 餘長(mm): {plan.gap} | 千斤頂: {plan.jack_center:.1f} | 區域: {plan.jack_region_id}")
    log(f"      材料規格: {str(plan.material_spec or '').strip()}")
    log(f"      片段: [{pieces_str}]")
    if plan.reason:
        log(f"      原因: {plan.reason}")


def format_plan_compact(plan: SupportPlan) -> str:
    pieces_str = format_pieces_for_display(plan.pieces)
    valid_str = "是" if plan.valid and not plan.reason else "否"
    base = (
        f"分數:{plan.score:.1f} | 合法:{valid_str} | 餘長(mm):{plan.gap} | "
        f"千斤頂:{plan.jack_center:.1f} | 區域:{plan.jack_region_id} | "
        f"材料規格:{str(plan.material_spec or '').strip()} | 片段:[{pieces_str}]"
    )
    if plan.reason:
        return f"{base} | 原因:{plan.reason}"
    return base


def print_global_solution(solution: GlobalSolution) -> None:
    total_gap = 0
    for plan in solution.plans:
        total_gap += plan.gap
    ratio_analysis = dict(getattr(solution, "material_ratio_analysis", {}) or {})
    counts = dict(ratio_analysis.get("counts", {}) or {})
    ratios = dict(ratio_analysis.get("ratios", {}) or {})
    targets = dict(ratio_analysis.get("targets", {}) or {})
    classified_total = int(ratio_analysis.get("classified_total", 0) or 0)

    log("===================================================")
    log("整體解摘要")
    log(f"  總分: {solution.total_score:.1f}")
    log(f"  是否合法: {'是' if solution.valid else '否'}")
    log(f"  千斤頂間距：{JACK_SPACING} mm")
    log("  群組評分:")
    log(f"    Jack Region 懲罰: {solution.jack_region_penalty:.1f}")
    log(f"    Material Ratio Weight: {solution.material_ratio_weight:.0f}")
    log(f"    材料比例懲罰: {solution.material_ratio_penalty:.2f}")
    log(f"    群組懲罰合計: {(solution.jack_region_penalty + solution.material_ratio_penalty):.2f}")
    if solution.min_jack_distance is not None:
        log(f"    最小相鄰 Jack 距離: {solution.min_jack_distance:.1f} mm")
        log(f"    規定最小距離: {MIN_JACK_DISTANCE_BETWEEN_SUPPORTS} mm")
    log("  材料比例:")
    for key, label in (("short", "短料"), ("mid", "中料"), ("long", "長料")):
        actual = float(ratios.get(key, 0.0))
        target = float(targets.get(key, 0.0))
        count = int(counts.get(key, 0) or 0)
        log(
            f"    {label}: {actual:.2%}（{count}支/{classified_total}支） "
            f"目標 {target:.2%}"
        )
    log(f"    比例偏差: {float(ratio_analysis.get('ratio_deviation', 0.0) or 0.0):.4f}")
    log("  最佳解使用材料：")
    pattern_summary = pattern_diversity_summary(solution.plans)
    log("  Pattern Diversity:")
    log(f"    Pattern種類數: {pattern_summary['pattern_kind_count']}")
    log(f"    最大Pattern使用次數: {pattern_summary['max_pattern_usage']}")
    log(f"    Pattern Concentration: {pattern_summary['pattern_concentration']}")
    for item in pattern_summary["pattern_usage"]:
        pattern_text = "(" + ",".join(str(length) for length in item["pattern"]) + ")"
        log(f"    {pattern_text} × {item['count']}")
    for line in format_material_usage_by_spec(solution.plans).splitlines():
        log(f"    {line}")
    log(f"  剩料統計：總餘長 {total_gap} mm")
    if solution.reason:
        log(f"  說明: {solution.reason}")
    log("---------------------------------------------------")
    for idx, p in enumerate(solution.plans, 1):
        log(f"支撐 {idx}：")
        print_plan(p)
