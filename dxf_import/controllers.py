"""Selection and formal-model controllers for the DXF dialog."""

from __future__ import annotations

from typing import Any, Callable

from .candidate_points import CandidatePointStore, apply_candidate_point_selection
from .waler_contact_adjustment import (
    WalerContactAdjustmentPlan,
    apply_waler_contact_adjustment,
    plan_waler_contact_adjustment,
)
from .material_recognition import set_member_material_spec
from .models import (
    CandidatePoint,
    DXFImportError,
    DXFImportResult,
    GeometryTolerances,
    SelectionState,
)
from .preview import PerformanceDiagnostics, RenderDirty


class SelectionController:
    """One-way intent -> state transition -> dirty-region notification."""

    VALID_SOURCES = {
        "canvas",
        "candidate_tree",
        "component_tree",
        "programmatic",
        "error_list",
        "restore_recommended",
        "cad_manual",
        "coordinate_dialog",
    }

    def __init__(
        self,
        state: SelectionState,
        candidate_store: CandidatePointStore,
        member_lookup: Callable[[str], Any],
        request_render: Callable[[RenderDirty], None],
        diagnostics: PerformanceDiagnostics | None = None,
    ) -> None:
        self.state = state
        self.candidate_store = candidate_store
        self.member_lookup = member_lookup
        self.request_render = request_render
        self.diagnostics = diagnostics

    def _called(self) -> None:
        if self.diagnostics is not None:
            self.diagnostics.selection_controller_calls += 1

    def _noop(self) -> bool:
        if self.diagnostics is not None:
            self.diagnostics.idempotent_skips += 1
        return False

    def _commit(self, source: str, dirty: RenderDirty) -> bool:
        self.state.selection_source = (
            source if source in self.VALID_SOURCES else "programmatic"
        )
        self.state.revision += 1
        self.request_render(dirty)
        return True

    @staticmethod
    def _candidate_selection_source(point: CandidatePoint) -> str:
        if (
            "cad_manual" in point.point_types
            or point.point_type.startswith("cad_manual")
        ):
            return "cad_manual"
        return "manual_candidate_points"

    def select_component(self, component_id: str, source: str) -> bool:
        self._called()
        member = self.member_lookup(component_id)
        if member is None:
            return self._noop()
        if component_id == self.state.selected_component_id:
            return self._noop()
        self.state.selected_component_id = component_id
        self.state.hovered_component_id = ""
        self.state.selected_candidate_point_id = ""
        self.state.selected_candidate_source = ""
        self.state.hovered_candidate_point_id = ""
        self.state.preview_candidate_point_id = ""
        self.state.mode = "idle"
        self.state.selected_start_point_id = member.selected_start_point_id
        self.state.selected_end_point_id = member.selected_end_point_id
        self.state.pending_start_point_id = member.selected_start_point_id
        self.state.pending_end_point_id = member.selected_end_point_id
        self.state.pick_baseline_start_point_id = member.selected_start_point_id
        self.state.pick_baseline_end_point_id = member.selected_end_point_id
        self.state.pending_selection_source = member.selection_source
        return self._commit(
            source,
            RenderDirty.CANDIDATE_LAYER
            | RenderDirty.COMPONENT_SELECTION
            | RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL
            | RenderDirty.TREE_SELECTION,
        )

    def select_candidate_point(self, point_id: str, source: str) -> bool:
        self._called()
        component_id = self.state.selected_component_id
        point = self.candidate_store.get(component_id, point_id)
        if point is None:
            return self._noop()
        self.state.selected_candidate_source = (
            source if source in self.VALID_SOURCES else "programmatic"
        )
        mode = self.state.mode
        selected_changed = point_id != self.state.selected_candidate_point_id
        pending_changed = False
        if mode == "pick_start":
            if "start" not in point.valid_for:
                return self._noop()
            pending_changed = point_id != self.state.pending_start_point_id
            self.state.pending_start_point_id = point_id
            self.state.pending_selection_source = self._candidate_selection_source(
                point
            )
            self.state.mode = "idle"
        elif mode == "pick_end":
            if "end" not in point.valid_for:
                return self._noop()
            pending_changed = point_id != self.state.pending_end_point_id
            self.state.pending_end_point_id = point_id
            self.state.pending_selection_source = self._candidate_selection_source(
                point
            )
            self.state.mode = "idle"
        if not selected_changed and not pending_changed and mode == "idle":
            return self._noop()
        self.state.selected_candidate_point_id = point_id
        self.state.preview_candidate_point_id = point_id
        return self._commit(
            source,
            RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL
            | RenderDirty.TREE_SELECTION,
        )

    def preview_candidate_point(self, point_id: str, source: str) -> bool:
        """Highlight a candidate without changing pending endpoint edits."""

        self._called()
        component_id = self.state.selected_component_id
        point = self.candidate_store.get(component_id, point_id)
        if point is None:
            return self._noop()
        selected_source = (
            source if source in self.VALID_SOURCES else "programmatic"
        )
        if (
            point_id == self.state.selected_candidate_point_id
            and selected_source == self.state.selected_candidate_source
        ):
            return self._noop()
        self.state.selected_candidate_point_id = point_id
        self.state.selected_candidate_source = selected_source
        self.state.preview_candidate_point_id = point_id
        return self._commit(
            source,
            RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.DETAIL_PANEL
            | RenderDirty.TREE_SELECTION,
        )

    def set_hovered_component(self, component_id: str) -> bool:
        self._called()
        if component_id and self.member_lookup(component_id) is None:
            component_id = ""
        if component_id == self.state.hovered_component_id:
            return self._noop()
        self.state.hovered_component_id = component_id
        if component_id:
            self.state.hovered_candidate_point_id = ""
        return self._commit("canvas", RenderDirty.HOVER)

    def set_hovered_candidate(self, point_id: str) -> bool:
        self._called()
        if point_id and self.candidate_store.get(
            self.state.selected_component_id,
            point_id,
        ) is None:
            point_id = ""
        if point_id == self.state.hovered_candidate_point_id:
            return self._noop()
        self.state.hovered_candidate_point_id = point_id
        if point_id:
            self.state.hovered_component_id = ""
        return self._commit(
            "canvas",
            RenderDirty.HOVER | RenderDirty.TEMP_LINE | RenderDirty.DETAIL_PANEL,
        )

    def begin_pick_start(self) -> bool:
        return self._begin_pick("pick_start")

    def begin_pick_end(self) -> bool:
        return self._begin_pick("pick_end")

    def _begin_pick(self, mode: str) -> bool:
        self._called()
        if self.member_lookup(self.state.selected_component_id) is None:
            return self._noop()
        if self.state.mode == mode:
            return self._noop()
        self.state.mode = mode
        self.state.selected_candidate_point_id = ""
        self.state.selected_candidate_source = ""
        self.state.pick_baseline_start_point_id = self.state.pending_start_point_id
        self.state.pick_baseline_end_point_id = self.state.pending_end_point_id
        return self._commit(
            "programmatic",
            RenderDirty.CANDIDATE_LAYER
            | RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL,
        )

    def cancel_pick(self) -> bool:
        self._called()
        if self.state.mode not in {"pick_start", "pick_end"}:
            return self._noop()
        self.state.pending_start_point_id = self.state.pick_baseline_start_point_id
        self.state.pending_end_point_id = self.state.pick_baseline_end_point_id
        self.state.mode = "idle"
        return self._commit(
            "programmatic",
            RenderDirty.CANDIDATE_LAYER
            | RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL,
        )

    def swap_pending_points(self) -> bool:
        self._called()
        if not self.state.selected_component_id:
            return self._noop()
        start_id = self.state.pending_start_point_id
        end_id = self.state.pending_end_point_id
        if not start_id and not end_id:
            return self._noop()
        self.state.pending_start_point_id = end_id
        self.state.pending_end_point_id = start_id
        self.state.pending_selection_source = "manual_candidate_points"
        self.state.mode = "idle"
        return self._commit(
            "programmatic",
            RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL,
        )

    def restore_recommended_points(self) -> bool:
        self._called()
        member = self.member_lookup(self.state.selected_component_id)
        if member is None:
            return self._noop()
        values = (
            member.recommended_start_point_id,
            member.recommended_end_point_id,
        )
        if values == (
            self.state.pending_start_point_id,
            self.state.pending_end_point_id,
        ) and self.state.mode == "idle":
            return self._noop()
        self.state.pending_start_point_id = values[0]
        self.state.pending_end_point_id = values[1]
        self.state.pending_selection_source = "auto"
        self.state.mode = "idle"
        return self._commit(
            "restore_recommended",
            RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL,
        )

    def cancel_pending(self) -> bool:
        self._called()
        values = (
            self.state.selected_start_point_id,
            self.state.selected_end_point_id,
        )
        if values == (
            self.state.pending_start_point_id,
            self.state.pending_end_point_id,
        ) and self.state.mode == "idle":
            return self._noop()
        self.state.pending_start_point_id = values[0]
        self.state.pending_end_point_id = values[1]
        member = self.member_lookup(self.state.selected_component_id)
        self.state.pending_selection_source = (
            member.selection_source if member is not None else "auto"
        )
        self.state.mode = "idle"
        return self._commit(
            "programmatic",
            RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL,
        )

    def set_pending_pair(
        self,
        start_point_id: str,
        end_point_id: str,
        source: str,
    ) -> bool:
        self._called()
        component_id = self.state.selected_component_id
        start = self.candidate_store.get(component_id, start_point_id)
        end = self.candidate_store.get(component_id, end_point_id)
        if start is None or end is None:
            return self._noop()
        if (
            start_point_id == self.state.pending_start_point_id
            and end_point_id == self.state.pending_end_point_id
            and self.state.mode == "idle"
        ):
            return self._noop()
        self.state.pending_start_point_id = start_point_id
        self.state.pending_end_point_id = end_point_id
        self.state.selected_candidate_point_id = start_point_id
        self.state.selected_candidate_source = (
            source if source in self.VALID_SOURCES else "programmatic"
        )
        self.state.preview_candidate_point_id = start_point_id
        self.state.pending_selection_source = (
            "cad_manual" if source == "cad_manual" else "manual_candidate_points"
        )
        self.state.mode = "idle"
        return self._commit(
            source,
            RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL
            | RenderDirty.TREE_SELECTION,
        )

    def synchronize_formal_member(self, source: str = "programmatic") -> bool:
        self._called()
        member = self.member_lookup(self.state.selected_component_id)
        if member is None:
            return self._noop()
        self.state.selected_start_point_id = member.selected_start_point_id
        self.state.selected_end_point_id = member.selected_end_point_id
        self.state.pending_start_point_id = member.selected_start_point_id
        self.state.pending_end_point_id = member.selected_end_point_id
        self.state.pending_selection_source = member.selection_source
        self.state.mode = "idle"
        return self._commit(
            source,
            RenderDirty.COMPONENT_LAYER
            | RenderDirty.COMPONENT_SELECTION
            | RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
            | RenderDirty.DETAIL_PANEL
            | RenderDirty.TREE_SELECTION,
        )


