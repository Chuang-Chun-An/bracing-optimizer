from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import Counter
import random
import math

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


def get_support_config_key(config: SupportConfig) -> Tuple[int, Tuple[int, ...], Tuple[int, ...], int]:
    return (
        config.total_length,
        tuple(config.pile_centers),
        tuple(config.waler_centers),
        config.target_jack_region,
    )


def clone_plan_with_support_id(plan: SupportPlan, support_id: str) -> SupportPlan:
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
    )


@dataclass
class GlobalSolution:
    plans: List[SupportPlan]
    total_score: float
    valid: bool
    reason: str = ""


# =========================================================
# 基本參數
# =========================================================

STEEL_LENGTHS = [
    1000, 1500, 2000, 2500, 3000, 3500,
    4000, 4500, 5000, 5500, 6000,
    6500, 7000, 7500, 8000, 8500,
    9000, 9500, 10000
]

JACK_LENGTH = 600
SHIM_LENGTHS = [0, 100, 150, 200, 300]

MAX_GAP = 150
TARGET_GAP = 80

MIN_END_CLEAR = 1600
PILE_FORBIDDEN_HALF = 730
WALER_FORBIDDEN_HALF = 1130

MIN_JACK_DISTANCE_BETWEEN_SUPPORTS = 600

# Debug
DEBUG = False

logger = None


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
    jack_centers: List[float] = []
    region_counts: Dict[int, int] = {}

    for plan in solution.plans:
        jack_centers.append(plan.jack_center)
        region_counts[plan.jack_region_id] = region_counts.get(plan.jack_region_id, 0) + 1

    min_jack_distance = None
    if len(jack_centers) > 1:
        min_jack_distance = min(
            abs(jack_centers[i] - jack_centers[i - 1])
            for i in range(1, len(jack_centers))
        )

    region_parts = [f"區{region}={count}" for region, count in sorted(region_counts.items())]
    region_str = ", ".join(region_parts) if region_parts else "無"

    metrics: Dict[str, object] = {
        "總分": f"{solution.total_score:.1f}",
        "是否合法": "是" if solution.valid else "否",
        "最小千斤頂間距(mm)": f"{min_jack_distance:.1f}" if min_jack_distance is not None else "無資料",
        "千斤頂區域分布": region_str,
    }
    if solution.reason:
        metrics["說明"] = solution.reason

    print_summary(
        "全域最佳化完成",
        metrics,
    )


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

    if not (0 <= gap <= MAX_GAP):
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
    short_steel_count = sum(1 for x in steel_lengths if x < 4000)

    short_penalty = short_steel_count * 8000
    joint_penalty = len(joints) * 1200
    gap_penalty = abs(gap - TARGET_GAP) * 20

    score += short_penalty
    score += joint_penalty
    score += gap_penalty

    # jack 不希望在端部區域
    jack_edge_penalty = 0
    if jack_center < 2500 or jack_center > config.total_length - 2500:
        jack_edge_penalty = 5000
        score += jack_edge_penalty

    invalid_penalty = 0
    if not valid:
        invalid_penalty = 1_000_000 + forbidden_count * 100_000 + max(0, -gap) * 1000 + max(0, gap - MAX_GAP) * 1000
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
        breakdown=breakdown
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


def _steel_order_state_penalty(sequence: Tuple[int, ...]) -> float:
    penalty = 0.0
    if not sequence:
        return penalty

    if sequence[0] < 4000:
        penalty += 40.0
    if sequence[-1] < 4000:
        penalty += 20.0
    if len(sequence) > 1 and sequence[-2] < 4000 and sequence[-1] < 4000:
        penalty += 10.0
    penalty += sum(1 for length in sequence if length < 4000) * 2.0
    return penalty


