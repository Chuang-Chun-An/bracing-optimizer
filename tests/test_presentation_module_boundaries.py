import ast
import unittest
from pathlib import Path

import main
from bracing_optimizer import presentation


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOVED_CLASS_NAMES = {
    "PreviewNavigationToolbar",
    "SolverDialogThreadBridge",
    "SupportSolverDialog",
    "TextRedirector",
    "WalerSelectionDialog",
    "WalerGlobalSolverDialog",
    "WalerSolverDialog",
    "ZoningSelectionDialog",
}


def imported_roots(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


class PresentationModuleBoundaryTests(unittest.TestCase):
    def test_moved_presentation_modules_do_not_import_main(self):
        module_paths = sorted(
            (PROJECT_ROOT / "bracing_optimizer" / "presentation").rglob("*.py")
        )

        for module_path in module_paths:
            with self.subTest(module=module_path.name):
                self.assertNotIn("main", imported_roots(module_path))

    def test_main_reexports_moved_classes_for_compatibility(self):
        for class_name in MOVED_CLASS_NAMES:
            with self.subTest(class_name=class_name):
                self.assertIs(
                    getattr(main, class_name),
                    getattr(presentation, class_name),
                )

    def test_main_no_longer_defines_moved_classes(self):
        tree = ast.parse((PROJECT_ROOT / "main.py").read_text(encoding="utf-8"))
        defined_classes = {
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef)
        }

        self.assertTrue(MOVED_CLASS_NAMES.isdisjoint(defined_classes))


if __name__ == "__main__":
    unittest.main()
