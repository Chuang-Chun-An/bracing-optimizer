from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from dxf_import.dialog import DXFImportDialog
from dxf_import.models import (
    Beam,
    Brace,
    Column,
    CoordinateSystem,
    CornerBrace,
    DXFImportResult,
    ReviewItem,
    Strut,
    ValidationMessage,
    Waler,
    WalerContactReviewState,
)
from dxf_import.review_confirmation import (
    FORMAL_REVIEW_ROLES,
    confirm_review_item,
    review_confirmation_identity,
    review_confirmation_signature,
    review_confirmations_from_state,
    review_item_can_be_confirmed,
    review_item_is_confirmed,
    serialize_review_confirmations,
    unconfirmed_formal_review_items,
    valid_review_confirmations,
)
from dxf_import.review_workflow import DXFReviewWorkflow, ReviewMutation
from dxf_import.validation import build_review_items


def _base_member_values(identifier: str, handle: str) -> dict:
    return {
        "id": identifier,
        "start": (0.0, 0.0),
        "end": (1000.0, 0.0),
        "source_layer": "MEMBER",
        "source_handles": (handle,),
        "source_entity_types": ("LINE",),
        "recognition_method": "existing_centerline",
        "centerline_computed": False,
        "source_width": 300.0,
        "confidence": 1.0,
    }


def _result(*, messages=(), coordinate_system=CoordinateSystem(), contact=None):
    waler = Waler(**_base_member_values("W1", "HW"))
    strut = Strut(
        **_base_member_values("S1", "HS"),
        from_waler="W1",
        to_waler="W1",
    )
    brace = Brace(
        **_base_member_values("B1", "HB"),
        from_waler="W1",
        to_waler="W1",
    )
    column = Column(**_base_member_values("C1", "HC"))
    beam = Beam(**_base_member_values("BM1", "HM"))
    corner = CornerBrace(**_base_member_values("CB1", "HK"))
    return DXFImportResult(
        source_path="review.dxf",
        layer_names=("MEMBER",),
        selected_layers={},
        layer_info=(),
        walers=(waler,),
        struts=(strut,),
        braces=(brace,),
        columns=(column,),
        beams=(beam,),
        corner_braces=(corner,),
        entity_debug=(),
        messages=tuple(messages),
        source_entity_counts={},
        coordinate_system=coordinate_system,
        waler_contact_reviews=((contact,) if contact is not None else ()),
    )


def _item(result: DXFImportResult, member_id: str) -> ReviewItem:
    return next(item for item in build_review_items(result) if item.member_id == member_id)


def _source_item(*, status: str, role: str = "unknown") -> ReviewItem:
    return ReviewItem(
        key=f"{status}:{role}:H1",
        display_id="待修-H1",
        role=role,
        status=status,
        member_id=None,
        source_handles=("H1",),
        source_layers=("MEMBER",),
        source_entity_types=("LINE",),
        selection_source="",
        problems=(),
        highest_severity="info",
    )


class _Variable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Button:
    def __init__(self):
        self.options = {}

    def configure(self, **options):
        self.options.update(options)


