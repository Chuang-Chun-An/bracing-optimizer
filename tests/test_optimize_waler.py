import unittest
from dataclasses import replace
from unittest.mock import patch

from bracing_optimizer.application.optimize_waler import OptimizeWaler, OptimizeWalerRequest
from bracing_optimizer.application.solver_input_builder import WalerProblemInput
from bracing_optimizer.algorithms.solver_search import DEFAULT_SEARCH_POLICY
from bracing_optimizer.domain.material_rules import MaterialRatioTargets


def make_request(waler_id="W1"):
    return OptimizeWalerRequest(
        input=WalerProblemInput(
            waler_id=waler_id,
            start_point=(0, 0),
            end_point=(12_000, 0),
            total_length=12_000,
            forbidden_points=(4_000,),
            material_spec="H400x400",
            purchasable_lengths=(4_000, 6_000, 8_000),
            stock_items=(),
        ),
        material_ratio_targets=MaterialRatioTargets.normalized(20, 50, 30),
    )


class OptimizeWalerTests(unittest.TestCase):
    def test_cache_key_contains_waler_id_and_ignores_stock_items(self):
        use_case = OptimizeWaler()
        first = make_request("W1")
        other_waler = replace(
            first,
            input=replace(first.input, waler_id="W2"),
        )
        other_stock = replace(
            first,
            input=replace(first.input, stock_items=({"length": 9_999},)),
        )

        self.assertNotEqual(
            use_case.build_cache_key(first),
            use_case.build_cache_key(other_waler),
        )
        self.assertEqual(
            use_case.build_cache_key(first),
            use_case.build_cache_key(other_stock),
        )

    @patch(
        "bracing_optimizer.application.optimize_waler.wales.is_joint_path_feasible",
        return_value=True,
    )
    @patch("bracing_optimizer.application.optimize_waler.wales.evolve")
    def test_stable_standard_result_stops_without_escalating(
        self,
        evolve,
        _is_feasible,
    ):
        solution = {
            "segments": [6_000, 6_000],
            "joints": [6_000],
            "gap": 0,
            "score": 10,
            "valid": True,
        }

        def run(_cfg, _stock, *, seed, diagnostics_out):
            diagnostics_out.update(
                best_score_history=[10, 10, 10, 10, 10],
                valid_candidate_count=3,
                unique_valid_solution_count=3,
            )
            return [solution]

        evolve.side_effect = run
        result = OptimizeWaler().execute(make_request(), logger=lambda *args: None)

        self.assertEqual(evolve.call_count, 1)
        config, stock_items = evolve.call_args.args
        self.assertEqual(config.total_length, 12_000)
        self.assertEqual(config.support_points, [4_000])
        self.assertEqual(config.purchasable_lengths, [4_000, 6_000, 8_000])
        self.assertEqual(config.short_segment_ratio_target, 0.2)
        self.assertEqual(config.mid_segment_ratio_target, 0.5)
        self.assertEqual(config.long_segment_ratio_target, 0.3)
        first_stage = DEFAULT_SEARCH_POLICY.waler_search_stages[0]
        self.assertEqual(config.generations, first_stage.generations)
        self.assertEqual(config.population_size, first_stage.population_size)
        self.assertEqual(stock_items, [])
        self.assertFalse(result.diagnostics.search_was_escalated)
        self.assertTrue(result.diagnostics.result_is_stable)
        self.assertEqual(result.solutions[0]["score"], 10)

    @patch(
        "bracing_optimizer.application.optimize_waler.wales.is_joint_path_feasible",
        return_value=False,
    )
    @patch("bracing_optimizer.application.optimize_waler.wales.evolve")
    def test_no_solution_escalates_and_reports_waler_id(
        self,
        evolve,
        _is_feasible,
    ):
        def run(_cfg, _stock, *, seed, diagnostics_out):
            diagnostics_out.update(
                best_score_history=[],
                valid_candidate_count=0,
                unique_valid_solution_count=0,
            )
            return []

        evolve.side_effect = run
        result = OptimizeWaler().execute(make_request("W7"), logger=lambda *args: None)

        self.assertEqual(
            evolve.call_count,
            len(DEFAULT_SEARCH_POLICY.waler_search_stages),
        )
        self.assertTrue(result.diagnostics.search_was_escalated)
        self.assertEqual(result.diagnostics.affected_component_ids, ["W7"])


if __name__ == "__main__":
    unittest.main()
