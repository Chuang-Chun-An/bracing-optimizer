import unittest
from unittest.mock import patch

import support


def make_config():
    return support.SupportConfig(
        support_id="S1",
        total_length=21300,
        pile_centers=[8550, 12750],
        waler_centers=[8550, 12750],
        target_jack_region=2,
    )


def make_key(**overrides):
    params = {
        "config": make_config(),
        "max_length_combinations": 100,
        "min_candidates": 40,
        "beam_width": 50,
        "max_layouts_per_combo": 20,
    }
    params.update(overrides)
    return support.build_support_candidate_cache_key(**params)


class SupportCandidateCacheKeyTests(unittest.TestCase):
    def test_same_settings_produce_same_key(self):
        self.assertEqual(make_key(), make_key())

    def test_steel_lengths_change_key(self):
        original = make_key()
        with patch.object(support, "STEEL_LENGTHS", support.STEEL_LENGTHS + [10500]):
            changed = make_key()
        self.assertNotEqual(original, changed)

    def test_shim_lengths_change_key(self):
        original = make_key()
        with patch.object(support, "SHIM_LENGTHS", support.SHIM_LENGTHS + [250]):
            changed = make_key()
        self.assertNotEqual(original, changed)

    def test_max_layouts_per_combo_change_key(self):
        self.assertNotEqual(
            make_key(max_layouts_per_combo=20),
            make_key(max_layouts_per_combo=40),
        )

    def test_max_length_combinations_change_key(self):
        self.assertNotEqual(
            make_key(max_length_combinations=100),
            make_key(max_length_combinations=200),
        )

    def test_min_candidates_change_key(self):
        self.assertNotEqual(
            make_key(min_candidates=40),
            make_key(min_candidates=80),
        )

    def test_min_candidate_pool_size_change_key(self):
        self.assertNotEqual(
            make_key(min_candidate_pool_size=80),
            make_key(min_candidate_pool_size=120),
        )

    def test_min_processed_steel_combinations_change_key(self):
        self.assertNotEqual(
            make_key(min_processed_steel_combinations=60),
            make_key(min_processed_steel_combinations=100),
        )

    def test_min_unique_jack_centers_change_key(self):
        self.assertNotEqual(
            make_key(min_unique_jack_centers=6),
            make_key(min_unique_jack_centers=10),
        )

    def test_min_no_under_4000_candidates_change_key(self):
        self.assertNotEqual(
            make_key(min_no_under_4000_candidates=10),
            make_key(min_no_under_4000_candidates=20),
        )

    def test_min_unique_material_styles_change_key(self):
        self.assertNotEqual(
            make_key(min_unique_material_styles=8),
            make_key(min_unique_material_styles=12),
        )

    def test_jack_center_bucket_size_change_key(self):
        self.assertNotEqual(
            make_key(jack_center_bucket_size=50),
            make_key(jack_center_bucket_size=100),
        )

    def test_min_candidates_per_jack_bucket_change_key(self):
        self.assertNotEqual(
            make_key(min_candidates_per_jack_bucket=5),
            make_key(min_candidates_per_jack_bucket=8),
        )

    def test_min_candidates_per_material_style_change_key(self):
        self.assertNotEqual(
            make_key(min_candidates_per_material_style=2),
            make_key(min_candidates_per_material_style=4),
        )

    def test_min_retained_no_under_4000_candidates_change_key(self):
        self.assertNotEqual(
            make_key(min_retained_no_under_4000_candidates=20),
            make_key(min_retained_no_under_4000_candidates=30),
        )

    def test_length_combination_selection_strategy_change_key(self):
        self.assertNotEqual(
            make_key(length_combination_selection_strategy="score_top"),
            make_key(length_combination_selection_strategy="material_style_v1"),
        )

    def test_layout_beam_width_change_key(self):
        self.assertNotEqual(
            make_key(beam_width=50),
            make_key(beam_width=100),
        )

    def test_candidate_selection_version_change_key(self):
        self.assertNotEqual(
            make_key(candidate_selection_version="phase1_score_topn_v1"),
            make_key(candidate_selection_version="phase1_diversified_v2"),
        )

    def test_solver_search_policy_version_change_key(self):
        self.assertNotEqual(
            make_key(solver_search_policy_version=1),
            make_key(solver_search_policy_version=2),
        )

    def test_material_ratio_weight_does_not_change_phase1_key(self):
        original = make_key()
        with patch.object(support, "SUPPORT_MATERIAL_RATIO_WEIGHT", 999999):
            changed = make_key()
        self.assertEqual(original, changed)


