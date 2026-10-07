import ast
import inspect
import unittest
from pathlib import Path
from unittest.mock import patch

from bracing_optimizer.algorithms.cancellation import (
    CancellationSource,
    SolverCancelled,
)

from bracing_optimizer.algorithms import solver_search, support
from bracing_optimizer.domain.material_rules import MaterialRatioTargets
from bracing_optimizer.application.project_data import ProjectDataModel
from main import SupportSolverDialog
from bracing_optimizer.application.optimize_support_zone import (
    OptimizeSupportZone,
    OptimizeSupportZoneRequest,
)
from bracing_optimizer.application.solver_input_builder import (
    SupportAdjacencyContract,
    SupportInputBuilder,
    SupportOptimizationUnit,
    SupportZoneInput,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class OptimizeSupportZoneTests(unittest.TestCase):
    def test_cancelled_operation_does_not_generate_or_commit_cache(self):
        cache = {("existing",): ["preserved"]}
        source = CancellationSource()

        plan = support.SupportPlan(
            support_id="template",
            pieces=[("steel", 4_000), ("steel", 6_000)],
            joints=[4_000],
            gap=0,
            jack_center=5_000,
            jack_region_id=2,
            score=10,
            valid=True,
        )

        def cancel_after_generation(*, cancellation_token, **_kwargs):
            self.assertIs(cancellation_token, source.token)
            source.cancel()
            return [plan]

        with (
            patch(
                "bracing_optimizer.application.optimize_support_zone.support."
                "build_support_candidate_cache_key",
                autospec=True,
                return_value=("new",),
            ),
            patch(
                "bracing_optimizer.application.optimize_support_zone.support."
                "generate_single_support_candidates",
                autospec=True,
                side_effect=cancel_after_generation,
            ) as generate,
        ):
            with self.assertRaises(SolverCancelled):
                OptimizeSupportZone(cache).execute(
                    self.request(),
                    cancellation_token=source.token,
                )

        generate.assert_called_once()
        self.assertEqual(cache, {("existing",): ["preserved"]})

    @staticmethod
    def request():
        config = support.SupportConfig(
            support_id="S1",
            total_length=10_000,
            pile_centers=[],
            waler_centers=[],
            material_spec="H400x400",
            steel_lengths=[4_000, 6_000],
        )
        unit = SupportOptimizationUnit(
            unit_id="S1",
            configs=(config,),
            member_ids=("S1",),
        )
        return OptimizeSupportZoneRequest(
            input=SupportZoneInput(
                "Z1",
                (config,),
                SupportAdjacencyContract(
                    zoning="Z1",
                    common_direction=(1.0, 0.0),
                    row_direction=(0.0, 1.0),
                    ordered_units=(unit,),
                    pairs=(),
                ),
            ),
            material_ratio_targets=MaterialRatioTargets.normalized(50, 50, 0),
            material_ratio_weight=10_000,
        )

    def test_execute_owns_candidate_cache_and_global_search(self):
        plan = support.SupportPlan(
            support_id="template",
            pieces=[("steel", 4_000), ("steel", 6_000)],
            joints=[4_000],
            gap=0,
            jack_center=5_000,
            jack_region_id=2,
            score=10,
            valid=True,
        )
        solution = support.GlobalSolution(
            plans=[plan],
            total_score=10,
            valid=True,
        )
        cache = {}
        progress = []

        def build_global_solution(**kwargs):
            kwargs["diagnostics_out"].update({
                "final_unique_solution_count": 3,
                "pruning_was_active": False,
            })
            return solution

        with (
            patch(
                "bracing_optimizer.application.optimize_support_zone.support.build_support_candidate_cache_key",
                autospec=True,
                return_value=("S1", "policy"),
            ),
            patch(
                "bracing_optimizer.application.optimize_support_zone.support.generate_single_support_candidates",
                autospec=True,
                return_value=[plan],
            ) as generate,
            patch(
                "bracing_optimizer.application.optimize_support_zone.support.build_global_solution",
                autospec=True,
                side_effect=build_global_solution,
            ) as build_global,
        ):
            use_case = OptimizeSupportZone(cache)
            first = use_case.execute(
                self.request(),
                on_progress=progress.append,
            )
            self.assertNotIn(("S1", "policy"), cache)
            use_case.adopt_candidate_cache_updates(first)
            second = use_case.execute(self.request())

        self.assertIs(first.solution, solution)
        self.assertIs(second.solution, solution)
        self.assertTrue(first.diagnostics.legal_solution_found)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(build_global.call_count, 2)
        build_kwargs = build_global.call_args.kwargs
        self.assertEqual(
            build_kwargs["material_ratio_targets"],
            {"short": 0.5, "mid": 0.5, "long": 0.0},
        )
        self.assertEqual(build_kwargs["material_ratio_weight"], 10_000)
        self.assertIsInstance(
            build_kwargs["candidates_by_support"][0][0],
            support.SupportUnitCandidate,
        )
        self.assertIn(("S1", "policy"), cache)
        self.assertIn("candidate_generation", {item.stage for item in progress})
        self.assertIn("global_optimization", {item.stage for item in progress})
        self.assertIn("finalizing", {item.stage for item in progress})
        self.assertIsNone(support.logger)

    def test_missing_candidates_returns_diagnostics_without_global_search(self):
        with (
            patch(
                "bracing_optimizer.application.optimize_support_zone.support.build_support_candidate_cache_key",
                autospec=True,
                return_value=("empty",),
            ),
            patch(
                "bracing_optimizer.application.optimize_support_zone.support.generate_single_support_candidates",
                autospec=True,
                return_value=[],
            ),
            patch(
                "bracing_optimizer.application.optimize_support_zone.support.build_global_solution",
                autospec=True,
            ) as build_global,
        ):
            result = OptimizeSupportZone({}).execute(self.request())

        self.assertIsNone(result.solution)
        self.assertFalse(result.diagnostics.legal_solution_found)
        self.assertEqual(
            result.diagnostics.main_issue_category,
            solver_search.ENGINEERING_CONSTRAINT_LIMITED,
        )
        build_global.assert_not_called()

    def test_geometry_order_and_cache_hits_produce_same_phase2_result(self):
        def project(rows):
            return ProjectDataModel(
                walers=[
                    {"WalerID": "W1", "material_spec": "H400x400"},
                    {"WalerID": "W2", "material_spec": "H400x400"},
                ],
                struts=[
                    {
                        "FromWaler": "W1",
                        "ToWaler": "W2",
                        "Zoning": "Z1",
                        "material_spec": "H400x400",
                        **row,
                    }
                    for row in rows
                ],
                inventory=[{
                    "ItemCode": "S-40",
                    "Spec": "H400x400",
                    "Usage": "支撐",
                    "Length": 4000,
                    "Qty": 10,
                }],
            )

        rows = [
            {"StrutID": "S3", "StartX": 0, "StartY": 3000,
             "EndX": 10000, "EndY": 3000, "ColumnPositions": "300"},
            {"StrutID": "S1", "StartX": 0, "StartY": 0,
             "EndX": 10000, "EndY": 0, "ColumnPositions": "100"},
            {"StrutID": "S2", "StartX": 0, "StartY": 1500,
             "EndX": 10000, "EndY": 1500, "ColumnPositions": "200"},
        ]
        first_input = SupportInputBuilder().build_zone(project(rows), "Z1")
        second_input = SupportInputBuilder().build_zone(
            project(list(reversed(rows))), "Z1"
        )
        policy = solver_search.SolverSearchPolicy(
            **{
                **solver_search.DEFAULT_SEARCH_POLICY.__dict__,
                "support_global_search_stages": (
                    solver_search.SupportGlobalSearchStage("TEST", 20),
                ),
                "minimum_unique_solution_count": 1,
                "support_phase1_retained_candidate_count": 1,
            }
        )
        cache = {}

        def candidates_for_config(*, config, **_kwargs):
            centers = {"S1": 1000, "S2": 1600, "S3": 2200}
            return [support.SupportPlan(
                support_id="template",
                pieces=[("steel", 4000), ("jack", 600)],
                joints=[4000],
                gap=0,
                jack_center=centers[config.support_id],
                jack_region_id=1,
                score=10,
                valid=True,
                pile_centers=list(config.pile_centers),
            )]

        targets = MaterialRatioTargets.normalized(1, 0, 0)
        with patch(
            "bracing_optimizer.application.optimize_support_zone.support."
            "generate_single_support_candidates",
            autospec=True,
            side_effect=candidates_for_config,
        ) as generate:
            optimizer = OptimizeSupportZone(cache, search_policy=policy)
            first = optimizer.execute(OptimizeSupportZoneRequest(
                input=first_input,
                material_ratio_targets=targets,
                material_ratio_weight=0,
            ))
            optimizer.adopt_candidate_cache_updates(first)
            second = optimizer.execute(OptimizeSupportZoneRequest(
                input=second_input,
                material_ratio_targets=targets,
                material_ratio_weight=0,
            ))

        self.assertEqual(generate.call_count, 3)
        self.assertEqual(
            [item.support_id for item in first.solution.plans],
            ["S1", "S2", "S3"],
        )
        self.assertEqual(
            [item.support_id for item in second.solution.plans],
            ["S1", "S2", "S3"],
        )
        self.assertEqual(first.solution.total_score, second.solution.total_score)
        self.assertEqual(
            first.solution.search_diagnostics["adjacency_pairs"],
            second.solution.search_diagnostics["adjacency_pairs"],
        )
        self.assertEqual(
            first.diagnostics.adjacency_pairs,
            first.solution.search_diagnostics["adjacency_pairs"],
        )
        self.assertTrue(first.diagnostics.phase2_executed)


class OptimizeSupportZoneArchitectureTests(unittest.TestCase):
    def test_use_case_has_no_gui_or_main_dependency(self):
        source = (
            PROJECT_ROOT
            / "bracing_optimizer"
            / "application"
            / "optimize_support_zone.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(
                    alias.name.split(".", 1)[0] for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])

        self.assertTrue({"main", "tkinter"}.isdisjoint(imported_roots))

    def test_dialog_does_not_control_solver_search(self):
        source = inspect.getsource(SupportSolverDialog)

        for implementation_detail in (
            "generate_single_support_candidates",
            "build_support_candidate_cache_key",
            "build_global_solution",
            "assess_support_stage",
            "select_best_support_solution",
            "Beam Width",
            "Phase 1",
            "Phase 2",
        ):
            self.assertNotIn(implementation_detail, source)
        self.assertIn("optimize_support_zone.execute", source)


if __name__ == "__main__":
    unittest.main()
