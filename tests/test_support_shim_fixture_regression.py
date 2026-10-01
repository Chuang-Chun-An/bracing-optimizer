import hashlib
import json
import unittest
from pathlib import Path

from bracing_optimizer.algorithms import support
from bracing_optimizer.application.optimize_support_zone import (
    OptimizeSupportZone,
    OptimizeSupportZoneRequest,
)
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.solver_input_builder import SupportInputBuilder
from bracing_optimizer.domain.material_rules import MaterialRatioTargets


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_FIXTURE = (
    PROJECT_ROOT / "project_cases" / "Y1A站第一層支撐" / "project.json"
)
INVENTORY_FIXTURE = PROJECT_ROOT / "data" / "inventory.json"


def _plan_signature(plan):
    return (
        str(plan.support_id),
        tuple(tuple(piece) for piece in plan.pieces),
        float(plan.score),
        tuple(sorted(dict(plan.breakdown).items())),
        bool(plan.valid),
        str(plan.reason),
    )


def _digest(value) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@unittest.skipUnless(
    PROJECT_FIXTURE.is_file() and INVENTORY_FIXTURE.is_file(),
    "Y1A Support Solver regression fixtures are unavailable",
)
class SupportShimRealFixtureRegressionTests(unittest.TestCase):
    def test_y1a_full_support_solution_matches_pre_change_snapshot(self):
        project_payload = json.loads(
            PROJECT_FIXTURE.read_text(encoding="utf-8")
        )
        inventory = json.loads(
            INVENTORY_FIXTURE.read_text(encoding="utf-8")
        )["inventory"]
        project = ProjectDataModel.from_case_data(
            project_payload["input_data"],
            default_inventory=inventory,
        )
        zone_input = SupportInputBuilder().build_zone(project, "DXF")
        cache = {}
        result = OptimizeSupportZone(cache).execute(
            OptimizeSupportZoneRequest(
                input=zone_input,
                material_ratio_targets=MaterialRatioTargets.normalized(
                    38,
                    40,
                    22,
                ),
                material_ratio_weight=support.SUPPORT_MATERIAL_RATIO_WEIGHT,
            )
        )

        candidate_sets = sorted(
            tuple(sorted(
                _plan_signature(plan)
                for plan in entry["candidates"]
            ))
            for entry in cache.values()
        )
        solution = result.solution
        solution_signature = (
            float(solution.total_score),
            bool(solution.valid),
            tuple(_plan_signature(plan) for plan in solution.plans),
        )

        self.assertEqual(len(zone_input.configs), 15)
        self.assertEqual(sorted(len(items) for items in candidate_sets), [100] * 7)
        self.assertEqual(
            _digest(candidate_sets),
            "1687838ec81ecf7f0d76f4bf2f7021e951bb5b01916431c33a40966e08a65767",
        )
        self.assertEqual(
            _digest(solution_signature),
            "9d8f605345b506794ecbe2725a04bfdb483058e8de3820b0cca62affc14f58f9",
        )
        self.assertEqual(solution.total_score, 80886.95652173914)
        self.assertTrue(solution.valid)
        self.assertEqual(
            [plan.support_id for plan in solution.plans],
            [f"S{index}" for index in range(15, 0, -1)],
        )
