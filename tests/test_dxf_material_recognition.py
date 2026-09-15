from __future__ import annotations

from dataclasses import replace
import unittest

from dxf_import.material_recognition import (
    recognize_material_spec_from_width,
    recognize_result_material_specs,
    restore_manual_material_specs_from_debug,
    section_plan_width_mm,
    set_member_material_spec,
)
from dxf_import.models import DXFImportResult, Strut, Waler


MATERIAL_SPECS = (
    {"Usage": "圍令", "Spec": "RC"},
    {"Usage": "圍令", "Spec": "H350x350"},
    {"Usage": "圍令", "Spec": "H400x408"},
    {"Usage": "支撐", "Spec": "H350x350"},
    {"Usage": "支撐", "Spec": "H414x405"},
)


def _result() -> DXFImportResult:
    waler = Waler(
        "W1", (0.0, 0.0), (1000.0, 0.0), "WALER", ("W-H",),
        ("LWPOLYLINE",), "inner_boundary_line", False, 408.0, 0.99,
    )
    strut = Strut(
        "S1", (500.0, 0.0), (500.0, 1000.0), "STRUT", ("S-H",),
        ("LWPOLYLINE",), "closed_outline_axis", True, 350.0,
        "W1", "", 0.99,
    )
    return DXFImportResult(
        source_path="C:/drawing/material.dxf",
        layer_names=(),
        selected_layers={},
        layer_info=(),
        walers=(waler,),
        struts=(strut,),
        braces=(),
        entity_debug=(),
        messages=(),
        source_entity_counts={},
    )


class DxfMaterialRecognitionTests(unittest.TestCase):
    def test_h_section_uses_second_dimension_as_plan_width(self):
        self.assertEqual(section_plan_width_mm("H400x408x21x21"), 408.0)
        self.assertEqual(section_plan_width_mm("H-414×405"), 405.0)
        self.assertIsNone(section_plan_width_mm("RC"))

    def test_unique_width_match_is_scoped_by_usage(self):
        self.assertEqual(
            recognize_material_spec_from_width(408.4, "圍令", MATERIAL_SPECS),
            "H400x408",
        )
        recognized = recognize_result_material_specs(_result(), MATERIAL_SPECS)
        self.assertEqual(recognized.walers[0].material_spec, "H400x408")
        self.assertEqual(recognized.struts[0].material_spec, "H350x350")
        self.assertEqual(recognized.walers[0].material_spec_source, "auto_width")

    def test_ambiguous_or_unknown_width_is_not_guessed(self):
        ambiguous = (
            {"Usage": "支撐", "Spec": "H400x405"},
            {"Usage": "支撐", "Spec": "H414x405"},
        )
        self.assertEqual(
            recognize_material_spec_from_width(405, "支撐", ambiguous),
            "",
        )
        self.assertEqual(
            recognize_material_spec_from_width(0, "支撐", MATERIAL_SPECS),
            "",
        )

    def test_manual_choice_enters_project_rows_without_changing_geometry(self):
        recognized = recognize_result_material_specs(_result(), MATERIAL_SPECS)
        before = recognized.struts[0].start, recognized.struts[0].end
        updated = set_member_material_spec(recognized, "S1", "H414x405")
        self.assertEqual((updated.struts[0].start, updated.struts[0].end), before)
        self.assertEqual(updated.struts[0].material_spec_source, "manual")
        self.assertEqual(
            updated.to_project_rows()["struts"][0]["material_spec"],
            "H414x405",
        )
        self.assertEqual(
            updated.to_project_rows()["walers"][0]["material_spec"],
            "H400x408",
        )

    def test_same_source_restores_only_manual_choice_by_source_handle(self):
        recognized = recognize_result_material_specs(_result(), MATERIAL_SPECS)
        manual = set_member_material_spec(recognized, "W1", "H350x350")
        rebuilt = recognize_result_material_specs(
            replace(_result(), walers=(replace(_result().walers[0], id="W9"),)),
            MATERIAL_SPECS,
        )
        restored = restore_manual_material_specs_from_debug(
            rebuilt,
            manual.to_debug_dict(),
            MATERIAL_SPECS,
        )
        self.assertEqual(restored.walers[0].id, "W9")
        self.assertEqual(restored.walers[0].material_spec, "H350x350")
        self.assertEqual(restored.walers[0].material_spec_source, "manual")

        cleared = set_member_material_spec(recognized, "W1", "")
        restored_clear = restore_manual_material_specs_from_debug(
            recognized,
            cleared.to_debug_dict(),
            MATERIAL_SPECS,
        )
        self.assertEqual(restored_clear.walers[0].material_spec, "")
        self.assertEqual(restored_clear.walers[0].material_spec_source, "manual")


if __name__ == "__main__":
    unittest.main()
