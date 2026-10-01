"""Application transaction contract for material-spec definition editing."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel


class MaterialSpecEditOperation(str, Enum):
    EDIT = "edit"
    DELETE = "delete"


class MaterialSpecEditStatus(str, Enum):
    STAGED = "staged"
    CONFIRMATION_REQUIRED = "confirmation_required"
    REJECTED = "rejected"
    NO_OP = "no_op"


class MaterialSpecEditError(str, Enum):
    INVALID_ROW = "invalid_row"
    STALE_REQUEST = "stale_request"
    INVALID_FIELD = "invalid_field"
    REQUIRED_SPEC_LOCKED = "required_spec_locked"
    BLANK_SPEC = "blank_spec"
    DUPLICATE_SPEC = "duplicate_spec"
    REFERENCED_USAGE_LOCKED = "referenced_usage_locked"
    REFERENCED_DELETE_BLOCKED = "referenced_delete_blocked"


@dataclass(frozen=True)
class ReferenceSummary:
    inventory: tuple[int, ...] = ()
    walers: tuple[int, ...] = ()
    struts: tuple[int, ...] = ()

    @property
    def count(self) -> int:
        return len(self.inventory) + len(self.walers) + len(self.struts)

    @property
    def changed_tables(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in ("inventory", "walers", "struts")
            if getattr(self, name)
        )


@dataclass(frozen=True)
class MaterialSpecEditRequest:
    operation: MaterialSpecEditOperation
    row_index: int
    expected_usage: str
    expected_spec: str
    field_name: str | None = None
    proposed_value: Any = ""
    allow_reference_sync: bool = False
    expected_references: ReferenceSummary | None = None


@dataclass(frozen=True)
class MaterialSpecEditOutcome:
    status: MaterialSpecEditStatus
    project_data: ProjectDataModel | None = None
    project_results: ProjectResultModel | None = None
    references: ReferenceSummary = field(default_factory=ReferenceSummary)
    changed_tables: tuple[str, ...] = ()
    clear_solver_memory: bool = False
    clear_support_candidate_cache: bool = False
    update_material_summary: bool = False
    dirty_reason: str = "輸入資料已變更"
    error_code: MaterialSpecEditError | None = None
    display_args: Mapping[str, Any] = field(default_factory=dict)


InputChangePlanner = Callable[..., Any]


def material_spec_key(usage: Any, spec: Any) -> tuple[str, str]:
    """Return the normalized key shared by material-spec workflows."""

    return (
        str(usage or "").strip().casefold(),
        str(spec or "").strip().casefold(),
    )


class MaterialSpecEditing:
    """Stage one material-spec edit without mutating committed models."""

    def __init__(self, plan_input_change: InputChangePlanner) -> None:
        self._plan_input_change = plan_input_change

    @staticmethod
    def clone_project_data(project_data: ProjectDataModel) -> ProjectDataModel:
        """Clone every persisted and runtime-only attribute for staging."""

        return copy.deepcopy(project_data)

    @staticmethod
    def _key(usage: Any, spec: Any) -> tuple[str, str]:
        return material_spec_key(usage, spec)

    @classmethod
    def _references(
        cls,
        project_data: ProjectDataModel,
        usage: Any,
        spec: Any,
    ) -> ReferenceSummary:
        target = cls._key(usage, spec)
        if not target[1]:
            return ReferenceSummary()
        inventory = tuple(
            index
            for index, row in enumerate(project_data.inventory)
            if cls._key(row.get("Usage"), row.get("Spec")) == target
        )
        walers = ()
        if target[0] == "圍令".casefold():
            walers = tuple(
                index
                for index, row in enumerate(project_data.walers)
                if cls._key("圍令", row.get("material_spec")) == target
            )
        struts = ()
        if target[0] == "支撐".casefold():
            struts = tuple(
                index
                for index, row in enumerate(project_data.struts)
                if cls._key("支撐", row.get("material_spec")) == target
            )
        return ReferenceSummary(
            inventory=inventory,
            walers=walers,
            struts=struts,
        )

    @staticmethod
    def _is_required_spec(row: Mapping[str, Any]) -> bool:
        return (
            str(row.get("Usage", "") or "").strip() == "圍令"
            and str(row.get("Spec", "") or "").strip().upper() == "RC"
        )

    @staticmethod
    def _display_args(
        usage: str,
        spec: str,
        references: ReferenceSummary,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "usage": usage,
            "spec": spec,
            "inventory_count": len(references.inventory),
            "waler_count": len(references.walers),
            "strut_count": len(references.struts),
            **extra,
        }

    @classmethod
    def _rejected(
        cls,
        error_code: MaterialSpecEditError,
        *,
        usage: str = "",
        spec: str = "",
        references: ReferenceSummary | None = None,
        **extra: Any,
    ) -> MaterialSpecEditOutcome:
        summary = references or ReferenceSummary()
        return MaterialSpecEditOutcome(
            status=MaterialSpecEditStatus.REJECTED,
            error_code=error_code,
            references=summary,
            display_args=cls._display_args(
                usage,
                spec,
                summary,
                **extra,
            ),
        )

    def _staged_outcome(
        self,
        *,
        project_data: ProjectDataModel,
        project_results: ProjectResultModel,
        references: ReferenceSummary,
        changed_tables: tuple[str, ...],
        invalidating_change: bool,
        field_name: str | None,
    ) -> MaterialSpecEditOutcome:
        plan = self._plan_input_change(
            table_name=None if invalidating_change else "material_specs",
            field_name="material_spec" if invalidating_change else field_name,
            dxf_binding_changed=False,
        )
        staged_results = (
            ProjectResultModel()
            if plan.invalidate_solver_results
            else copy.deepcopy(project_results)
        )
        return MaterialSpecEditOutcome(
            status=MaterialSpecEditStatus.STAGED,
            project_data=project_data,
            project_results=staged_results,
            references=references,
            changed_tables=changed_tables,
            clear_solver_memory=bool(plan.invalidate_solver_results),
            clear_support_candidate_cache=bool(plan.invalidate_solver_results),
            update_material_summary=(
                bool(plan.update_material_summary)
                or bool(references.inventory and invalidating_change)
            ),
            dirty_reason=str(plan.dirty_reason),
        )

    def stage(
        self,
        project_data: ProjectDataModel,
        project_results: ProjectResultModel,
        request: MaterialSpecEditRequest,
    ) -> MaterialSpecEditOutcome:
        rows = project_data.material_specs
        if not 0 <= request.row_index < len(rows):
            return self._rejected(MaterialSpecEditError.INVALID_ROW)

        row = rows[request.row_index]
        usage = str(row.get("Usage", "") or "").strip()
        spec = str(row.get("Spec", "") or "").strip()
        if (
            usage != str(request.expected_usage or "").strip()
            or spec != str(request.expected_spec or "").strip()
        ):
            return self._rejected(
                MaterialSpecEditError.STALE_REQUEST,
                usage=usage,
                spec=spec,
            )

        if self._is_required_spec(row):
            return self._rejected(
                MaterialSpecEditError.REQUIRED_SPEC_LOCKED,
                usage=usage,
                spec=spec,
                operation=request.operation.value,
            )

        references = self._references(project_data, usage, spec)
        if request.operation == MaterialSpecEditOperation.DELETE:
            if references.count:
                return self._rejected(
                    MaterialSpecEditError.REFERENCED_DELETE_BLOCKED,
                    usage=usage,
                    spec=spec,
                    references=references,
                )
            staged_data = self.clone_project_data(project_data)
            staged_data.material_specs.pop(request.row_index)
            return self._staged_outcome(
                project_data=staged_data,
                project_results=project_results,
                references=references,
                changed_tables=("material_specs",),
                invalidating_change=False,
                field_name=None,
            )

        if request.operation != MaterialSpecEditOperation.EDIT:
            return self._rejected(
                MaterialSpecEditError.INVALID_FIELD,
                usage=usage,
                spec=spec,
            )
        if request.field_name not in {"Usage", "Spec"}:
            return self._rejected(
                MaterialSpecEditError.INVALID_FIELD,
                usage=usage,
                spec=spec,
            )

        proposed_value = str(request.proposed_value or "").strip()
        current_value = usage if request.field_name == "Usage" else spec
        if proposed_value == current_value:
            return MaterialSpecEditOutcome(
                status=MaterialSpecEditStatus.NO_OP,
                references=references,
            )

        proposed_usage = proposed_value if request.field_name == "Usage" else usage
        proposed_spec = proposed_value if request.field_name == "Spec" else spec
        proposed_key = self._key(proposed_usage, proposed_spec)
        if proposed_spec and any(
            index != request.row_index
            and self._key(candidate.get("Usage"), candidate.get("Spec"))
            == proposed_key
            for index, candidate in enumerate(rows)
        ):
            return self._rejected(
                MaterialSpecEditError.DUPLICATE_SPEC,
                usage=proposed_usage,
                spec=proposed_spec,
            )

        if request.field_name == "Usage" and references.count:
            return self._rejected(
                MaterialSpecEditError.REFERENCED_USAGE_LOCKED,
                usage=usage,
                spec=spec,
                references=references,
            )
        if request.field_name == "Spec" and spec and not proposed_spec:
            return self._rejected(
                MaterialSpecEditError.BLANK_SPEC,
                usage=usage,
                spec=spec,
            )
        if request.field_name == "Spec" and references.count:
            if not request.allow_reference_sync:
                return MaterialSpecEditOutcome(
                    status=MaterialSpecEditStatus.CONFIRMATION_REQUIRED,
                    references=references,
                    display_args=self._display_args(
                        usage,
                        spec,
                        references,
                        proposed_spec=proposed_spec,
                    ),
                )
            if request.expected_references != references:
                return self._rejected(
                    MaterialSpecEditError.STALE_REQUEST,
                    usage=usage,
                    spec=spec,
                    references=references,
                )

        staged_data = self.clone_project_data(project_data)
        staged_data.material_specs[request.row_index][request.field_name] = (
            proposed_value
        )
        invalidating_change = request.field_name == "Spec" and references.count > 0
        if invalidating_change:
            for index in references.inventory:
                staged_data.inventory[index]["Spec"] = proposed_spec
            for index in references.walers:
                staged_data.walers[index]["material_spec"] = proposed_spec
            for index in references.struts:
                staged_data.struts[index]["material_spec"] = proposed_spec

        changed_tables = (
            ("material_specs", *references.changed_tables)
            if invalidating_change
            else ("material_specs",)
        )
        return self._staged_outcome(
            project_data=staged_data,
            project_results=project_results,
            references=references,
            changed_tables=changed_tables,
            invalidating_change=invalidating_change,
            field_name=request.field_name,
        )


__all__ = [
    "MaterialSpecEditError",
    "MaterialSpecEditOperation",
    "MaterialSpecEditOutcome",
    "MaterialSpecEditRequest",
    "MaterialSpecEditStatus",
    "MaterialSpecEditing",
    "ReferenceSummary",
    "material_spec_key",
]
