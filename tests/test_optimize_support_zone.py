import ast
import inspect
import unittest
from pathlib import Path
from unittest.mock import patch

from bracing_optimizer.algorithms import solver_search, support
from bracing_optimizer.domain.material_rules import MaterialRatioTargets
from main import SupportSolverDialog
from bracing_optimizer.application.optimize_support_zone import (
    OptimizeSupportZone,
    OptimizeSupportZoneRequest,
)
from bracing_optimizer.application.solver_input_builder import SupportZoneInput


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class OptimizeSupportZoneTests(unittest.TestCase):
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
        return OptimizeSupportZoneRequest(
            input=SupportZoneInput("Z1", (config,)),
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
