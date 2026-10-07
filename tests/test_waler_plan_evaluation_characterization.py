import unittest
from unittest.mock import patch

from bracing_optimizer.algorithms import wales
from bracing_optimizer.application.plan_editing import WalerPlanEditing
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.solver_input_builder import InventoryLookup


class WalerPlanEvaluationCharacterizationTests(unittest.TestCase):
    """Freeze the two pre-refactor Waler evaluation contracts."""

    INVENTORY_ROWS = [
        {
            "ItemCode": "W-4000",
            "Spec": "H400",
            "Usage": "圍令",
            "Length": 4000,
            "Qty": 3,
        },
        {
            "ItemCode": "W-6000",
            "Spec": "H400",
            "Usage": "圍令",
            "Length": 6000,
            "Qty": 2,
        },
        {
            "ItemCode": "W-8000",
            "Spec": "H400",
            "Usage": "圍令",
            "Length": 8000,
            "Qty": 2,
        },
    ]

    @classmethod
    def project_data(cls, inventory_rows=None):
        return ProjectDataModel(
            walers=[{
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 12000,
                "EndY": 0,
            }],
            inventory=list(
                cls.INVENTORY_ROWS
                if inventory_rows is None
                else inventory_rows
            ),
        )

    @staticmethod
    def _joints_for(segments):
        joints = []
        position = 0
        for segment in segments[:-1]:
            position += segment
            joints.append(position)
        return joints

    @classmethod
    def automatic_result(
        cls,
        segments,
        *,
        inventory_rows=None,
        material_spec="H400",
        support_points=None,
        min_piece_length=1000,
        max_piece_length=10000,
        joint_clearance=300,
    ):
        rows = cls.INVENTORY_ROWS if inventory_rows is None else inventory_rows
        inventory = InventoryLookup(rows)
        joints = cls._joints_for(segments)
        config = wales.Config(
            total_length=sum(segments),
            support_points=list(support_points or []),
            candidate_joint_points=list(joints),
            min_piece_length=min_piece_length,
            max_piece_length=max_piece_length,
            joint_clearance_to_support=joint_clearance,
            purchasable_lengths=inventory.purchasable_lengths(
                material_spec,
                "圍令",
            ),
        )
        joint_set = set(joints)
        individual = [
            int(point in joint_set)
            for point in config.candidate_joint_points
        ]
        return wales.evaluate_individual(
            individual,
            config,
            inventory.stock_items(material_spec, "圍令"),
        )

    @classmethod
    def manual_result(
        cls,
        segments,
        *,
        inventory_rows=None,
        material_spec="H400",
        forbidden_points=None,
        min_piece_length=1000,
        max_piece_length=10000,
        joint_clearance=300,
    ):
        return WalerPlanEditing(
            cls.project_data(inventory_rows)
        ).recalculate(
            {},
            list(segments),
            waler_id="W1",
            result_context={
                "material_spec": material_spec,
                "required_length": 12000,
                "forbidden_points": list(forbidden_points or []),
                "min_piece_length": min_piece_length,
                "max_piece_length": max_piece_length,
                "joint_clearance": joint_clearance,
            },
        )

    def test_automatic_legal_score_components_are_exact_with_inventory(self):
        result = self.automatic_result([6000, 6000])

        self.assertTrue(result["valid"])
        self.assertEqual(result["buy_count"], 0)
        self.assertEqual(result["distinct_groups"], 1)
        self.assertEqual(result["length_variation"], 0)
        self.assertEqual(result["under_4000_segment_count"], 0)
        self.assertEqual(
            result["segment_ratios"],
            {"short": 0.0, "mid": 1.0, "long": 0.0},
        )
        self.assertEqual(result["ratio_penalty"], 100000.0)
        self.assertEqual(result["joint_count"], 1)
        self.assertEqual(result["score"], 106000.0)
        self.assertIs(type(result["ratio_penalty"]), float)
        self.assertIs(type(result["score"]), float)
        self.assertEqual(
            result["assignments"],
            [
                {
                    "segment_length": 6000,
                    "stock_id": "W-6000#1",
                    "stock_group": "W-6000",
                    "stock_length": 6000,
                    "waste": 0,
                    "bought": False,
                },
                {
                    "segment_length": 6000,
                    "stock_id": "W-6000#2",
                    "stock_group": "W-6000",
                    "stock_length": 6000,
                    "waste": 0,
                    "bought": False,
                },
            ],
        )

    def test_automatic_legal_score_components_are_exact_when_buying(self):
        rows = [dict(row) for row in self.INVENTORY_ROWS]
        rows[1]["Qty"] = 1

        result = self.automatic_result([6000, 6000], inventory_rows=rows)

        self.assertTrue(result["valid"])
        self.assertEqual(result["buy_count"], 1)
        self.assertEqual(result["distinct_groups"], 2)
        self.assertEqual(result["length_variation"], 0)
        self.assertEqual(result["under_4000_segment_count"], 0)
        self.assertEqual(result["ratio_penalty"], 100000.0)
        self.assertEqual(result["joint_count"], 1)
        self.assertEqual(result["score"], 211000.0)

    def test_automatic_legal_score_components_cover_under_4000_penalty(self):
        rows = [
            {
                "ItemCode": "W-3500",
                "Spec": "H400",
                "Usage": "圍令",
                "Length": 3500,
                "Qty": 1,
            },
            {
                "ItemCode": "W-8500",
                "Spec": "H400",
                "Usage": "圍令",
                "Length": 8500,
                "Qty": 1,
            },
        ]

        result = self.automatic_result([3500, 8500], inventory_rows=rows)

        self.assertTrue(result["valid"])
        self.assertEqual(result["buy_count"], 0)
        self.assertEqual(result["distinct_groups"], 2)
        self.assertEqual(result["length_variation"], 5000)
        self.assertEqual(result["under_4000_segment_count"], 1)
        self.assertEqual(result["ratio_penalty"], 140000.0)
        self.assertEqual(result["joint_count"], 1)
        self.assertEqual(result["score"], 256000.0)

    def test_automatic_joint_clearance_boundary_is_exact(self):
        at_boundary = self.automatic_result(
            [6000, 6000],
            support_points=[6300],
        )
        inside_boundary = self.automatic_result(
            [6000, 6000],
            support_points=[6299],
        )

        self.assertTrue(at_boundary["valid"])
        self.assertEqual(at_boundary["score"], 106000.0)
        self.assertFalse(inside_boundary["valid"])
        self.assertEqual(inside_boundary["errors"], ["接頭 6000 距支撐過近"])
        self.assertEqual(inside_boundary["score"], 1050000)

    def test_automatic_piece_length_boundaries_and_failures_are_exact(self):
        at_minimum = self.automatic_result(
            [1000, 1000],
            inventory_rows=[{
                "ItemCode": "W-1000",
                "Spec": "H400",
                "Usage": "圍令",
                "Length": 1000,
                "Qty": 2,
            }],
        )
        at_maximum = self.automatic_result(
            [10000],
            inventory_rows=[{
                "ItemCode": "W-10000",
                "Spec": "H400",
                "Usage": "圍令",
                "Length": 10000,
                "Qty": 1,
            }],
        )
        outside = self.automatic_result(
            [500, 11500],
            inventory_rows=[
                {
                    "ItemCode": "W-500",
                    "Spec": "H400",
                    "Usage": "圍令",
                    "Length": 500,
                    "Qty": 1,
                },
                {
                    "ItemCode": "W-11500",
                    "Spec": "H400",
                    "Usage": "圍令",
                    "Length": 11500,
                    "Qty": 1,
                },
            ],
        )

        self.assertTrue(at_minimum["valid"])
        self.assertTrue(at_maximum["valid"])
        self.assertEqual(
            outside["errors"],
            [
                "段長 500 小於最短限制 1000",
                "段長 11500 大於最長限制 10000",
            ],
        )
        self.assertEqual(outside["score"], 1100000)

    def test_automatic_non_purchasable_lengths_short_circuit_exactly(self):
        result = self.automatic_result([5000, 7000])

        self.assertFalse(result["valid"])
        self.assertEqual(
            result["errors"],
            [
                "段長 5000 不在可用材料長度清單中",
                "段長 7000 不在可用材料長度清單中",
            ],
        )
        self.assertEqual(result["assignments"], [])
        self.assertIsNone(result["total_waste"])
        self.assertIsNone(result["ratio_penalty"])
        self.assertEqual(result["joint_count"], 1)
        self.assertEqual(result["score"], 1100000)

    def test_automatic_total_mismatch_penalty_is_exact(self):
        config = wales.Config(
            total_length=12000,
            support_points=[],
            candidate_joint_points=[6000],
            purchasable_lengths=[6000],
        )

        with patch.object(
            wales,
            "decode_individual",
            return_value=([6000], [6000]),
        ):
            result = wales.evaluate_individual(
                [1],
                config,
                [{"id": "W-6000", "length": 6000, "qty": 2}],
            )

        self.assertEqual(
            result["errors"],
            ["鋼材總長 6000 小於允許下限 11550"],
        )
        self.assertEqual(result["score"], 1050000)

    def test_automatic_allocation_failure_penalty_is_exact(self):
        config = wales.Config(
            total_length=12000,
            support_points=[],
            candidate_joint_points=[6000],
            purchasable_lengths=[6000],
        )

        with patch.object(wales, "allocate_stock_best_fit", return_value=None):
            result = wales.evaluate_individual(
                [1],
                config,
                [{"id": "W-6000", "length": 6000, "qty": 2}],
            )

        self.assertFalse(result["valid"])
        self.assertEqual(result["assignments"], [])
        self.assertIsNone(result["total_waste"])
        self.assertIsNone(result["buy_count"])
        self.assertIsNone(result["distinct_groups"])
        self.assertIsNone(result["length_variation"])
        self.assertEqual(result["joint_count"], 1)
        self.assertEqual(result["score"], 801000)

    def test_blank_material_fallback_uses_same_inventory_on_both_paths(self):
        automatic = self.automatic_result(
            [4000, 8000],
            material_spec="",
        )
        manual = self.manual_result(
            [4000, 8000],
            material_spec="",
        )

        core_fields = [
            "assignments",
            "total_waste",
            "buy_count",
            "distinct_groups",
            "length_variation",
            "under_4000_segment_count",
            "segment_ratios",
            "ratio_penalty",
            "joint_count",
            "score",
            "valid",
        ]
        for field in core_fields:
            with self.subTest(field=field):
                self.assertEqual(automatic[field], manual[field])
        self.assertEqual(automatic["score"], 75000.0)
        self.assertEqual(manual["score"], 75000.0)
        self.assertTrue(all(
            assignment["stock_group"].startswith("UNLIMITED-")
            for assignment in automatic["assignments"]
        ))

    def test_quantity_limited_inventory_is_shared_on_both_paths(self):
        rows = [dict(row) for row in self.INVENTORY_ROWS]
        rows[1]["Qty"] = 1
        automatic = self.automatic_result(
            [6000, 6000],
            inventory_rows=rows,
        )
        manual = self.manual_result(
            [6000, 6000],
            inventory_rows=rows,
        )

        core_fields = [
            "assignments",
            "total_waste",
            "buy_count",
            "distinct_groups",
            "length_variation",
            "under_4000_segment_count",
            "segment_ratios",
            "ratio_penalty",
            "joint_count",
            "score",
            "valid",
        ]
        for field in core_fields:
            with self.subTest(field=field):
                self.assertEqual(automatic[field], manual[field])
        self.assertEqual(automatic["buy_count"], 1)
        self.assertEqual(automatic["score"], 211000.0)

    def test_manual_legal_payload_and_field_order_are_exact(self):
        plan = self.manual_result([6000, 6000])

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
        self.assertEqual(plan["joints"], [6000])
        self.assertEqual(plan["segments"], [6000, 6000])
        self.assertEqual(plan["total_waste"], 0)
        self.assertEqual(plan["buy_count"], 0)
        self.assertEqual(plan["distinct_groups"], 1)
        self.assertEqual(plan["length_variation"], 0)
        self.assertEqual(plan["under_4000_segment_count"], 0)
        self.assertEqual(plan["segment_counts"], {"short": 0, "mid": 2, "long": 0})
        self.assertEqual(
            plan["segment_ratios"],
            {"short": 0.0, "mid": 1.0, "long": 0.0},
        )
        self.assertEqual(
            plan["ratio_targets"],
            {"short": 0.2, "mid": 0.5, "long": 0.3},
        )
        self.assertEqual(plan["ratio_penalty"], 100000.0)
        self.assertEqual(plan["joint_count"], 1)
        self.assertEqual(plan["score"], 106000.0)
        self.assertTrue(plan["valid"])
        self.assertEqual(plan["errors"], [])
        self.assertEqual(plan["pieces"], [("steel", 6000), ("steel", 6000)])
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

    def test_manual_invalid_joint_payload_is_characterized(self):
        plan = self.manual_result(
            [6000, 6000],
            forbidden_points=[6200],
        )

        self.assertFalse(plan["valid"])
        self.assertEqual(plan["errors"], [])
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
        self.assertEqual(
            plan["legality"],
            {
                "valid": False,
                "summary": "❌ 接頭落入禁止區",
                "violations": ["接頭落入禁止區"],
                "details": [
                    "❌ 接頭落入禁止區",
                    "接頭位置：6000 mm",
                    "禁止區：5900 ~ 6500 mm",
                ],
                "warnings": [],
                "required_length": 12000,
                "current_length": 12000,
                "tail_adjustment": 0,
                "gap": 0,
            },
        )

    def test_manual_non_purchasable_payload_is_characterized(self):
        plan = self.manual_result([5000, 7000])

        self.assertFalse(plan["valid"])
        self.assertIsNone(plan["assignments"])
        self.assertIsNone(plan["total_waste"])
        self.assertIsNone(plan["buy_count"])
        self.assertIsNone(plan["distinct_groups"])
        self.assertIsNone(plan["length_variation"])
        self.assertIsNone(plan["under_4000_segment_count"])
        self.assertIsNone(plan["ratio_penalty"])
        self.assertEqual(plan["joint_count"], 1)
        self.assertIsNone(plan["score"])
        self.assertEqual(
            plan["errors"],
            ["部分料長不在庫存可購買長度內，材料配置未完成。"],
        )
        self.assertEqual(
            plan["legality"]["violations"],
            ["無此料長", "無此料長"],
        )
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

    def test_manual_total_mismatch_payload_is_characterized(self):
        plan = self.manual_result([6000])

        self.assertFalse(plan["valid"])
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
        self.assertEqual(
            plan["legality"]["violations"],
            ["鋼材總長不足"],
        )
        self.assertEqual(
            plan["legality"]["details"],
            [
                "❌ 鋼材總長不足",
                "需求長度：12000 mm",
                "允許最短鋼材總長：11550 mm",
                "實際鋼材總長：6000 mm",
            ],
        )

    def test_invalid_joint_uses_shared_unavailable_core_and_compatible_outputs(self):
        automatic = self.automatic_result(
            [6000, 6000],
            support_points=[6200],
        )
        manual = self.manual_result(
            [6000, 6000],
            forbidden_points=[6200],
        )

        self.assertFalse(automatic["valid"])
        self.assertFalse(manual["valid"])
        self.assertEqual(automatic["score"], 1050000)
        self.assertIsNone(manual["score"])
        self.assertEqual(automatic["assignments"], [])
        self.assertIsNone(manual["assignments"])
        self.assertIsNone(manual["ratio_penalty"])

    def test_manual_projection_shows_all_joint_and_length_issues(self):
        joint_automatic = self.automatic_result(
            [4000, 4000, 4000],
            support_points=[4200, 8200],
        )
        joint_manual = self.manual_result(
            [4000, 4000, 4000],
            forbidden_points=[4200, 8200],
        )
        length_automatic = self.automatic_result([5000, 7000])
        length_manual = self.manual_result([5000, 7000])

        self.assertEqual(
            joint_automatic["errors"],
            ["接頭 4000 距支撐過近", "接頭 8000 距支撐過近"],
        )
        self.assertEqual(
            joint_manual["legality"]["violations"],
            ["接頭落入禁止區", "接頭落入禁止區"],
        )
        self.assertEqual(
            length_automatic["errors"],
            [
                "段長 5000 不在可用材料長度清單中",
                "段長 7000 不在可用材料長度清單中",
            ],
        )
        self.assertEqual(
            length_manual["legality"]["violations"],
            ["無此料長", "無此料長"],
        )

    def test_manual_total_length_boundaries_and_tail_adjustment(self):
        cases = (
            ([6000, 5549], False, ["鋼材總長不足"], None, None),
            ([6000, 5550], True, [], 300, 150),
            ([6000, 6000], True, [], 0, 0),
            ([6000, 6001], False, ["鋼材總長太長"], None, None),
        )
        for (
            segments,
            expected_valid,
            expected_violations,
            expected_adjustment,
            expected_gap,
        ) in cases:
            rows = [
                {
                    "ItemCode": f"W-{length}",
                    "Spec": "H400",
                    "Usage": "圍令",
                    "Length": length,
                    "Qty": segments.count(length),
                }
                for length in sorted(set(segments))
            ]
            with self.subTest(steel_length=sum(segments)):
                plan = self.manual_result(segments, inventory_rows=rows)

                self.assertEqual(plan["valid"], expected_valid)
                self.assertEqual(
                    plan["legality"]["violations"],
                    expected_violations,
                )
                self.assertEqual(plan["tail_adjustment"], expected_adjustment)
                self.assertEqual(plan["gap"], expected_gap)
                expected_pieces = [
                    ("steel", length) for length in segments
                ]
                if expected_adjustment:
                    expected_pieces.append(("shim", expected_adjustment))
                self.assertEqual(plan["pieces"], expected_pieces)
                if expected_valid:
                    self.assertIsNotNone(plan["assignments"])
                    self.assertIsNotNone(plan["score"])
                else:
                    self.assertIsNone(plan["assignments"])
                    self.assertIsNone(plan["ratio_penalty"])
                    self.assertIsNone(plan["score"])

    def test_manual_issue_order_is_total_then_joints_then_segments(self):
        plan = self.manual_result(
            [5000, 6000],
            forbidden_points=[5200],
        )

        self.assertEqual(
            plan["legality"]["violations"],
            ["鋼材總長不足", "接頭落入禁止區", "無此料長"],
        )
        self.assertEqual(plan["legality"]["summary"], "❌ 共 3 項違規")

    def test_invalid_core_result_is_identical_on_automatic_and_manual_paths(self):
        original = wales.evaluate_waler_plan
        captured = []

        def capture(*args, **kwargs):
            result = original(*args, **kwargs)
            captured.append(result)
            return result

        with patch.object(wales, "evaluate_waler_plan", side_effect=capture):
            automatic = self.automatic_result(
                [6000, 6000],
                support_points=[6200],
            )
            manual = self.manual_result(
                [6000, 6000],
                forbidden_points=[6200],
            )

        self.assertEqual(len(captured), 2)
        automatic_core, manual_core = captured
        self.assertEqual(automatic_core, manual_core)
        self.assertEqual(automatic["score"], 1050000)
        self.assertEqual(manual["score"], manual_core.local_score)
        self.assertIsNone(manual["score"])
        self.assertIsNone(automatic_core.assignments)
        self.assertIsNone(automatic_core.ratio_penalty)


if __name__ == "__main__":
    unittest.main()
