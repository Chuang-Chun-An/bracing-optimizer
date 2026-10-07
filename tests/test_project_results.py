import unittest
from collections import Counter

from bracing_optimizer.algorithms import support
from bracing_optimizer.algorithms.solver_search import SolverDiagnostics
from bracing_optimizer.application.project_results import (
    ExportLegality,
    MaterialDetailBuildError,
    MaterialDetailRow,
    ProjectResultModel,
)


class ProjectResultModelTests(unittest.TestCase):
    def test_solver_diagnostic_view_normalizes_algorithm_result(self):
        diagnostics = SolverDiagnostics(
            solver_type="support",
            legal_solution_found=True,
            search_was_escalated=True,
            result_is_stable=True,
            affected_component_ids=["S1"],
            component_candidate_counts={"S1": 3},
        )

        view = ProjectResultModel.solver_diagnostic_view(
            diagnostics.to_dict()
        )

        self.assertTrue(view.legal_solution_found)
        self.assertTrue(view.search_was_escalated)
        self.assertTrue(view.result_is_stable)
        self.assertEqual(view.affected_component_ids, ("S1",))
        self.assertEqual(view.component_candidate_counts, {"S1": 3})

    def test_solver_diagnostic_view_supports_legacy_missing_data(self):
        self.assertIsNone(ProjectResultModel.solver_diagnostic_view(None))

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

    def test_legacy_waler_tail_adjustment_loads_without_migration(self):
        source = {
            "type": "waler",
            "visible": True,
            "result": {
                "waler_id": "W1",
                "selected_plan": {
                    "segments": [6000, 6000],
                    "tail_adjustment": 75,
                    "pieces": [
                        ("steel", 6000),
                        ("steel", 6000),
                        ("shim", 75),
                    ],
                },
            },
        }

        payload = ProjectResultModel.serialize_result_item("W1-legacy", source)
        restored = ProjectResultModel.deserialize_result_item(payload)

        selected_plan = restored["result"]["selected_plan"]
        self.assertEqual(selected_plan["tail_adjustment"], 75)
        self.assertEqual(selected_plan["pieces"][-1], ("shim", 75))

    def test_canonical_waler_tail_survives_project_round_trip(self):
        source = {
            "type": "waler",
            "visible": True,
            "result": {
                "waler_id": "W1",
                "material_spec": "H400",
                "required_length": 16450,
                "selected_plan": {
                    "segments": [8000, 8000],
                    "steel_length": 16000,
                    "tail_adjustment": 300,
                    "gap": 150,
                    "pieces": [
                        ("steel", 8000),
                        ("steel", 8000),
                        ("shim", 300),
                    ],
                    "valid": True,
                    "legality": {"valid": True},
                },
            },
        }

        payload = ProjectResultModel.serialize_result_item("W1-plan", source)
        restored = ProjectResultModel.deserialize_result_item(payload)
        plan = restored["result"]["selected_plan"]

        self.assertEqual(plan["tail_adjustment"], 300)
        self.assertEqual(plan["gap"], 150)
        self.assertEqual(
            plan["pieces"],
            [("steel", 8000), ("steel", 8000), ("shim", 300)],
        )

    def test_canonical_adjustment_is_a_detail_but_not_steel_usage(self):
        model = ProjectResultModel(result_items={
            "W1-plan": {
                "type": "waler",
                "visible": True,
                "result": {
                    "waler_id": "W1",
                    "material_spec": "H400",
                    "selected_plan": {
                        "pieces": [
                            ("steel", 8000),
                            ("steel", 8000),
                            ("shim", 300),
                        ],
                        "gap": 150,
                        "valid": True,
                        "legality": {"valid": True},
                    },
                },
            },
        })

        details = model.collect_visible_material_details()

        self.assertEqual(
            [(row.material_type, row.length) for row in details],
            [("steel", 8000), ("steel", 8000), ("shim", 300)],
        )
        self.assertEqual(
            model.collect_visible_material_usage(),
            Counter({("圍令", "H400", 8000): 2}),
        )

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
        solution.search_diagnostics = SolverDiagnostics(
            solver_type="support",
            legal_solution_found=True,
            adjacency_units=[{
                "unit_id": "G1",
                "member_ids": ["S1"],
            }],
            adjacency_pairs=[],
            phase2_executed=True,
        ).to_dict()
        solution._adjacency_units = [object()]
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
        self.assertTrue(restored["result"].search_diagnostics["phase2_executed"])
        self.assertEqual(
            restored["result"].search_diagnostics["adjacency_units"][0]["unit_id"],
            "G1",
        )
        self.assertFalse(hasattr(restored["result"], "_adjacency_units"))
        self.assertNotIn("representative_position", str(payload))
        self.assertNotIn("canonical_direction", str(payload))

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

    def test_export_legality_normalizes_support_missing_valid_and_reason_conflict(self):
        solution = self.support_solution()
        missing_valid = solution.plans[0]
        del missing_valid.valid
        missing_valid.reason = ""
        solution.plans.append(support.SupportPlan(
            support_id="S2",
            pieces=[("steel", 8000)],
            joints=[],
            gap=0,
            jack_center=0,
            jack_region_id=1,
            score=0,
            valid=True,
            reason="接頭落入禁止區",
            material_spec="H400",
        ))
        model = ProjectResultModel(result_items={
            "Z1": {
                "type": "support",
                "visible": True,
                "result": solution,
            },
        })

        self.assertEqual(
            model.collect_visible_export_legality(),
            (
                ExportLegality(
                    "Z1",
                    "support",
                    "S1",
                    False,
                    ("未提供不合法原因",),
                ),
                ExportLegality(
                    "Z1",
                    "support",
                    "S2",
                    False,
                    ("接頭落入禁止區",),
                ),
            ),
        )

    def test_export_legality_uses_waler_legality_valid_before_plan_valid(self):
        model = ProjectResultModel(result_items={
            "W2-方案1": {
                "type": "waler",
                "visible": True,
                "result": {
                    "waler_id": "W2",
                    "selected_plan": {
                        "valid": False,
                        "legality": {
                            "valid": True,
                            "violations": ["不應輸出的舊問題"],
                        },
                    },
                },
            },
            "W1-方案1": {
                "type": "waler",
                "visible": True,
                "result": {
                    "waler_id": "W1",
                    "selected_plan": {
                        "valid": True,
                        "errors": ["fallback 不得蓋過 legality"],
                        "legality": {
                            "valid": False,
                            "violations": [
                                "鋼材總長不足",
                                "鋼材總長不足",
                                " ",
                                "接頭落入禁止區",
                            ],
                        },
                    },
                },
            },
        })

        self.assertEqual(
            model.collect_visible_export_legality(),
            (
                ExportLegality(
                    "W1-方案1",
                    "waler",
                    "W1",
                    False,
                    ("鋼材總長不足", "接頭落入禁止區"),
                ),
                ExportLegality("W2-方案1", "waler", "W2", True, ()),
            ),
        )

    def test_export_legality_defaults_waler_without_valid_or_reasons_to_invalid(self):
        model = ProjectResultModel(result_items={
            "W1-方案1": {
                "type": "waler",
                "visible": True,
                "result": {
                    "waler_id": "W1",
                    "selected_plan": {},
                },
            },
        })

        self.assertEqual(
            model.collect_visible_export_legality(),
            (
                ExportLegality(
                    "W1-方案1",
                    "waler",
                    "W1",
                    False,
                    ("未提供不合法原因",),
                ),
            ),
        )

    def test_export_legality_does_not_change_material_scope(self):
        solution = self.support_solution()
        solution.plans[0].valid = False
        solution.plans[0].reason = "待修正"
        model = ProjectResultModel(result_items={
            "Z1": {
                "type": "support",
                "visible": True,
                "result": solution,
            },
            "W1-方案1": {
                "type": "waler",
                "visible": True,
                "result": {
                    "waler_id": "W1",
                    "material_spec": "H350",
                    "selected_plan": {
                        "segments": [9000],
                        "legality": {"valid": False, "violations": []},
                    },
                },
            },
        })

        before_details = model.collect_visible_material_details()
        before_usage = model.collect_visible_material_usage()

        projection = model.collect_visible_export_legality()

        self.assertTrue(all(not row.valid for row in projection))
        self.assertEqual(model.collect_visible_material_details(), before_details)
        self.assertEqual(model.collect_visible_material_usage(), before_usage)

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
                    valid=False,
                    reasons=("未提供不合法原因",),
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
                    valid=False,
                    reasons=("未提供不合法原因",),
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
