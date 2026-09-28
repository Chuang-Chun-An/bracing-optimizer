import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import ezdxf

from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.project_service import (
    PausedReviewRelinkRequest,
    PausedReviewRelinkStatus,
)
from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfCompatibilityChecker,
    DxfWorkflowStatus,
    ProjectPersistenceError,
    ProjectSerializer,
    dxf_workflow_status_from_payload,
)
from dxf_import.dialog import (
    DXFImportDialog,
    DXFImportDialogOutcome,
)
from dxf_import.importer import DXFImporter
from dxf_import.models import (
    CoordinateSystem,
    DXFImportError,
    DXFImportResult,
    ValidationMessage,
)
from dxf_import.models import GeometryTolerances
from dxf_import.review_workflow import DXFReviewWorkflow
from dxf_import.source_exclusion import source_file_fingerprint
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

    def test_brace_axis_extension_rebuilds_across_exclusion_restore_and_resume(self):
        source = self.root / "brace-extension.dxf"
        document = ezdxf.new("R2018")
        document.layers.add("WALER")
        document.layers.add("STRUT")
        document.layers.add("BRACE")
        model = document.modelspace()
        model.add_line((0.0, -500.0), (0.0, 500.0), dxfattribs={"layer": "WALER"})
        model.add_line((2000.0, -500.0), (2000.0, 500.0), dxfattribs={"layer": "WALER"})
        model.add_line((500.0, 0.0), (1500.0, 0.0), dxfattribs={"layer": "BRACE"})
        document.saveas(source)
        roles = {"WALER": "waler", "STRUT": "strut", "BRACE": "brace"}

        importer = DXFImporter(source).read()
        workflow = DXFReviewWorkflow(importer, source)
        workflow.recognize(roles)
        self.assertIsNotNone(workflow.world_result)
        brace = workflow.world_result.braces[0]
        self.assertEqual((brace.start, brace.end), ((0.0, 0.0), (2000.0, 0.0)))
        self.assertEqual((brace.from_waler, brace.to_waler), ("W1", "W2"))
        self.assertEqual(
            sum(
                message.code == "BRACE_AXIS_EXTENDED_TO_WALER"
                for message in workflow.world_result.messages
            ),
            2,
        )

        brace_item = next(
            item
            for item in workflow.review_items
            if item.role == "brace" and item.member_id == brace.id
        )
        self.assertTrue(workflow.confirm(brace_item))
        self.assertTrue(workflow.is_review_item_confirmed(brace_item))

        first_waler_item = next(
            item
            for item in workflow.review_items
            if item.role == "waler" and item.member_id == "W1"
        )
        exclusion_plan, restoring, _identity = workflow.plan_source_exclusion_for_item(
            first_waler_item
        )
        self.assertFalse(restoring)
        workflow.commit_source_exclusion_plan(exclusion_plan)
        excluded_brace = workflow.world_result.braces[0]
        self.assertTrue(bool(excluded_brace.from_waler) ^ bool(excluded_brace.to_waler))
        active_waler_ids = {member.id for member in workflow.world_result.walers}
        self.assertTrue(
            {excluded_brace.from_waler, excluded_brace.to_waler} - {""}
            <= active_waler_ids
        )
        self.assertFalse(workflow.is_review_item_confirmed(brace_item))

        excluded_waler_item = next(
            item
            for item in workflow.review_items
            if item.role == "waler" and item.status == "excluded"
        )
        restore_plan, restoring, _identity = workflow.plan_source_exclusion_for_item(
            excluded_waler_item
        )
        self.assertTrue(restoring)
        workflow.commit_source_exclusion_plan(restore_plan)
        restored_brace = workflow.world_result.braces[0]
        self.assertEqual(
            (restored_brace.from_waler, restored_brace.to_waler),
            ("W1", "W2"),
        )

        state = workflow.serialize_review_state(layer_roles=roles)
        resumed_importer = DXFImporter(source).read()
        resumed = DXFReviewWorkflow(
            resumed_importer,
            source,
            initial_state=state,
            resume_review=True,
        )
        resumed.recognize(roles)
        resumed_brace = resumed.world_result.braces[0]
        self.assertEqual(
            (resumed_brace.start, resumed_brace.end),
            ((0.0, 0.0), (2000.0, 0.0)),
        )
        self.assertEqual(
            (resumed_brace.from_waler, resumed_brace.to_waler),
            ("W1", "W2"),
        )
        self.assertNotIn("brace_waler_connections", state)

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
        dialog.file_path = self.source
        dialog.importer = SimpleNamespace(
            source_fingerprint=result.source_fingerprint,
            layer_names=("0", "GRID"),
            tolerances=GeometryTolerances(),
        )
        dialog.review_workflow = DXFReviewWorkflow(
            dialog.importer,
            self.source,
            initial_world_result=result,
        )
        dialog.layer_use_vars = {
            "0": FakeVariable("忽略"),
            "GRID": FakeVariable("輔助線"),
        }
        dialog.coordinate_mode_var = FakeVariable("local")
        dialog.mode_var = FakeVariable("append")
        dialog.initial_state = {}
        dialog._initial_state_matches_source = False
        dialog.review_workflow.set_coordinate_origin((12.5, -8.0))
        dialog._sync_review_workflow_state()

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

    def test_compatible_recovery_save_load_keeps_schema_and_defers_managed_copy(self):
        candidate = create_dxf(self.root / "recovered-source.dxf", offset=5000)
        app = self.app()
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        original = review_state(self.source)
        recovered = review_state(
            candidate,
            review_state_version=2,
            validation_messages=[{
                "severity": "warning",
                "code": "RECOVERY_REVIEW_REQUIRED",
            }],
        )
        app.dxf_last_import_debug = original
        app.dxf_review_session = {
            "source_fingerprint": original["source_fingerprint"],
            "world_result": empty_result(self.source),
        }
        recovery_summary = object()
        result = SimpleNamespace(
            accepted=True,
            status=PausedReviewRelinkStatus.COMPATIBLE_RECOVERY_AVAILABLE,
            relinked_state=recovered,
            dxf_status_report=DxfAssetManager().accepted_relink_report(
                candidate,
                summary="recovered",
            ),
            workflow_status=DxfWorkflowStatus.REVIEW,
            dirty_reason="recovered",
            recovery_summary=recovery_summary,
            candidate_world_result=empty_result(candidate),
        )
        managed_path = (
            app.project_cases_dir / "recovered" / "source" / "source.dxf"
        )

        app._adopt_paused_review_relink(result)

        self.assertFalse(managed_path.exists())
        self.assertIs(app.last_dxf_recovery_summary, recovery_summary)

        saved_path = app.save_project_case("recovered")
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        loaded = self.app()
        loaded.load_project_case("recovered", silent=True)

        self.assertTrue(managed_path.is_file())
        self.assertEqual(
            source_file_fingerprint(managed_path),
            source_file_fingerprint(candidate),
        )
        self.assertEqual(saved["schema_version"], 3)
        self.assertEqual(
            saved["dxf_import_state"]["review_state_version"],
            2,
        )
        self.assertNotIn("recovery_summary", saved["dxf_import_state"])
        self.assertNotIn("recovery_plan", saved["dxf_import_state"])
        self.assertEqual(
            loaded._current_dxf_workflow_status(),
            DxfWorkflowStatus.REVIEW,
        )
        self.assertEqual(
            loaded.dxf_last_import_debug["source_fingerprint"],
            recovered["source_fingerprint"],
        )
        self.assertIsNone(loaded.last_dxf_recovery_summary)

    def test_same_sha_different_path_can_resume(self):
        copied = self.root / "renamed.dxf"
        shutil.copy2(self.source, copied)
        app = self.app()
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = review_state(self.source)
        app.dxf_asset_status_report = DxfAssetManager().runtime_report(copied)

        source, _fingerprint = app._review_resume_source()

        self.assertEqual(source, copied)

    def test_relink_routes_review_and_non_review_to_separate_workflows(self):
        review_app = self.app()
        review_app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        review_app._relink_paused_dxf_review = Mock(return_value="review")

        self.assertEqual(review_app._relink_dxf(), "review")
        review_app._relink_paused_dxf_review.assert_called_once_with()

        completed_app = self.app()
        completed_app.dxf_workflow_status = DxfWorkflowStatus.COMPLETED
        completed_app._relink_paused_dxf_review = Mock()
        with patch("main.filedialog.askopenfilename", return_value="") as picker:
            self.assertIsNone(completed_app._relink_dxf())

        picker.assert_called_once()
        completed_app._relink_paused_dxf_review.assert_not_called()

    def test_paused_review_exact_relink_preserves_state_and_resumes(self):
        candidate = self.root / "renamed.dxf"
        shutil.copy2(self.source, candidate)
        app = self.app()
        result = empty_result(self.source)
        state = review_state(
            self.source,
            excluded_sources=[{"role": "beam", "source_handles": ["6EF"]}],
            review_confirmations={"strut:HS": "ABC123"},
        )
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = copy.deepcopy(state)
        app.dxf_review_session = {
            "source_fingerprint": state["source_fingerprint"],
            "world_result": result,
        }
        app.dxf_asset_status_report = DxfAssetManager().runtime_report(self.source)
        app.solver_memory["kept"] = object()
        app.support_candidate_cache["kept"] = object()
        before_project = app.project_data.to_case_data()
        before_project_results = app._project_results
        before_solver = dict(app.solver_memory)
        before_support_cache = dict(app.support_candidate_cache)
        captured = {}

        class Dialog:
            def __init__(self, *_args, **kwargs):
                captured.update(kwargs)

            def show(self):
                return DXFImportDialogOutcome(
                    "pause",
                    copy.deepcopy(app.dxf_last_import_debug),
                    "replace",
                    result,
                    result,
                )

        with patch("main.filedialog.askopenfilename", return_value=str(candidate)):
            with patch("main.messagebox.askretrycancel") as retry:
                with patch("main.messagebox.askyesno") as confirmation:
                    with patch("main.DXFImportDialog", Dialog):
                        action = app._relink_dxf()

        self.assertEqual(action, "pause")
        retry.assert_not_called()
        confirmation.assert_not_called()
        self.assertEqual(
            app.dxf_last_import_debug["source_path"],
            str(candidate.resolve()),
        )
        self.assertEqual(
            app.dxf_last_import_debug["excluded_sources"],
            state["excluded_sources"],
        )
        self.assertEqual(
            app.dxf_last_import_debug["review_confirmations"],
            state["review_confirmations"],
        )
        self.assertIs(captured["initial_world_result"], result)
        self.assertTrue(captured["resume_review"])
        self.assertEqual(
            app._current_dxf_workflow_status(),
            DxfWorkflowStatus.REVIEW,
        )
        self.assertEqual(app.project_data.to_case_data(), before_project)
        self.assertIs(app._project_results, before_project_results)
        self.assertEqual(app.solver_memory, before_solver)
        self.assertEqual(app.support_candidate_cache, before_support_cache)
        self.assertTrue(app.project_dirty)

    def test_paused_review_relink_file_picker_cancel_is_no_op(self):
        app = self.app()
        state = review_state(self.source)
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.project_dirty = False
        app._ensure_project_service = Mock()

        with patch("main.filedialog.askopenfilename", return_value=""):
            result = app._relink_dxf()

        self.assertIsNone(result)
        app._ensure_project_service.assert_not_called()
        self.assertIs(app.dxf_last_import_debug, state)
        self.assertFalse(app.project_dirty)

    def test_paused_review_compatible_recovery_reject_is_no_op(self):
        candidate = create_dxf(self.root / "changed.dxf", offset=5000)
        app = self.app()
        state = review_state(self.source)
        session = {
            "source_fingerprint": state["source_fingerprint"],
            "world_result": empty_result(self.source),
        }
        report = DxfAssetManager().runtime_report(self.source)
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.dxf_review_session = session
        app.dxf_asset_status_report = report
        app.last_dxf_recovery_summary = None
        app.project_dirty = False
        summary = object()
        service = Mock()
        service.evaluate_paused_review_relink.return_value = SimpleNamespace(
            status=PausedReviewRelinkStatus.COMPATIBLE_RECOVERY_AVAILABLE,
            plan=object(),
            summary="compatible",
            detail_lines=(),
            recovery_summary=summary,
        )
        app._ensure_project_service = Mock(return_value=service)

        with patch("main.filedialog.askopenfilename", return_value=str(candidate)):
            with patch("main.confirm_review_recovery", return_value=False) as confirm:
                result = app._relink_paused_dxf_review()

        self.assertIsNone(result)
        confirm.assert_called_once_with(None, summary)
        service.commit_paused_review_relink.assert_not_called()
        self.assertIs(app.dxf_last_import_debug, state)
        self.assertIs(app.dxf_review_session, session)
        self.assertIs(app.dxf_asset_status_report, report)
        self.assertFalse(app.project_dirty)

    def test_paused_review_compatible_recovery_accepts_and_resumes(self):
        candidate = create_dxf(self.root / "changed.dxf", offset=5000)
        app = self.app()
        state = review_state(self.source)
        recovered = copy.deepcopy(state)
        recovered["source_path"] = str(candidate.resolve())
        recovered["source_fingerprint"] = source_file_fingerprint(candidate)
        candidate_world = empty_result(candidate)
        report = DxfAssetManager().runtime_report(candidate)
        recovery_summary = object()
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.dxf_review_session = {
            "source_fingerprint": state["source_fingerprint"],
            "world_result": empty_result(self.source),
        }
        app.last_dxf_recovery_summary = None
        app.project_dirty = False
        before_project = app.project_data.to_case_data()
        service = Mock()
        plan = object()
        service.evaluate_paused_review_relink.return_value = SimpleNamespace(
            status=PausedReviewRelinkStatus.COMPATIBLE_RECOVERY_AVAILABLE,
            plan=plan,
            summary="compatible",
            detail_lines=(),
            recovery_summary=recovery_summary,
        )
        service.commit_paused_review_relink.return_value = SimpleNamespace(
            accepted=True,
            status=PausedReviewRelinkStatus.COMPATIBLE_RECOVERY_AVAILABLE,
            relinked_state=recovered,
            dxf_status_report=report,
            workflow_status=DxfWorkflowStatus.REVIEW,
            dirty_reason="recovered",
            recovery_summary=recovery_summary,
            candidate_world_result=candidate_world,
        )
        app._ensure_project_service = Mock(return_value=service)
        captured = {}

        class Dialog:
            def __init__(self, *_args, **kwargs):
                captured.update(kwargs)

            def show(self):
                return DXFImportDialogOutcome(
                    "pause",
                    copy.deepcopy(recovered),
                    "replace",
                    candidate_world,
                    candidate_world,
                )

        with patch("main.filedialog.askopenfilename", return_value=str(candidate)):
            with patch("main.confirm_review_recovery", return_value=True):
                with patch("main.DXFImportDialog", Dialog):
                    result = app._relink_paused_dxf_review()

        self.assertEqual(result, "pause")
        service.commit_paused_review_relink.assert_called_once_with(
            plan,
            current_saved_state=state,
            current_workflow_status=DxfWorkflowStatus.REVIEW,
        )
        self.assertEqual(app.dxf_last_import_debug, recovered)
        self.assertIs(
            app.dxf_review_session["world_result"],
            candidate_world,
        )
        self.assertEqual(
            app.dxf_review_session["source_fingerprint"],
            recovered["source_fingerprint"],
        )
        self.assertIs(app.last_dxf_recovery_summary, recovery_summary)
        self.assertTrue(app.project_dirty)
        self.assertEqual(app.project_data.to_case_data(), before_project)
        self.assertIs(captured["initial_world_result"], candidate_world)
        self.assertTrue(captured["resume_review"])

    def test_paused_review_content_mismatch_retries_from_original_state(self):
        first = create_dxf(self.root / "changed-1.dxf", offset=5000)
        second = create_dxf(self.root / "changed-2.dxf", offset=9000)
        app = self.app()
        state = review_state(self.source)
        session = {"source_fingerprint": state["source_fingerprint"], "world_result": None}
        report = DxfAssetManager().runtime_report(self.source)
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.dxf_review_session = session
        app.dxf_asset_status_report = report
        app.project_dirty = False
        before_project = app.project_data.to_case_data()

        with patch(
            "main.filedialog.askopenfilename",
            side_effect=(str(first), str(second), ""),
        ):
            with patch(
                "main.messagebox.askretrycancel",
                side_effect=(True, True),
            ) as retry:
                result = app._relink_dxf()

        self.assertIsNone(result)
        self.assertEqual(retry.call_count, 2)
        self.assertIs(app.dxf_last_import_debug, state)
        self.assertIs(app.dxf_review_session, session)
        self.assertIs(app.dxf_asset_status_report, report)
        self.assertFalse(app.project_dirty)
        self.assertEqual(app.project_data.to_case_data(), before_project)

    def test_paused_review_validation_failure_preserves_original_state(self):
        invalid = self.root / "invalid.dxf"
        invalid.write_text("not a dxf", encoding="utf-8")
        app = self.app()
        state = review_state(self.source)
        session = {
            "source_fingerprint": state["source_fingerprint"],
            "world_result": empty_result(self.source),
        }
        report = DxfAssetManager().runtime_report(self.source)
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.dxf_review_session = session
        app.dxf_asset_status_report = report
        app.project_dirty = False

        with patch("main.filedialog.askopenfilename", return_value=str(invalid)):
            with patch("main.messagebox.askretrycancel", return_value=False):
                result = app._relink_dxf()

        self.assertIsNone(result)
        self.assertIs(app.dxf_last_import_debug, state)
        self.assertIs(app.dxf_review_session, session)
        self.assertIs(app.dxf_asset_status_report, report)
        self.assertFalse(app.project_dirty)
        self.assertEqual(
            app._current_dxf_workflow_status(),
            DxfWorkflowStatus.REVIEW,
        )

    def test_missing_resume_source_offers_paused_review_relink(self):
        app = self.app()
        state = review_state(
            self.source,
            source_path=str(self.root / "missing.dxf"),
        )
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.dxf_asset_status_report = None
        app._relink_paused_dxf_review = Mock(return_value="pause")

        with patch("main.messagebox.askretrycancel", return_value=True) as retry:
            result = app._continue_dxf_import()

        self.assertEqual(result, "pause")
        retry.assert_called_once()
        app._relink_paused_dxf_review.assert_called_once_with()

    def test_paused_review_relink_adoption_failure_rolls_back(self):
        candidate = self.root / "candidate.dxf"
        shutil.copy2(self.source, candidate)
        app = self.app()
        state = review_state(self.source)
        report = DxfAssetManager().runtime_report(self.source)
        compatibility = object()
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.dxf_asset_status_report = report
        app.last_dxf_compatibility_report = compatibility
        app.project_dirty = False
        app.project_dirty_reason = ""
        service = app._ensure_project_service()
        evaluation = service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=state,
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )
        committed = service.commit_paused_review_relink(
            evaluation.plan,
            current_saved_state=state,
            current_workflow_status=DxfWorkflowStatus.REVIEW,
        )
        refresh_calls = 0

        def fail_once():
            nonlocal refresh_calls
            refresh_calls += 1
            if refresh_calls == 1:
                raise RuntimeError("refresh failed")

        app._refresh_project_status_display = fail_once

        with self.assertRaises(RuntimeError):
            app._adopt_paused_review_relink(committed)

        self.assertIs(app.dxf_last_import_debug, state)
        self.assertIs(app.dxf_asset_status_report, report)
        self.assertIs(app.last_dxf_compatibility_report, compatibility)
        self.assertFalse(app.project_dirty)
        self.assertEqual(app.project_dirty_reason, "")

    def test_compatible_recovery_adoption_failure_rolls_back_entire_truth_set(self):
        candidate = create_dxf(self.root / "candidate-changed.dxf", offset=5000)
        app = self.app()
        state = review_state(self.source)
        old_world = empty_result(self.source)
        old_session = {
            "source_fingerprint": state["source_fingerprint"],
            "world_result": old_world,
        }
        old_report = DxfAssetManager().runtime_report(self.source)
        old_compatibility = object()
        old_recovery = object()
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.dxf_review_session = old_session
        app.dxf_asset_status_report = old_report
        app.last_dxf_compatibility_report = old_compatibility
        app.last_dxf_recovery_summary = old_recovery
        app.project_dirty = False
        app.project_dirty_reason = ""
        recovered = copy.deepcopy(state)
        recovered["source_path"] = str(candidate.resolve())
        recovered["source_fingerprint"] = source_file_fingerprint(candidate)
        result = SimpleNamespace(
            accepted=True,
            status=PausedReviewRelinkStatus.COMPATIBLE_RECOVERY_AVAILABLE,
            relinked_state=recovered,
            dxf_status_report=DxfAssetManager().runtime_report(candidate),
            workflow_status=DxfWorkflowStatus.REVIEW,
            dirty_reason="recovered",
            recovery_summary=object(),
            candidate_world_result=empty_result(candidate),
        )
        refresh_calls = 0

        def fail_once():
            nonlocal refresh_calls
            refresh_calls += 1
            if refresh_calls == 1:
                raise RuntimeError("refresh failed")

        app._refresh_project_status_display = fail_once

        with self.assertRaises(RuntimeError):
            app._adopt_paused_review_relink(result)

        self.assertIs(app.dxf_last_import_debug, state)
        self.assertIs(app.dxf_review_session, old_session)
        self.assertIs(app.dxf_asset_status_report, old_report)
        self.assertIs(app.last_dxf_compatibility_report, old_compatibility)
        self.assertIs(app.last_dxf_recovery_summary, old_recovery)
        self.assertFalse(app.project_dirty)
        self.assertEqual(app.project_dirty_reason, "")

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
        app._refresh_results_tree = lambda **_kwargs: (_ for _ in ()).throw(
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