def generate_length_combinations_dp(
    config: SupportConfig,
    max_combinations: int = 100,
    max_states_per_sum: int = 60,
    max_steel_pieces: int = 20,
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
                new_short = short_count + (1 if steel < 4000 else 0)
                new_score = len(new_seq) * 1000.0 + new_short * 10.0
                updated.append((new_score, new_seq, new_short))

            dp[total] = _keep_top_candidates(updated, max_states_per_sum)

    results: List[Dict[str, object]] = []
    seen: Dict[Tuple[Tuple[int, ...], int, int], bool] = {}

    for shim in SHIM_LENGTHS:
        for gap in range(0, MAX_GAP + 1):
            steel_target = config.total_length - JACK_LENGTH - shim - gap
            if steel_target < 0:
                continue

            for score, seq, _ in dp.get(steel_target, []):
                key = (seq, shim, gap)
                if key in seen:
                    continue
                seen[key] = True

                total_score = score + gap * 3.0 + shim * 1.0
                results.append({
                    "steel_lengths": list(seq),
                    "shim": shim,
                    "gap": gap,
                    "score": total_score,
                })

    results.sort(key=lambda item: item["score"])
    return results[:max_combinations]


def beam_search_steel_orders(
    steel_lengths: List[int],
    beam_width: int = 50,
    max_orders: int = 50,
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
    diagnostics: Optional[Dict[str, int]] = None,
) -> List[SupportPlan]:
    steel_orders = beam_search_steel_orders(
        steel_lengths,
        beam_width=beam_width,
        max_orders=beam_width,
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

    if diagnostics is not None:
        diagnostics["layouts_generated"] = diagnostics.get("layouts_generated", 0) + len(candidates)
        diagnostics["region_matched"] = diagnostics.get("region_matched", 0) + sum(
            plan.jack_region_id == config.target_jack_region
            for plan in candidates
        )
        diagnostics["valid_before_region"] = diagnostics.get("valid_before_region", 0) + sum(
            plan.valid and not plan.reason
            for plan in candidates
        )
        diagnostics["valid_region_matched"] = diagnostics.get("valid_region_matched", 0) + sum(
            plan.valid
            and not plan.reason
            and plan.jack_region_id == config.target_jack_region
            for plan in candidates
        )

    candidates.sort(key=lambda x: x.score)
    return candidates[:max_layouts]


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
    diagnostics: Dict[str, int],
    candidates: List[SupportPlan],
    retained_layouts: List[SupportPlan],
    returned_candidates: List[SupportPlan],
) -> None:
    merged_zones = _merged_forbidden_intervals(config)
    covered_length = sum(end - start for start, end in merged_zones)
    coverage_ratio = covered_length / config.total_length if config.total_length > 0 else 0.0

    safe_intervals: List[Tuple[int, int]] = []
    cursor = 0
    for start, end in merged_zones:
        if cursor < start:
            safe_intervals.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < config.total_length:
        safe_intervals.append((cursor, config.total_length))

    valid_candidates = [plan for plan in candidates if plan.valid and not plan.reason]
    returned_valid_count = sum(
        plan.valid and not plan.reason
        for plan in returned_candidates
    )
    best_single_score = min(
        (plan.score for plan in valid_candidates),
        default=None,
    )
    reason_statistics = _invalid_reason_statistics(candidates)
    candidates_sufficient = (
        len(valid_candidates) >= target_valid_candidate_count
        and returned_valid_count >= target_valid_candidate_count
    )

    log("=" * 72)
    log(f"支撐 {config.support_id} 候選方案分析")
    log(f"總長度：{config.total_length} mm")
    log(f"目標千斤頂區域：區 {config.target_jack_region}")
    log(f"鋼材組合探索數：{max_steel_combination_count}")
    log(f"實際處理鋼材組合數：{diagnostics.get('combinations_processed', 0)}")
    log(f"產生配置方案數：{diagnostics.get('layouts_generated', 0)}")
    log(f"符合目標千斤頂區域方案數：{diagnostics.get('region_matched', 0)}")
    log(f"合法方案數：{len(valid_candidates)}")
    log(f"最終保留合法候選數：{returned_valid_count}")
    log(
        f"最佳單體分數：{best_single_score:.1f}"
        if best_single_score is not None
        else "最佳單體分數：無資料"
    )
    log(f"禁止區覆蓋率：{coverage_ratio:.1%}")
    log("可用接頭區間：")
    if safe_intervals:
        for start, end in safe_intervals:
            log(f"  {start} ~ {end}")
    else:
        log("  無")

    log("主要不合法原因：")
    for label in ("接頭落入禁止區", "餘長不合法", "千斤頂數量錯誤"):
        log(f"  {label}：{reason_statistics.pop(label, 0)}")
    for label, count in sorted(reason_statistics.items()):
        log(f"  {label}：{count}")

    valid_before_region = diagnostics.get("valid_before_region", 0)
    valid_region_matched = diagnostics.get("valid_region_matched", 0)
    if candidates_sufficient:
        diagnosis = "第一階段正常：已成功產生足夠合法候選方案。"
    elif valid_before_region == 0:
        diagnosis = "A：目前探索範圍內沒有產生合法配置方案。"
    elif valid_region_matched == 0:
        diagnosis = "B：有合法配置方案，但被目標千斤頂區域條件排除。"
    elif not valid_candidates:
        diagnosis = "C：合法且符合區域的方案曾經產生，但未進入最終候選。"
    else:
        diagnosis = "合法候選方案已產生，但數量不足。"

    log("診斷結果：")
    log(f"  {diagnosis}")

    if DEBUG:
        log("除錯詳細統計：")
        log(f"  實際產生鋼材組合數：{combination_count}")
        log(f"  配置方案保留數：{diagnostics.get('layouts_retained', 0)}")
        log(f"  配置保留後符合目標區域數：{diagnostics.get('region_matched_retained', 0)}")
        log(f"  目標區域篩選前合法數：{valid_before_region}")
        log(f"  符合目標區域且合法數：{valid_region_matched}")
        log("  禁止區：")
        for start, end, label in forbidden_zones(config):
            log(f"    {label}：{start} ~ {end}")

    if not candidates_sufficient:
        failed_plans: List[SupportPlan] = []
        failed_keys = set()
        for plan in sorted(candidates, key=lambda item: item.score):
            if plan.valid and not plan.reason:
                continue
            key = tuple(plan.pieces)
            if key in failed_keys:
                continue
            failed_keys.add(key)
            failed_plans.append(plan)

        for plan in sorted(retained_layouts, key=lambda item: item.score):
            key = tuple(plan.pieces)
            if key in failed_keys:
                continue
            if (
                plan.valid
                and not plan.reason
                and plan.jack_region_id == config.target_jack_region
            ):
                continue
            failed_keys.add(key)
            failed_plans.append(plan)
            if len(failed_plans) >= 10:
                break

        log("候選不足時的前 10 個最低分方案：")
        if not failed_plans:
            log("  無可供排查的失敗方案")
        for rank, plan in enumerate(
            sorted(failed_plans, key=lambda item: item.score)[:10],
            start=1,
        ):
            pieces_text = format_pieces_for_display(plan.pieces)
            if plan.reason:
                reason = plan.reason
            elif plan.jack_region_id != config.target_jack_region:
                reason = (
                    f"不符合目標千斤頂區域"
                    f"（實際為區 {plan.jack_region_id}）"
                )
            else:
                reason = "未進入最終候選"
            log(f"  方案 {rank}")
            log(f"    分數：{plan.score:.1f}")
            log(
                f"    是否合法："
                f"{'是' if plan.valid and not plan.reason else '否'}"
            )
            log(f"    原因：{reason}")
            log(f"    接頭位置：{plan.joints}")
            log(f"    千斤頂中心：{plan.jack_center:.1f}")
            log(f"    配置：[{pieces_text}]")

    log(f"支撐 {config.support_id} 候選方案分析完成。")
    log(
        f"合法候選方案：{len(valid_candidates)} / "
        f"需求 {target_valid_candidate_count}"
    )
    log(f"狀態：{'正常' if candidates_sufficient else '不足'}")
    log("=" * 72)


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
    min_candidates: int = 30,
    max_length_combinations: int = 100,
    beam_width: int = 50,
    max_layouts_per_combo: int = 20,
    min_valid_candidates: Optional[int] = None,
    random_seed: Optional[int] = None,
    diagnostics_out: Optional[Dict[str, object]] = None,
) -> List[SupportPlan]:
    if random_seed is not None:
        random.seed(random_seed)

    if min_valid_candidates is None:
        min_valid_candidates = min_candidates

    combinations = generate_length_combinations_dp(
        config,
        max_combinations=max_length_combinations,
    )

    candidates: List[SupportPlan] = []
    retained_layouts: List[SupportPlan] = []
    seen: Dict[Tuple[Tuple[str, int], ...], bool] = {}
    valid_count = 0
    diagnostics: Dict[str, int] = {}

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

        if valid_count >= min_valid_candidates:
            break

    candidates.sort(key=lambda x: x.score)
    final_valid_plans = [plan for plan in candidates if plan.valid and not plan.reason]
    returned_candidates = (
        final_valid_plans[:min_candidates]
        if final_valid_plans
        else candidates[:min_candidates]
    )

    diagnostic_record: Dict[str, object] = {
        "max_steel_combination_count": max_length_combinations,
        "combination_count": len(combinations),
        "target_valid_candidate_count": min_candidates,
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
    beam_width: int = 80
) -> GlobalSolution:
    """
    使用 beam search 選出整體解。
    避免所有組合暴力枚舉。
    """

    log(f"全域最佳化開始：支撐數量={len(candidates_by_support)}")

    if not candidates_by_support:
        solution = GlobalSolution([], 0, False, "沒有候選資料")
        print_global_summary(solution)
        return solution

    # beam item: (total_score, plans)
    beam: List[Tuple[float, List[SupportPlan]]] = []

    for plan in candidates_by_support[0]:
        beam.append((plan.score, [plan]))

    beam.sort(key=lambda x: x[0])
    beam = beam[:beam_width]

    for support_idx in range(1, len(candidates_by_support)):
        new_beam: List[Tuple[float, List[SupportPlan]]] = []

        for current_score, selected_plans in beam:
            prev_plan = selected_plans[-1]

            for candidate in candidates_by_support[support_idx]:
                ok, penalty = pair_penalty(prev_plan, candidate)

                if not ok:
                    continue

                new_score = current_score + candidate.score + penalty
                new_beam.append((new_score, selected_plans + [candidate]))

        new_beam.sort(key=lambda x: x[0])
        beam = new_beam[:beam_width]

        if not beam:
            solution = fallback_global_solution(candidates_by_support)
            print_global_summary(solution)
            return solution

    best_score, best_plans = beam[0]
    solution = GlobalSolution(
        plans=best_plans,
        total_score=best_score,
        valid=all(p.valid and not p.reason for p in best_plans),
        reason=""
    )
    print_global_summary(solution)
    return solution


