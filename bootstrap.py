"""Production composition root for Support Distribution UV."""

from __future__ import annotations

import sys
from pathlib import Path

from app_dependencies import AppDependencies
from bracing_optimizer.infrastructure.cad_builder import (
    DEFAULT_TEMP_PATH,
    CadEventMapper,
    TempEventWatcher,
)
from bracing_optimizer.infrastructure.inventory_repository import (
    JsonInventoryRepository,
)
from bracing_optimizer.infrastructure.excel_result_export import (
    ExcelResultExporter,
)
from bracing_optimizer.application.optimize_support_zone import OptimizeSupportZone
from bracing_optimizer.application.optimize_waler import OptimizeWaler
from bracing_optimizer.application.optimize_waler_global import OptimizeWalerGlobal
from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfCompatibilityChecker,
)
from bracing_optimizer.application.project_service import ProjectService
from bracing_optimizer.application.solver_input_builder import (
    SupportInputBuilder,
    WalerInputBuilder,
)
from bracing_optimizer.application.waler_solver_guard import WalerSolverBusyGuard


RESOURCE_DIR = Path(__file__).resolve().parent


def application_dir(resource_dir: Path = RESOURCE_DIR) -> Path:
    return (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(resource_dir)
    )


def build_project_service(
    dxf_asset_manager: DxfAssetManager | None = None,
    dxf_compatibility_checker: DxfCompatibilityChecker | None = None,
) -> ProjectService:
    """Build a project service with one internally consistent component pair."""

    return ProjectService(
        dxf_asset_manager or DxfAssetManager(),
        dxf_compatibility_checker or DxfCompatibilityChecker(),
    )


def build_dependencies(
    *,
    resource_dir: str | Path = RESOURCE_DIR,
    app_dir: str | Path | None = None,
) -> AppDependencies:
    """Create one coherent production dependency graph for an application."""

    resource_path = Path(resource_dir).resolve()
    app_path = (
        Path(app_dir).resolve()
        if app_dir is not None
        else application_dir(resource_path)
    )
    inventory_path = resource_path / "data" / "inventory.json"

    project_service = build_project_service()
    waler_solver_guard = WalerSolverBusyGuard()

    return AppDependencies(
        inventory_repository=JsonInventoryRepository(inventory_path),
        project_service=project_service,
        support_input_builder=SupportInputBuilder(),
        waler_input_builder=WalerInputBuilder(),
        cad_event_watcher=TempEventWatcher(DEFAULT_TEMP_PATH),
        cad_event_mapper=CadEventMapper(),
        excel_result_exporter=ExcelResultExporter(),
        make_waler_optimizer=OptimizeWaler,
        make_waler_global_optimizer=lambda: OptimizeWalerGlobal(OptimizeWaler),
        make_support_optimizer=lambda cache: OptimizeSupportZone(cache),
        default_inventory_path=inventory_path,
        project_cases_dir=app_path / "project_cases",
        waler_solver_guard=waler_solver_guard,
    )


__all__ = ["application_dir", "build_dependencies", "build_project_service"]
