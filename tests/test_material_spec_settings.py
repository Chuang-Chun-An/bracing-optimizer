import unittest
from unittest.mock import patch

from main import SupportInputApp
from bracing_optimizer.application.material_spec_editing import (
    MaterialSpecEditError,
    MaterialSpecEditOperation,
    MaterialSpecEditOutcome,
    MaterialSpecEditRequest,
    MaterialSpecEditStatus,
    MaterialSpecEditing,
    ReferenceSummary,
)
from bracing_optimizer.application.project_data import (
    DEFAULT_MATERIAL_SPECS,
    ProjectDataModel,
    TABLE_COLUMNS,
)
from bracing_optimizer.application.solver_input_builder import SupportInputBuilder
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.project_service import ProjectService


class MaterialSpecSettingsTests(unittest.TestCase):
    class FakeTree:
        def __init__(self, selection=()):
            self.values = {}
            self._selection = tuple(selection)

        def set(self, row_id, column, value=None):
            if value is None:
                return self.values.get((row_id, column), "")
            self.values[(row_id, column)] = value

        def selection(self):
            return self._selection

    class FakeEditor:
        def __init__(self, value):
            self.value = value
            self.destroyed = False

        def winfo_exists(self):
            return not self.destroyed

        def get(self):
            return self.value

        def destroy(self):
            self.destroyed = True

    @staticmethod
    def editable_app():
        app = SupportInputApp.__new__(SupportInputApp)
        app.project_data = ProjectDataModel(
            walers=[{"WalerID": "W1", "material_spec": "H350x350"}],
            struts=[{"StrutID": "S1", "material_spec": "H350x350"}],
            inventory=[
                {
                    "ItemCode": "S1",
                    "Usage": "支撐",
                    "Spec": "H350x350",
                    "Length": 4500,
                    "Qty": 1,
                },
                {
                    "ItemCode": "W1",
                    "Usage": "圍令",
                    "Spec": "H350x350",
                    "Length": 8000,
                    "Qty": 1,
                },
            ],
            material_specs=[
                {"Usage": "支撐", "Spec": "H350x350"},
                {"Usage": "圍令", "Spec": "H350x350"},
            ],
        )
        app.root = object()
        app._project_results = ProjectResultModel()
        app.solver_memory = {}
        app.support_candidate_cache = {}
        app._material_spec_editing = MaterialSpecEditing(
            ProjectService.plan_input_change
        )
        app.numeric_columns = {}
        app.editing_entry = None
        app.treeviews = {}
        app._refresh_tree = lambda _table_name: None
        app._update_material_summary = lambda: None
        app._refresh_results_tree = lambda: None
        app._mark_project_dirty = lambda _reason: None
        app.update_preview = lambda **_kwargs: None
        app._handle_input_data_changed = lambda **_kwargs: None
        return app

    def test_tree_item_index_uses_final_underscore_segment(self):
        app = SupportInputApp.__new__(SupportInputApp)
        self.assertEqual(app._item_id_to_index("inventory_12"), 12)
        self.assertEqual(app._item_id_to_index("material_specs_12"), 12)
        self.assertIsNone(app._item_id_to_index("material_specs_bad"))

    def test_material_references_are_scoped_by_usage(self):
        app = self.editable_app()

        references = app._ensure_material_spec_editing()._references(
            app.project_data,
            "支撐",
            "h350X350",
        )

        self.assertEqual(references.inventory, (0,))
        self.assertEqual(references.struts, (0,))
        self.assertEqual(references.walers, ())

    def test_material_rename_updates_same_usage_references_only(self):
        app = self.editable_app()

        confirmation = app._ensure_material_spec_editing().stage(
            app.project_data,
            app._project_results,
            MaterialSpecEditRequest(
                operation=MaterialSpecEditOperation.EDIT,
                row_index=1,
                expected_usage="支撐",
                expected_spec="H350x350",
                field_name="Spec",
                proposed_value="H350x350A",
            ),
        )
        outcome = app._ensure_material_spec_editing().stage(
            app.project_data,
            app._project_results,
            MaterialSpecEditRequest(
                operation=MaterialSpecEditOperation.EDIT,
                row_index=1,
                expected_usage="支撐",
                expected_spec="H350x350",
                field_name="Spec",
                proposed_value="H350x350A",
                allow_reference_sync=True,
                expected_references=confirmation.references,
            ),
        )
        staged = outcome.project_data

        self.assertEqual(staged.inventory[0]["Spec"], "H350x350A")
        self.assertEqual(staged.struts[0]["material_spec"], "H350x350A")
        self.assertEqual(staged.inventory[1]["Spec"], "H350x350")
        self.assertEqual(staged.walers[0]["material_spec"], "H350x350")
        self.assertEqual(outcome.references.count, 2)

    def test_confirmed_material_rename_invalidates_solver_and_updates_rows(self):
        app = self.editable_app()
        tree = self.FakeTree()
        app.treeviews = {"material_specs": tree}
        changes = []
        refreshed = []
        app._handle_input_data_changed = lambda **kwargs: changes.append(kwargs)
        app._refresh_tree = lambda table_name: refreshed.append(table_name)

        with patch("main.messagebox.askyesno", return_value=True):
            app._finish_edit(
                tree,
                "material_specs_1",
                "Spec",
                self.FakeEditor("H350x350A"),
            )

        self.assertEqual(app.material_specs[1]["Spec"], "H350x350A")
        self.assertEqual(app.inventory[0]["Spec"], "H350x350A")
        self.assertEqual(app.struts[0]["material_spec"], "H350x350A")
        self.assertEqual(app.inventory[1]["Spec"], "H350x350")
        self.assertEqual(app.walers[0]["material_spec"], "H350x350")
        self.assertEqual(changes, [])
        self.assertEqual(set(refreshed), {"inventory", "struts"})
        self.assertTrue(app.project_dirty)
        self.assertEqual(app.project_dirty_reason, "輸入資料已變更")

    def test_cancelled_material_rename_changes_nothing(self):
        app = self.editable_app()
        tree = self.FakeTree()
        app.treeviews = {"material_specs": tree}

        changes = []
        app._handle_input_data_changed = lambda **kwargs: changes.append(kwargs)

        with patch("main.messagebox.askyesno", return_value=False) as confirm:
            app._finish_edit(
                tree,
                "material_specs_1",
                "Spec",
                self.FakeEditor("H350x350A"),
            )

        self.assertEqual(app.material_specs[1]["Spec"], "H350x350")
        self.assertEqual(app.inventory[0]["Spec"], "H350x350")
        self.assertEqual(app.struts[0]["material_spec"], "H350x350")
        confirm.assert_called_once_with(
            "同步更新材料規格",
            (
                "材料規格「H350x350」目前正在被引用。\n\n"
                "庫存：1 筆\n圍令：0 筆\n支撐：1 筆\n\n"
                "是否同步更新為「H350x350A」？"
            ),
            parent=app.root,
        )
        self.assertEqual(changes, [])

    def test_referenced_material_usage_cannot_be_changed(self):
        app = self.editable_app()
        app.material_specs = [
            {"Usage": "圍令", "Spec": "RC"},
            {"Usage": "支撐", "Spec": "H350x350"},
        ]
        tree = self.FakeTree()
        app.treeviews = {"material_specs": tree}

        with patch("main.messagebox.showwarning") as warning:
            app._finish_edit(
                tree,
                "material_specs_1",
                "Usage",
                self.FakeEditor("圍令"),
            )

        self.assertEqual(app.material_specs[1]["Usage"], "支撐")
        warning.assert_called_once_with(
            "用途不可變更",
            (
                "材料規格「H350x350」仍被使用，不可直接變更用途。\n\n"
                "庫存：1 筆\n圍令：0 筆\n支撐：1 筆\n\n"
                "請先移除或更換引用。"
            ),
            parent=app.root,
        )

    def test_duplicate_material_spec_warning_is_characterized(self):
        app = self.editable_app()
        app.material_specs.append({"Usage": "支撐", "Spec": "H400x400"})
        tree = self.FakeTree()
        app.treeviews = {"material_specs": tree}

        with patch("main.messagebox.showwarning") as warning:
            app._finish_edit(
                tree,
                "material_specs_1",
                "Spec",
                self.FakeEditor("H400x400"),
            )

        warning.assert_called_once_with(
            "規格重複",
            "支撐的材料規格「H400x400」已存在。",
            parent=app.root,
        )
        self.assertEqual(app.material_specs[1]["Spec"], "H350x350")

    def test_blank_material_spec_warning_is_characterized(self):
        app = self.editable_app()
        tree = self.FakeTree()
        app.treeviews = {"material_specs": tree}

        with patch("main.messagebox.showwarning") as warning:
            app._finish_edit(
                tree,
                "material_specs_1",
                "Spec",
                self.FakeEditor(""),
            )

        warning.assert_called_once_with(
            "材料規格不可空白",
            "既有材料規格不可改為空白。",
            parent=app.root,
        )
        self.assertEqual(app.material_specs[1]["Spec"], "H350x350")

    def test_inventory_usage_change_clears_incompatible_spec(self):
        app = self.editable_app()
        tree = self.FakeTree()
        app.treeviews = {"inventory": tree}

        app._finish_edit(
            tree,
            "inventory_0",
            "Usage",
            self.FakeEditor("圍令"),
        )

        self.assertEqual(app.inventory[0]["Usage"], "圍令")
        # This example exists for both usages, so it remains valid.
        self.assertEqual(app.inventory[0]["Spec"], "H350x350")

        app.material_specs = [
            {"Usage": "圍令", "Spec": "RC"},
            {"Usage": "支撐", "Spec": "H350x350"},
        ]
        app.inventory[0]["Usage"] = "支撐"
        app._finish_edit(
            tree,
            "inventory_0",
            "Usage",
            self.FakeEditor("圍令"),
        )
        self.assertEqual(app.inventory[0]["Spec"], "")
        self.assertEqual(tree.values[("inventory_0", "Spec")], "")

    def test_referenced_material_spec_cannot_be_deleted(self):
        app = self.editable_app()
        tree = self.FakeTree(("material_specs_1",))
        app.treeviews = {"material_specs": tree}
        app.current_table = "material_specs"

        with patch("main.messagebox.showwarning") as warning:
            app.delete_row()

        self.assertEqual(len(app.material_specs), 3)  # required RC + two test rows
        warning.assert_called_once_with(
            "材料規格仍被使用",
            (
                "材料規格「H350x350」仍被使用。\n\n"
                "庫存：1 筆\n圍令：0 筆\n支撐：1 筆\n\n"
                "請先移除或更換引用後再刪除。"
            ),
            parent=app.root,
        )

    def test_unreferenced_material_spec_can_be_deleted(self):
        app = self.editable_app()
        app.material_specs.append({"Usage": "支撐", "Spec": "H500x500"})
        tree = self.FakeTree(("material_specs_3",))
        app.treeviews = {"material_specs": tree}
        app.current_table = "material_specs"

        app.delete_row()

        self.assertFalse(
            any(row["Spec"] == "H500x500" for row in app.material_specs)
        )

    def test_every_material_spec_error_code_has_a_main_display_mapping(self):
        app = self.editable_app()
        references = ReferenceSummary(inventory=(0,), struts=(0,))

        with (
            patch("main.messagebox.showwarning") as warning,
            patch("main.messagebox.showinfo") as info,
            patch("main.messagebox.askyesno") as confirmation,
        ):
            for code in MaterialSpecEditError:
                with self.subTest(code=code.value):
                    app._show_material_spec_edit_error(
                        MaterialSpecEditOutcome(
                            status=MaterialSpecEditStatus.REJECTED,
                            error_code=code,
                            references=references,
                            display_args={
                                "usage": "支撐",
                                "spec": "H350x350",
                                "operation": "edit",
                            },
                        )
                    )

        self.assertEqual(
            warning.call_count + info.call_count,
            len(MaterialSpecEditError),
        )
        confirmation.assert_not_called()
        defensive_titles = [
            call.args[0]
            for call in warning.call_args_list[:3]
        ]
        self.assertEqual(defensive_titles, ["輸入錯誤"] * 3)

    def test_material_spec_adoption_applies_result_and_cache_effects(self):
        app = self.editable_app()
        app._project_results = ProjectResultModel(
            result_items={"old": {"type": "waler", "result": {}}},
            persisted_payload={"best_solution": {}},
        )
        app.solver_memory = {"old": object()}
        app.support_candidate_cache = {"old": object()}
        dirty = []
        previews = []
        app._mark_project_dirty = lambda reason: dirty.append(reason)
        app.update_preview = lambda **kwargs: previews.append(kwargs)
        app._handle_input_data_changed = (
            SupportInputApp._handle_input_data_changed.__get__(
                app,
                SupportInputApp,
            )
        )

        request = MaterialSpecEditRequest(
            operation=MaterialSpecEditOperation.EDIT,
            row_index=1,
            expected_usage="支撐",
            expected_spec="H350x350",
            field_name="Spec",
            proposed_value="H350x350A",
        )
        first = app._ensure_material_spec_editing().stage(
            app.project_data,
            app._project_results,
            request,
        )
        outcome = app._ensure_material_spec_editing().stage(
            app.project_data,
            app._project_results,
            MaterialSpecEditRequest(
                **{
                    **request.__dict__,
                    "allow_reference_sync": True,
                    "expected_references": first.references,
                }
            ),
        )

        app._adopt_material_spec_edit(outcome)

        self.assertEqual(app._project_results.result_items, {})
        self.assertEqual(app.solver_memory, {})
        self.assertEqual(app.support_candidate_cache, {})
        self.assertEqual(dirty, [])
        self.assertTrue(app.project_dirty)
        self.assertEqual(app.project_dirty_reason, "輸入資料已變更")
        self.assertEqual(previews, [{"preserve_view": True}])

    def test_unreferenced_material_spec_adoption_preserves_results_and_marks_dirty(self):
        app = self.editable_app()
        original_results = ProjectResultModel(
            result_items={"old": {"type": "waler", "result": {}}},
            persisted_payload={"best_solution": {}},
        )
        app._project_results = original_results
        dirty = []
        app._mark_project_dirty = lambda reason: dirty.append(reason)
        app._handle_input_data_changed = (
            SupportInputApp._handle_input_data_changed.__get__(
                app,
                SupportInputApp,
            )
        )
        app.project_data.material_specs.append(
            {"Usage": "支撐", "Spec": "H500x500"}
        )
        outcome = app._ensure_material_spec_editing().stage(
            app.project_data,
            original_results,
            MaterialSpecEditRequest(
                operation=MaterialSpecEditOperation.DELETE,
                row_index=3,
                expected_usage="支撐",
                expected_spec="H500x500",
            ),
        )

        app._adopt_material_spec_edit(outcome)

        self.assertEqual(app._project_results, original_results)
        self.assertIsNot(app._project_results, original_results)
        self.assertEqual(dirty, [])
        self.assertTrue(app.project_dirty)
        self.assertEqual(app.project_dirty_reason, "輸入資料已變更")

    def test_material_spec_adoption_replaces_caches_and_keeps_commit_on_ui_failure(self):
        class FailingClearDict(dict):
            def clear(self):
                super().clear()
                raise RuntimeError("clear failed")

        app = self.editable_app()
        app._project_results = ProjectResultModel(
            result_items={"old": {"type": "waler", "result": {}}}
        )
        first = app._ensure_material_spec_editing().stage(
            app.project_data,
            app._project_results,
            MaterialSpecEditRequest(
                operation=MaterialSpecEditOperation.EDIT,
                row_index=1,
                expected_usage="支撐",
                expected_spec="H350x350",
                field_name="Spec",
                proposed_value="H350x350A",
            ),
        )
        invalidating = app._ensure_material_spec_editing().stage(
            app.project_data,
            app._project_results,
            MaterialSpecEditRequest(
                operation=MaterialSpecEditOperation.EDIT,
                row_index=1,
                expected_usage="支撐",
                expected_spec="H350x350",
                field_name="Spec",
                proposed_value="H350x350A",
                allow_reference_sync=True,
                expected_references=first.references,
            ),
        )
        original_data = app.project_data
        original_results = app._project_results
        app.solver_memory = FailingClearDict(old=1)
        app.support_candidate_cache = {"old": 1}

        old_solver_memory = app.solver_memory
        app._adopt_material_spec_edit(invalidating)

        self.assertIs(app.project_data, invalidating.project_data)
        self.assertIs(app._project_results, invalidating.project_results)
        self.assertIsNot(app.project_data, original_data)
        self.assertIsNot(app._project_results, original_results)
        self.assertEqual(old_solver_memory, {"old": 1})
        self.assertEqual(app.solver_memory, {})
        self.assertEqual(app.support_candidate_cache, {})

        app = self.editable_app()
        app.project_data.material_specs.append(
            {"Usage": "支撐", "Spec": "H500x500"}
        )
        staged = app._ensure_material_spec_editing().stage(
            app.project_data,
            app._project_results,
            MaterialSpecEditRequest(
                operation=MaterialSpecEditOperation.DELETE,
                row_index=3,
                expected_usage="支撐",
                expected_spec="H500x500",
            ),
        )
        app._refresh_tree = lambda _table: (_ for _ in ()).throw(
            RuntimeError("refresh failed")
        )

        with self.assertRaisesRegex(RuntimeError, "refresh failed"):
            app._adopt_material_spec_edit(staged)

        self.assertIs(app.project_data, staged.project_data)
        self.assertIs(app._project_results, staged.project_results)
        self.assertTrue(app.projection_stale)

    def test_material_spec_table_has_no_length_and_is_persisted_separately(self):
        model = ProjectDataModel(
            inventory=[{"Length": 4500, "Qty": 2}],
            material_specs=[{"Usage": "支撐", "Spec": "H350x350"}],
        )

        payload = model.to_case_data()

        self.assertEqual(TABLE_COLUMNS["material_specs"], ("Usage", "Spec"))
        self.assertNotIn("Length", TABLE_COLUMNS["material_specs"])
        self.assertNotIn("WalerType", TABLE_COLUMNS["walers"])
        self.assertEqual(TABLE_COLUMNS["walers"].count("material_spec"), 1)
        self.assertEqual(payload["inventory"][0]["Length"], 4500)
        self.assertEqual(payload["inventory"][0]["Qty"], 2)
        self.assertIn({"Usage": "支撐", "Spec": "H350x350"}, payload["material_specs"])
        self.assertIn({"Usage": "圍令", "Spec": "RC"}, payload["material_specs"])

    def test_legacy_project_gets_default_material_specs(self):
        model = ProjectDataModel(material_specs=DEFAULT_MATERIAL_SPECS)
        self.assertIn({"Usage": "圍令", "Spec": "RC"}, model.material_specs)

    def test_support_input_builder_derives_waler_type_from_material_spec(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.project_data = ProjectDataModel(
            walers=[
                {"WalerID": "W1", "material_spec": "RC"},
                {"WalerID": "W2", "material_spec": "H350x350"},
            ],
            struts=[{
                "StrutID": "S1",
                "FromWaler": "W1",
                "ToWaler": "W2",
                "StartX": 0,
                "StartY": 0,
                "EndX": 9700,
                "EndY": 0,
                "Zoning": "Z1",
                "material_spec": "H350x350",
            }],
            inventory=[
                {"Spec": "H350x350", "Usage": "支撐", "Length": 4500, "Qty": 0},
                {"Spec": "H350x350", "Usage": "支撐", "Length": 5000, "Qty": 8},
            ],
            material_specs=[
                {"Usage": "支撐", "Spec": "H350x350"},
                {"Usage": "圍令", "Spec": "RC"},
            ],
        )

        result = SupportInputBuilder().build_zone(app.project_data, "Z1").configs

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].from_waler_type, "RC")
        self.assertEqual(result[0].to_waler_type, "Steel")
        self.assertEqual(result[0].steel_lengths, [4500, 5000])

    def test_material_catalog_does_not_invalidate_solver_but_selected_spec_does(self):
        app = SupportInputApp.__new__(SupportInputApp)
        invalidations = []
        app._invalidate_solver_state_after_input_change = lambda: invalidations.append(True)
        app._mark_project_dirty = lambda _reason: None
        app.update_preview = lambda **_kwargs: None
        app._update_material_summary = lambda: None

        app._handle_input_data_changed(table_name="material_specs")
        app._handle_input_data_changed(
            table_name="struts",
            field_name="material_spec",
        )
        self.assertEqual(len(invalidations), 1)

    def test_waler_spec_and_inventory_changes_do_invalidate_solver(self):
        app = SupportInputApp.__new__(SupportInputApp)
        invalidations = []
        app._invalidate_solver_state_after_input_change = lambda: invalidations.append(True)
        app._mark_project_dirty = lambda _reason: None
        app.update_preview = lambda **_kwargs: None
        app._update_material_summary = lambda: None

        app._handle_input_data_changed(
            table_name="walers",
            field_name="material_spec",
        )
        app._handle_input_data_changed(table_name="inventory")

        self.assertEqual(len(invalidations), 2)

    def test_rc_material_spec_is_always_restored(self):
        model = ProjectDataModel(material_specs=[])
        self.assertEqual(model.material_specs, [{"Usage": "圍令", "Spec": "RC"}])


if __name__ == "__main__":
    unittest.main()
