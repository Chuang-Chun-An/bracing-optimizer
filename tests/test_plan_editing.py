import unittest
from unittest.mock import patch

from bracing_optimizer.algorithms import support, wales
from bracing_optimizer.application.plan_editing import (
    SupportPlanEditing,
    WalerPlanEditing,
)
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.solver_input_builder import (
    SolverInputBuildError,
    SupportInputBuilder,
)


class PlanEditingTests(unittest.TestCase):
    class StaticSupportBuilder:
        def __init__(self, configs):
            self.configs = {
                config.support_id: config
                for config in configs
            }

        def build_one(self, _project_data, support_id):
            return self.configs.get(str(support_id))

    @staticmethod
    def project_data():
        return ProjectDataModel(
            walers=[{
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 12000,
                "EndY": 0,
            }],
            inventory=[{
                "ItemCode": "W-6000",
                "Spec": "H400",
                "Usage": "圍令",
                "Length": 6000,
                "Qty": 2,
            }],
        )

    def test_waler_editing_recalculates_and_validates_without_ui(self):
        result_context = {
            "material_spec": "H400",
            "required_length": 12000,
        }

        plan = WalerPlanEditing(self.project_data()).recalculate(
            {},
            [6000, 6000],
            waler_id="W1",
            result_context=result_context,
        )

        self.assertEqual(plan["joints"], [6000])
        self.assertEqual(plan["steel_length"], 12000)
        self.assertTrue(plan["valid"])
        self.assertTrue(plan["legality"]["valid"])
        self.assertNotIn("custom", plan)

    def test_waler_recalculation_clears_legacy_tail_adjustment_and_shim(self):
        legacy_plan = {
            "segments": [6000, 6000],
            "tail_adjustment": 75,
            "pieces": [
                ("steel", 6000),
                ("steel", 6000),
                ("shim", 75),
            ],
        }

        recalculated = WalerPlanEditing(self.project_data()).recalculate(
            legacy_plan,
            [6000, 6000],
            waler_id="W1",
            result_context={
                "material_spec": "H400",
                "required_length": 12000,
            },
        )

        self.assertEqual(recalculated["tail_adjustment"], 0)
        self.assertEqual(recalculated["gap"], 0)
        self.assertNotIn(
            "shim",
            [piece_type for piece_type, _length in recalculated["pieces"]],
        )

    def test_waler_manual_recalculation_does_not_run_ga_repair(self):
        with patch.object(
            wales,
            "repair_individual",
            side_effect=AssertionError("manual plan entered GA repair"),
        ) as repair:
            recalculated = WalerPlanEditing(self.project_data()).recalculate(
                {},
                [6000],
                waler_id="W1",
                result_context={
                    "material_spec": "H400",
                    "required_length": 12000,
                },
            )

        repair.assert_not_called()
        self.assertEqual(recalculated["segments"], [6000])
        self.assertFalse(recalculated["valid"])

    def test_waler_editing_rechecks_length_after_a_segment_is_deleted(self):
        result_context = {
            "material_spec": "H400",
            "required_length": 12000,
        }

        plan = WalerPlanEditing(self.project_data()).recalculate(
            {},
            [6000],
            waler_id="W1",
            result_context=result_context,
        )

        self.assertFalse(plan["valid"])
        self.assertFalse(plan["legality"]["valid"])
        self.assertIn("鋼材總長不足", plan["legality"]["violations"])

    def test_waler_editing_handles_deleting_the_last_segment(self):
        plan = WalerPlanEditing(self.project_data()).recalculate(
            {},
            [],
            waler_id="W1",
            result_context={
                "material_spec": "H400",
                "required_length": 12000,
            },
        )

        self.assertEqual(plan["segments"], [])
        self.assertFalse(plan["valid"])

    def test_waler_editing_characterizes_legal_payload_exactly(self):
        plan = WalerPlanEditing(self.project_data()).recalculate(
            {},
            [6000, 6000],
            waler_id="W1",
            result_context={
                "material_spec": "H400",
                "required_length": 12000,
            },
        )

        self.assertEqual(
            list(plan),
            [
                "joints",
                "segments",
                "assignments",
                "total_waste",
                "buy_count",
                "distinct_groups",
                "length_variation",
                "under_4000_segment_count",
                "segment_counts",
                "segment_ratios",
                "ratio_targets",
                "ratio_penalty",
                "joint_count",
                "score",
                "valid",
                "errors",
                "required_length",
                "steel_length",
                "tail_adjustment",
                "gap",
                "pieces",
                "legality",
            ],
        )
        self.assertEqual(plan["score"], 106000.0)
        self.assertEqual(plan["errors"], [])
        self.assertEqual(
            plan["legality"],
            {
                "valid": True,
                "summary": "✅ 合法",
                "violations": [],
                "details": [
                    "✅ 合法",
                    "需求長度：12000 mm",
                    "標準鋼材總長：12000 mm",
                    "現場處理餘量：0 mm",
                    "✅ 所有接頭均符合規範",
                ],
                "warnings": [],
                "required_length": 12000,
                "current_length": 12000,
                "tail_adjustment": 0,
                "gap": 0,
            },
        )

    def test_waler_editing_characterizes_invalid_joint_payload_exactly(self):
        plan = WalerPlanEditing(self.project_data()).recalculate(
            {},
            [6000, 6000],
            waler_id="W1",
            result_context={
                "material_spec": "H400",
                "required_length": 12000,
                "forbidden_points": [6200],
                "joint_clearance": 300,
            },
        )

        self.assertIsNone(plan["assignments"])
        self.assertIsNone(plan["total_waste"])
        self.assertIsNone(plan["buy_count"])
        self.assertIsNone(plan["distinct_groups"])
        self.assertIsNone(plan["length_variation"])
        self.assertIsNone(plan["under_4000_segment_count"])
        self.assertIsNone(plan["segment_counts"])
        self.assertIsNone(plan["segment_ratios"])
        self.assertIsNone(plan["ratio_penalty"])
        self.assertIsNone(plan["score"])
        self.assertEqual(plan["errors"], [])
        self.assertEqual(plan["legality"]["summary"], "❌ 接頭落入禁止區")
        self.assertEqual(
            plan["legality"]["details"],
            [
                "❌ 接頭落入禁止區",
                "接頭位置：6000 mm",
                "禁止區：5900 ~ 6500 mm",
            ],
        )
        self.assertEqual(plan["legality"]["warnings"], [])

    def test_waler_issue_codes_are_not_persisted(self):
        plan = WalerPlanEditing(self.project_data()).recalculate(
            {},
            [6000, 6000],
            waler_id="W1",
            result_context={
                "material_spec": "H400",
                "required_length": 12000,
                "forbidden_points": [6200],
                "joint_clearance": 300,
            },
        )
        payload = ProjectResultModel.serialize_result_item(
            "W1-invalid",
            {
                "type": "waler",
                "visible": True,
                "result": {
                    "waler_id": "W1",
                    "selected_plan": plan,
                },
            },
        )

        persisted_text = repr(payload)
        for issue_code in (
            wales.ISSUE_STEEL_TOTAL_SHORT,
            wales.ISSUE_STEEL_TOTAL_LONG,
            wales.ISSUE_JOINT_CLEARANCE,
            wales.ISSUE_SEGMENT_BELOW_MINIMUM,
            wales.ISSUE_SEGMENT_ABOVE_MAXIMUM,
            wales.ISSUE_SEGMENT_NOT_PURCHASABLE,
            wales.ISSUE_ALLOCATION_UNAVAILABLE,
        ):
            self.assertNotIn(issue_code, persisted_text)

    def test_waler_editing_characterizes_non_purchasable_payload_exactly(self):
        plan = WalerPlanEditing(self.project_data()).recalculate(
            {},
            [5000, 7000],
            waler_id="W1",
            result_context={
                "material_spec": "H400",
                "required_length": 12000,
            },
        )

        self.assertIsNone(plan["assignments"])
        self.assertIsNone(plan["total_waste"])
        self.assertIsNone(plan["buy_count"])
        self.assertIsNone(plan["distinct_groups"])
        self.assertIsNone(plan["length_variation"])
        self.assertIsNone(plan["ratio_penalty"])
        self.assertIsNone(plan["score"])
        self.assertEqual(
            plan["errors"],
            ["部分料長不在庫存可購買長度內，材料配置未完成。"],
        )
        self.assertEqual(plan["legality"]["summary"], "❌ 共 2 項違規")
        self.assertEqual(
            plan["legality"]["details"],
            [
                "❌ 共 2 項違規",
                "- 無此料長",
                "- 無此料長",
                "❌ 無此料長",
                "段次：1",
                "料長：5000 mm",
                "❌ 無此料長",
                "段次：2",
                "料長：7000 mm",
            ],
        )
        self.assertEqual(plan["legality"]["warnings"], [])

    def test_support_editing_recalculates_global_solution(self):
        plan = support.SupportPlan(
            support_id="S1",
            pieces=[("steel", 6000)],
            joints=[],
            gap=0,
            jack_center=3000,
            jack_region_id=1,
            score=10,
            valid=True,
        )
        solution = support.GlobalSolution(
            plans=[plan],
            total_score=0,
            valid=False,
        )

        group_penalty, reasons = SupportPlanEditing.recalculate_global_solution(
            solution
        )

        self.assertTrue(solution.valid)
        self.assertEqual(reasons, [])
        self.assertEqual(
            group_penalty,
            solution.jack_region_penalty + solution.material_ratio_penalty,
        )

    @staticmethod
    def support_config(support_id="S1", shared_layout_group=""):
        return support.SupportConfig(
            support_id=support_id,
            total_length=11600,
            pile_centers=[],
            waler_centers=[],
            target_jack_region=1,
            material_spec="H400",
            steel_lengths=[5000, 6000],
            shared_layout_group=shared_layout_group,
        )

    @staticmethod
    def support_plan(config, pieces=None):
        return support.evaluate_single_support(
            config,
            pieces or [("steel", 6000), ("jack", 600), ("steel", 5000)],
        )

    def support_editing(self, *configs):
        return SupportPlanEditing(
            project_data=object(),
            support_input_builder=self.StaticSupportBuilder(configs),
        )

    def test_support_edit_options_come_from_application_service(self):
        config = self.support_config()

        options = SupportPlanEditing.edit_options(config)

        self.assertEqual(options.piece_types, ("steel", "shim", "jack"))
        self.assertEqual(options.steel_lengths, (5000, 6000))
        self.assertEqual(options.shim_lengths, tuple(support.SHIM_LENGTHS))
        self.assertEqual(options.jack_length, support.JACK_LENGTH)
        self.assertEqual(options.default_steel_length, 5000)
        self.assertEqual(options.default_shim_length, 150)

    def test_support_editing_same_normalized_layout_is_no_op(self):
        config = self.support_config()
        original_plan = self.support_plan(config)
        solution = support.make_global_solution([original_plan])
        editing = self.support_editing(config)

        with (
            patch(
                "bracing_optimizer.application.plan_editing.copy.deepcopy"
            ) as deepcopy,
            patch.object(support, "evaluate_single_support") as evaluate,
            patch.object(
                editing,
                "recalculate_global_solution",
            ) as recalculate,
        ):
            result = editing.stage_edit(
                solution,
                "S1",
                [(" STEEL ", 6000.0), ("JACK", 600), ("steel", 5000)],
            )

        self.assertFalse(result.changed)
        self.assertIs(result.solution, solution)
        self.assertIs(result.plan, original_plan)
        self.assertEqual(result.updated_support_ids, ())
        deepcopy.assert_not_called()
        evaluate.assert_not_called()
        recalculate.assert_not_called()

    def test_support_editing_same_shared_layout_is_no_op(self):
        first_config = self.support_config("S1", "G1")
        second_config = self.support_config("S2", "G1")
        first_plan = self.support_plan(first_config)
        second_plan = self.support_plan(second_config)
        solution = support.make_global_solution([first_plan, second_plan])
        editing = self.support_editing(first_config)

        result = editing.stage_edit(solution, "S1", list(first_plan.pieces))

        self.assertFalse(result.changed)
        self.assertIs(result.solution, solution)
        self.assertIs(result.plan, first_plan)
        self.assertEqual(result.updated_support_ids, ())

    def test_support_editing_shared_member_difference_is_a_change(self):
        first_config = self.support_config("S1", "G1")
        second_config = self.support_config("S2", "G1")
        requested_pieces = [
            ("steel", 6000),
            ("jack", 600),
            ("steel", 5000),
        ]
        different_pieces = [
            ("steel", 5000),
            ("jack", 600),
            ("steel", 6000),
        ]
        solution = support.make_global_solution([
            self.support_plan(first_config, requested_pieces),
            self.support_plan(second_config, different_pieces),
        ])
        editing = self.support_editing(first_config, second_config)

        result = editing.stage_edit(solution, "S1", requested_pieces)

        self.assertTrue(result.changed)
        self.assertEqual(result.updated_support_ids, ("S1", "S2"))
        self.assertEqual(
            [plan.pieces for plan in result.solution.plans],
            [requested_pieces, requested_pieces],
        )

    def test_support_editing_stages_single_plan_without_mutating_source(self):
        config = self.support_config()
        original_plan = self.support_plan(config)
        solution = support.make_global_solution([original_plan])
        editing = self.support_editing(config)
        new_pieces = [("steel", 5000), ("jack", 600), ("steel", 6000)]

        result = editing.stage_edit(solution, "S1", new_pieces)

        self.assertTrue(result.changed)
        self.assertIsNot(result.solution, solution)
        self.assertEqual(solution.plans[0].pieces, original_plan.pieces)
        self.assertEqual(result.plan.pieces, new_pieces)
        self.assertEqual(result.updated_support_ids, ("S1",))
        self.assertTrue(result.validation.valid)
        self.assertEqual(len(result.solution.plans), 1)

    def test_support_editing_applies_invalid_engineering_layout_for_review(self):
        config = self.support_config()
        solution = support.make_global_solution([self.support_plan(config)])
        editing = self.support_editing(config)

        result = editing.stage_edit(
            solution,
            "S1",
            [("steel", 6000), ("steel", 5000)],
        )

        self.assertTrue(result.changed)
        self.assertFalse(result.validation.valid)
        self.assertEqual(result.validation.issue_code, "invalid_jack_count")
        self.assertEqual(
            result.plan.pieces,
            [("steel", 6000), ("steel", 5000)],
        )
        self.assertFalse(result.plan.valid)
        self.assertEqual(
            solution.plans[0].pieces,
            [("steel", 6000), ("jack", 600), ("steel", 5000)],
        )

    def test_support_editing_saves_multiple_shims_with_count_only_reason(self):
        config = self.support_config()
        original_plan = self.support_plan(config)
        solution = support.make_global_solution([original_plan])
        editing = self.support_editing(config)
        pieces = [
            ("shim", 100),
            ("steel", 5000),
            ("jack", 600),
            ("steel", 5000),
            ("shim", 100),
        ]

        result = editing.stage_edit(solution, "S1", pieces)

        self.assertTrue(result.changed)
        self.assertFalse(result.validation.valid)
        self.assertEqual(result.validation.issue_code, "invalid_shim_count")
        self.assertEqual(result.plan.reason, "非零 Shim 數量超過 1")
        self.assertFalse(result.plan.valid)
        self.assertEqual(result.plan.pieces, pieces)
        self.assertIs(solution.plans[0], original_plan)

    def test_support_editing_saves_forbidden_joint_as_invalid(self):
        config = self.support_config()
        original_plan = self.support_plan(config)
        solution = support.make_global_solution([original_plan])
        editing = self.support_editing(config)
        pieces = [("jack", 600), ("steel", 5000), ("steel", 6000)]

        result = editing.stage_edit(solution, "S1", pieces)

        self.assertTrue(result.changed)
        self.assertFalse(result.plan.valid)
        self.assertIn("接頭落入禁止區", result.plan.reason)
        self.assertEqual(result.plan.pieces, pieces)
        self.assertIs(solution.plans[0], original_plan)

    def test_support_editing_uses_solver_shim_placement_for_missing_type(self):
        config = self.support_config()
        config.from_waler_type = ""
        original_plan = self.support_plan(config)
        solution = support.make_global_solution([original_plan])
        editing = self.support_editing(config)
        pieces = [
            ("shim", 100),
            ("steel", 5000),
            ("jack", 600),
            ("steel", 5000),
        ]

        result = editing.stage_edit(solution, "S1", pieces)

        self.assertEqual(
            result.validation.issue_code,
            "invalid_shim_placement",
        )
        self.assertIn("Shim 位置", result.validation.message)
        self.assertTrue(result.plan.reason.startswith("Shim 位置"))
        self.assertFalse(result.plan.valid)

    def test_support_editing_rejects_nonpositive_pieces_transactionally(self):
        config = self.support_config()
        original_plan = self.support_plan(config)
        solution = support.make_global_solution([original_plan])
        editing = self.support_editing(config)

        for length in (0, -100):
            with self.subTest(length=length):
                with self.assertRaisesRegex(ValueError, "類型或長度格式錯誤"):
                    editing.stage_edit(
                        solution,
                        "S1",
                        [("shim", length), ("jack", 600), ("steel", 5000)],
                    )
                self.assertIs(solution.plans[0], original_plan)

    def test_forbidden_zone_diagnostic_uses_typed_piece_boundary(self):
        config = support.SupportConfig(
            support_id="S1",
            total_length=7180,
            pile_centers=[],
            waler_centers=[],
            from_waler_type="RC",
            to_waler_type="Steel",
            steel_lengths=[5000],
        )
        plan = support.evaluate_single_support(
            config,
            [("shim", 100), ("jack", 2000), ("steel", 5000)],
        )

        hit = SupportPlanEditing.find_forbidden_zone_hit(plan, config)

        self.assertEqual(hit, (100, 0, support.MIN_END_CLEAR, "left_end"))

    def test_loaded_legacy_result_is_revalidated_only_after_changed_edit(self):
        config = self.support_config()
        legacy_pieces = [
            ("shim", 100),
            ("steel", 5000),
            ("jack", 600),
            ("steel", 5000),
            ("shim", 100),
        ]
        legacy_plan = support.SupportPlan(
            support_id="S1",
            pieces=legacy_pieces,
            joints=[100, 5100, 5700, 10700],
            gap=800,
            jack_center=5400,
            jack_region_id=1,
            score=4800.0,
            valid=True,
            reason="",
        )
        serialized = ProjectResultModel.serialize_result_item(
            "Z1",
            {
                "type": "support",
                "visible": True,
                "result": support.GlobalSolution(
                    plans=[legacy_plan],
                    total_score=4800.0,
                    valid=True,
                ),
            },
        )

        loaded_item = ProjectResultModel.deserialize_result_item(serialized)
        loaded_plan = loaded_item["result"].plans[0]

        self.assertTrue(loaded_plan.valid)
        self.assertEqual(loaded_plan.reason, "")
        editing = self.support_editing(config)
        recalculated = editing.stage_edit(
            loaded_item["result"],
            "S1",
            [
                ("shim", 100),
                ("steel", 5000),
                ("jack", 600),
                ("shim", 100),
                ("steel", 5000),
            ],
        )
        self.assertTrue(recalculated.changed)
        self.assertFalse(recalculated.plan.valid)
        self.assertEqual(recalculated.plan.reason, "非零 Shim 數量超過 1")

    def test_support_editing_recalculates_every_shared_layout_member(self):
        first_config = self.support_config("S1", "G1")
        second_config = self.support_config("S2", "G1")
        solution = support.make_global_solution([
            self.support_plan(first_config),
            self.support_plan(second_config),
        ])
        editing = self.support_editing(first_config, second_config)
        new_pieces = [("steel", 5000), ("jack", 600), ("steel", 6000)]

        result = editing.stage_edit(solution, "S1", new_pieces)

        self.assertTrue(result.changed)
        self.assertEqual(result.updated_support_ids, ("S1", "S2"))
        self.assertEqual(
            [plan.pieces for plan in result.solution.plans],
            [new_pieces, new_pieces],
        )
        self.assertEqual(
            [plan.support_id for plan in result.solution.plans],
            ["S1", "S2"],
        )
        self.assertEqual(solution.plans[0].pieces, self.support_plan(first_config).pieces)

    def test_support_editing_detects_each_supported_layout_change(self):
        config = self.support_config()
        original_plan = self.support_plan(config)
        solution = support.make_global_solution([original_plan])
        editing = self.support_editing(config)
        cases = {
            "add": [
                ("steel", 6000),
                ("shim", 150),
                ("jack", 600),
                ("steel", 5000),
            ],
            "delete": [("jack", 600), ("steel", 5000)],
            "move": [
                ("steel", 6000),
                ("steel", 5000),
                ("jack", 600),
            ],
            "type": [
                ("shim", 100),
                ("jack", 600),
                ("steel", 5000),
            ],
            "length": [
                ("steel", 5000),
                ("jack", 600),
                ("steel", 5000),
            ],
        }

        for operation, pieces in cases.items():
            with self.subTest(operation=operation):
                result = editing.stage_edit(solution, "S1", pieces)

                self.assertTrue(result.changed)
                self.assertIsNot(result.solution, solution)
                self.assertEqual(result.plan.pieces, pieces)

    def test_support_editing_revert_compares_with_latest_committed_solution(self):
        config = self.support_config()
        original_pieces = [
            ("steel", 6000),
            ("jack", 600),
            ("steel", 5000),
        ]
        changed_pieces = [
            ("steel", 5000),
            ("jack", 600),
            ("steel", 6000),
        ]
        solution = support.make_global_solution([
            self.support_plan(config, original_pieces)
        ])
        editing = self.support_editing(config)

        first_edit = editing.stage_edit(solution, "S1", changed_pieces)
        reverted = editing.stage_edit(
            first_edit.solution,
            "S1",
            original_pieces,
        )
        repeated = editing.stage_edit(
            reverted.solution,
            "S1",
            original_pieces,
        )

        self.assertTrue(first_edit.changed)
        self.assertTrue(reverted.changed)
        self.assertEqual(reverted.plan.pieces, original_pieces)
        self.assertFalse(repeated.changed)
        self.assertIs(repeated.solution, reverted.solution)

    def test_support_editing_rejects_unnormalizable_input_transactionally(self):
        config = self.support_config()
        original_plan = self.support_plan(config)
        solution = support.make_global_solution([original_plan])
        editing = self.support_editing(config)

        with self.assertRaisesRegex(ValueError, "類型或長度格式錯誤"):
            editing.stage_edit(
                solution,
                "S1",
                [("steel", "not-a-number"), ("jack", 600)],
            )

        self.assertIs(solution.plans[0], original_plan)
        self.assertEqual(
            solution.plans[0].pieces,
            [("steel", 6000), ("jack", 600), ("steel", 5000)],
        )

    def test_support_editing_missing_shared_member_config_is_transactional(self):
        first_config = self.support_config("S1", "G1")
        second_config = self.support_config("S2", "G1")
        solution = support.make_global_solution([
            self.support_plan(first_config),
            self.support_plan(second_config),
        ])
        editing = self.support_editing(first_config)
        before = [list(plan.pieces) for plan in solution.plans]

        with self.assertRaisesRegex(ValueError, "S2"):
            editing.stage_edit(
                solution,
                "S1",
                [("steel", 5000), ("jack", 600), ("steel", 6000)],
            )

        self.assertEqual([plan.pieces for plan in solution.plans], before)

    def test_support_analysis_exposes_rules_without_ui_recalculation(self):
        config = self.support_config()
        plan = self.support_plan(config)
        solution = support.make_global_solution([plan])

        analysis = SupportPlanEditing.analyze_plan(plan, [], solution)
        global_analysis = SupportPlanEditing.global_analysis(solution)

        self.assertEqual(
            analysis.short_steel_threshold,
            support.SUPPORT_SHORT_STEEL_THRESHOLD,
        )
        self.assertEqual(analysis.target_gap, support.TARGET_GAP)
        self.assertEqual(
            analysis.minimum_jack_distance,
            support.MIN_JACK_DISTANCE_BETWEEN_SUPPORTS,
        )
        self.assertEqual(
            global_analysis.minimum_jack_distance,
            support.MIN_JACK_DISTANCE_BETWEEN_SUPPORTS,
        )

    @staticmethod
    def geometry_project(rows):
        return ProjectDataModel(
            walers=[
                {"WalerID": "W1", "material_spec": "H400"},
                {"WalerID": "W2", "material_spec": "H400"},
            ],
            struts=[
                {
                    "FromWaler": "W1",
                    "ToWaler": "W2",
                    "Zoning": "Z1",
                    "material_spec": "H400",
                    "TargetJackRegion": 3,
                    **row,
                }
                for row in rows
            ],
            inventory=[
                {"ItemCode": "S-50", "Spec": "H400", "Usage": "支撐",
                 "Length": 5000, "Qty": 10},
                {"ItemCode": "S-60", "Spec": "H400", "Usage": "支撐",
                 "Length": 6000, "Qty": 10},
            ],
        )

    @staticmethod
    def manual_plan(support_id, pieces, *, group=""):
        config = support.SupportConfig(
            support_id=support_id,
            total_length=sum(length for _kind, length in pieces),
            pile_centers=[],
            waler_centers=[],
            target_jack_region=3,
            material_spec="H400",
            steel_lengths=[5000, 6000],
            shared_layout_group=group,
        )
        return support.evaluate_single_support(config, pieces)

    def test_manual_recalculation_uses_geometry_contract_and_neighbors(self):
        rows = [
            {"StrutID": "S3", "StartX": 0, "StartY": 3000,
             "EndX": 16600, "EndY": 3000},
            {"StrutID": "S1", "StartX": 0, "StartY": 0,
             "EndX": 16600, "EndY": 0},
            {"StrutID": "S2", "StartX": 0, "StartY": 1500,
             "EndX": 16600, "EndY": 1500},
        ]
        project = self.geometry_project(rows)
        pieces_by_id = {
            "S1": [("steel", 5000), ("jack", 600),
                   ("steel", 5000), ("steel", 6000)],
            "S2": [("steel", 5000), ("steel", 5000),
                   ("jack", 600), ("steel", 6000)],
            "S3": [("steel", 6000), ("jack", 600),
                   ("steel", 5000), ("steel", 5000)],
        }
        source_pieces = dict(pieces_by_id)
        source_pieces["S1"] = [
            ("steel", 5000),
            ("steel", 5000),
            ("jack", 600),
            ("steel", 6000),
        ]
        solution = support.make_global_solution([
            self.manual_plan(row["StrutID"], source_pieces[row["StrutID"]])
            for row in rows
        ])
        editing = SupportPlanEditing(project, SupportInputBuilder())

        result = editing.stage_edit(solution, "S1", pieces_by_id["S1"])

        self.assertTrue(result.changed)
        self.assertEqual(
            [unit.unit_id for unit in result.solution._adjacency_units],
            ["S1", "S2", "S3"],
        )
        self.assertEqual(
            [item["support_id"] for item in result.neighbor_checks],
            ["S2"],
        )
        self.assertEqual(result.solution.min_jack_distance, 4000)
        self.assertTrue(result.solution.valid)

    def test_shared_lane_neighbors_are_only_external_units(self):
        rows = [
            {"StrutID": "A", "StartX": 0, "StartY": 0,
             "EndX": 11600, "EndY": 0},
            {"StrutID": "G-A", "SharedLayoutGroup": "G1",
             "StartX": 0, "StartY": 900, "EndX": 11600, "EndY": 900},
            {"StrutID": "G-B", "SharedLayoutGroup": "G1",
             "StartX": 0, "StartY": 1100, "EndX": 11600, "EndY": 1100},
            {"StrutID": "B", "StartX": 0, "StartY": 2200,
             "EndX": 11600, "EndY": 2200},
        ]
        project = self.geometry_project(rows)
        shared_pieces = [("steel", 5000), ("jack", 600), ("steel", 6000)]
        plans = [
            self.manual_plan("A", [("jack", 600), ("steel", 5000), ("steel", 6000)]),
            self.manual_plan("G-A", shared_pieces, group="G1"),
            self.manual_plan(
                "G-B",
                [("steel", 6000), ("jack", 600), ("steel", 5000)],
                group="G1",
            ),
            self.manual_plan("B", [("steel", 6000), ("jack", 600), ("steel", 5000)]),
        ]
        solution = support.make_global_solution(plans)
        editing = SupportPlanEditing(project, SupportInputBuilder())

        result = editing.stage_edit(solution, "G-A", shared_pieces)

        self.assertTrue(result.changed)
        self.assertEqual(
            {item["support_id"] for item in result.neighbor_checks},
            {"A", "B"},
        )
        self.assertFalse(any(
            item["support_id"] in {"G-A", "G-B", "G-A、G-B"}
            for item in result.neighbor_checks
        ))

    def test_invalid_project_geometry_rejects_staged_edit_transactionally(self):
        rows = [
            {"StrutID": "S1", "StartX": 0, "StartY": 0,
             "EndX": 11600, "EndY": 0},
            {"StrutID": "S2", "StartX": 0, "StartY": 1000,
             "EndX": 11400, "EndY": 3300},
        ]
        project = self.geometry_project(rows)
        original = self.manual_plan(
            "S1", [("steel", 5000), ("jack", 600), ("steel", 6000)]
        )
        solution = support.make_global_solution([original])
        editing = SupportPlanEditing(project, SupportInputBuilder())
        before = list(solution.plans[0].pieces)

        with self.assertRaises(SolverInputBuildError):
            editing.stage_edit(
                solution,
                "S1",
                [("steel", 6000), ("jack", 600), ("steel", 5000)],
            )

        self.assertEqual(solution.plans[0].pieces, before)

    def test_shared_jack_invariant_failure_does_not_mutate_solution(self):
        rows = [
            {"StrutID": "A", "StartX": 0, "StartY": 0,
             "EndX": 11600, "EndY": 0},
            {"StrutID": "S1", "SharedLayoutGroup": "G1",
             "StartX": 0, "StartY": 1000, "EndX": 11600, "EndY": 1000},
            {"StrutID": "S2", "SharedLayoutGroup": "G1",
             "StartX": 0, "StartY": 1200, "EndX": 11600, "EndY": 1200},
        ]
        project = self.geometry_project(rows)
        normal = self.manual_plan(
            "A", [("steel", 5000), ("jack", 600), ("steel", 6000)]
        )
        first = self.manual_plan(
            "S1", [("steel", 5000), ("jack", 600), ("steel", 6000)],
            group="G1",
        )
        second = self.manual_plan(
            "S2", [("steel", 5000), ("jack", 600), ("steel", 6000)],
            group="G1",
        )
        second.jack_center += 200
        solution = support.GlobalSolution(
            plans=[normal, first, second], total_score=1, valid=True
        )
        editing = SupportPlanEditing(project, SupportInputBuilder())

        with self.assertRaises(support.SupportUnitAssemblyError) as caught:
            editing.stage_edit(
                solution,
                "A",
                [("steel", 6000), ("jack", 600), ("steel", 5000)],
            )

        self.assertEqual(caught.exception.code, "SHARED_JACK_INVARIANT_VIOLATION")
        self.assertEqual(solution.total_score, 1)
        self.assertEqual(solution.plans[0].support_id, "A")


if __name__ == "__main__":
    unittest.main()
