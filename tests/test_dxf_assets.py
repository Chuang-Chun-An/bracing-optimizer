import unittest
from collections import Counter
from pathlib import Path

import ezdxf
from ezdxf import bbox


class DXFAssetTests(unittest.TestCase):
    def test_jack_symbol_is_a_physical_size_reusable_block(self):
        asset_path = (
            Path(__file__).resolve().parents[1]
            / "assets"
            / "dxf"
            / "jack_symbol.dxf"
        )
        document = ezdxf.readfile(asset_path)
        block = document.blocks.get("SUPPORT_JACK")
        extents = bbox.extents(block)

        self.assertEqual(document.header["$INSUNITS"], 4)
        self.assertEqual(
            Counter(entity.dxftype() for entity in block),
            {"LINE": 71, "CIRCLE": 1},
        )
        self.assertTrue(all(entity.dxf.layer == "0" for entity in block))
        self.assertAlmostEqual(extents.extmin.x, 0.0, places=6)
        self.assertAlmostEqual(extents.extmin.y, -150.0, places=6)
        self.assertAlmostEqual(extents.extmax.x, 600.0, places=6)
        self.assertAlmostEqual(extents.extmax.y, 150.0, places=6)

    def test_main_application_bundles_include_the_jack_asset(self):
        project_root = Path(__file__).resolve().parents[1]
        for filename in (
            "main.spec",
            "SupportSolver.spec",
            "SupportOptimizer.spec",
        ):
            content = (project_root / filename).read_text(encoding="utf-8")
            with self.subTest(spec=filename):
                self.assertIn("assets/dxf", content)


if __name__ == "__main__":
    unittest.main()
