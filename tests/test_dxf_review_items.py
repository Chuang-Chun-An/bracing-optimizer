from __future__ import annotations

import unittest
from types import SimpleNamespace

from bracing_optimizer.presentation.cad_view_interaction import CADViewport

from dxf_import.dialog import DXFImportDialog
from dxf_import.models import (
    DXFImportResult,
    EntityDebugInfo,
    ProblemRecord,
    ReviewItem,
    SelectionState,
    SourceGeometry,
    Strut,
    ValidationMessage,
)
from dxf_import.preview import RenderDirty
from dxf_import.validation import (
    build_problem_records,
    build_review_items,
    review_item_guidance,
)


class _Variable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _ReviewTree:
    def __init__(self):
        self.rows = {}
        self._selection = ()

    def get_children(self):
        return tuple(self.rows)

    def delete(self, *iids):
        for iid in iids:
            self.rows.pop(iid, None)

    def insert(
        self,
        parent,
        _position,
        *,
        iid,
        text="",
        values=(),
        tags=(),
        open=False,
    ):
        self.rows[iid] = {
            "parent": parent,
            "text": text,
            "values": tuple(values),
            "tags": tuple(tags),
            "open": open,
        }

    def selection(self):
        return self._selection


def _strut(
    identifier: str,
    handle: str,
    *,
    selection_source: str = "auto",
) -> Strut:
    return Strut(
        id=identifier,
        start=(0.0, 0.0),
        end=(1000.0, 0.0),
        source_layer="STRUT",
        source_handles=(handle,),
        source_entity_types=("LINE",),
        recognition_method="existing_centerline",
        centerline_computed=False,
        source_width=0.0,
        from_waler="W1",
        to_waler="W2",
        confidence=1.0,
        selection_source=selection_source,
    )


def _result(
    *,
    struts=(),
    messages=(),
    entity_debug=(),
    source_geometry=(),
) -> DXFImportResult:
    return DXFImportResult(
        source_path="review.dxf",
        layer_names=("STRUT", "BEAM"),
        selected_layers={"strut": ("STRUT",), "beam": ("BEAM",)},
        layer_info=(),
        walers=(),
        struts=tuple(struts),
        braces=(),
        columns=(),
        beams=(),
        corner_braces=(),
        entity_debug=tuple(entity_debug),
        messages=tuple(messages),
        source_entity_counts={},
        source_geometry=tuple(source_geometry),
    )


def _problem(
    severity: str,
    code: str,
    *,
    role="strut",
    handles=(),
    member_ids=(),
) -> ProblemRecord:
    return ProblemRecord(
        severity,
        code,
        ", ".join(member_ids or handles) or "—",
        f"{code} description",
        role,
        tuple(handles),
        tuple(member_ids),
    )