class ReviewConfirmationTests(unittest.TestCase):
    def test_legacy_review_state_without_confirmations_is_empty(self):
        self.assertEqual(
            review_confirmations_from_state({"review_state_version": 1}),
            {},
        )

    def test_confirmation_round_trip_persistence(self):
        result = _result()
        item = _item(result, "S1")
        confirmed = confirm_review_item(result, item)

        saved = serialize_review_confirmations(confirmed)
        restored = review_confirmations_from_state(
            {"review_state_version": 2, "review_confirmations": saved}
        )

        self.assertEqual(restored, confirmed)
        self.assertTrue(review_item_is_confirmed(result, item, restored))

    def test_unchanged_rebuild_preserves_confirmation(self):
        result = _result()
        original = _item(result, "S1")
        confirmed = confirm_review_item(result, original)
        rebuilt = _item(result, "S1")

        self.assertTrue(review_item_is_confirmed(result, rebuilt, confirmed))
        self.assertEqual(
            valid_review_confirmations(result, build_review_items(result), confirmed),
            confirmed,
        )

    def test_warning_can_be_confirmed(self):
        result = _result(
            messages=(
                ValidationMessage(
                    "warning", "CHECK", "review", "strut", ("HS",), ("S1",)
                ),
            )
        )
        item = _item(result, "S1")

        self.assertTrue(review_item_can_be_confirmed(item))
        self.assertTrue(
            review_item_is_confirmed(result, item, confirm_review_item(result, item))
        )

    def test_error_and_critical_cannot_be_confirmed(self):
        for severity in ("error", "critical"):
            with self.subTest(severity=severity):
                result = _result(
                    messages=(
                        ValidationMessage(
                            severity,
                            "BLOCKED",
                            "blocked",
                            "strut",
                            ("HS",),
                            ("S1",),
                        ),
                    )
                )
                item = _item(result, "S1")
                self.assertFalse(review_item_can_be_confirmed(item))
                self.assertIsNone(review_confirmation_signature(result, item))
                with self.assertRaises(ValueError):
                    confirm_review_item(result, item)

    def test_unresolved_excluded_and_unknown_do_not_need_confirmation(self):
        items = (
            _source_item(status="unresolved", role="beam"),
            _source_item(status="excluded", role="strut"),
            _source_item(status="unresolved", role="unknown"),
        )
        for item in items:
            with self.subTest(status=item.status, role=item.role):
                self.assertIsNone(review_confirmation_identity(item))
                self.assertFalse(review_item_can_be_confirmed(item))

    def test_all_six_formal_roles_can_be_confirmed(self):
        result = _result()
        items = build_review_items(result)

        self.assertEqual({item.role for item in items}, FORMAL_REVIEW_ROLES)
        self.assertTrue(all(review_item_can_be_confirmed(item) for item in items))

    def test_unconfirmed_projection_counts_only_six_formal_roles(self):
        result = _result()
        items = (
            *build_review_items(result),
            _source_item(status="unresolved", role="strut"),
            _source_item(status="excluded", role="beam"),
            _source_item(status="unresolved", role="unknown"),
        )
        confirmed = confirm_review_item(result, _item(result, "W1"))

        unconfirmed = unconfirmed_formal_review_items(
            result,
            items,
            confirmed,
        )

        self.assertEqual(len(unconfirmed), 5)
        self.assertEqual(
            {item.role for item in unconfirmed},
            FORMAL_REVIEW_ROLES - {"waler"},
        )

    def test_member_data_change_invalidates_signature(self):
        result = _result()
        item = _item(result, "S1")
        confirmed = confirm_review_item(result, item)
        changed = replace(
            result,
            struts=(replace(result.struts[0], associated_columns=("C1",)),),
        )
        changed_item = _item(changed, "S1")

        self.assertFalse(review_item_is_confirmed(changed, changed_item, confirmed))

    def test_coordinate_change_invalidates_signature(self):
        result = _result()
        item = _item(result, "S1")
        confirmed = confirm_review_item(result, item)
        changed = replace(
            result,
            coordinate_system=CoordinateSystem("local", 10.0, 20.0, "test"),
        )

        self.assertFalse(
            review_item_is_confirmed(changed, _item(changed, "S1"), confirmed)
        )

    def test_material_change_invalidates_signature(self):
        result = _result()
        item = _item(result, "S1")
        confirmed = confirm_review_item(result, item)
        changed = replace(
            result,
            struts=(replace(result.struts[0], material_spec="H400x400"),),
        )

        self.assertFalse(
            review_item_is_confirmed(changed, _item(changed, "S1"), confirmed)
        )

    def test_candidate_endpoint_change_invalidates_signature(self):
        result = _result()
        item = _item(result, "S1")
        confirmed = confirm_review_item(result, item)
        changed = replace(
            result,
            struts=(replace(result.struts[0], end=(1200.0, 0.0)),),
        )

        self.assertFalse(
            review_item_is_confirmed(changed, _item(changed, "S1"), confirmed)
        )

    def test_waler_contact_change_invalidates_signature(self):
        first_contact = WalerContactReviewState(
            "W1",
            (0.0, 0.0),
            (1000.0, 0.0),
            (0.0, 1.0),
            adopted_backfill_mm=100.0,
        )
        result = _result(contact=first_contact)
        item = _item(result, "W1")
        confirmed = confirm_review_item(result, item)
        changed_contact = replace(first_contact, adopted_backfill_mm=150.0)
        changed = replace(result, waler_contact_reviews=(changed_contact,))

        self.assertFalse(
            review_item_is_confirmed(changed, _item(changed, "W1"), confirmed)
        )

    def test_tree_text_can_show_severity_and_confirmation_together(self):
        result = _result(
            messages=(
                ValidationMessage(
                    "warning", "CHECK", "review", "strut", ("HS",), ("S1",)
                ),
            )
        )

        self.assertEqual(
            DXFImportDialog._review_item_text(
                _item(result, "S1"),
                confirmed=True,
            ),
            "⚠ S1 (1) ✓",
        )

    def test_only_collateral_confirmation_reset_shows_popup(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.window = object()

        with patch("tkinter.messagebox.showinfo") as showinfo:
            dialog._show_workflow_confirmation_invalidations(
                ReviewMutation(True, ("W1",)),
            )

        showinfo.assert_called_once()
        message = showinfo.call_args.args[1]
        self.assertIn("W1", message)
        self.assertNotIn("S1", message)

    def test_current_member_only_reset_is_silent(self):
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.window = object()

        with patch("tkinter.messagebox.showinfo") as showinfo:
            dialog._show_workflow_confirmation_invalidations(
                ReviewMutation(True),
            )

        showinfo.assert_not_called()


class ImportCompletionGateTests(unittest.TestCase):
    @staticmethod
    def _dialog(result, confirmations=None):
        destroyed = []
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = result
        dialog.coordinate_valid = True
        dialog.review_items = build_review_items(result)
        dialog.review_confirmations = dict(confirmations or {})
        workflow = DXFReviewWorkflow.__new__(DXFReviewWorkflow)
        workflow.result = dialog.result
        workflow.review_items = dialog.review_items
        workflow.review_confirmations = dialog.review_confirmations
        workflow.coordinate_valid = dialog.coordinate_valid
        dialog.review_workflow = workflow
        dialog._selected_member = lambda: None
        dialog.mode_var = _Variable("replace")
        dialog.window = SimpleNamespace(destroy=lambda: destroyed.append(True))
        dialog._build_review_state = lambda: {"saved": True}
        dialog._save_ui_state = lambda: None
        dialog.dialog_action = ""
        return dialog, destroyed

    def test_error_never_enters_optional_confirmation_flow(self):
        result = _result(
            messages=(
                ValidationMessage(
                    "error", "BLOCKED", "blocked", "strut", ("HS",), ("S1",)
                ),
            )
        )
        dialog, destroyed = self._dialog(result)

        with patch("tkinter.messagebox.askyesno") as ask:
            dialog._apply()

        ask.assert_not_called()
        self.assertEqual(dialog.dialog_action, "")
        self.assertEqual(destroyed, [])

    def test_warning_and_unconfirmed_use_one_combined_confirmation(self):
        result = _result(
            messages=(
                ValidationMessage(
                    "warning", "CHECK", "review", "strut", ("HS",), ("S1",)
                ),
            )
        )
        dialog, destroyed = self._dialog(result)

        with patch("tkinter.messagebox.askyesno", return_value=True) as ask:
            dialog._apply()

        ask.assert_called_once()
        prompt = ask.call_args.args[1]
        self.assertIn("警告：1 項", prompt)
        self.assertIn("未人工確認構件：6 個", prompt)
        self.assertEqual(dialog.dialog_action, "complete")
        self.assertEqual(destroyed, [True])

    def test_unconfirmed_without_warning_can_still_complete_after_reminder(self):
        result = _result()
        dialog, _destroyed = self._dialog(result)

        with patch("tkinter.messagebox.askyesno", return_value=True) as ask:
            dialog._apply()

        ask.assert_called_once()
        self.assertNotIn("警告：", ask.call_args.args[1])
        self.assertIn("未人工確認構件：6 個", ask.call_args.args[1])
        self.assertEqual(dialog.dialog_action, "complete")

    def test_all_confirmed_without_warning_completes_without_modal(self):
        result = _result()
        confirmations = {}
        for item in build_review_items(result):
            confirmations = confirm_review_item(result, item, confirmations)
        dialog, _destroyed = self._dialog(result, confirmations)

        with patch("tkinter.messagebox.askyesno") as ask:
            dialog._apply()

        ask.assert_not_called()
        self.assertEqual(dialog.dialog_action, "complete")

    def test_import_controls_ignore_confirmation_as_a_blocking_gate(self):
        result = _result()
        dialog, _destroyed = self._dialog(result)
        dialog.apply_button = _Button()
        dialog.status_var = _Variable()

        dialog._update_import_controls()

        self.assertEqual(dialog.apply_button.options["state"], "normal")
        self.assertEqual(
            dialog.apply_button.options["text"],
            "仍要完成匯入（取代）",
        )
        self.assertIn("未人工確認構件 6 個", dialog.status_var.get())

    def test_append_mode_is_visible_on_the_global_import_action(self):
        result = _result()
        dialog, _destroyed = self._dialog(result)
        dialog.mode_var.set("append")
        dialog.apply_button = _Button()
        dialog.status_var = _Variable()

        dialog._update_import_controls()

        self.assertEqual(
            dialog.apply_button.options["text"],
            "仍要完成匯入（附加）",
        )

    def test_error_and_critical_keep_import_button_disabled(self):
        for severity in ("error", "critical"):
            with self.subTest(severity=severity):
                result = _result(
                    messages=(
                        ValidationMessage(
                            severity,
                            "BLOCKED",
                            "blocked",
                            "strut",
                            ("HS",),
                            ("S1",),
                        ),
                    )
                )
                dialog, _destroyed = self._dialog(result)
                dialog.apply_button = _Button()
                dialog.status_var = _Variable()

                dialog._update_import_controls()

                self.assertEqual(
                    dialog.apply_button.options["state"],
                    "disabled",
                )
                self.assertEqual(
                    dialog.apply_button.options["text"],
                    "不可匯入",
                )


if __name__ == "__main__":
    unittest.main()
