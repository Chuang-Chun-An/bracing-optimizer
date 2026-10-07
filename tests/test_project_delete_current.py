from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.infrastructure.project_persistence import DxfWorkflowStatus
from main import SupportInputApp
from tests.project_state_test_support import (
    assert_formal_state_unchanged,
    formal_state_snapshot,
)


class DeleteCurrentProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.project_cases_dir = Path(self.temp_dir.name)

    def build_app(self, *, managed=True):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = Mock()
        app.project_cases_dir = self.project_cases_dir
        if managed:
            path = self.project_cases_dir / "current" / "project.json"
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path = self.project_cases_dir / "current.json"
        path.write_text("{}", encoding="utf-8")

        app.project_data = ProjectDataModel(
            walers=[{"WalerID": "W1"}],
            inventory=[{"ItemCode": "old"}],
        )
        app._project_results = ProjectResultModel(
            result_items={"old": {"type": "waler", "result": {}}},
            persisted_payload={"old": True},
            last_calculated_time="2026-10-07T00:00:00",
        )
        app.solver_memory = {"old": True}
        app.support_candidate_cache = {"old": True}
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_review_session = {"old": True}
        app.dxf_last_import_debug = {"source_path": "old.dxf"}
        app.dxf_asset = {"old": True}
        app.dxf_asset_status_report = object()
        app.last_dxf_compatibility_report = object()
        app.last_dxf_recovery_summary = object()
        app.last_cad_validation_report = object()
        app.current_project_path = path
        app.project_dirty = True
        app.project_dirty_reason = "pending"
        app.projection_stale = False
        app.projection_error = ""
        app.cad_ack_unresolved_event_id = None
        app.cad_ack_unresolved_event = None
        app.cad_import_enabled = False
        app.dxf_dialog_active = False
        app._cad_poll_after_id = None
        app.treeviews = {}
        app._load_default_inventory = Mock(
            return_value=[{"ItemCode": "default"}]
        )
        blank_status = object()
        app._ensure_project_service = Mock(
            return_value=SimpleNamespace(
                inspect_dxf_state=Mock(return_value=blank_status)
            )
        )
        app._refresh_tree = Mock()
        app._refresh_results_tree = Mock()
        app._update_material_summary = Mock()
        app.update_preview = Mock()
        app._refresh_project_status_display = Mock()
        app._refresh_dxf_workflow_ui = Mock()
        app._refresh_cad_import_status = Mock()
        app._update_project_action_states = Mock()
        app._update_window_title = Mock()
        return app, path, blank_status

    def test_target_validation_accepts_only_current_managed_or_legacy_file(self):
        managed, managed_path, _ = self.build_app(managed=True)
        self.assertEqual(
            managed._validated_current_project_target(),
            (managed_path.resolve(), True),
        )

        legacy, legacy_path, _ = self.build_app(managed=False)
        self.assertEqual(
            legacy._validated_current_project_target(),
            (legacy_path.resolve(), False),
        )

        invalid_paths = (
            None,
            self.project_cases_dir.parent / "outside.json",
            self.project_cases_dir / "nested" / "too-deep" / "project.json",
            self.project_cases_dir / "missing.json",
        )
        for path in invalid_paths:
            with self.subTest(path=path):
                app, _, _ = self.build_app(managed=True)
                app.current_project_path = path
                self.assertIsNone(app._validated_current_project_target())

    def test_new_and_delete_share_the_same_mutation_guard_rejections(self):
        for attribute, value, message in (
            ("cad_ack_unresolved_event_id", "event-1", "ACK"),
            ("projection_stale", True, "重新整理全部畫面"),
        ):
            with self.subTest(attribute=attribute):
                new_app, _, _ = self.build_app(managed=True)
                setattr(new_app, attribute, value)
                before_new = formal_state_snapshot(new_app)
                with self.assertRaisesRegex(RuntimeError, message):
                    new_app._reset_to_new_project()
                assert_formal_state_unchanged(self, before_new, new_app)

                delete_app, target, _ = self.build_app(managed=True)
                setattr(delete_app, attribute, value)
                before_delete = formal_state_snapshot(delete_app)
                with (
                    patch("main.messagebox.askyesno") as confirm,
                    patch("main.messagebox.showwarning"),
                ):
                    self.assertFalse(delete_app._delete_current_project_case())
                confirm.assert_not_called()
                self.assertTrue(target.exists())
                assert_formal_state_unchanged(self, before_delete, delete_app)

    def test_solver_operation_and_open_dxf_review_do_not_add_delete_guards(self):
        for attribute, value in (
            ("solver_operation_registry", object()),
            ("dxf_dialog_active", True),
        ):
            with self.subTest(attribute=attribute):
                app, target, _ = self.build_app(managed=True)
                setattr(app, attribute, value)
                with patch("main.messagebox.askyesno", return_value=False) as confirm:
                    self.assertFalse(app._delete_current_project_case())
                confirm.assert_called_once()
                self.assertTrue(target.exists())

    def test_cancel_shows_complete_details_and_never_saves(self):
        app, target, _ = self.build_app(managed=True)
        managed_dxf = target.parent / "source" / "source.dxf"
        managed_dxf.parent.mkdir()
        managed_dxf.write_bytes(b"dxf")
        app._save_current_project = Mock()
        before = formal_state_snapshot(app)

        with patch("main.messagebox.askyesno", return_value=False) as confirm:
            self.assertFalse(app._delete_current_project_case())

        text = confirm.call_args.args[1]
        self.assertIn("current", text)
        self.assertIn(str(target.resolve()), text)
        self.assertIn("包含管理 DXF：是", text)
        self.assertIn("具有未儲存變更：是", text)
        self.assertIn("無法復原", text)
        app._save_current_project.assert_not_called()
        self.assertTrue(target.exists())
        assert_formal_state_unchanged(self, before, app)

    def test_blank_outcome_preparation_failure_prevents_filesystem_delete(self):
        app, target, _ = self.build_app(managed=True)
        before = formal_state_snapshot(app)
        app._load_default_inventory.side_effect = RuntimeError("inventory failed")

        with (
            patch("main.messagebox.askyesno", return_value=True),
            patch("main.messagebox.showerror"),
        ):
            self.assertFalse(app._delete_current_project_case())

        self.assertTrue(target.exists())
        assert_formal_state_unchanged(self, before, app)

    def test_filesystem_failure_preserves_current_runtime(self):
        app, target, _ = self.build_app(managed=True)
        before = formal_state_snapshot(app)
        with (
            patch("main.messagebox.askyesno", return_value=True),
            patch("main.shutil.rmtree", side_effect=OSError("denied")),
            patch("main.messagebox.showerror"),
        ):
            self.assertFalse(app._delete_current_project_case())

        self.assertTrue(target.exists())
        assert_formal_state_unchanged(self, before, app)

    def test_success_deletes_exact_managed_or_legacy_target_and_adopts_blank(self):
        for managed in (True, False):
            with self.subTest(managed=managed):
                app, target, blank_status = self.build_app(managed=managed)
                deleted_container = target.parent if managed else target
                if managed:
                    sibling = target.parent / "kept.txt"
                    sibling.write_text("inside project", encoding="utf-8")
                with (
                    patch("main.messagebox.askyesno", return_value=True),
                    patch("main.messagebox.showinfo"),
                ):
                    self.assertTrue(app._delete_current_project_case())

                self.assertFalse(deleted_container.exists())
                self.assertEqual(
                    [row["ItemCode"] for row in app.project_data.inventory],
                    ["default"],
                )
                self.assertEqual(app.result_items, {})
                self.assertEqual(app.solver_memory, {})
                self.assertEqual(app.support_candidate_cache, {})
                self.assertEqual(app.dxf_workflow_status, DxfWorkflowStatus.NONE)
                self.assertIsNone(app.dxf_review_session)
                self.assertIsNone(app.dxf_last_import_debug)
                self.assertIsNone(app.dxf_asset)
                self.assertIs(app.dxf_asset_status_report, blank_status)
                self.assertIsNone(app.current_project_path)
                self.assertFalse(app.project_dirty)
                self.assertEqual(app.project_dirty_reason, "")

    def test_projection_failure_after_delete_keeps_blank_state_and_recovers(self):
        app, target, _ = self.build_app(managed=True)
        app._refresh_tree.side_effect = RuntimeError("tree failed")

        with (
            patch("main.messagebox.askyesno", return_value=True),
            patch("main.messagebox.showerror"),
        ):
            self.assertTrue(app._delete_current_project_case())

        self.assertFalse(target.parent.exists())
        self.assertIsNone(app.current_project_path)
        self.assertFalse(app.project_dirty)
        self.assertEqual(app.result_items, {})
        self.assertTrue(app.projection_stale)

        app._refresh_tree.side_effect = None
        self.assertTrue(app._reproject_all_from_committed_state())
        self.assertFalse(app.projection_stale)


if __name__ == "__main__":
    unittest.main()
