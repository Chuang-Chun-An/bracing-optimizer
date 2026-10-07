from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from PIL import Image, ImageChops

import main as app_main
from tools.generate_app_icons import APP_ICON_SIZES, MASTER_SHA256, _sha256


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = PROJECT_ROOT / "assets" / "app_icon"
MASTER_PATH = PROJECT_ROOT / "Glossy Blue Ribbon Monogram with Orange Orb.png"


class AppIconAssetTests(unittest.TestCase):
    def test_assets_are_derived_from_the_approved_master(self):
        self.assertEqual(_sha256(MASTER_PATH), MASTER_SHA256)

    def test_png_sets_have_expected_sizes_and_backgrounds(self):
        for variant in ("transparent", "dark"):
            for size in APP_ICON_SIZES:
                path = ICON_DIR / f"support_optimizer_{variant}_{size}.png"
                with self.subTest(variant=variant, size=size):
                    self.assertTrue(path.is_file())
                    with Image.open(path) as image:
                        image = image.convert("RGBA")
                        self.assertEqual(image.size, (size, size))
                        alpha_extrema = image.getchannel("A").getextrema()
                        if variant == "transparent":
                            self.assertEqual(alpha_extrema[0], 0)
                            self.assertGreater(alpha_extrema[1], 0)
                        else:
                            self.assertEqual(alpha_extrema, (255, 255))

    def test_orange_orb_remains_visible_at_every_size(self):
        for size in APP_ICON_SIZES:
            path = ICON_DIR / f"support_optimizer_transparent_{size}.png"
            with self.subTest(size=size), Image.open(path) as image:
                rgba = image.convert("RGBA")
                orange_pixels = [
                    (x, y)
                    for y in range(size)
                    for x in range(size)
                    if (
                        rgba.getpixel((x, y))[0] >= 200
                        and 45 <= rgba.getpixel((x, y))[1] <= 220
                        and rgba.getpixel((x, y))[2] <= 100
                        and rgba.getpixel((x, y))[3] >= 96
                    )
                ]
                self.assertGreaterEqual(len(orange_pixels), 2)
                self.assertGreater(
                    sum(x for x, _ in orange_pixels) / len(orange_pixels),
                    size / 2,
                )
                self.assertGreater(
                    sum(y for _, y in orange_pixels) / len(orange_pixels),
                    size / 2,
                )

    def test_ico_files_contain_the_optically_sized_png_frames(self):
        expected_sizes = {(size, size) for size in APP_ICON_SIZES}
        for variant in ("transparent", "dark"):
            ico_path = ICON_DIR / f"support_optimizer_{variant}.ico"
            with self.subTest(variant=variant), Image.open(ico_path) as icon:
                self.assertEqual(set(icon.ico.sizes()), expected_sizes)
                for size in APP_ICON_SIZES:
                    ico_frame = icon.ico.getimage((size, size)).convert("RGBA")
                    png_path = ICON_DIR / f"support_optimizer_{variant}_{size}.png"
                    with Image.open(png_path) as png:
                        difference = ImageChops.difference(
                            ico_frame,
                            png.convert("RGBA"),
                        )
                        self.assertIsNone(difference.getbbox())


class AppIconIntegrationTests(unittest.TestCase):
    def test_windows_ico_is_applied_to_default_and_existing_root(self):
        root = MagicMock()

        with (
            patch.object(app_main.tk, "PhotoImage") as photo_image,
            patch.object(app_main.sys, "platform", "win32"),
        ):
            app_main._apply_application_icon(root)

        self.assertEqual(
            root.iconbitmap.call_args_list,
            [
                call(default=str(app_main.APP_ICON_ICO_PATH)),
                call(str(app_main.APP_ICON_ICO_PATH)),
            ],
        )
        root.iconphoto.assert_not_called()
        photo_image.assert_not_called()

    def test_non_windows_uses_default_iconphoto(self):
        root = MagicMock()
        photos = [object() for _ in app_main.APP_ICON_PNG_PATHS]

        with (
            patch.object(app_main.tk, "PhotoImage", side_effect=photos),
            patch.object(app_main.sys, "platform", "linux"),
        ):
            app_main._apply_application_icon(root)

        root.iconphoto.assert_called_once_with(True, *photos)
        root.iconbitmap.assert_not_called()
        self.assertEqual(root._support_optimizer_icon_photos, tuple(photos))

    def test_windows_identity_is_set_before_tk_is_created(self):
        events = []
        root = MagicMock()

        with (
            patch.object(
                app_main,
                "_set_windows_app_user_model_id",
                side_effect=lambda: events.append("app_id"),
            ),
            patch.object(
                app_main.tk,
                "Tk",
                side_effect=lambda: (events.append("tk"), root)[1],
            ),
            patch.object(
                app_main,
                "_apply_application_icon",
                side_effect=lambda _root: events.append("icon"),
            ),
            patch.object(app_main, "build_dependencies", return_value=object()),
            patch.object(app_main, "SupportInputApp"),
        ):
            app_main.main()

        self.assertEqual(events[:3], ["app_id", "tk", "icon"])


if __name__ == "__main__":
    unittest.main()
