"""Application workflow for one DXF engineering-review session.

This module deliberately has no Tkinter dependency.  It owns the formal WCS
result and rebuilds every derived local/review projection after a committed
mutation.  Presentation state (selection, windows, canvas items and prompts)
remains in :mod:`dxf_import.dialog`.
"""

from __future__ import annotations

import copy
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .candidate_points import (
    CandidatePointStore,
    add_cad_candidate_points,
    apply_candidate_point_selection,
    rebuild_component_associations,
)
from .geometry import Point
from .material_recognition import set_member_material_spec
from .models import (
    AuxiliaryComponent,
    Brace,
    CoordinateSystem,
    DXFImportError,
    DXFImportResult,
    ExcludedSource,
    ProblemRecord,
    ReviewItem,
    SelectionState,
    Strut,
    Waler,
    apply_coordinate_system,
)
from .review_confirmation import (
    confirm_review_item,
    review_confirmation_identity,
    review_confirmations_from_state,
    review_item_is_confirmed,
    serialize_review_confirmations,
    unconfirmed_formal_review_items,
    valid_review_confirmations,
)
from .source_exclusion import (
    ManualReplayReport,
    canonical_source_identity,
    capture_manual_overrides,
    excluded_source_from_review_item,
    exclusions_from_review_state,
    manual_overrides_from_review_state,
    normalize_excluded_sources,
    normalize_source_handles,
    replay_manual_overrides,
    review_state_matches_source,
    shared_handle_conflicts,
)
from .support_pairing import (
    DoubleSupportSourceIdentity,
    apply_double_support_decisions,
    double_support_candidate_identity,
    double_support_decisions_from_review_state,
    preserve_double_support_result_decisions,
    serialize_double_support_decisions,
)
from .validation import (
    build_problem_records,
    build_review_items,
    validate_candidate_point_pair,
)
from .waler_contact_adjustment import (
    WalerContactAdjustmentPlan,
    apply_waler_contact_adjustment,
    plan_waler_contact_adjustment,
)


@dataclass(frozen=True)
class DXFReviewSnapshot:
    """Read-only application projection consumed by the dialog."""

    world_result: DXFImportResult | None
    result: DXFImportResult | None
    problem_records: tuple[ProblemRecord, ...]
    review_items: tuple[ReviewItem, ...]
    excluded_sources: tuple[ExcludedSource, ...]
    double_support_decisions: Mapping[DoubleSupportSourceIdentity, bool]
    review_confirmations: Mapping[str, str]
    selected_origin_world: Point | None
    coordinate_valid: bool
    import_mode: str
    last_manual_replay_report: ManualReplayReport
    revision: int


@dataclass(frozen=True)
class ReviewMutation:
    """Observable result of one committed application command."""

    changed: bool
    invalidated_confirmations: tuple[str, ...] = ()
    manual_replay: ManualReplayReport | None = None


@dataclass(frozen=True)
class SourceExclusionPlan:
    """A staged exclusion result that is safe to inspect before commit."""

    base_revision: int
    excluded_sources: tuple[ExcludedSource, ...]
    world_result: DXFImportResult
    result: DXFImportResult
    problem_records: tuple[ProblemRecord, ...]
    review_items: tuple[ReviewItem, ...]
    manual_replay: ManualReplayReport


@dataclass(frozen=True)
class ReviewCompletionStatus:
    """Import-completion facts without any presentation decisions."""

    coordinate_valid: bool
    can_import: bool
    warning_count: int
    blocking_error_count: int
    unconfirmed_count: int


