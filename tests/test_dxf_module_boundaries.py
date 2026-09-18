import ast
import importlib
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DXF_PACKAGE = PROJECT_ROOT / "dxf_import"
PUBLIC_API = {
    "CoordinateSystem": "dxf_import.models",
    "DXFImportDialog": "dxf_import.dialog",
    "DXFImportDialogOutcome": "dxf_import.dialog",
    "DXFImportError": "dxf_import.models",
    "DXFImportResult": "dxf_import.models",
    "GeometryTolerances": "dxf_import.models",
    "import_dxf": "dxf_import.importer",
    "read_dxf_layers": "dxf_import.importer",
    "review_state_matches_source": "dxf_import.source_exclusion",
    "source_file_fingerprint": "dxf_import.source_exclusion",
}
WORKFLOW_OWNED_DIALOG_FIELDS = {
    "world_result",
    "result",
    "problem_records",
    "review_items",
    "excluded_sources",
    "double_support_decisions",
    "review_confirmations",
    "selected_origin_world",
    "coordinate_valid",
    "import_mode",
    "last_manual_replay_report",
}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def local_dxf_dependencies(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    dependencies = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level and node.module:
            dependencies.add(node.module.split(".", 1)[0])
    return dependencies


def reachable_dxf_modules(start: str) -> set[str]:
    reachable = set()
    pending = [start]
    while pending:
        module = pending.pop()
        if module in reachable:
            continue
        reachable.add(module)
        path = DXF_PACKAGE / f"{module}.py"
        if path.is_file():
            pending.extend(local_dxf_dependencies(path) - reachable)
    return reachable


def assigned_self_attributes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    attributes = set()

    def collect(target):
        if (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
        ):
            attributes.add(target.attr)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                collect(item)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                collect(target)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            collect(node.target)
    return attributes


class DXFModuleBoundaryTests(unittest.TestCase):
    def test_package_init_is_an_import_only_public_api(self):
        tree = ast.parse((DXF_PACKAGE / "__init__.py").read_text(encoding="utf-8"))
        definitions = [
            node
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.assertEqual([], definitions)

    def test_package_root_exports_only_the_stable_public_api(self):
        public_api = importlib.import_module("dxf_import")
        self.assertEqual(set(public_api.__all__), set(PUBLIC_API))
        for name, owner_name in PUBLIC_API.items():
            with self.subTest(name=name):
                owner = importlib.import_module(owner_name)
                self.assertIs(getattr(public_api, name), getattr(owner, name))

    def test_package_root_does_not_export_private_helpers(self):
        public_api = importlib.import_module("dxf_import")
        for name in (
            "_Candidate",
            "_GeometryGroup",
            "_Primitive",
            "_active_monitor_work_areas",
            "_distance",
            "_point",
            "_replace_result_member",
            "_result_members",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(public_api, name))

    def test_repository_uses_owner_modules_instead_of_package_root(self):
        offenders = []
        for path in PROJECT_ROOT.rglob("*.py"):
            if any(part in {".venv", "build", "dist"} for part in path.parts):
                continue
            if path == DXF_PACKAGE / "__init__.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == "dxf_import":
                    offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual([], offenders)

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
            "review_workflow.py",
        ):
            imports = imported_roots(DXF_PACKAGE / name)
            with self.subTest(module=name):
                self.assertTrue({"dialog", "importer"}.isdisjoint(imports))

    def test_review_workflow_has_no_presentation_dependency(self):
        reachable = reachable_dxf_modules("review_workflow")
        self.assertTrue(
            {"controllers", "dialog", "preview"}.isdisjoint(reachable)
        )

    def test_dialog_does_not_assign_workflow_owned_review_fields(self):
        assigned = assigned_self_attributes(DXF_PACKAGE / "dialog.py")
        self.assertTrue(WORKFLOW_OWNED_DIALOG_FIELDS.isdisjoint(assigned))

    def test_recognition_core_does_not_depend_on_review_or_presentation(self):
        forbidden = {"controllers", "dialog", "preview", "review_workflow"}
        for name in (
            "geometry.py",
            "models.py",
            "recognition.py",
            "candidate_points.py",
            "validation.py",
            "support_pairing.py",
            "material_recognition.py",
        ):
            dependencies = local_dxf_dependencies(DXF_PACKAGE / name)
            with self.subTest(module=name):
                self.assertTrue(forbidden.isdisjoint(dependencies))


if __name__ == "__main__":
    unittest.main()
