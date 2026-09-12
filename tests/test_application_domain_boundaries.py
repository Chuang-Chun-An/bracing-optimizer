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
            "bracing_optimizer/application/optimize_support_zone.py",
            "bracing_optimizer/application/optimize_waler.py",
            "bracing_optimizer/application/plan_editing.py",
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
            "bracing_optimizer/algorithms/solver_search.py",
            "bracing_optimizer/algorithms/support.py",
            "bracing_optimizer/algorithms/wales.py",
        ):
            with self.subTest(module=module_name):
                self.assertFalse(
                    imports_any(module_name, forbidden),
                    f"{module_name} must not depend on an outer layer",
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
