from __future__ import annotations

import inspect
import unittest
from dataclasses import replace
from types import SimpleNamespace

from dxf_import.dialog import DXFImportDialog
from dxf_import.models import (
    Beam,
    BeamCrossing,
    CandidatePoint,
    Column,
    ComponentAssociation,
    DoubleSupportCandidate,
    DXFImportResult,
    ReviewItem,
    SelectionState,
    Strut,
    Waler,
)


class _Variable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _GridFrame:
    def __init__(self):
        self.visible = None

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False


class _Button:
    def __init__(self):
        self.options = {}

    def configure(self, **options):
        self.options.update(options)


def _candidate(identifier="P1", component_id="W1"):
    return CandidatePoint(
        id=identifier,
        world_point=(110.0, 220.0),
        local_point=(10.0, 20.0),
        point_type="endpoint",
        label="端點 A",
        component_id=component_id,
    )


def _waler(*, points=()):
    return Waler(
        id="W1",
        start=(10.0, 20.0),
        end=(1010.0, 20.0),
        source_layer="圍令",
        source_handles=("A1",),
        source_entity_types=("LINE",),
        recognition_method="existing_centerline",
        centerline_computed=False,
        source_width=300.0,
        confidence=0.9,
        candidate_points=tuple(points),
        selected_start_point_id="P1",
    )


def _strut(identifier):
    return Strut(
        id=identifier,
        start=(0.0, 0.0),
        end=(1000.0, 0.0),
        source_layer="支撐",
        source_handles=(f"H{identifier}",),
        source_entity_types=("LINE",),
        recognition_method="existing_centerline",
        centerline_computed=False,
        source_width=300.0,
        from_waler="W1",
        to_waler="W2",
        confidence=1.0,
    )


def _review_item(*, severity="success", status="recognized"):
    return ReviewItem(
        key="waler:A1",
        display_id="W1",
        role="waler",
        status=status,
        member_id="W1" if status == "recognized" else None,
        source_handles=("A1",),
        source_layers=("圍令",),
        source_entity_types=("LINE",),
        selection_source="auto",
        problems=(),
        highest_severity=severity,
    )


