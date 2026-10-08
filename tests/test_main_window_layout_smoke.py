from __future__ import annotations

import tkinter as tk
import unittest
from types import SimpleNamespace

from bracing_optimizer.infrastructure.project_persistence import DxfStatus
from main import SupportInputApp


class MainWindowLayoutSmokeTests(unittest.TestCase):
    def test_supported_window_sizes_keep_workspace_and_retained_toolbars_visible(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.addCleanup(root.destroy)
        app = SupportInputApp(root)

        self.assertFalse(hasattr(app, "project_case_selector"))
        self.assertFalse(hasattr(app, "project_quick_status_var"))
        self.assertTrue(hasattr(app, "context_toolbar"))
        self.assertTrue(hasattr(app, "preview_toolbar"))
        self.assertEqual(
            tuple(app.workspace_tab_labels.values()),
            ("工程配置", "材料設定", "分析結果"),
        )
        self.assertEqual(
            tuple(app.table_tab_labels.values()),
            ("圍令", "支撐", "斜撐", "機料庫存", "材料規格"),
        )

        def menu_labels():
            return tuple(
                app.menu_bar.entrycget(index, "label")
                for index in range(int(app.menu_bar.index("end")) + 1)
            )

        self.assertEqual(menu_labels(), ("檔案", "專案", "說明"))
        app.dxf_asset_status_report = SimpleNamespace(
            status=DxfStatus.RUNTIME_READY
        )
        app._sync_main_menu_projection()
        self.assertEqual(menu_labels(), ("檔案", "專案 待儲存", "說明"))
        app.dxf_asset_status_report = SimpleNamespace(status=DxfStatus.MISSING)
        app._sync_main_menu_projection()
        self.assertEqual(menu_labels(), ("檔案", "專案 ⚠", "說明"))

        for notebook in (
            app.notebook,
            app.engineering_notebook,
            app.materials_notebook,
            app.analysis_notebook,
        ):
            self.assertEqual(notebook.cget("style"), "")

        for geometry in ("900x600", "1024x768"):
            with self.subTest(geometry=geometry):
                root.geometry(geometry)
                root.update()
                self.assertGreater(app.main_paned.winfo_height(), 1)
                self.assertTrue(app.context_toolbar.winfo_ismapped())

        try:
            root.state("zoomed")
            root.update()
        except tk.TclError:
            root.attributes("-zoomed", True)
            root.update()
        self.assertGreater(app.main_paned.winfo_height(), 1)
        self.assertTrue(app.context_toolbar.winfo_ismapped())


if __name__ == "__main__":
    unittest.main()
