from __future__ import annotations

import copy
import inspect
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dxf_import.dialog import (
    DXFImportDialog,
    WalerConnectedMemberSummary,
    build_waler_connected_member_summary,
)
from dxf_import.models import (
    Beam,
    BeamCrossing,
    Brace,
    CandidatePoint,
    Column,
    ComponentAssociation,
    CornerBrace,
    CornerBraceConnection,
    DoubleSupportCandidate,
    DXFImportError,
    DXFImportResult,
    ProblemRecord,
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

    def trace_add(self, _mode, _callback):
        return None


class _GridFrame:
    def __init__(self):
        self.visible = None

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False


class _PackFrame:
    def __init__(self):
        self.visible = False
        self.options = {}

    def pack(self, **options):
        self.visible = True
        self.options = options

    def pack_forget(self):
        self.visible = False


class _Button:
    def __init__(self, *args, **options):
        self.options = dict(options)
        self.command = options.get("command")
        self.visible = False

    def configure(self, **options):
        self.options.update(options)

    def pack(self, **_options):
        self.visible = True

    def pack_forget(self):
        self.visible = False

    def invoke(self):
        if self.command is not None:
            return self.command()
        return None


def _candidate(identifier="P1", component_id="W1"):
    return CandidatePoint(
        id=identifier,
        world_point=(110.0, 220.0),
        local_point=(10.0, 20.0),
        point_type="endpoint",
        label="端點 A",
        component_id=component_id,
    )


def _waler(*, points=(), contact_face_state="formal"):
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
        contact_face_state=contact_face_state,
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


def _brace(*, source_width=350.0):
    return Brace(
        id="B1",
        start=(0.0, 0.0),
        end=(3000.0, 4000.0),
        source_layer="斜撐",
        source_handles=("HB1",),
        source_entity_types=("INSERT",),
        recognition_method="bim_block_whole_axis",
        centerline_computed=True,
        source_width=source_width,
        from_waler="W1",
        to_waler="W2",
        confidence=1.0,
    )


def _corner_brace(*, source_width=300.0):
    return CornerBrace(
        id="CB1",
        start=(0.0, 0.0),
        end=(300.0, 400.0),
        source_layer="角撐",
        source_handles=("HCB1",),
        source_entity_types=("INSERT",),
        recognition_method="connection_plate_midpoints",
        centerline_computed=True,
        source_width=source_width,
        confidence=1.0,
    )


def _column(identifier="C25"):
    return Column(
        id=identifier,
        start=(500.0, -500.0),
        end=(500.0, 500.0),
        source_layer="中間柱",
        source_handles=(f"H{identifier}",),
        source_entity_types=("LINE",),
        recognition_method="existing_centerline",
        centerline_computed=True,
        source_width=300.0,
        confidence=1.0,
        world_reference_point=(500.0, 0.0),
    )


def _column_review_item(*, status="recognized", member_id="C25"):
    return ReviewItem(
        key="member:column:C25" if member_id else "source:column:HC25",
        display_id=member_id or "待修-HC25",
        role="column",
        status=status,
        member_id=member_id,
        source_handles=("HC25",),
        source_layers=("中間柱",),
        source_entity_types=("LINE",),
        selection_source="auto" if member_id else "",
        problems=(),
        highest_severity="success" if member_id else "warning",
    )


def _corner_connection(corner_id="CB1", waler_id="W1"):
    return CornerBraceConnection(
        corner_brace_id=corner_id,
        waler_id=waler_id,
        strut_id="S1",
        strut_endpoint_name="from",
        corner_waler_endpoint_name="start",
        baseline_waler_attachment=(0.0, 0.0),
        baseline_strut_attachment=(300.0, 400.0),
        strut_hole_station_mm=500.0,
        fixed_length_mm=500.0,
        baseline_waler_station_mm=100.0,
    )


def _result(
    *,
    walers=(),
    struts=(),
    braces=(),
    corner_braces=(),
    corner_brace_connections=(),
    **extra,
):
    return DXFImportResult(
        source_path="review.dxf",
        layer_names=("圍令", "支撐", "斜撐", "角撐"),
        selected_layers={},
        layer_info=(),
        walers=tuple(walers),
        struts=tuple(struts),
        braces=tuple(braces),
        corner_braces=tuple(corner_braces),
        corner_brace_connections=tuple(corner_brace_connections),
        entity_debug=(),
        messages=(),
        source_entity_counts={},
        **extra,
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


def _select_state(state, member_id):
    if state.selected_component_id == member_id:
        return False
    state.selected_component_id = member_id
    return True


class DxfReviewPhase3LayoutTests(unittest.TestCase):
    def test_column_repair_uses_only_selected_formal_column_subject(self):
        build_source = inspect.getsource(DXFImportDialog._build_phase3_modification_tools)
        self.assertIn('text="中間柱關聯修補"', build_source)
        self.assertIn('command=self._open_column_association_repair', build_source)
        self.assertNotIn('problem_tree.bind', build_source)

        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_workflow = SimpleNamespace(
            world_result=SimpleNamespace(columns=(_column(),)),
        )
        column_item = _column_review_item()
        dialog.review_item_by_key = {column_item.key: column_item}
        dialog.selected_review_item_key = column_item.key
        dialog.selection_state = SelectionState(selected_component_id="C25")
        self.assertEqual(dialog._selected_column_repair_subject_id(), "C25")

        for role, member_id in (("strut", "S20"), ("brace", "B1"), ("waler", "W1")):
            item = replace(
                column_item,
                key=f"member:{role}:{member_id}",
                display_id=member_id,
                role=role,
                member_id=member_id,
            )
            dialog.review_item_by_key = {item.key: item}
            dialog.selected_review_item_key = item.key
            dialog.selection_state = SelectionState(selected_component_id=member_id)
            self.assertEqual(dialog._selected_column_repair_subject_id(), "")

        unresolved = _column_review_item(status="unresolved", member_id=None)
        dialog.review_item_by_key = {unresolved.key: unresolved}
        dialog.selected_review_item_key = unresolved.key
        dialog.selection_state = SelectionState()
        self.assertEqual(dialog._selected_column_repair_subject_id(), "")

        dialog.selected_review_item_key = ""
        self.assertEqual(dialog._selected_column_repair_subject_id(), "")

        plan = SimpleNamespace(candidate_strut_ids=("S20", "S35"))
        self.assertEqual(dialog._column_repair_selected_ids(plan, "first"), ("S20",))
        self.assertEqual(dialog._column_repair_selected_ids(plan, "second"), ("S35",))
        self.assertEqual(dialog._column_repair_selected_ids(plan, "both"), ("S20", "S35"))
        self.assertEqual(dialog._column_repair_selected_ids(plan, ""), ())

        class Window:
            destroyed = False

            def destroy(self):
                self.destroyed = True

        window = Window()
        dialog.column_repair_window = window
        dialog.column_repair_plan = plan
        dialog._column_repair_overlay_items = []
        dialog.canvas = None
        dialog.tk = SimpleNamespace(TclError=Exception)
        dialog._close_column_association_repair()
        self.assertTrue(window.destroyed)
        self.assertIsNone(dialog.column_repair_plan)
        self.assertIsNone(dialog.column_repair_window)

        update_source = inspect.getsource(DXFImportDialog._update_modification_tools)
        self.assertIn("self._selected_column_repair_subject_id()", update_source)
        self.assertNotIn("_column_repair_subjects", update_source)

    def test_column_repair_selection_paths_refresh_the_same_detail_boundary(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        column = _column()
        strut = _strut("S20")
        items = {
            "C25": _column_review_item(),
            "S20": ReviewItem(
                key="member:strut:S20",
                display_id="S20",
                role="strut",
                status="recognized",
                member_id="S20",
                source_handles=("HS20",),
                source_layers=("支撐",),
                source_entity_types=("LINE",),
                selection_source="auto",
                problems=(),
                highest_severity="success",
            ),
        }
        members = {"C25": column, "S20": strut}
        dialog.review_workflow = SimpleNamespace(
            world_result=SimpleNamespace(columns=(column,)),
        )
        dialog.review_item_by_key = {item.key: item for item in items.values()}
        dialog.selected_review_item_key = ""
        dialog.selection_state = SelectionState()
        dialog.selection_controller = SimpleNamespace(
            select_component=lambda member_id, _source: _select_state(
                dialog.selection_state, member_id
            )
        )
        dialog._review_item_for_member_id = lambda member_id: items.get(member_id)
        dialog._member_by_id = lambda member_id: members.get(member_id)
        dialog._selected_member = lambda: members.get(dialog.selected_member_id)
        dialog.selected_problem = None
        dialog.focus_member_ids = set()
        dialog.focus_handles = set()
        dialog.selected_only_var = _Variable(False)
        dialog.preview_view_bounds = None
        dialog.preview_fit_all = False
        dialog.render_scheduler = SimpleNamespace(request=lambda _dirty: None)
        observed = []
        dialog._update_selected_member_panel = lambda: observed.append(
            dialog._selected_column_repair_subject_id()
        )

        dialog._select_member("C25", refit=False, clear_problem=True, source="component_tree")
        dialog._select_member("S20", refit=False, clear_problem=True, source="component_tree")
        dialog._select_member("C25", refit=False, clear_problem=True, source="canvas")
        dialog.selection_state = SelectionState()
        dialog.selected_review_item_key = ""
        observed.append(dialog._selected_column_repair_subject_id())

        self.assertEqual(observed, ["C25", "", "C25", ""])
        canvas_source = inspect.getsource(DXFImportDialog._on_canvas_click)
        self.assertIn('source="canvas"', canvas_source)

    def test_column_repair_single_preview_uses_plan_for_repaired_and_review_states(self):
        source = inspect.getsource(DXFImportDialog._open_column_association_repair)
        self.assertNotIn("Listbox", source)
        self.assertNotIn("_column_repair_subjects", source)
        self.assertIn("plan_column_association_repair(column_id)", source)
        self.assertIn("plan.selected_strut_ids", source)
        self.assertIn("withdraw_column_association_repair(plan)", source)
        self.assertIn('plan.status == "requires_review"', source)

        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_workflow = SimpleNamespace(
            world_result=SimpleNamespace(columns=(_column(),)),
        )
        dialog.problem_records = (
            ProblemRecord(
                "warning",
                "COLUMN_ASSOCIATION_REQUIRES_REVIEW",
                "C25",
                "C25 的人工中間柱關聯已失效，需重新檢查。",
                "column",
                ("HC25",),
                ("C25",),
            ),
        )
        plan = SimpleNamespace(column_source_handles=("HC25",))
        self.assertEqual(
            dialog._column_repair_problem_reason(plan),
            "C25 的人工中間柱關聯已失效，需重新檢查。",
        )
        review_plan = SimpleNamespace(
            column_id="C25",
            column_source_handles=("HC25",),
            status="requires_review",
            candidate_strut_ids=("S20", "S35"),
            selected_strut_ids=(),
            options=(),
        )
        self.assertIn(
            "失效原因：C25 的人工中間柱關聯已失效，需重新檢查。",
            dialog._column_repair_detail_lines(review_plan),
        )

        dialog.column_repair_plan = SimpleNamespace(column_id="C25")
        dialog.selection_state = SelectionState(selected_component_id="S20")
        self.assertEqual(dialog.column_repair_plan.column_id, "C25")

    def test_column_repair_command_revalidates_selection_without_fallback(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        plan = Mock(side_effect=DXFImportError("此中間柱目前不可修補。"))
        dialog.review_workflow = SimpleNamespace(
            world_result=SimpleNamespace(columns=(_column("C25"), _column("C26"))),
            plan_column_association_repair=plan,
        )
        dialog.window = object()
        dialog._selected_column_repair_subject_id = lambda: "C25"
        with patch("tkinter.messagebox.showinfo") as showinfo:
            dialog._open_column_association_repair()
        plan.assert_called_once_with("C25")
        showinfo.assert_called_once()

        dialog._selected_column_repair_subject_id = lambda: ""
        plan.reset_mock()
        with patch("tkinter.messagebox.showwarning") as showwarning:
            dialog._open_column_association_repair()
        plan.assert_not_called()
        showwarning.assert_called_once()

    def test_repaired_column_opens_current_plan_and_withdraws_it(self):
        class Window(_PackFrame):
            destroyed = False

            def title(self, _value):
                return None

            def transient(self, _parent):
                return None

            def protocol(self, _name, _callback):
                return None

            def destroy(self):
                self.destroyed = True

        class Widgets:
            def __init__(self):
                self.buttons = []
                self.labels = []

            def Frame(self, *_args, **_kwargs):
                return _PackFrame()

            def Label(self, *_args, **kwargs):
                label = _PackFrame()
                label.options = kwargs
                self.labels.append(label)
                return label

            def Radiobutton(self, *_args, **kwargs):
                button = _Button(**kwargs)
                self.buttons.append(button)
                return button

            def Button(self, *_args, **kwargs):
                button = _Button(**kwargs)
                self.buttons.append(button)
                return button

        column = _column()
        plan = SimpleNamespace(
            column_id="C25",
            column_source_handles=("HC25",),
            status="repaired",
            candidate_strut_ids=("S20", "S35"),
            selected_strut_ids=("S35",),
            options=(
                (10.0, "S20", 400.0, (500.0, 0.0)),
                (12.0, "S35", 600.0, (500.0, 0.0)),
            ),
        )
        workflow = SimpleNamespace(
            world_result=SimpleNamespace(columns=(column,)),
            plan_column_association_repair=Mock(return_value=plan),
            withdraw_column_association_repair=Mock(return_value=SimpleNamespace()),
        )
        widgets = Widgets()
        window = Window()
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_workflow = workflow
        item = _column_review_item()
        dialog.review_item_by_key = {item.key: item}
        dialog.selected_review_item_key = item.key
        dialog.selection_state = SelectionState(selected_component_id="C25")
        dialog.problem_records = ()
        dialog.window = object()
        dialog.tk = SimpleNamespace(
            Toplevel=lambda _parent: window,
            StringVar=lambda value="": _Variable(value),
            TclError=Exception,
        )
        dialog.ttk = widgets
        dialog.canvas = None
        dialog.preview_renderer = None
        dialog.preview_transform = None
        dialog.result = None
        dialog._column_repair_overlay_items = []
        dialog._refresh_result_views = lambda **_kwargs: None
        dialog._show_workflow_confirmation_invalidations = lambda _mutation: None

        dialog._open_column_association_repair()

        workflow.plan_column_association_repair.assert_called_once_with("C25")
        self.assertIs(dialog.column_repair_plan, plan)
        self.assertEqual(
            dialog.column_repair_details_var.get(),
            "\n".join(dialog._column_repair_detail_lines(plan)),
        )
        self.assertEqual(dialog.column_repair_plan.selected_strut_ids, ("S35",))
        self.assertIn(
            "目前人工決策：S35",
            dialog._column_repair_detail_lines(plan),
        )
        withdraw = next(
            button for button in widgets.buttons
            if button.options.get("text") == "撤銷"
        )
        withdraw.invoke()
        workflow.withdraw_column_association_repair.assert_called_once_with(plan)
        self.assertTrue(window.destroyed)
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

    def test_preview_styles_formal_and_provisional_walers_from_typed_state(self):
        formal = _waler(contact_face_state="formal")
        provisional = replace(
            _waler(contact_face_state="provisional"),
            id="W2",
            source_handles=("A2",),
        )
        result = _result(walers=(formal, provisional))
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = result

        styles = {
            member.id: (color, width, dash)
            for member, color, width, dash in dialog._preview_member_styles()
            if isinstance(member, Waler)
        }

        self.assertEqual(styles["W1"], ("#2e7d32", 4, None))
        self.assertEqual(styles["W2"], ("#ef6c00", 3, (6, 4)))
        self.assertIs(dialog.result, result)
        self.assertEqual(result.walers, (formal, provisional))

    def test_engineering_rows_name_provisional_axis_without_promoting_it(self):
        provisional = _waler(contact_face_state="provisional")
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = _result(walers=(provisional,))

        rows = dict(dialog._engineering_data_rows(provisional))

        self.assertEqual(
            rows["圍令接觸面狀態"],
            "暫定中心軸（尚未完成接觸面）",
        )
        self.assertEqual(provisional.contact_face_state, "provisional")

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
        self.assertNotIn("構件寬度（mm）", labels)

    def test_brace_and_corner_brace_engineering_rows_show_source_width(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)

        for member, expected in (
            (_brace(source_width=350.0), "350.000"),
            (_corner_brace(source_width=300.0), "300.000"),
        ):
            with self.subTest(member=member.id):
                project_row_before = member.to_project_row().copy()

                rows = dialog._engineering_data_rows(member)
                labels = [label for label, _value in rows]

                self.assertEqual(dict(rows)["構件寬度（mm）"], expected)
                self.assertEqual(labels[-2:], [
                    "構件寬度（mm）",
                    "構件長度（mm）",
                ])
                self.assertEqual(member.to_project_row(), project_row_before)
                self.assertNotIn("Width", member.to_project_row())
                self.assertNotIn("source_width", member.to_project_row())

    def test_brace_width_display_uses_dash_for_unreliable_values(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)

        for source_width in (None, 0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(source_width=source_width):
                rows = dict(
                    dialog._engineering_data_rows(
                        _brace(source_width=source_width)
                    )
                )

                self.assertEqual(rows["構件寬度（mm）"], "—")

    def test_repaired_corner_brace_without_reliable_width_shows_dash(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        member = replace(
            _corner_brace(source_width=0.0),
            selection_source="corner_brace_repair",
        )

        rows = dict(dialog._engineering_data_rows(member))

        self.assertEqual(rows["構件寬度（mm）"], "—")
        self.assertEqual(member.source_width, 0.0)
        self.assertEqual(member.selection_source, "corner_brace_repair")

    def test_non_target_member_engineering_rows_do_not_show_width(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)

        rows = dialog._engineering_data_rows(_waler())

        self.assertNotIn("構件寬度（mm）", dict(rows))
        self.assertEqual(rows[-1][0], "構件長度（mm）")

    def test_waler_connection_summary_uses_formal_member_identity_not_ui_identity(self):
        selected_waler = _waler()
        same_handle_other_identity = replace(
            _waler(),
            id="W9",
            source_handles=selected_waler.source_handles,
        )
        result = _result(
            walers=(selected_waler, same_handle_other_identity),
            struts=(
                replace(_strut("S10"), from_waler="W1", to_waler="W1"),
                replace(_strut("S2"), from_waler="W1", to_waler="W2"),
                replace(_strut("S1"), from_waler="tree:waler:W1", to_waler="W9"),
            ),
            braces=(
                _brace(),
                replace(_brace(), id="B9", from_waler="W9", to_waler="W2"),
            ),
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = result
        dialog.selection_state = SelectionState(
            selected_component_id="tree:waler:W1"
        )
        dialog.member_by_tree_iid = {"tree:waler:W1": "W9"}

        summary = build_waler_connected_member_summary(result, selected_waler.id)
        rows = dict(dialog._engineering_data_rows(selected_waler))

        self.assertEqual(summary.strut_ids, ("S2", "S10"))
        self.assertEqual(summary.brace_ids, ("B1",))
        self.assertEqual(rows["直接連接支撐"], "S2、S10")
        self.assertEqual(rows["直接連接斜撐"], "B1")
        self.assertNotIn("S1", rows["直接連接支撐"].split("、"))
        self.assertNotIn("B9", rows["直接連接斜撐"].split("、"))

    def test_waler_connection_summary_is_order_independent_after_rebuild(self):
        struts = (
            replace(_strut("S10"), from_waler="W1", to_waler="W1"),
            replace(_strut("S2"), from_waler="W2", to_waler="W1"),
        )
        corners = (
            replace(_corner_brace(), id="CB10"),
            replace(_corner_brace(), id="CB2"),
        )
        connections = (
            _corner_connection("CB10"),
            _corner_connection("CB2"),
            _corner_connection("CB2"),
        )
        first = _result(
            walers=(_waler(),),
            struts=struts,
            corner_braces=corners,
            corner_brace_connections=connections,
        )
        rebuilt = _result(
            walers=(_waler(),),
            struts=tuple(reversed(struts)),
            corner_braces=tuple(reversed(corners)),
            corner_brace_connections=tuple(reversed(connections)),
        )

        first_summary = build_waler_connected_member_summary(first, "W1")
        rebuilt_summary = build_waler_connected_member_summary(rebuilt, "W1")

        self.assertEqual(first_summary, rebuilt_summary)
        self.assertEqual(first_summary.strut_ids, ("S2", "S10"))
        self.assertEqual(first_summary.corner_brace_ids, ("CB2", "CB10"))

    def test_waler_connection_summary_requires_formal_corner_member_and_connection(self):
        result = _result(
            walers=(_waler(),),
            corner_braces=(_corner_brace(),),
            corner_brace_connections=(
                _corner_connection("CB1", "W1"),
                _corner_connection("CB-ORPHAN", "W1"),
                _corner_connection("CB1", "W2"),
            ),
        )

        summary = build_waler_connected_member_summary(result, "W1")

        self.assertEqual(summary.corner_brace_ids, ("CB1",))

    def test_waler_connection_summary_ignores_nonformal_corner_states(self):
        result = _result(
            walers=(_waler(),),
            corner_brace_body_evidence=(SimpleNamespace(member_id="CB-HYP"),),
            corner_brace_relationship_assessments=(
                SimpleNamespace(corner_brace_id="CB-ASSESS", waler_id="W1"),
            ),
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = result
        dialog.corner_brace_repair_plan = SimpleNamespace(
            candidates=(SimpleNamespace(corner_brace_id="CB-PREVIEW", waler_id="W1"),)
        )
        dialog.corner_brace_repair_candidate_id = "CB-PREVIEW"

        summary = build_waler_connected_member_summary(result, "W1")
        rows = dict(dialog._engineering_data_rows(_waler()))

        self.assertEqual(summary.corner_brace_ids, ())
        self.assertEqual(rows["直接連接角撐"], "—")

    def test_waler_connection_summary_does_not_mutate_result_or_models(self):
        result = _result(
            walers=(_waler(),),
            struts=(_strut("S1"),),
            braces=(_brace(),),
            corner_braces=(_corner_brace(),),
            corner_brace_connections=(_corner_connection(),),
        )
        before = copy.deepcopy(result)
        identities = (
            id(result),
            id(result.walers[0]),
            id(result.struts[0]),
            id(result.braces[0]),
            id(result.corner_braces[0]),
            id(result.corner_brace_connections[0]),
        )

        summary = build_waler_connected_member_summary(result, "W1")

        self.assertIsInstance(summary, WalerConnectedMemberSummary)
        self.assertIsInstance(summary.strut_ids, tuple)
        self.assertIsInstance(summary.brace_ids, tuple)
        self.assertIsInstance(summary.corner_brace_ids, tuple)
        self.assertEqual(result, before)
        self.assertEqual(
            identities,
            (
                id(result),
                id(result.walers[0]),
                id(result.struts[0]),
                id(result.braces[0]),
                id(result.corner_braces[0]),
                id(result.corner_brace_connections[0]),
            ),
        )

    def test_waler_engineering_rows_show_three_connection_groups_before_length(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = _result(
            walers=(_waler(),),
            struts=(_strut("S1"),),
            braces=(_brace(),),
            corner_braces=(_corner_brace(),),
            corner_brace_connections=(_corner_connection(),),
        )

        rows = dialog._engineering_data_rows(_waler())
        labels = [label for label, _value in rows]
        values = dict(rows)

        self.assertEqual(
            labels[-4:],
            [
                "直接連接支撐",
                "直接連接斜撐",
                "直接連接角撐",
                "構件長度（mm）",
            ],
        )
        self.assertEqual(values["直接連接支撐"], "S1")
        self.assertEqual(values["直接連接斜撐"], "B1")
        self.assertEqual(values["直接連接角撐"], "CB1")

    def test_waler_engineering_rows_keep_empty_connection_groups_visible(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = _result(walers=(_waler(),))

        rows = dict(dialog._engineering_data_rows(_waler()))

        self.assertEqual(rows["直接連接支撐"], "—")
        self.assertEqual(rows["直接連接斜撐"], "—")
        self.assertEqual(rows["直接連接角撐"], "—")

    def test_waler_engineering_rows_reproject_current_result_without_cache(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        waler = _waler()
        first = _result(walers=(waler,), struts=(_strut("S1"),))
        rebuilt = _result(
            walers=(waler,),
            struts=(replace(_strut("S2"), from_waler="W2", to_waler="W1"),),
        )
        dialog.selection_state = SelectionState(selected_component_id="tree-old-W1")
        dialog.member_by_tree_iid = {"tree-old-W1": "DISPLAY-W1"}
        dialog.result = first
        first_rows = dict(dialog._engineering_data_rows(waler))

        dialog.selection_state = SelectionState(selected_component_id="tree-new-W1")
        dialog.member_by_tree_iid = {"tree-new-W1": "RENAMED-DISPLAY-W1"}
        dialog.result = rebuilt
        rebuilt_before = copy.deepcopy(rebuilt)
        rebuilt_rows = dict(dialog._engineering_data_rows(waler))

        self.assertEqual(first_rows["直接連接支撐"], "S1")
        self.assertEqual(rebuilt_rows["直接連接支撐"], "S2")
        self.assertEqual(rebuilt, rebuilt_before)

    def test_non_waler_engineering_rows_do_not_show_connection_groups(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = _result()

        for member in (_strut("S1"), _brace(), _corner_brace()):
            with self.subTest(member=member.id):
                rows = dict(dialog._engineering_data_rows(member))
                self.assertNotIn("直接連接支撐", rows)
                self.assertNotIn("直接連接斜撐", rows)
                self.assertNotIn("直接連接角撐", rows)

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


class CornerBraceRepairButtonStateTests(unittest.TestCase):
    @staticmethod
    def _repair_candidate(identifier="repair-a", *, diagnostics=()):
        return SimpleNamespace(
            id=identifier,
            world_start=(100.1234, -200.4556),
            world_end=(300.7894, 400.0124),
            target_waler_id=f"W-{identifier}",
            target_strut_id=f"S-{identifier}",
            template_reference=SimpleNamespace(member_id=f"CB-{identifier}"),
            transfer_mode="same_side",
            reference_waler_offset_mm=350.1246,
            reference_strut_station_mm=-20.5556,
            reference_fixed_length_mm=700.0,
            fixed_length_mm=1234.5678,
            positional_anchor=(10.0, -20.5556),
            primary_references=(SimpleNamespace(member_id="CB-primary"),),
            secondary_references=(SimpleNamespace(member_id="CB-secondary"),),
            diagnostics=tuple(diagnostics),
        )

    def test_only_safe_recognized_or_unresolved_corner_subject_is_enabled(self):
        base = _review_item()
        recognized = replace(
            base,
            key="corner:T1",
            role="corner_brace",
            display_id="CB71",
            member_id="CB71",
        )
        unresolved = replace(
            recognized,
            key="unresolved:corner:T1",
            status="unresolved",
            member_id=None,
        )
        self.assertEqual(
            DXFImportDialog.corner_brace_repair_disabled_reason(recognized),
            "",
        )
        self.assertEqual(
            DXFImportDialog.corner_brace_repair_disabled_reason(unresolved),
            "",
        )
        self.assertTrue(
            DXFImportDialog.corner_brace_repair_disabled_reason(
                replace(recognized, status="excluded")
            )
        )
        self.assertTrue(
            DXFImportDialog.corner_brace_repair_disabled_reason(
                replace(recognized, role="strut")
            )
        )
        self.assertTrue(
            DXFImportDialog.corner_brace_repair_disabled_reason(
                replace(unresolved, source_handles=())
            )
        )

    def test_repair_preview_cancel_is_ui_only_and_apply_uses_workflow_command(self):
        cancel_source = inspect.getsource(
            DXFImportDialog._cancel_corner_brace_repair
        )
        apply_source = inspect.getsource(
            DXFImportDialog._apply_corner_brace_repair
        )
        preview_source = inspect.getsource(
            DXFImportDialog._show_corner_brace_repair_window
        )

        self.assertNotIn("review_workflow", cancel_source)
        self.assertIn("commit_corner_brace_repair", apply_source)
        self.assertNotIn("world_result =", apply_source)
        self.assertNotIn("result =", apply_source)
        self.assertIn("candidate.id", apply_source)
        self.assertIn("plan.candidates", preview_source)
        self.assertIn("WM_DELETE_WINDOW", preview_source)
        self.assertIn("_cancel_corner_brace_repair", preview_source)

    def test_repair_preview_uses_shared_chinese_terms_without_changing_dto_values(self):
        preview_source = inspect.getsource(
            DXFImportDialog._show_corner_brace_repair_window
        )
        summary_source = inspect.getsource(
            DXFImportDialog._corner_brace_repair_summary_text
        )
        audit_source = inspect.getsource(DXFImportDialog._corner_brace_repair_audit_text)
        visible_source = preview_source + summary_source + audit_source

        for label in (
            "目標圍令／支撐",
            "選用模板",
            "移植方式",
            "圍令端定位距離",
            "支撐端定位距離",
            "結果長度",
            "參考固定長度",
            "自動辨識主要依據",
            "人工修補次要依據",
        ):
            self.assertIn(label, visible_source)
        self.assertIn(
            "量測基準：目標圍令與支撐的交會點；",
            preview_source,
        )
        self.assertIn("支撐端定位距離沿支撐內側方向量測。", preview_source)
        for replaced_label in (
            "圍令端距交會點",
            "支撐端距交會點",
            "圍令偏移",
            "支撐位置",
        ):
            self.assertNotIn(replaced_label, visible_source)
        for english_label in (
            "Selected template",
            "Waler offset",
            "Strut station",
            "Result mm",
            "Reference mm",
            "Supporting automatic",
            "Manual secondary",
        ):
            self.assertNotIn(english_label, preview_source)
        self.assertIn(
            "corner_brace_transfer_mode_label(candidate.transfer_mode)",
            preview_source + summary_source,
        )
        self.assertIn("reference_waler_offset_mm", visible_source)
        self.assertIn("reference_strut_station_mm", visible_source)
        self.assertNotIn("candidate.transfer_mode =", visible_source)

    def test_repair_preview_formatters_use_three_decimals_without_mutating_values(self):
        candidate = self._repair_candidate()
        original_values = (
            candidate.reference_waler_offset_mm,
            candidate.reference_strut_station_mm,
            candidate.reference_fixed_length_mm,
            candidate.fixed_length_mm,
            candidate.positional_anchor,
            candidate.world_start,
            candidate.world_end,
        )

        self.assertEqual(
            DXFImportDialog._format_corner_brace_repair_scalar(1234.5678),
            "1234.568",
        )
        self.assertEqual(
            DXFImportDialog._format_corner_brace_repair_scalar(-20.5556),
            "-20.556",
        )
        self.assertEqual(
            DXFImportDialog._format_corner_brace_repair_length(7),
            "7.000 mm",
        )
        self.assertEqual(
            DXFImportDialog._format_corner_brace_repair_point(
                candidate.positional_anchor
            ),
            "(10.000, -20.556)",
        )
        self.assertEqual(
            DXFImportDialog._format_corner_brace_repair_line(
                candidate.world_start,
                candidate.world_end,
            ),
            "(100.123, -200.456) → (300.789, 400.012)",
        )
        self.assertNotIn(
            "mm",
            DXFImportDialog._format_corner_brace_repair_point(
                candidate.positional_anchor
            ),
        )
        self.assertEqual(
            original_values,
            (
                candidate.reference_waler_offset_mm,
                candidate.reference_strut_station_mm,
                candidate.reference_fixed_length_mm,
                candidate.fixed_length_mm,
                candidate.positional_anchor,
                candidate.world_start,
                candidate.world_end,
            ),
        )

    def test_repair_summary_and_audit_project_only_selected_candidate(self):
        candidate = self._repair_candidate(diagnostics=("candidate diagnostic",))
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.corner_brace_repair_plan = SimpleNamespace(
            candidates=(candidate,),
            diagnostics=("plan diagnostic",),
        )

        summary = dialog._corner_brace_repair_summary_text(candidate)
        audit = dialog._corner_brace_repair_audit_text(candidate)

        self.assertIn("圍令端定位距離：350.125 mm", summary)
        self.assertIn("支撐端定位距離：-20.556 mm", summary)
        self.assertIn("結果長度：1234.568 mm", summary)
        self.assertIn("參考固定長度：700.000 mm", audit)
        self.assertIn(
            "工程線：(100.123, -200.456) → (300.789, 400.012)",
            audit,
        )
        self.assertIn("定位錨點：(10.000, -20.556)", audit)
        self.assertIn("自動辨識主要依據：CB-primary", audit)
        self.assertIn("人工修補次要依據：CB-secondary", audit)
        self.assertIn("candidate diagnostic", audit)
        self.assertIn("plan diagnostic", audit)

    def test_multi_candidate_selection_uses_candidate_id_and_refreshes_projection(self):
        first = self._repair_candidate("repair-a")
        second = self._repair_candidate("repair-b", diagnostics=("second",))

        class _Tree:
            selected = ()

            def selection(self):
                return self.selected

        tree = _Tree()
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.corner_brace_repair_plan = SimpleNamespace(
            candidates=(first, second),
            diagnostics=(),
        )
        dialog.corner_brace_repair_candidate_id = ""
        dialog.corner_brace_repair_tree = tree
        dialog.corner_brace_repair_apply_button = _Button()
        dialog.corner_brace_repair_summary_var = _Variable()
        dialog.corner_brace_repair_audit_var = _Variable()
        dialog.corner_brace_repair_diagnostic_hint_var = _Variable()
        drawn = []
        cleared = []
        dialog._draw_corner_brace_repair_overlay = drawn.append
        dialog._clear_corner_brace_repair_overlay = lambda: cleared.append(True)

        dialog._on_corner_brace_repair_candidate_selected()
        self.assertEqual(
            dialog.corner_brace_repair_apply_button.options["state"],
            "disabled",
        )
        self.assertEqual(cleared, [True])

        tree.selected = (second.id,)
        dialog._on_corner_brace_repair_candidate_selected()

        self.assertEqual(dialog.corner_brace_repair_candidate_id, second.id)
        self.assertEqual(
            dialog.corner_brace_repair_apply_button.options["state"],
            "normal",
        )
        self.assertIn("W-repair-b / S-repair-b", dialog.corner_brace_repair_summary_var.get())
        self.assertIn("second", dialog.corner_brace_repair_audit_var.get())
        self.assertEqual(dialog.corner_brace_repair_diagnostic_hint_var.get(), "有診斷資料")
        self.assertEqual(drawn, [second])

    def test_audit_toggle_is_presentation_only_and_can_be_reopened(self):
        preview_source = inspect.getsource(
            DXFImportDialog._show_corner_brace_repair_window
        )
        selection_source = inspect.getsource(
            DXFImportDialog._on_corner_brace_repair_candidate_selected
        )
        self.assertIn(
            "self.corner_brace_repair_audit_expanded = False",
            preview_source,
        )
        self.assertNotIn(
            "self.corner_brace_repair_audit_frame.pack(",
            preview_source,
        )
        self.assertNotIn("problem_severity", selection_source)
        self.assertNotIn("ERROR_SEVERITIES", selection_source)

        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.corner_brace_repair_audit_expanded = False
        dialog.corner_brace_repair_audit_frame = _PackFrame()
        dialog.corner_brace_repair_audit_button = _Button()
        dialog.corner_brace_repair_candidate_id = "repair-a"
        dialog.corner_brace_repair_apply_button = _Button()
        dialog.corner_brace_repair_apply_button.configure(state="normal")
        dialog._corner_brace_repair_overlay_items = [11, 12, 13]
        dialog.review_workflow = object()
        original_workflow = dialog.review_workflow

        dialog._toggle_corner_brace_repair_audit()
        self.assertTrue(dialog.corner_brace_repair_audit_expanded)
        self.assertTrue(dialog.corner_brace_repair_audit_frame.visible)
        self.assertEqual(
            dialog.corner_brace_repair_audit_button.options["text"],
            "隱藏稽核與診斷",
        )
        dialog._toggle_corner_brace_repair_audit()
        self.assertFalse(dialog.corner_brace_repair_audit_frame.visible)
        self.assertEqual(
            dialog.corner_brace_repair_audit_button.options["text"],
            "顯示稽核與診斷",
        )
        dialog._toggle_corner_brace_repair_audit()
        self.assertTrue(dialog.corner_brace_repair_audit_frame.visible)
        self.assertEqual(dialog.corner_brace_repair_candidate_id, "repair-a")
        self.assertEqual(
            dialog.corner_brace_repair_apply_button.options["state"],
            "normal",
        )
        self.assertEqual(dialog._corner_brace_repair_overlay_items, [11, 12, 13])
        self.assertIs(dialog.review_workflow, original_workflow)

    def test_single_candidate_ui_selection_refreshes_without_tree_or_commit(self):
        candidate = self._repair_candidate("only")
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.corner_brace_repair_plan = SimpleNamespace(
            candidates=(candidate,),
            diagnostics=(),
        )
        dialog.corner_brace_repair_candidate_id = candidate.id
        dialog.corner_brace_repair_tree = None
        dialog.corner_brace_repair_apply_button = _Button()
        dialog.corner_brace_repair_summary_var = _Variable()
        dialog.corner_brace_repair_audit_var = _Variable()
        dialog.corner_brace_repair_diagnostic_hint_var = _Variable()
        drawn = []
        dialog._draw_corner_brace_repair_overlay = drawn.append

        dialog._on_corner_brace_repair_candidate_selected()

        self.assertEqual(dialog.corner_brace_repair_candidate_id, candidate.id)
        self.assertEqual(
            dialog.corner_brace_repair_apply_button.options["state"],
            "normal",
        )
        self.assertIn("W-only / S-only", dialog.corner_brace_repair_summary_var.get())
        self.assertEqual(drawn, [candidate])

    def test_cancel_and_window_close_clear_preview_state_and_overlay(self):
        class _Window:
            destroyed = False

            def destroy(self):
                self.destroyed = True

        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.tk = SimpleNamespace(TclError=Exception)
        dialog.corner_brace_repair_plan = object()
        dialog.corner_brace_repair_candidate_id = "repair-a"
        dialog.corner_brace_repair_tree = object()
        dialog.corner_brace_repair_audit_expanded = True
        dialog.corner_brace_repair_window = _Window()
        cleared = []
        dialog._clear_corner_brace_repair_overlay = lambda: cleared.append(True)
        window = dialog.corner_brace_repair_window

        dialog._cancel_corner_brace_repair()

        self.assertEqual(cleared, [True])
        self.assertIsNone(dialog.corner_brace_repair_plan)
        self.assertEqual(dialog.corner_brace_repair_candidate_id, "")
        self.assertIsNone(dialog.corner_brace_repair_tree)
        self.assertFalse(dialog.corner_brace_repair_audit_expanded)
        self.assertIsNone(dialog.corner_brace_repair_window)
        self.assertTrue(window.destroyed)

    def test_repair_overlay_uses_plan_residuals_and_clears_before_redraw(self):
        class _Renderer:
            def __init__(self, scene):
                self.scene = scene
                self.created = []
                self.next_id = 1

            def _create(self, shape, layer, coordinates, options):
                item_id = self.next_id
                self.next_id += 1
                self.created.append((item_id, shape, layer, coordinates, options))
                self.scene.temporary_line_items.append(item_id)
                return item_id

            def create_line(self, layer, *coordinates, **options):
                return self._create("line", layer, coordinates, options)

            def create_oval(self, layer, *coordinates, **options):
                return self._create("oval", layer, coordinates, options)

        class _Canvas:
            def __init__(self):
                self.deleted = []
                self.raised = []

            def delete(self, item_id):
                self.deleted.append(item_id)

            def tag_raise(self, tag):
                self.raised.append(tag)

        candidate = self._repair_candidate("repair-a")
        residuals = (
            ((0.0, 0.0), (10.0, 0.0)),
            ((10.0, 0.0), (10.0, 10.0)),
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.tk = SimpleNamespace(TclError=Exception)
        dialog.preview_scene = SimpleNamespace(temporary_line_items=[])
        dialog.preview_renderer = _Renderer(dialog.preview_scene)
        dialog.preview_transform = object()
        dialog.canvas = _Canvas()
        dialog.result = SimpleNamespace(
            coordinate_system=SimpleNamespace(transform=lambda point: point)
        )
        dialog.corner_brace_repair_plan = SimpleNamespace(
            residual_segments=residuals
        )
        dialog._corner_brace_repair_overlay_items = []
        dialog._project_preview_point = lambda point: point

        dialog._draw_corner_brace_repair_overlay(candidate)

        first_items = tuple(dialog._corner_brace_repair_overlay_items)
        first_draw = dialog.preview_renderer.created[:]
        self.assertEqual(len(first_items), 4)
        self.assertEqual(
            [entry[4] for entry in first_draw[:2]],
            [
                {"fill": "#9e9e9e", "width": 2, "dash": (4, 3)},
                {"fill": "#9e9e9e", "width": 2, "dash": (4, 3)},
            ],
        )
        self.assertEqual(
            first_draw[2][4],
            {"fill": "#0d47a1", "width": 5},
        )
        self.assertEqual(first_draw[3][1], "oval")
        self.assertEqual(first_draw[3][4]["fill"], "#fb8c00")
        self.assertEqual(
            [entry[3] for entry in first_draw[:2]],
            [
                (0.0, 0.0, 10.0, 0.0),
                (10.0, 0.0, 10.0, 10.0),
            ],
        )

        dialog._draw_corner_brace_repair_overlay(candidate)

        second_items = tuple(dialog._corner_brace_repair_overlay_items)
        self.assertEqual(len(second_items), 4)
        self.assertTrue(set(first_items).issubset(dialog.canvas.deleted))
        self.assertTrue(set(first_items).isdisjoint(second_items))
        self.assertEqual(dialog.preview_scene.temporary_line_items, list(second_items))
        second_draw = dialog.preview_renderer.created[4:]
        self.assertEqual(len(second_draw), 4)
        self.assertEqual(sum(entry[1] == "line" for entry in second_draw), 3)

        dialog._clear_corner_brace_repair_overlay()
        self.assertEqual(dialog._corner_brace_repair_overlay_items, [])
        self.assertEqual(dialog.preview_scene.temporary_line_items, [])
        self.assertTrue(set(second_items).issubset(dialog.canvas.deleted))

        overlay_source = inspect.getsource(
            DXFImportDialog._draw_corner_brace_repair_overlay
        )
        self.assertIn("self.corner_brace_repair_plan.residual_segments", overlay_source)
        self.assertNotIn("source_geometry", overlay_source)
        self.assertNotIn("eligible_repair_references", overlay_source)

    def test_repair_preview_exposes_only_planner_candidates_and_never_auto_applies(self):
        open_source = inspect.getsource(
            DXFImportDialog._open_corner_brace_repair_preview
        )
        preview_source = inspect.getsource(
            DXFImportDialog._show_corner_brace_repair_window
        )

        no_candidate_branch = open_source.split("if not plan.candidates:", 1)[1]
        self.assertIn("showwarning", no_candidate_branch)
        self.assertLess(
            no_candidate_branch.index("return"),
            no_candidate_branch.index("_show_corner_brace_repair_window"),
        )
        self.assertIn("for candidate in plan.candidates", preview_source)
        self.assertIn("target_waler_id", preview_source)
        self.assertIn("target_strut_id", preview_source)
        self.assertIn("template_reference", preview_source)
        self.assertIn("transfer_mode", preview_source)
        self.assertIn("reference_waler_offset_mm", preview_source)
        self.assertIn("reference_strut_station_mm", preview_source)
        self.assertIn("reference_fixed_length_mm", preview_source)
        self.assertIn("fixed_length_mm", preview_source)
        self.assertIn("primary_references", preview_source)
        self.assertIn("secondary_references", preview_source)
        self.assertIn("len(plan.candidates) == 1", preview_source)
        self.assertNotIn("commit_corner_brace_repair", preview_source)

        projection_source = inspect.getsource(
            DXFImportDialog._corner_brace_repair_audit_text
        )
        selection_source = inspect.getsource(
            DXFImportDialog._on_corner_brace_repair_candidate_selected
        )
        self.assertIn("candidate.positional_anchor", projection_source)
        self.assertNotIn("plan_corner_brace_repair", selection_source)
        self.assertNotIn("eligible_repair_references", selection_source)


if __name__ == "__main__":
    unittest.main()
