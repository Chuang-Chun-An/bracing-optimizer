import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bracing_optimizer.application.optimize_waler_global import (
    OptimizeWalerGlobal,
    OptimizeWalerGlobalRequest,
)
from bracing_optimizer.application.solver_input_builder import WalerProblemInput
from bracing_optimizer.domain.material_rules import MaterialRatioTargets


def waler_input(waler_id, material_spec="H400x400"):
    return WalerProblemInput(
        waler_id=waler_id,
        start_point=(0, 0),
        end_point=(12_000, 0),
        total_length=12_000,
        forbidden_points=(),
        material_spec=material_spec,
        stock_items=(),
        purchasable_lengths=(1_000, 3_500, 5_000, 7_000, 9_000),
    )


class FakeWalerOptimizer:
    def __init__(self, solutions_by_waler, calls):
        self.solutions_by_waler = solutions_by_waler
        self.calls = calls

    def execute(self, request, *, logger=None):
        self.calls.append(request.input.waler_id)
        return SimpleNamespace(
            solutions=tuple(self.solutions_by_waler[request.input.waler_id]),
            diagnostics=SimpleNamespace(to_dict=lambda: {"solver_type": "waler"}),
        )


class OptimizeWalerGlobalTests(unittest.TestCase):
    def test_mixed_inputs_only_optimize_non_rc_walers(self):
        calls = []
        solutions = {
            "W1": [
                {"valid": True, "segments": [5_000], "joints": [], "score": 10}
            ],
            "W3": [
                {"valid": True, "segments": [7_000], "joints": [], "score": 20}
            ],
        }
        use_case = OptimizeWalerGlobal(
            lambda: FakeWalerOptimizer(solutions, calls)
        )

        result = use_case.execute(
            OptimizeWalerGlobalRequest(
                waler_inputs=(
                    waler_input("W1"),
                    waler_input("W2", " rc "),
                    waler_input("W3", "CUSTOM"),
                ),
                material_ratio_targets=MaterialRatioTargets.normalized(20, 50, 30),
            )
        )

        self.assertTrue(result.solution.valid)
        self.assertEqual(calls, ["W1", "W3"])
        self.assertEqual(
            [candidate.waler_id for candidate in result.solution.selected_candidates],
            ["W1", "W3"],
        )
        self.assertEqual(result.diagnostics.waler_count, 2)

    @patch(
        "bracing_optimizer.application.optimize_waler_global."
        "solve_global_waler_candidates"
    )
    def test_all_rc_inputs_return_without_local_or_global_solver(self, solve_global):
        factory_calls = []

        def factory():
            factory_calls.append(True)
            raise AssertionError("local optimizer must not be created")

        result = OptimizeWalerGlobal(factory).execute(
            OptimizeWalerGlobalRequest(
                waler_inputs=(waler_input("W1", "RC"), waler_input("W2", " rc ")),
                material_ratio_targets=MaterialRatioTargets.normalized(20, 50, 30),
            )
        )

        self.assertFalse(result.solution.valid)
        self.assertEqual(result.diagnostics.waler_count, 0)
        self.assertEqual(result.local_results, ())
        self.assertEqual(factory_calls, [])
        solve_global.assert_not_called()

    def test_runs_existing_local_solver_for_every_waler_then_exact_dp(self):
        calls = []
        solutions = {
            "W1": [
                {"valid": True, "segments": [5_000], "joints": [], "score": 10},
                {"valid": True, "segments": [7_000], "joints": [], "score": 12},
            ],
            "W2": [
                {"valid": True, "segments": [7_000], "joints": [], "score": 20},
                {"valid": True, "segments": [9_000], "joints": [], "score": 25},
            ],
        }
        use_case = OptimizeWalerGlobal(
            lambda: FakeWalerOptimizer(solutions, calls)
        )
        messages = []

        result = use_case.execute(
            OptimizeWalerGlobalRequest(
                waler_inputs=(waler_input("W1"), waler_input("W2")),
                material_ratio_targets=MaterialRatioTargets.normalized(20, 50, 30),
            ),
            logger=lambda *parts: messages.append(" ".join(map(str, parts))),
        )

        self.assertEqual(calls, ["W1", "W2"])
        self.assertTrue(result.solution.valid)
        self.assertEqual(len(result.solution.selected_candidates), 2)
        self.assertEqual(result.diagnostics.raw_candidate_count, 4)
        self.assertTrue(result.diagnostics.exact_search)
        self.assertFalse(result.diagnostics.shared_inventory_optimized)
        self.assertTrue(any("Exact DP" in message for message in messages))

    def test_zero_legal_local_candidates_returns_diagnostics_without_fallback(self):
        calls = []
        solutions = {
            "W1": [
                {"valid": False, "segments": [], "joints": [], "score": 1_000_000}
            ]
        }
        use_case = OptimizeWalerGlobal(
            lambda: FakeWalerOptimizer(solutions, calls)
        )

        result = use_case.execute(
            OptimizeWalerGlobalRequest(
                waler_inputs=(waler_input("W1"),),
                material_ratio_targets=MaterialRatioTargets.normalized(20, 50, 30),
            )
        )

        self.assertFalse(result.solution.valid)
        self.assertEqual(result.diagnostics.failed_waler_ids, ("W1",))
        self.assertIn("沒有合法", result.solution.reason)


if __name__ == "__main__":
    unittest.main()
