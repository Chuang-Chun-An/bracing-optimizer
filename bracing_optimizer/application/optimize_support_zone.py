"""Application use case for optimizing all supports in one zoning.

The use case owns the support Solver workflow, candidate-cache policy, staged
global search, and diagnostics.  It deliberately has no GUI or threading
dependency; callers decide where it runs and how progress is presented.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable, MutableMapping

from bracing_optimizer.algorithms import solver_search, support
from bracing_optimizer.application.solver_input_builder import SupportZoneInput
from bracing_optimizer.domain.material_rules import MaterialRatioTargets


@dataclass(frozen=True)
class OptimizeSupportZoneRequest:
    input: SupportZoneInput
    material_ratio_targets: MaterialRatioTargets
    material_ratio_weight: float


@dataclass(frozen=True)
class OptimizationProgress:
    stage: str
    message: str
    support_id: str | None = None


@dataclass(frozen=True)
class OptimizeSupportZoneResult:
    solution: support.GlobalSolution | None
    diagnostics: solver_search.SolverDiagnostics


ProgressCallback = Callable[[OptimizationProgress], None]
LogCallback = Callable[..., None]


class OptimizeSupportZone:
    """Run the complete, GUI-independent support-zone optimization workflow."""

    def __init__(
        self,
        candidate_cache: MutableMapping[object, object],
        *,
        search_policy: solver_search.SolverSearchPolicy = (
            solver_search.DEFAULT_SEARCH_POLICY
        ),
    ) -> None:
        self.candidate_cache = candidate_cache
        self.search_policy = search_policy

    def execute(
        self,
        request: OptimizeSupportZoneRequest,
        *,
        on_progress: ProgressCallback | None = None,
        logger: LogCallback | None = None,
    ) -> OptimizeSupportZoneResult:
        """Execute synchronously and return both the solution and diagnostics."""

        policy = self.search_policy
        support.set_logger(logger)
        support.random.seed(policy.support_phase1_random_seed)
        try:
            support.log(f"=== 分區 {request.input.zoning} 支撐配置開始 ===")
            support.log(f"搜尋政策：{policy.policy_id} v{policy.policy_version}")
            support.log(
                "Phase 1：每支支撐完整處理 "
                f"{policy.support_phase1_length_combination_count} 組材料組合；"
                f"最多保留 {policy.support_phase1_retained_candidate_count} 個候選送入全域配置。"
            )
            support.log(
                f"候選保留順序：每 {policy.support_phase1_jack_bucket_size} mm "
                f"Jack區間保留 {policy.support_phase1_candidates_per_jack_bucket} 個代表方案，"
                "再保留材料型態，剩餘名額依單體分數補入。"
            )
            self._emit_progress(
                on_progress,
                "candidate_generation",
                "正在建立材料組合與配置候選……",
            )
            solution, diagnostics = self._solve(request, on_progress)
            return OptimizeSupportZoneResult(
                solution=solution,
                diagnostics=diagnostics,
            )
        finally:
            support.set_logger(None)

    @staticmethod
    def _emit_progress(
        callback: ProgressCallback | None,
        stage: str,
        message: str,
        support_id: str | None = None,
    ) -> None:
        if callback is not None:
            callback(OptimizationProgress(stage, message, support_id))

    @staticmethod
    def _log_candidate_shortage(
        zoning,
        config,
        actual_valid_count,
        diagnostic_record,
    ) -> None:
        diagnostic_record = diagnostic_record or {}
        benchmark = dict(
            (diagnostic_record.get("diagnostics", {}) or {}).get(
                "candidate_benchmark", {}
            )
            or {}
        )
        invalid_reasons = Counter(
            (diagnostic_record.get("diagnostics", {}) or {}).get(
                "invalid_reason_counts", {}
            )
            or {}
        )
        region_mismatch_count = int(
            (diagnostic_record.get("diagnostics", {}) or {}).get(
                "target_region_mismatch_count", 0
            )
            or 0
        )
        support.log("支撐候選方案不足。")
        support.log(f"分區：{zoning}")
        support.log(f"支撐：{config.support_id}")
        support.log(f"實際合法候選數：{actual_valid_count}")
        support.log(
            "配置流程："
            f"原始 {int(benchmark.get('raw_layout_count', 0) or 0)}、"
            f"完整合法 {int(benchmark.get('valid_layout_count', 0) or 0)}、"
            f"目標 Jack 區域後 "
            f"{int(benchmark.get('candidate_count_before_topn', 0) or 0)}"
        )
        if invalid_reasons:
            support.log("主要不合法原因：")
            for reason, count in invalid_reasons.most_common(3):
                support.log(f"  - {reason}：{count}")
        if region_mismatch_count:
            support.log(f"  - Jack Region 不符：{region_mismatch_count}")
        support.log("請檢查該支撐的幾何、禁止區、Jack Region 與可用材料條件。")

    def _solve(
        self,
        request: OptimizeSupportZoneRequest,
        on_progress: ProgressCallback | None,
    ) -> tuple[support.GlobalSolution | None, solver_search.SolverDiagnostics]:
        policy = self.search_policy
        max_steel_combination_count = policy.support_phase1_length_combination_count
        target_valid_candidate_count = policy.support_phase1_retained_candidate_count
        candidates_by_support = []
        candidate_statuses = []
        ordered_configs = tuple(
            config
            for unit in request.input.units
            for config in unit.configs
        )

        for config in ordered_configs:
            self._emit_progress(
                on_progress,
                "candidate_generation",
                f"正在產生支撐 {config.support_id} 的候選方案……",
                config.support_id,
            )
            diagnostic_record = {}
            phase1_beam_width = support.SUPPORT_PHASE1_LAYOUT_BEAM_WIDTH
            max_layouts_per_combo = support.SUPPORT_PHASE1_MAX_LAYOUTS_PER_COMBO
            min_processed_steel_combinations = (
                support.SUPPORT_DEFAULT_MIN_PROCESSED_STEEL_COMBINATIONS
            )
            min_candidate_pool_size = support.SUPPORT_DEFAULT_MIN_CANDIDATE_POOL_SIZE
            min_unique_jack_centers = support.SUPPORT_DEFAULT_MIN_UNIQUE_JACK_CENTERS
            min_no_under_4000_candidates = (
                support.SUPPORT_DEFAULT_MIN_NO_UNDER_4000_CANDIDATES
            )
            min_unique_material_styles = (
                support.SUPPORT_DEFAULT_MIN_UNIQUE_MATERIAL_STYLES
            )
            jack_center_bucket_size = policy.support_phase1_jack_bucket_size
            min_candidates_per_jack_bucket = (
                policy.support_phase1_candidates_per_jack_bucket
            )
            min_candidates_per_material_style = (
                support.SUPPORT_DEFAULT_MIN_CANDIDATES_PER_MATERIAL_STYLE
            )
            min_retained_no_under_4000_candidates = (
                support.SUPPORT_DEFAULT_MIN_RETAINED_NO_UNDER_4000_CANDIDATES
            )
            final_candidate_count = target_valid_candidate_count
            cache_key = support.build_support_candidate_cache_key(
                config,
                max_length_combinations=max_steel_combination_count,
                final_candidate_count=final_candidate_count,
                beam_width=phase1_beam_width,
                max_layouts_per_combo=max_layouts_per_combo,
                min_processed_steel_combinations=min_processed_steel_combinations,
                min_candidate_pool_size=min_candidate_pool_size,
                min_unique_jack_centers=min_unique_jack_centers,
                min_no_under_4000_candidates=min_no_under_4000_candidates,
                min_unique_material_styles=min_unique_material_styles,
                jack_center_bucket_size=jack_center_bucket_size,
                min_candidates_per_jack_bucket=min_candidates_per_jack_bucket,
                min_candidates_per_material_style=min_candidates_per_material_style,
                min_retained_no_under_4000_candidates=(
                    min_retained_no_under_4000_candidates
                ),
                solver_search_policy_id=policy.policy_id,
                solver_search_policy_version=policy.policy_version,
            )
            if cache_key not in self.candidate_cache:
                support.log(f"產生支撐 {config.support_id} 候選解...")
                generated_candidates = support.generate_single_support_candidates(
                    config=config,
                    min_candidates=final_candidate_count,
                    final_candidate_count=final_candidate_count,
                    max_length_combinations=max_steel_combination_count,
                    beam_width=phase1_beam_width,
                    max_layouts_per_combo=max_layouts_per_combo,
                    min_processed_steel_combinations=min_processed_steel_combinations,
                    min_candidate_pool_size=min_candidate_pool_size,
                    min_unique_jack_centers=min_unique_jack_centers,
                    min_no_under_4000_candidates=min_no_under_4000_candidates,
                    min_unique_material_styles=min_unique_material_styles,
                    jack_center_bucket_size=jack_center_bucket_size,
                    min_candidates_per_jack_bucket=min_candidates_per_jack_bucket,
                    min_candidates_per_material_style=(
                        min_candidates_per_material_style
                    ),
                    min_retained_no_under_4000_candidates=(
                        min_retained_no_under_4000_candidates
                    ),
                    diagnostics_out=diagnostic_record,
                )
                self.candidate_cache[cache_key] = {
                    "candidates": generated_candidates,
                    "diagnostics": diagnostic_record,
                }
                candidates = generated_candidates
            else:
                support.log(f"支撐 {config.support_id} 使用本次候選快取。")
                cache_entry = self.candidate_cache[cache_key]
                if isinstance(cache_entry, dict):
                    candidates = cache_entry.get("candidates", [])
                    diagnostic_record = cache_entry.get("diagnostics") or {}
                    if diagnostic_record:
                        diagnostic_record.setdefault(
                            "max_steel_combination_count",
                            max_steel_combination_count,
                        )
                        diagnostic_record.setdefault(
                            "target_valid_candidate_count",
                            target_valid_candidate_count,
                        )
                        diagnostic_record.setdefault(
                            "final_candidate_count",
                            final_candidate_count,
                        )
                        diagnostic_record.setdefault(
                            "min_candidate_pool_size",
                            min_candidate_pool_size,
                        )
                        support.log_support_candidate_diagnostics(
                            config,
                            diagnostic_record,
                        )
                else:
                    candidates = cache_entry
                    diagnostic_record = {}

            valid_candidates = [
                plan
                for plan in candidates
                if plan.valid and not plan.reason
            ]
            actual_valid_count = len(valid_candidates)
            candidate_statuses.append({
                "config": config,
                "actual_valid_count": actual_valid_count,
                "diagnostics": diagnostic_record,
                "sufficient": actual_valid_count >= target_valid_candidate_count,
            })
            candidates_by_support.append([
                support.clone_plan_with_support_id(
                    plan,
                    config.support_id,
                    material_spec=config.material_spec,
                    shared_layout_group=config.shared_layout_group,
                )
                for plan in valid_candidates
            ])

        shared_group_indexes: dict[str, list[int]] = {}
        for index, config in enumerate(ordered_configs):
            group_id = str(config.shared_layout_group or "").strip()
            if group_id:
                shared_group_indexes.setdefault(group_id, []).append(index)
        for group_id, indexes in shared_group_indexes.items():
            common_signatures = None
            for index in indexes:
                signatures = {
                    support.shared_layout_signature(plan)
                    for plan in candidates_by_support[index]
                }
                common_signatures = (
                    signatures
                    if common_signatures is None
                    else common_signatures.intersection(signatures)
                )
            common_signatures = common_signatures or set()
            for index in indexes:
                candidates_by_support[index] = [
                    plan
                    for plan in candidates_by_support[index]
                    if support.shared_layout_signature(plan) in common_signatures
                ]
                status = candidate_statuses[index]
                status["shared_layout_group"] = group_id
                status["shared_candidate_count"] = len(
                    candidates_by_support[index]
                )
                status["actual_valid_count"] = len(candidates_by_support[index])
                status["sufficient"] = (
                    len(candidates_by_support[index])
                    >= target_valid_candidate_count
                )

        shortages = [
            status
            for status in candidate_statuses
            if not status["sufficient"]
        ]
        if shortages:
            support.log("")
            for status in shortages:
                self._log_candidate_shortage(
                    zoning=request.input.zoning,
                    config=status["config"],
                    actual_valid_count=status["actual_valid_count"],
                    diagnostic_record=status["diagnostics"],
                )
                support.log("")

        missing_candidates = [
            status
            for status in candidate_statuses
            if status["actual_valid_count"] == 0
        ]
        if missing_candidates:
            diagnostics = self._build_support_diagnostics(
                candidate_statuses=candidate_statuses,
                solution=None,
                stage_records=[],
                stage_scores=[],
                final_assessment=None,
            )
            support.log(
                f"分區 {request.input.zoning} 未進入全域配置："
                "至少一支支撐沒有合法單體候選。"
            )
            support.log("=" * 72)
            self._emit_progress(
                on_progress,
                "completed",
                "候選不足，正在整理診斷……",
            )
            return None, diagnostics

        support.log("候選合法性檢查完成，正在進行全域配置。")
        self._emit_progress(
            on_progress,
            "global_optimization",
            "正在進行全域配置並確認搜尋穩定度……",
        )

        solutions = []
        stage_records = []
        stage_scores = []
        final_assessment = None
        for stage_index, stage in enumerate(policy.support_global_search_stages):
            support.log("")
            support.log(
                f"[搜尋階段 {stage.name}／"
                f"{policy.support_global_search_stages[-1].name}]"
            )
            support.log(f"Beam Width：{stage.beam_width}")
            phase2_diagnostics = {}
            stage_solution = support.build_global_solution(
                candidates_by_support=candidates_by_support,
                beam_width=stage.beam_width,
                material_ratio_targets=request.material_ratio_targets.as_dict(),
                material_ratio_weight=request.material_ratio_weight,
                diagnostics_out=phase2_diagnostics,
            )
            solutions.append(stage_solution)
            if stage_solution.valid:
                stage_scores.append(float(stage_solution.total_score))
            unique_solution_count = int(
                phase2_diagnostics.get("final_unique_solution_count", 0) or 0
            )
            pruning_was_active = bool(
                phase2_diagnostics.get("pruning_was_active", False)
            )
            final_assessment = solver_search.assess_support_stage(
                legal_solution_found=bool(stage_solution.valid),
                unique_solution_count=unique_solution_count,
                stage_best_scores=stage_scores,
                pruning_was_active=pruning_was_active,
                is_last_stage=(
                    stage_index == len(policy.support_global_search_stages) - 1
                ),
                policy=policy,
            )
            stage_record = {
                "stage": stage.name,
                "beam_width": stage.beam_width,
                "legal_solution_found": bool(stage_solution.valid),
                "best_score": float(stage_solution.total_score),
                "unique_solution_count": unique_solution_count,
                "pruning_was_active": pruning_was_active,
                "result_is_stable": final_assessment.result_is_stable,
                "decision": (
                    "進入下一搜尋階段"
                    if final_assessment.should_escalate
                    else "停止搜尋"
                ),
                "reasons": list(final_assessment.reasons),
            }
            stage_records.append(stage_record)
            support.log(f"合法方案：{'是' if stage_solution.valid else '否'}")
            support.log(f"最佳分數：{stage_solution.total_score:.2f}")
            support.log(f"合法且唯一方案：{unique_solution_count}")
            support.log(f"決策：{stage_record['decision']}")
            support.log(
                "原因："
                + (
                    "、".join(final_assessment.reasons)
                    if final_assessment.reasons
                    else final_assessment.stopping_reason
                )
            )
            if not final_assessment.should_escalate:
                break
            self._emit_progress(
                on_progress,
                "search_escalated",
                "初始結果仍可能改善，系統正在進一步搜尋……",
            )

        solution = solver_search.select_best_support_solution(
            solutions,
            precision=policy.score_comparison_precision,
        )
        diagnostics = self._build_support_diagnostics(
            candidate_statuses=candidate_statuses,
            solution=solution,
            stage_records=stage_records,
            stage_scores=stage_scores,
            final_assessment=final_assessment,
        )
        solution.candidate_diagnostics = candidate_statuses
        solution.search_diagnostics = diagnostics.to_dict()
        self._emit_progress(
            on_progress,
            "finalizing",
            "正在整理結果與診斷……",
        )
        return solution, diagnostics

    def _support_phase1_issue_details(self, candidate_statuses):
        issue_counts = Counter()
        insufficient_ids = []
        missing_ids = []
        concentrated_ids = []
        retained_target = self.search_policy.support_phase1_retained_candidate_count
        for status in candidate_statuses:
            component_id = status["config"].support_id
            actual_count = int(status.get("actual_valid_count", 0) or 0)
            record = dict(status.get("diagnostics", {}) or {})
            phase1 = dict(record.get("diagnostics", {}) or {})
            benchmark = dict(phase1.get("candidate_benchmark", {}) or {})
            after_stats = dict(benchmark.get("after_topn", {}) or {})
            issue_counts.update(dict(phase1.get("invalid_reason_counts", {}) or {}))
            region_mismatch = int(
                phase1.get("target_region_mismatch_count", 0) or 0
            )
            if region_mismatch:
                issue_counts["Jack Region 不符"] += region_mismatch
            if actual_count < retained_target:
                insufficient_ids.append(component_id)
            if actual_count == 0:
                missing_ids.append(component_id)
            if actual_count and (
                int(after_stats.get("jack_bucket_count", 0) or 0) <= 1
                or int(after_stats.get("unique_steel_pattern_count", 0) or 0) <= 1
                or int(after_stats.get("material_style_count", 0) or 0) <= 1
            ):
                concentrated_ids.append(component_id)
        return issue_counts, insufficient_ids, missing_ids, concentrated_ids

    def _build_support_diagnostics(
        self,
        *,
        candidate_statuses,
        solution,
        stage_records,
        stage_scores,
        final_assessment,
    ) -> solver_search.SolverDiagnostics:
        policy = self.search_policy
        issue_counts, insufficient_ids, missing_ids, concentrated_ids = (
            self._support_phase1_issue_details(candidate_statuses)
        )
        legal_found = bool(solution is not None and solution.valid)
        scoring_preference_ids = []
        if legal_found:
            solution_plans = list(getattr(solution, "plans", []) or [])
            pattern_counts = Counter(
                support.steel_pattern_from_plan(plan)
                for plan in solution_plans
            )
            if len(solution_plans) >= 3 and pattern_counts:
                dominant_pattern, dominant_count = pattern_counts.most_common(1)[0]
                if (
                    dominant_count / len(solution_plans)
                    > policy.scoring_pattern_dominance_threshold
                ):
                    scoring_preference_ids = [
                        plan.support_id
                        for plan in solution_plans
                        if support.steel_pattern_from_plan(plan) == dominant_pattern
                    ]
        reached_last_stage = bool(
            stage_records
            and stage_records[-1]["stage"]
            == policy.support_global_search_stages[-1].name
        )
        limit_reached = bool(
            reached_last_stage
            and final_assessment is not None
            and final_assessment.reasons
        )
        main_issue = solver_search.NO_ISSUE
        issue_message = ""
        secondary = []
        if missing_ids:
            main_issue = solver_search.ENGINEERING_CONSTRAINT_LIMITED
            issue_message = "部分支撐在目前工程條件下沒有合法單體候選。"
            secondary.append(solver_search.CANDIDATE_INSUFFICIENT)
        elif insufficient_ids:
            main_issue = solver_search.CANDIDATE_INSUFFICIENT
            issue_message = "部分支撐的合法候選未填滿正式保留數。"
            if issue_counts:
                secondary.append(solver_search.ENGINEERING_CONSTRAINT_LIMITED)
        elif concentrated_ids:
            main_issue = solver_search.CANDIDATE_INSUFFICIENT
            issue_message = "候選數量雖足，但部分支撐的 Jack 位置或材料型態選項集中。"
        elif not legal_found:
            main_issue = solver_search.SEARCH_INSUFFICIENT
            issue_message = "啟發式全域搜尋已達上限，但尚未找到合法方案。"
        elif scoring_preference_ids:
            main_issue = solver_search.SCORING_PREFERENCE
            issue_message = (
                "合法候選充足，但全域結果集中使用同一材料 Pattern，"
                "可能來自評分偏好。"
            )

        escalation_reasons = []
        for record in stage_records[:-1]:
            if record.get("decision") == "進入下一搜尋階段":
                escalation_reasons.extend(record.get("reasons", []))

        final_unique = int(
            stage_records[-1].get("unique_solution_count", 0)
            if stage_records
            else 0
        )
        return solver_search.SolverDiagnostics(
            solver_type="support",
            search_status=(
                "candidate_insufficient"
                if insufficient_ids
                else "completed"
                if legal_found
                else "no_legal_solution"
            ),
            search_stage=(stage_records[-1]["stage"] if stage_records else "PHASE1"),
            legal_solution_found=legal_found,
            infeasibility_proven=False,
            search_limit_reached=limit_reached,
            search_was_escalated=len(stage_records) > 1,
            result_is_stable=bool(
                final_assessment and final_assessment.result_is_stable
            ),
            candidate_count=sum(
                int(
                    ((status.get("diagnostics", {}) or {}).get("diagnostics", {}) or {})
                    .get("candidate_pool_valid_count", 0)
                    or 0
                )
                for status in candidate_statuses
            ),
            valid_candidate_count=sum(
                int(status.get("actual_valid_count", 0) or 0)
                for status in candidate_statuses
            ),
            retained_candidate_count=sum(
                int(status.get("actual_valid_count", 0) or 0)
                for status in candidate_statuses
            ),
            unique_solution_count=final_unique,
            best_score_history=list(stage_scores),
            escalation_reasons=list(dict.fromkeys(escalation_reasons)),
            stopping_reason=(
                final_assessment.stopping_reason
                if final_assessment is not None
                else "單體候選不足，未進入全域配置"
            ),
            main_issue_category=main_issue,
            main_issue_message=issue_message,
            secondary_issue_categories=secondary,
            issue_counts=dict(issue_counts),
            affected_component_ids=list(dict.fromkeys(
                missing_ids
                + insufficient_ids
                + concentrated_ids
                + scoring_preference_ids
            )),
            component_candidate_counts={
                status["config"].support_id: int(
                    status.get("actual_valid_count", 0) or 0
                )
                for status in candidate_statuses
                if status["config"].support_id in insufficient_ids
            },
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            stage_records=stage_records,
        )


__all__ = [
    "OptimizationProgress",
    "OptimizeSupportZone",
    "OptimizeSupportZoneRequest",
    "OptimizeSupportZoneResult",
]