class SupportCandidateDiversityHelpersTests(unittest.TestCase):
    def test_default_jack_bucket_selection_settings_are_100mm_and_two_candidates(self):
        self.assertEqual(support.SUPPORT_DEFAULT_JACK_CENTER_BUCKET_SIZE, 100)
        self.assertEqual(support.SUPPORT_DEFAULT_MIN_CANDIDATES_PER_JACK_BUCKET, 2)

    def test_length_combination_prescore_uses_single_support_gap_rule(self):
        steel_lengths = [4000, 6500, 10000]

        self.assertEqual(
            support.calculate_length_combination_prescore(steel_lengths, 200, 0),
            6400.0,
        )
        self.assertEqual(
            support.calculate_length_combination_prescore(steel_lengths, 150, 50),
            5400.0,
        )
        self.assertEqual(
            support.calculate_length_combination_prescore(steel_lengths, 100, 100),
            5200.0,
        )

    def test_length_combination_prescore_has_no_shim_length_penalty(self):
        steel_lengths = [4000, 6500, 10000]

        self.assertEqual(
            support.calculate_length_combination_prescore(steel_lengths, 100, 80),
            support.calculate_length_combination_prescore(steel_lengths, 200, 80),
        )

    def test_generated_combination_scores_follow_single_support_rules(self):
        combinations = support.generate_length_combinations_dp(
            make_config(),
            max_combinations=180,
        )
        target = {
            (int(combo["shim"]), int(combo["gap"])): float(combo["score"])
            for combo in combinations
            if tuple(combo["steel_lengths"]) == (4000, 6500, 10000)
        }

        self.assertEqual(target[(200, 0)], 6400.0)
        self.assertEqual(target[(150, 50)], 5400.0)
        self.assertEqual(target[(100, 100)], 5200.0)

    def test_jack_center_bucket_uses_floor_based_half_open_ranges(self):
        self.assertEqual(support.jack_center_bucket(0, 50), 0)
        self.assertEqual(support.jack_center_bucket(49.999, 50), 0)
        self.assertEqual(support.jack_center_bucket(50, 50), 1)
        self.assertEqual(support.jack_center_bucket(99.999, 50), 1)
        self.assertEqual(support.jack_center_bucket(100, 50), 2)

    def test_jack_center_bucket_stabilizes_tiny_float_error(self):
        self.assertEqual(support.jack_center_bucket(99.99999999999999, 50), 2)

    def test_jack_center_bucket_rejects_invalid_bucket_size(self):
        with self.assertRaises(ValueError):
            support.jack_center_bucket(100, 0)
        with self.assertRaises(ValueError):
            support.jack_center_bucket(100, -50)

    def test_steel_pattern_ignores_order_jack_and_shim_but_keeps_duplicates(self):
        first = support.steel_pattern_from_pieces([
            ("steel", 10000),
            ("jack", support.JACK_LENGTH),
            ("shim", 200),
            ("steel", 4000),
            ("steel", 6500),
            ("steel", 4000),
        ])
        second = support.steel_pattern_from_pieces([
            ("steel", 6500),
            ("steel", 4000),
            ("shim", 200),
            ("steel", 10000),
            ("jack", support.JACK_LENGTH),
            ("steel", 4000),
        ])
        self.assertEqual(first, (4000, 4000, 6500, 10000))
        self.assertEqual(first, second)


def make_plan(score, jack_center, steel_lengths):
    return support.SupportPlan(
        support_id="S1",
        pieces=[("steel", length) for length in steel_lengths] + [("jack", support.JACK_LENGTH)],
        joints=[],
        gap=0,
        jack_center=jack_center,
        jack_region_id=1,
        score=float(score),
        valid=True,
    )


