import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def imported_modules(module_name: str) -> set[str]:
    source = (PROJECT_ROOT / module_name).read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def imports_any(module_name: str, forbidden: set[str]) -> bool:
    imports = imported_modules(module_name)
    return any(
        imported == prefix or imported.startswith(f"{prefix}.")
        for imported in imports
        for prefix in forbidden
    )


class ApplicationDomainBoundaryTests(unittest.TestCase):
    def test_manual_waler_editing_and_evaluator_do_not_own_global_profile(self):
        manual_source = (
            PROJECT_ROOT / "bracing_optimizer/application/plan_editing.py"
        ).read_text(encoding="utf-8")
        evaluator_source = (
            PROJECT_ROOT / "bracing_optimizer/algorithms/wales.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn("GLOBAL_FINAL_POPULATION", manual_source)
        self.assertNotIn("retention_profile", manual_source)
        self.assertNotIn("GLOBAL_FINAL_POPULATION", evaluator_source)
        self.assertNotIn("WalerCandidateRetentionProfile", evaluator_source)

    def test_main_does_not_import_solver_algorithms(self):
        self.assertFalse(
            imports_any("main.py", {"bracing_optimizer.algorithms"})
        )

    def test_project_service_does_not_import_gui_or_dxf_adapters(self):
        forbidden = {
            "dxf_import",
            "main",
            "presentation",
            "bracing_optimizer.presentation",
            "tkinter",
        }

        self.assertFalse(
            imports_any(
                "bracing_optimizer/application/project_service.py",
                forbidden,
            )
        )

    def test_completed_relink_and_paused_review_recovery_are_distinct_contracts(self):
        from bracing_optimizer.application.project_service import (
            PausedReviewRelinkRequest,
            RelinkDxfRequest,
        )

        self.assertIsNot(PausedReviewRelinkRequest, RelinkDxfRequest)
        self.assertNotIn(
            "project_rows",
            PausedReviewRelinkRequest.__dataclass_fields__,
        )
        self.assertIn("project_rows", RelinkDxfRequest.__dataclass_fields__)
        self.assertIn(
            "workflow_status",
            PausedReviewRelinkRequest.__dataclass_fields__,
        )

    def test_solver_core_and_use_cases_do_not_import_external_adapters(self):
        forbidden = {
            "cad_builder",
            "dxf_import",
            "ezdxf",
            "inventory_repository",
            "json",
            "main",
            "project_persistence",
            "presentation",
            "bracing_optimizer.infrastructure",
            "bracing_optimizer.presentation",
            "tkinter",
        }

        for module_name in (
            "bracing_optimizer/algorithms/support.py",
            "bracing_optimizer/algorithms/wales.py",
            "bracing_optimizer/algorithms/waler_global.py",
            "bracing_optimizer/application/optimize_support_zone.py",
            "bracing_optimizer/application/optimize_waler.py",
            "bracing_optimizer/application/optimize_waler_global.py",
            "bracing_optimizer/application/plan_editing.py",
            "bracing_optimizer/application/material_spec_editing.py",
            "bracing_optimizer/application/project_data.py",
            "bracing_optimizer/application/project_mapper.py",
            "bracing_optimizer/application/project_results.py",
            "bracing_optimizer/application/project_validation.py",
            "bracing_optimizer/application/solver_input_builder.py",
        ):
            with self.subTest(module=module_name):
                self.assertFalse(
                    imports_any(module_name, forbidden),
                    f"{module_name} must not import an external adapter",
                )

    def test_algorithms_do_not_import_application_or_presentation(self):
        forbidden = {
            "bracing_optimizer.application",
            "main",
            "presentation",
            "tkinter",
        }

        for module_name in (
            "bracing_optimizer/algorithms/cancellation.py",
            "bracing_optimizer/algorithms/solver_search.py",
            "bracing_optimizer/algorithms/support.py",
            "bracing_optimizer/algorithms/wales.py",
            "bracing_optimizer/algorithms/waler_global.py",
        ):
            with self.subTest(module=module_name):
                self.assertFalse(
                    imports_any(module_name, forbidden),
                    f"{module_name} must not depend on an outer layer",
                )

    def test_solver_operation_registry_does_not_import_gui_or_infrastructure(self):
        self.assertFalse(
            imports_any(
                "bracing_optimizer/application/solver_operation_registry.py",
                {
                    "bracing_optimizer.infrastructure",
                    "bracing_optimizer.presentation",
                    "main",
                    "tkinter",
                },
            )
        )

    def test_support_algorithm_consumes_contract_without_project_geometry(self):
        self.assertFalse(
            imports_any(
                "bracing_optimizer/algorithms/support.py",
                {
                    "bracing_optimizer.domain.project_domain",
                    "bracing_optimizer.domain.support_adjacency",
                    "bracing_optimizer.application.project_data",
                    "bracing_optimizer.application.solver_input_builder",
                },
            )
        )

    def test_domain_policy_modules_do_not_import_application_or_solver_modules(self):
        forbidden = {
            "cad_builder",
            "dxf_import",
            "ezdxf",
            "inventory_repository",
            "json",
            "main",
            "optimize_support_zone",
            "optimize_waler",
            "bracing_optimizer.algorithms",
            "bracing_optimizer.application",
            "project_data",
            "project_persistence",
            "solver_input_builder",
            "support",
            "tkinter",
            "wales",
        }

        for module_name in (
            "bracing_optimizer/domain/material_rules.py",
            "bracing_optimizer/domain/project_domain.py",
            "bracing_optimizer/domain/support_adjacency.py",
        ):
            with self.subTest(module=module_name):
                self.assertFalse(
                    imports_any(module_name, forbidden),
                    f"{module_name} must remain independent from outer layers",
                )

    def test_infrastructure_modules_do_not_import_gui_layers(self):
        forbidden = {
            "main",
            "presentation",
            "bracing_optimizer.presentation",
            "tkinter",
        }

        for module_name in (
            "bracing_optimizer/infrastructure/cad_builder.py",
            "bracing_optimizer/infrastructure/dxf_result_export.py",
            "bracing_optimizer/infrastructure/excel_result_export.py",
            "bracing_optimizer/infrastructure/inventory_repository.py",
            "bracing_optimizer/infrastructure/project_persistence.py",
        ):
            with self.subTest(module=module_name):
                self.assertFalse(
                    imports_any(module_name, forbidden),
                    f"{module_name} must not import a GUI layer",
                )


if __name__ == "__main__":
    unittest.main()
