import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from bracing_optimizer.infrastructure.inventory_repository import (
    INVENTORY_COLUMNS,
    InMemoryInventoryRepository,
    JsonInventoryRepository,
)
from tools.inventory_conversion import convert_source_rows
from main import SupportInputApp, UNLIMITED_INVENTORY_QTY
from bracing_optimizer.application.project_data import (
    DEFAULT_MATERIAL_SPECS,
    ProjectDataModel,
)
from bracing_optimizer.application.solver_input_builder import InventoryLookup


class InventoryRepositoryTests(unittest.TestCase):
    def test_json_repository_normalizes_full_inventory_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "inventory.json"
            path.write_text(json.dumps({
                "inventory": [{
                    "機料編號": "MAT-001",
                    "規格": "H350x350",
                    "用途": "支撐",
                    "長度": 9500,
                    "數量": 12,
                }]
            }, ensure_ascii=False), encoding="utf-8")

            rows = JsonInventoryRepository(path).list_items()

        self.assertEqual(tuple(rows[0]), INVENTORY_COLUMNS)
        self.assertEqual(rows[0], {
            "ItemCode": "MAT-001",
            "Spec": "H350x350",
            "Usage": "支撐",
            "Length": 9500,
            "Qty": 12,
        })

    def test_repository_interface_can_be_replaced_without_solver_changes(self):
        repository = InMemoryInventoryRepository([{
            "ItemCode": "W-01",
            "Spec": "H400x400",
            "Usage": "圍令",
            "Length": 8000,
            "Qty": 3,
        }])
        self.assertEqual(repository.list_items()[0]["ItemCode"], "W-01")

    def test_packaged_inventory_json_has_all_required_columns(self):
        path = Path(__file__).resolve().parents[1] / "data" / "inventory.json"
        rows = JsonInventoryRepository(path).list_items()
        self.assertTrue(rows)
        self.assertTrue(all(tuple(row) == INVENTORY_COLUMNS for row in rows))
        self.assertTrue(all(row["ItemCode"] for row in rows))
        self.assertTrue(all(row["Spec"] for row in rows))
        self.assertTrue(all(row["Usage"] in ("支撐", "圍令") for row in rows))

    def test_packaged_inventory_matches_converted_source_summary(self):
        path = Path(__file__).resolve().parents[1] / "data" / "inventory.json"
        payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["source"]["total_rows"], 326)
        self.assertEqual(payload["source"]["included_rows"], 229)
        self.assertEqual(payload["source"]["excluded_adjustment_blocks"], 28)
        self.assertEqual(payload["source"]["excluded_unrelated_rows"], 69)
        self.assertEqual(len(payload["inventory"]), 229)

    def test_default_material_catalog_covers_every_packaged_inventory_spec(self):
        path = Path(__file__).resolve().parents[1] / "data" / "inventory.json"
        rows = JsonInventoryRepository(path).list_items()
        catalog = {(row["Usage"], row["Spec"]) for row in DEFAULT_MATERIAL_SPECS}
        inventory_specs = {(row["Usage"], row["Spec"]) for row in rows}

        self.assertLessEqual(inventory_specs, catalog)

    def test_conversion_keeps_only_beam_bodies_and_normalizes_units(self):
        payload = convert_source_rows([
            {
                "機料編號": "S-001",
                "品名規格": "H400*408 L=4.5M 支撐樑",
                "總數": 7,
            },
            {
                "機料編號": "W-001",
                "品名規格": "H458*417 L=8.5M 圍令樑",
                "倉庫數量": 1,
                "工務所數量": 2,
                "工務所SITE數量": 3,
                "總數": None,
            },
            {
                "機料編號": "SHIM-001",
                "品名規格": "H400*400 L=0.1M 支撐樑(調整塊)",
                "總數": 99,
            },
            {
                "機料編號": "JACK-001",
                "品名規格": "200噸油壓千斤頂",
                "總數": 20,
            },
        ], source_file="source.json")

        self.assertEqual(payload["inventory"], [
            {
                "ItemCode": "S-001",
                "Spec": "H400x408",
                "Usage": "支撐",
                "Length": 4500,
                "Qty": 7,
            },
            {
                "ItemCode": "W-001",
                "Spec": "H458x417",
                "Usage": "圍令",
                "Length": 8500,
                "Qty": 6,
            },
        ])
        self.assertEqual(payload["source"]["excluded_adjustment_blocks"], 1)
        self.assertEqual(payload["source"]["excluded_unrelated_rows"], 1)


