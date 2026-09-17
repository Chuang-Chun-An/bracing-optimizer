import unittest

from bracing_optimizer.presentation.field_labels import (
    build_table_column_labels,
    dxf_entity_type_label,
    engineering_field_label,
    recognition_method_label,
)


class SharedFieldLabelTests(unittest.TestCase):
    def test_main_table_labels_are_returned_as_independent_copies(self):
        first = build_table_column_labels()
        second = build_table_column_labels()

        self.assertEqual(first["struts"]["StrutID"], "支撐編號")
        self.assertEqual(first["inventory"]["Qty"], "庫存數量")
        first["struts"]["StrutID"] = "changed"
        self.assertEqual(second["struts"]["StrutID"], "支撐編號")

    def test_dxf_engineering_labels_reuse_project_field_vocabulary(self):
        self.assertEqual(engineering_field_label("strut", "StartX"), "起點X")
        self.assertEqual(
            engineering_field_label("column", "PrimaryAssociatedStrutID"),
            "主要關聯支撐",
        )
        self.assertEqual(engineering_field_label("beam", "ID"), "托梁編號")
        self.assertEqual(
            engineering_field_label("corner_brace", "Length"),
            "構件長度（mm）",
        )

    def test_technical_display_values_are_chinese_without_changing_ids(self):
        self.assertEqual(recognition_method_label("existing_centerline"), "既有中心線")
        self.assertEqual(dxf_entity_type_label("LINE"), "LINE（線）")
        self.assertIn("custom_method", recognition_method_label("custom_method"))


if __name__ == "__main__":
    unittest.main()
