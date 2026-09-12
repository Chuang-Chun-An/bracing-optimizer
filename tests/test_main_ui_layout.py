import inspect
import unittest
from unittest.mock import patch

from main import SupportInputApp, SupportSolverDialog
from window_layout import responsive_dialog_geometry


class _GeometryRoot:
    def __init__(self):
        self.value = ""

    def geometry(self, value=None):
        if value is not None:
            self.value = value
        return self.value


class MainUILayoutTests(unittest.TestCase):
    class _Notebook:
        def __init__(self, selected_text):
            self.selected_text = selected_text

        def select(self):
            return "selected"

        def tab(self, _tab_id, option):
            if option == "text":
                return self.selected_text
            raise KeyError(option)

    def test_default_geometry_fits_a_1366_by_728_work_area(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = _GeometryRoot()

        with patch(
            "main._active_monitor_work_areas",
            return_value=((0, 0, 1366, 728),),
        ):
            geometry = app._default_main_window_geometry()

        self.assertEqual(geometry, "1229x655+68+36")

    def test_support_dialog_reserves_room_for_window_chrome_on_768p(self):
        geometry = responsive_dialog_geometry(
            900,
            720,
            ((0, 0, 1366, 728),),
        )

        self.assertEqual(geometry, "900x656+233+36")

    def test_support_editor_uses_the_monitor_containing_its_parent(self):
        geometry = responsive_dialog_geometry(
            780,
            760,
            ((0, 0, 1366, 728), (1366, 0, 3286, 1040)),
            anchor_geometry="1200x800+1500+80",
        )

        self.assertEqual(geometry, "780x760+1936+140")

    def test_both_support_windows_apply_the_responsive_geometry(self):
        solver_source = inspect.getsource(SupportSolverDialog.__init__)
        editor_source = inspect.getsource(
            SupportInputApp._open_support_plan_editor
        )

        self.assertIn("configure_responsive_dialog", solver_source)
        self.assertIn("configure_responsive_dialog", editor_source)
        self.assertLess(
            editor_source.index('footer_frame.pack(side="bottom"'),
            editor_source.index("status_var ="),
        )

    def test_main_action_row_is_reserved_below_the_expanding_workspace(self):
        source = inspect.getsource(SupportInputApp._build_ui)

        self.assertIn('side="bottom"', source)
        self.assertIn("before=self.main_paned", source)

    def test_restore_moves_remembered_window_back_from_missing_monitor(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = _GeometryRoot()
        app.main_ui_state = {"geometry": "1600x900+3000+100"}

        with patch(
            "main._active_monitor_work_areas",
            return_value=((0, 0, 1366, 728),),
        ):
            geometry = app._restore_main_window_geometry()

        self.assertEqual(geometry, "1366x728+0+0")
        self.assertEqual(app.root.value, geometry)

    def test_invalid_saved_sash_ratio_falls_back_to_sixty_percent(self):
        class Paned:
            def __init__(self):
                self.position = None

            def winfo_width(self):
                return 1000

            def sashpos(self, _index, position):
                self.position = position

        app = SupportInputApp.__new__(SupportInputApp)
        app.main_ui_state = {"main_sash_ratio": "invalid"}
        app.main_paned = Paned()

        app._restore_main_paned_position()

        self.assertEqual(app.main_paned.position, 600)

    def test_nested_workspace_selection_resolves_the_active_table(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.workspace_tab_labels = {
            "engineering": "工程配置",
            "materials": "材料設定",
            "analysis": "分析結果",
        }
        app.table_tab_labels = {
            "struts": "支撐",
            "walers": "圍令",
            "braces": "斜撐",
            "material_specs": "材料規格",
            "inventory": "機料庫存",
        }
        app.notebook = self._Notebook("工程配置")
        app.engineering_notebook = self._Notebook("支撐")
        app.materials_notebook = self._Notebook("材料規格")

        self.assertEqual(app._sync_current_table_from_active_tabs(), "struts")

        app.notebook.selected_text = "材料設定"
        self.assertEqual(
            app._sync_current_table_from_active_tabs(),
            "material_specs",
        )

        app.notebook.selected_text = "分析結果"
        self.assertIsNone(app._sync_current_table_from_active_tabs())


if __name__ == "__main__":
    unittest.main()
