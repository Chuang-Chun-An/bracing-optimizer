import unittest
from types import SimpleNamespace

from main import SupportInputApp


class InterfacePresentationTests(unittest.TestCase):
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
