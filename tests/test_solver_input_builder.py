import ast
import copy
import unittest
from pathlib import Path

from main import SupportInputApp
from bracing_optimizer.algorithms import support
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.solver_input_builder import (
    InventoryLookup,
    SolverInputBuildError,
    SupportInputBuilder,
    WalerInputBuilder,
)
from bracing_optimizer.domain.support_adjacency import (
    ZONING_ANGLE_OUT_OF_TOLERANCE,
    ZONING_LENGTH_OUT_OF_TOLERANCE,
    ZONING_PROJECTION_TIE,
    ZONING_ZERO_LENGTH_AXIS,
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

    def test_blank_spec_resolves_default_lengths_with_quantity_99(self):
        inventory = InventoryLookup([])

        lengths = inventory.purchasable_lengths("", "圍令")
        stock_items = inventory.stock_items("", "圍令")

        self.assertEqual(lengths, support.STEEL_LENGTHS)
        self.assertEqual(
            [item["length"] for item in stock_items],
            support.STEEL_LENGTHS,
        )
        self.assertTrue(stock_items)
        self.assertTrue(all(item["qty"] == 99 for item in stock_items))

    def test_explicit_quantity_five_is_preserved(self):
        inventory = InventoryLookup([{
            "ItemCode": "W-60",
            "Spec": "H400",
            "Usage": "圍令",
            "Length": 6000,
            "Qty": 5,
        }])

        self.assertEqual(inventory.purchasable_lengths("H400", "圍令"), [6000])
        self.assertEqual(
            inventory.stock_items("H400", "圍令"),
            [{"id": "W-60", "length": 6000, "qty": 5}],
        )

    def test_named_spec_without_inventory_resolves_explicit_empty_context(self):
        inventory = InventoryLookup([])

        self.assertEqual(inventory.purchasable_lengths("H400", "圍令"), [])
        self.assertEqual(inventory.stock_items("H400", "圍令"), [])


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

    @staticmethod
    def _geometry_model(rows):
        return ProjectDataModel(
            walers=[
                {"WalerID": "W1", "material_spec": "H350"},
                {"WalerID": "W2", "material_spec": "H350"},
            ],
            struts=[
                {
                    "FromWaler": "W1",
                    "ToWaler": "W2",
                    "Zoning": "Z1",
                    "material_spec": "H350",
                    **row,
                }
                for row in rows
            ],
            inventory=[{
                "ItemCode": "S-50",
                "Spec": "H350",
                "Usage": "支撐",
                "Length": 5000,
                "Qty": 8,
            }],
        )

    def test_builds_geometry_order_independent_of_rows_and_endpoints(self):
        rows = [
            {"StrutID": "S3", "StartX": 0, "StartY": 3000,
             "EndX": 10000, "EndY": 3000},
            {"StrutID": "S1", "StartX": 0, "StartY": 0,
             "EndX": 10000, "EndY": 0},
            {"StrutID": "S2", "StartX": 0, "StartY": 1500,
             "EndX": 10000, "EndY": 1500},
        ]
        reversed_rows = [
            {**row,
             "StartX": row["EndX"], "StartY": row["EndY"],
             "EndX": row["StartX"], "EndY": row["StartY"]}
            for row in reversed(rows)
        ]

        first = SupportInputBuilder().build_zone(self._geometry_model(rows), "Z1")
        second = SupportInputBuilder().build_zone(
            self._geometry_model(reversed_rows), "Z1"
        )

        def pair_set(result):
            return {
                frozenset((pair.first_unit_id, pair.second_unit_id))
                for pair in result.adjacency_contract.pairs
            }

        self.assertEqual(pair_set(first), pair_set(second))
        self.assertEqual(
            pair_set(first),
            {frozenset(("S1", "S2")), frozenset(("S2", "S3"))},
        )

    def test_shared_layout_collapses_before_ordering_and_keeps_both_configs(self):
        rows = [
            {"StrutID": "S3", "StartX": 0, "StartY": 3000,
             "EndX": 10000, "EndY": 3000},
            {"StrutID": "S2", "StartX": 0, "StartY": 1100,
             "EndX": 10000, "EndY": 1100, "SharedLayoutGroup": "G1"},
            {"StrutID": "S1", "StartX": 0, "StartY": 900,
             "EndX": 10000, "EndY": 900, "SharedLayoutGroup": "G1"},
        ]

        result = SupportInputBuilder().build_zone(self._geometry_model(rows), "Z1")

        self.assertEqual(len(result.units), 2)
        shared = next(unit for unit in result.units if unit.unit_id == "G1")
        self.assertEqual(shared.member_ids, ("S1", "S2"))
        self.assertEqual(
            tuple(config.support_id for config in shared.configs),
            ("S1", "S2"),
        )
        self.assertEqual(shared.representative_position, (5000.0, 1000.0))
        self.assertFalse(hasattr(shared, "representative_length"))

    def test_shared_lane_row_order_does_not_change_pair_set(self):
        rows = [
            {"StrutID": "S0", "StartX": 0, "StartY": 0,
             "EndX": 10000, "EndY": 0},
            {"StrutID": "S1", "StartX": 0, "StartY": 900,
             "EndX": 10000, "EndY": 900, "SharedLayoutGroup": "G1"},
            {"StrutID": "S2", "StartX": 0, "StartY": 1100,
             "EndX": 10000, "EndY": 1100, "SharedLayoutGroup": "G1"},
            {"StrutID": "S3", "StartX": 0, "StartY": 2500,
             "EndX": 10000, "EndY": 2500},
        ]
        first = SupportInputBuilder().build_zone(self._geometry_model(rows), "Z1")
        second_rows = [rows[3], rows[2], rows[0], rows[1]]
        second = SupportInputBuilder().build_zone(
            self._geometry_model(second_rows), "Z1"
        )

        first_pairs = tuple(
            (pair.first_unit_id, pair.second_unit_id)
            for pair in first.adjacency_contract.pairs
        )
        second_pairs = tuple(
            (pair.first_unit_id, pair.second_unit_id)
            for pair in second.adjacency_contract.pairs
        )
        self.assertEqual(first_pairs, second_pairs)
        self.assertEqual(first_pairs, (("S0", "G1"), ("G1", "S3")))

    def test_geometry_failures_are_structured_and_do_not_build_input(self):
        cases = (
            (
                ZONING_ZERO_LENGTH_AXIS,
                [
                    {"StrutID": "S1", "StartX": 0, "StartY": 0,
                     "EndX": 0, "EndY": 0},
                ],
            ),
            (
                ZONING_ANGLE_OUT_OF_TOLERANCE,
                [
                    {"StrutID": "S1", "StartX": 0, "StartY": 0,
                     "EndX": 10000, "EndY": 0},
                    {"StrutID": "S2", "StartX": 0, "StartY": 1000,
                     "EndX": 9900, "EndY": 2500},
                ],
            ),
            (
                ZONING_LENGTH_OUT_OF_TOLERANCE,
                [
                    {"StrutID": "S1", "StartX": 0, "StartY": 0,
                     "EndX": 10000, "EndY": 0},
                    {"StrutID": "S2", "StartX": 0, "StartY": 1000,
                     "EndX": 10006, "EndY": 1000},
                ],
            ),
            (
                ZONING_PROJECTION_TIE,
                [
                    {"StrutID": "S1", "StartX": 0, "StartY": 0,
                     "EndX": 10000, "EndY": 0},
                    {"StrutID": "S2", "StartX": 0, "StartY": 1,
                     "EndX": 10000, "EndY": 1},
                ],
            ),
        )

        for expected_code, rows in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(SolverInputBuildError) as caught:
                    SupportInputBuilder().build_zone(
                        self._geometry_model(rows), "Z1"
                    )
                self.assertIn(
                    expected_code,
                    {issue.code for issue in caught.exception.geometry_issues},
                )

    def test_confirmed_shared_group_outside_tolerance_is_rejected_for_solve(self):
        rows = [
            {"StrutID": "S1", "SharedLayoutGroup": "G1",
             "StartX": 0, "StartY": 0, "EndX": 10000, "EndY": 0},
            {"StrutID": "S2", "SharedLayoutGroup": "G1",
             "StartX": 0, "StartY": 1000, "EndX": 9900, "EndY": 2500},
        ]

        with self.assertRaises(SolverInputBuildError) as caught:
            SupportInputBuilder().build_zone(self._geometry_model(rows), "Z1")

        self.assertIn(
            ZONING_ANGLE_OUT_OF_TOLERANCE,
            {issue.code for issue in caught.exception.geometry_issues},
        )

class WalerInputBuilderTests(unittest.TestCase):
    def test_rc_waler_remains_in_formal_waler_build_output(self):
        model = ProjectDataModel(walers=[{
            "WalerID": "W-RC",
            "StartX": 0,
            "StartY": 0,
            "EndX": 6000,
            "EndY": 0,
            "material_spec": "RC",
        }])

        result = WalerInputBuilder().build_all(model)

        self.assertEqual(set(result), {"W-RC"})
        self.assertEqual(result["W-RC"].material_spec, "RC")
        self.assertEqual(result["W-RC"].start_point, (0, 0))
        self.assertEqual(result["W-RC"].end_point, (6000, 0))
        self.assertEqual(result["W-RC"].purchasable_lengths, ())

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
