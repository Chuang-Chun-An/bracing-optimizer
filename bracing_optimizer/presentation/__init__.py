"""Tkinter presentation layer and compatibility exports."""

from .dialogs.selection_dialogs import (
    WalerSelectionDialog,
    ZoningSelectionDialog,
)
from .dialogs.solver_dialog_base import (
    SolverDialogThreadBridge,
    TextRedirector,
)
from .dialogs.support_solver_dialog import SupportSolverDialog
from .dialogs.waler_solver_dialog import WalerSolverDialog
from .result_formatters import (
    format_result_list,
    format_result_value,
    format_waler_score_breakdown,
)
from .widgets.preview_toolbar import PreviewNavigationToolbar


__all__ = [
    "PreviewNavigationToolbar",
    "SolverDialogThreadBridge",
    "SupportSolverDialog",
    "TextRedirector",
    "WalerSelectionDialog",
    "WalerSolverDialog",
    "ZoningSelectionDialog",
    "format_result_list",
    "format_result_value",
    "format_waler_score_breakdown",
]