def plan_signature(plan):
    return (
        tuple(plan.pieces),
        tuple(plan.joints),
        plan.gap,
        plan.jack_center,
        plan.score,
        plan.valid,
        plan.reason,
    )


def solution_signature(solution):
    return (
        solution.valid,
        round(solution.total_score, 6),
        tuple(plan_signature(plan) for plan in solution.plans),
    )


class SelectDiverseTopCandidatesTests(unittest.TestCase):
    def test_jack_bucket_guarantee_has_first_priority(self):
        candidates = []
        for index in range(20):
            candidates.append(make_plan(index + 1, 10, [6000, 6000]))
        for index in range(5):
            candidates.append(make_plan(1000 + index, 110, [7000, 7000]))
            candidates.append(make_plan(2000 + index, 210, [8000, 8000]))

        selected, diagnostics = support.select_diverse_top_candidates(
            candidates,
            final_candidate_count=9,
            jack_center_bucket_size=50,
            min_candidates_per_jack_bucket=3,
            min_candidates_per_material_style=0,
            min_retained_no_under_4000_candidates=0,
        )
        bucket_counts = {}
        for plan in selected:
            bucket = support.jack_center_bucket(plan.jack_center, 50)
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

        self.assertEqual(bucket_counts, {0: 3, 2: 3, 4: 3})
        self.assertEqual(
            diagnostics["selection_counts"]["selected_by_jack_bucket_guarantee"],
            9,
        )
        self.assertEqual(
            [plan.score for plan in selected],
            sorted(plan.score for plan in selected),
        )

    def test_material_style_guarantee_fills_missing_styles(self):
        candidates = [
            make_plan(1, 10, [6000, 6000]),
            make_plan(2, 10, [6000, 6000]),
            make_plan(3, 10, [7000, 7000]),
            make_plan(4, 10, [7000, 7000]),
            make_plan(5, 10, [8000, 8000]),
            make_plan(6, 10, [8000, 8000]),
        ]
        selected, diagnostics = support.select_diverse_top_candidates(
            candidates,
            final_candidate_count=6,
            jack_center_bucket_size=50,
            min_candidates_per_jack_bucket=1,
            min_candidates_per_material_style=2,
            min_retained_no_under_4000_candidates=0,
        )
        style_counts = {}
        for plan in selected:
            style = support.material_style_from_plan(plan)
            style_counts[style] = style_counts.get(style, 0) + 1

        self.assertEqual(style_counts, {
            (6000, 0, 2, 0): 2,
            (7000, 0, 2, 0): 2,
            (8000, 0, 2, 0): 2,
        })
        self.assertGreaterEqual(
            diagnostics["selection_counts"]["selected_by_material_style_guarantee"],
            4,
        )

    def test_no_under_4000_guarantee_adds_buildable_candidates(self):
        candidates = [
            make_plan(1, 10, [3500, 10000]),
            make_plan(2, 10, [3500, 9500]),
            make_plan(3, 10, [3500, 9000]),
            make_plan(100, 10, [4000, 9000]),
            make_plan(101, 10, [4500, 8500]),
            make_plan(102, 10, [5000, 8000]),
        ]
        selected, diagnostics = support.select_diverse_top_candidates(
            candidates,
            final_candidate_count=6,
            jack_center_bucket_size=50,
            min_candidates_per_jack_bucket=0,
            min_candidates_per_material_style=0,
            min_retained_no_under_4000_candidates=3,
        )
        no_under_count = sum(
            1
            for plan in selected
            if support.plan_has_no_under_4000_steel(plan)
        )

        self.assertEqual(no_under_count, 3)
        self.assertEqual(
            diagnostics["selection_counts"]["selected_by_no_under_4000_guarantee"],
            3,
        )


