import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.infrastructure.project_persistence import (
    DxfWorkflowStatus,
    ProjectPersistenceError,
)
from bracing_optimizer.presentation.project_navigation import (
    NavigationGuardOutcome,
    ProjectSaveOutcome,
    ProjectSaveStatus,
)
from main import SupportInputApp


class _Variable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class ProjectNavigationFixture(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.project_cases_dir = Path(self.temp_dir.name)

    def build_app(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = Mock()
        app.project_cases_dir = self.project_cases_dir
        app.project_data = ProjectDataModel(
            walers=[{
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 1000,
                "EndY": 0,
            }]
        )
        app._project_results = ProjectResultModel(
            result_items={
                "W1-方案1": {
                    "type": "waler",
                    "result": {"waler_id": "W1", "manual_modified": True},
                }
            },
            persisted_payload={"best_solution": {"result_items": ["kept"]}},
            last_calculated_time="2026-09-23T12:00:00",
        )
        app.project_dirty = True
        app.project_dirty_reason = "manual edit"
        app.current_project_path = self.project_cases_dir / "current" / "project.json"
        app.project_case_var = _Variable("selected-case")
        app.dxf_last_import_debug = {"source_path": "source.dxf"}
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_review_session = {"coordinate_mode": "world"}
        app.dxf_asset = {"sha256": "abc"}
        app.dxf_asset_status_report = object()
        app.last_dxf_compatibility_report = object()
        app.solver_memory = {"cached": True}
        app.support_candidate_cache = {"cached": True}

        app._refresh_tree = Mock()
        app._refresh_results_tree = Mock()
        app._refresh_project_case_list = Mock()
        app.update_preview = Mock()
        app._refresh_dxf_workflow_ui = Mock()
        app._refresh_project_status_display = Mock()
        app._update_window_title = Mock()
        app._load_default_inventory = Mock(return_value=[])
        app._selected_project_case_name = Mock(return_value="target")
        app.load_project_case = Mock()
        app._ensure_project_service = Mock(
            return_value=SimpleNamespace(
                inspect_dxf_state=Mock(return_value=object()),
            )
        )
        return app

    @staticmethod
    def snapshot(app):
        return {
            "project_object": app.project_data,
            "project_data": app.project_data.to_case_data(),
            "result_object": app._project_results,
            "result_items": copy.deepcopy(app.result_items),
            "project_result": copy.deepcopy(app.project_result),
            "dirty": app.project_dirty,
            "dirty_reason": app.project_dirty_reason,
            "current_path": app.current_project_path,
            "dxf_state": copy.deepcopy(app.dxf_last_import_debug),
            "dxf_workflow": app.dxf_workflow_status,
            "dxf_review_session": copy.deepcopy(app.dxf_review_session),
            "dxf_asset": copy.deepcopy(app.dxf_asset),
            "ui_selection": app.project_case_var.get(),
        }

    def assert_snapshot_unchanged(self, before, app):
        after = self.snapshot(app)
        self.assertIs(after["project_object"], before["project_object"])
        self.assertIs(after["result_object"], before["result_object"])
        for key in before.keys() - {"project_object", "result_object"}:
            self.assertEqual(after[key], before[key], key)


class ProjectLifecycleCharacterizationTests(ProjectNavigationFixture):
    def test_fixture_observes_state_boundary_and_open_continuation(self):
        app = self.build_app()
        app.project_dirty = False

        app._load_selected_project_case()

        app.load_project_case.assert_called_once_with("target")

    def test_new_replaces_project_and_committed_result_models_at_continuation(self):
        app = self.build_app()
        app.project_dirty = False
        before = self.snapshot(app)

        app._new_project()

        self.assertIsNot(app.project_data, before["project_object"])
        self.assertIs(app._project_results, before["result_object"])
        self.assertEqual(app.result_items, {})
        self.assertIsNone(app.project_result)
        self.assertIsNone(app.current_project_path)
        self.assertEqual(app.project_case_var.get(), "")
        self.assertFalse(app.project_dirty)
        app._load_default_inventory.assert_called_once_with()

    def test_existing_path_save_routes_to_project_case_and_only_success_clears_dirty(self):
        app = self.build_app()
        saved_path = app.current_project_path

        def save(project_name):
            self.assertTrue(app.project_dirty)
            app._clear_project_dirty()
            return saved_path

        app.save_project_case = Mock(side_effect=save)

        with patch("main.messagebox.showinfo"):
            result = app._save_current_project()

        app.save_project_case.assert_called_once_with("current")
        self.assertEqual(result.status, ProjectSaveStatus.SAVED)
        self.assertEqual(result.path, saved_path)
        self.assertFalse(app.project_dirty)

    def test_unnamed_save_routes_to_existing_save_as_flow(self):
        app = self.build_app()
        app.current_project_path = None
        sentinel = object()
        app._save_project_as = Mock(return_value=sentinel)

        result = app._save_current_project()

        self.assertIs(result, sentinel)
        app._save_project_as.assert_called_once_with()

    def test_legacy_save_as_projection_keeps_path_or_none_contract(self):
        app = self.build_app()
        saved_path = self.project_cases_dir / "legacy" / "project.json"
        app._save_project_as = Mock(
            side_effect=(
                ProjectSaveOutcome.saved(saved_path),
                ProjectSaveOutcome.cancelled(),
            )
        )

        self.assertEqual(
            app._save_current_project_case_from_prompt(),
            saved_path,
        )
        self.assertIsNone(app._save_current_project_case_from_prompt())

    def test_save_as_cancel_preserves_all_current_state(self):
        app = self.build_app()
        app.current_project_path = None
        before = self.snapshot(app)

        with patch("main.simpledialog.askstring", return_value=None):
            result = app._save_project_as()

        self.assertEqual(result.status, ProjectSaveStatus.CANCELLED)
        self.assert_snapshot_unchanged(before, app)

    def test_save_as_blank_name_is_cancelled_without_persistence(self):
        app = self.build_app()
        app.current_project_path = None
        app.save_project_case = Mock()
        before = self.snapshot(app)

        with patch("main.simpledialog.askstring", return_value="   "):
            with patch("main.messagebox.showwarning") as showwarning:
                result = app._save_project_as()

        self.assertEqual(result.status, ProjectSaveStatus.CANCELLED)
        app.save_project_case.assert_not_called()
        showwarning.assert_called_once()
        self.assert_snapshot_unchanged(before, app)

    def test_save_as_declined_overwrite_is_cancelled_without_persistence(self):
        app = self.build_app()
        app.current_project_path = None
        target = self.project_cases_dir / "existing" / "project.json"
        target.parent.mkdir()
        target.write_text("{}", encoding="utf-8")
        app.save_project_case = Mock()
        before = self.snapshot(app)

        with patch("main.simpledialog.askstring", return_value="existing"):
            with patch("main.messagebox.askyesno", return_value=False):
                result = app._save_project_as()

        self.assertEqual(result.status, ProjectSaveStatus.CANCELLED)
        app.save_project_case.assert_not_called()
        self.assert_snapshot_unchanged(before, app)

    def test_save_as_success_returns_saved_outcome(self):
        app = self.build_app()
        app.current_project_path = None
        saved_path = self.project_cases_dir / "new-case" / "project.json"

        def save(_project_name):
            app.current_project_path = saved_path
            app._clear_project_dirty()
            return saved_path

        app.save_project_case = Mock(side_effect=save)

        with patch("main.simpledialog.askstring", return_value="new-case"):
            with patch("main.messagebox.showinfo"):
                result = app._save_project_as()

        self.assertEqual(result, ProjectSaveOutcome.saved(saved_path))
        app.save_project_case.assert_called_once_with("new-case")
        self.assertFalse(app.project_dirty)

    def test_save_as_persistence_failure_returns_failed_and_preserves_state(self):
        app = self.build_app()
        app.current_project_path = None
        app.save_project_case = Mock(side_effect=RuntimeError("write failed"))
        before = self.snapshot(app)

        with patch("main.simpledialog.askstring", return_value="new-case"):
            with patch("main.messagebox.showerror") as showerror:
                result = app._save_project_as()

        self.assertEqual(result.status, ProjectSaveStatus.FAILED)
        self.assertEqual(result.error, "write failed")
        showerror.assert_called_once()
        self.assert_snapshot_unchanged(before, app)

    def test_save_exception_preserves_all_current_state(self):
        app = self.build_app()
        before = self.snapshot(app)
        app.save_project_case = Mock(side_effect=RuntimeError("disk failed"))

        with patch("main.messagebox.showerror") as showerror:
            result = app._save_current_project()

        self.assertEqual(result.status, ProjectSaveStatus.FAILED)
        self.assertEqual(result.error, "disk failed")
        showerror.assert_called_once()
        self.assert_snapshot_unchanged(before, app)

    def test_open_load_failure_occurs_before_adopting_hydrated_state(self):
        app = self.build_app()
        project_path = self.project_cases_dir / "target" / "project.json"
        project_path.parent.mkdir()
        project_path.write_text("{}", encoding="utf-8")
        app._ensure_project_service = Mock(
            return_value=SimpleNamespace(
                load_project=Mock(side_effect=RuntimeError("invalid project")),
            )
        )
        before = self.snapshot(app)

        with self.assertRaisesRegex(RuntimeError, "invalid project"):
            SupportInputApp.load_project_case(app, "target", silent=True)

        self.assert_snapshot_unchanged(before, app)

    def test_schema_compatibility_failure_preserves_current_project_state(self):
        app = self.build_app()
        project_path = self.project_cases_dir / "target" / "project.json"
        project_path.parent.mkdir()
        project_path.write_text("{}", encoding="utf-8")
        error = ProjectPersistenceError(
            "專案版本不相容",
            "檔案版本高於目前支援版本，請使用較新程式開啟。",
        )
        app._ensure_project_service = Mock(
            return_value=SimpleNamespace(
                load_project=Mock(side_effect=error),
            )
        )
        before = self.snapshot(app)

        with self.assertRaises(ProjectPersistenceError) as raised:
            SupportInputApp.load_project_case(app, "target", silent=True)

        self.assertIs(raised.exception, error)
        self.assert_snapshot_unchanged(before, app)

    def test_open_adopts_only_the_hydrated_application_result(self):
        app = self.build_app()
        project_path = self.project_cases_dir / "target" / "project.json"
        project_path.parent.mkdir()
        project_path.write_text("{}", encoding="utf-8")
        hydrated = object()
        service = SimpleNamespace(
            load_project=Mock(
                return_value=SimpleNamespace(
                    payload={"schema_version": 3},
                    hydrated_project=hydrated,
                    dxf_status_report=object(),
                )
            )
        )
        app._ensure_project_service = Mock(return_value=service)
        app._adopt_hydrated_project = Mock()

        SupportInputApp.load_project_case(app, "target", silent=True)

        app._adopt_hydrated_project.assert_called_once_with(hydrated)
        service.load_project.assert_called_once()

    def test_manual_result_edit_commits_inside_existing_project_result_model(self):
        app = self.build_app()
        result_model = app._project_results
        before_payload = app.project_result
        app._recalculate_waler_plan = Mock(
            return_value={"segments": [400, 600], "legality": {"valid": True}}
        )
        app._build_material_summary_payload = Mock(return_value=[])

        app._apply_waler_plan_segments("W1-方案1", [400, 600])

        self.assertIs(app._project_results, result_model)
        self.assertIsNot(app.project_result, before_payload)
        self.assertEqual(
            app.result_items["W1-方案1"]["result"]["selected_plan"]["segments"],
            [400, 600],
        )
        self.assertTrue(app.project_dirty)
        self.assertEqual(app.project_dirty_reason, "成果配置已變更")


class MainWindowCloseOutcomeTests(ProjectNavigationFixture):
    def build_close_app(self):
        app = self.build_app()
        app._cad_poll_after_id = None
        app._save_main_ui_state = Mock()
        return app

    def test_close_destroys_after_saved_outcome(self):
        app = self.build_close_app()
        app._save_current_project = Mock(
            return_value=ProjectSaveOutcome.saved(app.current_project_path)
        )

        with patch("main.messagebox.askyesnocancel", return_value=True):
            app._on_main_window_close()

        app._save_current_project.assert_called_once_with()
        app._save_main_ui_state.assert_called_once_with()
        app.root.destroy.assert_called_once_with()

    def test_close_does_not_destroy_after_cancelled_or_failed_save(self):
        for outcome in (
            ProjectSaveOutcome.cancelled(),
            ProjectSaveOutcome.failed("write failed"),
        ):
            with self.subTest(status=outcome.status):
                app = self.build_close_app()
                app._save_current_project = Mock(return_value=outcome)

                with patch("main.messagebox.askyesnocancel", return_value=True):
                    app._on_main_window_close()

                app._save_main_ui_state.assert_not_called()
                app.root.destroy.assert_not_called()

    def test_close_discard_still_destroys_and_cancel_still_preserves(self):
        discard_app = self.build_close_app()
        with patch("main.messagebox.askyesnocancel", return_value=False):
            discard_app._on_main_window_close()
        discard_app.root.destroy.assert_called_once_with()

        cancel_app = self.build_close_app()
        with patch("main.messagebox.askyesnocancel", return_value=None):
            cancel_app._on_main_window_close()
        cancel_app.root.destroy.assert_not_called()


class DirtyNavigationGuardTests(ProjectNavigationFixture):
    NAVIGATION_CASES = (
        ("clean", False, None, ProjectSaveOutcome.failed("unused"), 1),
        ("existing saved", True, True, ProjectSaveOutcome.saved(Path("saved")), 1),
        ("unnamed saved", True, True, ProjectSaveOutcome.saved(Path("saved-as")), 1),
        ("discard", True, False, ProjectSaveOutcome.failed("unused"), 1),
        ("cancel", True, None, ProjectSaveOutcome.saved(Path("unused")), 0),
        ("save-as cancelled", True, True, ProjectSaveOutcome.cancelled(), 0),
        ("save failed", True, True, ProjectSaveOutcome.failed("write failed"), 0),
    )

    def test_clean_project_bypasses_prompt_and_save(self):
        app = self.build_app()
        app.project_dirty = False
        app._save_current_project = Mock()

        with patch("main.messagebox.askyesnocancel") as prompt:
            outcome = app._guard_unsaved_project_changes()

        self.assertEqual(outcome, NavigationGuardOutcome.PROCEED)
        prompt.assert_not_called()
        app._save_current_project.assert_not_called()

    def test_dirty_guard_maps_all_prompt_and_save_outcomes(self):
        cases = (
            (None, ProjectSaveOutcome.saved(Path("unused")), NavigationGuardOutcome.CANCELLED, 0),
            (False, ProjectSaveOutcome.saved(Path("unused")), NavigationGuardOutcome.PROCEED, 0),
            (True, ProjectSaveOutcome.saved(Path("saved")), NavigationGuardOutcome.PROCEED, 1),
            (True, ProjectSaveOutcome.cancelled(), NavigationGuardOutcome.CANCELLED, 1),
            (True, ProjectSaveOutcome.failed("failed"), NavigationGuardOutcome.CANCELLED, 1),
        )
        for decision, save_outcome, expected, save_calls in cases:
            with self.subTest(decision=decision, save=save_outcome.status):
                app = self.build_app()
                app._save_current_project = Mock(return_value=save_outcome)
                with patch(
                    "main.messagebox.askyesnocancel",
                    return_value=decision,
                ):
                    actual = app._guard_unsaved_project_changes()

                self.assertEqual(actual, expected)
                self.assertEqual(
                    app._save_current_project.call_count,
                    save_calls,
                )

    def test_guard_save_with_existing_path_uses_project_case_save(self):
        app = self.build_app()
        saved_path = app.current_project_path

        def save(_project_name):
            app._clear_project_dirty()
            return saved_path

        app.save_project_case = Mock(side_effect=save)
        with patch("main.messagebox.askyesnocancel", return_value=True):
            with patch("main.messagebox.showinfo"):
                outcome = app._guard_unsaved_project_changes()

        self.assertEqual(outcome, NavigationGuardOutcome.PROCEED)
        app.save_project_case.assert_called_once_with("current")

    def test_guard_save_with_unnamed_project_uses_save_as(self):
        app = self.build_app()
        app.current_project_path = None
        saved_path = self.project_cases_dir / "new-case" / "project.json"
        app._save_project_as = Mock(
            return_value=ProjectSaveOutcome.saved(saved_path)
        )

        with patch("main.messagebox.askyesnocancel", return_value=True):
            outcome = app._guard_unsaved_project_changes()

        self.assertEqual(outcome, NavigationGuardOutcome.PROCEED)
        app._save_project_as.assert_called_once_with()

    def test_new_calls_reset_once_only_after_guard_proceeds(self):
        for outcome, expected_calls in (
            (NavigationGuardOutcome.PROCEED, 1),
            (NavigationGuardOutcome.CANCELLED, 0),
        ):
            with self.subTest(outcome=outcome):
                app = self.build_app()
                app._guard_unsaved_project_changes = Mock(return_value=outcome)
                app._reset_to_new_project = Mock()

                app._new_project()

                self.assertEqual(
                    app._reset_to_new_project.call_count,
                    expected_calls,
                )

    def test_new_covers_clean_save_discard_cancel_and_failure_cases(self):
        for name, dirty, decision, save_outcome, expected_calls in self.NAVIGATION_CASES:
            with self.subTest(case=name):
                app = self.build_app()
                app.project_dirty = dirty
                app.current_project_path = (
                    None if name.startswith("unnamed") or name.startswith("save-as")
                    else app.current_project_path
                )
                app._save_current_project = Mock(return_value=save_outcome)
                app._reset_to_new_project = Mock()

                with patch(
                    "main.messagebox.askyesnocancel",
                    return_value=decision,
                ):
                    app._new_project()

                self.assertEqual(
                    app._reset_to_new_project.call_count,
                    expected_calls,
                )

    def test_open_calls_load_once_only_after_target_and_guard_are_valid(self):
        for outcome, expected_calls in (
            (NavigationGuardOutcome.PROCEED, 1),
            (NavigationGuardOutcome.CANCELLED, 0),
        ):
            with self.subTest(outcome=outcome):
                app = self.build_app()
                app._guard_unsaved_project_changes = Mock(return_value=outcome)

                app._load_selected_project_case()

                self.assertEqual(app.load_project_case.call_count, expected_calls)

        no_target = self.build_app()
        no_target._selected_project_case_name.return_value = ""
        no_target._guard_unsaved_project_changes = Mock()
        with patch("main.messagebox.showwarning"):
            no_target._load_selected_project_case()
        no_target._guard_unsaved_project_changes.assert_not_called()
        no_target.load_project_case.assert_not_called()

    def test_open_covers_clean_save_discard_cancel_and_failure_cases(self):
        for name, dirty, decision, save_outcome, expected_calls in self.NAVIGATION_CASES:
            with self.subTest(case=name):
                app = self.build_app()
                app.project_dirty = dirty
                app.current_project_path = (
                    None if name.startswith("unnamed") or name.startswith("save-as")
                    else app.current_project_path
                )
                app._save_current_project = Mock(return_value=save_outcome)

                with patch(
                    "main.messagebox.askyesnocancel",
                    return_value=decision,
                ):
                    app._load_selected_project_case()

                self.assertEqual(app.load_project_case.call_count, expected_calls)

    def test_new_cancelled_and_failed_save_preserve_full_snapshot(self):
        for save_outcome in (
            ProjectSaveOutcome.cancelled(),
            ProjectSaveOutcome.failed("write failed"),
        ):
            with self.subTest(status=save_outcome.status):
                app = self.build_app()
                before = self.snapshot(app)
                app._save_current_project = Mock(return_value=save_outcome)
                app._reset_to_new_project = Mock()

                with patch("main.messagebox.askyesnocancel", return_value=True):
                    app._new_project()

                app._reset_to_new_project.assert_not_called()
                self.assert_snapshot_unchanged(before, app)

    def test_open_cancelled_and_failed_save_preserve_full_snapshot(self):
        for save_outcome in (
            ProjectSaveOutcome.cancelled(),
            ProjectSaveOutcome.failed("write failed"),
        ):
            with self.subTest(status=save_outcome.status):
                app = self.build_app()
                before = self.snapshot(app)
                app._save_current_project = Mock(return_value=save_outcome)

                with patch("main.messagebox.askyesnocancel", return_value=True):
                    app._load_selected_project_case()

                app.load_project_case.assert_not_called()
                self.assert_snapshot_unchanged(before, app)

    def test_new_and_open_use_identical_guard_semantics(self):
        for decision, save_outcome, expected in (
            (False, ProjectSaveOutcome.failed("unused"), NavigationGuardOutcome.PROCEED),
            (None, ProjectSaveOutcome.saved(Path("unused")), NavigationGuardOutcome.CANCELLED),
            (True, ProjectSaveOutcome.saved(Path("saved")), NavigationGuardOutcome.PROCEED),
            (True, ProjectSaveOutcome.cancelled(), NavigationGuardOutcome.CANCELLED),
            (True, ProjectSaveOutcome.failed("failed"), NavigationGuardOutcome.CANCELLED),
        ):
            with self.subTest(decision=decision, save=save_outcome.status):
                outcomes = []
                for _destination in ("new", "open"):
                    app = self.build_app()
                    app._save_current_project = Mock(return_value=save_outcome)
                    with patch(
                        "main.messagebox.askyesnocancel",
                        return_value=decision,
                    ):
                        outcomes.append(app._guard_unsaved_project_changes())
                self.assertEqual(outcomes, [expected, expected])

    def test_destination_never_runs_before_save_reports_success(self):
        events = []
        app = self.build_app()
        app._save_current_project = Mock(
            side_effect=lambda: (
                events.append("save"),
                ProjectSaveOutcome.saved(app.current_project_path),
            )[1]
        )
        app._reset_to_new_project = Mock(
            side_effect=lambda: events.append("reset")
        )

        with patch("main.messagebox.askyesnocancel", return_value=True):
            app._new_project()

        self.assertEqual(events, ["save", "reset"])

        events.clear()
        app._save_current_project.return_value = ProjectSaveOutcome.cancelled()
        app._save_current_project.side_effect = lambda: (
            events.append("save"),
            ProjectSaveOutcome.cancelled(),
        )[1]
        app._reset_to_new_project.reset_mock()
        with patch("main.messagebox.askyesnocancel", return_value=True):
            app._new_project()
        self.assertEqual(events, ["save"])
        app._reset_to_new_project.assert_not_called()


class ProjectNavigationOutcomeTests(unittest.TestCase):
    def test_save_outcomes_keep_success_cancel_and_failure_distinct(self):
        path = Path("case/project.json")

        saved = ProjectSaveOutcome.saved(path)
        cancelled = ProjectSaveOutcome.cancelled()
        failed = ProjectSaveOutcome.failed(RuntimeError("disk failed"))

        self.assertEqual(saved.status, ProjectSaveStatus.SAVED)
        self.assertEqual(saved.path, path)
        self.assertEqual(cancelled.status, ProjectSaveStatus.CANCELLED)
        self.assertIsNone(cancelled.path)
        self.assertEqual(failed.status, ProjectSaveStatus.FAILED)
        self.assertEqual(failed.error, "disk failed")

    def test_navigation_outcome_is_named_instead_of_boolean(self):
        self.assertEqual(NavigationGuardOutcome.PROCEED.value, "proceed")
        self.assertEqual(NavigationGuardOutcome.CANCELLED.value, "cancelled")


if __name__ == "__main__":
    unittest.main()
