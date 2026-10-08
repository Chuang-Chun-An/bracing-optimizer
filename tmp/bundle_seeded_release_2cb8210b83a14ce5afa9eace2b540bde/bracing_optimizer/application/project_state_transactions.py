"""Typed application outcomes for replacing committed project state.

The outcome is deliberately data-only.  Presentation owns the final reference
swap and all widget projection after that swap.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel


@dataclass(frozen=True)
class ProjectStateMutationOutcome:
    """One complete set of references and scalar metadata to commit."""

    project_data: ProjectDataModel
    project_results: ProjectResultModel
    solver_memory: dict
    support_candidate_cache: dict
    dxf_workflow_status: Any
    dxf_review_session: Any
    dxf_last_import_debug: Any
    dxf_asset: Any
    dxf_asset_status_report: Any
    last_dxf_compatibility_report: Any
    last_dxf_recovery_summary: Any
    last_cad_validation_report: Any
    current_project_path: Path | None
    project_dirty: bool
    project_dirty_reason: str


@dataclass(frozen=True)
class CadEventMutationOutcome:
    """Staged CAD event plus the complete runtime state it will commit."""

    runtime_state: ProjectStateMutationOutcome | None
    table_name: str
    committed_index: int
    committed_row: dict[str, Any]
    binding_synced: bool = False
    binding_report: Any = None
    validation_report: Any = None
    no_op: bool = False


__all__ = ["CadEventMutationOutcome", "ProjectStateMutationOutcome"]