class DxfReviewPhase3LayoutTests(unittest.TestCase):
    def test_main_review_uses_fixed_layout_and_detail_scroll(self):
        source = inspect.getsource(DXFImportDialog._build_engineering_review)

        self.assertNotIn("Panedwindow", source)
        self.assertIn("member_frame.configure(width=260)", source)
        self.assertIn("review_detail_canvas", source)

    def test_member_confirmation_is_fixed_below_scrolling_detail(self):
        source = inspect.getsource(DXFImportDialog._build_engineering_review)

        self.assertIn(
            "self.review_confirmation_frame = self.ttk.Frame(detail_host)",
            source,
        )
        confirmation_source = source.split(
            "self.review_confirmation_frame = self.ttk.Frame(detail_host)",
            1,
        )[1]
        self.assertIn("row=1", confirmation_source)
        self.assertIn("columnspan=2", confirmation_source)

    def test_import_mode_is_global_footer_setting_not_member_detail(self):
        review_source = inspect.getsource(
            DXFImportDialog._build_engineering_review
        )
        init_source = inspect.getsource(DXFImportDialog.__init__)

        self.assertNotIn("import_mode_frame", review_source)
        self.assertIn("整批匯入方式", init_source)
        self.assertIn("套用於本次所有已辨識構件", init_source)
        self.assertIn("附加到目前工程", init_source)

    def test_preview_no_longer_duplicates_endpoint_buttons(self):
        source = inspect.getsource(DXFImportDialog._open_preview_window)

        self.assertNotIn('text="選起點"', source)
        self.assertNotIn('text="選終點"', source)

    def test_preview_provides_candidate_apply_and_cancel_actions(self):
        source = inspect.getsource(DXFImportDialog._open_preview_window)

        self.assertIn('text="套用選取點"', source)
        self.assertIn('command=self._apply_candidate_changes', source)
        self.assertIn('text="取消本次選點"', source)
        self.assertIn('command=self._cancel_candidate_changes', source)

    def test_candidate_action_buttons_enable_only_for_pending_changes(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.candidate_apply_button = _Button()
        dialog.preview_apply_candidate_button = _Button()
        dialog.preview_cancel_candidate_button = _Button()
        dialog.selection_state = SelectionState(
            selected_component_id="W1",
            selected_start_point_id="P1",
            selected_end_point_id="P2",
            pending_start_point_id="P3",
            pending_end_point_id="P2",
        )
        dialog._selected_member = lambda: _waler()

        dialog._update_preview_candidate_action_state()

        self.assertEqual(dialog.candidate_apply_button.options["state"], "normal")
        self.assertEqual(
            dialog.preview_apply_candidate_button.options["state"],
            "normal",
        )
        self.assertEqual(
            dialog.preview_cancel_candidate_button.options["state"],
            "normal",
        )

        dialog.selection_state.mode = "idle"
        dialog.selection_state.pending_start_point_id = "P1"
        dialog._update_preview_candidate_action_state()

        self.assertEqual(dialog.candidate_apply_button.options["state"], "disabled")
        self.assertEqual(
            dialog.preview_apply_candidate_button.options["state"],
            "disabled",
        )
        self.assertEqual(
            dialog.preview_cancel_candidate_button.options["state"],
            "disabled",
        )

        dialog.selection_state.mode = "pick_end"
        dialog._update_preview_candidate_action_state()

        self.assertEqual(dialog.candidate_apply_button.options["state"], "disabled")
        self.assertEqual(
            dialog.preview_apply_candidate_button.options["state"],
            "disabled",
        )
        self.assertEqual(
            dialog.preview_cancel_candidate_button.options["state"],
            "normal",
        )

    def test_candidate_rows_show_local_xy_only(self):
        point = _candidate()
        member = _waler(points=(point,))
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.selection_state = SelectionState(
            selected_component_id="W1",
            selected_candidate_point_id="P1",
        )

        values = dialog._candidate_row_values(member, point)

        self.assertEqual(len(values), 4)
        self.assertEqual(values[1:3], ("10.000", "20.000"))
        self.assertNotIn("110.000", values)
        self.assertIn("目前起點", values[3])

    def test_candidate_section_only_shows_for_formal_member_with_points(self):
        point = _candidate()
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.candidate_frame = _GridFrame()

        dialog._update_candidate_section_visibility(
            _review_item(),
            _waler(points=(point,)),
        )
        self.assertTrue(dialog.candidate_frame.visible)

        dialog._update_candidate_section_visibility(_review_item(), _waler())
        self.assertFalse(dialog.candidate_frame.visible)

        dialog._update_candidate_section_visibility(
            _review_item(status="unresolved"),
            None,
        )
        self.assertFalse(dialog.candidate_frame.visible)

    def test_engineering_rows_follow_project_order_and_add_length(self):
        first = _strut("S1")
        second = _strut("S2")
        pair = DoubleSupportCandidate(
            id="PAIR1",
            first_strut_id="S1",
            second_strut_id="S2",
            centerline_spacing=500.0,
            angle_difference_deg=0.0,
            overlap_ratio=1.0,
            length_difference=0.0,
            confidence=1.0,
            accepted=True,
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = DXFImportResult(
            source_path="review.dxf",
            layer_names=("支撐",),
            selected_layers={"strut": ("支撐",)},
            layer_info=(),
            walers=(),
            struts=(first, second),
            braces=(),
            entity_debug=(),
            messages=(),
            source_entity_counts={},
            double_support_candidates=(pair,),
        )

        rows = dialog._engineering_data_rows(first)
        labels = [label for label, _value in rows]

        self.assertEqual(labels[:4], [
            "支撐編號",
            "雙路群組",
            "起點圍令",
            "終點圍令",
        ])
        self.assertEqual(dict(rows)["雙路群組"], "G1")
        self.assertEqual(labels[-1], "構件長度（mm）")

    def test_column_engineering_rows_show_primary_and_all_strut_relations(self):
        column = Column(
            id="C62",
            start=(500.0, -100.0),
            end=(500.0, 100.0),
            source_layer="s",
            source_handles=("HC62",),
            source_entity_types=("INSERT",),
            recognition_method="block_reference",
            centerline_computed=False,
            source_width=0.0,
            confidence=1.0,
            associated_strut_id="S8",
        )
        s8 = replace(_strut("S8"), associated_columns=("C62",))
        s14 = replace(_strut("S14"), associated_columns=("C62",))
        associations = tuple(
            ComponentAssociation(
                component_id="C62",
                component_role="column",
                strut_id=strut_id,
                station=500.0,
                distance=0.0,
                world_projection_point=(500.0, 0.0),
                local_projection_point=(500.0, 0.0),
            )
            for strut_id in ("S8", "S14")
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = DXFImportResult(
            source_path="Y29_test.dxf",
            layer_names=("支撐", "s"),
            selected_layers={"strut": ("支撐",), "column": ("s",)},
            layer_info=(),
            walers=(),
            struts=(s8, s14),
            braces=(),
            columns=(column,),
            entity_debug=(),
            messages=(),
            source_entity_counts={},
            component_associations=associations,
        )

        rows = dict(dialog._engineering_data_rows(column))

        self.assertEqual(rows["主要關聯支撐"], "S8")
        self.assertEqual(rows["所有關聯支撐"], "S8,S14")

    def test_column_all_strut_relations_fall_back_to_reverse_strut_fields(self):
        column = Column(
            id="C62",
            start=(500.0, -100.0),
            end=(500.0, 100.0),
            source_layer="s",
            source_handles=("HC62",),
            source_entity_types=("INSERT",),
            recognition_method="block_reference",
            centerline_computed=False,
            source_width=0.0,
            confidence=1.0,
            associated_strut_id="S8",
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = DXFImportResult(
            source_path="restored-review.dxf",
            layer_names=("支撐", "s"),
            selected_layers={"strut": ("支撐",), "column": ("s",)},
            layer_info=(),
            walers=(),
            struts=(
                replace(_strut("S8"), associated_columns=("C62",)),
                replace(_strut("S14"), associated_columns=("C62",)),
            ),
            braces=(),
            columns=(column,),
            entity_debug=(),
            messages=(),
            source_entity_counts={},
        )

        self.assertEqual(
            dialog._associated_strut_ids_for_member(column),
            ("S8", "S14"),
        )

    def test_beam_paths_and_crossings_are_presented_as_chinese_engineering_data(self):
        beam = Beam(
            id="BM1",
            start=(0.0, 0.0),
            end=(1000.0, 0.0),
            source_layer="BEAM",
            source_handles=("HB1",),
            source_entity_types=("LINE",),
            recognition_method="existing_centerline",
            centerline_computed=False,
            source_width=300.0,
            confidence=1.0,
            world_path=((0.0, 0.0), (500.0, 100.0), (1000.0, 0.0)),
            local_path=((0.0, 0.0), (500.0, 100.0), (1000.0, 0.0)),
            path=((0.0, 0.0), (500.0, 100.0), (1000.0, 0.0)),
            associated_strut_ids=("S1",),
            crossings=(
                BeamCrossing(
                    beam_id="BM1",
                    strut_id="S1",
                    world_point=(500.0, 100.0),
                    local_point=(500.0, 100.0),
                    strut_station=2500.0,
                    beam_segment_index=1,
                    distance=0.0,
                ),
            ),
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)

        rows = dict(dialog._engineering_data_rows(beam))

        self.assertEqual(rows["托梁編號"], "BM1")
        self.assertIn("(500.000, 100.000)", rows["工程路徑"])
        self.assertIn("支撐 S1", rows["支撐交會資料"])
        self.assertIn("支撐位置 2500.000 mm", rows["支撐交會資料"])
        self.assertNotIn("strut_id", rows["支撐交會資料"])

    def test_confirm_visibility_and_blocking_severity(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_confirmation_button = _Button()
        dialog.review_confirmation_frame = _GridFrame()
        dialog._is_review_item_confirmed = lambda _item: False

        dialog._update_review_confirmation_action_state(_review_item())
        self.assertTrue(dialog.review_confirmation_frame.visible)
        self.assertEqual(
            dialog.review_confirmation_button.options["state"],
            "normal",
        )

        dialog._update_review_confirmation_action_state(
            _review_item(severity="error")
        )
        self.assertEqual(
            dialog.review_confirmation_button.options["state"],
            "disabled",
        )

        dialog._update_review_confirmation_action_state(
            _review_item(status="unresolved")
        )
        self.assertFalse(dialog.review_confirmation_frame.visible)

    def test_global_problem_header_is_collapsed_by_default_format(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.all_problems_button = _Button()
        dialog.all_problems_expanded = False
        dialog.problem_records = (
            SimpleNamespace(severity="error"),
            SimpleNamespace(severity="critical"),
            SimpleNamespace(severity="warning"),
        )

        dialog._update_all_problems_header()

        self.assertEqual(
            dialog.all_problems_button.options["text"],
            "▶ 全部問題清單（錯誤 2／警告 1）",
        )


if __name__ == "__main__":
    unittest.main()
