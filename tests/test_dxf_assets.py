import unittest
from collections import Counter
from pathlib import Path

import ezdxf
from ezdxf import bbox


class DXFAssetTests(unittest.TestCase):
    MAIN_APPLICATION_SPEC = "SupportSolver.spec"

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
        content = (project_root / self.MAIN_APPLICATION_SPEC).read_text(
            encoding="utf-8"
        )
        self.assertIn("assets/dxf", content)

    def test_main_application_bundles_include_runtime_resources(self):
        project_root = Path(__file__).resolve().parents[1]
        content = (project_root / self.MAIN_APPLICATION_SPEC).read_text(
            encoding="utf-8"
        )
        self.assertIn("('picture', 'picture')", content)
        self.assertIn('Path(SPECPATH) / "cad_builder.lsp"', content)
        self.assertIn('Path(SPECPATH) / "project_cases"', content)

    def test_main_application_output_is_named_support_optimizer(self):
        project_root = Path(__file__).resolve().parents[1]
        content = (project_root / self.MAIN_APPLICATION_SPEC).read_text(
            encoding="utf-8"
        )
        self.assertEqual(content.count("name='SupportOptimizer'"), 2)
        self.assertIn(
            'Path(DISTPATH) / "SupportOptimizer"',
            content,
        )

    def test_only_one_pyinstaller_spec_is_kept(self):
        project_root = Path(__file__).resolve().parents[1]
        specs = sorted(path.name for path in project_root.glob("*.spec"))
        self.assertEqual(specs, [self.MAIN_APPLICATION_SPEC])


if __name__ == "__main__":
    unittest.main()
