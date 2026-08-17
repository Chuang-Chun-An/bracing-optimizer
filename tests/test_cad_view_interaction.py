import unittest

from cad_view_interaction import CADViewInteractionController, CADViewport
from main import PreviewNavigationToolbar, SupportInputApp


class CADViewInteractionControllerTests(unittest.TestCase):
    def test_button_contract_reserves_left_for_selection_and_middle_for_pan(self):
        controller = CADViewInteractionController()
        self.assertTrue(controller.is_select_button(1))
        self.assertFalse(controller.is_pan_button(1))
        self.assertTrue(controller.is_pan_button(2))

    def test_pan_handles_tk_and_matplotlib_y_axis_directions(self):
        controller = CADViewInteractionController()
        controller.begin_pan((100, 100), (0, 1000, 0, 1000))
        tk_bounds = controller.pan_to(
            (200, 150),
            (1.0, 1.0),
            y_axis_screen_down=True,
        )
        self.assertEqual(tk_bounds, (-100, 900, 50, 1050))
        mpl_bounds = controller.pan_to(
            (200, 150),
            (1.0, 1.0),
            y_axis_screen_down=False,
        )
        self.assertEqual(mpl_bounds, (-100, 900, -50, 950))

    def test_zoom_keeps_cursor_anchor_fixed(self):
        bounds = CADViewInteractionController.zoom_bounds(
            (0, 1000, 0, 1000),
            (250, 750),
            0.8,
        )
        self.assertEqual(bounds, (50, 850, 150, 950))

    def test_pixel_hit_tests_are_scale_independent(self):
        self.assertEqual(
            CADViewInteractionController.nearest_segment(
                (50, 7),
                (("S1", (0, 0), (100, 0)),),
                8,
            ),
            "S1",
        )
        self.assertEqual(
            CADViewInteractionController.point_hits(
                (100, 100),
                (("P1", (104, 100)), ("P2", (106, 100))),
                8,
            ),
            ("P1", "P2"),
        )

    def test_viewport_expands_thin_local_content_to_canvas_aspect(self):
        viewport = CADViewport(canvas_width=1000, canvas_height=500)
        bounds = viewport.fit((0, 100, 0, 1000))

        self.assertEqual(bounds, (-950, 1050, 0, 1000))
        self.assertTrue(viewport.intersects(((900, 500),)))
        self.assertEqual(viewport.data_to_screen((-950, 1000)), (0, 0))
        self.assertEqual(viewport.data_to_screen((1050, 0)), (1000, 500))

    def test_viewport_repeated_zoom_keeps_cursor_data_anchor_fixed(self):
        viewport = CADViewport(canvas_width=1000, canvas_height=500, margin=50)
        viewport.fit((0, 100, 0, 1000))
        cursor = (760.0, 140.0)
        anchor = viewport.screen_to_data(cursor)

        for _index in range(8):
            viewport.zoom_at_screen(cursor, 0.8)
            projected = viewport.data_to_screen(anchor)
            self.assertAlmostEqual(projected[0], cursor[0])
            self.assertAlmostEqual(projected[1], cursor[1])

        for _index in range(8):
            viewport.zoom_at_screen(cursor, 1.25)
            projected = viewport.data_to_screen(anchor)
            self.assertAlmostEqual(projected[0], cursor[0])
            self.assertAlmostEqual(projected[1], cursor[1])

    def test_viewport_resize_preserves_center_and_data_scale(self):
        viewport = CADViewport(canvas_width=1000, canvas_height=500, margin=50)
        viewport.fit((0, 100, 0, 1000))
        original_center = (
            (viewport.view_bounds[0] + viewport.view_bounds[1]) / 2,
            (viewport.view_bounds[2] + viewport.view_bounds[3]) / 2,
        )
        original_scale = viewport.scale

        viewport.configure(1400, 800, 50)

        resized_center = (
            (viewport.view_bounds[0] + viewport.view_bounds[1]) / 2,
            (viewport.view_bounds[2] + viewport.view_bounds[3]) / 2,
        )
        self.assertEqual(resized_center, original_center)
        self.assertAlmostEqual(viewport.scale, original_scale)

    def test_main_preview_has_no_left_button_pan_toolbar_mode(self):
        labels = {item[0] for item in PreviewNavigationToolbar.toolitems}
        self.assertNotIn("平移", labels)
        self.assertTrue(callable(SupportInputApp._on_preview_button_press))
        self.assertTrue(callable(SupportInputApp._on_preview_motion))
        self.assertTrue(callable(SupportInputApp._on_preview_button_release))

    def test_main_preview_draws_blue_overlay_for_selected_strut(self):
        class Artist:
            def remove(self):
                pass

        class Axes:
            def __init__(self):
                self.plot_calls = []

            def plot(self, *args, **kwargs):
                self.plot_calls.append((args, kwargs))
                return (Artist(),)

        app = SupportInputApp.__new__(SupportInputApp)
        app.ax = Axes()
        app._preview_selection_overlay = []
        app._preview_selected_key = "strut:S1"
        app._preview_selection_targets = [{
            "key": "strut:S1",
            "kind": "strut",
            "geometry": "segment",
            "start": (0.0, 0.0),
            "end": (1000.0, 0.0),
        }]

        app._draw_preview_selection_highlight()

        self.assertEqual(len(app._preview_selection_overlay), 1)
        self.assertEqual(app.ax.plot_calls[0][1]["color"], "#1565c0")
        self.assertEqual(app.ax.plot_calls[0][1]["linewidth"], 7)

    def test_blank_preview_click_clears_all_geometry_table_selections(self):
        class Tree:
            def __init__(self, selected):
                self.selected = list(selected)

            def selection(self):
                return tuple(self.selected)

            def selection_remove(self, *items):
                self.selected = [item for item in self.selected if item not in items]

        class Toolbar:
            def __init__(self):
                self.message = ""

            def set_message(self, message):
                self.message = message

        class Canvas:
            def __init__(self):
                self.draw_count = 0

            def draw_idle(self):
                self.draw_count += 1

        app = SupportInputApp.__new__(SupportInputApp)
        app.treeviews = {
            "walers": Tree(("walers_0",)),
            "struts": Tree(("struts_1",)),
            "braces": Tree(("braces_2",)),
        }
        app.preview_toolbar = Toolbar()
        app.canvas = Canvas()
        app._preview_selected_key = "strut:S2"
        app._draw_preview_selection_highlight = lambda: None

        app._select_preview_target(None)

        self.assertEqual(app._preview_selected_key, "")
        self.assertTrue(
            all(not tree.selection() for tree in app.treeviews.values())
        )
        self.assertEqual(
            app.preview_toolbar.message,
            "左鍵選取｜中鍵平移｜滾輪縮放",
        )
        self.assertEqual(app.canvas.draw_count, 1)

    def test_waler_and_brace_tree_selection_use_shared_preview_sync(self):
        class SelectedTree:
            def __init__(self, item_id):
                self.item_id = item_id

            def selection(self):
                return (self.item_id,)

        app = SupportInputApp.__new__(SupportInputApp)
        app.treeviews = {
            "walers": SelectedTree("walers_2"),
            "braces": SelectedTree("braces_4"),
        }
        calls = []
        app._sync_preview_to_geometry_selection = (
            lambda table_name, kind, index: calls.append(
                (table_name, kind, index)
            )
        )

        app._on_geometry_tree_select("walers")
        app._on_geometry_tree_select("braces")

        self.assertEqual(
            calls,
            [
                ("walers", "waler", 2),
                ("braces", "brace", 4),
            ],
        )

    def test_preview_waler_and_brace_clicks_navigate_to_matching_rows(self):
        class Notebook:
            labels = {"w": "圍令", "b": "斜撐"}

            def __init__(self):
                self.selected = []

            def tabs(self):
                return tuple(self.labels)

            def tab(self, tab_id, option):
                self.assert_option(option)
                return self.labels[tab_id]

            @staticmethod
            def assert_option(option):
                if option != "text":
                    raise AssertionError(option)

            def select(self, tab_id):
                self.selected.append(tab_id)

        class Toolbar:
            def set_message(self, _message):
                pass

        class Canvas:
            def draw_idle(self):
                pass

        app = SupportInputApp.__new__(SupportInputApp)
        app.treeviews = {"walers": object(), "braces": object()}
        app.table_tab_labels = {"walers": "圍令", "braces": "斜撐"}
        app.notebook = Notebook()
        app.preview_toolbar = Toolbar()
        app.canvas = Canvas()
        app._draw_preview_selection_highlight = lambda: None
        selected_rows = []
        app._select_input_row = (
            lambda table_name, row_index: selected_rows.append(
                (table_name, row_index)
            )
        )

        app._select_preview_target({
            "key": "waler:W2",
            "kind": "waler",
            "identifier": "W2",
            "table_name": "walers",
            "row_index": 1,
        })
        app._select_preview_target({
            "key": "brace:B4",
            "kind": "brace",
            "identifier": "B4",
            "table_name": "braces",
            "row_index": 3,
        })

        self.assertEqual(selected_rows, [("walers", 1), ("braces", 3)])
        self.assertEqual(app.notebook.selected, ["w", "b"])


if __name__ == "__main__":
    unittest.main()
