"""Application service for the project save, load, and DXF relink workflows.

The service coordinates persistence components and returns data-only outcomes.
It deliberately has no Tkinter dependency; callers own file dialogs, user
confirmation, application-state mutation, and presentation.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.solver_input_builder import (
    InventoryLookup,
    UNLIMITED_INVENTORY_QTY,
)

from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfAssetStatusReport,
    DxfCompatibilityChecker,
    DxfCompatibilityReport,
    DxfStatus,
    DxfWorkflowStatus,
    PROJECT_SCHEMA_VERSION,
    ProjectPersistenceError,
    ProjectSerializer,
    dxf_workflow_status_from_payload,
)


PROJECT_DXF_BINDING_FIELDS = {
    "walers": frozenset(("WalerID", "StartX", "StartY", "EndX", "EndY")),
    "struts": frozenset((
        "StrutID",
        "FromWaler",
        "ToWaler",
        "StartX",
        "StartY",
        "EndX",
        "EndY",
    )),
    "braces": frozenset((
        "BraceID",
        "FromWaler",
        "ToWaler",
        "StartX",
        "StartY",
        "EndX",
        "EndY",
    )),
}


class ProjectRowsSource(Protocol):
    """Port implemented by a reviewed DXF result without importing its adapter."""

    def to_project_rows(
        self,
        existing_rows: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]: ...


@dataclass(frozen=True)
class ApplyDxfReviewRequest:
    current_project_data: ProjectDataModel
    current_workflow_status: DxfWorkflowStatus
    import_mode: str
    review_result: ProjectRowsSource


@dataclass(frozen=True)
class ApplyDxfReviewResult:
    project_data: ProjectDataModel
    project_results: ProjectResultModel
    imported_rows: dict[str, list[dict[str, Any]]]
    workflow_status: DxfWorkflowStatus
    clear_solver_memory: bool
    clear_support_candidate_cache: bool
    dirty_reason: str


@dataclass(frozen=True)
class HydratedProject:
    project_path: Path | None
    project_data: ProjectDataModel
    project_results: ProjectResultModel
    workflow_status: DxfWorkflowStatus
    dxf_import_state: dict[str, Any] | None
    dxf_asset: dict[str, Any] | None


@dataclass(frozen=True)
class BuildProjectPayloadRequest:
    project_name: str
    project_data: ProjectDataModel
    project_results: ProjectResultModel
    workflow_status: DxfWorkflowStatus
    dxf_import_state: Mapping[str, Any] | None
    dxf_asset: Mapping[str, Any] | None


@dataclass(frozen=True)
class ProjectInputChangePlan:
    mark_dxf_binding_stale: bool
    invalidate_solver_results: bool
    update_material_summary: bool
    dirty_reason: str = "輸入資料已變更"


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
    hydrated_project: HydratedProject


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
    """Coordinate project use cases without depending on GUI state."""

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

    def stage_dxf_review_apply(
        self,
        request: ApplyDxfReviewRequest,
    ) -> ApplyDxfReviewResult:
        """Build the next Project state for one completed DXF review."""

        try:
            workflow_status = (
                request.current_workflow_status
                if isinstance(request.current_workflow_status, DxfWorkflowStatus)
                else DxfWorkflowStatus(
                    str(request.current_workflow_status).strip().upper()
                )
            )
        except ValueError as exc:
            raise ValueError("DXF workflow 狀態無效。") from exc
        if workflow_status != DxfWorkflowStatus.REVIEW:
            raise ValueError("只有 REVIEW 狀態可以完成 DXF 匯入。")

        import_mode = str(request.import_mode or "").strip().lower()
        if import_mode not in {"replace", "append"}:
            raise ValueError(f"不支援的 DXF 匯入方式：{request.import_mode}")

        current = request.current_project_data
        case_data = current.to_case_data()
        existing_rows = current.geometry_rows() if import_mode == "append" else None
        imported = request.review_result.to_project_rows(existing_rows)

        if import_mode == "append":
            walers = [*case_data["walers"], *imported["walers"]]
            struts = [*case_data["struts"], *imported["struts"]]
            braces = [*case_data["braces"], *imported["braces"]]
        else:
            walers = imported["walers"]
            struts = imported["struts"]
            braces = imported["braces"]

        staged_project_data = ProjectDataModel(
            walers=walers,
            struts=struts,
            braces=braces,
            inventory=case_data["inventory"],
            material_specs=case_data["material_specs"],
        )
        return ApplyDxfReviewResult(
            project_data=staged_project_data,
            project_results=ProjectResultModel(),
            imported_rows=copy.deepcopy(imported),
            workflow_status=DxfWorkflowStatus.COMPLETED,
            clear_solver_memory=True,
            clear_support_candidate_cache=True,
            dirty_reason="輸入資料已變更",
        )

    def hydrate_project(
        self,
        payload: Mapping[str, Any],
        *,
        project_path: str | Path | None = None,
        default_inventory: Sequence[Mapping[str, Any]] = (),
    ) -> HydratedProject:
        """Create all application models before the caller adopts project state."""

        project_data = ProjectDataModel.from_case_data(
            payload["input_data"],
            default_inventory=default_inventory,
        )
        project_results = ProjectResultModel.from_payload(payload.get("result"))
        import_state = payload.get("dxf_import_state")
        asset = payload.get("dxf_asset")
        return HydratedProject(
            project_path=(
                Path(project_path).resolve()
                if project_path is not None
                else None
            ),
            project_data=project_data,
            project_results=project_results,
            workflow_status=dxf_workflow_status_from_payload(payload),
            dxf_import_state=(
                copy.deepcopy(dict(import_state))
                if isinstance(import_state, Mapping)
                else None
            ),
            dxf_asset=(
                copy.deepcopy(dict(asset))
                if isinstance(asset, Mapping)
                else None
            ),
        )

    def build_project_payload(
        self,
        request: BuildProjectPayloadRequest,
        *,
        now: Callable[[], datetime] = datetime.now,
    ) -> dict[str, Any]:
        """Build the current persisted project schema from application models."""

        usage = request.project_results.collect_visible_material_usage()
        inventory = InventoryLookup(request.project_data.inventory)
        material_summary = ProjectResultModel.build_material_summary(
            usage,
            inventory.quantity,
            unlimited_quantity=UNLIMITED_INVENTORY_QTY,
        )
        return {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "project_information": {
                "project_name": str(request.project_name),
                "saved_at": now().isoformat(timespec="seconds"),
                "application": "SupportSolver",
            },
            "input_data": request.project_data.to_case_data(),
            "dxf_workflow_status": request.workflow_status.value,
            "dxf_import_state": copy.deepcopy(request.dxf_import_state),
            "dxf_asset": copy.deepcopy(request.dxf_asset),
            "result": request.project_results.to_payload(
                material_summary,
                now=now,
            ),
        }

    @staticmethod
    def plan_input_change(
        *,
        table_name: str | None,
        field_name: str | None,
        dxf_binding_changed: bool | None = None,
    ) -> ProjectInputChangePlan:
        """Describe application-state invalidation caused by one input edit."""

        if dxf_binding_changed is None:
            dxf_binding_changed = field_name in PROJECT_DXF_BINDING_FIELDS.get(
                table_name,
                (),
            )
        invalidate_solver_results = table_name in {
            None,
            "walers",
            "struts",
            "braces",
            "inventory",
        }
        return ProjectInputChangePlan(
            mark_dxf_binding_stale=bool(dxf_binding_changed),
            invalidate_solver_results=invalidate_solver_results,
            update_material_summary=table_name == "inventory",
        )

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

    def load_project(
        self,
        project_path: str | Path,
        *,
        default_inventory: Sequence[Mapping[str, Any]] = (),
    ) -> LoadProjectResult:
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
        hydrated = self.hydrate_project(
            payload,
            project_path=path,
            default_inventory=default_inventory,
        )
        return LoadProjectResult(
            path,
            payload,
            status,
            legacy_no_state,
            hydrated,
        )

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
    "ApplyDxfReviewRequest",
    "ApplyDxfReviewResult",
    "BuildProjectPayloadRequest",
    "HydratedProject",
    "LoadProjectResult",
    "PROJECT_DXF_BINDING_FIELDS",
    "ProjectService",
    "ProjectInputChangePlan",
    "RelinkDxfRequest",
    "RelinkDxfResult",
    "SaveProjectRequest",
    "SaveProjectResult",
]
