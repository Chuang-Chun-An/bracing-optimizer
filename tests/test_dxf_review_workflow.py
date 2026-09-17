import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import ezdxf

from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfCompatibilityChecker,
    DxfWorkflowStatus,
    ProjectPersistenceError,
    ProjectSerializer,
    dxf_workflow_status_from_payload,
)
from dxf_import import (
    CoordinateSystem,
    DXFImportDialog,
    DXFImportDialogOutcome,
    DXFImportError,
    DXFImportResult,
    ValidationMessage,
    source_file_fingerprint,
)
from main import SupportInputApp


def create_dxf(path: Path, *, offset: float = 0.0) -> Path:
    document = ezdxf.new("R2018")
    document.modelspace().add_line((offset, 0), (offset + 1000, 0))
    document.saveas(path)
    return path


def empty_result(
    source: Path,
    *,
    messages=(),
) -> DXFImportResult:
    return DXFImportResult(
        source_path=str(source),
        source_fingerprint=source_file_fingerprint(source),
        layer_names=("0",),
        selected_layers={},
        layer_info=(),
        walers=(),
        struts=(),
        braces=(),
        entity_debug=(),
        messages=tuple(messages),
        source_entity_counts={},
        layer_classification={"0": "ignore"},
    )


def review_state(source: Path, **updates):
    state = {
        "review_state_version": 1,
        "source_path": str(source),
        "source_fingerprint": source_file_fingerprint(source),
        "layer_classification": {"0": "ignore"},
        "coordinate_system": {
            "mode": "local",
            "origin_x": 125.0,
            "origin_y": -75.0,
            "source": "selected_candidate_point",
        },
        "import_mode": "replace",
        "excluded_sources": [],
        "manual_overrides": [],
        "double_support_decisions": [],
    }
    state.update(updates)
    return state


