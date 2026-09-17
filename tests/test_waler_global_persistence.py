import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from bracing_optimizer.algorithms.waler_global import (
    WalerGlobalDiagnostics,
    WalerGlobalSolution,
    build_global_candidate,
)
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.solver_input_builder import WalerProblemInput
from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfCompatibilityChecker,
)
from main import SupportInputApp


def candidate(waler_id, rank, segments, score):
    return build_global_candidate(
        waler_id=waler_id,
        candidate_rank=rank,
        payload={
            "valid": True,
            "segments": segments,
            "joints": [sum(segments[:index]) for index in range(1, len(segments))],
            "pieces": [("steel", length) for length in segments],
            "score": score,
            "buy_count": 0,
            "distinct_groups": len(set(segments)),
        },
        local_best_score=10,
    )


class GlobalResult:
    def __init__(self):
        candidates = (
            candidate("W1", 2, [5_000, 7_000], 12),
            candidate("W2", 1, [9_000, 5_000], 10),
        )
        self.solution = WalerGlobalSolution(
            selected_candidates=candidates,
            total_short=2,
            total_mid=1,
            total_long=1,
            total_out=0,
            total_out_distance_mm=0,
            short_ratio=0.5,
            mid_ratio=0.25,
            long_ratio=0.25,
            ratio_deviation=0.6,
            total_local_regret=2,
            changed_waler_count=1,
            objective_tuple=(0, 0, 0.6, 2, 1, (2, 1)),
            valid=True,
        )
        self.diagnostics = WalerGlobalDiagnostics(
            waler_count=2,
            raw_candidate_count=4,
            retained_candidate_count_after_signature_merge=4,
            transition_count=8,
            final_state_count=3,
            target_ratio={"short": 0.25, "mid": 0.5, "long": 0.25},
            final_objective=self.solution.objective_tuple,
            changed_waler_ids=("W1",),
        )
        self.records = {
            item.waler_id: SimpleNamespace(
                waler_input=WalerProblemInput(
                    waler_id=item.waler_id,
                    start_point=(0, 0),
                    end_point=(12_000, 0),
                    total_length=12_000,
                    forbidden_points=(4_000,),
                    material_spec="H400x400",
                    stock_items=(),
                    purchasable_lengths=(5_000, 7_000, 9_000),
                ),
                result=SimpleNamespace(
                    diagnostics=SimpleNamespace(
                        to_dict=lambda: {
                            "solver_type": "waler",
                            "search_stage": "STANDARD",
                        }
                    )
                ),
            )
            for item in candidates
        }

    def local_result_for(self, waler_id):
        return self.records.get(waler_id)


class WalerGlobalPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_app(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = None
        app.project_cases_dir = self.root
        app.project_data = ProjectDataModel(
            walers=[
                {
                    "WalerID": "W1",
                    "StartX": 0,
                    "StartY": 0,
                    "EndX": 12_000,
                    "EndY": 0,
                    "material_spec": "H400x400",
                },
                {
                    "WalerID": "W2",
                    "StartX": 0,
                    "StartY": 1_000,
                    "EndX": 12_000,
                    "EndY": 1_000,
                    "material_spec": "H400x400",
                },
            ],
            inventory=[
                {
                    "ItemCode": "W-5000",
                    "Spec": "H400x400",
                    "Usage": "圍令",
                    "Length": 5_000,
                    "Qty": 99,
                },
                {
                    "ItemCode": "W-7000",
                    "Spec": "H400x400",
                    "Usage": "圍令",
                    "Length": 7_000,
                    "Qty": 99,
                },
                {
                    "ItemCode": "W-9000",
                    "Spec": "H400x400",
                    "Usage": "圍令",
                    "Length": 9_000,
                    "Qty": 99,
                },
            ],
        )
        app._project_results = ProjectResultModel()
        app.current_project_path = None
        app.project_dirty = False
        app.project_dirty_reason = ""
        app.dxf_last_import_debug = None
        app.dxf_asset = None
        app.dxf_asset_status_report = None
        app.last_dxf_compatibility_report = None
        app.dxf_asset_manager = DxfAssetManager()
        app.dxf_compatibility_checker = DxfCompatibilityChecker()
        app.solver_memory = {}
        app.support_candidate_cache = {}
        app._refresh_tree = lambda _name: None
        app._refresh_results_tree = lambda **_kwargs: None
        app._refresh_project_case_list = lambda **_kwargs: None
        app._select_results_tab = lambda: None
        app.update_preview = lambda **_kwargs: None
        app._refresh_dxf_workflow_ui = lambda: None
        app.show_result = lambda _text: None

        def mark_dirty(reason=""):
            app.project_dirty = True
            app.project_dirty_reason = reason

        def clear_dirty():
            app.project_dirty = False
            app.project_dirty_reason = ""

        app._mark_project_dirty = mark_dirty
        app._clear_project_dirty = clear_dirty
        return app

    def test_global_apply_save_and_reopen_preserves_metadata_and_material_stats(self):
        app = self.make_app()
        result = GlobalResult()

        outcome = app._apply_waler_global_result(result)

        self.assertTrue(outcome.committed)
        self.assertTrue(outcome.refreshed)
        self.assertTrue(app.project_dirty)
        before_items = copy.deepcopy(app.result_items)
        before_usage = ProjectResultModel(
            result_items=app.result_items,
        ).collect_visible_material_usage()

        saved_path = app.save_project_case("global-roundtrip")

        self.assertTrue(saved_path.is_file())
        self.assertFalse(app.project_dirty)

        reopened = self.make_app()
        reopened.load_project_case("global-roundtrip", silent=True)

        self.assertFalse(reopened.project_dirty)
        self.assertEqual(set(reopened.result_items), set(before_items))
        after_usage = ProjectResultModel(
            result_items=reopened.result_items,
        ).collect_visible_material_usage()
        self.assertEqual(after_usage, before_usage)

        for result_id, original_item in before_items.items():
            restored_item = reopened.result_items[result_id]
            original = original_item["result"]
            restored = restored_item["result"]
            self.assertEqual(restored["waler_id"], original["waler_id"])
            self.assertTrue(restored["global_selected"])
            self.assertEqual(
                restored["selected_plan"]["global_candidate_rank"],
                original["selected_plan"]["global_candidate_rank"],
            )
            self.assertEqual(
                restored["selected_plan"]["global_local_regret"],
                original["selected_plan"]["global_local_regret"],
            )
            self.assertEqual(
                restored["selected_plan"]["segments"],
                original["selected_plan"]["segments"],
            )
            self.assertEqual(
                restored["selected_plan"]["joints"],
                original["selected_plan"]["joints"],
            )
            self.assertEqual(
                restored["selected_plan"]["pieces"],
                [
                    list(piece)
                    for piece in original["selected_plan"]["pieces"]
                ],
            )
            self.assertEqual(
                restored["material_spec"],
                original["material_spec"],
            )
            self.assertEqual(
                restored["global_search_diagnostics"],
                json.loads(json.dumps(original["global_search_diagnostics"])),
            )

        diagnostics = reopened.result_items["W1-方案2"]["result"][
            "global_search_diagnostics"
        ]
        self.assertEqual(diagnostics["algorithm_version"], "waler_global_dp_v1")
        self.assertEqual(
            diagnostics["target_ratio"],
            {"short": 0.25, "mid": 0.5, "long": 0.25},
        )
        summary = diagnostics["solution_summary"]
        self.assertEqual(
            (summary["total_short"], summary["total_mid"], summary["total_long"]),
            (2, 1, 1),
        )
        self.assertEqual(summary["total_out"], 0)
        self.assertEqual(summary["total_out_distance_mm"], 0)
        self.assertEqual(summary["ratio_deviation"], 0.6)
        self.assertEqual(summary["changed_waler_count"], 1)
        self.assertEqual(summary["changed_waler_ids"], ["W1"])


if __name__ == "__main__":
    unittest.main()
