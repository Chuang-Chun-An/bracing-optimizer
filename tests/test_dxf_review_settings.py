from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from dxf_import.controllers import SelectionController
from dxf_import.dialog import DXFImportDialog
from dxf_import.models import (
    CandidatePoint,
    CoordinateSystem,
    DoubleSupportCandidate,
    DXFImportResult,
    GeometryTolerances,
    SelectionState,
    Strut,
    Waler,
)
from dxf_import.review_workflow import DXFReviewWorkflow, ReviewMutation


class _Variable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Window:
    def __init__(self):
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


class _CandidateStore:
    def __init__(self, values):
        self.values = values

    def component_points(self, component_id):
        return self.values.get(component_id, ())

    def get(self, component_id, point_id):
        return next(
            (
                point
                for point in self.component_points(component_id)
                if point.id == point_id
            ),
            None,
        )


def _waler(identifier="W1", handle="HW1"):
    return Waler(
        id=identifier,
        start=(0.0, 0.0),
        end=(1000.0, 0.0),
        source_layer="WALER",
        source_handles=(handle,),
        source_entity_types=("LINE",),
        recognition_method="existing_centerline",
        centerline_computed=False,
        source_width=300.0,
        confidence=1.0,
    )


def _strut(identifier, handle, y=0.0):
    return Strut(
        id=identifier,
        start=(0.0, y),
        end=(10000.0, y),
        source_layer="STRUT",
        source_handles=(handle,),
        source_entity_types=("LINE",),
        recognition_method="existing_centerline",
        centerline_computed=False,
        source_width=300.0,
        from_waler="W1",
        to_waler="W2",
        confidence=1.0,
    )


def _candidate(identifier, component_id, point):
    return CandidatePoint(
        id=identifier,
        world_point=point,
        local_point=point,
        point_type="endpoint",
        label=identifier,
        component_id=component_id,
    )


def _result(*, walers=(), struts=(), double_support_candidates=()):
    return DXFImportResult(
        source_path="settings.dxf",
        layer_names=("WALER", "STRUT"),
        selected_layers={"waler": ("WALER",), "strut": ("STRUT",)},
        layer_info=(),
        walers=tuple(walers),
        struts=tuple(struts),
        braces=(),
        entity_debug=(),
        messages=(),
        source_entity_counts={"waler": len(walers), "strut": len(struts)},
        double_support_candidates=tuple(double_support_candidates),
    )


