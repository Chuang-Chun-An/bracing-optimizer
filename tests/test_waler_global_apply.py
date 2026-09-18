import copy
import unittest
from types import SimpleNamespace

from bracing_optimizer.algorithms.waler_global import (
    WalerGlobalDiagnostics,
    WalerGlobalSolution,
    build_global_candidate,
)
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.solver_input_builder import WalerProblemInput
from main import SupportInputApp


def make_candidate(waler_id, rank, segments, score=10):
    return build_global_candidate(
        waler_id=waler_id,
        candidate_rank=rank,
        payload={
            "valid": True,
            "segments": segments,
            "joints": [sum(segments[:index]) for index in range(1, len(segments))],
            "pieces": [("steel", length) for length in segments],
            "score": score,
        },
        local_best_score=10,
    )


def make_input(waler_id):
    return WalerProblemInput(
        waler_id=waler_id,
        start_point=(0, 0),
        end_point=(12_000, 0),
        total_length=12_000,
        forbidden_points=(4_000,),
        material_spec="H400x400",
        stock_items=(),
        purchasable_lengths=(5_000, 7_000, 9_000),
    )


class FakeGlobalResult:
    def __init__(self, candidates, missing_record_id=None):
        self.solution = WalerGlobalSolution(
            selected_candidates=tuple(candidates),
            total_short=sum(item.short_count for item in candidates),
            total_mid=sum(item.mid_count for item in candidates),
            total_long=sum(item.long_count for item in candidates),
            total_out=sum(item.out_count for item in candidates),
            total_out_distance_mm=sum(item.out_distance_mm for item in candidates),
            short_ratio=0.25,
            mid_ratio=0.5,
            long_ratio=0.25,
            ratio_deviation=0.1,
            total_local_regret=sum(item.local_regret for item in candidates),
            changed_waler_count=sum(item.candidate_rank != 1 for item in candidates),
            objective_tuple=(0, 0, 0.1, 0, 0, tuple(item.candidate_rank for item in candidates)),
            valid=True,
        )
        self.diagnostics = WalerGlobalDiagnostics(
            waler_count=len(candidates),
            target_ratio={"short": 0.2, "mid": 0.5, "long": 0.3},
        )
        self.records = {
            item.waler_id: SimpleNamespace(
                waler_input=make_input(item.waler_id),
                result=SimpleNamespace(
                    diagnostics=SimpleNamespace(
                        to_dict=lambda: {"solver_type": "waler"}
                    )
                ),
            )
            for item in candidates
            if item.waler_id != missing_record_id
        }

    def local_result_for(self, waler_id):
        return self.records.get(waler_id)


