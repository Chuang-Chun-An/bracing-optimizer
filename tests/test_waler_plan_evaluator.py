import unittest
from unittest.mock import patch

from bracing_optimizer.algorithms import wales


class WalerPlanEvaluatorTests(unittest.TestCase):
    def config(
        self,
        *,
        required_length=12_000,
        support_points=None,
        purchasable_lengths=None,
    ):
        return wales.Config(
            total_length=required_length,
            support_points=list(support_points or []),
            candidate_joint_points=[6_000],
            purchasable_lengths=list(
                purchasable_lengths
                if purchasable_lengths is not None
                else [4_000, 5_800, 5_799, 6_000, 6_001, 8_000]
            ),
        )

    @staticmethod
    def stock(length, qty, item_id=None):
        return [{
            "id": item_id or f"W-{length}",
            "length": length,
            "qty": qty,
        }]

    def test_total_length_closed_interval_boundaries(self):
        config = self.config()
        cases = (
            ([6_000, 5_799], False, wales.ISSUE_STEEL_TOTAL_SHORT),
            ([6_000, 5_800], True, None),
            ([6_000, 6_000], True, None),
            ([6_000, 6_001], False, wales.ISSUE_STEEL_TOTAL_LONG),
        )

        for segments, expected_valid, expected_total_issue in cases:
            with self.subTest(steel_length=sum(segments)):
                result = wales.evaluate_waler_plan(
                    segments,
                    [6_000],
                    config,
                    [],
                    required_length=12_000,
                )

                self.assertEqual(result.valid, expected_valid)
                total_codes = [
                    issue.code
                    for issue in result.issues
                    if issue.code in {
                        wales.ISSUE_STEEL_TOTAL_SHORT,
                        wales.ISSUE_STEEL_TOTAL_LONG,
                    }
                ]
                self.assertEqual(
                    total_codes,
                    [] if expected_total_issue is None else [expected_total_issue],
                )
                if expected_valid:
                    self.assertIsNotNone(result.assignments)
                    self.assertIsNotNone(result.local_score)
                else:
                    self.assertIsNone(result.assignments)
                    self.assertIsNone(result.total_waste)
                    self.assertIsNone(result.buy_count)
                    self.assertIsNone(result.distinct_groups)
                    self.assertIsNone(result.length_variation)
                    self.assertIsNone(result.under_4000_segment_count)
                    self.assertIsNone(result.segment_counts)
                    self.assertIsNone(result.segment_ratios)
                    self.assertIsNone(result.ratio_penalty)
                    self.assertIsNone(result.local_score)

    def test_total_issue_facts_are_normalized(self):
        config = self.config(purchasable_lengths=[5_799, 6_000])

        result = wales.evaluate_waler_plan(
            [6_000, 5_799],
            [6_000],
            config,
            [],
            required_length=12_000,
        )

        issue = result.issues[0]
        self.assertEqual(issue.code, wales.ISSUE_STEEL_TOTAL_SHORT)
        self.assertEqual(
            dict(issue.facts),
            {
                "required_length": 12_000,
                "minimum_steel_length": 11_800,
                "actual_steel_length": 11_799,
            },
        )

    def test_collects_multiple_joint_issues_with_distinct_facts(self):
        config = self.config(
            support_points=[4_200, 8_200],
            purchasable_lengths=[4_000],
        )

        result = wales.evaluate_waler_plan(
            [4_000, 4_000, 4_000],
            [4_000, 8_000],
            config,
            self.stock(4_000, 3),
        )

        issues = [
            issue
            for issue in result.issues
            if issue.code == wales.ISSUE_JOINT_CLEARANCE
        ]
        self.assertEqual(len(issues), 2)
        self.assertEqual(
            [dict(issue.facts)["joint_index"] for issue in issues],
            [0, 1],
        )
        self.assertNotEqual(issues[0], issues[1])

    def test_same_missing_length_at_two_indexes_remains_two_issues(self):
        config = self.config(
            required_length=10_000,
            purchasable_lengths=[6_000],
        )

        result = wales.evaluate_waler_plan(
            [5_000, 5_000],
            [5_000],
            config,
            [],
        )

        issues = [
            issue
            for issue in result.issues
            if issue.code == wales.ISSUE_SEGMENT_NOT_PURCHASABLE
        ]
        self.assertEqual(len(issues), 2)
        self.assertEqual(
            [dict(issue.facts)["segment_index"] for issue in issues],
            [0, 1],
        )
        self.assertNotEqual(issues[0], issues[1])

    def test_issue_identity_does_not_depend_on_display_message(self):
        display_message = "相同顯示訊息"
        below_minimum = wales.WalerPlanIssue(
            code=wales.ISSUE_SEGMENT_BELOW_MINIMUM,
            facts=(("segment_index", 0), ("segment_length", 500)),
        )
        not_purchasable = wales.WalerPlanIssue(
            code=wales.ISSUE_SEGMENT_NOT_PURCHASABLE,
            facts=(("segment_index", 0), ("segment_length", 500)),
        )

        projected_messages = [display_message, display_message]

        self.assertEqual(projected_messages[0], projected_messages[1])
        self.assertNotEqual(below_minimum, not_purchasable)
        self.assertEqual(len({below_minimum, not_purchasable}), 2)

    def test_hard_invalid_plan_stops_before_allocation_and_scoring(self):
        config = self.config(
            support_points=[6_200],
            purchasable_lengths=[6_000],
        )

        with patch.object(wales, "allocate_stock_best_fit") as allocate:
            result = wales.evaluate_waler_plan(
                [6_000, 6_000],
                [6_000],
                config,
                self.stock(6_000, 2),
            )

        allocate.assert_not_called()
        self.assertFalse(result.valid)
        self.assertEqual(
            [issue.code for issue in result.issues],
            [wales.ISSUE_JOINT_CLEARANCE],
        )
        self.assertIsNone(result.assignments)
        self.assertIsNone(result.total_waste)
        self.assertIsNone(result.buy_count)
        self.assertIsNone(result.distinct_groups)
        self.assertIsNone(result.length_variation)
        self.assertIsNone(result.under_4000_segment_count)
        self.assertIsNone(result.segment_counts)
        self.assertIsNone(result.segment_ratios)
        self.assertIsNone(result.ratio_penalty)
        self.assertIsNone(result.local_score)

    def test_collects_every_hard_issue_before_stopping(self):
        config = self.config(
            support_points=[700],
            purchasable_lengths=[6_000],
        )

        with patch.object(wales, "allocate_stock_best_fit") as allocate:
            result = wales.evaluate_waler_plan(
                [500, 10_500],
                [500],
                config,
                [],
            )

        allocate.assert_not_called()
        self.assertEqual(
            [issue.code for issue in result.issues],
            [
                wales.ISSUE_STEEL_TOTAL_SHORT,
                wales.ISSUE_JOINT_CLEARANCE,
                wales.ISSUE_SEGMENT_BELOW_MINIMUM,
                wales.ISSUE_SEGMENT_NOT_PURCHASABLE,
                wales.ISSUE_SEGMENT_ABOVE_MAXIMUM,
                wales.ISSUE_SEGMENT_NOT_PURCHASABLE,
            ],
        )
        self.assertIsNone(result.assignments)
        self.assertIsNone(result.segment_counts)
        self.assertIsNone(result.local_score)

    def test_repair_boolean_probe_matches_full_issue_collection(self):
        cases = (
            ([6_000], [6_000, 6_000], [], [6_000], False),
            ([6_000], [6_000, 5_799], [], [5_799, 6_000], True),
            ([6_000], [6_000, 6_000], [6_200], [6_000], True),
            ([500], [500, 11_500], [], [500, 11_500], True),
            ([500], [500, 10_500], [700], [6_000], True),
        )

        for joints, segments, supports, lengths, expected_has_issue in cases:
            with self.subTest(
                joints=joints,
                segments=segments,
                supports=supports,
            ):
                config = self.config(
                    support_points=supports,
                    purchasable_lengths=lengths,
                )
                full_issues = wales._collect_waler_plan_issues(
                    joints,
                    segments,
                    config,
                    required_length=12_000,
                )
                boolean_result = wales._has_waler_plan_issue(
                    joints,
                    segments,
                    config,
                    required_length=12_000,
                )

                self.assertEqual(boolean_result, bool(full_issues))
                self.assertEqual(boolean_result, expected_has_issue)

    def test_repair_probe_does_not_materialize_or_format_issues(self):
        config = self.config(
            support_points=[6_200],
            purchasable_lengths=[6_000],
        )

        with (
            patch.object(
                wales,
                "_collect_waler_plan_issues",
                side_effect=AssertionError("repair materialized diagnostics"),
            ) as collect,
            patch.object(
                wales,
                "format_automatic_waler_issue",
                side_effect=AssertionError("repair formatted diagnostics"),
            ) as formatter,
            patch.object(
                wales,
                "_waler_issue",
                side_effect=AssertionError("repair constructed an issue"),
            ) as issue_factory,
        ):
            repaired = wales.repair_individual([1], config)

        self.assertEqual(len(repaired), 1)
        collect.assert_not_called()
        formatter.assert_not_called()
        issue_factory.assert_not_called()

    def test_non_purchasable_plan_has_no_fabricated_allocation_or_score(self):
        config = self.config(purchasable_lengths=[6_000])

        result = wales.evaluate_waler_plan(
            [5_000, 7_000],
            [5_000],
            config,
            [],
        )

        self.assertFalse(result.valid)
        self.assertEqual(
            [issue.code for issue in result.issues],
            [
                wales.ISSUE_SEGMENT_NOT_PURCHASABLE,
                wales.ISSUE_SEGMENT_NOT_PURCHASABLE,
            ],
        )
        self.assertIsNone(result.assignments)
        self.assertIsNone(result.total_waste)
        self.assertIsNone(result.buy_count)
        self.assertIsNone(result.distinct_groups)
        self.assertIsNone(result.length_variation)
        self.assertIsNone(result.ratio_penalty)
        self.assertIsNone(result.local_score)

    def test_defensive_allocation_failure_has_named_issue_and_no_score(self):
        config = self.config(purchasable_lengths=[6_000])

        with patch.object(wales, "allocate_stock_best_fit", return_value=None):
            result = wales.evaluate_waler_plan(
                [6_000, 6_000],
                [6_000],
                config,
                self.stock(6_000, 2),
            )

        self.assertFalse(result.valid)
        self.assertEqual(
            [issue.code for issue in result.issues],
            [wales.ISSUE_ALLOCATION_UNAVAILABLE],
        )
        self.assertIsNone(result.assignments)
        self.assertIsNone(result.buy_count)
        self.assertIsNone(result.local_score)

    def test_automatic_projection_keeps_exact_legal_score(self):
        config = self.config(purchasable_lengths=[6_000])

        result = wales.evaluate_individual(
            [1],
            config,
            self.stock(6_000, 2),
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["buy_count"], 0)
        self.assertEqual(result["distinct_groups"], 1)
        self.assertEqual(result["length_variation"], 0)
        self.assertEqual(result["under_4000_segment_count"], 0)
        self.assertEqual(result["ratio_penalty"], 100000.0)
        self.assertEqual(result["joint_count"], 1)
        self.assertEqual(result["score"], 106000.0)

    def test_automatic_projection_keeps_invalid_search_penalty(self):
        config = self.config(
            support_points=[6_200],
            purchasable_lengths=[6_000],
        )

        result = wales.evaluate_individual(
            [1],
            config,
            self.stock(6_000, 2),
        )

        self.assertFalse(result["valid"])
        self.assertEqual(result["assignments"], [])
        self.assertEqual(result["ratio_penalty"], None)
        self.assertEqual(result["score"], 1050000)

    def test_evaluator_and_automatic_projection_use_same_legal_components(self):
        config = self.config(purchasable_lengths=[6_000])
        stock_items = self.stock(6_000, 1)
        core = wales.evaluate_waler_plan(
            [6_000, 6_000],
            [6_000],
            config,
            stock_items,
        )
        automatic = wales.evaluate_individual([1], config, stock_items)

        self.assertEqual(automatic["assignments"], list(core.assignments or ()))
        self.assertEqual(automatic["total_waste"], core.total_waste)
        self.assertEqual(automatic["buy_count"], core.buy_count)
        self.assertEqual(automatic["distinct_groups"], core.distinct_groups)
        self.assertEqual(automatic["length_variation"], core.length_variation)
        self.assertEqual(
            automatic["under_4000_segment_count"],
            core.under_4000_segment_count,
        )
        self.assertEqual(automatic["segment_ratios"], core.segment_ratios)
        self.assertEqual(automatic["ratio_penalty"], core.ratio_penalty)
        self.assertEqual(automatic["joint_count"], core.joint_count)
        self.assertEqual(automatic["score"], core.local_score)

    def test_waler_results_never_add_adjustment_or_shim(self):
        config = wales.Config(
            total_length=12_200,
            support_points=[],
            candidate_joint_points=[6_000],
            purchasable_lengths=[6_000],
            top_n=1,
        )
        evaluated = wales.evaluate_individual(
            [1],
            config,
            self.stock(6_000, 2),
        )

        results = wales._top_results([evaluated], config)

        self.assertTrue(results[0]["valid"])
        self.assertEqual(results[0]["tail_adjustment"], 0)
        self.assertEqual(results[0]["gap"], 200)
        self.assertEqual(
            results[0]["pieces"],
            [("steel", 6_000), ("steel", 6_000)],
        )

    def test_adjustment_only_shortfall_is_invalid_without_search_changes(self):
        config = wales.Config(
            total_length=12_201,
            support_points=[],
            candidate_joint_points=[6_000],
            purchasable_lengths=[6_000],
        )

        result = wales.evaluate_individual(
            [1],
            config,
            self.stock(6_000, 2),
        )

        self.assertEqual(config.steel_target_length, 12_000)
        self.assertEqual(config.tail_adjustment, 0)
        self.assertEqual(config.tail_gap, 201)
        self.assertFalse(result["valid"])
        self.assertEqual(result["score"], 1050000)
        self.assertEqual(
            result["errors"],
            ["鋼材總長 12000 小於允許下限 12001"],
        )


if __name__ == "__main__":
    unittest.main()
