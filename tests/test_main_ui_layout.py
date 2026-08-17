import unittest
from unittest.mock import patch

from main import SupportInputApp


class _GeometryRoot:
    def __init__(self):
        self.value = ""

    def geometry(self, value=None):
        if value is not None:
            self.value = value
        return self.value


class MainUILayoutTests(unittest.TestCase):
    def test_default_geometry_fits_a_1366_by_728_work_area(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = _GeometryRoot()

        with patch(
            "main._active_monitor_work_areas",
            return_value=((0, 0, 1366, 728),),
        ):
            geometry = app._default_main_window_geometry()

        self.assertEqual(geometry, "1229x655+68+36")

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


if __name__ == "__main__":
    unittest.main()
