"""Application use case for optimizing one Waler.

The use case owns configuration, staged GA search, result merging, and
diagnostics.  It deliberately has no GUI or threading dependency.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable

from bracing_optimizer.algorithms import solver_search, wales
from bracing_optimizer.application.solver_input_builder import WalerProblemInput
from bracing_optimizer.domain.material_rules import MaterialRatioTargets


@dataclass(frozen=True)
class OptimizeWalerRequest:
    input: WalerProblemInput
    material_ratio_targets: MaterialRatioTargets


@dataclass(frozen=True)
class WalerOptimizationProgress:
    stage: str
    message: str


@dataclass(frozen=True)
class OptimizeWalerResult:
    solutions: tuple[dict, ...]
    diagnostics: solver_search.SolverDiagnostics
    config: wales.Config


ProgressCallback = Callable[[WalerOptimizationProgress], None]
LogCallback = Callable[..., None]


class OptimizeWaler:
    """Run the complete, GUI-independent Waler optimization workflow."""

    CACHE_SCHEMA = "waler_tail_adjustment_v1"

    def __init__(
        self,
        *,
        search_policy: solver_search.SolverSearchPolicy = (
            solver_search.DEFAULT_SEARCH_POLICY
        ),
    ) -> None:
        self.search_policy = search_policy

    def build_cache_key(self, request: OptimizeWalerRequest) -> tuple:
        """Identify equivalent requests for the current in-memory result cache."""

        return (
            self.CACHE_SCHEMA,
            *self.search_policy.cache_token,
            request.input.waler_id,
            int(request.input.total_length),
            tuple(sorted(int(point) for point in request.input.forbidden_points)),
            float(request.material_ratio_targets.short),
            float(request.material_ratio_targets.mid),
            float(request.material_ratio_targets.long),
            tuple(sorted(int(length) for length in request.input.purchasable_lengths)),
        )

    def execute(
        self,
        request: OptimizeWalerRequest,
        *,
        on_progress: ProgressCallback | None = None,
        logger: LogCallback | None = None,
    ) -> OptimizeWalerResult:
        """Execute synchronously and return solutions, diagnostics, and config."""

        cfg = self._build_config(request)
        wales.set_logger(logger or print)
        try:
            return self._run_search(request, cfg, on_progress)
        finally:
            wales.set_logger(print)

    def _build_config(self, request: OptimizeWalerRequest) -> wales.Config:
        first_stage = self.search_policy.waler_search_stages[0]
        return wales.Config(
            total_length=int(request.input.total_length),
            support_points=list(request.input.forbidden_points),
            min_piece_length=1000,
            max_piece_length=10000,
            joint_clearance_to_support=300,
            candidate_joint_step=500,
            purchasable_lengths=list(request.input.purchasable_lengths),
            short_segment_ratio_target=request.material_ratio_targets.short,
            mid_segment_ratio_target=request.material_ratio_targets.mid,
            long_segment_ratio_target=request.material_ratio_targets.long,
            population_size=first_stage.population_size,
            generations=first_stage.generations,
            crossover_rate=0.85,
            mutation_rate=0.08,
            elite_size=8,
            tournament_k=4,
            top_n=5,
        )

    @staticmethod
    def _emit_progress(
        callback: ProgressCallback | None,
        stage: str,
        message: str,
    ) -> None:
        if callback is not None:
            callback(WalerOptimizationProgress(stage, message))

    def _run_search(
        self,
        request: OptimizeWalerRequest,
        cfg: wales.Config,
        on_progress: ProgressCallback | None,
    ) -> OptimizeWalerResult:
        policy = self.search_policy
        all_results = []
        stage_records = []
        best_score_history = []
        escalation_reasons = []
        final_assessment = None

        for stage_index, stage in enumerate(policy.waler_search_stages):
            stage_cfg = copy.deepcopy(cfg)
            stage_cfg.generations = stage.generations
            stage_cfg.population_size = stage.population_size
            self._emit_progress(
                on_progress,
                stage.name,
                "正在建立配置候選並檢查工程合法性……",
            )
            wales.logger("")
            wales.logger(
                f"[搜尋階段 {stage.name}／{policy.waler_search_stages[-1].name}]"
            )
            wales.logger(f"Generations：{stage.generations}")
            wales.logger(f"Population：{stage.population_size}")
            wales.logger(f"Seed：{stage.random_seed}")

            stage_diagnostics = {}
            stage_results = wales.evolve(
                stage_cfg,
                list(request.input.stock_items),
                seed=stage.random_seed,
                diagnostics_out=stage_diagnostics,
            )
            all_results.extend(stage_results)
            stage_history = list(
                stage_diagnostics.get("best_score_history", []) or []
            )
            best_score_history.extend(stage_history)
            valid_count = int(
                stage_diagnostics.get("valid_candidate_count", 0) or 0
            )
            unique_count = int(
                stage_diagnostics.get("unique_valid_solution_count", 0) or 0
            )
            final_assessment = solver_search.assess_waler_stage(
                valid_solution_count=valid_count,
                unique_solution_count=unique_count,
                best_score_history=stage_history,
                is_last_stage=(
                    stage_index == len(policy.waler_search_stages) - 1
                ),
                policy=policy,
            )
            best_score = min(
                (
                    float(item.get("score", float("inf")))
                    for item in stage_results
                ),
                default=None,
            )
            stage_record = {
                "stage": stage.name,
                "generations": stage.generations,
                "population_size": stage.population_size,
                "random_seed": stage.random_seed,
                "legal_solution_found": valid_count > 0,
                "valid_solution_count": valid_count,
                "unique_solution_count": unique_count,
                "best_score": best_score,
                "tail_score_improvement": (
                    solver_search.relative_score_improvement(
                        stage_history[-policy.stability_window],
                        min(stage_history[-policy.stability_window:]),
                    )
                    if len(stage_history) >= policy.stability_window
                    else None
                ),
                "result_is_stable": final_assessment.result_is_stable,
                "decision": (
                    "進入下一搜尋階段"
                    if final_assessment.should_escalate
                    else "停止搜尋"
                ),
                "reasons": list(final_assessment.reasons),
            }
            stage_records.append(stage_record)
            wales.logger(f"合法方案：{'是' if valid_count else '否'}")
            wales.logger(
                "最佳分數：" + ("無" if best_score is None else f"{best_score:.2f}")
            )
            wales.logger(f"合法方案數：{valid_count}")
            wales.logger(f"合法且唯一方案：{unique_count}")
            wales.logger(f"決策：{stage_record['decision']}")
            wales.logger(
                "原因："
                + (
                    "、".join(final_assessment.reasons)
                    if final_assessment.reasons
                    else final_assessment.stopping_reason
                )
            )
            if not final_assessment.should_escalate:
                break
            escalation_reasons.extend(final_assessment.reasons)
            self._emit_progress(
                on_progress,
                "search_escalated",
                "初始結果仍可改善，系統正在進一步搜尋……",
            )

        results = solver_search.merge_waler_results(
            all_results,
            limit=cfg.top_n,
            precision=policy.score_comparison_precision,
        )
        diagnostics = self._build_diagnostics(
            request=request,
            cfg=cfg,
            results=results,
            stage_records=stage_records,
            best_score_history=best_score_history,
            escalation_reasons=escalation_reasons,
            final_assessment=final_assessment,
        )
        self._emit_progress(
            on_progress,
            "result_processing",
            "正在整理結果與診斷……",
        )
        return OptimizeWalerResult(tuple(results), diagnostics, cfg)

    def _build_diagnostics(
        self,
        *,
        request: OptimizeWalerRequest,
        cfg: wales.Config,
        results: list[dict],
        stage_records: list[dict],
        best_score_history: list[float],
        escalation_reasons: list[str],
        final_assessment: solver_search.SearchStageAssessment | None,
    ) -> solver_search.SolverDiagnostics:
        policy = self.search_policy
        legal_found = any(bool(item.get("valid")) for item in results)
        final_record = stage_records[-1] if stage_records else {}
        final_unique = int(final_record.get("unique_solution_count", 0) or 0)
        reached_last_stage = bool(
            final_record.get("stage") == policy.waler_search_stages[-1].name
        )
        limit_reached = bool(
            reached_last_stage
            and final_assessment is not None
            and final_assessment.reasons
        )
        path_feasible = wales.is_joint_path_feasible(cfg)
        main_issue = solver_search.NO_ISSUE
        issue_message = ""
        secondary = []
        affected_ids = []
        if not legal_found and not path_feasible:
            main_issue = solver_search.ENGINEERING_CONSTRAINT_LIMITED
            issue_message = "目前材料長度與禁止區無法形成合法的圍令分段路徑。"
            affected_ids = [request.input.waler_id]
        elif not legal_found:
            main_issue = solver_search.SEARCH_INSUFFICIENT
            issue_message = "啟發式搜尋已達上限，但尚未找到合法方案。"
            affected_ids = [request.input.waler_id]
        elif limit_reached:
            main_issue = solver_search.SEARCH_INSUFFICIENT
            issue_message = "已找到合法方案，但搜尋達上限時仍未完全穩定。"
            if final_unique < policy.minimum_unique_solution_count:
                secondary.append(solver_search.CANDIDATE_INSUFFICIENT)
                affected_ids = [request.input.waler_id]

        return solver_search.SolverDiagnostics(
            solver_type="waler",
            search_status="completed" if legal_found else "no_legal_solution",
            search_stage=str(final_record.get("stage", "")),
            legal_solution_found=legal_found,
            infeasibility_proven=False,
            search_limit_reached=limit_reached,
            search_was_escalated=len(stage_records) > 1,
            result_is_stable=bool(
                final_assessment and final_assessment.result_is_stable
            ),
            candidate_count=sum(
                int(record.get("population_size", 0) or 0)
                for record in stage_records
            ),
            valid_candidate_count=int(
                final_record.get("valid_solution_count", 0) or 0
            ),
            retained_candidate_count=len(results),
            unique_solution_count=final_unique,
            best_score_history=best_score_history,
            escalation_reasons=list(dict.fromkeys(escalation_reasons)),
            stopping_reason=(
                final_assessment.stopping_reason
                if final_assessment is not None
                else "搜尋未開始"
            ),
            main_issue_category=main_issue,
            main_issue_message=issue_message,
            secondary_issue_categories=secondary,
            affected_component_ids=affected_ids,
            policy_id=policy.policy_id,
            policy_version=policy.policy_version,
            stage_records=stage_records,
        )


__all__ = [
    "OptimizeWaler",
    "OptimizeWalerRequest",
    "OptimizeWalerResult",
    "WalerOptimizationProgress",
]
