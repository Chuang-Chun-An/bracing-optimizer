import inspect
import shutil
import tempfile
import unittest
from pathlib import Path

from app_dependencies import AppDependencies
from bootstrap import build_dependencies
from bracing_optimizer.infrastructure.cad_builder import (
    CadEventMapper,
    TempEventWatcher,
)
from bracing_optimizer.infrastructure.inventory_repository import (
    InMemoryInventoryRepository,
)
from bracing_optimizer.infrastructure.excel_result_export import (
    ExcelResultExporter,
)
from main import SupportInputApp, SupportSolverDialog, WalerSolverDialog
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.optimize_support_zone import OptimizeSupportZone
from bracing_optimizer.application.optimize_waler import OptimizeWaler
from bracing_optimizer.application.optimize_waler_global import OptimizeWalerGlobal
from bracing_optimizer.application.project_service import (
    BuildProjectPayloadRequest,
    ProjectService,
    SaveProjectRequest,
)
from bracing_optimizer.application.solver_input_builder import (
    SupportInputBuilder,
    WalerInputBuilder,
)
from bracing_optimizer.application.waler_solver_guard import WalerSolverBusyGuard
from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfCompatibilityChecker,
    DxfWorkflowStatus,
)
from tests.release_project_assets import (
    RELEASE_PROJECT_CASE_DIRS,
    RELEASE_PROJECT_CASE_NAMES,
    RELEASE_PROJECT_RELATIVE_FILES,
)


