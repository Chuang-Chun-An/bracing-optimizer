import ast
import importlib
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DXF_PACKAGE = PROJECT_ROOT / "dxf_import"


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


class DXFModuleBoundaryTests(unittest.TestCase):
    def test_package_init_is_an_import_only_public_api(self):
        tree = ast.parse((DXF_PACKAGE / "__init__.py").read_text(encoding="utf-8"))
        definitions = [
            node
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual([], definitions)

    def test_public_api_points_to_owning_modules(self):
        public_api = importlib.import_module("dxf_import")
        expected_owners = {
            "Waler": "dxf_import.models",
            "outline_centerline": "dxf_import.recognition",
            "build_candidate_points": "dxf_import.candidate_points",
            "build_validation_overview": "dxf_import.validation",
            "DXFImporter": "dxf_import.importer",
            "PreviewRenderer": "dxf_import.preview",
            "ImportModelController": "dxf_import.controllers",
            "DXFImportDialog": "dxf_import.dialog",
        }
        for name, owner_name in expected_owners.items():
            with self.subTest(name=name):
                owner = importlib.import_module(owner_name)
                self.assertIs(getattr(public_api, name), getattr(owner, name))

    def test_tkinter_is_confined_to_dialog_module(self):
        for path in DXF_PACKAGE.glob("*.py"):
            if path.name in {"dialog.py"}:
                continue
            with self.subTest(module=path.name):
                self.assertNotIn("tkinter", imported_roots(path))

    def test_ezdxf_is_confined_to_importer_module(self):
        for path in DXF_PACKAGE.glob("*.py"):
            if path.name == "importer.py":
                continue
            with self.subTest(module=path.name):
                self.assertNotIn("ezdxf", imported_roots(path))

    def test_core_modules_do_not_depend_on_dialog_or_importer(self):
        for name in (
            "geometry.py",
            "models.py",
            "recognition.py",
            "candidate_points.py",
            "validation.py",
        ):
            imports = imported_roots(DXF_PACKAGE / name)
            with self.subTest(module=name):
                self.assertTrue({"dialog", "importer"}.isdisjoint(imports))


if __name__ == "__main__":
    unittest.main()