class ImportModelController:
    """The only UI controller allowed to commit pending endpoint choices."""

    def __init__(
        self,
        tolerances: GeometryTolerances,
        candidate_store: CandidatePointStore | None = None,
    ) -> None:
        self.tolerances = tolerances
        self.candidate_store = candidate_store

    def apply_pending(
        self,
        result: DXFImportResult,
        state: SelectionState,
    ) -> DXFImportResult:
        if self.candidate_store is not None:
            start = self.candidate_store.get(
                state.selected_component_id,
                state.pending_start_point_id,
            )
            end = self.candidate_store.get(
                state.selected_component_id,
                state.pending_end_point_id,
            )
            if start is None or end is None:
                raise DXFImportError("待套用候選點不在 CandidatePointStore 中。")
        return apply_candidate_point_selection(
            result,
            state.selected_component_id,
            state.pending_start_point_id,
            state.pending_end_point_id,
            self.tolerances,
            selection_source=state.pending_selection_source,
        )

    def preview_waler_contact_adjustment(
        self,
        result: DXFImportResult,
        waler_id: str,
        **dimensions,
    ) -> WalerContactAdjustmentPlan:
        return plan_waler_contact_adjustment(
            result,
            waler_id,
            tolerances=self.tolerances,
            **dimensions,
        )

    def apply_waler_contact_adjustment(
        self,
        result: DXFImportResult,
        waler_id: str,
        **dimensions,
    ) -> DXFImportResult:
        return apply_waler_contact_adjustment(
            result,
            waler_id,
            tolerances=self.tolerances,
            **dimensions,
        )

    def apply_material_spec(
        self,
        result: DXFImportResult,
        member_id: str,
        material_spec: str,
    ) -> DXFImportResult:
        return set_member_material_spec(result, member_id, material_spec)
