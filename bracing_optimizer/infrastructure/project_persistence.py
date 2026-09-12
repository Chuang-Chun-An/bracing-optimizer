"""Project JSON persistence and managed DXF asset lifecycle.

This module deliberately owns filesystem, hashing, schema and compatibility
work.  The GUI coordinates these services but does not duplicate their rules.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

import ezdxf

from bracing_optimizer.application.project_mapper import (
    ProjectDomainMappingError,
    ProjectRowMapper,
)


PROJECT_SCHEMA_VERSION = 3
MANAGED_DXF_RELATIVE_PATH = "source/source.dxf"
DXF_GEOMETRY_TOLERANCE_MM = 5.0
DXF_AMBIGUITY_TOLERANCE_MM = 0.1
CRITICAL_COMPONENT_TABLES = ("walers", "struts", "braces")


class ProjectPersistenceError(RuntimeError):
    """A project operation failed at a named, user-actionable stage."""

    def __init__(self, stage: str, detail: str):
        super().__init__(f"{stage}：{detail}")
        self.stage = stage
        self.detail = detail


class DxfStatus(str, Enum):
    READY = "READY"
    RUNTIME_READY = "RUNTIME_READY"
    VERIFIED_PENDING_SAVE = "VERIFIED_PENDING_SAVE"
    MANAGED_COPY_MODIFIED = "MANAGED_COPY_MODIFIED"
    SOURCE_MODIFIED = "SOURCE_MODIFIED"
    MISSING = "MISSING"
    RELINK_REQUIRED = "RELINK_REQUIRED"
    BINDING_REQUIRED = "BINDING_REQUIRED"
    LEGACY_NO_STATE = "LEGACY_NO_STATE"
    INCOMPATIBLE = "INCOMPATIBLE"
    GEOMETRY_COMPATIBLE = "GEOMETRY_COMPATIBLE"
    NO_DXF = "NO_DXF"


@dataclass(frozen=True)
class DxfFileInfo:
    path: Path
    sha256: str
    file_size: int
    modified_time: float


@dataclass(frozen=True)
class VerifiedDxfSource:
    """Capability passed to the exporter after centralized verification."""

    path: Path
    sha256: str
    status: DxfStatus
    original_path: str = ""


@dataclass(frozen=True)
class DxfAssetStatusReport:
    status: DxfStatus
    summary: str
    managed_path: Path | None = None
    original_path: Path | None = None
    active_source: VerifiedDxfSource | None = None
    messages: tuple[str, ...] = ()
    managed_exists: bool = False
    original_exists: bool = False
    repaired: bool = False

    @property
    def can_export(self) -> bool:
        return self.active_source is not None and self.status in {
            DxfStatus.READY,
            DxfStatus.RUNTIME_READY,
            DxfStatus.VERIFIED_PENDING_SAVE,
        }


@dataclass(frozen=True)
class ComponentMatch:
    role: str
    component_id: str
    saved_index: int
    candidate_index: int
    match_kind: str
    geometry_error_mm: float


@dataclass(frozen=True)
class DxfCompatibilityReport:
    status: DxfStatus
    exact_match_count: int = 0
    geometry_match_count: int = 0
    layer_changed_match_count: int = 0
    total_saved_components: int = 0
    candidate_component_count: int = 0
    binding_required_ids: tuple[str, ...] = ()
    incompatible_items: tuple[str, ...] = ()
    matches: tuple[ComponentMatch, ...] = ()

    @property
    def compatible(self) -> bool:
        return self.status in {DxfStatus.READY, DxfStatus.GEOMETRY_COMPATIBLE}

    def summary_lines(self) -> tuple[str, ...]:
        return (
            f"完全匹配：{self.exact_match_count}",
            f"幾何匹配：{self.geometry_match_count}",
            f"跨圖層幾何匹配：{self.layer_changed_match_count}",
            f"需要人工處理：{', '.join(self.binding_required_ids) or '無'}",
            f"不相容：{'；'.join(self.incompatible_items) or '無'}",
        )


@dataclass(frozen=True)
class ProjectSaveResult:
    project_path: Path
    dxf_asset: dict[str, Any] | None
    copied_dxf: bool
    backup_path: Path | None


class ProjectSerializer:
    """Validate the project structure used by the current application."""

    @staticmethod
    def validate(payload: Mapping[str, Any]) -> None:
        try:
            encoded = json.dumps(payload, ensure_ascii=False)
            decoded = json.loads(encoded)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProjectPersistenceError("JSON 驗證失敗", str(exc)) from exc
        if "dxf_asset" not in decoded:
            raise ProjectPersistenceError(
                "JSON 驗證失敗",
                "schema version 3 必須明確包含 dxf_asset（可為 null）",
            )
        input_data = decoded.get("input_data")
        if not isinstance(input_data, dict):
            raise ProjectPersistenceError("JSON 驗證失敗", "input_data 必須是物件")
        required_domain_tables = (
            "walers",
            "struts",
            "braces",
        )
        missing_tables = [
            table_name
            for table_name in required_domain_tables
            if not isinstance(input_data.get(table_name), list)
        ]
        if missing_tables:
            raise ProjectPersistenceError(
                "JSON 驗證失敗",
                "input_data 缺少 Domain 資料表：" + ", ".join(missing_tables),
            )
        id_fields = {
            "walers": "WalerID",
            "struts": "StrutID",
            "braces": "BraceID",
        }
        for table_name, id_field in id_fields.items():
            rows = input_data[table_name]
            if any(not isinstance(row, dict) for row in rows):
                raise ProjectPersistenceError(
                    "JSON 驗證失敗",
                    f"input_data.{table_name} 的每一筆都必須是物件",
                )
            identifiers = [
                str(row.get(id_field, "") or "").strip()
                for row in rows
            ]
            if any(not identifier for identifier in identifiers):
                raise ProjectPersistenceError(
                    "JSON 驗證失敗",
                    f"input_data.{table_name} 含空白 {id_field}",
                )
            if len(identifiers) != len(set(identifiers)):
                raise ProjectPersistenceError(
                    "JSON 驗證失敗",
                    f"input_data.{table_name} 含重複 {id_field}",
                )
        try:
            ProjectRowMapper.project(
                walers=input_data["walers"],
                struts=input_data["struts"],
                braces=input_data["braces"],
                strict=True,
            )
        except (ProjectDomainMappingError, TypeError, ValueError) as exc:
            raise ProjectPersistenceError("Domain 驗證失敗", str(exc)) from exc
        asset = decoded.get("dxf_asset")
        if asset is not None and not isinstance(asset, dict):
            raise ProjectPersistenceError("JSON 驗證失敗", "dxf_asset 必須是物件或 null")
        if asset is None:
            return
        required = {
            "storage_mode",
            "relative_path",
            "original_path",
            "original_file_name",
            "sha256",
            "file_size",
            "modified_time",
        }
        missing = sorted(required.difference(asset))
        if missing:
            raise ProjectPersistenceError(
                "JSON 驗證失敗", f"dxf_asset 缺少欄位：{', '.join(missing)}"
            )
        if asset["storage_mode"] != "managed_copy":
            raise ProjectPersistenceError("JSON 驗證失敗", "不支援的 DXF 儲存模式")
        relative = DxfAssetManager.normalized_relative_path(asset["relative_path"])
        if relative != MANAGED_DXF_RELATIVE_PATH:
            raise ProjectPersistenceError(
                "JSON 驗證失敗", "DXF 管理副本路徑必須是 source/source.dxf"
            )
        if not str(asset["sha256"]).strip() or int(asset["file_size"]) <= 0:
            raise ProjectPersistenceError("JSON 驗證失敗", "DXF 完整性資料不完整")


class DxfAssetManager:
    """Managed-copy resolution, hashing, repair and transactional storage."""

    def __init__(
        self,
        *,
        failure_hook: Callable[[str], None] | None = None,
    ) -> None:
        self.failure_hook = failure_hook

    def _checkpoint(self, stage: str) -> None:
        if self.failure_hook is not None:
            self.failure_hook(stage)

    @staticmethod
    def normalized_relative_path(value: Any) -> str:
        text = str(value or MANAGED_DXF_RELATIVE_PATH).replace("\\", "/")
        pure = PurePosixPath(text)
        if pure.is_absolute() or ".." in pure.parts:
            raise ProjectPersistenceError(
                "DXF 路徑驗證失敗", "管理副本必須使用專案內相對路徑"
            )
        return pure.as_posix()

    @classmethod
    def managed_path(
        cls,
        project_path: str | Path,
        asset: Mapping[str, Any] | None = None,
    ) -> Path:
        project_path = Path(project_path).resolve()
        relative = cls.normalized_relative_path(
            (asset or {}).get("relative_path", MANAGED_DXF_RELATIVE_PATH)
        )
        candidate = (project_path.parent / Path(*PurePosixPath(relative).parts)).resolve()
        try:
            candidate.relative_to(project_path.parent)
        except ValueError as exc:
            raise ProjectPersistenceError(
                "DXF 路徑驗證失敗", "管理副本超出專案資料夾"
            ) from exc
        return candidate

    @staticmethod
    def file_info(path: str | Path, *, validate_dxf: bool = True) -> DxfFileInfo:
        path = Path(path).resolve()
        try:
            stat = path.stat()
        except OSError as exc:
            raise ProjectPersistenceError("DXF 讀取失敗", f"{path}\n{exc}") from exc
        if not path.is_file() or stat.st_size <= 0:
            raise ProjectPersistenceError("DXF 驗證失敗", f"檔案不存在或內容為空：{path}")
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if validate_dxf:
                ezdxf.readfile(path)
        except (OSError, ezdxf.DXFError) as exc:
            raise ProjectPersistenceError("DXF 驗證失敗", f"{path}\n{exc}") from exc
        return DxfFileInfo(path, digest.hexdigest(), stat.st_size, stat.st_mtime)

    @classmethod
    def verified_source(
        cls,
        path: str | Path,
        status: DxfStatus,
        *,
        original_path: str | Path | None = None,
    ) -> VerifiedDxfSource:
        info = cls.file_info(path)
        return VerifiedDxfSource(
            info.path,
            info.sha256,
            status,
            str(original_path or info.path),
        )

    @staticmethod
    def metadata(
        info: DxfFileInfo,
        *,
        original_path: str | Path,
    ) -> dict[str, Any]:
        original = Path(original_path)
        return {
            "storage_mode": "managed_copy",
            "relative_path": MANAGED_DXF_RELATIVE_PATH,
            "original_path": str(original),
            "original_file_name": original.name,
            "sha256": info.sha256,
            "file_size": info.file_size,
            "modified_time": info.modified_time,
        }

    def _copy_verified(self, source: Path, target: Path) -> DxfFileInfo:
        temporary = target.with_name(target.name + ".repair.tmp")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, temporary)
            copied = self.file_info(temporary)
            source_info = self.file_info(source, validate_dxf=False)
            if copied.sha256 != source_info.sha256:
                raise ProjectPersistenceError("DXF 驗證失敗", "複製後 SHA-256 不一致")
            os.replace(temporary, target)
            return self.file_info(target)
        except OSError as exc:
            raise ProjectPersistenceError("DXF 修復失敗", str(exc)) from exc
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def inspect(
        self,
        project_path: str | Path | None,
        asset: Mapping[str, Any] | None,
        import_state: Mapping[str, Any] | None,
        *,
        has_solver_result: bool = False,
        legacy_no_state: bool = False,
        repair: bool = True,
    ) -> DxfAssetStatusReport:
        if asset is not None and project_path is not None:
            managed = self.managed_path(project_path, asset)
            original_text = str(asset.get("original_path", "") or "")
            original = Path(original_text).expanduser() if original_text else None
            original_exists = bool(original and original.is_file())
            if managed.is_file():
                try:
                    info = self.file_info(managed)
                except ProjectPersistenceError as exc:
                    return DxfAssetStatusReport(
                        DxfStatus.MANAGED_COPY_MODIFIED,
                        "專案管理副本無法讀取",
                        managed,
                        original,
                        messages=(str(exc),),
                        managed_exists=True,
                        original_exists=original_exists,
                    )
                expected_hash = str(asset.get("sha256", "") or "")
                expected_size = int(asset.get("file_size", 0) or 0)
                if info.sha256 != expected_hash or info.file_size != expected_size:
                    return DxfAssetStatusReport(
                        DxfStatus.MANAGED_COPY_MODIFIED,
                        "專案管理副本內容與 project.json 記錄不同",
                        managed,
                        original,
                        messages=("已阻止無提示匯出，請重新連結或修復 DXF。",),
                        managed_exists=True,
                        original_exists=original_exists,
                    )
                source = VerifiedDxfSource(
                    managed,
                    info.sha256,
                    DxfStatus.READY,
                    original_text,
                )
                return DxfAssetStatusReport(
                    DxfStatus.READY,
                    "專案管理副本已驗證",
                    managed,
                    original,
                    source,
                    managed_exists=True,
                    original_exists=original_exists,
                )

            if original_exists:
                try:
                    original_info = self.file_info(original)
                except ProjectPersistenceError as exc:
                    return DxfAssetStatusReport(
                        DxfStatus.MISSING,
                        "管理副本遺失，外部原始來源無法讀取",
                        managed,
                        original,
                        messages=(str(exc),),
                        original_exists=True,
                    )
                if original_info.sha256 != str(asset.get("sha256", "") or ""):
                    return DxfAssetStatusReport(
                        DxfStatus.SOURCE_MODIFIED,
                        "管理副本遺失，外部原始來源內容已修改",
                        managed,
                        original,
                        messages=("不可直接以外部來源取代底圖，請執行重新連結。",),
                        original_exists=True,
                    )
                if repair:
                    try:
                        repaired = self._copy_verified(original, managed)
                    except ProjectPersistenceError as exc:
                        return DxfAssetStatusReport(
                            DxfStatus.MISSING,
                            "管理副本遺失且自動修復失敗",
                            managed,
                            original,
                            messages=(str(exc),),
                            original_exists=True,
                        )
                    source = VerifiedDxfSource(
                        managed,
                        repaired.sha256,
                        DxfStatus.READY,
                        original_text,
                    )
                    return DxfAssetStatusReport(
                        DxfStatus.READY,
                        "管理副本已由完全相同的原始來源修復",
                        managed,
                        original,
                        source,
                        managed_exists=True,
                        original_exists=True,
                        repaired=True,
                    )
            return DxfAssetStatusReport(
                DxfStatus.MISSING,
                "找不到專案管理副本與可修復的原始來源",
                managed,
                original,
                messages=("請使用「重新連結 DXF」。",),
                original_exists=original_exists,
            )

        if isinstance(import_state, Mapping):
            source_text = str(import_state.get("source_path", "") or "")
            source = Path(source_text) if source_text else None
            return DxfAssetStatusReport(
                DxfStatus.RELINK_REQUIRED,
                "舊專案尚未建立 DXF 管理副本",
                original_path=source,
                messages=(
                    "Solver 資料已保留；儲存專案可從仍存在的原始來源建立管理副本。",
                ),
                original_exists=bool(source and source.is_file()),
            )
        if has_solver_result and legacy_no_state:
            return DxfAssetStatusReport(
                DxfStatus.LEGACY_NO_STATE,
                "專案沒有可用的 DXF 構件綁定資訊",
                messages=(
                    "既有 Solver 輸入、最佳化結果與材料配置仍可使用。",
                    "若要匯出 DXF，請重新建立 DXF 關聯。",
                ),
            )
        return DxfAssetStatusReport(
            DxfStatus.NO_DXF,
            "此專案未建立 DXF 關聯",
            messages=("可正常使用手動輸入與 Solver；DXF 成果匯出停用。",),
        )

    def runtime_report(self, source_path: str | Path) -> DxfAssetStatusReport:
        source = self.verified_source(source_path, DxfStatus.RUNTIME_READY)
        return DxfAssetStatusReport(
            DxfStatus.RUNTIME_READY,
            "DXF 已匯入，尚未保存為專案管理副本",
            original_path=source.path,
            active_source=source,
            messages=("儲存專案後會建立 source/source.dxf。",),
            original_exists=True,
        )

    def accepted_relink_report(
        self,
        source_path: str | Path,
        *,
        summary: str,
    ) -> DxfAssetStatusReport:
        source = self.verified_source(
            source_path,
            DxfStatus.VERIFIED_PENDING_SAVE,
            original_path=source_path,
        )
        return DxfAssetStatusReport(
            DxfStatus.VERIFIED_PENDING_SAVE,
            summary,
            original_path=source.path,
            active_source=source,
            messages=("重新連結已驗證；請儲存專案以更新管理副本。",),
            original_exists=True,
        )

    def rejected_relink_report(
        self,
        source_path: str | Path,
        *,
        status: DxfStatus,
        messages: Sequence[str],
    ) -> DxfAssetStatusReport:
        if status not in {DxfStatus.BINDING_REQUIRED, DxfStatus.INCOMPATIBLE}:
            raise ValueError(f"不支援的重新連結失敗狀態：{status.value}")
        source_path = Path(source_path).resolve()
        return DxfAssetStatusReport(
            status,
            "候選 DXF 尚未通過構件相容性檢查",
            original_path=source_path,
            messages=tuple(messages),
            original_exists=source_path.is_file(),
        )

    def save_project(
        self,
        project_path: str | Path,
        payload: Mapping[str, Any],
        *,
        active_source: VerifiedDxfSource | None,
        existing_asset: Mapping[str, Any] | None,
    ) -> ProjectSaveResult:
        project_path = Path(project_path).resolve()
        project_dir = project_path.parent
        managed_path = self.managed_path(project_path, existing_asset)
        json_temporary = project_path.with_name(project_path.name + ".tmp")
        dxf_temporary = managed_path.with_name(managed_path.name + ".tmp")
        dxf_rollback = managed_path.with_name(managed_path.name + ".rollback")
        backup_path = project_path.with_name(project_path.name + ".bak")
        copied_dxf = False
        asset_replaced = False
        had_managed_asset = managed_path.is_file()
        stage = "建立專案資料夾失敗"
        final_payload = copy.deepcopy(dict(payload))
        try:
            project_dir.mkdir(parents=True, exist_ok=True)
            self._checkpoint("project_directory_created")

            asset_metadata: dict[str, Any] | None = None
            if active_source is not None:
                stage = "DXF 來源驗證失敗"
                source_info = self.file_info(active_source.path, validate_dxf=False)
                if source_info.sha256 != active_source.sha256:
                    raise ProjectPersistenceError(
                        stage, "DXF 在驗證後又被修改，請重新執行儲存"
                    )
                existing_info = None
                if managed_path.is_file():
                    try:
                        existing_info = self.file_info(
                            managed_path,
                            validate_dxf=False,
                        )
                    except ProjectPersistenceError:
                        existing_info = None
                needs_copy = not (
                    existing_info is not None
                    and existing_info.sha256 == source_info.sha256
                )
                if needs_copy:
                    stage = "DXF 複製失敗"
                    managed_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_info.path, dxf_temporary)
                    self._checkpoint("dxf_copied_to_temp")
                    stage = "DXF 驗證失敗"
                    staged_info = self.file_info(dxf_temporary)
                    if staged_info.sha256 != source_info.sha256:
                        raise ProjectPersistenceError(stage, "暫存副本 SHA-256 不一致")
                    copied_dxf = True
                    metadata_info = staged_info
                else:
                    metadata_info = existing_info
                original_path = active_source.original_path or str(source_info.path)
                if source_info.path == managed_path and existing_asset:
                    original_path = str(
                        existing_asset.get("original_path", original_path) or original_path
                    )
                asset_metadata = self.metadata(
                    metadata_info,
                    original_path=original_path,
                )
            elif existing_asset is not None:
                # Preserve an already recorded missing/corrupt asset so saving
                # Solver edits never silently discards recovery metadata.
                asset_metadata = copy.deepcopy(dict(existing_asset))

            final_payload["schema_version"] = PROJECT_SCHEMA_VERSION
            final_payload["dxf_asset"] = asset_metadata
            stage = "JSON 驗證失敗"
            ProjectSerializer.validate(final_payload)
            stage = "JSON 寫入失敗"
            with json_temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(final_payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._checkpoint("json_written_to_temp")
            with json_temporary.open("r", encoding="utf-8") as stream:
                parsed = json.load(stream)
            ProjectSerializer.validate(parsed)

            if project_path.is_file():
                stage = "專案備份失敗"
                shutil.copy2(project_path, backup_path)

            if copied_dxf:
                stage = "DXF 正式檔案替換失敗"
                if managed_path.is_file():
                    shutil.copy2(managed_path, dxf_rollback)
                os.replace(dxf_temporary, managed_path)
                asset_replaced = True
                stage = "project.json 正式檔案替換失敗"
                self._checkpoint("dxf_replaced")

            stage = "project.json 正式檔案替換失敗"
            os.replace(json_temporary, project_path)
        except ProjectPersistenceError:
            if asset_replaced:
                self._rollback_asset(managed_path, dxf_rollback, had_managed_asset)
            raise
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            if asset_replaced:
                self._rollback_asset(managed_path, dxf_rollback, had_managed_asset)
            raise ProjectPersistenceError(stage, str(exc)) from exc
        finally:
            for temporary in (json_temporary, dxf_temporary, dxf_rollback):
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

        return ProjectSaveResult(
            project_path,
            asset_metadata,
            copied_dxf,
            backup_path if backup_path.is_file() else None,
        )

    @staticmethod
    def _rollback_asset(target: Path, rollback: Path, had_asset: bool) -> None:
        try:
            if had_asset and rollback.is_file():
                os.replace(rollback, target)
            elif not had_asset:
                target.unlink(missing_ok=True)
        except OSError as exc:
            raise ProjectPersistenceError(
                "交易回復失敗",
                f"DXF 管理副本可能需要人工檢查：{target}\n{exc}",
            ) from exc


class DxfCompatibilityChecker:
    """Match saved engineering components to a relink candidate by geometry."""

    def __init__(
        self,
        *,
        geometry_tolerance_mm: float = DXF_GEOMETRY_TOLERANCE_MM,
    ) -> None:
        self.geometry_tolerance_mm = float(geometry_tolerance_mm)

    @staticmethod
    def _point(item: Mapping[str, Any], prefix: str) -> tuple[float, float] | None:
        value = item.get(prefix)
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 2:
            return None
        try:
            point = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
        return point if all(math.isfinite(number) for number in point) else None

    @classmethod
    def _line(
        cls,
        item: Mapping[str, Any],
    ) -> tuple[tuple[float, float], tuple[float, float]] | None:
        for start_key, end_key in (
            ("world_start", "world_end"),
            ("start", "end"),
            ("local_start", "local_end"),
        ):
            start, end = cls._point(item, start_key), cls._point(item, end_key)
            if start is not None and end is not None:
                return start, end
        return None

    @staticmethod
    def _line_error(first, second) -> float:
        def distance(a, b):
            return math.hypot(a[0] - b[0], a[1] - b[1])

        return min(
            max(distance(first[0], second[0]), distance(first[1], second[1])),
            max(distance(first[0], second[1]), distance(first[1], second[0])),
        )

    @staticmethod
    def _handles(item: Mapping[str, Any]) -> set[str]:
        values = item.get("source_handles", ()) or ()
        return {str(value) for value in values if str(value)}

    @staticmethod
    def _coordinate_error(
        saved_state: Mapping[str, Any],
        candidate_state: Mapping[str, Any],
    ) -> str | None:
        saved = saved_state.get("coordinate_system") or {}
        candidate = candidate_state.get("coordinate_system") or {}
        if str(saved.get("mode", "world")) != str(candidate.get("mode", "world")):
            return "座標系統模式不同"
        for key in ("origin_x", "origin_y"):
            try:
                difference = abs(float(saved.get(key, 0)) - float(candidate.get(key, 0)))
            except (TypeError, ValueError):
                return f"座標系統 {key} 無法比較"
            if difference > DXF_GEOMETRY_TOLERANCE_MM:
                return f"座標原點 {key} 不同"
        return None

    def compare(
        self,
        saved_state: Mapping[str, Any],
        candidate_state: Mapping[str, Any],
        input_data: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    ) -> DxfCompatibilityReport:
        coordinate_error = self._coordinate_error(saved_state, candidate_state)
        incompatible = [coordinate_error] if coordinate_error else []
        saved_converted = saved_state.get("converted") or {}
        candidate_converted = candidate_state.get("converted") or {}
        matches: list[ComponentMatch] = []
        binding_required: list[str] = []
        exact_count = geometry_count = layer_changed_count = 0
        total_saved = candidate_total = 0

        for role in CRITICAL_COMPONENT_TABLES:
            saved_items = [
                item for item in saved_converted.get(role, ()) if isinstance(item, Mapping)
            ]
            candidate_items = [
                item for item in candidate_converted.get(role, ()) if isinstance(item, Mapping)
            ]
            total_saved += len(saved_items)
            candidate_total += len(candidate_items)
            if len(saved_items) != len(candidate_items):
                incompatible.append(
                    f"{role} 構件數量不同：保存 {len(saved_items)}、候選 {len(candidate_items)}"
                )
            unused = set(range(len(candidate_items)))
            for saved_index, saved_item in enumerate(saved_items):
                component_id = str(saved_item.get("id", f"{role}:{saved_index + 1}"))
                saved_line = self._line(saved_item)
                if saved_line is None:
                    incompatible.append(f"{component_id} 缺少保存的工程線")
                    continue
                options = []
                for candidate_index in unused:
                    candidate_item = candidate_items[candidate_index]
                    candidate_line = self._line(candidate_item)
                    if candidate_line is None:
                        continue
                    error = self._line_error(saved_line, candidate_line)
                    if error <= self.geometry_tolerance_mm:
                        same_handle = bool(
                            self._handles(saved_item) & self._handles(candidate_item)
                        )
                        same_layer = str(saved_item.get("source_layer", "")) == str(
                            candidate_item.get("source_layer", "")
                        )
                        priority = 0 if same_handle else (1 if same_layer else 2)
                        options.append((priority, error, candidate_index))
                options.sort()
                if not options:
                    binding_required.append(component_id)
                    continue
                best_priority, best_error, candidate_index = options[0]
                equally_good = [
                    option
                    for option in options
                    if option[0] == best_priority
                    and abs(option[1] - best_error) <= DXF_AMBIGUITY_TOLERANCE_MM
                ]
                if len(equally_good) > 1:
                    binding_required.append(component_id)
                    continue
                unused.remove(candidate_index)
                kind = ("exact" if best_priority == 0 else (
                    "geometry" if best_priority == 1 else "geometry_layer_changed"
                ))
                exact_count += kind == "exact"
                geometry_count += kind == "geometry"
                layer_changed_count += kind == "geometry_layer_changed"
                matches.append(
                    ComponentMatch(
                        role,
                        component_id,
                        saved_index,
                        candidate_index,
                        kind,
                        best_error,
                    )
                )

        incompatible.extend(self._validate_solver_rows(saved_state, input_data or {}))
        if incompatible or (total_saved and not matches):
            status = DxfStatus.INCOMPATIBLE
        elif binding_required:
            status = DxfStatus.BINDING_REQUIRED
        elif total_saved:
            status = DxfStatus.GEOMETRY_COMPATIBLE
        else:
            status = DxfStatus.BINDING_REQUIRED
            binding_required.append("未保存可比對的關鍵構件")
        return DxfCompatibilityReport(
            status,
            exact_count,
            geometry_count,
            layer_changed_count,
            total_saved,
            candidate_total,
            tuple(binding_required),
            tuple(item for item in incompatible if item),
            tuple(matches),
        )

    def compare_candidate_to_solver(
        self,
        candidate_state: Mapping[str, Any],
        input_data: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> DxfCompatibilityReport:
        """Rebuild only the missing legacy binding contract from Solver rows."""

        coordinate = copy.deepcopy(candidate_state.get("coordinate_system") or {})
        local_mode = str(coordinate.get("mode", "world")) == "local"
        origin_x = float(coordinate.get("origin_x", 0.0) or 0.0)
        origin_y = float(coordinate.get("origin_y", 0.0) or 0.0)
        specs = (
            ("walers", "WalerID"),
            ("struts", "StrutID"),
            ("braces", "BraceID"),
        )
        converted: dict[str, list[dict[str, Any]]] = {}
        for role, id_field in specs:
            converted[role] = []
            for row in input_data.get(role, ()):
                try:
                    start = float(row["StartX"]), float(row["StartY"])
                    end = float(row["EndX"]), float(row["EndY"])
                except (KeyError, TypeError, ValueError):
                    continue
                world_start = (
                    (start[0] + origin_x, start[1] + origin_y)
                    if local_mode
                    else start
                )
                world_end = (
                    (end[0] + origin_x, end[1] + origin_y)
                    if local_mode
                    else end
                )
                converted[role].append({
                    "id": str(row.get(id_field, "") or ""),
                    "start": start,
                    "end": end,
                    "world_start": world_start,
                    "world_end": world_end,
                    "source_handles": (),
                    "source_layer": "",
                })
        solver_state = {
            "coordinate_system": coordinate,
            "converted": converted,
        }
        return self.compare(solver_state, candidate_state, input_data)

    @staticmethod
    def adopt_candidate_state_for_solver(
        candidate_state: Mapping[str, Any],
        report: DxfCompatibilityReport,
        *,
        source_path: str | Path,
    ) -> dict[str, Any]:
        if not report.compatible:
            raise ProjectPersistenceError("DXF 重新連結失敗", "候選 DXF 尚未通過相容性檢查")
        adopted = copy.deepcopy(dict(candidate_state))
        converted = adopted.get("converted") or {}
        for match in report.matches:
            converted[match.role][match.candidate_index]["id"] = match.component_id
        adopted["source_path"] = str(Path(source_path).resolve())
        return adopted

    def _validate_solver_rows(
        self,
        saved_state: Mapping[str, Any],
        input_data: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> list[str]:
        converted = saved_state.get("converted") or {}
        specs = (
            ("walers", "WalerID"),
            ("struts", "StrutID"),
            ("braces", "BraceID"),
        )
        errors: list[str] = []
        for role, id_field in specs:
            row_lines = []
            for row in input_data.get(role, ()):
                component_id = str(row.get(id_field, "") or "")
                try:
                    row_line = (
                        (float(row["StartX"]), float(row["StartY"])),
                        (float(row["EndX"]), float(row["EndY"])),
                    )
                except (KeyError, TypeError, ValueError):
                    errors.append(f"{component_id} 的 Solver 工程線無法驗證")
                    continue
                row_lines.append((component_id, row_line))
            for saved_item in converted.get(role, ()):
                if not isinstance(saved_item, Mapping):
                    continue
                component_id = str(saved_item.get("id", "") or "")
                saved_line = (
                    self._point(saved_item, "start"),
                    self._point(saved_item, "end"),
                )
                if None in saved_line:
                    errors.append(f"{component_id} 缺少本地工程線")
                    continue
                if not any(
                    self._line_error(row_line, saved_line) <= self.geometry_tolerance_mm
                    for _row_id, row_line in row_lines
                ):
                    errors.append(
                        f"{component_id} 的 Solver 工程線與 DXF 保存狀態不一致"
                    )
        return errors

    @staticmethod
    def merge_source_references(
        saved_state: Mapping[str, Any],
        candidate_state: Mapping[str, Any],
        report: DxfCompatibilityReport,
        *,
        source_path: str | Path,
    ) -> dict[str, Any]:
        if not report.compatible:
            raise ProjectPersistenceError("DXF 重新連結失敗", "相容性報告尚未通過")
        merged = copy.deepcopy(dict(saved_state))
        candidate_converted = candidate_state.get("converted") or {}
        merged_converted = merged.get("converted") or {}
        for match in report.matches:
            saved_item = merged_converted[match.role][match.saved_index]
            candidate_item = candidate_converted[match.role][match.candidate_index]
            for key in (
                "source_layer",
                "source_handles",
                "source_entity_types",
                "recognition_method",
            ):
                if key in candidate_item:
                    saved_item[key] = copy.deepcopy(candidate_item[key])
        for key in (
            "layer_names",
            "selected_layers",
            "layer_classification",
            "layer_assignments",
            "layer_info",
        ):
            if key in candidate_state:
                merged[key] = copy.deepcopy(candidate_state[key])
        merged["source_path"] = str(Path(source_path).resolve())
        return merged


__all__ = [
    "CRITICAL_COMPONENT_TABLES",
    "DXF_GEOMETRY_TOLERANCE_MM",
    "DxfAssetManager",
    "DxfAssetStatusReport",
    "DxfCompatibilityChecker",
    "DxfCompatibilityReport",
    "DxfFileInfo",
    "DxfStatus",
    "MANAGED_DXF_RELATIVE_PATH",
    "PROJECT_SCHEMA_VERSION",
    "ProjectPersistenceError",
    "ProjectSaveResult",
    "ProjectSerializer",
    "VerifiedDxfSource",
]