class ReviewProjectionTests(unittest.TestCase):
    def test_formal_member_without_problem_is_normal(self):
        item = build_review_items(_result(struts=(_strut("S1", "H1"),)))[0]

        self.assertEqual(item.key, "member:strut:S1")
        self.assertEqual(item.status, "recognized")
        self.assertEqual(item.highest_severity, "success")
        self.assertEqual(item.problems, ())

    def test_highest_severity_uses_critical_error_warning_order(self):
        member = _strut("S1", "H1")
        records = (
            _problem("warning", "WARN", handles=("H1",), member_ids=("S1",)),
            _problem("error", "ERROR", handles=("H1",), member_ids=("S1",)),
            _problem("critical", "CRITICAL", handles=("H1",), member_ids=("S1",)),
        )

        item = build_review_items(_result(struts=(member,)), records)[0]

        self.assertEqual(item.highest_severity, "critical")
        self.assertEqual(item.problem_count, 3)

    def test_explicit_shared_problem_is_same_object_on_both_members(self):
        first = _strut("S1", "H1")
        second = _strut("S2", "H2")
        shared = _problem(
            "error",
            "SHARED",
            handles=("H1", "H2"),
            member_ids=("S1", "S2"),
        )

        items = build_review_items(_result(struts=(first, second)), (shared,))

        self.assertIs(items[0].problems[0], shared)
        self.assertIs(items[1].problems[0], shared)

    def test_problem_records_use_explicit_ids_then_strict_unique_fallback(self):
        first = _strut("S1", "H1")
        second = _strut("S2", "H2")
        result = _result(
            struts=(first, second),
            messages=(
                ValidationMessage(
                    "error",
                    "EXPLICIT",
                    "shared",
                    "strut",
                    ("H1", "H2"),
                    ("S1", "S2"),
                ),
                ValidationMessage(
                    "warning",
                    "UNIQUE",
                    "unique",
                    "strut",
                    ("H1",),
                ),
                ValidationMessage(
                    "error",
                    "AMBIGUOUS",
                    "ambiguous",
                    "strut",
                    ("H1", "H2"),
                ),
            ),
        )

        records = {item.code: item for item in build_problem_records(result)}

        self.assertEqual(records["EXPLICIT"].member_ids, ("S1", "S2"))
        self.assertEqual(records["UNIQUE"].member_ids, ("S1",))
        self.assertEqual(records["AMBIGUOUS"].member_ids, ())

    def test_same_source_problem_set_builds_one_unresolved_item(self):
        messages = (
            ValidationMessage(
                "error",
                "BEAM_CENTERLINE_FAILED",
                "centerline",
                "beam",
                ("6EF",),
            ),
            ValidationMessage(
                "error",
                "BEAM_RECOGNITION_FAILED",
                "recognition",
                "beam",
                ("6EF",),
            ),
        )
        result = _result(
            messages=messages,
            entity_debug=(
                EntityDebugInfo("beam", "BEAM", "LINE", "6EF", "read"),
            ),
            source_geometry=(
                SourceGeometry(
                    "beam",
                    "6EF",
                    ((0.0, 0.0), (100.0, 0.0)),
                    False,
                    "BEAM",
                    "LINE",
                ),
            ),
        )

        items = build_review_items(result)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].display_id, "待修-6EF")
        self.assertEqual(items[0].status, "unresolved")
        self.assertEqual(items[0].problem_count, 2)
        self.assertEqual(items[0].source_layers, ("BEAM",))
        self.assertEqual(items[0].source_entity_types, ("LINE",))

    def test_unresolved_identity_uses_role_and_complete_handle_set(self):
        records = (
            _problem("error", "A", role="beam", handles=("H1", "H2")),
            _problem("warning", "B", role="beam", handles=("H1",)),
            _problem("error", "C", role="column", handles=("H1", "H2")),
        )

        items = build_review_items(_result(), records)

        self.assertEqual(len(items), 3)
        self.assertEqual(len({item.key for item in items}), 3)

    def test_ambiguous_formal_source_stays_only_in_global_problem_list(self):
        first = _strut("S1", "SHARED")
        second = _strut("S2", "SHARED")
        result = _result(
            struts=(first, second),
            messages=(
                ValidationMessage(
                    "error",
                    "AMBIGUOUS",
                    "cannot safely assign",
                    "strut",
                    ("SHARED",),
                ),
            ),
        )

        records = build_problem_records(result)
        items = build_review_items(result, records)

        self.assertEqual(records[0].member_ids, ())
        self.assertEqual(len(items), 2)
        self.assertTrue(all(item.status == "recognized" for item in items))
        self.assertTrue(all(not item.problems for item in items))

    def test_global_problem_does_not_create_fake_review_item(self):
        result = _result(
            messages=(
                ValidationMessage(
                    "critical",
                    "STRUT_RECOGNITION_FAILED",
                    "no struts",
                    "strut",
                ),
            )
        )

        self.assertEqual(build_review_items(result), ())
        self.assertEqual(len(build_problem_records(result)), 1)

    def test_guidance_is_deduplicated_and_respects_item_capability(self):
        formal = ReviewItem(
            "member:strut:S1",
            "S1",
            "strut",
            "recognized",
            "S1",
            ("H1",),
            ("STRUT",),
            ("LINE",),
            "auto",
            (
                _problem("error", "STRUT_NOT_CONNECTED", member_ids=("S1",)),
                _problem(
                    "error",
                    "STRUT_ONE_END_NOT_CONNECTED",
                    member_ids=("S1",),
                ),
            ),
            "error",
        )
        unresolved = ReviewItem(
            "source:beam:6EF",
            "待修-6EF",
            "beam",
            "unresolved",
            None,
            ("6EF",),
            ("BEAM",),
            ("LINE",),
            "",
            (_problem("error", "BEAM_RECOGNITION_FAILED", role="beam"),),
            "error",
        )

        formal_guidance = review_item_guidance(formal)
        unresolved_guidance = review_item_guidance(unresolved)

        self.assertEqual(len(formal_guidance), 1)
        self.assertIn("候選點區", formal_guidance[0])
        self.assertIn("從 CAD 指定工程線", formal_guidance[0])
        self.assertEqual(len(unresolved_guidance), 1)
        self.assertIn("圖層 ✓", unresolved_guidance[0])
        self.assertIn("幾何修正工具不適用", unresolved_guidance[0])

    def test_rebuilding_projection_removes_resolved_source_item(self):
        failed = _result(
            messages=(
                ValidationMessage(
                    "error",
                    "STRUT_RECOGNITION_FAILED",
                    "failed",
                    "strut",
                    ("H1",),
                ),
            )
        )
        resolved = _result(struts=(_strut("S1", "H1"),))

        self.assertEqual(build_review_items(failed)[0].status, "unresolved")
        resolved_items = build_review_items(resolved)
        self.assertEqual(len(resolved_items), 1)
        self.assertEqual(resolved_items[0].display_id, "S1")


