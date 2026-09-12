import unittest
from collections import Counter

from bracing_optimizer.algorithms import support
from bracing_optimizer.application.project_results import (
    MaterialDetailBuildError,
    MaterialDetailRow,
    ProjectResultModel,
)


class ProjectResultModelTests(unittest.TestCase):
    def test_modified_waler_marker_survives_project_round_trip(self):
        source = {
            "type": "waler",
            "visible": True,
            "result": {
                "waler_id": "W1",
                "option_index": 2,
                "manual_modified": True,
                "selected_plan": {
                    "segments": [6000, 6000],
                    "legality": {"valid": True, "summary": "✅ 合法"},
                },
            },
        }

        payload = ProjectResultModel.serialize_result_item("W1-方案2", source)
        restored = ProjectResultModel.deserialize_result_item(payload)

        self.assertTrue(restored["result"]["manual_modified"])
        self.assertEqual(restored["result"]["selected_plan"]["segments"], [6000, 6000])

    @staticmethod
    def support_solution():
        plan = support.SupportPlan(
            support_id="S1",
            pieces=[("steel", 6000), ("jack", 600)],
            joints=[6000],
            gap=0,
            jack_center=6300,
            jack_region_id=2,
            score=10,
            valid=True,
            material_spec="H400",
        )
        return support.GlobalSolution(
            plans=[plan],
            total_score=10,
            valid=True,
            material_ratio_targets={"short": 0.2, "mid": 0.5, "long": 0.3},
        )

    def test_support_result_round_trip_preserves_runtime_model(self):
        solution = self.support_solution()
        solution.plans[0].shared_layout_group = "G1"
        source = {
            "type": "support",
            "visible": True,
            "support_visibility": {"S1": True},
            "result": solution,
        }

        payload = ProjectResultModel.serialize_result_item("Z1", source)
        restored = ProjectResultModel.deserialize_result_item(payload)

        self.assertIsInstance(restored["result"], support.GlobalSolution)
        self.assertEqual(restored["result"].plans[0].support_id, "S1")
        self.assertEqual(restored["result"].plans[0].material_spec, "H400")
        self.assertEqual(restored["result"].plans[0].shared_layout_group, "G1")
        self.assertEqual(restored["support_visibility"], {"S1": True})

    def test_material_usage_respects_result_and_support_visibility(self):
        solution = self.support_solution()
        hidden_plan = support.SupportPlan(
            support_id="S2",
            pieces=[("steel", 8000)],
            joints=[],
            gap=0,
            jack_center=0,
            jack_region_id=1,
            score=0,
            valid=True,
            material_spec="H400",
        )
        solution.plans.append(hidden_plan)
        model = ProjectResultModel(result_items={
            "Z1": {
                "type": "support",
                "visible": True,
                "support_visibility": {"S1": True, "S2": False},
                "result": solution,
            },
            "W1": {
                "type": "waler",
                "visible": True,
                "result": {
                    "material_spec": "H350",
                    "selected_plan": {
                        "assignments": [{"stock_length": 9000}],
                    },
                },
            },
        })

        self.assertEqual(
            model.collect_visible_material_usage(),
            Counter({
                ("支撐", "H400", 6000): 1,
                ("圍令", "H350", 9000): 1,
            }),
        )

    def test_material_details_list_each_visible_piece_and_its_owner(self):
        solution = self.support_solution()
        solution.plans.append(support.SupportPlan(
            support_id="S2",
            pieces=[("steel", 8000)],
            joints=[],
            gap=100,
            jack_center=0,
            jack_region_id=1,
            score=0,
            valid=True,
            material_spec="H400",
        ))
        model = ProjectResultModel(result_items={
            "W1-plan-1": {
                "type": "waler",
                "visible": True,
                "result": {
                    "waler_id": "W1",
                    "material_spec": "H350",
                    "selected_plan": {
                        "pieces": [("steel", 9000), ("shim", 50)],
                        "gap": 25,
                    },
                },
            },
            "Z1": {
                "type": "support",
                "visible": True,
                "support_visibility": {"S1": True, "S2": False},
                "result": solution,
            },
        })

        self.assertEqual(
            model.collect_visible_material_details(),
            [
                MaterialDetailRow(
                    result_id="W1-plan-1",
                    usage="圍令",
                    member_id="W1",
                    zoning="",
                    piece_index=1,
                    material_type="steel",
                    material_spec="H350",
                    length=9000,
                ),
                MaterialDetailRow(
                    result_id="W1-plan-1",
                    usage="圍令",
                    member_id="W1",
                    zoning="",
                    piece_index=2,
                    material_type="shim",
                    material_spec="",
                    length=50,
                ),
                MaterialDetailRow(
                    result_id="Z1",
                    usage="支撐",
                    member_id="S1",
                    zoning="Z1",
                    piece_index=1,
                    material_type="steel",
                    material_spec="H400",
                    length=6000,
                ),
                MaterialDetailRow(
                    result_id="Z1",
                    usage="支撐",
                    member_id="S1",
                    zoning="Z1",
                    piece_index=2,
                    material_type="jack",
                    material_spec="",
                    length=600,
                ),
            ],
        )
        self.assertEqual(
            model.collect_visible_material_usage(),
            Counter({
                ("圍令", "H350", 9000): 1,
                ("支撐", "H400", 6000): 1,
            }),
        )

    def test_material_details_support_legacy_waler_assignments(self):
        model = ProjectResultModel(result_items={
            "W1": {
                "type": "waler",
                "visible": True,
                "result": {
                    "waler_id": "W1",
                    "material_spec": "H350",
                    "selected_plan": {
                        "assignments": [{"stock_length": 9000}],
                        "tail_adjustment": 75,
                    },
                },
            },
        })

        details = model.collect_visible_material_details()

        self.assertEqual(
            [(row.material_type, row.length) for row in details],
            [("steel", 9000), ("shim", 75)],
        )

    def test_material_details_reject_invalid_piece_length(self):
        solution = self.support_solution()
        solution.plans[0].pieces = [("steel", 0)]
        model = ProjectResultModel(result_items={
            "Z1": {
                "type": "support",
                "visible": True,
                "result": solution,
            },
        })

        with self.assertRaisesRegex(MaterialDetailBuildError, "S1"):
            model.collect_visible_material_details()


if __name__ == "__main__":
    unittest.main()