class DxfReviewSettingsTests(unittest.TestCase):
    def test_coordinate_picker_lists_only_formal_walers(self):
        result = _result(
            walers=(_waler("W1", "HW1"), _waler("W2", "HW2")),
            struts=(_strut("S1", "HS1"),),
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = result

        self.assertEqual(
            [member.id for member in dialog._formal_walers_for_coordinate_picker()],
            ["W1", "W2"],
        )

    def test_waler_selection_lists_only_that_walers_candidates(self):
        first = _candidate("W1-P1", "W1", (10.0, 20.0))
        second = _candidate("W2-P1", "W2", (30.0, 40.0))
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = _result(walers=(_waler("W1"), _waler("W2", "HW2")))
        dialog.candidate_point_store = _CandidateStore(
            {"W1": (first,), "W2": (second,)}
        )

        self.assertEqual(
            dialog._coordinate_candidates_for_waler("W1"),
            (first,),
        )
        self.assertEqual(dialog._coordinate_candidates_for_waler("S1"), ())

    def test_coordinate_candidate_preview_stays_in_settings_window(self):
        candidate = _candidate("W1-P1", "W1", (10.0, 20.0))
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = _result(walers=(_waler(),))
        dialog.selection_state = SimpleNamespace(selected_component_id="W1")
        dialog.selected_origin_world = None
        calls = []
        dialog.preview_view_bounds = None
        dialog._center_candidate_if_hidden = lambda value: calls.append(value)
        dialog.render_scheduler = SimpleNamespace(request=calls.append)
        dialog.selection_controller = SimpleNamespace(
            preview_candidate_point=lambda *args: calls.append(args)
        )
        dialog._open_preview_window = lambda: calls.append("preview")

        dialog._preview_coordinate_candidate(candidate)

        self.assertEqual(dialog.result.coordinate_system, CoordinateSystem())
        self.assertIsNone(dialog.selected_origin_world)
        self.assertNotIn("preview", calls)
        self.assertIn((candidate.id, "coordinate_dialog"), calls)

    def test_coordinate_preview_does_not_change_pending_endpoint_pick(self):
        candidate = _candidate("W1-P1", "W1", (10.0, 20.0))
        state = SelectionState(
            selected_component_id="W1",
            mode="pick_start",
            pending_start_point_id="ORIGINAL",
            pending_end_point_id="END",
        )
        controller = SelectionController(
            state,
            _CandidateStore({"W1": (candidate,)}),
            lambda _member_id: _waler(),
            lambda _dirty: None,
        )

        controller.preview_candidate_point(candidate.id, "coordinate_dialog")

        self.assertEqual(state.mode, "pick_start")
        self.assertEqual(state.pending_start_point_id, "ORIGINAL")
        self.assertEqual(state.pending_end_point_id, "END")
        self.assertEqual(state.selected_candidate_point_id, candidate.id)

    def test_coordinate_apply_is_the_boundary_that_changes_origin(self):
        candidate = _candidate("W1-P1", "W1", (10.0, 20.0))
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.coordinate_settings_mode_var = _Variable("local")
        dialog.coordinate_mode_var = _Variable("world")
        dialog.coordinate_settings_candidate = candidate
        dialog.selected_origin_world = None
        dialog.coordinate_settings_window = _Window()
        applied = []
        dialog._set_origin_from_candidate = lambda value: (
            applied.append(value),
            setattr(dialog, "selected_origin_world", value.world_point),
        )
        dialog._close_settings_window = lambda name: applied.append(name)

        dialog._apply_coordinate_settings_dialog()

        self.assertEqual(dialog.selected_origin_world, (10.0, 20.0))
        self.assertIs(applied[0], candidate)
        self.assertEqual(applied[1], "coordinate_settings_window")

    def test_layer_cancel_does_not_change_committed_roles_or_recognize(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.tk = SimpleNamespace(TclError=Exception)
        dialog.layer_use_vars = {"A": _Variable("支撐")}
        dialog.layer_settings_vars = {"A": _Variable("圍令")}
        dialog.layer_settings_window = _Window()
        recognitions = []
        dialog._convert_preview = lambda: recognitions.append(True)

        dialog._close_settings_window("layer_settings_window")

        self.assertEqual(dialog.layer_use_vars["A"].get(), "支撐")
        self.assertEqual(recognitions, [])

    def test_layer_apply_commits_all_rows_then_recognizes_once(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.layer_use_vars = {
            "A": _Variable("支撐"),
            "B": _Variable("忽略"),
        }
        dialog.result = object()
        recognitions = []
        dialog._convert_preview = lambda: recognitions.append(
            {key: value.get() for key, value in dialog.layer_use_vars.items()}
        )

        started = dialog._commit_layer_settings({"A": "圍令", "B": "斜撐"})

        self.assertTrue(started)
        self.assertEqual(recognitions, [{"A": "圍令", "B": "斜撐"}])

    def test_double_support_cancel_does_not_change_result_or_decisions(self):
        candidate = DoubleSupportCandidate(
            "DS1", "S1", "S2", 1000.0, 0.0, 1.0, 0.0, 1.0, True
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.tk = SimpleNamespace(TclError=Exception)
        dialog.result = _result(double_support_candidates=(candidate,))
        dialog.double_support_decisions = {("A", "B"): True}
        dialog.double_support_settings_candidates = (
            replace(candidate, accepted=False),
        )
        dialog.double_support_settings_window = _Window()

        dialog._close_settings_window("double_support_settings_window")

        self.assertTrue(dialog.result.double_support_candidates[0].accepted)
        self.assertEqual(dialog.double_support_decisions, {("A", "B"): True})

    def test_double_support_apply_rebuilds_associations_once(self):
        struts = (_strut("S1", "HA"), _strut("S2", "HB", 1000.0))
        candidate = DoubleSupportCandidate(
            "DS1", "S1", "S2", 1000.0, 0.0, 1.0, 0.0, 1.0, True
        )
        result = _result(struts=struts, double_support_candidates=(candidate,))
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.importer = SimpleNamespace(tolerances=GeometryTolerances())
        dialog.review_workflow = DXFReviewWorkflow(
            SimpleNamespace(
                tolerances=GeometryTolerances(),
                source_fingerprint=result.source_fingerprint,
                layer_names=result.layer_names,
            ),
            "settings.dxf",
            initial_world_result=result,
        )
        dialog._sync_review_workflow_state()
        refreshes = []
        dialog._refresh_result_views = lambda **kwargs: refreshes.append(kwargs)
        dialog._show_workflow_confirmation_invalidations = lambda *_args: None

        with patch(
            "dxf_import.review_workflow.rebuild_component_associations",
            side_effect=lambda staged, _tolerances: staged,
        ) as rebuild:
            changed = dialog._commit_double_support_candidates(
                (replace(candidate, accepted=False),)
            )

        self.assertTrue(changed)
        self.assertEqual(rebuild.call_count, 1)
        self.assertEqual(len(refreshes), 1)
        self.assertFalse(dialog.result.double_support_candidates[0].accepted)
        self.assertEqual(len(dialog.double_support_decisions), 1)

    def test_persisted_double_support_decision_is_the_initial_staged_value(self):
        candidate = DoubleSupportCandidate(
            "DS1", "S1", "S2", 1000.0, 0.0, 1.0, 0.0, 1.0, False
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = _result(double_support_candidates=(candidate,))

        staged = dialog._double_support_candidates_for_settings()

        self.assertFalse(staged[0].accepted)

    def test_high_impact_coordinate_apply_uses_confirmation_boundary(self):
        candidate = _candidate("W1-P1", "W1", (10.0, 20.0))
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.coordinate_mode_var = _Variable("world")
        dialog.selected_origin_world = None
        finished = []
        mutation = ReviewMutation(True, ("W2",))
        dialog.review_workflow = SimpleNamespace(
            set_coordinate_origin=lambda point: (
                finished.append(("command", point)) or mutation
            )
        )
        dialog.coordinate_error_var = _Variable()
        dialog._sync_review_workflow_state = lambda: setattr(
            dialog, "selected_origin_world", candidate.world_point
        )
        dialog._refresh_result_views = lambda **_kwargs: None
        dialog._show_workflow_confirmation_invalidations = (
            lambda value: finished.append(("invalidations", value))
        )

        dialog._set_origin_from_candidate(candidate)

        self.assertEqual(dialog.selected_origin_world, (10.0, 20.0))
        self.assertEqual(dialog.coordinate_mode_var.get(), "local")
        self.assertEqual(
            finished,
            [
                ("command", (10.0, 20.0)),
                ("invalidations", mutation),
            ],
        )


if __name__ == "__main__":
    unittest.main()
