"""Isolated candidate recognition for changed-content paused Review recovery."""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .review_recovery import (
    RecoveryCategory,
    RecoverySummary,
    RecoverySummaryEntry,
    ReviewRecoveryPlan,
    ReviewRecoveryResult,
    ReviewRecoveryStage,
    ReviewRecoveryStatus,
    critical_member_identity_map,
    match_critical_members,
    rebind_manual_overrides,
)
from .review_confirmation import review_confirmations_from_state
from .source_exclusion import (
    canonical_source_identity,
    manual_overrides_from_review_state,
    normalize_excluded_sources,
    normalize_source_handles,
)
from .support_pairing import (
    double_support_candidate_identity,
    double_support_decisions_from_review_state,
)


_SUPPORTED_LAYER_ROLES = {
    "waler",
    "strut",
    "brace",
    "column",
    "beam",
    "corner_brace",
    "continuous_wall",
    "auxiliary",
    "ignore",
}


class ReviewRecoveryPlanner:
    """Build a disposable candidate-based paused-Review recovery plan."""

    def __init__(
        self,
        *,
        geometry_tolerance_mm: float,
        ambiguity_tolerance_mm: float,
        importer_factory: Callable[[Path], Any] | None = None,
        workflow_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.geometry_tolerance_mm = float(geometry_tolerance_mm)
        self.ambiguity_tolerance_mm = float(ambiguity_tolerance_mm)
        self._importer_factory = importer_factory
        self._workflow_factory = workflow_factory

    @staticmethod
    def _saved_layer_roles(saved_state: Mapping[str, Any]) -> dict[str, str]:
        raw = saved_state.get("layer_classification", {})
        if isinstance(raw, Mapping):
            return {
                str(layer): str(role).strip().lower()
                for layer, role in raw.items()
                if str(layer)
            }
        assignments = saved_state.get("layer_assignments", ())
        if not isinstance(assignments, Sequence) or isinstance(
            assignments, (str, bytes)
        ):
            return {}
        return {
            str(item.get("layer_name")): str(item.get("layer_type")).strip().lower()
            for item in assignments
            if isinstance(item, Mapping) and str(item.get("layer_name", ""))
        }

    @staticmethod
    def _world_coordinate() -> dict[str, Any]:
        return {
            "mode": "world",
            "origin_x": 0.0,
            "origin_y": 0.0,
            "source": "world_origin",
        }

    @classmethod
    def _safe_coordinate_system(
        cls,
        saved_state: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        raw = saved_state.get("coordinate_system", {})
        if not isinstance(raw, Mapping):
            return cls._world_coordinate(), False
        mode = str(raw.get("mode", "world") or "world").strip().lower()
        if mode == "world":
            return cls._world_coordinate(), True
        if mode != "local":
            return cls._world_coordinate(), False
        try:
            origin_x = float(raw.get("origin_x", 0.0))
            origin_y = float(raw.get("origin_y", 0.0))
        except (TypeError, ValueError):
            return cls._world_coordinate(), False
        if not math.isfinite(origin_x) or not math.isfinite(origin_y):
            return cls._world_coordinate(), False
        return {
            "mode": "local",
            "origin_x": origin_x,
            "origin_y": origin_y,
            "source": str(
                raw.get("source", "selected_candidate_point")
                or "selected_candidate_point"
            ),
        }, True

    @staticmethod
    def _safe_import_mode(saved_state: Mapping[str, Any]) -> tuple[str, bool]:
        value = str(
            saved_state.get("import_mode", "replace") or "replace"
        ).strip().lower()
        return (value, True) if value in {"replace", "append"} else ("replace", False)

    def _new_importer(self, candidate_path: Path) -> Any:
        if self._importer_factory is not None:
            return self._importer_factory(candidate_path)
        from .importer import DXFImporter

        return DXFImporter(candidate_path)

    def _new_workflow(
        self,
        importer: Any,
        candidate_path: Path,
        *,
        initial_state: Mapping[str, Any],
        material_specs: Sequence[Mapping[str, Any]],
    ) -> Any:
        if self._workflow_factory is not None:
            return self._workflow_factory(
                importer,
                candidate_path,
                initial_state=initial_state,
                material_specs=material_specs,
            )
        from .review_workflow import DXFReviewWorkflow

        return DXFReviewWorkflow(
            importer,
            candidate_path,
            initial_state=initial_state,
            material_specs=material_specs,
        )

    @staticmethod
    def _manual_subject_kind(label: str) -> str:
        if label.endswith("材料規格"):
            return "material"
        if label.endswith("Waler 背填／寬度"):
            return "waler_contact"
        return "manual_endpoint"

    @classmethod
    def _manual_summary_entry(
        cls,
        label: str,
        category: RecoveryCategory,
    ) -> RecoverySummaryEntry:
        preserved = category == RecoveryCategory.PRESERVED
        return RecoverySummaryEntry(
            category,
            cls._manual_subject_kind(label),
            label,
            "MANUAL_INPUT_PRESERVED" if preserved else "MANUAL_INPUT_REVIEW_REQUIRED",
            (
                f"{label} 已安全套用到候選構件。"
                if preserved
                else f"{label} 無法安全沿用，請在 Review 中重新檢查。"
            ),
        )

    @staticmethod
    def _repair_recovery_entries(
        overrides: Sequence[Any],
        candidate_result: Any,
    ) -> tuple[RecoverySummaryEntry, ...]:
        """Changed-content recovery never geometry-rebinds repair decisions."""

        candidate_identities = {
            canonical_source_identity("corner_brace", member.source_handles)
            for member in getattr(candidate_result, "corner_braces", ())
            if normalize_source_handles(member.source_handles)
        }
        candidate_identities.update(
            canonical_source_identity(message.role, message.source_handles)
            for message in getattr(candidate_result, "messages", ())
            if message.role == "corner_brace"
            and normalize_source_handles(message.source_handles)
        )
        candidate_identities.update(
            canonical_source_identity(geometry.role, (geometry.source_handle,))
            for geometry in getattr(candidate_result, "source_geometry", ())
            if geometry.role == "corner_brace" and str(geometry.source_handle).strip()
        )
        entries = []
        for override in overrides:
            provenance = override.corner_brace_repair
            if provenance is None:
                continue
            label = f"{override.display_id or provenance.preferred_display_id or 'CornerBrace'} CornerBrace repair"
            identity = canonical_source_identity(
                provenance.subject_key.role,
                provenance.subject_key.source_handles,
            )
            if identity in candidate_identities:
                entries.append(
                    RecoverySummaryEntry(
                        RecoveryCategory.REQUIRES_REVIEW,
                        "corner_brace_repair",
                        label,
                        "CORNER_BRACE_REPAIR_REVIEW_REQUIRED",
                        "Exact CornerBrace source survives, but its repair decision must be reviewed again.",
                    )
                )
            else:
                entries.append(
                    RecoverySummaryEntry(
                        RecoveryCategory.DISABLED,
                        "corner_brace_repair",
                        label,
                        "CORNER_BRACE_REPAIR_SOURCE_MISSING",
                        "The exact CornerBrace source no longer survives; the repair decision is disabled.",
                    )
                )
        return tuple(entries)

    @staticmethod
    def _recover_exclusions(
        saved_state: Mapping[str, Any],
        candidate_result: Any,
    ) -> tuple[tuple[Any, ...], tuple[RecoverySummaryEntry, ...]]:
        available: dict[str, set[str]] = defaultdict(set)
        for geometry in getattr(candidate_result, "source_geometry", ()):
            role = str(getattr(geometry, "role", "") or "").strip().lower()
            handle = str(
                getattr(geometry, "source_handle", "") or ""
            ).strip().upper()
            if role and handle:
                available[role].add(handle)
        preserved = []
        entries = []
        for exclusion in normalize_excluded_sources(
            saved_state.get("excluded_sources", ())
        ):
            handles = set(normalize_source_handles(exclusion.source_handles))
            exact = bool(handles) and handles.issubset(available[exclusion.role])
            label = exclusion.display_id_when_excluded or exclusion.identity
            if exact:
                preserved.append(exclusion)
                entries.append(
                    RecoverySummaryEntry(
                        RecoveryCategory.PRESERVED,
                        "source_exclusion",
                        label,
                        "EXCLUSION_IDENTITY_PRESERVED",
                        f"排除來源 {label} 的相同 role／handle identity 仍存在。",
                    )
                )
            else:
                entries.append(
                    RecoverySummaryEntry(
                        RecoveryCategory.DISABLED,
                        "source_exclusion",
                        label,
                        "EXCLUSION_IDENTITY_MISSING",
                        f"排除來源 {label} 的 exact identity 已不存在，不套用舊排除決策。",
                    )
                )
        return tuple(preserved), tuple(entries)

    @staticmethod
    def _recover_double_support_decisions(
        saved_state: Mapping[str, Any],
        candidate_result: Any,
        matches: Sequence[Any],
    ) -> tuple[dict[Any, bool], tuple[RecoverySummaryEntry, ...]]:
        identity_map = critical_member_identity_map(matches)
        candidate_counts: dict[Any, int] = defaultdict(int)
        for candidate in getattr(candidate_result, "double_support_candidates", ()):
            if getattr(candidate, "qualification_status", "eligible") != "eligible":
                continue
            identity = double_support_candidate_identity(candidate_result, candidate)
            if identity is not None:
                candidate_counts[identity] += 1
        recovered: dict[Any, bool] = {}
        entries = []
        for old_identity, accepted in double_support_decisions_from_review_state(
            saved_state
        ).items():
            mapped = []
            for handles in old_identity:
                mapped_handles = identity_map.get(
                    canonical_source_identity("strut", handles)
                )
                if mapped_handles is None:
                    mapped = []
                    break
                mapped.append(mapped_handles)
            candidate_identity = tuple(sorted(mapped)) if len(mapped) == 2 else None
            label = " / ".join("|".join(handles) for handles in old_identity)
            if candidate_identity is not None and candidate_counts[candidate_identity] == 1:
                recovered[candidate_identity] = bool(accepted)
                entries.append(
                    RecoverySummaryEntry(
                        RecoveryCategory.PRESERVED,
                        "double_support",
                        label,
                        "DOUBLE_SUPPORT_DECISION_PRESERVED",
                        f"雙路支撐決策 {label} 已安全對應候選配對。",
                    )
                )
            else:
                entries.append(
                    RecoverySummaryEntry(
                        RecoveryCategory.REQUIRES_REVIEW,
                        "double_support",
                        label,
                        "DOUBLE_SUPPORT_DECISION_REVIEW_REQUIRED",
                        f"雙路支撐決策 {label} 無唯一候選配對，請重新檢查。",
                    )
                )
        return recovered, tuple(entries)

    @staticmethod
    def _candidate_member_identities(candidate_result: Any) -> set[str]:
        identities: set[str] = set()
        collections = (
            ("waler", "walers"),
            ("strut", "struts"),
            ("brace", "braces"),
            ("column", "columns"),
            ("beam", "beams"),
            ("corner_brace", "corner_braces"),
        )
        for role, collection in collections:
            for member in getattr(candidate_result, collection, ()):
                handles = normalize_source_handles(
                    getattr(member, "source_handles", ())
                    if not isinstance(member, Mapping)
                    else member.get("source_handles", ())
                )
                if handles:
                    identities.add(canonical_source_identity(role, handles))
        return identities

    @classmethod
    def _rebind_confirmations(
        cls,
        saved_state: Mapping[str, Any],
        candidate_result: Any,
        matches: Sequence[Any],
    ) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
        identity_map = critical_member_identity_map(matches)
        candidate_identities = cls._candidate_member_identities(candidate_result)
        rebound: dict[str, str] = {}
        provenance: dict[str, tuple[str, str]] = {}
        conflicts: set[str] = set()
        for old_identity, signature in review_confirmations_from_state(
            saved_state
        ).items():
            role = old_identity.partition(":")[0]
            handles = identity_map.get(old_identity)
            new_identity = (
                canonical_source_identity(role, handles)
                if handles is not None
                else (old_identity if old_identity in candidate_identities else "")
            )
            if not new_identity:
                provenance[old_identity] = ("", signature)
                continue
            if new_identity in rebound and rebound[new_identity] != signature:
                conflicts.add(new_identity)
            else:
                rebound[new_identity] = signature
                provenance[old_identity] = (new_identity, signature)
        for identity in conflicts:
            rebound.pop(identity, None)
        return rebound, provenance

    def plan(
        self,
        candidate_path: str | Path,
        candidate_fingerprint: str,
        saved_state: Mapping[str, Any],
        base_state_token: str,
        *,
        material_specs: Sequence[Mapping[str, Any]] = (),
    ) -> ReviewRecoveryResult:
        path = Path(candidate_path).resolve()
        expected_fingerprint = str(candidate_fingerprint or "").strip().upper()
        entries: list[RecoverySummaryEntry] = []

        try:
            importer = self._new_importer(path).read()
            actual_fingerprint = str(importer.source_fingerprint).strip().upper()
            if not actual_fingerprint or actual_fingerprint != expected_fingerprint:
                return ReviewRecoveryResult(
                    ReviewRecoveryStatus.VALIDATION_FAILED,
                    None,
                    RecoverySummary(),
                    ("候選 DXF 在規劃期間已變更，請重新選擇檔案。",),
                )

            candidate_layers = tuple(str(layer) for layer in importer.layer_names)
            candidate_layer_set = set(candidate_layers)
            saved_roles = self._saved_layer_roles(saved_state)
            safe_roles: dict[str, str] = {}
            for layer in candidate_layers:
                saved_role = saved_roles.get(layer)
                if saved_role in _SUPPORTED_LAYER_ROLES:
                    safe_roles[layer] = saved_role
                    entries.append(
                        RecoverySummaryEntry(
                            RecoveryCategory.PRESERVED,
                            "layer",
                            layer,
                            "LAYER_ROLE_PRESERVED",
                            f"圖層「{layer}」沿用原用途設定。",
                        )
                    )
                else:
                    safe_roles[layer] = "ignore"
                    entries.append(
                        RecoverySummaryEntry(
                            RecoveryCategory.REQUIRES_REVIEW,
                            "layer",
                            layer,
                            (
                                "LAYER_ROLE_INVALID"
                                if saved_role is not None
                                else "CANDIDATE_LAYER_UNSEEN"
                            ),
                            f"圖層「{layer}」暫設為忽略，請重新檢查用途。",
                        )
                    )
            for layer in sorted(set(saved_roles).difference(candidate_layer_set)):
                entries.append(
                    RecoverySummaryEntry(
                        RecoveryCategory.REQUIRES_REVIEW,
                        "layer",
                        layer,
                        "SAVED_LAYER_MISSING",
                        f"原 Review 圖層「{layer}」不存在於候選 DXF。",
                    )
                )

            coordinate_system, coordinate_preserved = self._safe_coordinate_system(
                saved_state
            )
            entries.append(
                RecoverySummaryEntry(
                    (
                        RecoveryCategory.PRESERVED
                        if coordinate_preserved
                        else RecoveryCategory.REQUIRES_REVIEW
                    ),
                    "setting",
                    "座標模式",
                    (
                        "COORDINATE_SYSTEM_PRESERVED"
                        if coordinate_preserved
                        else "COORDINATE_SYSTEM_FALLBACK"
                    ),
                    (
                        "座標模式與原點已保留。"
                        if coordinate_preserved
                        else "原座標設定無效，已安全降級為 World Coordinates。"
                    ),
                )
            )
            import_mode, import_mode_preserved = self._safe_import_mode(saved_state)
            entries.append(
                RecoverySummaryEntry(
                    (
                        RecoveryCategory.PRESERVED
                        if import_mode_preserved
                        else RecoveryCategory.REQUIRES_REVIEW
                    ),
                    "setting",
                    "匯入模式",
                    (
                        "IMPORT_MODE_PRESERVED"
                        if import_mode_preserved
                        else "IMPORT_MODE_FALLBACK"
                    ),
                    (
                        f"匯入模式保留為 {import_mode}。"
                        if import_mode_preserved
                        else "原匯入模式無效，已安全降級為 replace。"
                    ),
                )
            )

            candidate_initial_state = {
                "review_state_version": 2,
                "source_path": str(path),
                "source_fingerprint": actual_fingerprint,
                "layer_names": list(candidate_layers),
                "layer_classification": dict(safe_roles),
                "coordinate_system": coordinate_system,
                "import_mode": import_mode,
            }
            workflow = self._new_workflow(
                importer,
                path,
                initial_state=candidate_initial_state,
                material_specs=material_specs,
            )
            workflow.recognize(safe_roles)
            candidate_result = workflow.world_result
            if candidate_result is None:
                raise ValueError("候選 DXF 未產生辨識結果。")

            matching = match_critical_members(
                saved_state,
                candidate_result,
                geometry_tolerance_mm=self.geometry_tolerance_mm,
                ambiguity_tolerance_mm=self.ambiguity_tolerance_mm,
            )
            if not matching.compatible:
                entries.extend(self._matching_summary(matching))
                summary = RecoverySummary(tuple(entries))
                return ReviewRecoveryResult(
                    ReviewRecoveryStatus.INCOMPATIBLE_SOURCE,
                    None,
                    summary,
                    tuple(
                        entry.description
                        for entry in summary.entries_for(RecoveryCategory.DISABLED)
                    ),
                )

            exclusions, exclusion_entries = self._recover_exclusions(
                saved_state,
                candidate_result,
            )
            saved_overrides = manual_overrides_from_review_state(saved_state)
            repair_overrides = tuple(
                override
                for override in saved_overrides
                if override.corner_brace_repair is not None
            )
            manual_rebind = rebind_manual_overrides(
                tuple(
                    override
                    for override in saved_overrides
                    if override.corner_brace_repair is None
                ),
                matching.matches,
            )
            staged_result, manual_report = workflow.recognize_staged(
                exclusions,
                manual_rebind.rebound,
                layer_roles=safe_roles,
            )
            final_matching = match_critical_members(
                saved_state,
                staged_result,
                geometry_tolerance_mm=self.geometry_tolerance_mm,
                ambiguity_tolerance_mm=self.ambiguity_tolerance_mm,
            )
            entries.extend(self._matching_summary(final_matching))
            if not final_matching.compatible:
                summary = RecoverySummary(tuple(entries))
                return ReviewRecoveryResult(
                    ReviewRecoveryStatus.INCOMPATIBLE_SOURCE,
                    None,
                    summary,
                    tuple(
                        entry.description
                        for entry in summary.entries_for(RecoveryCategory.DISABLED)
                    ),
                )

            entries.extend(exclusion_entries)
            raw_column_decisions = saved_state.get("column_association_decisions", ())
            if isinstance(raw_column_decisions, (list, tuple)):
                def member_sources(members: Sequence[Any]) -> dict[tuple[str, ...], int]:
                    counts: dict[tuple[str, ...], int] = defaultdict(int)
                    for member in members:
                        handles = (
                            member.get("source_handles", ())
                            if isinstance(member, Mapping)
                            else getattr(member, "source_handles", ())
                        )
                        source = normalize_source_handles(handles)
                        if source:
                            counts[source] += 1
                    return counts

                column_sources = member_sources(getattr(staged_result, "columns", ()))
                strut_sources = member_sources(getattr(staged_result, "struts", ()))
                for decision in raw_column_decisions:
                    if not isinstance(decision, Mapping):
                        continue
                    label = str(decision.get("column_display_id", "") or "中間柱")
                    column_source = normalize_source_handles(decision.get("column_source_handles", ()))
                    raw_candidates = decision.get("candidate_strut_sources", ())
                    if not isinstance(raw_candidates, (list, tuple)):
                        raw_candidates = ()
                    candidate_sources = tuple(
                        normalize_source_handles(handles)
                        for handles in raw_candidates
                    )
                    identifiable = (
                        column_sources.get(column_source) == 1
                        and len(candidate_sources) == 2
                        and all(strut_sources.get(source) == 1 for source in candidate_sources)
                    )
                    entries.append(
                        RecoverySummaryEntry(
                            RecoveryCategory.REQUIRES_REVIEW if identifiable else RecoveryCategory.DISABLED,
                            "column_association",
                            label,
                            "COLUMN_ASSOCIATION_REVIEW_REQUIRED" if identifiable else "COLUMN_ASSOCIATION_DISABLED",
                            (
                                f"{label} 的人工支撐關聯未轉移；請在新 DXF Review 重新判定。"
                                if identifiable else
                                f"{label} 的柱或候選支撐來源無法唯一識別；原人工關聯已停用。"
                            ),
                        )
                    )
            entries.extend(
                self._repair_recovery_entries(
                    repair_overrides,
                    staged_result,
                )
            )
            requires_review_labels = tuple(dict.fromkeys((
                *manual_rebind.requires_review_labels,
                *manual_report.needs_review,
                *manual_report.disabled,
            )))
            disabled_labels = tuple(dict.fromkeys(
                manual_rebind.disabled_labels
            ))
            requires_review_set = set(requires_review_labels)
            disabled_set = set(disabled_labels)
            for label in manual_report.preserved:
                if label in requires_review_set or label in disabled_set:
                    continue
                entries.append(
                    self._manual_summary_entry(
                        label,
                        RecoveryCategory.PRESERVED,
                    )
                )
            for label in requires_review_labels:
                entries.append(
                    self._manual_summary_entry(
                        label,
                        RecoveryCategory.REQUIRES_REVIEW,
                    )
                )
            for label in disabled_labels:
                entries.append(
                    self._manual_summary_entry(
                        label,
                        RecoveryCategory.DISABLED,
                    )
                )

            double_decisions, double_entries = (
                self._recover_double_support_decisions(
                    saved_state,
                    staged_result,
                    final_matching.matches,
                )
            )
            entries.extend(double_entries)
            rebound_confirmations, confirmation_provenance = (
                self._rebind_confirmations(
                    saved_state,
                    staged_result,
                    final_matching.matches,
                )
            )
            workflow.install_staged_recovery(
                staged_result,
                layer_roles=safe_roles,
                excluded_sources=exclusions,
                double_support_decisions=double_decisions,
                review_confirmations=rebound_confirmations,
                manual_replay_report=manual_report,
            )
            for old_identity, (new_identity, signature) in (
                confirmation_provenance.items()
            ):
                preserved = bool(
                    new_identity
                    and workflow.review_confirmations.get(new_identity) == signature
                )
                entries.append(
                    RecoverySummaryEntry(
                        (
                            RecoveryCategory.PRESERVED
                            if preserved
                            else RecoveryCategory.REQUIRES_REVIEW
                        ),
                        "confirmation",
                        old_identity,
                        (
                            "CONFIRMATION_PRESERVED"
                            if preserved
                            else "CONFIRMATION_REVIEW_REQUIRED"
                        ),
                        (
                            f"確認 {old_identity} 的 current-state signature 仍有效。"
                            if preserved
                            else f"確認 {old_identity} 已失效，請重新檢查。"
                        ),
                    )
                )

            summary = RecoverySummary(tuple(entries))
            recovered_state = workflow.serialize_review_state(
                layer_roles=safe_roles,
                import_mode=import_mode,
            )
            stage = ReviewRecoveryStage(
                path,
                actual_fingerprint,
                base_state_token,
                recovered_state,
                workflow.world_result,
                summary,
            )
            return ReviewRecoveryResult(
                ReviewRecoveryStatus.COMPATIBLE_RECOVERY_AVAILABLE,
                ReviewRecoveryPlan(stage, final_matching.matches),
                summary,
            )
        except Exception as exc:
            return ReviewRecoveryResult(
                ReviewRecoveryStatus.VALIDATION_FAILED,
                None,
                RecoverySummary(tuple(entries)),
                (str(exc) or exc.__class__.__name__,),
            )

    @staticmethod
    def _matching_summary(matching: Any) -> tuple[RecoverySummaryEntry, ...]:
        entries: list[RecoverySummaryEntry] = []
        for match in matching.matches:
            entries.append(
                RecoverySummaryEntry(
                    RecoveryCategory.PRESERVED,
                    match.role,
                    match.saved_id,
                    "CRITICAL_MEMBER_MATCHED",
                    f"{match.saved_id} 已唯一對應候選構件 {match.candidate_id}。",
                )
            )
        for addition in matching.additions:
            entries.append(
                RecoverySummaryEntry(
                    RecoveryCategory.REQUIRES_REVIEW,
                    addition.role,
                    addition.candidate_id,
                    "CANDIDATE_MEMBER_ADDED",
                    f"候選 DXF 新增構件 {addition.candidate_id}，需重新檢查。",
                )
            )
        for member_id in matching.missing_saved_ids:
            entries.append(
                RecoverySummaryEntry(
                    RecoveryCategory.DISABLED,
                    "critical_member",
                    member_id,
                    "SAVED_MEMBER_MISSING",
                    f"找不到原構件 {member_id} 的唯一候選對應。",
                )
            )
        for member_id in matching.ambiguous_saved_ids:
            entries.append(
                RecoverySummaryEntry(
                    RecoveryCategory.DISABLED,
                    "critical_member",
                    member_id,
                    "SAVED_MEMBER_AMBIGUOUS",
                    f"原構件 {member_id} 有多個同等候選，無法安全恢復。",
                )
            )
        return tuple(entries)


__all__ = ["ReviewRecoveryPlanner"]