class ReviewPresentationTests(unittest.TestCase):
    def test_step3_text_keeps_severity_manual_marker_and_problem_count(self):
        item = ReviewItem(
            "member:strut:S1",
            "S1",
            "strut",
            "recognized",
            "S1",
            ("H1",),
            ("STRUT",),
            ("LINE",),
            "manual_candidate_points",
            (_problem("error", "ERROR", member_ids=("S1",)),),
            "error",
        )

        self.assertEqual(DXFImportDialog._review_item_text(item), "✗ S1 ＊ (1)")

    def test_group_summary_counts_affected_items_not_problem_records(self):
        error = ReviewItem(
            "member:strut:S1",
            "S1",
            "strut",
            "recognized",
            "S1",
            (),
            (),
            (),
            "auto",
            (_problem("error", "E1"), _problem("error", "E2")),
            "error",
        )
        warning = ReviewItem(
            "member:strut:S2",
            "S2",
            "strut",
            "recognized",
            "S2",
            (),
            (),
            (),
            "auto",
            (_problem("warning", "W1"),),
            "warning",
        )

        text = DXFImportDialog._review_group_text("支撐", (error, warning))

        self.assertEqual(text, "支撐（2）｜✗1 ⚠1")

    def test_member_tree_contains_formal_and_unresolved_review_items(self):
        formal = build_review_items(
            _result(struts=(_strut("S1", "H1", selection_source="manual_candidate_points"),))
        )[0]
        unresolved = ReviewItem(
            "source:beam:6EF",
            "待修-6EF",
            "beam",
            "unresolved",
            None,
            ("6EF",),
            ("BEAM",),
            ("LINE",),
            "",
            (_problem("error", "FAILED", role="beam", handles=("6EF",)),),
            "error",
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.member_tree = _ReviewTree()
        dialog.member_by_tree_iid = {}
        dialog.review_item_by_tree_iid = {}
        dialog.review_items = (formal, unresolved)
        dialog.selected_review_item_key = ""
        dialog.result = object()
        dialog._updating_member_tree = False
        dialog.member_tree_selection = SimpleNamespace(select=lambda _iid: None)

        dialog._refresh_member_tree()

        texts = {row["text"] for row in dialog.member_tree.rows.values()}
        self.assertIn("支撐（1）", texts)
        self.assertIn("S1 ＊", texts)
        self.assertIn("托梁（1）｜✗1", texts)
        self.assertIn("✗ 待修-6EF (1)", texts)

    def test_unresolved_selection_focuses_handles_without_fake_member(self):
        item = ReviewItem(
            "source:beam:6EF",
            "待修-6EF",
            "beam",
            "unresolved",
            None,
            ("6EF",),
            ("BEAM",),
            ("LINE",),
            "",
            (_problem("error", "FAILED", role="beam", handles=("6EF",)),),
            "error",
        )
        render_requests = []
        panel_updates = []
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.selected_problem = object()
        dialog.selected_review_item_key = ""
        dialog.focus_member_ids = {"S1"}
        dialog.focus_handles = set()
        dialog.selection_state = SelectionState(selected_component_id="S1")
        dialog.selection_controller = SimpleNamespace(state=dialog.selection_state)
        dialog.selected_only_var = _Variable(False)
        dialog.candidate_action_status_var = _Variable("")
        dialog._update_selected_member_panel = lambda: panel_updates.append(True)
        dialog.preview_viewport = CADViewport()
        dialog.preview_fit_all = True
        dialog._open_preview_window = lambda: None
        dialog.render_scheduler = SimpleNamespace(request=render_requests.append)

        dialog._select_unresolved_review_item(item)

        self.assertEqual(dialog.selected_member_id, "")
        self.assertEqual(dialog.selected_review_item_key, item.key)
        self.assertEqual(dialog.focus_member_ids, set())
        self.assertEqual(dialog.focus_handles, {"6EF"})
        self.assertEqual(panel_updates, [True])
        self.assertEqual(render_requests, [RenderDirty.FULL_SCENE])

    def test_step4_and_step7_use_shared_problem_focus_helper(self):
        record = _problem("error", "FAILED", handles=("6EF",))
        focused = []
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.problem_tree = _ReviewTree()
        dialog.problem_tree._selection = ("problem_0",)
        dialog.problem_record_by_iid = {"problem_0": record}
        dialog.detail_problem_tree = _ReviewTree()
        dialog.detail_problem_tree._selection = ("detail_0",)
        dialog.detail_problem_record_by_iid = {"detail_0": record}
        dialog.selected_only_var = _Variable(False)
        dialog._focus_problem_record = focused.append

        dialog._on_problem_selected()
        dialog._on_detail_problem_activated()

        self.assertEqual(focused, [record, record])

    def test_unresolved_issue_level_is_available_for_preview_overlay(self):
        item = ReviewItem(
            "source:beam:6EF",
            "待修-6EF",
            "beam",
            "unresolved",
            None,
            ("6EF",),
            (),
            (),
            "",
            (_problem("warning", "WARN", handles=("6EF",)),),
            "warning",
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.review_items = (item,)

        self.assertEqual(
            dialog._unresolved_source_issue_levels(),
            {"6EF": "warning"},
        )

    def test_step4_normal_item_explicitly_reports_validation_pass(self):
        item = ReviewItem(
            "member:strut:S1",
            "S1",
            "strut",
            "recognized",
            "S1",
            ("H1",),
            ("STRUT",),
            ("LINE",),
            "auto",
            (),
            "success",
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.detail_problem_tree = _ReviewTree()
        dialog.detail_problem_record_by_iid = {}
        dialog.detail_problem_empty_var = _Variable("")
        dialog.detail_guidance_var = _Variable("")

        dialog._update_review_issue_panel(item)

        self.assertEqual(dialog.detail_problem_tree.rows, {})
        self.assertEqual(
            dialog.detail_problem_empty_var.get(),
            "✓ 此構件目前沒有檢核問題",
        )
        self.assertEqual(
            dialog.detail_guidance_var.get(),
            "目前不需要額外處理。",
        )


if __name__ == "__main__":
    unittest.main()
