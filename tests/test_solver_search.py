import unittest
from types import SimpleNamespace

from bracing_optimizer.algorithms.solver_search import (
    DEFAULT_SEARCH_POLICY,
    SCORING_PREFERENCE,
    SolverDiagnostics,
    assess_support_stage,
    assess_waler_stage,
    merge_waler_results,
    score_history_is_stable,
    select_best_support_solution,
)


class SolverSearchPolicyTests(unittest.TestCase):
    def test_formal_support_phase1_policy_is_unchanged(self):
        policy = DEFAULT_SEARCH_POLICY
        self.assertEqual(policy.support_phase1_length_combination_count, 100)
        self.assertEqual(policy.support_phase1_retained_candidate_count, 100)
        self.assertEqual(policy.support_phase1_jack_bucket_size, 100)
        self.assertEqual(policy.support_phase1_candidates_per_jack_bucket, 2)

    def test_stable_legal_waler_stage_stops(self):
        assessment = assess_waler_stage(
            valid_solution_count=10,
            unique_solution_count=8,
            best_score_history=[100.0] * DEFAULT_SEARCH_POLICY.stability_window,
            is_last_stage=False,
        )
        self.assertFalse(assessment.should_escalate)
        self.assertTrue(assessment.result_is_stable)

    def test_waler_stage_escalates_when_no_legal_solution(self):
        assessment = assess_waler_stage(
            valid_solution_count=0,
            unique_solution_count=0,
            best_score_history=[100.0] * DEFAULT_SEARCH_POLICY.stability_window,
            is_last_stage=False,
        )
        self.assertTrue(assessment.should_escalate)
        self.assertIn("尚未找到合法方案", assessment.reasons)

    def test_waler_stage_escalates_when_unique_solutions_are_insufficient(self):
        assessment = assess_waler_stage(
            valid_solution_count=10,
            unique_solution_count=1,
            best_score_history=[100.0] * DEFAULT_SEARCH_POLICY.stability_window,
            is_last_stage=False,
        )
        self.assertTrue(assessment.should_escalate)

    def test_waler_stage_escalates_while_tail_score_keeps_improving(self):
        assessment = assess_waler_stage(
            valid_solution_count=10,
            unique_solution_count=8,
            best_score_history=[105.0, 104.0, 103.0, 102.0, 100.0],
            is_last_stage=False,
        )
        self.assertTrue(assessment.should_escalate)
        self.assertFalse(assessment.result_is_stable)

    def test_maximum_stage_always_stops(self):
        assessment = assess_waler_stage(
            valid_solution_count=0,
            unique_solution_count=0,
            best_score_history=[],
            is_last_stage=True,
        )
        self.assertFalse(assessment.should_escalate)
        self.assertEqual(assessment.stopping_reason, "已達最大搜尋階段")

    def test_deterministic_support_search_compares_widths_when_pruned(self):
        first = assess_support_stage(
            legal_solution_found=True,
            unique_solution_count=10,
            stage_best_scores=[100.0],
            pruning_was_active=True,
            is_last_stage=False,
        )
        second = assess_support_stage(
            legal_solution_found=True,
            unique_solution_count=10,
            stage_best_scores=[100.0, 100.0],
            pruning_was_active=True,
            is_last_stage=False,
        )
        self.assertTrue(first.should_escalate)
        self.assertFalse(second.should_escalate)
        self.assertTrue(second.result_is_stable)

    def test_scoring_preference_is_not_an_escalation_input(self):
        diagnostics = SolverDiagnostics(
            solver_type="waler",
            main_issue_category=SCORING_PREFERENCE,
        )
        assessment = assess_waler_stage(
            valid_solution_count=10,
            unique_solution_count=10,
            best_score_history=[100.0] * DEFAULT_SEARCH_POLICY.stability_window,
            is_last_stage=False,
        )
        self.assertEqual(diagnostics.main_issue_category, SCORING_PREFERENCE)
        self.assertFalse(assessment.should_escalate)

    def test_policy_version_is_part_of_cache_token(self):
        self.assertEqual(
            DEFAULT_SEARCH_POLICY.cache_token,
            (DEFAULT_SEARCH_POLICY.policy_id, DEFAULT_SEARCH_POLICY.policy_version),
        )


class SolverSearchResultMergeTests(unittest.TestCase):
    def test_waler_results_are_merged_across_stages_by_canonical_signature(self):
        first = {"segments": [6000, 6000], "joints": [6000], "gap": 0, "score": 20, "valid": True}
        duplicate_better = {"segments": [6000, 6000], "joints": [6000], "gap": 0, "score": 10, "valid": True}
        different = {"segments": [5000, 7000], "joints": [5000], "gap": 0, "score": 15, "valid": True}

        merged = merge_waler_results([first, duplicate_better, different])

        self.assertEqual([item["score"] for item in merged], [10, 15])

    def test_best_legal_support_solution_is_retained_across_stages(self):
        plan_a = SimpleNamespace(
            support_id="S1", pieces=[("steel", 10000)], joints=[], gap=0,
            jack_center=1000, jack_region_id=1,
        )
        plan_b = SimpleNamespace(
            support_id="S1", pieces=[("steel", 9000)], joints=[], gap=0,
            jack_center=1100, jack_region_id=1,
        )
        earlier = SimpleNamespace(plans=[plan_a], total_score=10, valid=True)
        later = SimpleNamespace(plans=[plan_b], total_score=20, valid=True)

        self.assertIs(select_best_support_solution([earlier, later]), earlier)


class SolverDiagnosticsTests(unittest.TestCase):
    def test_diagnostics_round_trip_and_legacy_missing_value(self):
        diagnostics = SolverDiagnostics(
            solver_type="support",
            search_stage="ENHANCED",
            legal_solution_found=True,
            affected_component_ids=["S5"],
        )
        restored = SolverDiagnostics.from_dict(diagnostics.to_dict())

        self.assertEqual(restored.search_stage, "ENHANCED")
        self.assertEqual(restored.affected_component_ids, ["S5"])
        self.assertIsNone(SolverDiagnostics.from_dict(None))

    def test_score_stability_uses_relative_improvement(self):
        stable_history = [100.0, 100.0, 100.0, 100.0, 99.95]
        improving_history = [100.0, 99.0, 98.0, 97.0, 96.0]
        self.assertTrue(score_history_is_stable(stable_history))
        self.assertFalse(score_history_is_stable(improving_history))


if __name__ == "__main__":
    unittest.main()