class InventorySettingsQueryTests(unittest.TestCase):
    def app(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.project_data = ProjectDataModel(inventory=[
            {
                "ItemCode": "S-45",
                "Spec": "H350x350",
                "Usage": "支撐",
                "Length": 4500,
                "Qty": 2,
            },
            {
                "ItemCode": "S-50",
                "Spec": "H350x350",
                "Usage": "支撐",
                "Length": 5000,
                "Qty": 0,
            },
            {
                "ItemCode": "W-80",
                "Spec": "H350x350",
                "Usage": "圍令",
                "Length": 8000,
                "Qty": 7,
            },
            {
                "ItemCode": "S-90",
                "Spec": "H400x400",
                "Usage": "支撐",
                "Length": 9000,
                "Qty": 5,
            },
        ])
        return app

    def test_spec_and_usage_filter_purchasable_lengths_and_stock(self):
        app = self.app()
        inventory = InventoryLookup(app.project_data.inventory)

        self.assertEqual(
            inventory.purchasable_lengths("H350x350", "支撐"),
            [4500, 5000],
        )
        self.assertEqual(
            inventory.purchasable_lengths("H350x350", "圍令"),
            [8000],
        )
        self.assertEqual(inventory.stock_items("H350x350", "支撐"), [{
            "id": "S-45",
            "length": 4500,
            "qty": 2,
        }])

    def test_unspecified_spec_uses_unlimited_quantity_99(self):
        app = self.app()
        inventory = InventoryLookup(app.project_data.inventory)

        self.assertEqual(
            app._inventory_quantity("", "支撐", 4500),
            UNLIMITED_INVENTORY_QTY,
        )
        stock = inventory.stock_items("", "支撐")
        self.assertTrue(stock)
        self.assertTrue(all(item["qty"] == 99 for item in stock))

    def test_selected_spec_never_reads_other_spec_or_usage_quantity(self):
        app = self.app()
        self.assertEqual(
            app._inventory_quantity("H350x350", "支撐", 4500),
            2,
        )
        self.assertEqual(
            app._inventory_quantity("H350x350", "支撐", 8000),
            0,
        )
        self.assertEqual(
            app._inventory_quantity("H400x400", "支撐", 9000),
            5,
        )

    def test_unspecified_spec_material_summary_displays_99(self):
        app = self.app()
        app._collect_visible_material_usage = lambda: Counter({
            ("支撐", "", 4500): 3,
        })

        summary = app._build_material_summary_payload()

        self.assertEqual(summary[0]["inventory_qty"], 99)
        self.assertEqual(summary[0]["remaining_qty"], 99)

    def test_component_specs_use_readonly_choices(self):
        app = self.app()
        app.project_data.replace_table("material_specs", [
            {"Usage": "圍令", "Spec": "RC"},
            {"Usage": "圍令", "Spec": "H350x350"},
            {"Usage": "支撐", "Spec": "H350x350"},
        ])

        waler_specs, waler_state = app._cell_editor_options(
            "walers", "material_spec", 0
        )
        strut_specs, strut_state = app._cell_editor_options(
            "struts", "material_spec", 0
        )
        self.assertEqual(waler_state, "readonly")
        self.assertEqual(waler_specs, ("", "RC", "H350x350"))
        self.assertEqual(strut_state, "readonly")
        self.assertEqual(strut_specs, ("", "H350x350"))


if __name__ == "__main__":
    unittest.main()
