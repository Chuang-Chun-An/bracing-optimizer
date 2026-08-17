import unittest

import wales


class WalerTailAdjustmentTests(unittest.TestCase):
    def test_every_500_mm_residue_is_resolved_with_one_block_and_199_gap(self):
        for residue in range(500):
            required_length = 95_500 + residue
            steel, adjustment, gap = wales.resolve_tail_adjustment(
                required_length
            )
            self.assertEqual(steel % 500, 0)
            self.assertIn(adjustment, wales.WALER_ADJUSTMENT_LENGTHS)
            self.assertGreaterEqual(gap, 0)
            self.assertLessEqual(gap, 199)
            self.assertEqual(steel + adjustment + gap, required_length)

    def test_non_standard_length_solver_uses_standard_steel_and_tail_data(self):
        cfg = wales.Config(
            total_length=95_736,
            support_points=[],
            purchasable_lengths=list(range(1000, 10_001, 500)),
            population_size=20,
            generations=2,
            elite_size=4,
            tournament_k=4,
            top_n=2,
        )
        self.assertEqual(cfg.steel_target_length, 95_500)
        self.assertEqual(cfg.tail_adjustment, 200)
        self.assertEqual(cfg.tail_gap, 36)

        previous_logger = wales.logger
        diagnostics = {}
        try:
            wales.set_logger(lambda *_args: None)
            results = wales.evolve(cfg, [], seed=1, diagnostics_out=diagnostics)
            repeated_diagnostics = {}
            repeated = wales.evolve(
                cfg,
                [],
                seed=1,
                diagnostics_out=repeated_diagnostics,
            )
        finally:
            wales.set_logger(previous_logger)

        self.assertTrue(results)
        self.assertEqual(
            [(item["segments"], item["score"]) for item in results],
            [(item["segments"], item["score"]) for item in repeated],
        )
        self.assertEqual(
            diagnostics["best_score_history"],
            repeated_diagnostics["best_score_history"],
        )
        self.assertEqual(diagnostics["generations"], 2)
        for result in results:
            self.assertTrue(result["valid"])
            self.assertEqual(sum(result["segments"]), 95_500)
            self.assertEqual(result["tail_adjustment"], 200)
            self.assertEqual(result["gap"], 36)
            self.assertEqual(
                sum(result["segments"])
                + result["tail_adjustment"]
                + result["gap"],
                95_736,
            )


if __name__ == "__main__":
    unittest.main()
