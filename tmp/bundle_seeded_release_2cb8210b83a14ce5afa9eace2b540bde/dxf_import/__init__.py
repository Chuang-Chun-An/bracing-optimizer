"""Stable public API for the DXF import subsystem.

Implementation helpers live in their owning modules.  Keeping this facade
small prevents presentation, recognition, and review internals from becoming
accidental cross-package contracts.
"""

from dxf_import.dialog import DXFImportDialog, DXFImportDialogOutcome
from dxf_import.importer import import_dxf, read_dxf_layers
from dxf_import.models import (
    CoordinateSystem,
    DXFImportError,
    DXFImportResult,
    GeometryTolerances,
)
from dxf_import.source_exclusion import (
    review_state_matches_source,
    source_file_fingerprint,
)


__all__ = [
    "CoordinateSystem",
    "DXFImportDialog",
    "DXFImportDialogOutcome",
    "DXFImportError",
    "DXFImportResult",
    "GeometryTolerances",
    "import_dxf",
    "read_dxf_layers",
    "review_state_matches_source",
    "source_file_fingerprint",
]
