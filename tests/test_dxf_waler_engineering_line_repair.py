from __future__ import annotations

from dataclasses import replace
import math
import unittest

from dxf_import.models import (
    DXFImportError,
    DXFImportResult,
    ValidationMessage,
    Waler,
)
from dxf_import.waler_engineering_line_repair import (
    WALER_REPAIR_REPLACED_DIAGNOSTIC_CODES,
    formalize_waler_engineering_line,
    replace_waler_engineering_line_diagnostics,
)


def _waler(**changes):
    values = dict(
        id="W14",
        start=(0.0, 0.0),
        end=(1000.0, 0.0),
        source_layer="WALER",
        source_handles=("58d",),
        source_entity_types=("LWPOLYLINE",),
        recognition_method="closed_outline_axis",
        centerline_computed=True,
        source_width=400.0,
        confidence=0.9,
        contact_face_state="provisional",
        source_width_state="unique",
    )
    values.update(changes)
    return Waler(**values)


def _result(waler=None, messages=()):
    return DXFImportResult(
        source_path="Y29.dxf",
        layer_names=("WALER",),
        selected_layers={"waler": ("WALER",)},
        layer_info=(),
        walers=(waler or _waler(),),
        struts=(),
        braces=(),
        entity_debug=(),
        messages=tuple(messages),
        source_entity_counts={},
    )


class WalerEngineeringLineRepairTests(unittest.TestCase):
    def test_candidate_and_cad_lines_share_formalization_semantics(self):
        for input_kind in ("manual_candidate_points", "cad_manual"):
            with self.subTest(input_kind=input_kind):
                staged = formalize_waler_engineering_line(
                    _result(),
                    ("58D",),
                    (20.0, 30.0),
                    (1020.0, 30.0),
                    input_kind=input_kind,
                    selected_candidate_id="line_1",
                )

                repaired = staged.walers[0]
                self.assertEqual(repaired.world_start, (20.0, 30.0))
                self.assertEqual(repaired.world_end, (1020.0, 30.0))
                self.assertEqual(repaired.contact_face_state, "formal")
                self.assertEqual(repaired.engineering_line_authority, "manual_repair")
                self.assertEqual(repaired.selection_source, input_kind)
                self.assertEqual(
                    staged.waler_contact_reviews[0].baseline_contact_start,
                    (20.0, 30.0),
                )

    def test_line_need_not_match_envelope_or_differ_from_provisional_axis(self):
        staged = formalize_waler_engineering_line(
            _result(),
            ("58D",),
            (0.0, 0.0),
            (1000.0, 0.0),
            input_kind="manual_candidate_points",
        )

        self.assertEqual(staged.walers[0].world_start, (0.0, 0.0))
        self.assertEqual(staged.walers[0].engineering_line_authority, "manual_repair")

    def test_manual_formal_waler_can_be_atomically_replaced(self):
        first = formalize_waler_engineering_line(
            _result(),
            ("58D",),
            (0.0, 50.0),
            (1000.0, 50.0),
            input_kind="cad_manual",
        )
        second = formalize_waler_engineering_line(
            first,
            ("58d",),
            (0.0, 75.0),
            (1000.0, 75.0),
            input_kind="cad_manual",
        )

        self.assertEqual(second.walers[0].world_start, (0.0, 75.0))
        self.assertEqual(len(second.walers), 1)

    def test_ineligible_or_invalid_input_leaves_original_unchanged(self):
        original = _result(
            _waler(contact_face_state="formal", engineering_line_authority="automatic")
        )
        for start, end in (
            ((0.0, 0.0), (1000.0, 0.0)),
            ((math.nan, 0.0), (1000.0, 0.0)),
        ):
            with self.subTest(start=start):
                with self.assertRaises(DXFImportError):
                    formalize_waler_engineering_line(
                        original,
                        ("58D",),
                        start,
                        end,
                        input_kind="cad_manual",
                    )
                self.assertEqual(original.walers[0].engineering_line_authority, "automatic")

    def test_only_exact_identity_allowlisted_diagnostics_are_removed(self):
        messages = [
            ValidationMessage("error", code, code, "waler", ("58d",))
            for code in WALER_REPAIR_REPLACED_DIAGNOSTIC_CODES
        ]
        preserved = (
            ValidationMessage(
                "error", "WALER_ENVELOPE_AMBIGUOUS", "composite", "waler", ("58D", "AA")
            ),
            ValidationMessage(
                "error", "WALER_CONTACT_FACE_UNRESOLVED", "other", "waler", ("59A",)
            ),
            ValidationMessage(
                "warning", "WALER_SOURCE_OVERLAP", "overlap", "waler", ("58D",)
            ),
            ValidationMessage(
                "error", "WALER_OVERLAP_COMPETITION", "competition", "waler", ("58D",)
            ),
            ValidationMessage(
                "error", "AMBIGUOUS_WALER_CONNECTION", "connection", "strut", ("58D",)
            ),
        )

        surviving_messages = replace_waler_engineering_line_diagnostics(
            (*messages, *preserved),
            ("58D",),
        )

        surviving = {(item.code, item.message) for item in surviving_messages}
        for item in preserved:
            self.assertIn((item.code, item.message), surviving)
        self.assertFalse(
            any(
                item.code in WALER_REPAIR_REPLACED_DIAGNOSTIC_CODES
                and item.message == item.code
                for item in surviving_messages
            )
        )

    def test_nonunique_width_clears_only_auto_material(self):
        for material_source, expected in (
            ("auto_width", ("", "")),
            ("manual", ("H400", "manual")),
        ):
            with self.subTest(material_source=material_source):
                staged = formalize_waler_engineering_line(
                    _result(
                        _waler(
                            source_width=0.0,
                            source_width_state="ambiguous",
                            material_spec="H400",
                            material_spec_source=material_source,
                        )
                    ),
                    ("58D",),
                    (0.0, 50.0),
                    (1000.0, 50.0),
                    input_kind="cad_manual",
                )
                self.assertEqual(
                    (
                        staged.walers[0].material_spec,
                        staged.walers[0].material_spec_source,
                    ),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