class SelectDiverseEligibleLayoutsTests(unittest.TestCase):
    def test_eligible_layouts_are_all_kept_when_count_is_within_limit(self):
        layouts = [
            make_plan(100 + index, center, [5000, 5500, 10000])
            for index, center in enumerate([10300, 10300, 10500, 10800, 11000])
        ]
        selected = support.select_diverse_eligible_layouts(
            layouts,
            max_layouts_per_combo=20,
            jack_center_bucket_size=50,
        )

        self.assertEqual(
            {support.layout_signature(plan) for plan in selected},
            {support.layout_signature(plan) for plan in layouts},
        )
        self.assertTrue(
            all(
                getattr(plan, "layout_selection_reason", "") == "eligible_all_kept"
                for plan in selected
            )
        )

    def test_eligible_layouts_over_limit_keep_jack_bucket_representatives(self):
        layouts = []
        for bucket_index, center in enumerate([10300, 10500, 10800, 11000]):
            for variant in range(4):
                layouts.append(
                    make_plan(
                        score=100 * bucket_index + variant,
                        jack_center=center,
                        steel_lengths=[5000 + variant * 500, 5500, 10000],
                    )
                )
        selected = support.select_diverse_eligible_layouts(
            layouts,
            max_layouts_per_combo=6,
            jack_center_bucket_size=50,
        )
        selected_buckets = {
            support.jack_center_bucket(plan.jack_center, 50)
            for plan in selected
        }

        self.assertEqual(len(selected), 6)
        self.assertEqual(selected_buckets, {
            support.jack_center_bucket(center, 50)
            for center in [10300, 10500, 10800, 11000]
        })


