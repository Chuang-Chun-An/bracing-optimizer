import unittest
from collections import Counter
from pathlib import Path
import subprocess

import ezdxf
from ezdxf import bbox

from bootstrap import build_project_service
from bracing_optimizer.infrastructure.project_persistence import DxfStatus
from tests.release_project_assets import (
    RELEASE_PROJECT_CASE_DIRS,
    RELEASE_PROJECT_CASE_NAMES,
    RELEASE_PROJECT_DIR,
    RELEASE_PROJECT_RELATIVE_FILES,
)
from tests.sample_dxf_assets import (
    SAMPLE_DXF_DIR,
    SAMPLE_DXF_FILENAMES,
    SAMPLE_DXF_PATHS,
)


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

    def test_sample_dxf_sources_are_an_exact_readable_allowlist(self):
        project_root = Path(__file__).resolve().parents[1]
        actual_names = {
            path.name
            for path in SAMPLE_DXF_DIR.iterdir()
            if path.is_file()
        }

        self.assertEqual(SAMPLE_DXF_FILENAMES, actual_names)
        for path in SAMPLE_DXF_PATHS:
            with self.subTest(path=path.name):
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                document = ezdxf.readfile(path)
                self.assertTrue(document.dxfversion)
                self.assertFalse((project_root / path.name).exists())

        fixture_copies = {
            path.name
            for path in (project_root / "tests" / "fixtures").rglob("*.dxf")
        }
        self.assertTrue(SAMPLE_DXF_FILENAMES.isdisjoint(fixture_copies))

    def test_release_project_sources_are_an_exact_loadable_allowlist(self):
        actual_case_names = tuple(
            sorted(path.name for path in RELEASE_PROJECT_DIR.iterdir())
        )
        self.assertEqual(RELEASE_PROJECT_CASE_NAMES, actual_case_names)

        project_service = build_project_service()
        for case_dir in RELEASE_PROJECT_CASE_DIRS:
            with self.subTest(project=case_dir.name):
                self.assertTrue(case_dir.is_dir())
                contents = tuple(case_dir.rglob("*"))
                self.assertTrue(all(not path.is_symlink() for path in contents))
                relative_files = {
                    path.relative_to(case_dir).as_posix()
                    for path in contents
                    if path.is_file()
                }
                self.assertEqual(RELEASE_PROJECT_RELATIVE_FILES, relative_files)

                project_path = case_dir / "project.json"
                managed_dxf_path = case_dir / "source" / "source.dxf"
                document = ezdxf.readfile(managed_dxf_path)
                self.assertTrue(document.dxfversion)

                loaded = project_service.load_project(project_path)
                self.assertEqual(3, loaded.payload["schema_version"])
                self.assertEqual(DxfStatus.READY, loaded.dxf_status_report.status)
                self.assertIsNotNone(loaded.dxf_status_report.active_source)
                self.assertEqual(
                    managed_dxf_path.resolve(),
                    loaded.dxf_status_report.active_source.path,
                )

    def test_runtime_project_directory_is_ignored_and_has_no_tracked_fixtures(self):
        project_root = Path(__file__).resolve().parents[1]
        tracked = subprocess.run(
            [
                "git",
                "-c",
                "core.quotepath=false",
                "ls-files",
                "-z",
                "--",
                "project_cases",
                "test_cases",
            ],
            cwd=project_root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        ignored = subprocess.run(
            [
                "git",
                "check-ignore",
                "--no-index",
                "project_cases/runtime-project/project.json",
            ],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        release_asset_ignored = subprocess.run(
            [
                "git",
                "check-ignore",
                "--no-index",
                (
                    "assets/project_cases/"
                    "Y05車站第一層支撐/project.json"
                ),
            ],
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        tracked_existing = [
            relative_path
            for relative_path in tracked.stdout.split("\0")
            if relative_path and (project_root / relative_path).exists()
        ]
        self.assertEqual([], tracked_existing)
        self.assertEqual(0, ignored.returncode, ignored.stderr)
        self.assertEqual(1, release_asset_ignored.returncode)
        self.assertEqual(
            [],
            list((project_root / "tests" / "fixtures").rglob("project.json")),
        )

    def test_main_application_bundles_include_the_jack_asset(self):
        project_root = Path(__file__).resolve().parents[1]
        content = (project_root / self.MAIN_APPLICATION_SPEC).read_text(
            encoding="utf-8"
        )
        self.assertIn("assets/dxf", content)

    def test_main_application_bundles_only_runtime_and_sample_resources(self):
        project_root = Path(__file__).resolve().parents[1]
        content = (project_root / self.MAIN_APPLICATION_SPEC).read_text(
            encoding="utf-8"
        )
        for required in (
            "('data', 'data')",
            "('picture', 'picture')",
            "('assets/dxf', 'assets/dxf')",
            "('assets/software_history.json', 'assets')",
            'Path(SPECPATH) / "cad_builder.lsp"',
            'output_dir / "sample_dxf"',
            'Path(SPECPATH) / "assets" / "project_cases"',
            'output_dir / "project_cases"',
        ):
            with self.subTest(required=required):
                self.assertIn(required, content)

        for filename in SAMPLE_DXF_FILENAMES:
            with self.subTest(filename=filename):
                self.assertEqual(1, content.count(filename))

        for case_name in RELEASE_PROJECT_CASE_NAMES:
            with self.subTest(project=case_name):
                self.assertEqual(
                    1,
                    content.count(f'Path("{case_name}") / "project.json"'),
                )
                self.assertEqual(
                    1,
                    content.count(
                        f'Path("{case_name}") / "source" / "source.dxf"'
                    ),
                )

        for forbidden in (
            'Path(SPECPATH) / "project_cases"',
            'Path(SPECPATH) / "test_cases"',
            'Path(SPECPATH) / "tests" / "fixtures"',
            "docs/DEVELOPMENT_HISTORY.md",
            "('docs', 'docs')",
            "shutil.copytree(",
            "project.json.bak",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, content)

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
