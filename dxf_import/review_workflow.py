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
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .candidate_points import (
    CandidatePointStore,
    add_cad_candidate_points,
    ambiguous_column_repair_options,
    apply_candidate_point_selection,
    rebuild_component_associations,
)
from .corner_brace_repair import (
    CornerBraceRepairPlan,
    apply_corner_brace_repair,
    plan_corner_brace_repair as build_corner_brace_repair_plan,
    repair_subject_key,
    repair_subject_signature,
)
from .geometry import Point
from .material_recognition import set_member_material_spec
from .models import (
    AuxiliaryComponent,
    Brace,
    ColumnAssociationDecision,
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
    baseline_for_visible_brace_edit,
    plan_waler_contact_adjustment,
)
from .waler_engineering_line_repair import (
    formalize_waler_engineering_line,
    is_waler_engineering_line_repair_eligible,
)


@dataclass(frozen=True)
class PendingSourceExclusionDraft:
    """Immutable user intent collected before canonical recognition."""

    base_revision: int
    source_fingerprint: str
    generation: int
    sources: tuple[ExcludedSource, ...] = ()
    state: str = "EMPTY"

    @property
    def identities(self) -> tuple[str, ...]:
        return tuple(source.identity for source in self.sources)

    @property
    def is_empty(self) -> bool:
        return not self.sources


@dataclass(frozen=True)
class DXFReviewSnapshot:
    """Read-only application projection consumed by the dialog."""

    world_result: DXFImportResult | None
    result: DXFImportResult | None
    problem_records: tuple[ProblemRecord, ...]
    review_items: tuple[ReviewItem, ...]
    excluded_sources: tuple[ExcludedSource, ...]
    pending_source_exclusion: PendingSourceExclusionDraft
    double_support_decisions: Mapping[DoubleSupportSourceIdentity, bool]
    column_association_decisions: Mapping[tuple[str, ...], ColumnAssociationDecision]
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
    effects: ReviewMutationEffects | None = None


@dataclass(frozen=True)
class ReviewMutationEffects:
    """UI-neutral description of projections invalidated by one commit."""

    committed_revision: int
    source_geometry_changed: bool = False
    source_bounds_changed: bool = False
    changed_source_identities: tuple[str, ...] = ()
    changed_source_handles: tuple[str, ...] = ()
    excluded_source_identities: tuple[str, ...] = ()
    engineering_members_changed: bool = False
    problems_changed: bool = False
    review_items_changed: bool = False
    candidate_points_changed: bool = False
    selection_targets_invalidated: bool = False
    hit_index_invalidated: bool = False


@dataclass(frozen=True)
class SourceExclusionPlan:
    """A staged exclusion result that is safe to inspect before commit."""

    base_revision: int
    excluded_sources: tuple[ExcludedSource, ...]
    world_result: DXFImportResult
    result: DXFImportResult
    problem_records: tuple[ProblemRecord, ...]
    review_items: tuple[ReviewItem, ...]
    review_confirmations: Mapping[str, str]
    candidate_point_store: CandidatePointStore
    manual_replay: ManualReplayReport
    effects: ReviewMutationEffects
    source_fingerprint: str
    pending_generation: int | None = None
    pending_source_identities: tuple[str, ...] = ()
    pending_plan_token: int | None = None


