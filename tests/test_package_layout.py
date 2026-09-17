import importlib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_MODULES = (
    "bracing_optimizer.domain.material_rules",
    "bracing_optimizer.domain.project_domain",
    "bracing_optimizer.algorithms.solver_search",
    "bracing_optimizer.algorithms.support",
    "bracing_optimizer.algorithms.wales",
    "bracing_optimizer.algorithms.waler_global",
    "bracing_optimizer.application.optimize_support_zone",
    "bracing_optimizer.application.optimize_waler",
    "bracing_optimizer.application.optimize_waler_global",
    "bracing_optimizer.application.plan_editing",
    "bracing_optimizer.application.project_data",
    "bracing_optimizer.application.project_mapper",
    "bracing_optimizer.application.project_results",
    "bracing_optimizer.application.project_service",
    "bracing_optimizer.application.project_validation",
    "bracing_optimizer.application.solver_input_builder",
    "bracing_optimizer.infrastructure.cad_builder",
    "bracing_optimizer.infrastructure.dxf_result_export",
    "bracing_optimizer.infrastructure.excel_result_export",
    "bracing_optimizer.infrastructure.inventory_repository",
    "bracing_optimizer.infrastructure.project_persistence",
    "bracing_optimizer.presentation",
    "bracing_optimizer.presentation.cad_view_interaction",
    "dxf_import",
    "dxf_import.support_pairing",
    "tools.inventory_conversion",
)

LEGACY_PATHS = (
    "DXFinput.py",
    "cad_builder.py",
    "cad_view_interaction.py",
    "dxf_result_export.py",
    "inventory_conversion.py",
    "inventory_repository.py",
    "material_rules.py",
    "optimize_support_zone.py",
    "optimize_waler.py",
    "plan_editing.py",
    "project_data.py",
    "project_domain.py",
    "project_mapper.py",
    "project_persistence.py",
    "project_results.py",
    "project_service.py",
    "project_validation.py",
    "solver_input_builder.py",
    "solver_search.py",
    "support.py",
    "wales.py",
    "presentation",
)


class PackageLayoutTests(unittest.TestCase):
    def test_canonical_modules_are_importable(self):
        for module_name in CANONICAL_MODULES:
            with self.subTest(module=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))

    def test_legacy_compatibility_paths_are_removed(self):
        for relative_path in LEGACY_PATHS:
            with self.subTest(path=relative_path):
                self.assertFalse((PROJECT_ROOT / relative_path).exists())


if __name__ == "__main__":
    unittest.main()
