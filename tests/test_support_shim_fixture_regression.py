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


def _build_y1a_support_project(inventory) -> ProjectDataModel:
    walers = [
        {
            "WalerID": "W2",
            "StartX": 0,
            "StartY": 21300,
            "EndX": 95600,
            "EndY": 21300,
            "material_spec": "",
        },
        {
            "WalerID": "W3",
            "StartX": 0,
            "StartY": 0,
            "EndX": 95600,
            "EndY": 0,
            "material_spec": "",
        },
    ]
    support_rows = (
        ("S1", 3550, "8297.94,8801.94,12497.9,13001.9", "8549.94,12749.9"),
        ("S2", 13050, "8261.15,8765.03,12534.8,13038.7", "8549.94,12749.9"),
        ("S3", 19050, "7598.07,8101.94,13197.9,13701.8", "7849.94,13449.9"),
        ("S4", 25050, "7590.1,8093.97,13205.9,13709.8", "7849.94,13449.9"),
        ("S5", 31050, "7448.07,7951.94,13347.9,13851.8", "7699.94,13599.9"),
        ("S6", 36050, "7447.94,7951.94,13347.9,13851.9", "7699.94,13599.9"),
        ("S7", 42050, "7447.94,7951.94,13347.9,13851.9", "7699.94,13599.9"),
        ("S8", 48050, "7447.94,7951.94,13347.9,13851.9", "7699.93,13599.9"),
        ("S9", 53550, "7447.94,7951.94,13347.9,13851.9", "7699.94,13599.9"),
        ("S10", 59550, "7447.94,7951.94,13347.9,13851.9", "7699.94,13599.9"),
        ("S11", 65550, "7455.89,7959.89,13340,13844", "7699.94,13599.9"),
        ("S12", 71550, "7597.94,8101.94,13197.9,13701.9", "7849.94,13449.9"),
        ("S13", 77550, "7634.77,8138.77,13161.1,13665.1", "7849.94,13449.9"),
        ("S14", 83550, "8297.94,8801.94,12497.9,13001.9", "8549.94,12749.9"),
        ("S15", 92050, "8297.94,8801.94,12497.9,13001.9", "8549.94,12749.9"),
    )
    struts = [
        {
            "StrutID": support_id,
            "FromWaler": "W3",
            "ToWaler": "W2",
            "StartX": x,
            "StartY": 0,
            "EndX": x,
            "EndY": 21300,
            "material_spec": "",
            "BeamPositions": beam_positions,
            "ColumnPositions": column_positions,
            "TargetJackRegion": 2,
            "Zoning": "DXF",
        }
        for support_id, x, beam_positions, column_positions in support_rows
    ]
    return ProjectDataModel(
        walers=walers,
        struts=struts,
        inventory=inventory,
    )


@unittest.skipUnless(
    INVENTORY_FIXTURE.is_file(),
    "Support Solver inventory is unavailable",
)
class SupportShimRealFixtureRegressionTests(unittest.TestCase):
    def test_y1a_full_support_solution_matches_pre_change_snapshot(self):
        inventory = json.loads(
            INVENTORY_FIXTURE.read_text(encoding="utf-8")
        )["inventory"]
        project = _build_y1a_support_project(inventory)
        zone_input = SupportInputBuilder().build_zone(project, "DXF")
        cache = {}
        optimizer = OptimizeSupportZone(cache)
        result = optimizer.execute(
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
        optimizer.adopt_candidate_cache_updates(result)

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
