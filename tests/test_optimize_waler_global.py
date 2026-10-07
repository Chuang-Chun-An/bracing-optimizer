import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from bracing_optimizer.algorithms.cancellation import (
    CancellationSource,
    SolverCancelled,
)

from bracing_optimizer.application.optimize_waler_global import (
    OptimizeWalerGlobal,
    OptimizeWalerGlobalRequest,
)
from bracing_optimizer.application.optimize_waler import GLOBAL_FINAL_POPULATION
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

    def execute(self, request, *, logger=None, retention_profile=None):
        self.calls.append(request.input.waler_id)
        if retention_profile is not GLOBAL_FINAL_POPULATION:
            raise AssertionError("Global caller must opt into the global profile")
        return SimpleNamespace(
            solutions=tuple(self.solutions_by_waler[request.input.waler_id]),
            diagnostics=SimpleNamespace(to_dict=lambda: {"solver_type": "waler"}),
        )


class OptimizeWalerGlobalTests(unittest.TestCase):
    @patch(
        "bracing_optimizer.application.optimize_waler_global."
        "solve_global_waler_candidates"
    )
    def test_cancellation_after_group_completion_discards_partial_groups(
        self,
        solve_global,
    ):
        source = CancellationSource()
        solutions = {
            "W1": [
                {"valid": True, "segments": [5_000], "joints": [], "score": 10}
            ]
        }

        class TokenAwareOptimizer(FakeWalerOptimizer):
            def execute(self, request, **kwargs):
                self_outer.assertIs(kwargs["cancellation_token"], source.token)
                return super().execute(
                    request,
                    logger=kwargs.get("logger"),
                    retention_profile=kwargs.get("retention_profile"),
                )

        self_outer = self
        use_case = OptimizeWalerGlobal(
            lambda: TokenAwareOptimizer(solutions, [])
        )

        def cancel_after_merge(candidates, *, cancellation_token=None):
            self.assertIs(cancellation_token, source.token)
            source.cancel()
            return tuple(candidates)

        with patch(
            "bracing_optimizer.application.optimize_waler_global."
            "merge_equivalent_candidates",
            side_effect=cancel_after_merge,
        ):
            with self.assertRaises(SolverCancelled):
                use_case.execute(
                    OptimizeWalerGlobalRequest(
                        waler_inputs=(waler_input("W1"),),
                        material_ratio_targets=MaterialRatioTargets.normalized(
                            20, 50, 30
                        ),
                    ),
                    cancellation_token=source.token,
                )

        solve_global.assert_not_called()

    @patch(
        "bracing_optimizer.application.optimize_waler_global."
        "solve_global_waler_candidates"
    )
    def test_cancellation_immediately_before_exact_dp_discards_results(
        self,
        solve_global,
    ):
        source = CancellationSource()
        solutions = {
            "W1": [
                {"valid": True, "segments": [5_000], "joints": [], "score": 10}
            ]
        }

        class TokenAwareOptimizer(FakeWalerOptimizer):
            def execute(self, request, **kwargs):
                return super().execute(
                    request,
                    logger=kwargs.get("logger"),
                    retention_profile=kwargs.get("retention_profile"),
                )

        def cancel_on_dp_progress(progress):
            if progress.stage == "global_exact_dp":
                source.cancel()

        with self.assertRaises(SolverCancelled):
            OptimizeWalerGlobal(
                lambda: TokenAwareOptimizer(solutions, [])
            ).execute(
                OptimizeWalerGlobalRequest(
                    waler_inputs=(waler_input("W1"),),
                    material_ratio_targets=MaterialRatioTargets.normalized(
                        20, 50, 30
                    ),
                ),
                cancellation_token=source.token,
                on_progress=cancel_on_dp_progress,
            )

        solve_global.assert_not_called()

    @patch(
        "bracing_optimizer.application.optimize_waler_global."
        "solve_global_waler_candidates"
    )
    def test_same_token_cancels_local_search_and_skips_exact_dp(
        self,
        solve_global,
    ):
        source = CancellationSource()
        calls = []

        class CancellingOptimizer:
            def execute(
                self,
                request,
                *,
                logger=None,
                cancellation_token=None,
                retention_profile=None,
            ):
                calls.append(request.input.waler_id)
                self_outer.assertIs(cancellation_token, source.token)
                self_outer.assertIs(retention_profile, GLOBAL_FINAL_POPULATION)
                source.cancel()
                cancellation_token.raise_if_cancelled()

        self_outer = self
        use_case = OptimizeWalerGlobal(lambda: CancellingOptimizer())

        with self.assertRaises(SolverCancelled):
            use_case.execute(
                OptimizeWalerGlobalRequest(
                    waler_inputs=(waler_input("W1"), waler_input("W2")),
                    material_ratio_targets=MaterialRatioTargets.normalized(
                        20, 50, 30
                    ),
                ),
                cancellation_token=source.token,
            )

        self.assertEqual(calls, ["W1"])
        solve_global.assert_not_called()

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

    def test_rank_six_material_signature_can_be_selected(self):
        calls = []
        solutions = {
            "W1": [
                {
                    "valid": True,
                    "segments": [5_000],
                    "joints": [],
                    "score": 10 + rank,
                }
                for rank in range(5)
            ]
            + [
                {
                    "valid": True,
                    "segments": [7_000],
                    "joints": [],
                    "score": 20,
                }
            ],
        }
        result = OptimizeWalerGlobal(
            lambda: FakeWalerOptimizer(solutions, calls)
        ).execute(
            OptimizeWalerGlobalRequest(
                waler_inputs=(waler_input("W1"),),
                material_ratio_targets=MaterialRatioTargets.normalized(20, 50, 30),
            )
        )

        self.assertTrue(result.solution.valid)
        self.assertEqual(result.solution.selected_candidates[0].candidate_rank, 6)
        self.assertEqual(result.diagnostics.raw_candidate_count, 6)
        self.assertEqual(result.diagnostics.raw_candidate_counts_by_waler, {"W1": 6})
        self.assertEqual(
            result.diagnostics.retained_candidate_counts_by_waler,
            {"W1": 2},
        )

    def test_equivalent_waler_inputs_are_still_optimized_independently(self):
        calls = []
        solutions = {
            "W1": [
                {"valid": True, "segments": [5_000], "joints": [], "score": 10}
            ],
            "W2": [
                {"valid": True, "segments": [5_000], "joints": [], "score": 10}
            ],
        }
        first = waler_input("W1")
        second = replace(first, waler_id="W2")

        result = OptimizeWalerGlobal(
            lambda: FakeWalerOptimizer(solutions, calls)
        ).execute(
            OptimizeWalerGlobalRequest(
                waler_inputs=(first, second),
                material_ratio_targets=MaterialRatioTargets.normalized(20, 50, 30),
            )
        )

        self.assertEqual(calls, ["W1", "W2"])
        self.assertEqual(len(result.local_results), 2)
        self.assertEqual(
            [item.waler_id for item in result.solution.selected_candidates],
            ["W1", "W2"],
        )

    @patch(
        "bracing_optimizer.application.optimize_waler_global."
        "solve_global_waler_candidates"
    )
    def test_zero_legal_local_candidates_returns_diagnostics_without_fallback(
        self,
        solve_global,
    ):
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
                waler_inputs=(
                    replace(waler_input("W1"), purchasable_lengths=()),
                ),
                material_ratio_targets=MaterialRatioTargets.normalized(20, 50, 30),
            )
        )

        self.assertFalse(result.solution.valid)
        self.assertEqual(result.diagnostics.failed_waler_ids, ("W1",))
        self.assertIn("沒有合法", result.solution.reason)
        self.assertEqual(result.solution.selected_candidates, ())
        solve_global.assert_not_called()

    @patch(
        "bracing_optimizer.application.optimize_waler_global."
        "solve_global_waler_candidates"
    )
    def test_stage_projection_exception_returns_failure_without_partial_groups(
        self,
        solve_global,
    ):
        with patch(
            "bracing_optimizer.application.optimize_waler.wales.evolve",
            side_effect=RuntimeError("stage projection exception"),
        ):
            result = OptimizeWalerGlobal().execute(
                OptimizeWalerGlobalRequest(
                    waler_inputs=(waler_input("W1"),),
                    material_ratio_targets=MaterialRatioTargets.normalized(
                        20, 50, 30
                    ),
                )
            )

        self.assertFalse(result.solution.valid)
        self.assertEqual(result.diagnostics.failed_waler_ids, ("W1",))
        self.assertIn("stage projection exception", result.solution.reason)
        self.assertEqual(result.solution.selected_candidates, ())
        self.assertEqual(result.local_results, ())
        solve_global.assert_not_called()

    @patch(
        "bracing_optimizer.application.optimize_waler_global."
        "solve_global_waler_candidates"
    )
    def test_cross_stage_merge_exception_returns_failure_without_partial_groups(
        self,
        solve_global,
    ):
        stage_result = {
            "valid": True,
            "segments": [5_000, 7_000],
            "joints": [5_000],
            "score": 10.0,
        }

        def evolve(_cfg, _stock, *, diagnostics_out, **_kwargs):
            diagnostics_out.update(
                best_score_history=[10.0] * 5,
                valid_candidate_count=1,
                unique_valid_solution_count=1,
            )
            return [stage_result]

        with patch(
            "bracing_optimizer.application.optimize_waler.wales.evolve",
            side_effect=evolve,
        ), patch(
            "bracing_optimizer.application.optimize_waler."
            "solver_search.merge_waler_results",
            side_effect=RuntimeError("cross-stage merge exception"),
        ):
            result = OptimizeWalerGlobal().execute(
                OptimizeWalerGlobalRequest(
                    waler_inputs=(waler_input("W1"),),
                    material_ratio_targets=MaterialRatioTargets.normalized(
                        20, 50, 30
                    ),
                )
            )

        self.assertFalse(result.solution.valid)
        self.assertEqual(result.diagnostics.failed_waler_ids, ("W1",))
        self.assertIn("cross-stage merge exception", result.solution.reason)
        self.assertEqual(result.solution.selected_candidates, ())
        self.assertEqual(result.local_results, ())
        solve_global.assert_not_called()


if __name__ == "__main__":
    unittest.main()