class FakeButton:
    def __init__(self, managed=False):
        self.managed = managed

    def pack(self, **_kwargs):
        self.managed = True

    def pack_forget(self):
        self.managed = False

    def winfo_manager(self):
        return "pack" if self.managed else ""


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DxfReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.source = create_dxf(self.root / "review.dxf")

    def tearDown(self):
        self.temp_dir.cleanup()

    def app(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = None
        app.project_cases_dir = self.root / "projects"
        app.project_cases_dir.mkdir(exist_ok=True)
        app.project_data = ProjectDataModel(
            walers=[{
                "WalerID": "W-OLD",
                "StartX": 0,
                "StartY": 0,
                "EndX": 1000,
                "EndY": 0,
            }]
        )
        app._project_results = ProjectResultModel()
        app.current_project_path = None
        app.project_dirty = False
        app.project_dirty_reason = ""
        app.dxf_last_import_debug = None
        app.dxf_workflow_status = DxfWorkflowStatus.NONE
        app.dxf_review_session = None
        app.dxf_asset = None
        app.dxf_asset_status_report = None
        app.last_dxf_compatibility_report = None
        app.dxf_asset_manager = DxfAssetManager()
        app.dxf_compatibility_checker = DxfCompatibilityChecker()
        app.solver_memory = {}
        app.support_candidate_cache = {}
        app.dxf_dialog_active = False
        app.dxf_import_status = ""
        app.dxf_import_error = ""
        app.cad_event_watcher = None
        app._refresh_tree = lambda _name: None
        app._refresh_results_tree = lambda **_kwargs: None
        app._refresh_project_case_list = lambda **_kwargs: None
        app.update_preview = lambda **_kwargs: None
        app.show_result = lambda _text: None
        return app

    def outcome(self, *, action="pause", result=None, state=None):
        result = result or empty_result(self.source)
        return DXFImportDialogOutcome(
            action=action,
            review_state=state or review_state(self.source),
            import_mode="replace",
            result=result,
            world_result=result,
        )

    def test_explicit_workflow_is_one_way(self):
        app = self.app()

        app._transition_dxf_workflow(DxfWorkflowStatus.REVIEW)
        app._transition_dxf_workflow(DxfWorkflowStatus.COMPLETED)

        with self.assertRaises(RuntimeError):
            app._transition_dxf_workflow(DxfWorkflowStatus.REVIEW)

    def test_pause_with_blocking_error_keeps_project_data_unchanged(self):
        app = self.app()
        before = app.project_data.to_case_data()
        blocked = empty_result(
            self.source,
            messages=(ValidationMessage("error", "UNRESOLVED", "待修"),),
        )

        action = app._handle_dxf_review_outcome(
            self.outcome(result=blocked),
            self.source,
        )

        self.assertEqual(action, "pause")
        self.assertEqual(app._current_dxf_workflow_status(), DxfWorkflowStatus.REVIEW)
        self.assertEqual(app.project_data.to_case_data(), before)
        self.assertTrue(app.project_dirty)

    def test_dialog_x_uses_pause_not_cancel(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        calls = []
        dialog.allow_pause = True
        dialog._pause = lambda: calls.append("pause")
        dialog._cancel = lambda: calls.append("cancel")

        dialog._close_dialog()

        self.assertEqual(calls, ["pause"])

    def test_pause_captures_layer_coordinate_and_mode(self):
        result = empty_result(self.source)
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = result
        dialog.world_result = result
        dialog.file_path = self.source
        dialog.importer = SimpleNamespace(
            source_fingerprint=result.source_fingerprint,
            layer_names=("0", "GRID"),
        )
        dialog.layer_use_vars = {
            "0": FakeVariable("忽略"),
            "GRID": FakeVariable("輔助線"),
        }
        dialog.coordinate_mode_var = FakeVariable("local")
        dialog.selected_origin_world = (12.5, -8.0)
        dialog.mode_var = FakeVariable("append")
        dialog.excluded_sources = ()
        dialog.double_support_decisions = {}
        dialog.initial_state = {}
        dialog._initial_state_matches_source = False

        state = dialog._build_review_state()

        self.assertEqual(
            state["layer_classification"],
            {"0": "ignore", "GRID": "auxiliary"},
        )
        self.assertEqual(state["coordinate_system"]["mode"], "local")
        self.assertEqual(state["coordinate_system"]["origin_x"], 12.5)
        self.assertEqual(state["coordinate_system"]["origin_y"], -8.0)
        self.assertEqual(state["import_mode"], "append")
        self.assertEqual(state["review_state_version"], 2)
        self.assertEqual(state["review_confirmations"], {})

    def test_continue_button_depends_only_on_workflow(self):
        app = self.app()
        app.dxf_start_import_button = FakeButton(True)
        app.dxf_continue_import_button = FakeButton(False)

        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app._refresh_dxf_workflow_ui()
        self.assertFalse(app.dxf_start_import_button.managed)
        self.assertTrue(app.dxf_continue_import_button.managed)

        app.dxf_workflow_status = DxfWorkflowStatus.COMPLETED
        app._refresh_dxf_workflow_ui()
        self.assertFalse(app.dxf_start_import_button.managed)
        self.assertFalse(app.dxf_continue_import_button.managed)

    def test_same_session_resume_passes_current_world_result(self):
        app = self.app()
        result = empty_result(self.source)
        state = review_state(self.source)
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.dxf_review_session = {
            "source_fingerprint": state["source_fingerprint"],
            "world_result": result,
        }
        app.dxf_asset_status_report = DxfAssetManager().runtime_report(self.source)
        captured = {}

        class Dialog:
            def __init__(self, *_args, **kwargs):
                captured.update(kwargs)

            def show(self):
                return DXFImportDialogOutcome(
                    "pause",
                    state,
                    "replace",
                    result,
                    result,
                )

        with patch("main.DXFImportDialog", Dialog):
            action = app._continue_dxf_import()

        self.assertEqual(action, "pause")
        self.assertIs(captured["initial_world_result"], result)
        self.assertTrue(captured["resume_review"])

    def test_disk_resume_rebuild_path_does_not_pass_derived_result(self):
        app = self.app()
        state = review_state(self.source)
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.dxf_review_session = None
        app.dxf_asset_status_report = DxfAssetManager().runtime_report(self.source)
        captured = {}

        class Dialog:
            def __init__(self, *_args, **kwargs):
                captured.update(kwargs)

            def show(self):
                return DXFImportDialogOutcome(
                    "pause",
                    state,
                    "replace",
                    None,
                    None,
                )

        with patch("main.DXFImportDialog", Dialog):
            app._continue_dxf_import()

        self.assertIsNone(captured["initial_world_result"])
        self.assertTrue(captured["resume_review"])

    def test_changed_layer_roles_force_rerecognition_in_same_session(self):
        app = self.app()
        result = empty_result(self.source)
        state = review_state(
            self.source,
            layer_classification={"0": "auxiliary"},
        )
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.dxf_review_session = {
            "source_fingerprint": state["source_fingerprint"],
            "world_result": result,
        }
        app.dxf_asset_status_report = DxfAssetManager().runtime_report(self.source)
        captured = {}

        class Dialog:
            def __init__(self, *_args, **kwargs):
                captured.update(kwargs)

            def show(self):
                return DXFImportDialogOutcome(
                    "pause",
                    state,
                    "replace",
                    None,
                    None,
                )

        with patch("main.DXFImportDialog", Dialog):
            app._continue_dxf_import()

        self.assertIsNone(captured["initial_world_result"])

    def test_saved_coordinate_system_is_restored_as_project_local(self):
        coordinate = DXFImportDialog._coordinate_system_from_review_state(
            review_state(self.source)
        )

        self.assertEqual(coordinate, CoordinateSystem(
            "local",
            125.0,
            -75.0,
            "selected_candidate_point",
        ))

    def test_review_save_load_uses_managed_copy_and_restores_workflow(self):
        app = self.app()
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = review_state(
            self.source,
            excluded_sources=[{
                "role": "beam",
                "source_handles": ["6EF"],
                "source_layers": ["BEAM"],
                "source_entity_types": ["LWPOLYLINE"],
                "reason": "user_excluded",
            }],
            review_confirmations={"strut:HS": "ABC123"},
        )
        app.dxf_asset_status_report = DxfAssetManager().runtime_report(self.source)

        saved_path = app.save_project_case("paused")
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        loaded = self.app()
        loaded.load_project_case("paused", silent=True)
        resume_source, _fingerprint = loaded._review_resume_source()

        self.assertEqual(saved["dxf_workflow_status"], "REVIEW")
        self.assertEqual(
            saved["dxf_import_state"]["excluded_sources"][0]["source_handles"],
            ["6EF"],
        )
        self.assertEqual(
            saved["dxf_import_state"]["review_confirmations"],
            {"strut:HS": "ABC123"},
        )
        self.assertEqual(
            loaded._current_dxf_workflow_status(),
            DxfWorkflowStatus.REVIEW,
        )
        self.assertEqual(
            loaded.dxf_last_import_debug["review_confirmations"],
            {"strut:HS": "ABC123"},
        )
        self.assertEqual(resume_source, saved_path.parent / "source" / "source.dxf")

    def test_same_sha_different_path_can_resume(self):
        copied = self.root / "renamed.dxf"
        shutil.copy2(self.source, copied)
        app = self.app()
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = review_state(self.source)
        app.dxf_asset_status_report = DxfAssetManager().runtime_report(copied)

        source, _fingerprint = app._review_resume_source()

        self.assertEqual(source, copied)

    def test_same_name_different_bytes_rejects_resume(self):
        state = review_state(self.source)
        create_dxf(self.source, offset=5000)
        app = self.app()
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.dxf_asset_status_report = DxfAssetManager().runtime_report(self.source)

        with self.assertRaises(DXFImportError):
            app._review_resume_source()

    def test_successful_complete_commits_then_transitions(self):
        app = self.app()

        action = app._handle_dxf_review_outcome(
            self.outcome(action="complete"),
            self.source,
        )

        self.assertEqual(action, "complete")
        self.assertEqual(app.walers, [])
        self.assertEqual(
            app._current_dxf_workflow_status(),
            DxfWorkflowStatus.COMPLETED,
        )
        self.assertIsNone(app.dxf_review_session)

    def test_completed_workflow_round_trips_without_resume_capability(self):
        app = self.app()
        app._handle_dxf_review_outcome(
            self.outcome(action="complete"),
            self.source,
        )

        saved_path = app.save_project_case("completed")
        loaded = self.app()
        loaded.load_project_case("completed", silent=True)

        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["dxf_workflow_status"], "COMPLETED")
        self.assertEqual(
            loaded._current_dxf_workflow_status(),
            DxfWorkflowStatus.COMPLETED,
        )
        with self.assertRaises(RuntimeError):
            loaded._run_dxf_review_dialog(
                self.source,
                initial_state=loaded.dxf_last_import_debug,
                resume_review=True,
            )

    def test_validation_failure_stays_review_and_preserves_project(self):
        app = self.app()
        before = app.project_data.to_case_data()
        blocked = empty_result(
            self.source,
            messages=(ValidationMessage("error", "BLOCKED", "尚未完成"),),
        )

        with self.assertRaises(DXFImportError):
            app._handle_dxf_review_outcome(
                self.outcome(action="complete", result=blocked),
                self.source,
            )

        self.assertEqual(app.project_data.to_case_data(), before)
        self.assertEqual(app._current_dxf_workflow_status(), DxfWorkflowStatus.REVIEW)

    def test_project_commit_failure_rolls_back_and_stays_review(self):
        app = self.app()
        before = app.project_data
        app._handle_input_data_changed = lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("commit failed")
        )

        with self.assertRaises(ValueError):
            app._handle_dxf_review_outcome(
                self.outcome(action="complete"),
                self.source,
            )

        self.assertIs(app.project_data, before)
        self.assertEqual(app._current_dxf_workflow_status(), DxfWorkflowStatus.REVIEW)

    def test_completed_internal_resume_guard(self):
        app = self.app()
        app.dxf_workflow_status = DxfWorkflowStatus.COMPLETED

        with self.assertRaises(RuntimeError):
            app._run_dxf_review_dialog(
                self.source,
                initial_state=review_state(self.source),
                resume_review=True,
            )

    def test_main_updates_do_not_reverse_completed_workflow(self):
        app = self.app()
        app.dxf_workflow_status = DxfWorkflowStatus.COMPLETED

        app._handle_input_data_changed(table_name="material_specs")

        self.assertEqual(
            app._current_dxf_workflow_status(),
            DxfWorkflowStatus.COMPLETED,
        )


class DxfWorkflowPersistenceTests(unittest.TestCase):
    def payload(self, state=None, workflow=None):
        payload = {
            "schema_version": 3,
            "project_information": {"project_name": "workflow"},
            "input_data": {"walers": [], "struts": [], "braces": []},
            "dxf_import_state": copy.deepcopy(state),
            "dxf_asset": None,
            "result": None,
        }
        if workflow is not None:
            payload["dxf_workflow_status"] = workflow
        return payload

    def test_review_requires_review_state(self):
        with self.assertRaises(ProjectPersistenceError):
            ProjectSerializer.validate(self.payload(workflow="REVIEW"))

    def test_legacy_state_defaults_to_completed(self):
        self.assertEqual(
            dxf_workflow_status_from_payload(self.payload(state={})),
            DxfWorkflowStatus.COMPLETED,
        )

    def test_legacy_project_without_dxf_context_defaults_to_none(self):
        self.assertEqual(
            dxf_workflow_status_from_payload(self.payload()),
            DxfWorkflowStatus.NONE,
        )


if __name__ == "__main__":
    unittest.main()
