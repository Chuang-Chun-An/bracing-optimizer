import unittest

from bracing_optimizer.algorithms import support


def plan(support_id, steel_lengths, *, jack_center=0, region=1, score=0):
    pieces = []
    for length in steel_lengths:
        pieces.append(("steel", length))
    pieces.append(("shim", 200))
    pieces.append(("jack", support.JACK_LENGTH))
    return support.SupportPlan(
        support_id=support_id,
        pieces=pieces,
        joints=[],
        gap=0,
        jack_center=jack_center,
        jack_region_id=region,
        score=score,
        valid=True,
    )


class SupportMaterialRatioTests(unittest.TestCase):
    def test_default_support_material_ratio_is_38_40_22(self):
        self.assertEqual(support.SUPPORT_DEFAULT_SHORT_MATERIAL_RATIO, 38)
        self.assertEqual(support.SUPPORT_DEFAULT_MID_MATERIAL_RATIO, 40)
        self.assertEqual(support.SUPPORT_DEFAULT_LONG_MATERIAL_RATIO, 22)
        self.assertEqual(
            support.default_material_ratio_targets(),
            {"short": 0.38, "mid": 0.40, "long": 0.22},
        )

    def test_ratio_penalty_zero_when_counts_match_targets(self):
        plans = [
            plan("S1", [4000, 4500, 6000, 6500, 7000]),
            plan("S2", [7500, 8000, 9000, 9500, 10000]),
        ]

        analysis = support.calculate_material_ratio_analysis(
            plans,
            support.normalize_material_ratio_targets(20, 50, 30),
            material_ratio_weight=100000,
        )

        self.assertEqual(analysis["counts"], {"short": 2, "mid": 5, "long": 3})
        self.assertAlmostEqual(analysis["ratio_deviation"], 0.0)
        self.assertAlmostEqual(analysis["penalty"], 0.0)

    def test_ratio_penalty_matches_expected_deviation(self):
        plans = [
            plan("S1", [4000, 6000, 6500, 7000, 7500]),
            plan("S2", [9000, 9000, 9500, 10000, 10000]),
        ]

        analysis = support.calculate_material_ratio_analysis(
            plans,
            support.normalize_material_ratio_targets(20, 50, 30),
            material_ratio_weight=100000,
        )

        self.assertEqual(analysis["counts"], {"short": 1, "mid": 4, "long": 5})
        self.assertAlmostEqual(analysis["ratios"]["short"], 0.1)
        self.assertAlmostEqual(analysis["ratios"]["mid"], 0.4)
        self.assertAlmostEqual(analysis["ratios"]["long"], 0.5)
        self.assertAlmostEqual(analysis["ratio_deviation"], 0.4)
        self.assertAlmostEqual(analysis["penalty"], 40000.0)

    def test_jack_and_shim_are_not_counted_in_material_ratio(self):
        support_plan = support.SupportPlan(
            support_id="S1",
            pieces=[
                ("shim", 4000),
                ("jack", 6000),
                ("steel", 4000),
                ("steel", 6000),
                ("steel", 9000),
            ],
            joints=[],
            gap=0,
            jack_center=0,
            jack_region_id=1,
            score=0,
            valid=True,
        )

        analysis = support.calculate_material_ratio_analysis(
            [support_plan],
            support.normalize_material_ratio_targets(1, 1, 1),
            material_ratio_weight=100000,
        )

        self.assertEqual(analysis["counts"], {"short": 1, "mid": 1, "long": 1})
        self.assertEqual(analysis["classified_total"], 3)

    def test_material_concentration_penalty_zero_below_threshold(self):
        plans = [
            plan("S1", [4000, 4500, 5000, 5500]),
            plan("S2", [6000, 6500, 7000, 7500]),
        ]

        analysis = support.calculate_material_concentration_analysis(
            plans,
            material_concentration_threshold=0.25,
            material_concentration_weight=10000,
        )

        self.assertAlmostEqual(analysis["penalty"], 0.0)
        self.assertEqual(analysis["spec_breakdown"][4000]["count"], 1)

    def test_material_concentration_penalty_uses_only_steel(self):
        support_plan = support.SupportPlan(
            support_id="S1",
            pieces=[
                ("steel", 10000),
                ("steel", 10000),
                ("steel", 10000),
                ("steel", 4000),
                ("shim", 10000),
                ("jack", 10000),
            ],
            joints=[],
            gap=0,
            jack_center=0,
            jack_region_id=1,
            score=0,
            valid=True,
        )

        analysis = support.calculate_material_concentration_analysis(
            [support_plan],
            material_concentration_threshold=0.25,
            material_concentration_weight=10000,
        )

        self.assertEqual(analysis["total_steel_count"], 4)
        self.assertEqual(analysis["spec_breakdown"][10000]["count"], 3)
        self.assertAlmostEqual(analysis["spec_breakdown"][10000]["ratio"], 0.75)
        self.assertAlmostEqual(analysis["penalty"], 5000.0)

    def test_material_concentration_default_weight_does_not_change_solution_score(self):
        targets = support.normalize_material_ratio_targets(50, 50, 0)
        solution = support.make_global_solution(
            [
                plan("S1", [4000], jack_center=0),
                plan("S2", [6000], jack_center=1000),
            ],
            material_ratio_targets=targets,
            material_ratio_weight=100000,
        )

        self.assertAlmostEqual(solution.material_concentration_penalty, 0.0)
        self.assertAlmostEqual(solution.total_score, 0.0)

    def test_beam_search_uses_material_concentration_without_double_counting(self):
        targets = support.normalize_material_ratio_targets(50, 50, 0)
        solution = support.build_global_solution(
            candidates_by_support=[
                [
                    plan("S1", [10000], jack_center=0, score=300),
                    plan("S1", [4000], jack_center=0, score=100),
                ],
                [
                    plan("S2", [10000], jack_center=1000, score=200),
                    plan("S2", [6000], jack_center=1000, score=100),
                ],
            ],
            beam_width=10,
            material_ratio_targets=targets,
            material_ratio_weight=0,
            material_concentration_threshold=0.25,
            material_concentration_weight=10000,
        )

        self.assertTrue(solution.valid)
        self.assertEqual([p.pieces[0][1] for p in solution.plans], [4000, 6000])
        self.assertAlmostEqual(solution.material_concentration_penalty, 5000.0)
        self.assertAlmostEqual(solution.total_score, 5200.0)

    def test_replacing_one_support_changes_group_material_ratio_score(self):
        targets = support.normalize_material_ratio_targets(50, 50, 0)
        first = support.make_global_solution(
            [
                plan("S1", [4000], jack_center=0),
                plan("S2", [9000], jack_center=1000),
            ],
            material_ratio_targets=targets,
            material_ratio_weight=100000,
        )
        second = support.make_global_solution(
            [
                plan("S1", [4000], jack_center=0),
                plan("S2", [6000], jack_center=1000),
            ],
            material_ratio_targets=targets,
            material_ratio_weight=100000,
        )

        self.assertGreater(first.material_ratio_penalty, 0)
        self.assertAlmostEqual(second.material_ratio_penalty, 0.0)
        self.assertNotEqual(first.total_score, second.total_score)

    def test_beam_search_recomputes_material_ratio_without_double_counting(self):
        targets = support.normalize_material_ratio_targets(50, 50, 0)
        solution = support.build_global_solution(
            candidates_by_support=[
                [plan("S1", [4000], jack_center=0)],
                [plan("S2", [6000], jack_center=1000)],
            ],
            beam_width=10,
            material_ratio_targets=targets,
            material_ratio_weight=100000,
        )

        self.assertTrue(solution.valid)
        self.assertAlmostEqual(solution.material_ratio_penalty, 0.0)
        self.assertAlmostEqual(solution.total_score, 0.0)

    def test_pattern_diversity_tie_break_prefers_less_repeated_pattern_on_equal_score(self):
        solution = support.build_global_solution(
            candidates_by_support=[
                [
                    plan("S1", [4000, 6500, 10000], jack_center=0, score=0),
                    plan("S1", [4500, 6000, 10000], jack_center=0, score=0),
                ],
                [
                    plan("S2", [4000, 6500, 10000], jack_center=1000, score=0),
                    plan("S2", [4500, 6000, 10000], jack_center=1000, score=0),
                ],
            ],
            beam_width=10,
            material_ratio_weight=0,
        )

        self.assertTrue(solution.valid)
        self.assertEqual(
            [support.steel_pattern_from_plan(p) for p in solution.plans],
            [(4000, 6500, 10000), (4500, 6000, 10000)],
        )
        summary = support.pattern_diversity_summary(solution.plans)
        self.assertEqual(summary["max_pattern_usage"], 1)
        self.assertEqual(summary["pattern_concentration"], 2)

    def test_pattern_diversity_tie_break_does_not_override_lower_score(self):
        solution = support.build_global_solution(
            candidates_by_support=[
                [
                    plan("S1", [4000, 6500, 10000], jack_center=0, score=0),
                    plan("S1", [4500, 6000, 10000], jack_center=0, score=1),
                ],
                [
                    plan("S2", [4000, 6500, 10000], jack_center=1000, score=0),
                    plan("S2", [4500, 6000, 10000], jack_center=1000, score=1),
                ],
            ],
            beam_width=10,
            material_ratio_weight=0,
        )

        self.assertTrue(solution.valid)
        self.assertEqual(
            [support.steel_pattern_from_plan(p) for p in solution.plans],
            [(4000, 6500, 10000), (4000, 6500, 10000)],
        )
        self.assertAlmostEqual(solution.total_score, 0.0)


if __name__ == "__main__":
    unittest.main()