class SupportDiagnosticsInvarianceTests(unittest.TestCase):
    def test_candidate_user_log_is_compact_and_explains_the_funnel(self):
        messages = []
        support.set_logger(messages.append)
        try:
            support.generate_single_support_candidates(
                config=make_config(),
                min_candidates=5,
                final_candidate_count=5,
                max_length_combinations=5,
                beam_width=5,
                max_layouts_per_combo=5,
                min_candidates_per_jack_bucket=1,
                min_candidates_per_material_style=1,
                min_retained_no_under_4000_candidates=0,
            )
        finally:
            support.set_logger(None)

        output = "\n".join(messages)
        self.assertIn("S1｜材料組合 5/5｜配置", output)
        self.assertIn("保留來源：Jack位置", output)
        self.assertIn("保留分數", output)
        self.assertNotIn("Jack 中心分組（TopN後）", output)
        self.assertNotIn("除錯詳細統計", output)

    def test_global_user_log_is_one_line_and_omits_tuning_details(self):
        plans = [
            make_plan(5200, 1000, [4000, 7000, 9500]),
            make_plan(6400, 1600, [4000, 7000, 9500]),
        ]
        plans[0].support_id = "S1"
        plans[1].support_id = "S2"
        solution = support.GlobalSolution(
            plans=plans,
            total_score=11600,
            single_score_total=11600,
            valid=True,
            min_jack_distance=600,
        )
        messages = []
        support.set_logger(messages.append)
        try:
            support.print_global_summary(solution)
        finally:
            support.set_logger(None)

        self.assertEqual(len(messages), 1)
        self.assertIn("全域搭配完成｜合法 2/2 支", messages[0])
        self.assertIn("最小Jack距離 600 mm", messages[0])
        self.assertNotIn("Material Ratio Weight", messages[0])
        self.assertNotIn("最佳解使用材料", messages[0])

    def test_candidate_generation_processes_every_selected_combination(self):
        diagnostics = {}
        support.generate_single_support_candidates(
            config=make_config(),
            min_candidates=5,
            final_candidate_count=5,
            max_length_combinations=5,
            beam_width=5,
            max_layouts_per_combo=5,
            min_processed_steel_combinations=0,
            min_candidate_pool_size=0,
            min_unique_jack_centers=0,
            min_no_under_4000_candidates=0,
            min_unique_material_styles=0,
            min_candidates_per_jack_bucket=0,
            min_candidates_per_material_style=0,
            min_retained_no_under_4000_candidates=0,
            diagnostics_out=diagnostics,
        )

        self.assertEqual(diagnostics["combination_count"], 5)
        self.assertEqual(diagnostics["diagnostics"]["combinations_processed"], 5)
        self.assertEqual(
            diagnostics["diagnostics"]["stop_reason"],
            "已完整處理選入的鋼材組合",
        )

    def test_candidate_benchmark_summary_does_not_reorder_candidates(self):
        config = make_config()
        candidates = [
            make_plan(3, 110, [8000, 8000]),
            make_plan(1, 10, [6000, 6000]),
            make_plan(2, 60, [7000, 7000]),
        ]
        before = [id(plan) for plan in candidates]
        support.support_candidate_benchmark_summary(
            config=config,
            combination_count=3,
            diagnostics={
                "combinations_processed": 3,
                "layouts_generated": 3,
                "valid_before_region": 3,
            },
            candidate_pool=candidates,
            returned_candidates=candidates[:2],
        )
        self.assertEqual(before, [id(plan) for plan in candidates])

    def test_phase2_diagnostics_does_not_change_final_result(self):
        candidates_by_support = [
            [
                make_plan(10, 1000, [6000, 5000]),
                make_plan(20, 1500, [7000, 4000]),
            ],
            [
                make_plan(5, 1500, [6000, 5000]),
                make_plan(6, 2000, [7000, 4000]),
            ],
            [
                make_plan(7, 2000, [6000, 5000]),
                make_plan(8, 2500, [7000, 4000]),
            ],
        ]
        for support_index, candidates in enumerate(candidates_by_support, start=1):
            for plan in candidates:
                plan.support_id = f"S{support_index}"

        without_diagnostics = support.build_global_solution(
            candidates_by_support,
            beam_width=10,
            material_ratio_targets=support.normalize_material_ratio_targets(38, 40, 22),
            material_ratio_weight=10000,
        )
        diagnostics = {}
        with_diagnostics = support.build_global_solution(
            candidates_by_support,
            beam_width=10,
            material_ratio_targets=support.normalize_material_ratio_targets(38, 40, 22),
            material_ratio_weight=10000,
            diagnostics_out=diagnostics,
        )

        self.assertEqual(
            solution_signature(without_diagnostics),
            solution_signature(with_diagnostics),
        )
        self.assertIn("steps", diagnostics)
        self.assertIn("selected_candidate_indices", diagnostics)

    def test_same_input_repeated_phase2_result_is_consistent(self):
        candidates_by_support = [
            [make_plan(10, 1000, [6000, 5000]), make_plan(20, 1500, [7000, 4000])],
            [make_plan(5, 1500, [6000, 5000]), make_plan(6, 2000, [7000, 4000])],
        ]
        first_diag = {}
        second_diag = {}
        first = support.build_global_solution(
            candidates_by_support,
            beam_width=10,
            diagnostics_out=first_diag,
        )
        second = support.build_global_solution(
            candidates_by_support,
            beam_width=10,
            diagnostics_out=second_diag,
        )

        self.assertEqual(solution_signature(first), solution_signature(second))
        self.assertEqual(
            first_diag["selected_candidate_indices"],
            second_diag["selected_candidate_indices"],
        )

    def test_candidate_cache_enabled_and_disabled_results_are_consistent(self):
        config = make_config()
        params = {
            "config": config,
            "min_candidates": 5,
            "final_candidate_count": 5,
            "max_length_combinations": 5,
            "beam_width": 5,
            "max_layouts_per_combo": 5,
            "min_processed_steel_combinations": 0,
            "min_candidate_pool_size": 0,
            "min_unique_jack_centers": 0,
            "min_no_under_4000_candidates": 0,
            "min_unique_material_styles": 0,
            "min_candidates_per_jack_bucket": 0,
            "min_candidates_per_material_style": 0,
            "min_retained_no_under_4000_candidates": 0,
        }
        key = support.build_support_candidate_cache_key(
            config,
            max_length_combinations=5,
            final_candidate_count=5,
            beam_width=5,
            max_layouts_per_combo=5,
            min_processed_steel_combinations=0,
            min_candidate_pool_size=0,
            min_unique_jack_centers=0,
            min_no_under_4000_candidates=0,
            min_unique_material_styles=0,
            min_candidates_per_jack_bucket=0,
            min_candidates_per_material_style=0,
            min_retained_no_under_4000_candidates=0,
        )
        cache = {}
        uncached = support.generate_single_support_candidates(**params)
        cache[key] = support.generate_single_support_candidates(**params)
        cached = cache[key]

        self.assertEqual(
            [plan_signature(plan) for plan in uncached],
            [plan_signature(plan) for plan in cached],
        )


if __name__ == "__main__":
    unittest.main()
