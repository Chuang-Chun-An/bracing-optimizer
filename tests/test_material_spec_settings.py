import unittest
from unittest.mock import patch

from main import SupportInputApp
from bracing_optimizer.application.project_data import (
    DEFAULT_MATERIAL_SPECS,
    ProjectDataModel,
    TABLE_COLUMNS,
)
from bracing_optimizer.application.solver_input_builder import SupportInputBuilder


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
        app.numeric_columns = {}
        app.editing_entry = None
        app.treeviews = {}
        app._refresh_tree = lambda _table_name: None
        app._update_material_summary = lambda: None
        app._handle_input_data_changed = lambda **_kwargs: None
        return app

    def test_tree_item_index_uses_final_underscore_segment(self):
        app = SupportInputApp.__new__(SupportInputApp)
        self.assertEqual(app._item_id_to_index("inventory_12"), 12)
        self.assertEqual(app._item_id_to_index("material_specs_12"), 12)
        self.assertIsNone(app._item_id_to_index("material_specs_bad"))

    def test_material_references_are_scoped_by_usage(self):
        app = self.editable_app()

        references = app._material_spec_references("支撐", "h350X350")

        self.assertEqual(references["inventory"], [0])
        self.assertEqual(references["struts"], [0])
        self.assertEqual(references["walers"], [])

    def test_material_rename_updates_same_usage_references_only(self):
        app = self.editable_app()

        references = app._rename_material_spec_references(
            "支撐",
            "H350x350",
            "H350x350A",
        )

        self.assertEqual(app.inventory[0]["Spec"], "H350x350A")
        self.assertEqual(app.struts[0]["material_spec"], "H350x350A")
        self.assertEqual(app.inventory[1]["Spec"], "H350x350")
        self.assertEqual(app.walers[0]["material_spec"], "H350x350")
        self.assertEqual(app._material_spec_reference_count(references), 2)

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
        self.assertEqual(changes[0]["table_name"], None)
        self.assertEqual(set(refreshed), {"inventory", "struts"})

    def test_cancelled_material_rename_changes_nothing(self):
        app = self.editable_app()
        tree = self.FakeTree()
        app.treeviews = {"material_specs": tree}

        with patch("main.messagebox.askyesno", return_value=False):
            app._finish_edit(
                tree,
                "material_specs_1",
                "Spec",
                self.FakeEditor("H350x350A"),
            )

        self.assertEqual(app.material_specs[1]["Spec"], "H350x350")
        self.assertEqual(app.inventory[0]["Spec"], "H350x350")
        self.assertEqual(app.struts[0]["material_spec"], "H350x350")

    def test_referenced_material_usage_cannot_be_changed(self):
        app = self.editable_app()
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
        warning.assert_called_once()

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
        warning.assert_called_once()

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