@dataclass(frozen=True)
class ColumnAssociationRepairPlan:
    """Revision-bound, side-effect-free view of one two-Strut ambiguity."""

    base_revision: int
    column_source_handles: tuple[str, ...]
    column_id: str
    candidate_strut_ids: tuple[str, str]
    candidate_strut_sources: tuple[tuple[str, ...], tuple[str, ...]]
    options: tuple[tuple[float, str, float, Point], ...]
    source_fingerprint: str
    status: str
    selected_strut_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class WalerEngineeringLineRepairPlan:
    """Revision-bound staged adoption of one formal Waler contact line."""

    base_revision: int
    source_fingerprint: str
    member_id: str
    source_handles: tuple[str, ...]
    start_point_id: str
    end_point_id: str
    world_start: Point
    world_end: Point
    input_kind: str
    selected_candidate_id: str
    world_result: DXFImportResult
    result: DXFImportResult
    problem_records: tuple[ProblemRecord, ...]
    review_items: tuple[ReviewItem, ...]
    review_confirmations: Mapping[str, str]
    invalidated_confirmations: tuple[str, ...]


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
        self.column_association_decisions: dict[
            tuple[str, ...], ColumnAssociationDecision
        ] = {}
        if self.initial_state_matches_source:
            raw_decisions = self.initial_state.get("column_association_decisions", ())
            if isinstance(raw_decisions, (list, tuple)):
                for raw in raw_decisions:
                    if not isinstance(raw, Mapping):
                        continue
                    try:
                        decision = ColumnAssociationDecision(**raw)
                    except (TypeError, ValueError):
                        continue
                    self.column_association_decisions[decision.column_source_handles] = decision
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
        self._pending_source_exclusion_draft = PendingSourceExclusionDraft(
            base_revision=self.revision,
            source_fingerprint=str(self.importer.source_fingerprint),
            generation=0,
        )
        self._pending_source_exclusion_plan_sequence = 0
        self._active_pending_source_exclusion_plan_token: int | None = None

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
            pending_source_exclusion=self.pending_source_exclusion_draft,
            double_support_decisions=dict(self.double_support_decisions),
            column_association_decisions=dict(self.column_association_decisions),
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

    def _rebuild_derived_state(
        self,
        *,
        coordinate_mode: str | None = None,
        rebuild_associations: bool = True,
    ) -> None:
        if self.world_result is None:
            self.result = None
            self.problem_records = ()
            self.review_items = ()
            self.coordinate_valid = False
            self.candidate_point_store.rebuild(())
            return
        if rebuild_associations and self.column_association_decisions:
            self.world_result = rebuild_component_associations(
                self.world_result,
                self.importer.tolerances,
                column_decisions=tuple(
                    self.column_association_decisions.values()
                ),
            )
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
        return self._confirmed_projection(
            self.result,
            self.review_items,
            self.review_confirmations,
        )

    @staticmethod
    def _confirmed_projection(
        result: DXFImportResult,
        items: Sequence[ReviewItem],
        confirmations: Mapping[str, str],
    ) -> dict[str, str]:
        return {
            identity: item.display_id
            for item in items
            if (identity := review_confirmation_identity(item)) is not None
            and review_item_is_confirmed(
                result,
                item,
                confirmations,
            )
        }

    def confirmed_snapshot(self) -> dict[str, str]:
        return self._confirmed_snapshot()

    def prune_confirmations(self) -> None:
        self.require_no_pending_source_exclusions()
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
        effects: ReviewMutationEffects | None = None,
        after_confirmed: Mapping[str, str] | None = None,
    ) -> ReviewMutation:
        current_confirmed = (
            self._confirmed_snapshot()
            if after_confirmed is None
            else after_confirmed
        )
        initiating = {str(value) for value in initiating_member_ids if str(value)}
        invalidated = tuple(
            display_id
            for identity, display_id in before_confirmed.items()
            if identity not in current_confirmed and display_id not in initiating
        )
        return ReviewMutation(
            changed=changed,
            invalidated_confirmations=tuple(dict.fromkeys(invalidated)),
            manual_replay=manual_replay,
            effects=effects,
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
            review_confirmations=self.review_confirmations,
            confirmation_coordinate_system=self._current_coordinate_system(),
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
        staged = rebuild_component_associations(
            replace(staged, double_support_candidates=candidates),
            self.importer.tolerances,
            column_decisions=tuple(self.column_association_decisions.values()),
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

        self.require_no_pending_source_exclusions()
        return self._recognize_staged(
            excluded_sources,
            manual_overrides,
            layer_roles=layer_roles,
        )

    def install_staged_recovery(
        self,
        world_result: DXFImportResult,
        *,
        layer_roles: Mapping[str, str],
        excluded_sources: Sequence[ExcludedSource],
        double_support_decisions: Mapping[
            DoubleSupportSourceIdentity,
            bool,
        ],
        review_confirmations: Mapping[str, str],
        manual_replay_report: ManualReplayReport,
    ) -> None:
        """Install one already-validated candidate stage into this workflow.

        Recovery matching and decision classification stay in the recovery
        planner. This method only uses the workflow's existing rebuild and
        confirmation-validation boundary to make the candidate stage live.
        """

        self.require_no_pending_source_exclusions()
        if (
            str(world_result.source_fingerprint).strip().upper()
            != str(self.importer.source_fingerprint).strip().upper()
        ):
            raise DXFImportError("候選辨識結果與目前 DXF 來源不一致。")
        decisions = dict(double_support_decisions)
        candidates = apply_double_support_decisions(world_result, decisions)
        if candidates != world_result.double_support_candidates:
            world_result = rebuild_component_associations(
                replace(world_result, double_support_candidates=candidates),
                self.importer.tolerances,
            )
        self.layer_roles = dict(layer_roles)
        self.world_result = world_result
        self.excluded_sources = tuple(excluded_sources)
        self.double_support_decisions = decisions
        self.review_confirmations = dict(review_confirmations)
        self.last_manual_replay_report = manual_replay_report
        self._rebuild_derived_state()
        self.revision += 1

    def recognize(self, layer_roles: Mapping[str, str]) -> ReviewMutation:
        self.require_no_pending_source_exclusions()
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
        self.require_no_pending_source_exclusions()
        before_confirmed = self._confirmed_snapshot()
        self._rebuild_derived_state(coordinate_mode=mode)
        return self._mutation_result(before_confirmed, changed=False)

    def set_coordinate_origin(self, point: Point | None) -> ReviewMutation:
        self.require_no_pending_source_exclusions()
        before_confirmed = self._confirmed_snapshot()
        normalized = None if point is None else (float(point[0]), float(point[1]))
        if normalized == self.selected_origin_world:
            return ReviewMutation(changed=False)
        self.selected_origin_world = normalized
        self._rebuild_derived_state()
        self.revision += 1
        return self._mutation_result(before_confirmed)

    def set_import_mode(self, mode: str) -> bool:
        self.require_no_pending_source_exclusions()
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
        self.require_no_pending_source_exclusions()
        if self.world_result is None or self.result is None:
            return ReviewMutation(changed=False)
        requested = {
            item.id: item
            for item in updated
            if item.qualification_status == "eligible"
        }
        updated = tuple(
            replace(item, accepted=requested[item.id].accepted)
            if item.qualification_status == "eligible" and item.id in requested
            else item
            for item in self.world_result.double_support_candidates
        )
        previous_by_id = {
            item.id: item for item in self.result.double_support_candidates
        }
        changed = tuple(
            item
            for item in updated
            if item.id in previous_by_id
            and item.qualification_status == "eligible"
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
            **(
                {"column_decisions": tuple(self.column_association_decisions.values())}
                if self.column_association_decisions else {}
            ),
        )
        self._rebuild_derived_state(rebuild_associations=False)
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
        self.require_no_pending_source_exclusions()
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
        target = next(
            (
                member
                for member in self.world_result.braces
                if member.id == member_id
            ),
            None,
        )
        replacement_baseline = None
        if isinstance(target, Brace):
            replacement_baseline = baseline_for_visible_brace_edit(
                self.world_result,
                member_id,
                start.world_point,
                end.world_point,
                self.importer.tolerances,
            )
        staged = apply_candidate_point_selection(
            self.world_result,
            state.selected_component_id,
            state.pending_start_point_id,
            state.pending_end_point_id,
            self.importer.tolerances,
            selection_source=state.pending_selection_source,
        )
        if replacement_baseline is not None:
            staged_brace = next(
                (item for item in staged.braces if item.id == member_id),
                None,
            )
            if (
                staged_brace is None
                or not staged_brace.has_formal_connection
                or staged_brace.from_waler
                != replacement_baseline.from_waler_id
                or staged_brace.to_waler != replacement_baseline.to_waler_id
                or tuple(staged_brace.source_handles)
                != replacement_baseline.source_handles
            ):
                raise DXFImportError(
                    f"{member_id} 人工端點未能維持原本兩端正式圍令連接，修改已取消。"
                )
            staged = replace(
                staged,
                brace_adjustment_baselines=tuple(
                    replacement_baseline
                    if item.brace_id == member_id
                    else item
                    for item in staged.brace_adjustment_baselines
                ),
            )
        self.world_result = staged
        self._rebuild_derived_state()
        self.revision += 1
        return self._mutation_result(
            before_confirmed,
            initiating_member_ids=(member_id,),
        )

    def plan_waler_engineering_line_repair(
        self,
        member_id: str,
        start_point_id: str,
        end_point_id: str,
        input_kind: str,
        *,
        selected_candidate_id: str = "",
    ) -> WalerEngineeringLineRepairPlan:
        """Stage an explicit Waler formalization without mutating live state."""

        self.require_no_pending_source_exclusions()
        if self.world_result is None or self.result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        matches = tuple(
            waler for waler in self.world_result.walers if waler.id == member_id
        )
        if len(matches) != 1 or not is_waler_engineering_line_repair_eligible(matches[0]):
            raise DXFImportError("此圍令不可採用人工正式工程線。")
        target = matches[0]
        source = normalize_source_handles(target.source_handles)
        if not source:
            raise DXFImportError("圍令來源 identity 不得為空。")
        start = self.candidate_point_store.get(member_id, start_point_id)
        end = self.candidate_point_store.get(member_id, end_point_id)
        if start is None or end is None:
            raise DXFImportError("待採用候選點不在 CandidatePointStore 中。")

        staged_world = formalize_waler_engineering_line(
            self.world_result,
            source,
            start.world_point,
            end.world_point,
            input_kind=input_kind,
            tolerances=self.importer.tolerances,
            selected_candidate_id=selected_candidate_id,
        )
        staged_result = apply_coordinate_system(
            staged_world,
            self._current_coordinate_system(),
        )
        records = build_problem_records(staged_result)
        items = build_review_items(staged_result, records)
        confirmations = valid_review_confirmations(
            staged_result,
            items,
            self.review_confirmations,
        )
        before_confirmed = self._confirmed_snapshot()
        after_confirmed = {
            identity: item.display_id
            for item in items
            if (identity := review_confirmation_identity(item)) is not None
            and review_item_is_confirmed(staged_result, item, confirmations)
        }
        invalidated = tuple(
            display_id
            for identity, display_id in before_confirmed.items()
            if identity not in after_confirmed and display_id != member_id
        )
        return WalerEngineeringLineRepairPlan(
            base_revision=self.revision,
            source_fingerprint=str(self.world_result.source_fingerprint),
            member_id=member_id,
            source_handles=source,
            start_point_id=start_point_id,
            end_point_id=end_point_id,
            world_start=start.world_point,
            world_end=end.world_point,
            input_kind=input_kind,
            selected_candidate_id=selected_candidate_id,
            world_result=staged_world,
            result=staged_result,
            problem_records=records,
            review_items=items,
            review_confirmations=confirmations,
            invalidated_confirmations=tuple(dict.fromkeys(invalidated)),
        )

    def commit_waler_engineering_line_repair(
        self,
        plan: WalerEngineeringLineRepairPlan,
    ) -> ReviewMutation:
        """Commit a still-current staged Waler decision atomically."""

        self.require_no_pending_source_exclusions()
        if self.world_result is None or self.result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        if plan.base_revision != self.revision:
            raise DXFImportError("DXF Review 已變更，請重新預覽圍令正式工程線。")
        current_fingerprint = str(self.world_result.source_fingerprint)
        importer_fingerprint = str(self.importer.source_fingerprint)
        if (
            current_fingerprint.strip().upper()
            != plan.source_fingerprint.strip().upper()
            or importer_fingerprint.strip().upper()
            != plan.source_fingerprint.strip().upper()
        ):
            raise DXFImportError("DXF 來源已變更，請重新預覽圍令正式工程線。")
        current = self.plan_waler_engineering_line_repair(
            plan.member_id,
            plan.start_point_id,
            plan.end_point_id,
            plan.input_kind,
            selected_candidate_id=plan.selected_candidate_id,
        )
        if (
            current.source_handles != plan.source_handles
            or current.world_start != plan.world_start
            or current.world_end != plan.world_end
            or current.world_result != plan.world_result
        ):
            raise DXFImportError("圍令候選線或來源 identity 已變更，請重新預覽。")

        before_confirmed = self._confirmed_snapshot()
        self.world_result = plan.world_result
        self.result = plan.result
        self.problem_records = plan.problem_records
        self.review_items = plan.review_items
        self.review_confirmations = dict(plan.review_confirmations)
        self.coordinate_valid = True
        self.candidate_point_store.rebuild(self.all_members())
        self.revision += 1
        mutation = self._mutation_result(
            before_confirmed,
            initiating_member_ids=(plan.member_id,),
        )
        return mutation

    def add_cad_candidate_line(
        self,
        member_id: str,
        start: Point,
        end: Point,
    ) -> tuple[str, str, ReviewMutation]:
        self.require_no_pending_source_exclusions()
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
        self.require_no_pending_source_exclusions()
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

    def plan_column_association_repair(
        self,
        column_id: str,
    ) -> ColumnAssociationRepairPlan:
        self.require_no_pending_source_exclusions()
        if self.world_result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        matches = [column for column in self.world_result.columns if column.id == column_id]
        if len(matches) != 1:
            raise DXFImportError("所選中間柱已不存在，請重新預覽。")
        column = matches[0]
        source = normalize_source_handles(column.source_handles)
        if not source or sum(normalize_source_handles(item.source_handles) == source for item in self.world_result.columns) != 1:
            raise DXFImportError("中間柱來源身分不唯一，無法安全修補。")
        saved = self.column_association_decisions.get(source)
        repair = ambiguous_column_repair_options(
            column, self.world_result.struts, self.importer.tolerances,
            double_support_candidates=self.world_result.double_support_candidates,
        )
        if repair.reason:
            if saved is None:
                raise DXFImportError(f"此中間柱目前不可修補：{repair.reason}。")
            ids_by_source = {
                normalize_source_handles(strut.source_handles): strut.id for strut in self.world_result.struts
                if strut.source_handles
            }
            candidate_sources = saved.candidate_strut_sources
            return ColumnAssociationRepairPlan(
                self.revision, source, column.id,
                tuple(ids_by_source.get(item, "") for item in candidate_sources),
                candidate_sources, (), self.world_result.source_fingerprint,
                "requires_review", (),
            )
        struts_by_id = {strut.id: strut for strut in self.world_result.struts}
        candidate_ids = tuple(option[1] for option in repair.options)
        candidate_sources = tuple(normalize_source_handles(struts_by_id[item].source_handles) for item in candidate_ids)
        if any(
            not handles
            or sum(normalize_source_handles(strut.source_handles) == handles for strut in self.world_result.struts) != 1
            for handles in candidate_sources
        ):
            raise DXFImportError("候選支撐來源身分不唯一，無法安全修補。")
        selected_ids = tuple(
            strut.id for strut in self.world_result.struts
            if saved is not None and normalize_source_handles(strut.source_handles) in saved.selected_strut_sources
        )
        status = "unresolved"
        if saved is not None:
            status = "requires_review" if any(
                item.code == "COLUMN_ASSOCIATION_REQUIRES_REVIEW"
                and normalize_source_handles(item.source_handles) == source
                for item in self.world_result.messages
            ) else "repaired"
        return ColumnAssociationRepairPlan(
            self.revision, source, column.id, candidate_ids,
            candidate_sources, repair.options,
            self.world_result.source_fingerprint, status, selected_ids,
        )

    def _stage_column_repair(
        self,
        decisions: Mapping[tuple[str, ...], ColumnAssociationDecision],
    ) -> tuple[DXFImportResult, DXFImportResult, tuple[ProblemRecord, ...], tuple[ReviewItem, ...], dict[str, str], CandidatePointStore]:
        assert self.world_result is not None and self.result is not None
        staged_world = rebuild_component_associations(
            self.world_result, self.importer.tolerances,
            column_decisions=tuple(decisions.values()),
        )
        staged_result = apply_coordinate_system(staged_world, self.result.coordinate_system)
        records = build_problem_records(staged_result)
        items = build_review_items(staged_result, records)
        confirmations = valid_review_confirmations(staged_result, items, self.review_confirmations)
        store = CandidatePointStore(self.candidate_point_store.tolerance)
        store.rebuild(self._result_members_for_store(staged_result))
        return staged_world, staged_result, records, items, confirmations, store

    def _install_column_repair_stage(
        self,
        decisions: dict[tuple[str, ...], ColumnAssociationDecision],
        stage: tuple[DXFImportResult, DXFImportResult, tuple[ProblemRecord, ...], tuple[ReviewItem, ...], dict[str, str], CandidatePointStore],
    ) -> None:
        self.column_association_decisions = decisions
        (
            self.world_result, self.result, self.problem_records,
            self.review_items, self.review_confirmations,
            self.candidate_point_store,
        ) = stage
        self.revision += 1

    def commit_column_association_repair(
        self,
        plan: ColumnAssociationRepairPlan,
        selected_strut_ids: Sequence[str],
    ) -> ReviewMutation:
        self.require_no_pending_source_exclusions()
        if self.world_result is None or self.result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        if plan.base_revision != self.revision:
            raise DXFImportError("DXF Review 已變更，請重新預覽中間柱關聯。")
        current = self.plan_column_association_repair(plan.column_id)
        if current != plan or current.source_fingerprint != self.importer.source_fingerprint:
            raise DXFImportError("中間柱候選或來源已變更，請重新預覽。")
        selected = tuple(dict.fromkeys(selected_strut_ids))
        if not selected or len(selected) != len(selected_strut_ids) or not set(selected).issubset(current.candidate_strut_ids):
            raise DXFImportError("必須明確選擇列出的第一支、第二支或兩支支撐。")
        source_by_id = dict(zip(current.candidate_strut_ids, current.candidate_strut_sources))
        decision = ColumnAssociationDecision(
            current.column_source_handles, current.candidate_strut_sources,
            tuple(source_by_id[item] for item in selected),
            current.source_fingerprint, current.column_id,
        )
        decisions = dict(self.column_association_decisions)
        decisions[current.column_source_handles] = decision
        before_confirmed = self._confirmed_snapshot()
        stage = self._stage_column_repair(decisions)
        if not any(
            item.code == "COLUMN_ASSOCIATION_MANUALLY_RESOLVED"
            and normalize_source_handles(item.source_handles) == current.column_source_handles
            for item in stage[0].messages
        ):
            raise DXFImportError("人工關聯重新驗證失敗，未採用決策。")
        self._install_column_repair_stage(decisions, stage)
        return self._mutation_result(before_confirmed)

    def withdraw_column_association_repair(
        self,
        plan: ColumnAssociationRepairPlan,
    ) -> ReviewMutation:
        self.require_no_pending_source_exclusions()
        if self.world_result is None or self.result is None or plan.base_revision != self.revision:
            raise DXFImportError("DXF Review 已變更，請重新預覽中間柱關聯。")
        current = self.plan_column_association_repair(plan.column_id)
        if current != plan or current.column_source_handles not in self.column_association_decisions:
            raise DXFImportError("人工關聯已變更或不存在，請重新預覽。")
        decisions = dict(self.column_association_decisions)
        del decisions[current.column_source_handles]
        before_confirmed = self._confirmed_snapshot()
        stage = self._stage_column_repair(decisions)
        self._install_column_repair_stage(decisions, stage)
        return self._mutation_result(before_confirmed)

    def preview_waler_contact_adjustment(
        self,
        waler_id: str,
        **dimensions: Any,
    ) -> WalerContactAdjustmentPlan:
        self.require_no_pending_source_exclusions()
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
        self.require_no_pending_source_exclusions()
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

    def plan_corner_brace_repair(
        self,
        item_or_key: ReviewItem | str,
    ) -> CornerBraceRepairPlan:
        """Build a side-effect-free STEP4 CornerBrace repair preview."""

        self.require_no_pending_source_exclusions()
        if self.world_result is None or self.result is None:
            raise DXFImportError("請先完成 DXF 辨識，再修補角撐。")
        item = (
            item_or_key
            if isinstance(item_or_key, ReviewItem)
            else self.review_item_by_key(str(item_or_key))
        )
        if item is None:
            raise DXFImportError("所選角撐檢視項目已不存在。")
        return build_corner_brace_repair_plan(
            self.world_result,
            item,
            base_revision=self.revision,
            review_items=self.review_items,
            confirmations=self.review_confirmations,
            confirmation_result=self.result,
            tolerances=self.importer.tolerances,
        )

    def _corner_brace_repair_item(
        self,
        plan: CornerBraceRepairPlan,
    ) -> ReviewItem | None:
        if self.world_result is None:
            return None
        for item in self.review_items:
            if item.role != "corner_brace":
                continue
            if plan.target_kind == "recognized" and item.member_id != plan.target_member_id:
                continue
            if plan.target_kind == "unresolved" and item.status != "unresolved":
                continue
            try:
                current_key = repair_subject_key(
                    self.world_result,
                    item,
                    self.importer.tolerances,
                )
            except DXFImportError:
                continue
            if current_key == plan.subject_key:
                return item
        return None

    @staticmethod
    def _result_members_for_store(result: DXFImportResult) -> tuple[Any, ...]:
        return (
            *result.walers,
            *result.struts,
            *result.braces,
            *result.columns,
            *result.beams,
            *result.corner_braces,
        )

    def commit_corner_brace_repair(
        self,
        plan: CornerBraceRepairPlan,
        candidate_id: str,
        *,
        explicit_adoption: bool = True,
    ) -> ReviewMutation:
        """Atomically adopt one currently eligible CornerBrace repair."""

        self.require_no_pending_source_exclusions()
        if self.world_result is None or self.result is None:
            raise DXFImportError("請先完成 DXF 辨識，再修補角撐。")
        if plan.base_revision != self.revision:
            raise DXFImportError("DXF 檢視狀態已變更，請重新預覽角撐修補。")
        item = self._corner_brace_repair_item(plan)
        if item is None:
            raise DXFImportError("角撐修補目標已變更，請重新預覽。")
        if repair_subject_signature(
            self.world_result,
            item,
            self.importer.tolerances,
        ) != plan.subject_signature:
            raise DXFImportError("角撐修補證據已變更，請重新預覽。")

        # Re-plan from current truth so a saved candidate cannot bypass a
        # changed reference, connection, confirmation or unresolved-create gate.
        current_plan = build_corner_brace_repair_plan(
            self.world_result,
            item,
            base_revision=self.revision,
            review_items=self.review_items,
            confirmations=self.review_confirmations,
            confirmation_result=self.result,
            tolerances=self.importer.tolerances,
        )
        planned_candidate = next(
            (candidate for candidate in plan.candidates if candidate.id == candidate_id),
            None,
        )
        current_candidate = next(
            (
                candidate
                for candidate in current_plan.candidates
                if candidate.id == candidate_id
            ),
            None,
        )
        if planned_candidate is None or current_candidate != planned_candidate:
            raise DXFImportError(
                "角撐修補候選已過期或不再符合資格，請重新預覽。"
            )

        before_confirmed = self._confirmed_snapshot()
        staged_world, repaired_member_id = apply_corner_brace_repair(
            self.world_result,
            item,
            current_plan,
            candidate_id,
            explicit_adoption=explicit_adoption,
            tolerances=self.importer.tolerances,
        )
        staged_result = apply_coordinate_system(
            staged_world,
            self.result.coordinate_system,
        )
        staged_records = build_problem_records(staged_result)
        staged_items = build_review_items(staged_result, staged_records)
        staged_confirmations = valid_review_confirmations(
            staged_result,
            staged_items,
            self.review_confirmations,
        )
        staged_store = CandidatePointStore(self.candidate_point_store.tolerance)
        staged_store.rebuild(self._result_members_for_store(staged_result))

        # The live workflow is changed only after every projection succeeds.
        self.world_result = staged_world
        self.result = staged_result
        self.problem_records = staged_records
        self.review_items = staged_items
        self.review_confirmations = staged_confirmations
        self.candidate_point_store = staged_store
        self.revision += 1
        return self._mutation_result(before_confirmed)

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
        self.require_no_pending_source_exclusions()
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

    def _current_source_fingerprint(self) -> str:
        if self.world_result is not None:
            return str(self.world_result.source_fingerprint)
        return str(self.importer.source_fingerprint)

    def _refresh_pending_source_exclusion_state(self) -> None:
        draft = getattr(self, "_pending_source_exclusion_draft", None)
        if draft is None:
            world_result = getattr(self, "world_result", None)
            importer = getattr(self, "importer", None)
            fingerprint = str(
                getattr(world_result, "source_fingerprint", "")
                or getattr(importer, "source_fingerprint", "")
            )
            self._pending_source_exclusion_draft = PendingSourceExclusionDraft(
                base_revision=int(getattr(self, "revision", 0)),
                source_fingerprint=fingerprint,
                generation=0,
            )
            return
        if draft.is_empty or draft.state == "STALE":
            return
        if (
            draft.base_revision != self.revision
            or draft.source_fingerprint != self._current_source_fingerprint()
        ):
            self._pending_source_exclusion_draft = replace(draft, state="STALE")

    @property
    def pending_source_exclusion_draft(self) -> PendingSourceExclusionDraft:
        self._refresh_pending_source_exclusion_state()
        return self._pending_source_exclusion_draft

    def pending_source_exclusion_contains(self, item: ReviewItem | str) -> bool:
        identity = (
            item
            if isinstance(item, str)
            else canonical_source_identity(item.role, item.source_handles)
        )
        return identity in self.pending_source_exclusion_draft.identities

    def mark_source_exclusion(
        self,
        item: ReviewItem,
    ) -> PendingSourceExclusionDraft:
        draft = self.pending_source_exclusion_draft
        if draft.state == "STALE":
            raise DXFImportError("待排除來源已失效，請先捨棄後重新選取。")
        current = self.review_item_by_key(item.key)
        if current is None or self.review_item_identity(current) != self.review_item_identity(item):
            raise DXFImportError("選取的來源已變更，請重新選取。")
        if current.status == "excluded":
            raise DXFImportError("此來源已正式排除，不能加入待排除清單。")
        reason = self.source_exclusion_disabled_reason(current)
        if reason:
            raise DXFImportError(reason)
        if self.world_result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        source = excluded_source_from_review_item(current, self.world_result)
        sources = normalize_excluded_sources((*draft.sources, source))
        if sources == draft.sources:
            return draft
        base_revision = draft.base_revision if draft.sources else self.revision
        source_fingerprint = (
            draft.source_fingerprint
            if draft.sources
            else self._current_source_fingerprint()
        )
        self._pending_source_exclusion_draft = PendingSourceExclusionDraft(
            base_revision=base_revision,
            source_fingerprint=source_fingerprint,
            generation=draft.generation + 1,
            sources=sources,
            state="ACTIVE",
        )
        self._active_pending_source_exclusion_plan_token = None
        return self._pending_source_exclusion_draft

    def unmark_source_exclusion(
        self,
        item_or_identity: ReviewItem | str,
    ) -> PendingSourceExclusionDraft:
        draft = self.pending_source_exclusion_draft
        if draft.state == "STALE":
            raise DXFImportError("待排除來源已失效，只能捨棄後重新選取。")
        identity = (
            item_or_identity
            if isinstance(item_or_identity, str)
            else self.review_item_identity(item_or_identity)
        )
        sources = tuple(
            source for source in draft.sources if source.identity != identity
        )
        if sources == draft.sources:
            return draft
        self._pending_source_exclusion_draft = PendingSourceExclusionDraft(
            base_revision=(draft.base_revision if sources else self.revision),
            source_fingerprint=(
                draft.source_fingerprint
                if sources
                else self._current_source_fingerprint()
            ),
            generation=draft.generation + 1,
            sources=sources,
            state="ACTIVE" if sources else "EMPTY",
        )
        self._active_pending_source_exclusion_plan_token = None
        return self._pending_source_exclusion_draft

    def discard_pending_source_exclusions(self) -> PendingSourceExclusionDraft:
        draft = self.pending_source_exclusion_draft
        if draft.is_empty and draft.state == "EMPTY":
            return draft
        self._pending_source_exclusion_draft = PendingSourceExclusionDraft(
            base_revision=self.revision,
            source_fingerprint=self._current_source_fingerprint(),
            generation=draft.generation + 1,
        )
        self._active_pending_source_exclusion_plan_token = None
        return self._pending_source_exclusion_draft

    def pending_mutation_disabled_reason(self) -> str:
        if self.pending_source_exclusion_draft.sources:
            return "請先套用或捨棄待排除來源"
        return ""

    def require_no_pending_source_exclusions(self) -> None:
        reason = self.pending_mutation_disabled_reason()
        if reason:
            raise DXFImportError(reason)

    def source_exclusion_disabled_reason(self, item: ReviewItem | None) -> str:
        if item is None:
            return "請先選取 Formal、待修或已排除來源。"
        if not item.role or not normalize_source_handles(item.source_handles):
            return "此項目沒有可安全識別的 DXF 來源，無法使用來源排除。"
        draft = getattr(self, "_pending_source_exclusion_draft", None)
        if draft is None:
            draft = PendingSourceExclusionDraft(0, "", 0)
        else:
            draft = self.pending_source_exclusion_draft
        if draft.state == "STALE":
            return "待排除來源已失效，請先捨棄後重新選取。"
        if item.status == "excluded":
            if draft.sources:
                return "請先套用或捨棄待排除來源"
            return ""
        conflicts = shared_handle_conflicts(
            item,
            self.review_items,
            getattr(self, "world_result", None),
        )
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

    @staticmethod
    def _source_review_projection(
        items: Sequence[ReviewItem],
    ) -> Mapping[str, tuple[tuple[str, str, str], ...]]:
        """Return the UI-visible review state associated with each source handle."""

        projected: dict[str, list[tuple[str, str, str]]] = {}
        for item in items:
            value = (item.status, item.highest_severity, item.key)
            for handle in normalize_source_handles(item.source_handles):
                projected.setdefault(handle, []).append(value)
        return {
            handle: tuple(sorted(values))
            for handle, values in projected.items()
        }

    def _source_exclusion_effects(
        self,
        *,
        excluded_sources: Sequence[ExcludedSource],
        staged_result: DXFImportResult,
        staged_records: Sequence[ProblemRecord],
        staged_items: Sequence[ReviewItem],
    ) -> ReviewMutationEffects:
        assert self.result is not None
        before_sources = {source.identity: source for source in self.excluded_sources}
        after_sources = {source.identity: source for source in excluded_sources}
        changed_identities = set(before_sources) ^ set(after_sources)

        before_projection = self._source_review_projection(self.review_items)
        after_projection = self._source_review_projection(staged_items)
        before_identity_projection = {
            canonical_source_identity(item.role, item.source_handles): (
                item.status,
                item.highest_severity,
                item.key,
            )
            for item in self.review_items
            if normalize_source_handles(item.source_handles)
        }
        after_identity_projection = {
            canonical_source_identity(item.role, item.source_handles): (
                item.status,
                item.highest_severity,
                item.key,
            )
            for item in staged_items
            if normalize_source_handles(item.source_handles)
        }
        changed_identities.update(
            identity
            for identity in (
                set(before_identity_projection) | set(after_identity_projection)
            )
            if before_identity_projection.get(identity)
            != after_identity_projection.get(identity)
        )
        changed_handles = {
            handle
            for handle in set(before_projection) | set(after_projection)
            if before_projection.get(handle) != after_projection.get(handle)
        }
        for identity in changed_identities:
            source = before_sources.get(identity) or after_sources.get(identity)
            if source is not None:
                changed_handles.update(normalize_source_handles(source.source_handles))

        source_geometry_changed = (
            self._source_geometry_signature(self.result)
            != self._source_geometry_signature(staged_result)
        )
        members_changed = (
            self._result_members_for_store(self.result)
            != self._result_members_for_store(staged_result)
        )
        review_items_changed = self.review_items != tuple(staged_items)
        return ReviewMutationEffects(
            committed_revision=self.revision + 1,
            source_geometry_changed=source_geometry_changed,
            source_bounds_changed=source_geometry_changed,
            changed_source_identities=tuple(sorted(changed_identities)),
            changed_source_handles=tuple(sorted(changed_handles)),
            excluded_source_identities=tuple(sorted(after_sources)),
            engineering_members_changed=members_changed,
            problems_changed=self.problem_records != tuple(staged_records),
            review_items_changed=review_items_changed,
            candidate_points_changed=members_changed,
            selection_targets_invalidated=review_items_changed or members_changed,
            hit_index_invalidated=bool(changed_handles) or review_items_changed,
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
        confirmations = valid_review_confirmations(
            staged_result,
            review_items,
            self.review_confirmations,
        )
        candidate_store = CandidatePointStore(self.candidate_point_store.tolerance)
        candidate_store.rebuild(self._result_members_for_store(staged_result))
        effects = self._source_exclusion_effects(
            excluded_sources=normalized,
            staged_result=staged_result,
            staged_records=records,
            staged_items=review_items,
        )
        return SourceExclusionPlan(
            base_revision=self.revision,
            excluded_sources=normalized,
            world_result=staged_world,
            result=staged_result,
            problem_records=records,
            review_items=review_items,
            review_confirmations=MappingProxyType(dict(confirmations)),
            candidate_point_store=candidate_store,
            manual_replay=replay_report,
            effects=effects,
            source_fingerprint=self._current_source_fingerprint(),
        )

    def plan_pending_source_exclusions(self) -> SourceExclusionPlan:
        draft = self.pending_source_exclusion_draft
        if draft.state == "STALE":
            raise DXFImportError("待排除來源已失效，請先捨棄後重新選取。")
        if draft.is_empty:
            raise DXFImportError("目前沒有待排除來源。")
        candidate_exclusions = normalize_excluded_sources(
            (*self.excluded_sources, *draft.sources)
        )
        plan = self.plan_source_exclusion_change(candidate_exclusions)
        self._pending_source_exclusion_plan_sequence += 1
        token = self._pending_source_exclusion_plan_sequence
        self._active_pending_source_exclusion_plan_token = token
        return replace(
            plan,
            pending_generation=draft.generation,
            pending_source_identities=draft.identities,
            pending_plan_token=token,
        )

    def cancel_pending_source_exclusion_plan(
        self,
        plan: SourceExclusionPlan,
    ) -> None:
        if (
            plan.pending_plan_token is not None
            and plan.pending_plan_token
            == self._active_pending_source_exclusion_plan_token
        ):
            self._active_pending_source_exclusion_plan_token = None

    def plan_source_exclusion_for_item(
        self,
        item: ReviewItem,
    ) -> tuple[SourceExclusionPlan, bool, str]:
        identity = canonical_source_identity(item.role, item.source_handles)
        restoring = item.status == "excluded"
        if restoring:
            self.require_no_pending_source_exclusions()
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
        if plan.pending_generation is None:
            self.require_no_pending_source_exclusions()
        if plan.base_revision != self.revision:
            raise DXFImportError("DXF Review 已變更，請重新預覽來源排除影響。")
        if self.world_result is None or self.result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        if normalize_excluded_sources(plan.excluded_sources) != plan.excluded_sources:
            raise DXFImportError("來源排除計畫內容無效，請重新預覽。")
        if plan.source_fingerprint != self._current_source_fingerprint():
            raise DXFImportError("DXF 來源已變更，請重新預覽來源排除影響。")
        if plan.pending_generation is not None:
            draft = self.pending_source_exclusion_draft
            expected_exclusions = normalize_excluded_sources(
                (*self.excluded_sources, *draft.sources)
            )
            if (
                draft.state != "ACTIVE"
                or plan.pending_plan_token is None
                or plan.pending_plan_token
                != self._active_pending_source_exclusion_plan_token
                or draft.generation != plan.pending_generation
                or draft.identities != plan.pending_source_identities
                or expected_exclusions != plan.excluded_sources
            ):
                raise DXFImportError("待排除來源已變更，請重新預覽合併影響。")
        if (
            plan.world_result.source_fingerprint
            != self.world_result.source_fingerprint
            or plan.result.source_fingerprint != self.result.source_fingerprint
            or self._source_geometry_signature(plan.world_result)
            != self._source_geometry_signature(self.world_result)
            or plan.result.coordinate_system != self.result.coordinate_system
            or plan.effects.committed_revision != self.revision + 1
        ):
            raise DXFImportError("來源排除計畫已失效或內容不完整，請重新預覽。")
        before_confirmed = self._confirmed_snapshot()
        after_confirmed = self._confirmed_projection(
            plan.result,
            plan.review_items,
            plan.review_confirmations,
        )
        mutation = self._mutation_result(
            before_confirmed,
            initiating_member_ids=initiating_member_ids,
            manual_replay=plan.manual_replay,
            effects=plan.effects,
            after_confirmed=after_confirmed,
        )
        previous = (
            self.excluded_sources,
            self.world_result,
            self.result,
            self.problem_records,
            self.review_items,
            self.last_manual_replay_report,
            self.review_confirmations,
            self.candidate_point_store,
            self.revision,
            self._pending_source_exclusion_draft,
        )
        try:
            self._adopt_source_exclusion_plan(plan)
            if plan.pending_generation is not None:
                self._pending_source_exclusion_draft = PendingSourceExclusionDraft(
                    base_revision=self.revision,
                    source_fingerprint=self._current_source_fingerprint(),
                    generation=plan.pending_generation + 1,
                )
                self._active_pending_source_exclusion_plan_token = None
        except Exception:
            (
                self.excluded_sources,
                self.world_result,
                self.result,
                self.problem_records,
                self.review_items,
                self.last_manual_replay_report,
                self.review_confirmations,
                self.candidate_point_store,
                self.revision,
                self._pending_source_exclusion_draft,
            ) = previous
            raise
        return mutation

    def _adopt_source_exclusion_plan(self, plan: SourceExclusionPlan) -> None:
        """Adopt a fully built plan using assignment only.

        This small boundary also gives tests a deterministic failure-injection
        point for the rollback safety net around otherwise infallible swaps.
        """

        self.excluded_sources = plan.excluded_sources
        self.world_result = plan.world_result
        self.result = plan.result
        self.problem_records = plan.problem_records
        self.review_items = plan.review_items
        self.last_manual_replay_report = plan.manual_replay
        self.review_confirmations = dict(plan.review_confirmations)
        self.candidate_point_store = plan.candidate_point_store
        self.revision = plan.effects.committed_revision

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
                "column_association_decisions": [
                    asdict(decision)
                    for decision in self.column_association_decisions.values()
                ],
                "review_confirmations": serialize_review_confirmations(
                    self.review_confirmations
                ),
            }
        )
        return state