class DXFReviewWorkflow:
    """Own the formal and derived state for one DXF Review workflow."""

    def __init__(
        self,
        importer: Any,
        file_path: str | Path,
        *,
        initial_state: Mapping[str, Any] | None = None,
        material_specs: Sequence[Mapping[str, Any]] = (),
        resume_review: bool = False,
        initial_world_result: DXFImportResult | None = None,
    ) -> None:
        self.importer = importer
        self.file_path = Path(file_path)
        self.initial_state = dict(initial_state or {})
        self.material_specs = tuple(
            dict(row) for row in material_specs if isinstance(row, Mapping)
        )
        self.initial_state_matches_source = review_state_matches_source(
            self.initial_state,
            self.importer.source_fingerprint,
            self.file_path,
        )
        if resume_review and not self.initial_state_matches_source:
            raise DXFImportError(
                "此專案保存的 DXF 檢核使用的是不同版本的 DXF。"
                "為避免人工修正套用到錯誤來源，目前無法直接繼續此檢核。"
            )

        restored = exclusions_from_review_state(
            self.initial_state,
            self.importer.source_fingerprint,
        )
        self.excluded_sources = restored.excluded_sources
        self.exclusion_fingerprint_mismatch = restored.fingerprint_mismatch
        self.double_support_decisions: dict[
            DoubleSupportSourceIdentity, bool
        ] = (
            double_support_decisions_from_review_state(self.initial_state)
            if self.initial_state_matches_source
            else {}
        )
        self.review_confirmations = (
            review_confirmations_from_state(self.initial_state)
            if self.initial_state_matches_source
            else {}
        )
        self.layer_roles = self._saved_layer_roles()
        self.import_mode = self._saved_import_mode()
        self.selected_origin_world = self._saved_origin()
        self.coordinate_valid = False
        self.world_result = self._valid_initial_world_result(initial_world_result)
        self.result: DXFImportResult | None = None
        self.problem_records: tuple[ProblemRecord, ...] = ()
        self.review_items: tuple[ReviewItem, ...] = ()
        self.last_manual_replay_report = ManualReplayReport()
        self.revision = 0

        candidate_tolerance = min(
            self.importer.tolerances.duplicate_tolerance_mm,
            self.importer.tolerances.endpoint_tolerance_mm,
            1.0,
        )
        self.candidate_point_store = CandidatePointStore(candidate_tolerance)
        if self.world_result is not None:
            self._rebuild_derived_state()

    def _saved_layer_roles(self) -> dict[str, str]:
        if not self.initial_state_matches_source:
            return {}
        raw = self.initial_state.get("layer_classification", {})
        if not isinstance(raw, Mapping):
            return {}
        return {str(key): str(value) for key, value in raw.items()}

    def _saved_import_mode(self) -> str:
        value = str(
            self.initial_state.get("import_mode", "replace")
            if self.initial_state_matches_source
            else "replace"
        ).strip().lower()
        return value if value in {"replace", "append"} else "replace"

    def _saved_origin(self) -> Point | None:
        if not self.initial_state_matches_source:
            return None
        raw = self.initial_state.get("coordinate_system", {})
        if not isinstance(raw, Mapping) or raw.get("mode") != "local":
            return None
        try:
            coordinate = CoordinateSystem(
                "local",
                float(raw.get("origin_x", 0.0)),
                float(raw.get("origin_y", 0.0)),
                str(raw.get("source", "selected_candidate_point")),
            )
        except (TypeError, ValueError):
            return None
        return coordinate.origin_x, coordinate.origin_y

    def _valid_initial_world_result(
        self,
        result: DXFImportResult | None,
    ) -> DXFImportResult | None:
        if result is None:
            return None
        if (
            str(result.source_fingerprint).strip().upper()
            != str(self.importer.source_fingerprint).strip().upper()
        ):
            return None
        return result

    @property
    def snapshot(self) -> DXFReviewSnapshot:
        return DXFReviewSnapshot(
            world_result=self.world_result,
            result=self.result,
            problem_records=self.problem_records,
            review_items=self.review_items,
            excluded_sources=self.excluded_sources,
            double_support_decisions=dict(self.double_support_decisions),
            review_confirmations=dict(self.review_confirmations),
            selected_origin_world=self.selected_origin_world,
            coordinate_valid=self.coordinate_valid,
            import_mode=self.import_mode,
            last_manual_replay_report=self.last_manual_replay_report,
            revision=self.revision,
        )

    def all_members(
        self,
        result: DXFImportResult | None = None,
    ) -> tuple[Waler | Strut | Brace | AuxiliaryComponent, ...]:
        active = self.result if result is None else result
        if active is None:
            return ()
        return (
            *active.walers,
            *active.struts,
            *active.braces,
            *active.columns,
            *active.beams,
            *active.corner_braces,
        )

    def member_by_id(self, member_id: str) -> Any | None:
        return next(
            (member for member in self.all_members() if member.id == member_id),
            None,
        )

    def review_item_by_key(self, key: str) -> ReviewItem | None:
        return next((item for item in self.review_items if item.key == key), None)

    def review_item_for_member(self, member_id: str) -> ReviewItem | None:
        return next(
            (item for item in self.review_items if item.member_id == member_id),
            None,
        )

    def _current_coordinate_system(self) -> CoordinateSystem:
        if self.selected_origin_world is None:
            return CoordinateSystem()
        return CoordinateSystem(
            "local",
            self.selected_origin_world[0],
            self.selected_origin_world[1],
            "selected_candidate_point",
        )

    def _rebuild_derived_state(self, *, coordinate_mode: str | None = None) -> None:
        if self.world_result is None:
            self.result = None
            self.problem_records = ()
            self.review_items = ()
            self.coordinate_valid = False
            self.candidate_point_store.rebuild(())
            return
        requested_mode = coordinate_mode or (
            "local" if self.selected_origin_world is not None else "world"
        )
        if requested_mode == "local" and self.selected_origin_world is None:
            self.coordinate_valid = False
            self.result = self.world_result
        else:
            self.coordinate_valid = True
            self.result = apply_coordinate_system(
                self.world_result,
                self._current_coordinate_system(),
            )
        self.problem_records = build_problem_records(self.result)
        self.review_items = build_review_items(self.result, self.problem_records)
        self.review_confirmations = valid_review_confirmations(
            self.result,
            self.review_items,
            self.review_confirmations,
        )
        self.candidate_point_store.rebuild(self.all_members())

    def _confirmed_snapshot(self) -> dict[str, str]:
        if self.result is None:
            return {}
        return {
            identity: item.display_id
            for item in self.review_items
            if (identity := review_confirmation_identity(item)) is not None
            and review_item_is_confirmed(
                self.result,
                item,
                self.review_confirmations,
            )
        }

    def confirmed_snapshot(self) -> dict[str, str]:
        return self._confirmed_snapshot()

    def prune_confirmations(self) -> None:
        if self.result is None:
            return
        self.review_confirmations = valid_review_confirmations(
            self.result,
            self.review_items,
            self.review_confirmations,
        )

    def _mutation_result(
        self,
        before_confirmed: Mapping[str, str],
        *,
        initiating_member_ids: Sequence[str] = (),
        changed: bool = True,
        manual_replay: ManualReplayReport | None = None,
    ) -> ReviewMutation:
        after_confirmed = self._confirmed_snapshot()
        initiating = {str(value) for value in initiating_member_ids if str(value)}
        invalidated = tuple(
            display_id
            for identity, display_id in before_confirmed.items()
            if identity not in after_confirmed and display_id not in initiating
        )
        return ReviewMutation(
            changed=changed,
            invalidated_confirmations=tuple(dict.fromkeys(invalidated)),
            manual_replay=manual_replay,
        )

    def _recognize_staged(
        self,
        excluded_sources: Sequence[ExcludedSource],
        manual_overrides: Sequence[Any] = (),
        *,
        layer_roles: Mapping[str, str],
    ) -> tuple[DXFImportResult, ManualReplayReport]:
        staged = self.importer.convert(
            layer_roles=layer_roles,
            coordinate_system=CoordinateSystem(),
            material_specs=self.material_specs,
            excluded_sources=excluded_sources,
        )
        staged, replay_report = replay_manual_overrides(
            staged,
            manual_overrides,
            material_specs=self.material_specs,
            tolerances=self.importer.tolerances,
        )
        candidates = staged.double_support_candidates
        if self.world_result is not None:
            candidates = preserve_double_support_result_decisions(
                self.world_result,
                staged,
            )
        if self.double_support_decisions:
            candidates = apply_double_support_decisions(
                replace(staged, double_support_candidates=candidates),
                self.double_support_decisions,
            )
        if candidates != staged.double_support_candidates:
            staged = rebuild_component_associations(
                replace(staged, double_support_candidates=candidates),
                self.importer.tolerances,
            )
        return staged, replay_report

    def recognize_staged(
        self,
        excluded_sources: Sequence[ExcludedSource],
        manual_overrides: Sequence[Any] = (),
        *,
        layer_roles: Mapping[str, str],
    ) -> tuple[DXFImportResult, ManualReplayReport]:
        """Expose non-mutating recognition for staging and compatibility tests."""

        return self._recognize_staged(
            excluded_sources,
            manual_overrides,
            layer_roles=layer_roles,
        )

    def recognize(self, layer_roles: Mapping[str, str]) -> ReviewMutation:
        before_confirmed = self._confirmed_snapshot()
        if self.world_result is not None:
            overrides = capture_manual_overrides(self.world_result)
        elif self.initial_state_matches_source:
            overrides = manual_overrides_from_review_state(self.initial_state)
        else:
            overrides = ()
        try:
            staged, replay_report = self._recognize_staged(
                self.excluded_sources,
                overrides,
                layer_roles=layer_roles,
            )
        except Exception:
            # Preserve the current observable dialog contract for a failed
            # normal recognition pass.  Exclusion staging uses a separate path
            # and never clears the active result.
            self.world_result = None
            self._rebuild_derived_state()
            self.revision += 1
            raise
        self.layer_roles = dict(layer_roles)
        self.world_result = staged
        self.excluded_sources = staged.excluded_sources
        self.last_manual_replay_report = replay_report
        self._rebuild_derived_state()
        self.revision += 1
        return self._mutation_result(
            before_confirmed,
            manual_replay=replay_report,
        )

    def reapply_coordinate_system(self, mode: str | None = None) -> ReviewMutation:
        before_confirmed = self._confirmed_snapshot()
        self._rebuild_derived_state(coordinate_mode=mode)
        return self._mutation_result(before_confirmed, changed=False)

    def set_coordinate_origin(self, point: Point | None) -> ReviewMutation:
        before_confirmed = self._confirmed_snapshot()
        normalized = None if point is None else (float(point[0]), float(point[1]))
        if normalized == self.selected_origin_world:
            return ReviewMutation(changed=False)
        self.selected_origin_world = normalized
        self._rebuild_derived_state()
        self.revision += 1
        return self._mutation_result(before_confirmed)

    def set_import_mode(self, mode: str) -> bool:
        normalized = str(mode or "replace").strip().lower()
        if normalized not in {"replace", "append"}:
            normalized = "replace"
        changed = normalized != self.import_mode
        self.import_mode = normalized
        return changed

    def commit_double_support_candidates(
        self,
        updated: Sequence[Any],
    ) -> ReviewMutation:
        if self.world_result is None or self.result is None:
            return ReviewMutation(changed=False)
        updated = tuple(updated)
        previous_by_id = {
            item.id: item for item in self.result.double_support_candidates
        }
        changed = tuple(
            item
            for item in updated
            if item.id in previous_by_id
            and previous_by_id[item.id].accepted != item.accepted
        )
        if not changed:
            return ReviewMutation(changed=False)
        before_confirmed = self._confirmed_snapshot()
        for item in changed:
            identity = double_support_candidate_identity(self.world_result, item)
            if identity is not None:
                self.double_support_decisions[identity] = item.accepted
        self.world_result = rebuild_component_associations(
            replace(self.world_result, double_support_candidates=updated),
            self.importer.tolerances,
        )
        self._rebuild_derived_state()
        self.revision += 1
        return self._mutation_result(before_confirmed)

    def validate_candidate_change(
        self,
        member_id: str,
        start_point_id: str,
        end_point_id: str,
    ) -> tuple[Any, ...]:
        member = self.member_by_id(member_id)
        if member is None or self.result is None:
            raise DXFImportError("請先選取構件。")
        return validate_candidate_point_pair(
            member,
            start_point_id,
            end_point_id,
            self.importer.tolerances,
            self.result.walers,
        )

    def apply_candidate_change(
        self,
        member_id: str,
        start_point_id: str,
        end_point_id: str,
        selection_source: str,
    ) -> ReviewMutation:
        if self.world_result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        before_confirmed = self._confirmed_snapshot()
        state = SelectionState(
            selected_component_id=member_id,
            pending_start_point_id=start_point_id,
            pending_end_point_id=end_point_id,
            pending_selection_source=selection_source,
        )
        start = self.candidate_point_store.get(member_id, start_point_id)
        end = self.candidate_point_store.get(member_id, end_point_id)
        if start is None or end is None:
            raise DXFImportError("待套用候選點不在 CandidatePointStore 中。")
        self.world_result = apply_candidate_point_selection(
            self.world_result,
            state.selected_component_id,
            state.pending_start_point_id,
            state.pending_end_point_id,
            self.importer.tolerances,
            selection_source=state.pending_selection_source,
        )
        self._rebuild_derived_state()
        self.revision += 1
        return self._mutation_result(
            before_confirmed,
            initiating_member_ids=(member_id,),
        )

    def add_cad_candidate_line(
        self,
        member_id: str,
        start: Point,
        end: Point,
    ) -> tuple[str, str, ReviewMutation]:
        if self.world_result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        before_confirmed = self._confirmed_snapshot()
        self.world_result, start_id, end_id = add_cad_candidate_points(
            self.world_result,
            member_id,
            start,
            end,
            self.importer.tolerances,
        )
        self._rebuild_derived_state()
        self.revision += 1
        mutation = self._mutation_result(
            before_confirmed,
            initiating_member_ids=(member_id,),
        )
        return start_id, end_id, mutation

    def set_material_spec(
        self,
        member_id: str,
        material_spec: str,
    ) -> ReviewMutation:
        if self.world_result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        before_confirmed = self._confirmed_snapshot()
        self.world_result = set_member_material_spec(
            self.world_result,
            member_id,
            material_spec,
        )
        self._rebuild_derived_state()
        self.revision += 1
        return self._mutation_result(
            before_confirmed,
            initiating_member_ids=(member_id,),
        )

    def preview_waler_contact_adjustment(
        self,
        waler_id: str,
        **dimensions: Any,
    ) -> WalerContactAdjustmentPlan:
        if self.world_result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        return plan_waler_contact_adjustment(
            self.world_result,
            waler_id,
            tolerances=self.importer.tolerances,
            **dimensions,
        )

    def apply_waler_contact_adjustment(
        self,
        waler_id: str,
        **dimensions: Any,
    ) -> ReviewMutation:
        if self.world_result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        before_confirmed = self._confirmed_snapshot()
        self.world_result = apply_waler_contact_adjustment(
            self.world_result,
            waler_id,
            tolerances=self.importer.tolerances,
            **dimensions,
        )
        self._rebuild_derived_state()
        self.revision += 1
        return self._mutation_result(
            before_confirmed,
            initiating_member_ids=(waler_id,),
        )

    def is_review_item_confirmed(self, item: ReviewItem | None) -> bool:
        return bool(
            item is not None
            and self.result is not None
            and review_item_is_confirmed(
                self.result,
                item,
                self.review_confirmations,
            )
        )

    def unconfirmed_formal_review_items(self) -> tuple[ReviewItem, ...]:
        if self.result is None:
            return ()
        return unconfirmed_formal_review_items(
            self.result,
            self.review_items,
            self.review_confirmations,
        )

    def confirm(self, item: ReviewItem) -> bool:
        if self.result is None:
            return False
        updated = confirm_review_item(
            self.result,
            item,
            self.review_confirmations,
        )
        if updated == self.review_confirmations:
            return False
        self.review_confirmations = updated
        self.revision += 1
        return True

    def source_exclusion_disabled_reason(self, item: ReviewItem | None) -> str:
        if item is None:
            return "請先選取 Formal、待修或已排除來源。"
        if not item.role or not normalize_source_handles(item.source_handles):
            return "此項目沒有可安全識別的 DXF 來源，無法使用來源排除。"
        if item.status == "excluded":
            return ""
        conflicts = shared_handle_conflicts(item, self.review_items)
        if not conflicts:
            return ""
        details = "；".join(
            f"Handle {conflict.handle} 同時由 {', '.join(conflict.owner_labels)} 使用"
            for conflict in conflicts
        )
        return f"此來源有共用 Handle，不能安全單獨排除：{details}。"

    @staticmethod
    def _source_geometry_signature(result: DXFImportResult) -> tuple[Any, ...]:
        return tuple(
            (
                geometry.role,
                geometry.source_handle,
                geometry.points,
                geometry.closed,
                geometry.source_layer,
                geometry.source_entity_type,
            )
            for geometry in result.source_geometry
        )

    def plan_source_exclusion_change(
        self,
        candidate_exclusions: Sequence[ExcludedSource],
    ) -> SourceExclusionPlan:
        if self.world_result is None or self.result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        normalized = normalize_excluded_sources(candidate_exclusions)
        overrides = [*capture_manual_overrides(self.world_result)]
        overrides.extend(
            source.manual_override
            for source in self.excluded_sources
            if source.manual_override is not None
        )
        overrides.extend(
            source.manual_override
            for source in normalized
            if source.manual_override is not None
        )
        staged_world, replay_report = self._recognize_staged(
            normalized,
            overrides,
            layer_roles=self.world_result.layer_classification,
        )
        if staged_world.source_fingerprint != self.world_result.source_fingerprint:
            raise DXFImportError("暫存檢核的 DXF 來源指紋不一致。")
        if self._source_geometry_signature(staged_world) != self._source_geometry_signature(
            self.world_result
        ):
            raise DXFImportError("暫存檢核未完整保留原始 DXF 來源幾何。")
        staged_result = apply_coordinate_system(
            staged_world,
            self.result.coordinate_system,
        )
        records = build_problem_records(staged_result)
        review_items = build_review_items(staged_result, records)
        return SourceExclusionPlan(
            base_revision=self.revision,
            excluded_sources=normalized,
            world_result=staged_world,
            result=staged_result,
            problem_records=records,
            review_items=review_items,
            manual_replay=replay_report,
        )

    def plan_source_exclusion_for_item(
        self,
        item: ReviewItem,
    ) -> tuple[SourceExclusionPlan, bool, str]:
        identity = canonical_source_identity(item.role, item.source_handles)
        restoring = item.status == "excluded"
        if restoring:
            candidate_exclusions = tuple(
                source
                for source in self.excluded_sources
                if source.identity != identity
            )
        else:
            if self.world_result is None:
                raise DXFImportError("請先完成 DXF 辨識。")
            candidate_exclusions = (
                *self.excluded_sources,
                excluded_source_from_review_item(item, self.world_result),
            )
        return (
            self.plan_source_exclusion_change(candidate_exclusions),
            restoring,
            identity,
        )

    def commit_source_exclusion_plan(
        self,
        plan: SourceExclusionPlan,
        *,
        initiating_member_ids: Sequence[str] = (),
    ) -> ReviewMutation:
        if plan.base_revision != self.revision:
            raise DXFImportError("DXF Review 已變更，請重新預覽來源排除影響。")
        before_confirmed = self._confirmed_snapshot()
        self.excluded_sources = plan.excluded_sources
        self.world_result = plan.world_result
        self.result = plan.result
        self.problem_records = plan.problem_records
        self.review_items = plan.review_items
        self.last_manual_replay_report = plan.manual_replay
        self.review_confirmations = valid_review_confirmations(
            self.result,
            self.review_items,
            self.review_confirmations,
        )
        self.candidate_point_store.rebuild(self.all_members())
        self.revision += 1
        return self._mutation_result(
            before_confirmed,
            initiating_member_ids=initiating_member_ids,
            manual_replay=plan.manual_replay,
        )

    @staticmethod
    def review_item_identity(item: ReviewItem) -> str:
        return canonical_source_identity(item.role, item.source_handles)

    @classmethod
    def review_item_for_identity(
        cls,
        items: Sequence[ReviewItem],
        identity: str,
        *,
        excluded: bool,
    ) -> ReviewItem | None:
        return next(
            (
                item
                for item in items
                if cls.review_item_identity(item) == identity
                and (item.status == "excluded") == excluded
            ),
            None,
        )

    def completion_status(self) -> ReviewCompletionStatus:
        if self.result is None:
            return ReviewCompletionStatus(False, False, 0, 0, 0)
        counts = Counter(message.severity for message in self.result.messages)
        blocking = counts["error"] + counts["critical"]
        return ReviewCompletionStatus(
            coordinate_valid=self.coordinate_valid,
            can_import=self.result.can_import and self.coordinate_valid,
            warning_count=counts["warning"],
            blocking_error_count=blocking,
            unconfirmed_count=len(self.unconfirmed_formal_review_items()),
        )

    def serialize_review_state(
        self,
        *,
        layer_roles: Mapping[str, str] | None = None,
        import_mode: str | None = None,
    ) -> dict[str, Any]:
        if layer_roles is not None:
            self.layer_roles = dict(layer_roles)
        if import_mode is not None:
            self.set_import_mode(import_mode)
        self.review_confirmations = (
            valid_review_confirmations(
                self.result,
                self.review_items,
                self.review_confirmations,
            )
            if self.result is not None
            else self.review_confirmations
        )
        if self.result is not None:
            state = self.result.to_debug_dict()
        elif self.initial_state_matches_source:
            state = copy.deepcopy(self.initial_state)
        else:
            state = {}
        replay_source = self.world_result or self.result
        manual_overrides = (
            capture_manual_overrides(replay_source)
            if replay_source is not None
            else manual_overrides_from_review_state(self.initial_state)
        )
        state.update(
            {
                "review_state_version": 2,
                "source_path": str(self.file_path.resolve()),
                "source_fingerprint": self.importer.source_fingerprint,
                "layer_names": list(self.importer.layer_names),
                "layer_classification": dict(self.layer_roles),
                "layer_assignments": [
                    {"layer_name": name, "layer_type": role}
                    for name, role in self.layer_roles.items()
                ],
                "coordinate_system": asdict(self._current_coordinate_system()),
                "import_mode": self.import_mode,
                "excluded_sources": [
                    asdict(source) for source in self.excluded_sources
                ],
                "manual_overrides": [
                    asdict(override) for override in manual_overrides
                ],
                "double_support_decisions": serialize_double_support_decisions(
                    self.double_support_decisions
                ),
                "review_confirmations": serialize_review_confirmations(
                    self.review_confirmations
                ),
            }
        )
        return state
