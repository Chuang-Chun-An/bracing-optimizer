import unittest

from bracing_optimizer.algorithms import wales


class WalerLengthCoverageTests(unittest.TestCase):
    def test_final_projection_can_keep_all_unique_final_population_results(self):
        cfg = wales.Config(
            total_length=12_000,
            support_points=[],
            purchasable_lengths=[4_000, 6_000, 8_000],
            top_n=5,
        )
        evaluated = [
            {
                "segments": [4_000 + index, 8_000 - index],
                "joints": [4_000 + index],
                "score": float(index),
                "valid": True,
            }
            for index in range(8)
        ]

        single = wales._top_results(evaluated, cfg)
        global_results = wales._top_results(
            evaluated,
            cfg,
            retain_all_final_results=True,
        )

        self.assertEqual(len(single), 5)
        self.assertEqual(len(global_results), 8)

    def test_every_residue_through_450_has_a_legal_tail_resolution(self):
        for residue in range(451):
            required_length = 95_500 + residue
            resolution = wales.resolve_waler_tail(required_length)

            self.assertIsNotNone(resolution, residue)
            assert resolution is not None
            self.assertEqual(resolution.steel_length, 95_500)
            self.assertEqual(resolution.steel_length % 500, 0)
            self.assertIn(
                resolution.tail_adjustment,
                wales.WALER_TAIL_ADJUSTMENTS,
            )
            self.assertGreaterEqual(resolution.gap, 0)
            self.assertLessEqual(resolution.gap, 150)
            self.assertEqual(
                resolution.steel_length
                + resolution.tail_adjustment
                + resolution.gap,
                required_length,
            )
            if residue <= 150:
                self.assertEqual(resolution.tail_adjustment, 0)
                self.assertEqual(resolution.gap, residue)

    def test_residues_451_through_499_have_no_legal_tail_resolution(self):
        for residue in range(451, 500):
            self.assertIsNone(wales.resolve_waler_tail(95_500 + residue))

    def test_fixed_steel_examples_use_no_block_or_smallest_legal_block(self):
        examples = (
            (12_100, 12_000, 0, 100),
            (12_180, 12_000, 100, 80),
            (12_250, 12_000, 100, 150),
            (16_450, 16_000, 300, 150),
            (11_950, 11_500, 300, 150),
            (12_000, 12_000, 0, 0),
        )

        for required, steel, adjustment, gap in examples:
            with self.subTest(required=required, steel=steel):
                resolution = wales.resolve_waler_tail(
                    required,
                    steel_length=steel,
                )
                self.assertEqual(
                    resolution,
                    wales.WalerTailResolution(steel, adjustment, gap),
                )

    def test_adjustment_options_are_sorted_by_smallest_legal_block(self):
        resolution = wales.resolve_waler_tail(
            12_250,
            steel_length=12_000,
            adjustment_options=(300, 200, 150, 100, 0),
        )

        self.assertEqual(
            resolution,
            wales.WalerTailResolution(12_000, 100, 150),
        )

    def test_fixed_steel_without_a_legal_tail_returns_none(self):
        self.assertIsNone(
            wales.resolve_waler_tail(16_451, steel_length=16_000)
        )
        self.assertIsNone(
            wales.resolve_waler_tail(12_000, steel_length=12_001)
        )

    def test_zero_length_and_invalid_programmer_inputs(self):
        self.assertEqual(
            wales.resolve_waler_tail(0),
            wales.WalerTailResolution(0, 0, 0),
        )

        invalid_calls = (
            lambda: wales.resolve_waler_tail(-1),
            lambda: wales.resolve_waler_tail(1_000, steel_length=-1),
            lambda: wales.resolve_waler_tail(1_000, steel_step=0),
            lambda: wales.resolve_waler_tail(1_000, max_gap=-1),
            lambda: wales.resolve_waler_tail(
                1_000,
                adjustment_options=(0, -100),
            ),
        )
        for invalid_call in invalid_calls:
            with self.subTest(call=invalid_call):
                with self.assertRaises(ValueError):
                    invalid_call()

    def test_config_keeps_existing_grid_joint_positions_and_search_budget(self):
        cfg = wales.Config(
            total_length=16_450,
            support_points=[],
        )

        self.assertEqual(cfg.steel_target_length, 16_000)
        self.assertEqual(cfg.tail_adjustment, 300)
        self.assertEqual(cfg.tail_gap, 150)
        self.assertEqual(
            cfg.candidate_joint_points,
            wales.generate_candidate_joint_points(16_000, 1_000, 500),
        )
        self.assertEqual(cfg.candidate_joint_step, 500)
        self.assertEqual(
            cfg.population_size,
            wales.DEFAULT_SEARCH_POLICY.waler_search_stages[0].population_size,
        )
        self.assertEqual(
            cfg.generations,
            wales.DEFAULT_SEARCH_POLICY.waler_search_stages[0].generations,
        )

    def test_automatic_tail_results_and_order_repeat_with_the_same_seed(self):
        def run_once():
            cfg = wales.Config(
                total_length=12_250,
                support_points=[],
                purchasable_lengths=list(range(1_000, 10_001, 500)),
                population_size=20,
                generations=2,
                elite_size=4,
                tournament_k=4,
                top_n=5,
            )
            diagnostics = {}
            return wales.evolve(
                cfg,
                [],
                seed=7,
                diagnostics_out=diagnostics,
            ), diagnostics

        previous_logger = wales.logger
        try:
            wales.set_logger(lambda *_args: None)
            first, first_diagnostics = run_once()
            second, second_diagnostics = run_once()
        finally:
            wales.set_logger(previous_logger)

        exact_fields = (
            "segments",
            "joints",
            "tail_adjustment",
            "gap",
            "pieces",
            "valid",
            "assignments",
            "total_waste",
            "buy_count",
            "distinct_groups",
            "length_variation",
            "under_4000_segment_count",
            "segment_ratios",
            "ratio_penalty",
            "joint_count",
            "score",
        )
        self.assertEqual(
            [{field: item.get(field) for field in exact_fields} for item in first],
            [{field: item.get(field) for field in exact_fields} for item in second],
        )
        self.assertEqual(first_diagnostics, second_diagnostics)
        self.assertTrue(first)
        self.assertTrue(all(item["tail_adjustment"] == 100 for item in first))
        self.assertTrue(all(item["gap"] == 150 for item in first))


if __name__ == "__main__":
    unittest.main()
