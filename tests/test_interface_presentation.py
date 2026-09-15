import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bracing_optimizer.domain.material_rules import MaterialRatioTargets
from main import SupportInputApp, SupportSolverDialog, WalerSolverDialog
from bracing_optimizer.application.optimize_waler import OptimizeWaler, OptimizeWalerRequest
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.solver_input_builder import WalerProblemInput
from bracing_optimizer.algorithms.solver_search import (
    DEFAULT_SEARCH_POLICY,
    SolverDiagnostics,
)


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

    def test_solver_dialogs_use_shared_material_ratio_targets(self):
        support_source = inspect.getsource(SupportSolverDialog._run_solver)
        waler_source = inspect.getsource(WalerSolverDialog._run_solver)
        for source in (support_source, waler_source):
            self.assertIn("MaterialRatioTargets.normalized", source)
        self.assertNotIn("support.normalize_material_ratio_targets", support_source)

    def test_solver_workers_use_ui_queue_instead_of_tk_after(self):
        support_worker = inspect.getsource(SupportSolverDialog._solver_thread)
        waler_worker = inspect.getsource(WalerSolverDialog._solver_thread)
        self.assertNotIn("dialog.after", support_worker)
        self.assertNotIn("dialog.after", waler_worker)
        self.assertIn("_post_ui", support_worker)
        self.assertIn("_post_ui", waler_worker)

    def test_waler_results_are_edited_directly_without_custom_plan_actions(self):
        results_source = inspect.getsource(SupportInputApp._create_results_tab)
        editor_source = inspect.getsource(SupportInputApp._open_waler_plan_editor)

        self.assertNotIn("建立自訂方案", results_source)
        self.assertNotIn("刪除方案", results_source)
        for label in ("新增鋼材", "刪除鋼材", "上移", "下移"):
            self.assertIn(label, editor_source)
        self.assertIn("manual_modified", editor_source)
        self.assertIn("_apply_waler_plan_segments", editor_source)

    def test_double_clicking_a_waler_result_opens_the_plan_editor(self):
        class Tree:
            selected = None

            @staticmethod
            def identify_region(_x, _y):
                return "tree"

            @staticmethod
            def identify_row(_y):
                return "W1-方案1"

            @classmethod
            def selection_set(cls, item_id):
                cls.selected = item_id

        app = SupportInputApp.__new__(SupportInputApp)
        app.results_tree = Tree()
        app.result_items = {
            "W1-方案1": {
                "type": "waler",
                "result": {"waler_id": "W1", "option_index": 1},
            }
        }
        app._open_waler_plan_editor = Mock()

        handled = app._on_results_tree_double_click(SimpleNamespace(x=1, y=1))

        self.assertEqual(handled, "break")
        self.assertEqual(Tree.selected, "W1-方案1")
        app._open_waler_plan_editor.assert_called_once_with("W1-方案1")

    def test_modified_waler_results_are_detected_before_solver_replacement(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.result_items = {
            "W1-方案1": {
                "type": "waler",
                "result": {"waler_id": "W1", "manual_modified": True},
            },
            "W2-方案1": {
                "type": "waler",
                "result": {"waler_id": "W2"},
            },
        }

        self.assertTrue(app._has_modified_waler_results("W1"))
        self.assertFalse(app._has_modified_waler_results("W2"))

    def test_applying_waler_segments_updates_the_selected_option_in_place(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.project_data = ProjectDataModel(
            walers=[{
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 12000,
                "EndY": 0,
                "material_spec": "H400",
            }],
            inventory=[
                {
                    "ItemCode": "W-4000",
                    "Spec": "H400",
                    "Usage": "圍令",
                    "Length": 4000,
                    "Qty": 1,
                },
                {
                    "ItemCode": "W-8000",
                    "Spec": "H400",
                    "Usage": "圍令",
                    "Length": 8000,
                    "Qty": 1,
                },
            ],
        )
        app.result_items = {
            "W1-方案2": {
                "type": "waler",
                "result": {
                    "waler_id": "W1",
                    "option_index": 2,
                    "material_spec": "H400",
                    "required_length": 12000,
                    "forbidden_points": [],
                    "selected_plan": {"segments": [8000, 4000]},
                },
            }
        }
        app._mark_results_updated = Mock()

        edited = app._apply_waler_plan_segments("W1-方案2", [4000, 8000])

        result = app.result_items["W1-方案2"]["result"]
        self.assertEqual(set(app.result_items), {"W1-方案2"})
        self.assertEqual(edited["segments"], [4000, 8000])
        self.assertTrue(edited["legality"]["valid"])
        self.assertTrue(result["manual_modified"])
        self.assertEqual(
            app._get_result_tree_info(
                "W1-方案2",
                app.result_items["W1-方案2"],
            )["child_label"],
            "方案2 [已修改] ✅",
        )
        app._mark_results_updated.assert_called_once_with()

    def test_waler_solver_memory_key_contains_policy_and_waler_id(self):
        request = OptimizeWalerRequest(
            input=WalerProblemInput(
                waler_id="W1",
                start_point=(0, 0),
                end_point=(20_000, 0),
                total_length=20_000,
                forbidden_points=(5_000,),
                material_spec="H400x400",
                purchasable_lengths=(8_000, 10_000),
                stock_items=(),
            ),
            material_ratio_targets=MaterialRatioTargets.normalized(20, 50, 30),
        )
        key = OptimizeWaler().build_cache_key(request)
        self.assertEqual(key[1:3], DEFAULT_SEARCH_POLICY.cache_token)
        self.assertEqual(key[3], "W1")

    def test_waler_dialog_does_not_orchestrate_search_algorithm(self):
        source = inspect.getsource(WalerSolverDialog)
        for term in (
            "wales.Config",
            "wales.evolve",
            "waler_search_stages",
            "assess_waler_stage",
            "merge_waler_results",
            "population_size",
            "generations",
        ):
            self.assertNotIn(term, source)

    def test_project_ui_does_not_orchestrate_persistence_components(self):
        save_source = inspect.getsource(SupportInputApp.save_project_case)
        load_source = inspect.getsource(SupportInputApp.load_project_case)
        relink_source = inspect.getsource(SupportInputApp._relink_dxf)

        self.assertNotIn("DxfAssetManager", save_source + load_source + relink_source)
        self.assertNotIn("ProjectSerializer", load_source)
        self.assertNotIn("DxfCompatibilityChecker", relink_source)
        self.assertNotIn(".compare(", relink_source)
        self.assertNotIn(".merge_source_references(", relink_source)

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

    def test_strut_summary_includes_double_support_group(self):
        self.assertEqual(
            SupportInputApp.STRUT_SUMMARY_COLUMNS,
            (
                "No",
                "StrutID",
                "SharedLayoutGroup",
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

    def test_export_actions_remain_available_without_dxf_coordinate_metadata(self):
        class Tree:
            @staticmethod
            def selection():
                return ()

        class Configurable:
            def __init__(self):
                self.options = {}

            def configure(self, **kwargs):
                self.options.update(kwargs)

        class Variable:
            def __init__(self):
                self.value = ""

            def set(self, value):
                self.value = value

        app = SupportInputApp.__new__(SupportInputApp)
        app.results_tree = Tree()
        app.result_items = {
            "W1-plan-1": {
                "type": "waler",
                "visible": True,
                "result": {"waler_id": "W1"},
            },
        }
        app.export_results_excel_button = Configurable()
        app.export_results_dxf_button = Configurable()
        app.result_scope_var = Variable()
        app.result_scope_label = Configurable()

        app._update_result_action_states()

        self.assertEqual(
            app.export_results_excel_button.options["state"],
            "normal",
        )
        self.assertEqual(app.export_results_dxf_button.options["state"], "normal")
        self.assertIn(
            "匯出目前 1 個配置成果 Excel",
            app.export_results_excel_button.options["text"],
        )
        self.assertIn("Excel 材料明細仍可匯出", app.result_scope_var.value)
        self.assertIn("Project → World 座標資訊", app.result_scope_var.value)

    def test_excel_export_callback_uses_visible_results_without_dxf(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = object()
        app.current_project_path = None
        app.result_items = {
            "W1-plan-1": {
                "type": "waler",
                "visible": True,
                "result": {
                    "waler_id": "W1",
                    "material_spec": "H350",
                    "selected_plan": {"pieces": [("steel", 9000)]},
                },
            },
        }
        app._build_material_summary_payload = lambda: [{
            "usage": "圍令",
            "material_spec": "H350",
            "length": 9000,
            "used_qty": 1,
            "inventory_qty": 2,
            "remaining_qty": 1,
        }]
        app.excel_result_exporter = Mock()
        app.excel_result_exporter.export.return_value = SimpleNamespace(
            output_path="C:/output.xlsx",
            detail_row_count=1,
            material_quantity=1,
            summary_row_count=1,
        )

        with (
            patch(
                "main.filedialog.asksaveasfilename",
                return_value="C:/output.xlsx",
            ),
            patch("main.messagebox.showinfo") as showinfo,
        ):
            app._export_visible_results_to_excel()

        export_call = app.excel_result_exporter.export.call_args
        self.assertEqual(export_call.args[0], "C:/output.xlsx")
        self.assertEqual(export_call.args[1][0].member_id, "W1")
        self.assertEqual(export_call.kwargs["project_name"], "未命名專案")
        showinfo.assert_called_once()


if __name__ == "__main__":
    unittest.main()
