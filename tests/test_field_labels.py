import unittest

from bracing_optimizer.presentation.field_labels import (
    build_table_column_labels,
    corner_brace_transfer_mode_label,
    dxf_entity_type_label,
    engineering_field_label,
    member_role_label,
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
        self.assertEqual(
            recognition_method_label("occluded_parallel_rails"),
            "遮蔽平行 rail 中線",
        )
        self.assertEqual(
            recognition_method_label("bim_block_whole_axis"),
            "BIM 圖塊完整構件軸",
        )
        self.assertEqual(dxf_entity_type_label("LINE"), "LINE（線）")
        self.assertIn("custom_method", recognition_method_label("custom_method"))

    def test_shared_role_and_corner_brace_transfer_labels_preserve_unknown_ids(self):
        role = "corner_brace"
        same_side = "same_side"
        mirrored = "mirrored"

        self.assertEqual(member_role_label(role), "角撐")
        self.assertEqual(corner_brace_transfer_mode_label(same_side), "同側移植")
        self.assertEqual(corner_brace_transfer_mode_label(mirrored), "鏡射移植")
        self.assertEqual(member_role_label("custom_role"), "custom_role")
        self.assertEqual(
            corner_brace_transfer_mode_label("custom_transfer"),
            "custom_transfer",
        )
        self.assertEqual(role, "corner_brace")
        self.assertEqual(same_side, "same_side")
        self.assertEqual(mirrored, "mirrored")

    def test_waler_connected_member_display_labels_are_presentation_only(self):
        self.assertEqual(
            engineering_field_label("waler", "ConnectedStrutIDs"),
            "直接連接支撐",
        )
        self.assertEqual(
            engineering_field_label("waler", "ConnectedBraceIDs"),
            "直接連接斜撐",
        )
        self.assertEqual(
            engineering_field_label("waler", "ConnectedCornerBraceIDs"),
            "直接連接角撐",
        )


if __name__ == "__main__":
    unittest.main()
