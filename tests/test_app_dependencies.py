import inspect
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
from bracing_optimizer.application.optimize_support_zone import OptimizeSupportZone
from bracing_optimizer.application.optimize_waler import OptimizeWaler
from bracing_optimizer.application.optimize_waler_global import OptimizeWalerGlobal
from bracing_optimizer.application.project_service import ProjectService
from bracing_optimizer.application.solver_input_builder import (
    SupportInputBuilder,
    WalerInputBuilder,
)
from bracing_optimizer.application.waler_solver_guard import WalerSolverBusyGuard
from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfCompatibilityChecker,
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
