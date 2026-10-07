import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from bracing_optimizer.application.optimize_waler import (
    GLOBAL_FINAL_POPULATION,
    SINGLE_TOP_5,
    OptimizeWaler,
    OptimizeWalerRequest,
    WalerOptimizationExcludedError,
    is_rc_waler_material,
    partition_waler_optimization_inputs,
)
from bracing_optimizer.application.solver_input_builder import WalerProblemInput
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.solver_input_builder import WalerInputBuilder
from bracing_optimizer.algorithms.solver_search import (
    DEFAULT_SEARCH_POLICY,
    WalerSearchStage,
)
from bracing_optimizer.algorithms.cancellation import (
    CancellationSource,
    SolverCancelled,
)
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
    @staticmethod
    def _unique_solutions(count=8, *, start=1_000):
        return [
            {
                "segments": [start + index, 12_000 - start - index],
                "joints": [start + index],
                "gap": 0,
                "score": float(index),
                "valid": True,
            }
            for index in range(count)
        ]

    @patch("bracing_optimizer.application.optimize_waler.wales.evolve")
    def test_retention_profile_keeps_single_top_five_and_global_all(self, evolve):
        solutions = self._unique_solutions()

        def run(_cfg, _stock, *, seed, diagnostics_out, **kwargs):
            diagnostics_out.update(
                best_score_history=[10, 10, 10, 10, 10],
                valid_candidate_count=8,
                unique_valid_solution_count=8,
            )
            return (
                solutions
                if kwargs.get("retain_all_final_results")
                else solutions[:5]
            )

        evolve.side_effect = run
        use_case = OptimizeWaler()

        single = use_case.execute(make_request(), logger=lambda *args: None)
        global_result = use_case.execute(
            make_request(),
            logger=lambda *args: None,
            retention_profile=GLOBAL_FINAL_POPULATION,
        )

        self.assertEqual(len(single.solutions), 5)
        self.assertEqual(single.diagnostics.retention_profile, SINGLE_TOP_5.value)
        self.assertEqual(len(global_result.solutions), 8)
        self.assertEqual(
            global_result.diagnostics.retention_profile,
            GLOBAL_FINAL_POPULATION.value,
        )
        self.assertEqual(
            global_result.diagnostics.candidate_count_after_cross_stage_solution_merge,
            8,
        )
        self.assertEqual(
            global_result.diagnostics.stage_records[0][
                "result_count_after_stage_solution_merge"
            ],
            8,
        )

    def test_retention_profile_does_not_change_cache_key_shape(self):
        use_case = OptimizeWaler()
        key = use_case.build_cache_key(make_request())

        self.assertEqual(key, use_case.build_cache_key(make_request()))
        self.assertEqual(key[0], "waler_tail_adjustment_v2")
        self.assertNotEqual(key[0], "waler_tail_adjustment_v1")
        self.assertNotIn(SINGLE_TOP_5.value, key)
        self.assertNotIn(GLOBAL_FINAL_POPULATION.value, key)

    @patch("bracing_optimizer.application.optimize_waler.wales.evolve")
    def test_global_cross_stage_union_is_not_truncated_and_policy_is_unchanged(
        self,
        evolve,
    ):
        policy = replace(
            DEFAULT_SEARCH_POLICY,
            waler_search_stages=(
                WalerSearchStage("STANDARD", 1, 20, 11),
                WalerSearchStage("ENHANCED", 2, 30, 22),
            ),
        )
        stage_one = self._unique_solutions(4, start=1_000)
        stage_two = self._unique_solutions(4, start=2_000)

        def run(config, _stock, *, seed, diagnostics_out, **kwargs):
            self.assertTrue(kwargs["retain_all_final_results"])
            self.assertEqual(
                (config.generations, config.population_size),
                (1, 20) if seed == 11 else (2, 30),
            )
            diagnostics_out.update(
                best_score_history=[10, 10, 10, 10, 10],
                valid_candidate_count=1 if seed == 11 else 8,
                unique_valid_solution_count=1 if seed == 11 else 8,
            )
            return stage_one if seed == 11 else stage_two

        evolve.side_effect = run
        result = OptimizeWaler(search_policy=policy).execute(
            make_request(),
            logger=lambda *args: None,
            retention_profile=GLOBAL_FINAL_POPULATION,
        )

        self.assertEqual(evolve.call_count, 2)
        self.assertEqual([record["stage"] for record in result.diagnostics.stage_records], ["STANDARD", "ENHANCED"])
        self.assertEqual(len(result.solutions), 8)
        self.assertEqual(
            result.diagnostics.candidate_count_after_cross_stage_solution_merge,
            8,
        )

    @patch("bracing_optimizer.application.optimize_waler.wales.evolve")
    def test_cancellation_after_search_discards_partial_result(self, evolve):
        source = CancellationSource()

        def run(
            _cfg,
            _stock,
            *,
            seed,
            diagnostics_out,
            cancellation_token,
        ):
            self.assertIs(cancellation_token, source.token)
            source.cancel()
            diagnostics_out.update(
                best_score_history=[10],
                valid_candidate_count=1,
                unique_valid_solution_count=1,
            )
            return [{"valid": True, "score": 10, "segments": [12_000]}]

        evolve.side_effect = run

        with self.assertRaises(SolverCancelled):
            OptimizeWaler().execute(
                make_request(),
                logger=lambda *args: None,
                cancellation_token=source.token,
            )

        self.assertEqual(evolve.call_count, 1)

    def test_rc_exclusion_is_not_a_general_material_classification(self):
        for value in ("RC", " rc ", "Rc"):
            with self.subTest(value=value):
                self.assertTrue(is_rc_waler_material(value))
        for value in ("", None, "H400x400", "CUSTOM"):
            with self.subTest(value=value):
                self.assertFalse(is_rc_waler_material(value))

        inputs = tuple(
            replace(make_request().input, waler_id=waler_id, material_spec=spec)
            for waler_id, spec in (
                ("W1", "RC"),
                ("W2", ""),
                ("W3", "CUSTOM"),
                ("W4", "H400x400"),
            )
        )
        eligible, excluded = partition_waler_optimization_inputs(inputs)

        self.assertEqual([item.waler_id for item in eligible], ["W2", "W3", "W4"])
        self.assertEqual([item.waler_id for item in excluded], ["W1"])

    @patch("bracing_optimizer.application.optimize_waler.wales.evolve")
    def test_rc_request_is_rejected_before_algorithm_execution(self, evolve):
        request = replace(
            make_request("W-RC"),
            input=replace(make_request("W-RC").input, material_spec=" rc "),
        )

        with self.assertRaises(WalerOptimizationExcludedError):
            OptimizeWaler().execute(request, logger=lambda *args: None)

        evolve.assert_not_called()

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

    @patch(
        "bracing_optimizer.application.optimize_waler.wales.is_joint_path_feasible",
        return_value=False,
    )
    @patch("bracing_optimizer.application.optimize_waler.wales.evolve")
    def test_explicit_empty_lengths_report_no_legal_solution_without_exception(
        self,
        evolve,
        _is_feasible,
    ):
        invalid = {
            "segments": [6_000, 6_000],
            "joints": [6_000],
            "score": 1_100_000,
            "valid": False,
        }

        def run(config, _stock, *, seed, diagnostics_out):
            self.assertEqual(config.purchasable_lengths, [])
            diagnostics_out.update(
                best_score_history=[1_100_000],
                valid_candidate_count=0,
                unique_valid_solution_count=0,
            )
            return [invalid]

        evolve.side_effect = run
        request = replace(
            make_request("W-empty"),
            input=replace(
                make_request("W-empty").input,
                purchasable_lengths=(),
            ),
        )

        result = OptimizeWaler().execute(request, logger=lambda *args: None)

        self.assertEqual(result.diagnostics.search_status, "no_legal_solution")
        self.assertFalse(result.diagnostics.legal_solution_found)
        self.assertTrue(result.solutions)
        self.assertTrue(all(not item["valid"] for item in result.solutions))

    def test_explicit_empty_lengths_real_search_returns_normal_failure(self):
        policy = replace(
            DEFAULT_SEARCH_POLICY,
            waler_search_stages=(
                WalerSearchStage(
                    "TEST",
                    generations=1,
                    population_size=8,
                    random_seed=42,
                ),
            ),
            stability_window=2,
        )
        request = replace(
            make_request("W-empty-real"),
            input=replace(
                make_request("W-empty-real").input,
                purchasable_lengths=(),
            ),
        )

        result = OptimizeWaler(search_policy=policy).execute(
            request,
            logger=lambda *args: None,
        )

        self.assertEqual(result.config.purchasable_lengths, [])
        self.assertEqual(result.diagnostics.search_status, "no_legal_solution")
        self.assertFalse(result.diagnostics.legal_solution_found)
        self.assertEqual(result.diagnostics.valid_candidate_count, 0)
        self.assertTrue(result.solutions)
        self.assertTrue(all(not item["valid"] for item in result.solutions))

    def test_raw_y05_y29_waler_lengths_resolve_with_canonical_tail(self):
        project_root = Path(__file__).resolve().parents[1]
        cases = (
            (
                "Y05車站第一層支撐",
                "W2",
                16_950,
                16_500,
                300,
                150,
            ),
            (
                "Y29車站第一層支撐",
                "W4",
                22_400,
                22_000,
                300,
                100,
            ),
            (
                "Y29車站第一層支撐",
                "W5",
                12_200,
                12_000,
                100,
                100,
            ),
        )

        for (
            case_name,
            waler_id,
            required_length,
            steel_length,
            adjustment,
            gap,
        ) in cases:
            with self.subTest(case=case_name, waler_id=waler_id):
                project_path = (
                    project_root / "project_cases" / case_name / "project.json"
                )
                payload = json.loads(project_path.read_text(encoding="utf-8"))
                project_data = ProjectDataModel.from_case_data(
                    payload["input_data"]
                )
                problem = WalerInputBuilder.build_all(project_data)[waler_id]

                self.assertEqual(problem.total_length, required_length)
                result = OptimizeWaler().execute(
                    OptimizeWalerRequest(
                        input=problem,
                        material_ratio_targets=(
                            MaterialRatioTargets.normalized(20, 50, 30)
                        ),
                    ),
                    logger=lambda *_args: None,
                )
                legal = [item for item in result.solutions if item["valid"]]

                self.assertTrue(legal)
                selected = legal[0]
                self.assertEqual(selected["steel_length"], steel_length)
                self.assertEqual(selected["tail_adjustment"], adjustment)
                self.assertEqual(selected["gap"], gap)
                self.assertEqual(selected["pieces"][-1], ("shim", adjustment))
                self.assertEqual(
                    sum(length for kind, length in selected["pieces"] if kind == "steel"),
                    steel_length,
                )
                self.assertEqual(
                    selected["steel_length"]
                    + selected["tail_adjustment"]
                    + selected["gap"],
                    required_length,
                )


if __name__ == "__main__":
    unittest.main()
