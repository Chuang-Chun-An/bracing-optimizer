import json
import math
from pathlib import Path
from collections import Counter

import support

support.set_logger(lambda msg: None)
targets = support.normalize_material_ratio_targets(38, 40, 22)
project = sorted(Path("project_cases").glob("*.json"), key=lambda p: p.name)[1]


def parse_positions(value):
    return [
        int(round(float(part.strip())))
        for part in str(value or "").replace("，", ",").split(",")
        if part.strip()
    ]


def row_length(row):
    explicit = row.get("Length")
    if explicit not in (None, ""):
        return int(round(float(explicit)))
    return int(
        round(
            math.hypot(
                float(row["EndX"]) - float(row["StartX"]),
                float(row["EndY"]) - float(row["StartY"]),
            )
        )
    )


with project.open("r", encoding="utf-8-sig") as f:
    data = json.load(f)

configs = []
for row in data.get("input_data", data).get("struts", []):
    if str(row.get("Zoning", "")).strip() == "H1":
        configs.append(
            support.SupportConfig(
                support_id=str(row.get("StrutID") or row.get("SupportID") or "").strip(),
                total_length=row_length(row),
                pile_centers=parse_positions(row.get("ColumnPositions", "")),
                waler_centers=parse_positions(row.get("BeamPositions", "")),
                target_jack_region=int(float(row.get("TargetJackRegion", 2) or 2)),
                material_spec=str(row.get("material_spec", "") or "").strip(),
            )
        )


manual_steel = {
    "S1": [5000, 5500, "jack", 10000],
    "S2": [10000, "jack", 4500, 6000],
    "S3": [6000, 5500, "jack", 9000],
    "S4": [8500, "jack", 5500, 6500],
    "S5": [4500, 7000, "jack", 9000],
    "S6": [8500, "jack", 5500, 6500],
    "S7": [6000, 5500, "jack", 9000],
    "S8": [8500, 5500, "jack", 6500],
    "S9": [4500, 7000, "jack", 9000],
    "S10": [8500, "jack", 7000, 5000],
    "S11": [6000, 5500, "jack", 9000],
    "S12": [8500, "jack", 7000, 5000],
    "S13": [4500, 7000, "jack", 9000],
    "S14": [10000, "jack", 4500, 6000],
    "S15": [5000, 5500, "jack", 10000],
}


def pattern(plan):
    return support.steel_pattern_from_plan(plan)


def pieces_text(plan):
    return "[" + ", ".join(f"{kind}:{length}" for kind, length in plan.pieces) + "]"


def manual_plan(config, shim=150, shim_after_jack=True):
    pieces = []
    inserted_shim = False
    for item in manual_steel[config.support_id]:
        if item == "jack":
            pieces.append(("jack", support.JACK_LENGTH))
            if shim_after_jack and shim:
                pieces.append(("shim", shim))
                inserted_shim = True
        else:
            pieces.append(("steel", int(item)))
    if shim and not inserted_shim:
        pieces.append(("shim", shim))
    return support.evaluate_single_support(config, pieces)


def solution_summary(label, plans):
    solution = support.make_global_solution(
        plans,
        material_ratio_targets=targets,
        material_ratio_weight=10000,
        material_concentration_weight=0.0,
    )
    steel_counts = Counter(support.support_steel_lengths(plans))
    pattern_summary = support.pattern_diversity_summary(plans)
    ratio_counts = solution.material_ratio_analysis.get("counts", {})
    ratio_values = solution.material_ratio_analysis.get("ratios", {})
    distances = [
        abs(curr.jack_center - prev.jack_center)
        for prev, curr in zip(plans, plans[1:])
    ]
    print("\n" + label)
    print("total", round(solution.total_score, 2), "single", solution.single_score_total, "ratio", round(solution.material_ratio_penalty, 2), "region", solution.jack_region_penalty, "valid", solution.valid, "reason", solution.reason)
    print("under4000", support.count_under_4000_steel_in_plans(plans), "minJack", min(distances) if distances else None)
    print("steel_counts", dict(sorted(steel_counts.items())))
    print("ratio_counts", ratio_counts, "ratio_pct", {k: round(v * 100, 2) for k, v in ratio_values.items()})
    print("pattern_kind_count", pattern_summary["pattern_kind_count"], "max_pattern_usage", pattern_summary["max_pattern_usage"], "pattern_concentration", pattern_summary["pattern_concentration"])
    print("pattern_usage", pattern_summary["pattern_usage"])
    print("jack_centers", [int(round(plan.jack_center)) for plan in plans])
    print("distances", distances)
    for plan in plans:
        print(plan.support_id, "score", plan.score, "valid", plan.valid and not plan.reason, "reason", plan.reason, "jack", plan.jack_center, "region", plan.jack_region_id, "gap", plan.gap, "pattern", pattern(plan), pieces_text(plan))
    return solution


all_candidates = []
for config in configs:
    all_candidates.append(
        support.generate_single_support_candidates(
            config,
            min_candidates=40,
            max_length_combinations=100,
            beam_width=support.SUPPORT_PHASE1_LAYOUT_BEAM_WIDTH,
            max_layouts_per_combo=20,
            diagnostics_out={},
            min_processed_steel_combinations=60,
            min_candidate_pool_size=80,
            min_unique_jack_centers=6,
            min_no_under_4000_candidates=10,
            min_unique_material_styles=8,
            jack_center_bucket_size=50,
            min_candidates_per_jack_bucket=support.SUPPORT_DEFAULT_MIN_CANDIDATES_PER_JACK_BUCKET,
            min_candidates_per_material_style=support.SUPPORT_DEFAULT_MIN_CANDIDATES_PER_MATERIAL_STYLE,
            min_retained_no_under_4000_candidates=support.SUPPORT_DEFAULT_MIN_RETAINED_NO_UNDER_4000_CANDIDATES,
            final_candidate_count=100,
            length_combination_selection_strategy=support.SUPPORT_LENGTH_COMBINATION_SELECTION_STRATEGY,
        )
    )

diag = {}
solver = support.build_global_solution(
    all_candidates,
    beam_width=100,
    material_ratio_targets=targets,
    material_ratio_weight=10000,
    diagnostics_out=diag,
)
solution_summary("SOLVER", solver.plans)

manual = [manual_plan(config, shim=150) for config in configs]
solution_summary("MANUAL_SHIM150_AFTER_JACK", manual)

# Try best shim position among: after jack, before jack, end. Keep manual steel order.
best_manual = []
for config in configs:
    variants = []
    raw = manual_steel[config.support_id]
    for mode in ("after", "before", "end"):
        pieces = []
        for item in raw:
            if item == "jack":
                if mode == "before":
                    pieces.append(("shim", 150))
                pieces.append(("jack", support.JACK_LENGTH))
                if mode == "after":
                    pieces.append(("shim", 150))
            else:
                pieces.append(("steel", int(item)))
        if mode == "end":
            pieces.append(("shim", 150))
        p = support.evaluate_single_support(config, pieces)
        variants.append(p)
    valid_variants = [p for p in variants if p.valid and not p.reason and p.jack_region_id == config.target_jack_region]
    best_manual.append(min(valid_variants or variants, key=lambda p: p.score))
solution_summary("MANUAL_BEST_SHIM_POSITION_PER_SUPPORT", best_manual)
