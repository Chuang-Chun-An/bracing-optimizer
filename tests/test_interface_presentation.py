import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bracing_optimizer.domain.material_rules import MaterialRatioTargets
from main import SupportInputApp, SupportSolverDialog, WalerSolverDialog
from bracing_optimizer.application.optimize_waler import OptimizeWaler, OptimizeWalerRequest
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.solver_input_builder import WalerProblemInput
from bracing_optimizer.algorithms.solver_search import (
    DEFAULT_SEARCH_POLICY,
    SolverDiagnostics,
)


class InterfacePresentationTests(unittest.TestCase):
    @staticmethod
    def make_global_waler_preflight_app(*, manually_modified):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = object()
        app.project_data = object()
        app.validate_data = Mock(return_value=True)
        app._show_waler_solver_busy = Mock()
        app._ensure_waler_solver_guard = Mock(
            return_value=SimpleNamespace(is_busy=False)
        )
        builder = Mock()
        builder.build_all.return_value = {
            "W1": SimpleNamespace(
                waler_id="W1",
                material_spec="",
                purchasable_lengths=(),
            )
        }
        app._ensure_solver_input_builders = Mock(
            return_value=(Mock(), builder)
        )
        app._has_modified_waler_results = Mock(
            return_value=manually_modified
        )
        app._apply_waler_global_result = Mock()
        app.make_waler_global_optimizer = Mock(return_value=object())
        return app

    @staticmethod
    def make_single_waler_preflight_app(waler_inputs):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = object()
        app.project_data = object()
        app.validate_data = Mock(return_value=True)
        app.show_result = Mock()
        app._show_waler_solver_busy = Mock()
        app._ensure_waler_solver_guard = Mock(
            return_value=SimpleNamespace(is_busy=False)
        )
        builder = Mock()
        builder.build_all.return_value = waler_inputs
        app._ensure_solver_input_builders = Mock(
            return_value=(Mock(), builder)
        )
        app._has_modified_waler_results = Mock(return_value=False)
        app.solver_memory = {}
        app._store_waler_result = Mock()
        app.make_waler_optimizer = Mock(return_value=object())
        return app

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

    def test_global_waler_declined_overwrite_stops_before_dialog_and_solver(self):
        app = self.make_global_waler_preflight_app(manually_modified=True)

        with patch("main.messagebox.askyesno", return_value=False) as confirm:
            with patch("main.WalerGlobalSolverDialog") as dialog_class:
                app._open_waler_global_solver()

        confirm.assert_called_once()
        dialog_class.assert_not_called()
        app.make_waler_global_optimizer.assert_not_called()
        app._apply_waler_global_result.assert_not_called()

    def test_global_waler_accepted_overwrite_opens_solver_dialog(self):
        app = self.make_global_waler_preflight_app(manually_modified=True)

        with patch("main.messagebox.askyesno", return_value=True) as confirm:
            with patch("main.WalerGlobalSolverDialog") as dialog_class:
                app._open_waler_global_solver()

        confirm.assert_called_once()
        dialog_class.assert_called_once()
        dialog_class.return_value.open.assert_called_once_with()

    def test_global_waler_without_manual_edits_skips_overwrite_prompt(self):
        app = self.make_global_waler_preflight_app(manually_modified=False)

        with patch("main.messagebox.askyesno") as confirm:
            with patch("main.WalerGlobalSolverDialog") as dialog_class:
                app._open_waler_global_solver()

        confirm.assert_not_called()
        dialog_class.assert_called_once()
        dialog_class.return_value.open.assert_called_once_with()

    def test_single_waler_selection_excludes_rc_input(self):
        inputs = {
            "W-RC": SimpleNamespace(
                waler_id="W-RC",
                material_spec=" rc ",
                purchasable_lengths=(),
            ),
            "W1": SimpleNamespace(
                waler_id="W1",
                material_spec="H400x400",
                purchasable_lengths=(5_000,),
            ),
        }
        app = self.make_single_waler_preflight_app(inputs)

        with patch("main.WalerSelectionDialog") as selection_class:
            selection_class.return_value.open.return_value = None
            with patch("main.WalerSolverDialog") as solver_class:
                app._open_waler_solver()

        self.assertEqual(selection_class.call_args.args[1], ["W1"])
        solver_class.assert_not_called()

    def test_single_waler_all_rc_returns_without_dialog_or_state_change(self):
        inputs = {
            "W-RC": SimpleNamespace(
                waler_id="W-RC",
                material_spec="RC",
                purchasable_lengths=(),
            )
        }
        app = self.make_single_waler_preflight_app(inputs)
        sentinel_results = {"old": object()}
        app._project_results = ProjectResultModel(result_items=sentinel_results.copy())

        with patch("main.WalerSelectionDialog") as selection_class:
            with patch("main.WalerSolverDialog") as solver_class:
                app._open_waler_solver()

        selection_class.assert_not_called()
        solver_class.assert_not_called()
        app.make_waler_optimizer.assert_not_called()
        self.assertEqual(app.result_items, sentinel_results)
        app.show_result.assert_called_once()

    def test_global_waler_filters_rc_before_inventory_and_overwrite_checks(self):
        app = self.make_global_waler_preflight_app(manually_modified=True)
        builder = app._ensure_solver_input_builders.return_value[1]
        builder.build_all.return_value = {
            "W-RC": SimpleNamespace(
                waler_id="W-RC",
                material_spec="RC",
                purchasable_lengths=(),
            ),
            "W1": SimpleNamespace(
                waler_id="W1",
                material_spec="H400x400",
                purchasable_lengths=(5_000,),
            ),
        }

        with patch("main.messagebox.askyesno", return_value=True):
            with patch("main.WalerGlobalSolverDialog") as dialog_class:
                app._open_waler_global_solver()

        self.assertEqual(
            [item.waler_id for item in dialog_class.call_args.args[1]],
            ["W1"],
        )
        app._has_modified_waler_results.assert_called_once_with("W1")
        dialog_class.return_value.open.assert_called_once_with()

    def test_global_waler_all_rc_returns_without_dialog_or_state_change(self):
        app = self.make_global_waler_preflight_app(manually_modified=True)
        app.show_result = Mock()
        app._project_results = ProjectResultModel(result_items={"old": {}})
        builder = app._ensure_solver_input_builders.return_value[1]
        builder.build_all.return_value = {
            "W-RC": SimpleNamespace(
                waler_id="W-RC",
                material_spec="RC",
                purchasable_lengths=(),
            )
        }

        with patch("main.messagebox.askyesno") as confirm:
            with patch("main.WalerGlobalSolverDialog") as dialog_class:
                app._open_waler_global_solver()

        confirm.assert_not_called()
        dialog_class.assert_not_called()
        app.make_waler_global_optimizer.assert_not_called()
        app._apply_waler_global_result.assert_not_called()
        self.assertEqual(app.result_items, {"old": {}})
        app.show_result.assert_called_once()

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
        review_relink_source = inspect.getsource(
            SupportInputApp._relink_paused_dxf_review
        )
        review_adoption_source = inspect.getsource(
            SupportInputApp._adopt_paused_review_relink
        )
        relink_presentation_source = (
            relink_source + review_relink_source + review_adoption_source
        )

        self.assertNotIn(
            "DxfAssetManager",
            save_source + load_source + relink_presentation_source,
        )
        self.assertNotIn("ProjectSerializer", load_source)
        self.assertNotIn("DxfCompatibilityChecker", relink_presentation_source)
        self.assertNotIn(".compare(", relink_presentation_source)
        self.assertNotIn(".merge_source_references(", relink_presentation_source)
        self.assertNotIn("source_file_fingerprint", relink_presentation_source)
        self.assertNotIn("review_state_matches_source", relink_presentation_source)
        self.assertNotIn(".sha256", relink_presentation_source)

    def test_project_ui_delegates_project_application_workflows(self):
        dxf_apply_source = inspect.getsource(
            SupportInputApp._complete_dxf_review
        )
        payload_build_source = inspect.getsource(
            SupportInputApp._build_project_payload
        )
        hydration_source = inspect.getsource(
            SupportInputApp._apply_project_payload
        )
        global_apply_source = inspect.getsource(
            SupportInputApp._apply_waler_global_result
        )

        self.assertNotIn(".to_project_rows(", dxf_apply_source)
        self.assertNotIn("ProjectDataModel(", dxf_apply_source)
        self.assertNotIn('"schema_version"', payload_build_source)
        self.assertNotIn('"best_solution"', hydration_source)
        self.assertNotIn("selected_id_set", global_apply_source)
        self.assertIn("stage_dxf_review_apply", dxf_apply_source)
        self.assertIn("build_project_payload", payload_build_source)
        self.assertIn("hydrate_project", hydration_source)
        self.assertIn("stage_waler_global_result", global_apply_source)

    def test_support_plan_editor_delegates_engineering_workflow(self):
        editor_source = inspect.getsource(
            SupportInputApp._open_support_plan_editor
        )
        adoption_source = inspect.getsource(
            SupportInputApp._adopt_support_plan_edit
        )
        breakdown_source = inspect.getsource(
            SupportInputApp._format_support_plan_breakdown
        )

        self.assertIn("editing_service.stage_edit", editor_source)
        self.assertIn("self._adopt_support_plan_edit", editor_source)
        self.assertIn("if not staged.changed", adoption_source)
        self.assertIn('item["result"] = staged.solution', adoption_source)
        self.assertNotIn('item["result"] =', editor_source)
        self.assertIn("SupportPlanEditing.analyze_plan", breakdown_source)
        for hidden_rule in (
            "evaluate_single_support",
            "configured_steel_lengths",
            "_normalize_pieces",
            "shared_layout_group",
            "support.JACK_LENGTH",
            "support.SHIM_LENGTHS",
            "support.TARGET_GAP",
        ):
            self.assertNotIn(
                hidden_rule,
                editor_source + adoption_source + breakdown_source,
            )

    def test_support_plan_no_op_does_not_adopt_or_mutate_result_state(self):
        for initial_dirty, initial_reason in (
            (False, ""),
            (True, "其他尚未儲存的修改"),
        ):
            with self.subTest(initial_dirty=initial_dirty):
                app = SupportInputApp.__new__(SupportInputApp)
                original_solution = SimpleNamespace(plans=[], valid=True)
                replacement = SimpleNamespace(plans=[], valid=False)
                item = {"type": "support", "result": original_solution}
                persisted = {"marker": "before"}
                app._project_results = ProjectResultModel(
                    result_items={"Z1": item},
                    last_calculated_time="2000-01-01T00:00:00",
                    persisted_payload=persisted,
                )
                app.project_dirty = initial_dirty
                app.project_dirty_reason = initial_reason
                app._refresh_results_tree = Mock()
                app.update_preview = Mock()
                app.results_tree = Mock()
                staged = SimpleNamespace(
                    changed=False,
                    solution=replacement,
                )

                adopted = app._adopt_support_plan_edit(
                    item,
                    staged,
                    "Z1",
                    "S1",
                )

                self.assertFalse(adopted)
                self.assertIs(item["result"], original_solution)
                self.assertEqual(
                    app.last_calculated_time,
                    "2000-01-01T00:00:00",
                )
                self.assertIs(app.project_result, persisted)
                self.assertEqual(app.project_dirty, initial_dirty)
                self.assertEqual(app.project_dirty_reason, initial_reason)
                app._refresh_results_tree.assert_not_called()
                app.update_preview.assert_not_called()
                app.results_tree.exists.assert_not_called()

    def test_support_plan_changed_result_is_adopted_even_when_invalid(self):
        app = SupportInputApp.__new__(SupportInputApp)
        original_solution = SimpleNamespace(plans=[], valid=True)
        changed_solution = SimpleNamespace(
            plans=[],
            valid=False,
            reason="人工配置不合法",
        )
        item = {"type": "support", "result": original_solution}
        app._project_results = ProjectResultModel(
            result_items={"Z1": item},
            last_calculated_time="2000-01-01T00:00:00",
            persisted_payload={"marker": "before"},
        )
        app.project_dirty = False
        app.project_dirty_reason = ""
        app._build_material_summary_payload = Mock(return_value=[])
        app._refresh_project_status_display = Mock()
        app._refresh_results_tree = Mock()
        app.update_preview = Mock()
        app.results_tree = Mock()
        app.results_tree.exists.return_value = True
        app.results_tree.parent.return_value = "support-group"
        staged = SimpleNamespace(
            changed=True,
            solution=changed_solution,
        )

        adopted = app._adopt_support_plan_edit(
            item,
            staged,
            "Z1",
            "S1",
        )

        self.assertTrue(adopted)
        self.assertIs(item["result"], changed_solution)
        self.assertNotEqual(
            app.last_calculated_time,
            "2000-01-01T00:00:00",
        )
        self.assertNotEqual(app.project_result, {"marker": "before"})
        self.assertTrue(app.project_dirty)
        self.assertEqual(app.project_dirty_reason, "成果配置已變更")
        app._refresh_results_tree.assert_called_once_with(
            selected_id="__support_plan__:Z1:S1"
        )
        app.results_tree.item.assert_called_once_with(
            "support-group",
            open=True,
        )
        app.update_preview.assert_called_once_with(preserve_view=True)

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
