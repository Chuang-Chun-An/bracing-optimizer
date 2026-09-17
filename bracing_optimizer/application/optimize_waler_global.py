"""Application use case for project-wide Waler candidate selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from bracing_optimizer.algorithms.waler_global import (
    WalerGlobalCandidate,
    WalerGlobalDiagnostics,
    WalerGlobalSolution,
    build_global_candidate,
    merge_equivalent_candidates,
    solve_global_waler_candidates,
)
from bracing_optimizer.application.optimize_waler import (
    OptimizeWaler,
    OptimizeWalerRequest,
    OptimizeWalerResult,
)
from bracing_optimizer.application.solver_input_builder import WalerProblemInput
from bracing_optimizer.domain.material_rules import MaterialRatioTargets


@dataclass(frozen=True)
class OptimizeWalerGlobalRequest:
    waler_inputs: tuple[WalerProblemInput, ...]
    material_ratio_targets: MaterialRatioTargets


@dataclass(frozen=True)
class WalerGlobalProgress:
    stage: str
    message: str


@dataclass(frozen=True)
class WalerLocalOptimizationRecord:
    waler_input: WalerProblemInput
    result: OptimizeWalerResult


@dataclass(frozen=True)
class OptimizeWalerGlobalResult:
    solution: WalerGlobalSolution
    diagnostics: WalerGlobalDiagnostics
    local_results: tuple[WalerLocalOptimizationRecord, ...] = ()

    def local_result_for(self, waler_id: str) -> WalerLocalOptimizationRecord | None:
        normalized_id = str(waler_id or "").strip()
        return next(
            (
                record
                for record in self.local_results
                if record.waler_input.waler_id == normalized_id
            ),
            None,
        )


ProgressCallback = Callable[[WalerGlobalProgress], None]
LogCallback = Callable[..., None]
WalerOptimizerFactory = Callable[[], OptimizeWaler]


class OptimizeWalerGlobal:
    """Run local candidate generation, then exact project-wide selection."""

    def __init__(
        self,
        optimize_waler_factory: WalerOptimizerFactory = OptimizeWaler,
    ) -> None:
        self.optimize_waler_factory = optimize_waler_factory

    @staticmethod
    def _emit_progress(
        callback: ProgressCallback | None,
        stage: str,
        message: str,
    ) -> None:
        if callback is not None:
            callback(WalerGlobalProgress(stage, message))

    def execute(
        self,
        request: OptimizeWalerGlobalRequest,
        *,
        on_progress: ProgressCallback | None = None,
        logger: LogCallback | None = None,
    ) -> OptimizeWalerGlobalResult:
        log = logger or (lambda *args: None)
        inputs = tuple(request.waler_inputs)
        waler_order = tuple(item.waler_id for item in inputs)
        log("=== 全部圍令最佳化 ===")
        log(f"圍令數：{len(inputs)}")

        local_records: list[WalerLocalOptimizationRecord] = []
        candidates_by_waler: dict[str, tuple[WalerGlobalCandidate, ...]] = {}
        raw_candidate_count = 0

        for index, waler_input in enumerate(inputs, start=1):
            waler_id = str(waler_input.waler_id or "").strip()
            self._emit_progress(
                on_progress,
                "local_candidate_generation",
                f"正在計算圍令 {waler_id}（{index}/{len(inputs)}）……",
            )
            log(f"\n--- {waler_id}：產生單支候選（{index}/{len(inputs)}）---")
            try:
                local_result = self.optimize_waler_factory().execute(
                    OptimizeWalerRequest(
                        input=waler_input,
                        material_ratio_targets=request.material_ratio_targets,
                    ),
                    logger=log,
                )
                local_records.append(WalerLocalOptimizationRecord(
                    waler_input=waler_input,
                    result=local_result,
                ))
                raw_solutions = tuple(local_result.solutions)
                raw_candidate_count += len(raw_solutions)
                valid_solutions = tuple(
                    (rank, payload)
                    for rank, payload in enumerate(raw_solutions, start=1)
                    if bool(payload.get("valid", False))
                )
                if not valid_solutions or valid_solutions[0][0] != 1:
                    return self._failure_result(
                        inputs=inputs,
                        targets=request.material_ratio_targets,
                        local_records=local_records,
                        raw_candidate_count=raw_candidate_count,
                        failed_waler_id=waler_id,
                        message=f"圍令 {waler_id} 沒有合法的第一名候選。",
                    )
                rank_one_score = float(valid_solutions[0][1]["score"])
                candidates = tuple(
                    build_global_candidate(
                        waler_id=waler_id,
                        candidate_rank=rank,
                        payload=payload,
                        local_best_score=rank_one_score,
                    )
                    for rank, payload in valid_solutions
                )
                candidates_by_waler[waler_id] = merge_equivalent_candidates(
                    candidates
                )
            except Exception as exc:
                return self._failure_result(
                    inputs=inputs,
                    targets=request.material_ratio_targets,
                    local_records=local_records,
                    raw_candidate_count=raw_candidate_count,
                    failed_waler_id=waler_id,
                    message=f"圍令 {waler_id} 候選建立失敗：{exc}",
                )

        retained_count = sum(len(items) for items in candidates_by_waler.values())
        log(f"\n單支候選：{raw_candidate_count}")
        log(f"全域代表候選：{retained_count}")
        log("正在進行 Exact DP……")
        self._emit_progress(
            on_progress,
            "global_exact_dp",
            "單支候選已完成，正在進行全域 Exact DP……",
        )
        solution, diagnostics = solve_global_waler_candidates(
            candidates_by_waler,
            request.material_ratio_targets,
            waler_order=waler_order,
            raw_candidate_count=raw_candidate_count,
        )
        self._log_result(log, solution, diagnostics)
        self._emit_progress(
            on_progress,
            "completed" if solution.valid else "failed",
            "全部圍令最佳化完成。" if solution.valid else solution.reason,
        )
        return OptimizeWalerGlobalResult(
            solution=solution,
            diagnostics=diagnostics,
            local_results=tuple(local_records),
        )

    @staticmethod
    def _failure_result(
        *,
        inputs: tuple[WalerProblemInput, ...],
        targets: MaterialRatioTargets,
        local_records: list[WalerLocalOptimizationRecord],
        raw_candidate_count: int,
        failed_waler_id: str,
        message: str,
    ) -> OptimizeWalerGlobalResult:
        solution = WalerGlobalSolution(reason=message)
        diagnostics = WalerGlobalDiagnostics(
            waler_count=len(inputs),
            raw_candidate_count=raw_candidate_count,
            target_ratio=targets.as_dict(),
            failed_waler_ids=(failed_waler_id,),
            messages=(message,),
        )
        return OptimizeWalerGlobalResult(
            solution=solution,
            diagnostics=diagnostics,
            local_results=tuple(local_records),
        )

    @staticmethod
    def _log_result(
        log: LogCallback,
        solution: WalerGlobalSolution,
        diagnostics: WalerGlobalDiagnostics,
    ) -> None:
        log(f"Transitions：{diagnostics.transition_count}")
        log(f"Merged states：{diagnostics.merged_state_count}")
        log(f"Final states：{diagnostics.final_state_count}")
        if not solution.valid:
            log(f"全域最佳化失敗：{solution.reason}")
            return
        log("\n最終：")
        log(f"Short：{solution.total_short}")
        log(f"Mid：{solution.total_mid}")
        log(f"Long：{solution.total_long}")
        log(f"Out：{solution.total_out}")
        log(
            "比例："
            f"{solution.short_ratio:.2%} / "
            f"{solution.mid_ratio:.2%} / "
            f"{solution.long_ratio:.2%}"
        )
        log(f"Out distance：{solution.total_out_distance_mm} mm")
        log(f"全域比例偏差：{solution.ratio_deviation:.6f}")
        log(f"Local regret：{solution.total_local_regret:.6f}")
        log(f"因全域協調改用非 #1：{solution.changed_waler_count} 支")
        if solution.changed_waler_ids:
            log("調整圍令：" + "、".join(solution.changed_waler_ids))
        log("限制：第一版未進行全場共用庫存扣除。")


__all__ = [
    "OptimizeWalerGlobal",
    "OptimizeWalerGlobalRequest",
    "OptimizeWalerGlobalResult",
    "WalerGlobalProgress",
    "WalerLocalOptimizationRecord",
]
