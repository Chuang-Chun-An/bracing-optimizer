"""Pure text formatters shared by the main window and Solver dialogs."""

from __future__ import annotations

import math
from collections.abc import Iterable

from bracing_optimizer.algorithms import wales


def format_result_value(value: object, decimals: int = 1) -> str:
    if value == "N/A":
        return "無資料"
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return str(int(value))
        return f"{value:.{decimals}f}"
    return str(value)


def format_result_list(values: Iterable[object] | None) -> str:
    values = list(values or [])
    if not values:
        return "無"
    return ", ".join(format_result_value(value) for value in values)


def format_waler_score_breakdown(
    plan,
    option_index=None,
    ratio_targets=None,
    segment_counts=None,
):
    plan = plan or {}
    segments = list(plan.get("segments", []) or [])
    joints = list(plan.get("joints", []) or [])
    total_segments = len(segments)

    def finite_number(value, default=0.0):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if math.isfinite(number) else default

    def count_value(value, default=0):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return default

    def score_text(value):
        return format_result_value(value, decimals=2)

    targets_source = ratio_targets or plan.get("ratio_targets") or {}
    target_defaults = {"short": 0.2, "mid": 0.5, "long": 0.3}
    targets = {
        key: finite_number(
            targets_source.get(key, targets_source.get(f"{key}_segment_ratio_target")),
            target_defaults[key],
        )
        for key in ("short", "mid", "long")
    }

    counts_source = segment_counts or plan.get("segment_counts") or {}
    ratios_source = plan.get("segment_ratios") or {}
    counts = {}
    for key in ("short", "mid", "long"):
        if key in counts_source and counts_source.get(key) is not None:
            counts[key] = count_value(counts_source.get(key))
        else:
            counts[key] = count_value(
                finite_number(ratios_source.get(key), 0.0) * total_segments
            )

    actual_ratios = {
        key: (counts[key] / total_segments if total_segments else 0.0)
        for key in ("short", "mid", "long")
    }
    ratio_deviation = sum(
        abs(actual_ratios[key] - targets[key])
        for key in ("short", "mid", "long")
    )

    buy_count = count_value(plan.get("buy_count"), 0)
    under_4000_count = count_value(
        plan.get("under_4000_segment_count"),
        sum(1 for segment in segments if segment < 4000),
    )
    distinct_groups = count_value(
        plan.get("distinct_groups"),
        len({segment for segment in segments}),
    )
    joint_count = count_value(plan.get("joint_count"), len(joints))
    max_length = max(segments) if segments else 0
    min_length = min(segments) if segments else 0
    length_variation = finite_number(
        plan.get("length_variation"),
        max_length - min_length if segments else 0,
    )

    buy_score = buy_count * 100_000
    ratio_score = finite_number(
        plan.get("ratio_penalty"),
        ratio_deviation * 100_000,
    )
    ratio_deviation_for_score = ratio_score / 100_000
    under_4000_score = under_4000_count * 100_000
    distinct_score = distinct_groups * 5_000
    joint_score = joint_count * 1_000
    total_check = (
        buy_score
        + ratio_score
        + under_4000_score
        + distinct_score
        + length_variation
        + joint_score
    )
    total_score = finite_number(plan.get("score"), total_check)

    def pct(value):
        return f"{value * 100:.2f}%"

    def compact_score_line(label, expression, value):
        return f"{label:<12} {expression:<16} = {score_text(value):>10}"

    def compact_ratio_line(label, key):
        return (
            f"{label} {pct(actual_ratios[key])}"
            f"({counts[key]}/{total_segments}) → {pct(targets[key])}"
        )

    ratio_formula_lines = [
        f"|{pct(actual_ratios['short'])}-{pct(targets['short'])}|",
        f"+|{pct(actual_ratios['mid'])}-{pct(targets['mid'])}|",
        f"+|{pct(actual_ratios['long'])}-{pct(targets['long'])}|",
        f"={ratio_deviation_for_score:.4f}",
    ]
    total_check_text = " + ".join([
        score_text(buy_score),
        score_text(ratio_score),
        score_text(under_4000_score),
        score_text(distinct_score),
        score_text(length_variation),
        score_text(joint_score),
    ])
    steel_length = count_value(plan.get("steel_length"), sum(segments))
    tail_adjustment = count_value(plan.get("tail_adjustment"), 0)
    tail_gap = count_value(plan.get("gap"), 0)
    required_length = count_value(
        plan.get("required_length"),
        steel_length + tail_adjustment + tail_gap,
    )
    tail_lines = [
        f"需求長度：{required_length} mm",
        f"標準鋼材總長：{steel_length} mm",
        f"尾端調整塊：{tail_adjustment} mm",
        f"現場處理餘量：{tail_gap} mm（允許 0～{wales.WALER_MAX_GAP} mm）",
    ]

    option_title = f"方案 {option_index}" if option_index is not None else "方案"
    return "\n".join([
        option_title,
        *tail_lines,
        f"總分：{score_text(total_score)}",
        f"分段長度：{segments}",
        "評分拆解",
        compact_score_line("購買數", f"{buy_count} ×100000", buy_score),
        compact_score_line("比例偏差", f"{ratio_deviation_for_score:.4f}×100000", ratio_score),
        compact_score_line("小於4000mm", f"{under_4000_count} ×100000", under_4000_score),
        compact_score_line("材料種類", f"{distinct_groups} ×5000", distinct_score),
        compact_score_line("料長差", f"{score_text(max_length)}-{score_text(min_length)}", length_variation),
        compact_score_line("接頭數", f"{joint_count} ×1000", joint_score),
        "比例偏差詳細",
        compact_ratio_line("短段", "short"),
        compact_ratio_line("中段", "mid"),
        compact_ratio_line("長段", "long"),
        *ratio_formula_lines,
        f"總分驗算：{total_check_text} = {score_text(total_check)}",
    ])