def fallback_global_solution(
    candidates_by_support: List[List[SupportPlan]]
) -> GlobalSolution:
    """
    若 Phase 2 找不到完全符合 jack 間距的組合，
    則選每支支撐單體分數最低者，並標記為 fallback。
    """
    plans = []

    for candidates in candidates_by_support:
        if candidates:
            plans.append(min(candidates, key=lambda x: x.score))

    total_score = sum(p.score for p in plans)

    return GlobalSolution(
        plans=plans,
        total_score=total_score + 5_000_000,
        valid=False,
        reason="找不到完全符合相鄰 jack 間距的整體解，已回傳 fallback"
    )


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
    log(f"      片段: [{pieces_str}]")
    if plan.reason:
        log(f"      原因: {plan.reason}")


def format_plan_compact(plan: SupportPlan) -> str:
    pieces_str = format_pieces_for_display(plan.pieces)
    valid_str = "是" if plan.valid and not plan.reason else "否"
    base = (
        f"分數:{plan.score:.1f} | 合法:{valid_str} | 餘長(mm):{plan.gap} | "
        f"千斤頂:{plan.jack_center:.1f} | 區域:{plan.jack_region_id} | 片段:[{pieces_str}]"
    )
    if plan.reason:
        return f"{base} | 原因:{plan.reason}"
    return base


def print_global_solution(solution: GlobalSolution) -> None:
    log("===================================================")
    log("整體解摘要")
    log(f"  總分: {solution.total_score:.1f}")
    log(f"  是否合法: {'是' if solution.valid else '否'}")
    if solution.reason:
        log(f"  說明: {solution.reason}")
    log("---------------------------------------------------")
    for idx, p in enumerate(solution.plans, 1):
        log(f"支撐 {idx}：")
        print_plan(p)
