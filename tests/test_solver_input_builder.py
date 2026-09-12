import ast
import copy
import unittest
from pathlib import Path

from main import SupportInputApp
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.solver_input_builder import (
    InventoryLookup,
    SolverInputBuildError,
    SupportInputBuilder,
    WalerInputBuilder,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class InventoryLookupTests(unittest.TestCase):
    def test_filters_lengths_and_positive_stock_by_spec_and_usage(self):
        inventory = InventoryLookup([
            {
                "ItemCode": "S-45",
                "Spec": "H350",
                "Usage": "支撐",
                "Length": 4500,
                "Qty": 2,
            },
            {
                "ItemCode": "S-50",
                "Spec": "H350",
                "Usage": "支撐",
                "Length": 5000,
                "Qty": 0,
            },
            {
                "ItemCode": "W-80",
                "Spec": "H350",
                "Usage": "圍令",
                "Length": 8000,
                "Qty": 7,
            },
        ])

        self.assertEqual(
            inventory.purchasable_lengths("H350", "支撐"),
            [4500, 5000],
        )
        self.assertEqual(inventory.stock_items("H350", "支撐"), [{
            "id": "S-45",
            "length": 4500,
            "qty": 2,
        }])
        self.assertEqual(inventory.quantity("H350", "圍令", 8000), 7)


class SupportInputBuilderTests(unittest.TestCase):
    @staticmethod
    def model():
        return ProjectDataModel(
            walers=[
                {"WalerID": "W1", "material_spec": "RC"},
                {"WalerID": "W2", "material_spec": "H350"},
            ],
            struts=[{
                "StrutID": "S1",
                "FromWaler": "W1",
                "ToWaler": "W2",
                "StartX": 0,
                "StartY": 0,
                "EndX": 9700,
                "EndY": 0,
                "ColumnPositions": "2500, 7200",
                "BeamPositions": "4800",
                "TargetJackRegion": 3,
                "Zoning": "Z1",
                "material_spec": "H350",
            }],
            inventory=[
                {
                    "ItemCode": "S-45",
                    "Spec": "H350",
                    "Usage": "支撐",
                    "Length": 4500,
                    "Qty": 0,
                },
                {
                    "ItemCode": "S-50",
                    "Spec": "H350",
                    "Usage": "支撐",
                    "Length": 5000,
                    "Qty": 8,
                },
            ],
        )

    def test_builds_zone_engineering_input_without_mutating_project(self):
        model = self.model()
        before = copy.deepcopy(model.to_case_data())

        result = SupportInputBuilder().build_zone(model, "Z1")

        self.assertEqual(result.zoning, "Z1")
        self.assertEqual(len(result.configs), 1)
        config = result.configs[0]
        self.assertEqual(config.support_id, "S1")
        self.assertEqual(config.total_length, 9700)
        self.assertEqual(config.pile_centers, [2500, 7200])
        self.assertEqual(config.waler_centers, [4800])
        self.assertEqual(config.target_jack_region, 3)
        self.assertEqual(config.from_waler_type, "RC")
        self.assertEqual(config.to_waler_type, "Steel")
        self.assertEqual(config.steel_lengths, [4500, 5000])
        self.assertEqual(model.to_case_data(), before)

class WalerInputBuilderTests(unittest.TestCase):
    def test_builds_all_walers_and_projects_forbidden_points(self):
        model = ProjectDataModel(
            walers=[{
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 10000,
                "EndY": 0,
                "material_spec": "H400",
            }],
            struts=[{
                "StrutID": "S1",
                "FromWaler": "W1",
                "StartX": 2000,
                "StartY": 0,
                "EndX": 2000,
                "EndY": 5000,
                "FromBraceToWalerStartLen": 500,
                "FromBraceToWalerEndLen": 700,
            }],
            braces=[{
                "BraceID": "B1",
                "FromWaler": "W1",
                "StartX": 8000,
                "StartY": 0,
                "EndX": 9000,
                "EndY": 1000,
            }],
            inventory=[{
                "ItemCode": "W-80",
                "Spec": "H400",
                "Usage": "圍令",
                "Length": 8000,
                "Qty": 2,
            }],
        )
        before = copy.deepcopy(model.to_case_data())

        result = WalerInputBuilder().build_all(model)

        self.assertEqual(set(result), {"W1"})
        waler_input = result["W1"]
        self.assertEqual(waler_input.start_point, (0, 0))
        self.assertEqual(waler_input.end_point, (10000, 0))
        self.assertEqual(waler_input.total_length, 10000)
        self.assertEqual(waler_input.forbidden_points, (1500, 2000, 2700, 8000))
        self.assertEqual(waler_input.purchasable_lengths, (8000,))
        self.assertEqual(waler_input.stock_items[0]["id"], "W-80")
        self.assertEqual(model.to_case_data(), before)

    def test_invalid_waler_geometry_reports_builder_error(self):
        model = ProjectDataModel(walers=[{
            "WalerID": "W1",
            "StartX": 0,
            "StartY": 0,
            "EndX": "",
            "EndY": 0,
        }])

        with self.assertRaises(SolverInputBuildError) as caught:
            WalerInputBuilder().build_all(model)

        self.assertIn("W1", str(caught.exception))


class SolverInputBuilderArchitectureTests(unittest.TestCase):
    def test_builder_module_has_no_gui_or_main_dependency(self):
        source = (
            PROJECT_ROOT
            / "bracing_optimizer"
            / "application"
            / "solver_input_builder.py"
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

    def test_support_input_app_no_longer_owns_solver_input_builders(self):
        self.assertFalse(hasattr(SupportInputApp, "build_support_inputs"))
        self.assertFalse(hasattr(SupportInputApp, "build_waler_inputs"))
        self.assertFalse(hasattr(SupportInputApp, "_get_inventory_items"))
        self.assertFalse(hasattr(SupportInputApp, "_get_purchasable_lengths"))


if __name__ == "__main__":
    unittest.main()
