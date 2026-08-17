import unittest
from types import SimpleNamespace

from main import SupportSolverDialog
from solver_search import (
    CANDIDATE_INSUFFICIENT,
    ENGINEERING_CONSTRAINT_LIMITED,
    SCORING_PREFERENCE,
    SEARCH_INSUFFICIENT,
    SearchStageAssessment,
)


def candidate_status(
    support_id,
    actual_count,
    *,
    jack_buckets=2,
    patterns=2,
    styles=2,
    invalid_reasons=None,
):
    return {
        "config": SimpleNamespace(support_id=support_id),
        "actual_valid_count": actual_count,
        "diagnostics": {
            "diagnostics": {
                "candidate_pool_valid_count": actual_count,
                "invalid_reason_counts": invalid_reasons or {},
                "candidate_benchmark": {
                    "after_topn": {
                        "jack_bucket_count": jack_buckets,
                        "unique_steel_pattern_count": patterns,
                        "material_style_count": styles,
                    }
                },
            }
        },
    }


class SupportDiagnosticsClassificationTests(unittest.TestCase):
    def setUp(self):
        self.dialog = SupportSolverDialog.__new__(SupportSolverDialog)

    @staticmethod
    def assessment(*, stable=True, reasons=()):
        return SearchStageAssessment(
            should_escalate=False,
            result_is_stable=stable,
            reasons=tuple(reasons),
            stopping_reason=(
                "結果已穩定且方案數充足" if not reasons else "已達最大搜尋階段"
            ),
        )

    def test_search_insufficient_is_distinct(self):
        diagnostics = self.dialog._build_support_diagnostics(
            candidate_statuses=[candidate_status("S1", 100)],
            solution=SimpleNamespace(valid=False),
            stage_records=[{
                "stage": "DEEP",
                "unique_solution_count": 0,
                "decision": "停止搜尋",
                "reasons": ["尚未找到合法全域方案"],
            }],
            stage_scores=[],
            final_assessment=self.assessment(
                stable=False,
                reasons=("尚未找到合法全域方案",),
            ),
        )
        self.assertEqual(diagnostics.main_issue_category, SEARCH_INSUFFICIENT)
        self.assertFalse(diagnostics.infeasibility_proven)

    def test_candidate_insufficient_is_distinct(self):
        diagnostics = self.dialog._build_support_diagnostics(
            candidate_statuses=[candidate_status("S5", 2)],
            solution=SimpleNamespace(valid=True),
            stage_records=[{
                "stage": "STANDARD",
                "unique_solution_count": 5,
                "decision": "停止搜尋",
                "reasons": [],
            }],
            stage_scores=[10],
            final_assessment=self.assessment(),
        )
        self.assertEqual(diagnostics.main_issue_category, CANDIDATE_INSUFFICIENT)
        self.assertEqual(diagnostics.affected_component_ids, ["S5"])

    def test_engineering_constraint_limited_is_distinct(self):
        diagnostics = self.dialog._build_support_diagnostics(
            candidate_statuses=[candidate_status(
                "S8",
                0,
                invalid_reasons={"接頭落入禁止區": 12},
            )],
            solution=None,
            stage_records=[],
            stage_scores=[],
            final_assessment=None,
        )
        self.assertEqual(
            diagnostics.main_issue_category,
            ENGINEERING_CONSTRAINT_LIMITED,
        )
        self.assertEqual(diagnostics.issue_counts["接頭落入禁止區"], 12)

    def test_concentrated_phase1_options_are_candidate_insufficient(self):
        diagnostics = self.dialog._build_support_diagnostics(
            candidate_statuses=[candidate_status(
                "S12",
                100,
                jack_buckets=1,
                patterns=1,
                styles=1,
            )],
            solution=SimpleNamespace(valid=True),
            stage_records=[{
                "stage": "STANDARD",
                "unique_solution_count": 5,
                "decision": "停止搜尋",
                "reasons": [],
            }],
            stage_scores=[10],
            final_assessment=self.assessment(),
        )
        self.assertEqual(diagnostics.main_issue_category, CANDIDATE_INSUFFICIENT)
        self.assertFalse(diagnostics.search_was_escalated)

    def test_scoring_preference_is_distinct_and_does_not_change_search(self):
        plans = [
            SimpleNamespace(
                support_id=f"S{index}",
                pieces=[("steel", 10_000), ("jack", 600)],
            )
            for index in range(1, 5)
        ]
        diagnostics = self.dialog._build_support_diagnostics(
            candidate_statuses=[
                candidate_status(f"S{index}", 100)
                for index in range(1, 5)
            ],
            solution=SimpleNamespace(valid=True, plans=plans),
            stage_records=[{
                "stage": "STANDARD",
                "unique_solution_count": 5,
                "decision": "停止搜尋",
                "reasons": [],
            }],
            stage_scores=[10],
            final_assessment=self.assessment(),
        )
        self.assertEqual(diagnostics.main_issue_category, SCORING_PREFERENCE)
        self.assertFalse(diagnostics.search_was_escalated)


if __name__ == "__main__":
    unittest.main()
