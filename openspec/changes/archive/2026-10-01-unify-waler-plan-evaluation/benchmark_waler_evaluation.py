"""Repeatable before/after benchmark for Waler evaluation unification.

The fixture values intentionally match ``tests/test_optimize_waler.py`` and
``tests/test_optimize_waler_global.py``.  The Global fixture uses the real
``OptimizeWaler`` implementation instead of the unit test's fake optimizer so
that evaluator overhead is included in the measurement.
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from bracing_optimizer.algorithms.solver_search import DEFAULT_SEARCH_POLICY
from bracing_optimizer.application.optimize_waler import (
    OptimizeWaler,
    OptimizeWalerRequest,
)
from bracing_optimizer.application.optimize_waler_global import (
    OptimizeWalerGlobal,
    OptimizeWalerGlobalRequest,
)
from bracing_optimizer.application.solver_input_builder import WalerProblemInput
from bracing_optimizer.domain.material_rules import MaterialRatioTargets


REPEATS = 5
TARGETS = MaterialRatioTargets.normalized(20, 50, 30)


def single_input(waler_id: str = "W1") -> WalerProblemInput:
    """Match ``tests.test_optimize_waler.make_request``."""

    return WalerProblemInput(
        waler_id=waler_id,
        start_point=(0, 0),
        end_point=(12_000, 0),
        total_length=12_000,
        forbidden_points=(4_000,),
        material_spec="H400x400",
        purchasable_lengths=(4_000, 6_000, 8_000),
        stock_items=(),
    )


def global_input(waler_id: str) -> WalerProblemInput:
    """Match ``tests.test_optimize_waler_global.waler_input``."""

    return WalerProblemInput(
        waler_id=waler_id,
        start_point=(0, 0),
        end_point=(12_000, 0),
        total_length=12_000,
        forbidden_points=(),
        material_spec="H400x400",
        stock_items=(),
        purchasable_lengths=(1_000, 3_500, 5_000, 7_000, 9_000),
    )


def run_single() -> dict:
    result = OptimizeWaler().execute(
        OptimizeWalerRequest(single_input(), TARGETS),
        logger=lambda *_parts: None,
    )
    return {
        "solution_count": len(result.solutions),
        "candidate_count": result.diagnostics.candidate_count,
        "valid_candidate_count": result.diagnostics.valid_candidate_count,
        "retained_candidate_count": result.diagnostics.retained_candidate_count,
        "stage_records": result.diagnostics.stage_records,
        "solution_signature": [
            {
                "segments": item.get("segments"),
                "joints": item.get("joints"),
                "tail_adjustment": item.get("tail_adjustment"),
                "gap": item.get("gap"),
                "score": item.get("score"),
                "valid": item.get("valid"),
            }
            for item in result.solutions
        ],
    }


def run_global() -> dict:
    result = OptimizeWalerGlobal().execute(
        OptimizeWalerGlobalRequest(
            waler_inputs=(global_input("W1"), global_input("W2")),
            material_ratio_targets=TARGETS,
        ),
        logger=lambda *_parts: None,
    )
    return {
        "valid": result.solution.valid,
        "selected_count": len(result.solution.selected_candidates),
        "raw_candidate_count": result.diagnostics.raw_candidate_count,
        "retained_candidate_count": (
            result.diagnostics.retained_candidate_count_after_signature_merge
        ),
        "transition_count": result.diagnostics.transition_count,
        "local_runs": [
            {
                "waler_id": record.waler_input.waler_id,
                "solution_count": len(record.result.solutions),
                "candidate_count": record.result.diagnostics.candidate_count,
                "valid_candidate_count": (
                    record.result.diagnostics.valid_candidate_count
                ),
                "stage_records": record.result.diagnostics.stage_records,
            }
            for record in result.local_results
        ],
        "solution_signature": [
            {
                "waler_id": item.waler_id,
                "candidate_rank": item.candidate_rank,
                "segments": list(item.segments),
                "score": item.local_score,
            }
            for item in result.solution.selected_candidates
        ],
    }


def measure(name: str, run: Callable[[], dict]) -> dict:
    samples = []
    signatures = []
    for _ in range(REPEATS):
        started = time.perf_counter()
        signature = run()
        samples.append(time.perf_counter() - started)
        signatures.append(signature)
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise AssertionError(f"{name} produced non-deterministic result metadata")
    return {
        "raw_seconds": samples,
        "min_seconds": min(samples),
        "median_seconds": statistics.median(samples),
        "mean_seconds": statistics.mean(samples),
        "max_seconds": max(samples),
        "result": signatures[0],
    }


def main() -> None:
    policy = DEFAULT_SEARCH_POLICY
    report = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "timer": "time.perf_counter",
            "repeats": REPEATS,
        },
        "policy": {
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "waler_search_stages": [
                asdict(stage) for stage in policy.waler_search_stages
            ],
        },
        "single": measure("single", run_single),
        "global": measure("global", run_global),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
