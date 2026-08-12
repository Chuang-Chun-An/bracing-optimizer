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


if __name__ == "__main__":
    unittest.main()
