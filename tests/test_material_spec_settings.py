import unittest

from main import SupportInputApp
from project_data import DEFAULT_MATERIAL_SPECS, ProjectDataModel, TABLE_COLUMNS


class MaterialSpecSettingsTests(unittest.TestCase):
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
        self.assertEqual(payload["inventory"], [{"Length": 4500, "Qty": 2}])
        self.assertEqual(
            payload["material_specs"],
            [{"Usage": "支撐", "Spec": "H350x350"}],
        )

    def test_legacy_project_gets_default_material_specs(self):
        model = ProjectDataModel(material_specs=DEFAULT_MATERIAL_SPECS)
        self.assertIn({"Usage": "圍令", "Spec": "RC"}, model.material_specs)

    def test_build_support_inputs_uses_explicit_waler_type_and_inventory_lengths(self):
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
                {"Length": 4500, "Qty": 0},
                {"Length": 5000, "Qty": 8},
            ],
            material_specs=[
                {"Usage": "支撐", "Spec": "H350x350"},
                {"Usage": "圍令", "Spec": "RC"},
            ],
        )

        result = app.build_support_inputs("Z1")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].from_waler_type, "RC")
        self.assertEqual(result[0].to_waler_type, "Steel")
        self.assertEqual(result[0].steel_lengths, [4500, 5000])

    def test_material_catalog_and_support_spec_do_not_invalidate_solver(self):
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
        self.assertEqual(invalidations, [])

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

    def test_legacy_waler_type_rc_migrates_to_the_single_material_spec_field(self):
        model = ProjectDataModel(walers=[{
            "WalerID": "W1",
            "WalerType": "RC",
            "material_spec": "",
        }])

        self.assertEqual(model.walers[0]["material_spec"], "RC")
        self.assertNotIn("WalerType", model.walers[0])


if __name__ == "__main__":
    unittest.main()
