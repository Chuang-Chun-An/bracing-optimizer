import unittest

from bracing_optimizer.algorithms import support
from bracing_optimizer.application.plan_editing import (
    SupportPlanEditing,
    WalerPlanEditing,
)
from bracing_optimizer.application.project_data import ProjectDataModel


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
        self.assertIn("尾端調整量不合法", plan["legality"]["violations"])

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

    def test_support_editing_stages_single_plan_without_mutating_source(self):
        config = self.support_config()
        original_plan = self.support_plan(config)
        solution = support.make_global_solution([original_plan])
        editing = self.support_editing(config)
        new_pieces = [("steel", 5000), ("jack", 600), ("steel", 6000)]

        result = editing.stage_edit(solution, "S1", new_pieces)

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


if __name__ == "__main__":
    unittest.main()
