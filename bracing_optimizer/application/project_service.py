"""Application service for the project save, load, and DXF relink workflows.

The service coordinates persistence components and returns data-only outcomes.
It deliberately has no Tkinter dependency; callers own file dialogs, user
confirmation, application-state mutation, and presentation.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfAssetStatusReport,
    DxfCompatibilityChecker,
    DxfCompatibilityReport,
    DxfStatus,
    ProjectPersistenceError,
    ProjectSerializer,
)


@dataclass(frozen=True)
class SaveProjectRequest:
    project_path: Path
    payload: Mapping[str, Any]
    current_project_path: Path | None
    existing_asset: Mapping[str, Any] | None
    import_state: Mapping[str, Any] | None
    current_dxf_report: DxfAssetStatusReport | None
    has_solver_result: bool


@dataclass(frozen=True)
class SaveProjectResult:
    project_path: Path
    payload: dict[str, Any]
    dxf_asset: dict[str, Any] | None
    dxf_status_report: DxfAssetStatusReport


@dataclass(frozen=True)
class LoadProjectResult:
    project_path: Path
    payload: dict[str, Any]
    dxf_status_report: DxfAssetStatusReport
    legacy_no_state: bool


@dataclass(frozen=True)
class RelinkDxfRequest:
    candidate_path: Path
    saved_state: Mapping[str, Any] | None
    existing_asset: Mapping[str, Any] | None
    current_dxf_report: DxfAssetStatusReport | None
    project_rows: Mapping[str, Any]
    candidate_state: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class RelinkDxfResult:
    accepted: bool
    relinked_state: dict[str, Any] | None
    dxf_status_report: DxfAssetStatusReport
    compatibility_report: DxfCompatibilityReport | None
    summary: str
    detail_lines: tuple[str, ...]


class ProjectService:
    """Coordinate project persistence without depending on GUI state."""

    def __init__(
        self,
        dxf_asset_manager: DxfAssetManager | None = None,
        dxf_compatibility_checker: DxfCompatibilityChecker | None = None,
    ) -> None:
        self.dxf_asset_manager = dxf_asset_manager or DxfAssetManager()
        self.dxf_compatibility_checker = (
            dxf_compatibility_checker or DxfCompatibilityChecker()
        )

    def inspect_dxf_state(
        self,
        project_path: str | Path | None,
        dxf_asset: Mapping[str, Any] | None,
        import_state: Mapping[str, Any] | None,
        *,
        has_solver_result: bool = False,
        legacy_no_state: bool = False,
        repair: bool = False,
    ) -> DxfAssetStatusReport:
        """Expose DXF status inspection through the project boundary."""

        return self.dxf_asset_manager.inspect(
            project_path,
            dxf_asset,
            import_state,
            has_solver_result=has_solver_result,
            legacy_no_state=legacy_no_state,
            repair=repair,
        )

    def runtime_dxf_report(self, source_path: str | Path) -> DxfAssetStatusReport:
        """Describe a DXF imported into memory before the project is saved."""

        return self.dxf_asset_manager.runtime_report(source_path)

    def save_project(self, request: SaveProjectRequest) -> SaveProjectResult:
        path = Path(request.project_path).resolve()
        active_source = self._active_dxf_source_for_save(request)
        is_save_as = (
            request.current_project_path is not None
            and Path(request.current_project_path).resolve() != path
        )
        if is_save_as and request.existing_asset is not None and active_source is None:
            raise ProjectPersistenceError(
                "另存新專案失敗",
                "目前 DXF 管理副本不可用，請先重新連結 DXF，避免建立不完整的新專案。",
            )

        persistence_result = self.dxf_asset_manager.save_project(
            path,
            request.payload,
            active_source=active_source,
            existing_asset=request.existing_asset,
        )
        saved_payload = copy.deepcopy(dict(request.payload))
        saved_payload["dxf_asset"] = copy.deepcopy(persistence_result.dxf_asset)
        status = self.dxf_asset_manager.inspect(
            persistence_result.project_path,
            persistence_result.dxf_asset,
            request.import_state,
            has_solver_result=request.has_solver_result,
            repair=False,
        )
        return SaveProjectResult(
            project_path=persistence_result.project_path,
            payload=saved_payload,
            dxf_asset=copy.deepcopy(persistence_result.dxf_asset),
            dxf_status_report=status,
        )

    def _active_dxf_source_for_save(self, request: SaveProjectRequest):
        report = request.current_dxf_report
        if report is not None and report.active_source is not None:
            return report.active_source

        state = request.import_state
        if request.existing_asset is None and isinstance(state, Mapping):
            source_text = str(state.get("source_path", "") or "")
            source_path = Path(source_text) if source_text else None
            if source_path is not None and source_path.is_file():
                # Saving is the migration point for a legacy unmanaged source.
                return self.dxf_asset_manager.verified_source(
                    source_path,
                    DxfStatus.RUNTIME_READY,
                    original_path=source_path,
                )
        return None

    def load_project(self, project_path: str | Path) -> LoadProjectResult:
        path = Path(project_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"找不到專案：{path}")

        payload = json.loads(path.read_text(encoding="utf-8"))
        legacy_no_state = (
            "dxf_asset" not in payload
            and not isinstance(payload.get("dxf_import_state"), dict)
        )
        ProjectSerializer.validate(payload)
        status = self.dxf_asset_manager.inspect(
            path,
            payload.get("dxf_asset"),
            payload.get("dxf_import_state"),
            has_solver_result=self._payload_has_solver_result(payload),
            legacy_no_state=legacy_no_state,
            repair=True,
        )
        return LoadProjectResult(path, payload, status, legacy_no_state)

    @staticmethod
    def _payload_has_solver_result(payload: Mapping[str, Any]) -> bool:
        result = payload.get("result")
        if not isinstance(result, Mapping):
            return False
        best_solution = result.get("best_solution")
        if not isinstance(best_solution, Mapping):
            return False
        return bool(best_solution.get("result_items"))

    def try_exact_relink(
        self,
        request: RelinkDxfRequest,
    ) -> RelinkDxfResult | None:
        """Return an accepted result for a hash match, otherwise request import."""

        candidate_info = self.dxf_asset_manager.file_info(request.candidate_path)
        expected_hash = str((request.existing_asset or {}).get("sha256", "") or "")
        report = request.current_dxf_report
        if (
            not expected_hash
            and report is not None
            and report.active_source is not None
        ):
            expected_hash = report.active_source.sha256
        if not (
            expected_hash
            and candidate_info.sha256 == expected_hash
            and isinstance(request.saved_state, Mapping)
        ):
            return None

        relinked_state = copy.deepcopy(dict(request.saved_state))
        relinked_state["source_path"] = str(Path(request.candidate_path).resolve())
        summary = "重新連結 DXF 與專案記錄完全一致"
        return RelinkDxfResult(
            accepted=True,
            relinked_state=relinked_state,
            dxf_status_report=self.dxf_asset_manager.accepted_relink_report(
                request.candidate_path,
                summary=summary,
            ),
            compatibility_report=None,
            summary=summary,
            detail_lines=("SHA-256 完全一致",),
        )

    def relink_dxf(self, request: RelinkDxfRequest) -> RelinkDxfResult:
        """Evaluate an imported DXF candidate without mutating project state."""

        if not isinstance(request.candidate_state, Mapping):
            raise ValueError("DXF 重新連結缺少候選解析資料")

        candidate_state = request.candidate_state
        if isinstance(request.saved_state, Mapping):
            compatibility = self.dxf_compatibility_checker.compare(
                request.saved_state,
                candidate_state,
                request.project_rows,
            )
            relinked_state = (
                self.dxf_compatibility_checker.merge_source_references(
                    request.saved_state,
                    candidate_state,
                    compatibility,
                    source_path=request.candidate_path,
                )
                if compatibility.compatible
                else None
            )
        else:
            compatibility = (
                self.dxf_compatibility_checker.compare_candidate_to_solver(
                    candidate_state,
                    request.project_rows,
                )
            )
            relinked_state = (
                self.dxf_compatibility_checker.adopt_candidate_state_for_solver(
                    candidate_state,
                    compatibility,
                    source_path=request.candidate_path,
                )
                if compatibility.compatible
                else None
            )

        detail_lines = compatibility.summary_lines()
        if relinked_state is None:
            status = self.dxf_asset_manager.rejected_relink_report(
                request.candidate_path,
                status=compatibility.status,
                messages=detail_lines,
            )
            return RelinkDxfResult(
                accepted=False,
                relinked_state=None,
                dxf_status_report=status,
                compatibility_report=compatibility,
                summary="DXF 重新連結尚未通過",
                detail_lines=detail_lines,
            )

        summary = "DXF 幾何相容性已確認"
        return RelinkDxfResult(
            accepted=True,
            relinked_state=relinked_state,
            dxf_status_report=self.dxf_asset_manager.accepted_relink_report(
                request.candidate_path,
                summary=summary,
            ),
            compatibility_report=compatibility,
            summary=summary,
            detail_lines=detail_lines,
        )


__all__ = [
    "LoadProjectResult",
    "ProjectService",
    "RelinkDxfRequest",
    "RelinkDxfResult",
    "SaveProjectRequest",
    "SaveProjectResult",
]