class WalerGlobalApplyTests(unittest.TestCase):
    def make_app(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app._project_results = ProjectResultModel(result_items={
            "W1-方案1": {
                "type": "waler",
                "result": {
                    "waler_id": "W1",
                    "manual_modified": True,
                    "selected_plan": {"segments": [5_000]},
                },
                "visible": True,
            },
            "Z1": {
                "type": "support",
                "result": SimpleNamespace(plans=[]),
                "visible": True,
            },
        })
        app.project_dirty = False
        app.project_dirty_reason = ""
        app._refresh_results_tree = lambda **_kwargs: None
        app._select_results_tab = lambda: None
        app.update_preview = lambda: None
        app.show_result = lambda _message: None
        return app

    def test_apply_replaces_all_selected_walers_once_and_preserves_support(self):
        app = self.make_app()
        app._mark_results_updated = lambda: setattr(app, "project_dirty", True)
        result = FakeGlobalResult((
            make_candidate("W1", 1, [5_000, 7_000]),
            make_candidate("W2", 2, [5_000, 7_000], score=12),
        ))

        outcome = app._apply_waler_global_result(result)

        self.assertIn("Z1", app.result_items)
        waler_items = {
            result_id: item
            for result_id, item in app.result_items.items()
            if item["type"] == "waler"
        }
        self.assertEqual(set(waler_items), {"W1-方案1", "W2-方案2"})
        self.assertEqual(len(waler_items), 2)
        self.assertNotIn("manual_modified", waler_items["W1-方案1"]["result"])
        self.assertTrue(waler_items["W2-方案2"]["visible"])
        self.assertTrue(
            waler_items["W2-方案2"]["result"]["global_selected"]
        )
        self.assertTrue(app.project_dirty)
        self.assertTrue(outcome.committed)
        self.assertTrue(outcome.refreshed)

    def test_project_result_model_stages_global_apply_without_mutating_source(self):
        model = ProjectResultModel(result_items={
            "W1-方案1": {
                "type": "waler",
                "result": {
                    "waler_id": "W1",
                    "selected_plan": {"segments": [5_000]},
                },
                "visible": True,
            },
            "Z1": {
                "type": "support",
                "result": SimpleNamespace(plans=[]),
                "visible": True,
            },
        })
        result = FakeGlobalResult((
            make_candidate("W1", 2, [5_000, 7_000], score=12),
        ))

        staged = model.stage_waler_global_result(result)

        self.assertIn("W1-方案1", model.result_items)
        self.assertNotIn("W1-方案1", staged.result_items)
        self.assertIn("W1-方案2", staged.result_items)
        self.assertIn("Z1", staged.result_items)
        self.assertEqual(staged.selected_candidates[0].candidate_rank, 2)

    def test_project_result_model_stages_single_batch_without_mutating_source(self):
        global_item = {
            "type": "waler",
            "result": {
                "waler_id": "W1",
                "option_index": 2,
                "selected_plan": {"segments": [5_000, 7_000]},
                "global_selected": True,
            },
            "visible": True,
        }
        model = ProjectResultModel(result_items={
            "W1-方案2": copy.deepcopy(global_item),
        })

        staged = model.stage_single_waler_result(
            {
                "waler_id": "W1",
                "top_results": [{"segments": [6_000, 6_000]}],
                "required_length": 12_000,
            },
            (),
        )

        self.assertEqual(model.result_items, {"W1-方案2": global_item})
        self.assertIn("W1-方案2", staged.result_items)
        self.assertIn("W1-單支方案1", staged.result_items)
        self.assertTrue(staged.preserved_global_result)

    def test_missing_staged_record_leaves_existing_results_unchanged(self):
        app = self.make_app()
        before = copy.deepcopy(app.result_items)
        result = FakeGlobalResult(
            (make_candidate("W1", 1, [5_000, 7_000]),),
            missing_record_id="W1",
        )

        with self.assertLogs("main", level="ERROR"):
            outcome = app._apply_waler_global_result(result)

        self.assertEqual(app.result_items, before)
        self.assertFalse(outcome.committed)
        self.assertFalse(outcome.refreshed)

    def test_commit_failure_rolls_back_every_waler_result(self):
        app = self.make_app()
        before = copy.deepcopy(app.result_items)
        app.project_result = {"old": True}
        app.last_calculated_time = "before"

        def fail_commit():
            app.project_result = {"partial": True}
            app.last_calculated_time = "partial"
            raise RuntimeError("commit failed")

        app._mark_results_updated = fail_commit
        refresh_calls = []
        app._refresh_results_tree = lambda **_kwargs: refresh_calls.append(
            "tree"
        )
        result = FakeGlobalResult((
            make_candidate("W1", 1, [5_000, 7_000]),
            make_candidate("W2", 1, [7_000, 5_000]),
        ))

        with self.assertLogs("main", level="ERROR"):
            outcome = app._apply_waler_global_result(result)

        self.assertEqual(app.result_items, before)
        self.assertEqual(app.project_result, {"old": True})
        self.assertEqual(app.last_calculated_time, "before")
        self.assertFalse(outcome.committed)
        self.assertEqual(refresh_calls, [])

    def test_result_tree_refresh_failure_keeps_committed_global_results(self):
        app = self.make_app()
        app._mark_results_updated = lambda: setattr(app, "project_dirty", True)
        app._refresh_results_tree = lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("tree refresh failed")
        )
        result = FakeGlobalResult((
            make_candidate("W1", 2, [5_000, 7_000], score=12),
        ))

        with self.assertLogs("main", level="ERROR"):
            outcome = app._apply_waler_global_result(result)

        self.assertTrue(outcome.committed)
        self.assertFalse(outcome.refreshed)
        self.assertIn("W1-方案2", app.result_items)
        self.assertTrue(
            app.result_items["W1-方案2"]["result"]["global_selected"]
        )
        payload = ProjectResultModel(
            result_items=app.result_items,
        ).to_payload([])
        saved_ids = {
            item["id"]
            for item in payload["best_solution"]["result_items"]
        }
        self.assertIn("W1-方案2", saved_ids)

    def test_preview_refresh_failure_keeps_committed_global_results(self):
        app = self.make_app()
        app._mark_results_updated = lambda: setattr(app, "project_dirty", True)
        refresh_calls = []
        app._refresh_results_tree = lambda **_kwargs: refresh_calls.append(
            "tree"
        )
        app._select_results_tab = lambda: refresh_calls.append("tab")

        def fail_preview():
            refresh_calls.append("preview")
            raise RuntimeError("preview refresh failed")

        app.update_preview = fail_preview
        result = FakeGlobalResult((
            make_candidate("W1", 1, [5_000, 7_000]),
        ))

        with self.assertLogs("main", level="ERROR"):
            outcome = app._apply_waler_global_result(result)

        self.assertTrue(outcome.committed)
        self.assertFalse(outcome.refreshed)
        self.assertEqual(refresh_calls, ["tree", "tab", "preview"])
        self.assertIn("W1-方案1", app.result_items)

    def test_legacy_cleanup_uses_exact_waler_identity_and_preserves_support(self):
        app = self.make_app()
        support_item = copy.deepcopy(app.result_items["Z1"])
        w10_item = {
            "type": "waler",
            "result": {"selected_plan": {"segments": [9_000]}},
            "visible": True,
        }
        app.result_items = {
            "W1-方案1": {
                "type": "waler",
                "result": {"selected_plan": {"segments": [5_000]}},
                "visible": True,
            },
            "old-w2": {
                "type": "waler",
                "result": {
                    "waler_id": "W2",
                    "selected_plan": {"segments": [7_000]},
                },
                "visible": True,
            },
            "W10-方案1": copy.deepcopy(w10_item),
            "Z1": support_item,
        }
        app._mark_results_updated = lambda: None
        result = FakeGlobalResult((
            make_candidate("W1", 2, [5_000, 7_000], score=12),
            make_candidate("W2", 1, [7_000, 5_000]),
        ))

        outcome = app._apply_waler_global_result(result)

        self.assertTrue(outcome.committed)
        self.assertNotIn("W1-方案1", app.result_items)
        self.assertNotIn("old-w2", app.result_items)
        self.assertIn("W1-方案2", app.result_items)
        self.assertIn("W2-方案1", app.result_items)
        self.assertEqual(app.result_items["W10-方案1"], w10_item)
        self.assertEqual(app.result_items["Z1"], support_item)
        identities = [
            ProjectResultModel.waler_result_identity(result_id, item)
            for result_id, item in app.result_items.items()
            if item.get("type") == "waler"
        ]
        self.assertEqual(identities.count("W1"), 1)
        self.assertEqual(identities.count("W2"), 1)
        self.assertEqual(identities.count("W10"), 1)

    def test_single_solver_preserves_global_result_and_adds_five_namespaced_results(self):
        app = self.make_app()
        global_item = {
            "type": "waler",
            "result": {
                "waler_id": "W1",
                "option_index": 3,
                "selected_plan": {"segments": [5_000, 7_000]},
                "global_selected": True,
                "result_series": "global",
            },
            "visible": True,
        }
        app.result_items = {
            "W1-方案3": copy.deepcopy(global_item),
            "Z1": {
                "type": "support",
                "result": SimpleNamespace(plans=[]),
                "visible": True,
            },
        }
        app.walers = []
        app._mark_results_updated = lambda: None

        app._store_waler_result({
            "waler_id": "W1",
            "top_results": [
                {"segments": [5_000 + index, 7_000 - index]}
                for index in range(5)
            ],
            "ratio_targets": {"short": 0.2, "mid": 0.5, "long": 0.3},
            "required_length": 12_000,
        })

        self.assertEqual(app.result_items["W1-方案3"], global_item)
        self.assertIn("Z1", app.result_items)
        expected_single_ids = {
            f"W1-單支方案{index}" for index in range(1, 6)
        }
        self.assertTrue(expected_single_ids <= set(app.result_items))
        self.assertEqual(
            len([
                item
                for item in app.result_items.values()
                if item.get("type") == "waler"
            ]),
            6,
        )
        self.assertTrue(app.result_items["W1-方案3"]["visible"])
        self.assertTrue(all(
            not app.result_items[result_id]["visible"]
            for result_id in expected_single_ids
        ))
        self.assertEqual(
            app._get_result_tree_info(
                "W1-方案3",
                app.result_items["W1-方案3"],
            )["child_label"],
            "全域方案3",
        )
        self.assertEqual(
            app._get_result_tree_info(
                "W1-單支方案1",
                app.result_items["W1-單支方案1"],
            )["child_label"],
            "單支方案1",
        )

    def test_repeated_single_solver_replaces_only_previous_single_batch(self):
        app = self.make_app()
        app.result_items = {
            "W1-方案2": {
                "type": "waler",
                "result": {
                    "waler_id": "W1",
                    "option_index": 2,
                    "selected_plan": {"segments": [5_000, 7_000]},
                    "global_selected": True,
                },
                "visible": True,
            },
        }
        app.walers = []
        app._mark_results_updated = lambda: None
        base_result = {
            "waler_id": "W1",
            "ratio_targets": {"short": 0.2, "mid": 0.5, "long": 0.3},
            "required_length": 12_000,
        }
        first = dict(base_result, top_results=[
            {"segments": [5_000, 7_000], "score": index}
            for index in range(5)
        ])
        second = dict(base_result, top_results=[
            {"segments": [4_000, 8_000], "score": 100 + index}
            for index in range(5)
        ])

        app._store_waler_result(first)
        app._store_waler_result(second)

        waler_items = {
            result_id: item
            for result_id, item in app.result_items.items()
            if item.get("type") == "waler"
        }
        self.assertEqual(
            set(waler_items),
            {"W1-方案2"} | {
                f"W1-單支方案{index}" for index in range(1, 6)
            },
        )
        self.assertEqual(
            waler_items["W1-單支方案1"]["result"]["selected_plan"]["score"],
            100,
        )

    def test_single_solver_without_global_result_keeps_legacy_result_ids(self):
        app = self.make_app()
        app.result_items = {}
        app.walers = []
        app._mark_results_updated = lambda: None

        app._store_waler_result({
            "waler_id": "W1",
            "top_results": [{"segments": [5_000, 7_000]}],
            "required_length": 12_000,
        })

        self.assertIn("W1-方案1", app.result_items)
        self.assertNotIn("W1-單支方案1", app.result_items)


if __name__ == "__main__":
    unittest.main()