class ApplicationDependencyTests(unittest.TestCase):
    def test_bootstrap_builds_one_coherent_dependency_graph(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dependencies = build_dependencies(
                resource_dir=root,
                app_dir=root / "application",
            )

        self.assertIsInstance(dependencies, AppDependencies)
        self.assertIsInstance(
            dependencies.project_service.dxf_asset_manager,
            DxfAssetManager,
        )
        self.assertIsInstance(
            dependencies.project_service.dxf_compatibility_checker,
            DxfCompatibilityChecker,
        )
        self.assertEqual(
            dependencies.default_inventory_path,
            root / "data" / "inventory.json",
        )
        self.assertEqual(
            dependencies.project_cases_dir,
            root / "application" / "project_cases",
        )
        self.assertIsInstance(
            dependencies.excel_result_exporter,
            ExcelResultExporter,
        )
        self.assertIsInstance(
            dependencies.waler_solver_guard,
            WalerSolverBusyGuard,
        )

    def test_optimizer_factories_respect_operation_lifetimes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dependencies = build_dependencies(
                resource_dir=temp_dir,
                app_dir=temp_dir,
            )
            first_waler = dependencies.make_waler_optimizer()
            second_waler = dependencies.make_waler_optimizer()
            global_waler = dependencies.make_waler_global_optimizer()
            cache = {}
            support_optimizer = dependencies.make_support_optimizer(cache)

        self.assertIsInstance(first_waler, OptimizeWaler)
        self.assertIsInstance(second_waler, OptimizeWaler)
        self.assertIsNot(first_waler, second_waler)
        self.assertIsInstance(global_waler, OptimizeWalerGlobal)
        self.assertIsInstance(support_optimizer, OptimizeSupportZone)
        self.assertIs(support_optimizer.candidate_cache, cache)

    def test_missing_runtime_project_directory_is_created_and_can_save(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dependencies = build_dependencies(
                resource_dir=root,
                app_dir=root / "application",
            )
            project_root = dependencies.project_cases_dir
            self.assertFalse(project_root.exists())

            app = SupportInputApp.__new__(SupportInputApp)
            app.project_cases_dir = project_root
            self.assertEqual([], SupportInputApp._project_case_json_files(app))
            self.assertTrue(project_root.is_dir())

            project_path = SupportInputApp._managed_project_case_path(
                app,
                "first-project",
            )
            project_data = ProjectDataModel()
            project_results = ProjectResultModel()
            payload = dependencies.project_service.build_project_payload(
                BuildProjectPayloadRequest(
                    project_name="first-project",
                    project_data=project_data,
                    project_results=project_results,
                    workflow_status=DxfWorkflowStatus.NONE,
                    dxf_import_state=None,
                    dxf_asset=None,
                )
            )
            saved = dependencies.project_service.save_project(
                SaveProjectRequest(
                    project_path=project_path,
                    payload=payload,
                    current_project_path=None,
                    existing_asset=None,
                    import_state=None,
                    current_dxf_report=None,
                    has_solver_result=False,
                )
            )

            self.assertEqual(project_path.resolve(), saved.project_path)
            self.assertTrue(project_path.is_file())
            self.assertEqual(
                [project_path],
                SupportInputApp._project_case_json_files(app),
            )

    def test_packaged_release_projects_are_listed_and_loadable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_dir = root / "application"
            packaged_project_root = app_dir / "project_cases"
            for source_case_dir in RELEASE_PROJECT_CASE_DIRS:
                destination_case_dir = packaged_project_root / source_case_dir.name
                for relative_file in RELEASE_PROJECT_RELATIVE_FILES:
                    source_path = source_case_dir / relative_file
                    destination_path = destination_case_dir / relative_file
                    destination_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, destination_path)

            dependencies = build_dependencies(
                resource_dir=root / "resources",
                app_dir=app_dir,
            )
            app = SupportInputApp.__new__(SupportInputApp)
            app.project_cases_dir = dependencies.project_cases_dir

            project_paths = SupportInputApp._project_case_json_files(app)
            self.assertEqual(
                list(RELEASE_PROJECT_CASE_NAMES),
                [path.parent.name for path in project_paths],
            )
            for project_path in project_paths:
                with self.subTest(project=project_path.parent.name):
                    loaded = dependencies.project_service.load_project(project_path)
                    self.assertEqual(project_path.resolve(), loaded.project_path)
                    self.assertEqual(
                        project_path.parent / "source" / "source.dxf",
                        loaded.dxf_status_report.active_source.path,
                    )

            shutil.rmtree(packaged_project_root / RELEASE_PROJECT_CASE_NAMES[0])
            self.assertEqual(
                [RELEASE_PROJECT_CASE_NAMES[1]],
                [
                    path.parent.name
                    for path in SupportInputApp._project_case_json_files(app)
                ],
            )

    def test_support_input_app_attaches_injected_collaborators_by_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manager = DxfAssetManager()
            checker = DxfCompatibilityChecker()
            project_service = ProjectService(manager, checker)
            inventory = InMemoryInventoryRepository([])
            support_builder = SupportInputBuilder()
            waler_builder = WalerInputBuilder()
            watcher = TempEventWatcher(root / "cad-event.json")
            mapper = CadEventMapper()
            excel_exporter = ExcelResultExporter()
            dependencies = AppDependencies(
                inventory_repository=inventory,
                project_service=project_service,
                support_input_builder=support_builder,
                waler_input_builder=waler_builder,
                cad_event_watcher=watcher,
                cad_event_mapper=mapper,
                excel_result_exporter=excel_exporter,
                make_waler_optimizer=OptimizeWaler,
                make_waler_global_optimizer=lambda: OptimizeWalerGlobal(
                    OptimizeWaler
                ),
                make_support_optimizer=lambda cache: OptimizeSupportZone(cache),
                default_inventory_path=root / "inventory.json",
                project_cases_dir=root / "projects",
            )
            app = SupportInputApp.__new__(SupportInputApp)
            app._apply_dependencies(dependencies)

        self.assertIs(app.inventory_repository, inventory)
        self.assertIs(app.project_service, project_service)
        self.assertIs(app.dxf_asset_manager, manager)
        self.assertIs(app.dxf_compatibility_checker, checker)
        self.assertIs(app.support_input_builder, support_builder)
        self.assertIs(app.waler_input_builder, waler_builder)
        self.assertIs(app.cad_event_watcher, watcher)
        self.assertIs(app.cad_event_mapper, mapper)
        self.assertIs(app.excel_result_exporter, excel_exporter)
        self.assertIs(
            app.waler_solver_guard,
            dependencies.waler_solver_guard,
        )
        self.assertIs(
            app.make_waler_global_optimizer,
            dependencies.make_waler_global_optimizer,
        )

    def test_app_constructor_no_longer_constructs_concrete_services(self):
        source = inspect.getsource(SupportInputApp.__init__)

        for constructor in (
            "JsonInventoryRepository(",
            "DxfAssetManager(",
            "DxfCompatibilityChecker(",
            "TempEventWatcher(",
            "CadEventMapper(",
            "SupportInputBuilder(",
            "WalerInputBuilder(",
        ):
            self.assertNotIn(constructor, source)

    def test_solver_dialogs_require_injected_optimizers(self):
        support_source = inspect.getsource(SupportSolverDialog.__init__)
        waler_source = inspect.getsource(WalerSolverDialog.__init__)

        self.assertNotIn("OptimizeSupportZone(", support_source)
        self.assertNotIn("OptimizeWaler(", waler_source)
        self.assertNotIn("optimize_support_zone=None", support_source)
        self.assertNotIn("optimize_waler=None", waler_source)


if __name__ == "__main__":
    unittest.main()
