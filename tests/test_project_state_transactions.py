import ast
import copy
import inspect
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bracing_optimizer.application.material_spec_editing import (
    MaterialSpecEditOperation,
    MaterialSpecEditRequest,
    MaterialSpecEditing,
)
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.project_service import ProjectService
from bracing_optimizer.infrastructure.project_persistence import DxfWorkflowStatus
from main import SupportInputApp
from tests.project_state_test_support import (
    assert_formal_state_unchanged,
    formal_state_snapshot,
)


class ProjectStateTransactionFixture(unittest.TestCase):
    def build_app(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = Mock()
        app.project_data = ProjectDataModel(
            walers=[{
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 1000,
                "EndY": 0,
                "material_spec": "H350",
            }],
            inventory=[{
                "ItemCode": "I1",
                "Usage": "圍令",
                "Spec": "H350",
                "Length": 1000,
                "Qty": 10,
            }],
            material_specs=[{"Usage": "圍令", "Spec": "RC"}],
        )
        app._project_results = ProjectResultModel(
            result_items={"old": {"type": "waler", "result": {}}},
            persisted_payload={"best_solution": {}},
            last_calculated_time="2026-10-01T00:00:00",
        )
        app.solver_memory = {"old": 1}
        app.support_candidate_cache = {"old": 1}
        app.dxf_workflow_status = DxfWorkflowStatus.NONE
        app.dxf_review_session = None
        app.dxf_last_import_debug = {"old": True}
        app.dxf_asset = {"sha256": "old"}
        app.dxf_asset_status_report = object()
        app.last_dxf_compatibility_report = object()
        app.last_dxf_recovery_summary = object()
        app.last_cad_validation_report = object()
        app.current_project_path = Path("old/project.json")
        app.project_dirty = False
        app.project_dirty_reason = ""
        app.projection_stale = False
        app.projection_error = ""
        app.cad_ack_unresolved_event_id = None
        app.cad_ack_unresolved_event = None
        app.cad_import_enabled = False
        app._cad_poll_after_id = None
        app.treeviews = {}
        app.table_columns = {
            "walers": ["WalerID"],
            "struts": ["StrutID"],
            "braces": ["BraceID"],
        }
        app._refresh_tree = Mock()
        app._refresh_results_tree = Mock()
        app._update_material_summary = Mock()
        app.update_preview = Mock()
        app._refresh_project_status_display = Mock()
        app._refresh_dxf_workflow_ui = Mock()
        app._refresh_cad_import_status = Mock()
        app._update_project_action_states = Mock()
        app._update_window_title = Mock()
        app._select_results_tab = Mock()
        app.show_result = Mock()
        app._get_result_tree_info = Mock(return_value={"group_iid": "result:1"})
        return app


class FormalStateSnapshotTests(ProjectStateTransactionFixture):
    def test_snapshot_helper_detects_mixed_old_and_new_state(self):
        app = self.build_app()
        before = formal_state_snapshot(app)
        app.current_project_path = Path("new/project.json")

        with self.assertRaises(AssertionError):
            assert_formal_state_unchanged(self, before, app)


class CommitSurfaceTests(unittest.TestCase):
    def test_commit_helper_contains_only_plain_self_assignments(self):
        tree = ast.parse(textwrap.dedent(inspect.getsource(
            SupportInputApp._commit_runtime_outcome
        )))
        function = tree.body[0]
        statements = function.body[1:]  # docstring
        self.assertTrue(statements)
        self.assertTrue(all(isinstance(node, ast.Assign) for node in statements))
        forbidden = (ast.Call, ast.AugAssign, ast.Subscript)
        self.assertFalse(any(
            isinstance(node, forbidden)
            for statement in statements
            for node in ast.walk(statement)
        ))
        targets = {
            statement.targets[0].attr
            for statement in statements
            if isinstance(statement.targets[0], ast.Attribute)
        }
        property_names = {
            name
            for name, value in SupportInputApp.__dict__.items()
            if isinstance(value, property)
        }
        self.assertTrue(targets)
        self.assertFalse(targets & property_names)
        self.assertNotIn("__setattr__", SupportInputApp.__dict__)

    def test_main_commit_targets_have_no_tk_trace(self):
        source = inspect.getsource(SupportInputApp)
        self.assertNotIn("trace_add", source)
        self.assertNotIn("trace_variable", source)
        self.assertNotIn(".trace(", source)


class MutationFailureBoundaryTests(ProjectStateTransactionFixture):
    def test_support_stage_failure_leaves_formal_state_unchanged(self):
        app = self.build_app()
        before = formal_state_snapshot(app)
        solution = SimpleNamespace(plans=[], total_score=0, valid=True)
        app._build_material_summary_payload = Mock(
            side_effect=RuntimeError("summary failed")
        )

        with self.assertRaisesRegex(RuntimeError, "summary failed"):
            app._store_result_item("Z1", "support", solution)

        assert_formal_state_unchanged(self, before, app)

    def test_support_projection_failure_keeps_complete_committed_result(self):
        app = self.build_app()
        old_results = app._project_results
        solution = SimpleNamespace(plans=[], total_score=0, valid=True)
        app._refresh_results_tree.side_effect = RuntimeError("tree failed")

        with self.assertRaisesRegex(RuntimeError, "tree failed"):
            app._store_result_item("Z1", "support", solution)

        self.assertIsNot(app._project_results, old_results)
        self.assertIn("Z1", app.result_items)
        self.assertTrue(app.project_dirty)
        self.assertEqual(app.project_dirty_reason, "成果配置已變更")
        self.assertTrue(app.projection_stale)

    def test_single_waler_projection_failure_keeps_complete_result_metadata(self):
        app = self.build_app()
        old_results = app._project_results
        app._refresh_results_tree.side_effect = RuntimeError("tree failed")
        result = {
            "waler_id": "W1",
            "top_results": [{"segments": [1000]}],
            "required_length": 1000,
            "material_spec": "H350",
        }

        with self.assertRaisesRegex(RuntimeError, "tree failed"):
            app._store_waler_result(result)

        self.assertIsNot(app._project_results, old_results)
        self.assertTrue(any(
            key.startswith("W1-") for key in app.result_items
        ))
        self.assertIsNotNone(app._project_results.last_calculated_time)
        self.assertIsNotNone(app._project_results.persisted_payload)
        self.assertTrue(app.project_dirty)
        self.assertTrue(app.projection_stale)

    def test_load_projection_failure_keeps_new_clean_project(self):
        app = self.build_app()
        hydrated = SimpleNamespace(
            project_path=Path("new/project.json"),
            project_data=ProjectDataModel(walers=[{"WalerID": "NEW"}]),
            project_results=ProjectResultModel(),
            workflow_status=DxfWorkflowStatus.REVIEW,
            dxf_import_state={"new": True},
            dxf_asset={"sha256": "new"},
        )
        app._refresh_tree.side_effect = RuntimeError("projection failed")

        with self.assertRaisesRegex(RuntimeError, "projection failed"):
            app._adopt_hydrated_project(hydrated, dxf_status_report="new-status")

        self.assertIs(app.project_data, hydrated.project_data)
        self.assertIs(app._project_results, hydrated.project_results)
        self.assertEqual(app.solver_memory, {})
        self.assertEqual(app.support_candidate_cache, {})
        self.assertEqual(app.current_project_path, hydrated.project_path)
        self.assertFalse(app.project_dirty)
        self.assertEqual(app.project_dirty_reason, "")
        self.assertTrue(app.projection_stale)

    def test_material_cache_staging_failure_keeps_formal_state_unchanged(self):
        class FailingCopyDict(dict):
            def __deepcopy__(self, memo):
                raise RuntimeError("cache copy failed")

        app = self.build_app()
        outcome = SimpleNamespace(
            project_data=copy.deepcopy(app.project_data),
            project_results=copy.deepcopy(app._project_results),
            clear_solver_memory=False,
            clear_support_candidate_cache=False,
            changed_tables=("material_specs",),
            update_material_summary=False,
            dirty_reason="輸入資料已變更",
        )
        old_project = app.project_data
        old_results = app._project_results
        old_path = app.current_project_path
        app.solver_memory = FailingCopyDict(old=1)
        old_solver_memory = app.solver_memory

        with self.assertRaisesRegex(RuntimeError, "cache copy failed"):
            app._adopt_material_spec_edit(outcome)

        self.assertIs(app.project_data, old_project)
        self.assertIs(app._project_results, old_results)
        self.assertIs(app.solver_memory, old_solver_memory)
        self.assertEqual(app.current_project_path, old_path)
        self.assertFalse(app.project_dirty)


class ProjectionRecoveryTests(ProjectStateTransactionFixture):
    def test_recovery_menu_remains_after_failure_and_is_removed_after_success(self):
        app = self.build_app()
        app.menu_bar = Mock()
        app.file_menu = Mock()
        app.project_menu = Mock()
        app.project_menu_index = 1
        app._validated_current_project_target = Mock(return_value=None)
        app._reprojection_menu_visible = False
        app.projection_stale = True
        app._sync_main_menu_projection()
        before = formal_state_snapshot(app)
        app._project_all_runtime_state = Mock(
            side_effect=RuntimeError("projection failed")
        )

        with patch("main.messagebox.showerror"):
            self.assertFalse(app._reproject_all_from_committed_state())

        self.assertTrue(app.projection_stale)
        self.assertTrue(app._reprojection_menu_visible)
        self.assertEqual(app.menu_bar.insert_command.call_count, 1)
        app.menu_bar.delete.assert_not_called()
        assert_formal_state_unchanged(self, before, app)

        app._project_all_runtime_state.side_effect = None
        self.assertTrue(app._reproject_all_from_committed_state())
        self.assertFalse(app.projection_stale)
        self.assertFalse(app._reprojection_menu_visible)
        app.menu_bar.delete.assert_called_once_with(2)

    def test_full_reprojection_unlocks_only_after_every_step_succeeds(self):
        failure_points = (
            "_refresh_tree",
            "_refresh_results_tree",
            "_update_material_summary",
            "update_preview",
            "_refresh_project_status_display",
            "_refresh_dxf_workflow_ui",
            "_refresh_cad_import_status",
            "_sync_current_table_from_active_tabs",
            "_update_context_toolbar",
            "_update_project_action_states",
            "_update_window_title",
        )
        for failure_point in failure_points:
            with self.subTest(failure_point=failure_point):
                app = self.build_app()
                app.projection_stale = True
                app.notebook = object()
                app.context_toolbar = object()
                app._sync_current_table_from_active_tabs = Mock()
                app._update_context_toolbar = Mock()
                before = formal_state_snapshot(app)
                getattr(app, failure_point).side_effect = RuntimeError(
                    f"{failure_point} failed"
                )

                self.assertFalse(app._reproject_all_from_committed_state())
                self.assertTrue(app.projection_stale)
                assert_formal_state_unchanged(self, before, app)

        app = self.build_app()
        app.projection_stale = True
        self.assertTrue(app._reproject_all_from_committed_state())
        self.assertFalse(app.projection_stale)

    def test_stale_projection_blocks_manual_edit(self):
        app = self.build_app()
        app.projection_stale = True

        with self.assertRaisesRegex(RuntimeError, "重新整理全部畫面"):
            app._commit_project_field_edit("walers", 0, "WalerID", "W2")

        self.assertEqual(app.walers[0]["WalerID"], "W1")

    def test_stale_projection_blocks_result_visibility_mutation(self):
        app = self.build_app()
        app.projection_stale = True
        before = copy.deepcopy(app.result_items)

        with self.assertRaisesRegex(RuntimeError, "重新整理全部畫面"):
            app._toggle_result_visibility("old")

        self.assertEqual(app.result_items, before)


if __name__ == "__main__":
    unittest.main()
