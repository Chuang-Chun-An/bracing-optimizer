"""Tkinter presentation layer and compatibility exports."""

from .dialogs.selection_dialogs import (
    WalerSelectionDialog,
    ZoningSelectionDialog,
)
from .dialogs.software_information_dialog import SoftwareInformationDialog
from .dialogs.project_selection_dialog import ProjectSelectionDialog
from .dialogs.solver_dialog_base import (
    SolverDialogThreadBridge,
    TextRedirector,
)
from .dialogs.support_solver_dialog import SupportSolverDialog
from .dialogs.waler_solver_dialog import WalerSolverDialog
from .dialogs.waler_global_solver_dialog import WalerGlobalSolverDialog
from .result_formatters import (
    format_result_list,
    format_result_value,
    format_waler_score_breakdown,
)
from .widgets.preview_toolbar import PreviewNavigationToolbar


__all__ = [
    "PreviewNavigationToolbar",
    "ProjectSelectionDialog",
    "SolverDialogThreadBridge",
    "SoftwareInformationDialog",
    "SupportSolverDialog",
    "TextRedirector",
    "WalerSelectionDialog",
    "WalerGlobalSolverDialog",
    "WalerSolverDialog",
    "ZoningSelectionDialog",
    "format_result_list",
    "format_result_value",
    "format_waler_score_breakdown",
]
