import unittest

from bracing_optimizer.algorithms import support
from bracing_optimizer.application.plan_editing import (
    SupportPlanEditing,
    WalerPlanEditing,
)
from bracing_optimizer.application.project_data import ProjectDataModel


class PlanEditingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
