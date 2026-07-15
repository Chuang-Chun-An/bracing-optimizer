from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import Counter
import random
import math
import sys

import matplotlib.pyplot as plt
import matplotlib.font_manager as font_manager
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
import tkinter as tk
from tkinter import messagebox


def configure_matplotlib_engineering_font() -> str:
    """Configure matplotlib fonts for clean engineering drawings with Chinese support."""
    preferred_fonts = [
        "Microsoft JhengHei",
        "Microsoft YaHei",
        "PingFang TC",
        "Noto Sans CJK TC",
        "Source Han Sans TC",
        "SimHei",
        "WenQuanYi Micro Hei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]

    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    selected_font = next((name for name in preferred_fonts if name in available_fonts), None)
    if selected_font is None:
        selected_font = "DejaVu Sans"

    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = [selected_font]
    plt.rcParams["font.serif"] = [selected_font]
    plt.rcParams["font.monospace"] = [selected_font]
    plt.rcParams["font.size"] = 10
    plt.rcParams["font.weight"] = "normal"
    plt.rcParams["axes.unicode_minus"] = True
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42

    return selected_font


SELECTED_MATPLOTLIB_FONT = configure_matplotlib_engineering_font()


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
DEFAULT_MIN_VALID_CANDIDATES = 51

# Debug
DEBUG = False
DEBUG_FREQ = 10
DP_PROGRESS_STEP = 100
BEAM_PROGRESS_STEP = 10


@dataclass
class DebugLogger:
    dp_candidates: int = 0
    beam_expansions: int = 0
    beam_kept: int = 0
    layout_generated: int = 0
    valid_plans: int = 0
    forbidden_violations: int = 0
    scores: List[float] = field(default_factory=list)
    best_score: Optional[float] = None
    no_improve_count: int = 0

    def record_score(self, score: float):
        self.scores.append(score)
        if self.best_score is None or score < self.best_score:
            self.best_score = score
            self.no_improve_count = 0
        else:
            self.no_improve_count += 1

    def periodic_print(self, context: str, iteration: int):
        if not DEBUG:
            return
        if iteration % DEBUG_FREQ != 0:
            return
        if not self.scores:
            return
        best = min(self.scores)
        worst = max(self.scores)
        avg = sum(self.scores) / len(self.scores)
        print("[DEBUG] ------------------------------")
        print(f"[DEBUG] 位置: {context}，迭代: {iteration}")
        print(f"[DEBUG] best_score: {best:.1f}, avg_score: {avg:.1f}, worst_score: {worst:.1f}")
        print(f"[DEBUG] no_improve_count: {self.no_improve_count}")
        print(f"[DEBUG] DP 候選數: {self.dp_candidates}, Beam 展開數: {self.beam_expansions}, 保留數: {self.beam_kept}")
        print(f"[DEBUG] 產生佈局: {self.layout_generated}, 合法數: {self.valid_plans}, 禁止區違規數: {self.forbidden_violations}")
        print("[DEBUG] ------------------------------")

    def reset(self) -> None:
        self.dp_candidates = 0
        self.beam_expansions = 0
        self.beam_kept = 0
        self.layout_generated = 0
        self.valid_plans = 0
        self.forbidden_violations = 0
        self.scores.clear()
        self.best_score = None
        self.no_improve_count = 0


logger = DebugLogger()


def print_progress(context: str, current: int, total: int, extra: str = "") -> None:
    if total <= 0:
        return
    bar_length = 30
    filled = int(bar_length * current / total)
    bar = "[" + "=" * filled + " " * (bar_length - filled) + "]"
    percent = current * 100.0 / total
    sys.stdout.write(f"\r[PROGRESS] {context}: {current}/{total} {bar} {percent:5.1f}% {extra}")
    sys.stdout.flush()


def finalize_progress() -> None:
    sys.stdout.write("\n")
    sys.stdout.flush()


def print_summary(
    context: str,
    metrics: Dict[str, object],
    iteration: int = 0,
    total_iterations: int = 0,
) -> None:
    if total_iterations and iteration % 10 != 0 and iteration != total_iterations:
        return

    header = f"【摘要】{context}"
    if total_iterations:
        header += f" ({iteration}/{total_iterations})"

    lines = [header]
    for key, value in metrics.items():
        lines.append(f"{key}: {value}")

    width = max(len(line) for line in lines) + 4
    border_top = "╔" + "═" * (width - 2) + "╗"
    border_mid = "╠" + "═" * (width - 2) + "╣"
    border_bot = "╚" + "═" * (width - 2) + "╝"

    print(border_top)
    print(f"║ {header.ljust(width - 4)} ║")
    print(border_mid)
    for line in lines[1:]:
        print(f"║ {line.ljust(width - 4)} ║")
    print(border_bot)
    print()


def print_global_summary(solution: GlobalSolution) -> None:
    scores = [plan.score for plan in solution.plans]
    avg_single = sum(scores) / len(scores) if scores else 0.0
    penalty = solution.total_score - sum(scores)
    steel_usage: Dict[int, int] = {}
    material_usage: Dict[str, int] = {}
    jack_centers: List[float] = []
    region_counts: Dict[int, int] = {}

    for plan in solution.plans:
        for kind, length in plan.pieces:
            if kind == "steel":
                steel_usage[length] = steel_usage.get(length, 0) + 1
                label = f"steel:{length}"
            elif kind == "shim":
                label = f"shim:{length}"
            elif kind == "jack":
                label = "jack"
            else:
                label = f"{kind}:{length}"
            material_usage[label] = material_usage.get(label, 0) + 1
        jack_centers.append(plan.jack_center)
        region_counts[plan.jack_region_id] = region_counts.get(plan.jack_region_id, 0) + 1

    steel_types = len(steel_usage)
    material_types = len(material_usage)
    usage_parts = [f"{length}:{count}" for length, count in sorted(steel_usage.items())]
    usage_str = ", ".join(usage_parts) if usage_parts else "無"
    material_usage_parts = [f"{mat}:{count}" for mat, count in sorted(material_usage.items())]
    material_usage_str = ", ".join(material_usage_parts) if material_usage_parts else "無"

    min_jack_distance = None
    if len(jack_centers) > 1:
        min_jack_distance = min(
            abs(jack_centers[i] - jack_centers[i - 1])
            for i in range(1, len(jack_centers))
        )

    config_types = len({
        tuple(length for kind, length in plan.pieces if kind == "steel")
        for plan in solution.plans
    })

    region_parts = [f"區{region}={count}" for region, count in sorted(region_counts.items())]
    region_str = ", ".join(region_parts) if region_parts else "無"

    print_summary(
        "Phase 2 全域摘要",
        {
            "總分": f"{solution.total_score:.1f}",
            "全域罰則": f"{penalty:.1f}",
            "不同配置型態數": config_types,
            "使用鋼材種類數": steel_types,
            "鋼材長度使用次數": usage_str,
            "不同材料使用數量": material_types,
            "材料使用統計": material_usage_str,
            "相鄰支撐 Jack 最小距離": f"{min_jack_distance:.1f}" if min_jack_distance is not None else "N/A",
            "Jack 區域分布": region_str,
        },
    )


def draw_support_construction_diagram(solution: GlobalSolution, filename: str = "support_layout.png") -> str:
    """產生所有支撐合併施工圖，並輸出成圖檔。"""
    if not solution.plans:
        raise ValueError("Solution has no plans to draw.")

    total_lengths = [sum(length for _, length in plan.pieces) + plan.gap for plan in solution.plans]
    max_length = max(total_lengths)
    row_height = 0.8
    row_padding = 0.4
    figure_height = len(solution.plans) * (row_height + row_padding) + 2.0

    fig, ax = plt.subplots(figsize=(12, max(4.0, figure_height)))

    steel_color = "#4c72b0"
    colors = {
        "jack": "#d62728",
        "shim": "#ff7f0e",
        "gap": "#d3d3d3",
    }

    for index, plan in enumerate(solution.plans):
        y = len(solution.plans) - index
        x = 0.0
        for kind, length in plan.pieces:
            if kind == "steel":
                color = steel_color
                label = f"{length}"
            else:
                color = colors.get(kind, "#7f7f7f")
                label = "Jack" if kind == "jack" else ("Shim" if kind == "shim" else "")

            rect = Rectangle((x, y - row_height / 2), length, row_height,
                             facecolor=color, edgecolor="black")
            ax.add_patch(rect)
            if label:
                ax.text(x + length / 2, y, label, va="center", ha="center",
                        color="white" if kind == "steel" else "black", fontsize=7, fontweight="bold")
            x += length

        if plan.gap > 0:
            ax.add_patch(Rectangle((x, y - row_height / 2), plan.gap, row_height,
                                   facecolor=colors["gap"], edgecolor="black", hatch="..."))

        # 樁與托梁位置標示
        for p in plan.pile_centers:
            ax.vlines(p, y - row_height / 2, y + row_height / 2, colors="#2ca02c", linestyles="--", linewidth=1.5)
            ax.text(p, y + row_height / 2 + 0.08, "Pile", ha="center", va="bottom", fontsize=7, color="#2ca02c")
        for w in plan.waler_centers:
            ax.vlines(w, y - row_height / 2, y + row_height / 2, colors="#9467bd", linestyles="-.", linewidth=1.5)
            ax.text(w, y + row_height / 2 + 0.08, "Waler", ha="center", va="bottom", fontsize=7, color="#9467bd")

        annotations = (
            f"S{plan.support_id}  L={total_lengths[index]} mm  "
            f"Jack@{plan.jack_center:.0f}  區{plan.jack_region_id}"
        )
        ax.text(-max_length * 0.02, y, annotations, va="center", ha="right", fontsize=9)

    border = Rectangle((0, 0.5), max_length, len(solution.plans) + 0.5,
                       fill=False, edgecolor="black", linewidth=1.8)
    ax.add_patch(border)

    ax.set_xlim(-max_length * 0.08, max_length * 1.02)
    ax.set_ylim(0.5, len(solution.plans) + 1.5)
    ax.set_yticks([])
    ax.set_xlabel("長度 (mm)")
    ax.set_title("支撐施工圖 - 合併檢視")
    ax.grid(axis="x", linestyle="--", alpha=0.4)

    legend_patches = [
        Rectangle((0, 0), 1, 1, facecolor=steel_color, edgecolor='black'),
        Rectangle((0, 0), 1, 1, facecolor=colors["jack"], edgecolor='black'),
        Rectangle((0, 0), 1, 1, facecolor=colors["shim"], edgecolor='black'),
        Rectangle((0, 0), 1, 1, facecolor=colors["gap"], edgecolor='black', hatch="..."),
        Line2D([0], [0], color="#2ca02c", linestyle="--", linewidth=1.5),
        Line2D([0], [0], color="#9467bd", linestyle="-.", linewidth=1.5),
    ]
    ax.legend(legend_patches, ["steel", "jack", "shim", "gap", "Pile", "Waler"], loc="upper right")

    plt.tight_layout()
    fig.savefig(filename, dpi=150)
    plt.close(fig)
    return filename


# =========================================================
# 幾何工具
# =========================================================

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
        reasons.append("jack 數量不是 1")

    if not (0 <= gap <= MAX_GAP):
        valid = False
        reasons.append(f"gap 不合法: {gap}")

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

    # record to logger
    logger.record_score(score)

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

    steel_idx = 0
    for steel in STEEL_LENGTHS:
        steel_idx += 1
        # periodic progress: steel index
        logger.periodic_print("DP-steel", steel_idx)
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

        # debug: after finishing this steel length iteration
        if DEBUG:
            print(f"[DEBUG] DP: processed steel {steel} (index {steel_idx}), sums tracked: {len(dp)}")

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
    # debug
    logger.dp_candidates = len(results)
    if DEBUG:
        print(f"[DEBUG] DP combos generated: {len(results)} candidates from {len(dp)} sums")
    logger.periodic_print("DP", 1)
    return results[:max_combinations]


def beam_search_steel_orders(
    steel_lengths: List[int],
    beam_width: int = 50,
    max_orders: int = 50,
) -> List[List[int]]:
    initial_state = (0.0, (), Counter(steel_lengths))
    beam: List[Tuple[float, Tuple[int, ...], Counter[int]]] = [initial_state]
    completed: List[Tuple[float, Tuple[int, ...]]] = []

    round_idx = 0

    while beam:
        next_beam: List[Tuple[float, Tuple[int, ...], Counter[int]]] = []
        round_idx += 1

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

        # debug: count expansions
        logger.beam_expansions += len(next_beam)
        next_beam.sort(key=lambda item: item[0])
        beam = next_beam[:beam_width]
        logger.beam_kept = len(beam)
        # periodic debug print per round
        logger.periodic_print("BeamOrders", round_idx)
        if DEBUG:
            print(f"[DEBUG] Beam round {round_idx}: expansions={len(next_beam)}, kept={len(beam)}, completed={len(completed)}")

    completed.sort(key=lambda item: item[0])
    return [list(sequence) for _, sequence in completed[:max_orders]]


def beam_search_layout(
    config: SupportConfig,
    steel_lengths: List[int],
    shim: int,
    gap: int,
    beam_width: int = 50,
    max_layouts: int = 50,
) -> List[SupportPlan]:
    steel_orders = beam_search_steel_orders(
        steel_lengths,
        beam_width=beam_width,
        max_orders=beam_width,
    )

    if DEBUG:
        print(f"[DEBUG] BeamLayout start: steel_lengths={steel_lengths}, shim={shim}, gap={gap}, steel_orders={len(steel_orders)}")

    candidates: List[SupportPlan] = []
    seen: Dict[Tuple[Tuple[str, int], ...], bool] = {}

    for idx, order in enumerate(steel_orders, 1):
        logger.periodic_print("BeamLayoutOrder", idx)
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
                    # update layout stats
                    logger.layout_generated += 1
                    if plan.valid and not plan.reason:
                        logger.valid_plans += 1
                    # count forbidden joints explicitly
                    logger.forbidden_violations += count_forbidden_joints(plan.joints, config)
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
                logger.layout_generated += 1
                if plan.valid and not plan.reason:
                    logger.valid_plans += 1
                logger.forbidden_violations += count_forbidden_joints(plan.joints, config)
                candidates.append(plan)

    candidates.sort(key=lambda x: x.score)
    return candidates[:max_layouts]


def generate_single_support_candidates(
    config: SupportConfig,
    min_candidates: int = 30,
    max_length_combinations: int = 100,
    beam_width: int = 50,
    max_layouts_per_combo: int = 20,
    min_valid_candidates: Optional[int] = None,
    random_seed: Optional[int] = None,
) -> List[SupportPlan]:
    if random_seed is not None:
        random.seed(random_seed)

    if min_valid_candidates is None:
        min_valid_candidates = min_candidates

    combinations = generate_length_combinations_dp(
        config,
        max_combinations=max_length_combinations,
    )

    logger.reset()
    candidates: List[SupportPlan] = []
    seen: Dict[Tuple[Tuple[str, int], ...], bool] = {}
    valid_count = 0

    for idx, combo in enumerate(combinations, 1):
        logger.periodic_print("GenerateCombo", idx)
        layouts = beam_search_layout(
            config,
            combo["steel_lengths"],
            combo["shim"],
            combo["gap"],
            beam_width=beam_width,
            max_layouts=max_layouts_per_combo,
        )

        added_count = 0
        for plan in layouts:
            if plan.jack_region_id != config.target_jack_region:
                continue
            key = tuple(plan.pieces)
            if key in seen:
                continue
            seen[key] = True
            candidates.append(plan)
            added_count += 1
            if plan.valid and not plan.reason:
                valid_count += 1

        if DEBUG:
            print(f"[DEBUG] GenerateCombo {idx}/{len(combinations)} complete: layouts={len(layouts)}, new candidates={added_count}, total unique candidates={len(candidates)}")

        total_layouts = logger.layout_generated
        if DEBUG:
            valid_plans_list = [plan for plan in candidates if plan.valid and not plan.reason]
            invalid_plans_list = [plan for plan in candidates if not (plan.valid and not plan.reason)]
            valid_ratio = len(valid_plans_list) / total_layouts if total_layouts else 0.0
            best_score = min((plan.score for plan in valid_plans_list), default=None)
            avg_valid_score = sum(plan.score for plan in valid_plans_list) / len(valid_plans_list) if valid_plans_list else None
            steel_combo_set = set(
                tuple(sorted(length for kind, length in plan.pieces if kind == "steel"))
                for plan in valid_plans_list
            )
            distinct_steel_combos = len(steel_combo_set)
            distinct_jack_regions = len({plan.jack_region_id for plan in valid_plans_list})
            print_summary(
                f"Support {config.support_id}",
                {
                    "DP 組合數": len(combinations),
                    "DP 檢查": f"{idx}/{len(combinations)}",
                    "Layout 檢查數": total_layouts,
                    "目前累積合法方案數": len(valid_plans_list),
                    "合法率": f"{valid_ratio:.2%}",
                    "最佳分數": f"{best_score:.1f}" if best_score is not None else "N/A",
                    "合法方案平均分數": f"{avg_valid_score:.1f}" if avg_valid_score is not None else "N/A",
                    "不合法方案數": len(invalid_plans_list),
                    "不同鋼材組合數": distinct_steel_combos,
                    "不同 Jack 區域數": distinct_jack_regions,
                },
                iteration=idx,
                total_iterations=len(combinations),
            )

        # periodic debug print per combination index
        logger.periodic_print("GenerateSingle", len(candidates))

        if valid_count >= min_valid_candidates:
            break

    if combinations:
        finalize_progress()

    total_layouts = logger.layout_generated
    candidates.sort(key=lambda x: x.score)
    final_valid_plans = [plan for plan in candidates if plan.valid and not plan.reason]
    final_invalid_plans = [plan for plan in candidates if not (plan.valid and not plan.reason)]
    final_steel_combo_set = set(
        tuple(sorted(length for kind, length in plan.pieces if kind == "steel"))
        for plan in final_valid_plans
    )
    final_distinct_steel_combos = len(final_steel_combo_set)
    final_returned_candidates = final_valid_plans[:min_candidates] if final_valid_plans else candidates[:min_candidates]
    final_avg_valid_score = (
        sum(plan.score for plan in final_valid_plans) / len(final_valid_plans)
        if final_valid_plans
        else None
    )

    print_summary(
        f"Support {config.support_id} 最終統計",
        {
            "DP 組合總數": len(combinations),
            "Layout 檢查總數": total_layouts,
            "最終合法方案數": len(final_valid_plans),
            "最終不合法方案數": len(final_invalid_plans),
            "最終合法平均分數": f"{final_avg_valid_score:.1f}" if final_avg_valid_score is not None else "N/A",
            "不同鋼材組合數": final_distinct_steel_combos,
            "最終保留候選數": len(final_returned_candidates),
        },
    )

    if final_valid_plans:
        return final_valid_plans[:min_candidates]

    return candidates[:min_candidates]


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

    if not candidates_by_support:
        return GlobalSolution([], 0, False, "沒有候選資料")

    # beam item: (total_score, plans)
    beam: List[Tuple[float, List[SupportPlan]]] = []

    for plan in candidates_by_support[0]:
        beam.append((plan.score, [plan]))

    beam.sort(key=lambda x: x[0])
    beam = beam[:beam_width]

    no_improve = 0
    best_so_far = beam[0][0] if beam else None
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

        # debug: record beam stats
        logger.beam_expansions += sum(len(candidates) for candidates in candidates_by_support)
        logger.beam_kept = len(beam)
        # track improvement
        if beam:
            if best_so_far is None or beam[0][0] < best_so_far:
                best_so_far = beam[0][0]
                no_improve = 0
            else:
                no_improve += 1
        logger.no_improve_count = no_improve
        logger.periodic_print("GlobalBeam", support_idx)

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

def parse_position_list(text: str) -> List[int]:
    """將使用者輸入的逗號或空白分隔位置字串解析成排序且唯一的整數清單。

    回傳空清單表示使用者未輸入任何位置。
    """
    if not text:
        return []

    normalized = text.replace(",", " ").replace("\n", " ")
    parts = [part for part in normalized.split() if part]
    values: List[int] = []
    for part in parts:
        try:
            value = int(part)
            if value < 0:
                raise ValueError
            values.append(value)
        except ValueError:
            raise ValueError(f"無效位置值：{part}，請輸入非負整數")

    return sorted(set(values))


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
    pieces_str = ", ".join(f"{kind}:{length}" for kind, length in plan.pieces)
    valid_str = "是" if plan.valid and not plan.reason else "否"
    print(f"    分數: {plan.score:.1f} | 合法: {valid_str} | gap: {plan.gap} | jack: {plan.jack_center:.1f} | 區域: {plan.jack_region_id}")
    print(f"      片段: [{pieces_str}]")
    if plan.reason:
        print(f"      原因: {plan.reason}")


def format_plan_compact(plan: SupportPlan) -> str:
    pieces_str = ", ".join(f"{kind}:{length}" for kind, length in plan.pieces)
    valid_str = "是" if plan.valid and not plan.reason else "否"
    base = (
        f"分數:{plan.score:.1f} | 合法:{valid_str} | gap:{plan.gap} | "
        f"jack:{plan.jack_center:.1f} | 區域:{plan.jack_region_id} | 片段:[{pieces_str}]"
    )
    if plan.reason:
        return f"{base} | 原因:{plan.reason}"
    return base


def print_support_diagram(plan: SupportPlan, width: int = 80) -> None:
    total_length = sum(length for _, length in plan.pieces) + plan.gap
    if total_length <= 0:
        print("      (無法繪製支撐圖：總長度為 0)")
        return

    scale = max(1, width / total_length)
    bar_chars: List[str] = []

    def append_segment(char: str, length: int) -> None:
        count = max(1, int(round(length * scale)))
        bar_chars.extend([char] * count)

    for kind, length in plan.pieces:
        if kind == "steel":
            append_segment("=", length)
        elif kind == "jack":
            append_segment("J", length)
        elif kind == "shim":
            append_segment("~", length)
        else:
            append_segment("?", length)

    if plan.gap > 0:
        append_segment(".", plan.gap)

    # Force final width exact if rounding drifted
    if len(bar_chars) > width:
        bar_chars = bar_chars[:width]
    elif len(bar_chars) < width:
        bar_chars.extend(["."] * (width - len(bar_chars)))

    diagram = "".join(bar_chars)
    print(f"      [{diagram}]")
    print(f"      legend: '=' steel, 'J' jack, '~' shim, '.' gap")
    print(f"      total_length={total_length}, gap={plan.gap}, jack_center={plan.jack_center:.1f}")


def print_global_solution(solution: GlobalSolution) -> None:
    print("===================================================")
    print("整體解摘要")
    print(f"  總分: {solution.total_score:.1f}")
    print(f"  是否合法: {'是' if solution.valid else '否'}")
    if solution.reason:
        print(f"  說明: {solution.reason}")
    print("---------------------------------------------------")
    for idx, p in enumerate(solution.plans, 1):
        print(f"支撐 {idx}：")
        print_plan(p)
        print_support_diagram(p)

    try:
        output_path = draw_support_construction_diagram(solution)
        print(f"已輸出合併施工圖: {output_path}")
    except Exception as exc:
        print(f"無法輸出施工圖: {exc}")


def launch_support_input_gui(default_supports: List[SupportConfig]) -> List[SupportConfig]:
    root = tk.Tk()
    root.title("支撐配置輸入")
    root.geometry("980x720")
    root.resizable(True, True)

    values: List[dict] = []
    result: List[SupportConfig] = []
    support_count_var = tk.IntVar(value=len(default_supports))

    def parse_positions(text: str) -> List[int]:
        text = text.strip()
        if not text or text == "無":
            return []
        return parse_position_list(text)

    def build_rows():
        for widget in row_frame.winfo_children():
            widget.destroy()
        values.clear()
        count = support_count_var.get()
        for idx in range(1, count + 1):
            if idx <= len(default_supports):
                default_support = default_supports[idx - 1]
                total_value = str(default_support.total_length)
                pile_value = ",".join(map(str, default_support.pile_centers)) if default_support.pile_centers else ""
                waler_value = ",".join(map(str, default_support.waler_centers)) if default_support.waler_centers else ""
                region_value = str(default_support.target_jack_region)
            else:
                total_value = ""
                pile_value = ""
                waler_value = ""
                region_value = ""

            total_var = tk.StringVar(value=total_value)
            pile_var = tk.StringVar(value=pile_value)
            waler_var = tk.StringVar(value=waler_value)
            region_var = tk.StringVar(value=region_value)
            values.append({
                "support_id": f"S{idx}",
                "total": total_var,
                "pile": pile_var,
                "waler": waler_var,
                "region": region_var,
            })

            row = idx - 1
            label = tk.Label(row_frame, text=f"S{idx}", anchor="w", width=4)
            label.grid(row=row, column=0, padx=5, pady=4, sticky="w")
            total_entry = tk.Entry(row_frame, textvariable=total_var, width=14)
            total_entry.grid(row=row, column=1, padx=5, pady=4)
            pile_entry = tk.Entry(row_frame, textvariable=pile_var, width=24)
            pile_entry.grid(row=row, column=2, padx=5, pady=4)
            waler_entry = tk.Entry(row_frame, textvariable=waler_var, width=24)
            waler_entry.grid(row=row, column=3, padx=5, pady=4)
            region_entry = tk.Entry(row_frame, textvariable=region_var, width=10)
            region_entry.grid(row=row, column=4, padx=5, pady=4)

    def update_rows(*args):
        count = support_count_var.get()
        if count < 1:
            support_count_var.set(1)
            return
        build_rows()

    def on_submit():
        nonlocal result
        result.clear()
        try:
            for idx, item in enumerate(values, start=1):
                total_length = int(item["total"].get().strip())
                if total_length <= 0:
                    raise ValueError("總長度必須大於 0")
                pile_centers = parse_positions(item["pile"].get())
                waler_centers = parse_positions(item["waler"].get())
                target_jack_region = int(item["region"].get().strip())
                if target_jack_region <= 0:
                    raise ValueError("Jack 區域必須大於 0")
                result.append(
                    SupportConfig(
                        support_id=f"S{idx}",
                        total_length=total_length,
                        pile_centers=pile_centers,
                        waler_centers=waler_centers,
                        target_jack_region=target_jack_region,
                    )
                )
        except ValueError as exc:
            messagebox.showerror("輸入錯誤", str(exc), parent=root)
            return

        root.destroy()

    def on_cancel():
        root.destroy()

    title_label = tk.Label(root, text="支撐配置輸入", font=(None, 18, "bold"))
    title_label.pack(fill="x", padx=10, pady=(10, 0))

    top_frame = tk.Frame(root)
    top_frame.pack(fill="x", padx=10, pady=10)

    tk.Label(top_frame, text="支撐數量：").pack(side="left")
    support_count_spin = tk.Spinbox(
        top_frame,
        from_=1,
        to=50,
        textvariable=support_count_var,
        width=4,
        command=update_rows,
    )
    support_count_spin.pack(side="left")
    tk.Label(top_frame, text="（修改數量後會重新建立輸入欄位）").pack(side="left", padx=8)

    header_frame = tk.Frame(root)
    header_frame.pack(fill="x", padx=10)
    header_labels = ["支撐ID", "總長度(mm)", "樁位置(mm)", "托梁位置(mm)", "Jack 區域"]
    header_widths = [4, 14, 24, 24, 10]
    for col, (text, width) in enumerate(zip(header_labels, header_widths)):
        tk.Label(
            header_frame,
            text=text,
            font=(None, 10, "bold"),
            borderwidth=1,
            relief="raised",
            width=width,
        ).grid(row=0, column=col, padx=2, pady=2)

    for col, width in enumerate(header_widths):
        header_frame.grid_columnconfigure(col, minsize=width * 8)

    canvas = tk.Canvas(root)
    scrollbar = tk.Scrollbar(root, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas)

    scroll_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    row_frame = scroll_frame
    for col, width in enumerate(header_widths):
        row_frame.grid_columnconfigure(col, minsize=width * 8)
    build_rows()

    button_frame = tk.Frame(root)
    button_frame.pack(fill="x", pady=10)
    tk.Button(button_frame, text="產生支撐配置", command=on_submit, width=18).pack(side="right", padx=10)
    tk.Button(button_frame, text="取消", command=on_cancel, width=10).pack(side="right")

    root.mainloop()
    return result


def get_support_configs_from_input(default_count: Optional[int] = None) -> List[SupportConfig]:
    default_supports = get_default_supports()
    if default_count is None:
        default_count = len(default_supports)
    return launch_support_input_gui(default_supports[:default_count])


def get_default_supports() -> List[SupportConfig]:
    """回傳預設的支撐設定，用於非互動測試或快速執行。"""
    return [
        SupportConfig(support_id="S1", total_length=21300, pile_centers=[8550, 12750], waler_centers=[8550, 12750]),
        SupportConfig(support_id="S2", total_length=21300, pile_centers=[8642, 12787], waler_centers=[8642, 12787]),
        SupportConfig(support_id="S3", total_length=21300, pile_centers=[7850, 13450], waler_centers=[7850, 13450]),
        SupportConfig(support_id="S4", total_length=21300, pile_centers=[7850, 13450], waler_centers=[7850, 13450]),
        SupportConfig(support_id="S5", total_length=21300, pile_centers=[7850, 13450], waler_centers=[7850, 13450]),
        SupportConfig(support_id="S6", total_length=21300, pile_centers=[7850, 13450], waler_centers=[7850, 13450]),
        SupportConfig(support_id="S7", total_length=21300, pile_centers=[7850, 13450], waler_centers=[7850, 13450]),
        SupportConfig(support_id="S8", total_length=21300, pile_centers=[7850, 13450], waler_centers=[7850, 13450]),
        SupportConfig(support_id="S9", total_length=21300, pile_centers=[7850, 13450], waler_centers=[7850, 13450]),
        SupportConfig(support_id="S10", total_length=21300, pile_centers=[7850, 13450], waler_centers=[7850, 13450]),
        SupportConfig(support_id="S11", total_length=21300, pile_centers=[7850, 13450], waler_centers=[7850, 13450]),
        SupportConfig(support_id="S12", total_length=21300, pile_centers=[7850, 13450], waler_centers=[7850, 13450]),
        SupportConfig(support_id="S13", total_length=21300, pile_centers=[7850, 13450], waler_centers=[7850, 13450]),
        SupportConfig(support_id="S14", total_length=21300, pile_centers=[8642, 12787], waler_centers=[8642, 12787]),
        SupportConfig(support_id="S15", total_length=21300, pile_centers=[8550, 12750], waler_centers=[8550, 12750], target_jack_region=1),
    ]


def format_support_group_ids(configs: List[SupportConfig]) -> str:
    ids = [config.support_id for config in configs]
    if len(ids) == 1:
        return ids[0]
    return "、".join(ids)


def main():
    random.seed(42)

    supports = get_support_configs_from_input()
    candidates_by_support: List[List[SupportPlan]] = []
    cache: Dict[Tuple[int, Tuple[int, ...], Tuple[int, ...]], List[SupportPlan]] = {}
    support_groups: Dict[Tuple[int, Tuple[int, ...], Tuple[int, ...]], List[SupportConfig]] = {}

    for config in supports:
        key = get_support_config_key(config)
        support_groups.setdefault(key, []).append(config)
        if key not in cache:
            cache[key] = generate_single_support_candidates(
                config=config,
                min_candidates=40,
                min_valid_candidates=DEFAULT_MIN_VALID_CANDIDATES,
                max_length_combinations=100,
                beam_width=50,
                max_layouts_per_combo=20,
            )

        candidates_by_support.append([
            clone_plan_with_support_id(plan, config.support_id)
            for plan in cache[key]
        ])

    print("===================================================")
    print("Phase 1：產生單支支撐候選方案")
    print("===================================================")

    for key, configs in support_groups.items():
        group_candidates = cache[key]
        feasible_count = sum(1 for p in group_candidates if p.valid and not p.reason)
        ratio = feasible_count / len(group_candidates) if group_candidates else 0
        group_label = format_support_group_ids(configs)

        print(f"\n支撐 {group_label} 共用設定 (共 {len(configs)} 支)")
        print(f"  目標 Jack 區域 : {configs[0].target_jack_region}")
        print(f"  候選數量   : {len(group_candidates)}")
        print(f"  可行數量   : {feasible_count}")
        print(f"  可行解比例 : {ratio:.2%}")

        if group_candidates:
            print("  前10名候選：")
            for rank, candidate in enumerate(group_candidates[:10], start=1):
                compact = format_plan_compact(clone_plan_with_support_id(candidate, configs[0].support_id))
                print(f"    {rank:2}. {compact}")

    solution = build_global_solution(
        candidates_by_support=candidates_by_support,
        beam_width=100
    )

    print_global_solution(solution)
    input("\n按 Enter 結束...")


if __name__ == "__main__":
    main()