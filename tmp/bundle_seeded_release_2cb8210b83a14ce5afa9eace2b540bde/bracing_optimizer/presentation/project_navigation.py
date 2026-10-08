"""Explicit presentation outcomes for project save and navigation guards."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ProjectSaveStatus(str, Enum):
    """Terminal result of one user-facing Save or Save As attempt."""

    SAVED = "saved"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class ProjectSaveOutcome:
    """Keep cancellation distinct from persistence failure."""

    status: ProjectSaveStatus
    path: Path | None = None
    error: str = ""

    @classmethod
    def saved(cls, path: Path) -> "ProjectSaveOutcome":
        return cls(ProjectSaveStatus.SAVED, path=Path(path))

    @classmethod
    def cancelled(cls) -> "ProjectSaveOutcome":
        return cls(ProjectSaveStatus.CANCELLED)

    @classmethod
    def failed(cls, error: object) -> "ProjectSaveOutcome":
        return cls(ProjectSaveStatus.FAILED, error=str(error))


class NavigationGuardOutcome(str, Enum):
    """Whether a requested destructive destination may continue."""

    PROCEED = "proceed"
    CANCELLED = "cancelled"


__all__ = [
    "NavigationGuardOutcome",
    "ProjectSaveOutcome",
    "ProjectSaveStatus",
]
