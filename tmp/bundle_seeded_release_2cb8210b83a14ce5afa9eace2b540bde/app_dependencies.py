"""Explicit application dependencies supplied to the Tkinter shell.

This module contains declarations only.  Concrete production objects are
created by :mod:`bootstrap`, which is the application's composition root.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, MutableMapping

from bracing_optimizer.infrastructure.cad_builder import (
    CadEventMapper,
    TempEventWatcher,
)
from bracing_optimizer.infrastructure.inventory_repository import InventoryRepository
from bracing_optimizer.infrastructure.excel_result_export import ExcelResultExporter
from bracing_optimizer.application.optimize_support_zone import OptimizeSupportZone
from bracing_optimizer.application.optimize_waler import OptimizeWaler
from bracing_optimizer.application.optimize_waler_global import OptimizeWalerGlobal
from bracing_optimizer.application.project_service import ProjectService
from bracing_optimizer.application.solver_input_builder import (
    SupportInputBuilder,
    WalerInputBuilder,
)
from bracing_optimizer.application.waler_solver_guard import WalerSolverBusyGuard


WalerOptimizerFactory = Callable[[], OptimizeWaler]
WalerGlobalOptimizerFactory = Callable[[], OptimizeWalerGlobal]
SupportOptimizerFactory = Callable[
    [MutableMapping[object, object]],
    OptimizeSupportZone,
]


@dataclass(frozen=True)
class AppDependencies:
    """Long-lived collaborators and per-operation factories used by the UI."""

    inventory_repository: InventoryRepository
    project_service: ProjectService
    support_input_builder: SupportInputBuilder
    waler_input_builder: WalerInputBuilder
    cad_event_watcher: TempEventWatcher
    cad_event_mapper: CadEventMapper
    excel_result_exporter: ExcelResultExporter
    make_waler_optimizer: WalerOptimizerFactory
    make_waler_global_optimizer: WalerGlobalOptimizerFactory
    make_support_optimizer: SupportOptimizerFactory
    default_inventory_path: Path
    project_cases_dir: Path
    waler_solver_guard: WalerSolverBusyGuard = field(
        default_factory=WalerSolverBusyGuard
    )


__all__ = [
    "AppDependencies",
    "SupportOptimizerFactory",
    "WalerGlobalOptimizerFactory",
    "WalerOptimizerFactory",
]
