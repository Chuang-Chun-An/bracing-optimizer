import inspect
import unittest
from types import SimpleNamespace

from main import SupportInputApp, SupportSolverDialog, WalerSolverDialog
from solver_search import DEFAULT_SEARCH_POLICY, SolverDiagnostics


class InterfacePresentationTests(unittest.TestCase):
    def test_solver_dialogs_hide_algorithm_tuning_fields(self):
        support_source = inspect.getsource(SupportSolverDialog.__init__)
        waler_source = inspect.getsource(WalerSolverDialog.__init__)

        self.assertNotIn("max_steel_combination_count_var", support_source)
        self.assertNotIn("target_valid_candidate_count_var", support_source)
        self.assertNotIn("generations_var", waler_source)
        self.assertNotIn("population_size_var", waler_source)
        self.assertNotIn("顯示進階設定", support_source + waler_source)
        self.assertIn("搜尋策略：系統自動調整", support_source)
        self.assertIn("搜尋策略：系統自動調整", waler_source)

    def test_material_ratio_fields_remain_in_both_solver_dialogs(self):
        support_source = inspect.getsource(SupportSolverDialog.__init__)
        waler_source = inspect.getsource(WalerSolverDialog.__init__)
        for source in (support_source, waler_source):
            self.assertIn("short_ratio_var", source)
            self.assertIn("mid_ratio_var", source)
            self.assertIn("long_ratio_var", source)

    def test_solver_workers_use_ui_queue_instead_of_tk_after(self):
        support_worker = inspect.getsource(SupportSolverDialog._solver_thread)
        waler_worker = inspect.getsource(WalerSolverDialog._solver_thread)
        self.assertNotIn("dialog.after", support_worker)
        self.assertNotIn("dialog.after", waler_worker)
        self.assertIn("_post_ui", support_worker)
        self.assertIn("_post_ui", waler_worker)

    def test_waler_solver_memory_key_contains_search_policy(self):
        key = WalerSolverDialog._build_solver_key(
            20_000,
            [5_000],
            20,
            50,
            30,
            [8_000, 10_000],
        )
        self.assertEqual(key[1:3], DEFAULT_SEARCH_POLICY.cache_token)

    def test_saved_result_summary_uses_engineering_status_not_algorithm_values(self):
        diagnostics = SolverDiagnostics(
            solver_type="support",
            legal_solution_found=True,
            search_was_escalated=True,
            result_is_stable=True,
        )
        text = "\n".join(
            SupportInputApp._solver_diagnostic_summary_lines(
                diagnostics.to_dict()
            )
        )
        self.assertIn("已找到合法方案", text)
        self.assertIn("系統已自動增加計算強度", text)
        for hidden_term in (
            "Generations", "Population", "Beam Width", "Random Seed",
            "Stability Window", "Candidate Count",
        ):
            self.assertNotIn(hidden_term, text)

    def test_strut_summary_is_kept_to_the_confirmed_seven_columns(self):
        self.assertEqual(
            SupportInputApp.STRUT_SUMMARY_COLUMNS,
            (
                "No",
                "StrutID",
                "FromWaler",
                "ToWaler",
                "material_spec",
                "TargetJackRegion",
                "Zoning",
            ),
        )

    def test_visible_result_scope_counts_support_children_individually(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.result_items = {
            "W1-option-1": {
                "type": "waler",
                "visible": True,
                "result": {"waler_id": "W1"},
            },
            "Z1": {
                "type": "support",
                "visible": True,
                "support_visibility": {"S1": True, "S2": False},
                "result": SimpleNamespace(
                    plans=[
                        SimpleNamespace(support_id="S1"),
                        SimpleNamespace(support_id="S2"),
                    ]
                ),
            },
        }

        counts, conflicts = app._visible_result_scope()

        self.assertEqual(counts, {"waler": 1, "support": 1})
        self.assertEqual(conflicts, ())

    def test_visible_result_scope_reports_multiple_plans_for_same_member(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.result_items = {
            "W1-option-1": {
                "type": "waler",
                "visible": True,
                "result": {"waler_id": "W1"},
            },
            "W1-option-2": {
                "type": "waler",
                "visible": True,
                "result": {"waler_id": "W1"},
            },
        }

        counts, conflicts = app._visible_result_scope()

        self.assertEqual(counts, {"waler": 2, "support": 0})
        self.assertEqual(conflicts, (("圍令", "W1", 2),))


if __name__ == "__main__":
    unittest.main()
