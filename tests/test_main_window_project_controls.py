from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import main
from bracing_optimizer.infrastructure.project_persistence import DxfStatus
from main import SupportInputApp


class MainMenuWiringTests(unittest.TestCase):
    def build_app(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = MagicMock()
        app.projection_stale = False
        app._refresh_project_status_display = MagicMock()
        app._update_project_action_states = MagicMock()
        return app

    def test_menu_order_labels_handlers_and_shortcuts(self):
        app = self.build_app()
        menu_bar, file_menu, project_menu, help_menu = (
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
        menu_bar.index.return_value = 1
        with (
            patch.object(
                main.tk,
                "Menu",
                side_effect=(menu_bar, file_menu, project_menu, help_menu),
            ) as menu_factory,
            patch.object(main.tk, "StringVar", return_value=MagicMock()),
            patch.object(main.ttk, "Frame") as frame,
        ):
            app._build_project_menu_and_toolbar()

        self.assertEqual(menu_factory.call_args_list[0], call(app.root, tearoff=False))
        menu_bar.index.assert_called_once_with("end")
        self.assertEqual(app.project_menu_index, 1)
        self.assertEqual(
            [item.kwargs["label"] for item in menu_bar.add_cascade.call_args_list],
            ["檔案", "專案", "說明"],
        )
        file_commands = [
            item.kwargs
            for item in file_menu.add_command.call_args_list
        ]
        self.assertEqual(
            [item["label"] for item in file_commands],
            ["新建專案", "開啟專案…", "儲存專案", "另存新專案…", "結束"],
        )
        self.assertEqual(
            [item.get("accelerator") for item in file_commands],
            ["Ctrl+N", "Ctrl+O", "Ctrl+S", "Ctrl+Shift+S", None],
        )
        self.assertEqual(
            [item["command"] for item in file_commands],
            [
                app._new_project,
                app._load_selected_project_case,
                app._save_current_project,
                app._save_project_as,
                app._on_main_window_close,
            ],
        )
        self.assertEqual(file_menu.add_separator.call_count, 2)
        self.assertEqual(
            [item.kwargs["label"] for item in project_menu.add_command.call_args_list],
            ["專案與 DXF 狀態…", "重新連結 DXF…", "刪除目前專案…"],
        )
        self.assertEqual(project_menu.add_separator.call_count, 2)
        help_menu.add_command.assert_called_once_with(
            label="軟體資訊",
            command=app._show_software_information,
        )
        self.assertEqual(
            [item.args[0] for item in app.root.bind.call_args_list],
            [
                "<Control-n>",
                "<Control-o>",
                "<Control-s>",
                "<Control-Shift-S>",
            ],
        )
        frame.assert_not_called()

    def test_removed_toolbar_does_not_remove_workspace_toolbars_or_tab_names(self):
        menu_source = inspect.getsource(
            SupportInputApp._build_project_menu_and_toolbar
        )
        ui_source = inspect.getsource(SupportInputApp._build_ui)

        for removed in (
            "project_case_selector",
            "open_project_button",
            "reproject_button",
            "project_quick_status_var",
        ):
            self.assertNotIn(removed, menu_source)
        self.assertIn("self.context_toolbar = ttk.Frame", ui_source)
        self.assertIn("PreviewNavigationToolbar", inspect.getsource(main))
        for label in (
            "工程配置",
            "材料設定",
            "分析結果",
            "支撐",
            "圍令",
            "斜撐",
            "DXF 批次匯入",
            "CAD 新增構件",
        ):
            self.assertIn(label, inspect.getsource(SupportInputApp))


class MainShortcutScopeTests(unittest.TestCase):
    def build_app(self, focus_root):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = MagicMock()
        focus_widget = MagicMock()
        focus_widget.winfo_toplevel.return_value = focus_root(app)
        app.root.focus_get.return_value = focus_widget
        app.projection_stale = False
        return app

    def test_root_and_inline_focus_invoke_shared_handler_and_return_break(self):
        app = self.build_app(lambda app: app.root)
        handler = MagicMock()

        result = app._invoke_project_shortcut(object(), "save", handler)

        self.assertEqual(result, "break")
        handler.assert_called_once_with()

    def test_child_toplevel_focus_does_not_trigger_or_intercept_commands(self):
        for child_kind in (
            "DXF Review",
            "Support Solver",
            "Waler Solver",
            "other Toplevel",
        ):
            child = object()
            app = self.build_app(lambda _app: child)
            for command_name in ("new", "open", "save", "save_as"):
                with self.subTest(child=child_kind, command=command_name):
                    handler = MagicMock()
                    result = app._invoke_project_shortcut(
                        object(),
                        command_name,
                        handler,
                    )
                    self.assertIsNone(result)
                    handler.assert_not_called()

    def test_disabled_main_command_is_not_invoked(self):
        app = self.build_app(lambda app: app.root)
        app.projection_stale = True
        handler = MagicMock()

        result = app._invoke_project_shortcut(object(), "save", handler)

        self.assertEqual(result, "break")
        handler.assert_not_called()

    def test_shortcut_implementation_never_uses_bind_all(self):
        source = inspect.getsource(SupportInputApp._bind_project_shortcuts)
        self.assertNotIn("bind_all", source)


class ProjectMenuProjectionTests(unittest.TestCase):
    def test_every_dxf_status_has_the_approved_project_label(self):
        warning = {
            DxfStatus.MANAGED_COPY_MODIFIED,
            DxfStatus.SOURCE_MODIFIED,
            DxfStatus.MISSING,
            DxfStatus.RELINK_REQUIRED,
            DxfStatus.BINDING_REQUIRED,
            DxfStatus.LEGACY_NO_STATE,
            DxfStatus.INCOMPATIBLE,
            DxfStatus.GEOMETRY_COMPATIBLE,
        }
        pending = {
            DxfStatus.RUNTIME_READY,
            DxfStatus.VERIFIED_PENDING_SAVE,
        }
        self.assertEqual(set(DxfStatus), warning | pending | {
            DxfStatus.READY,
            DxfStatus.NO_DXF,
        })

        for status in DxfStatus:
            with self.subTest(status=status):
                app = SupportInputApp.__new__(SupportInputApp)
                app.dxf_asset_status_report = SimpleNamespace(status=status)
                app.project_dirty = False
                expected = (
                    "專案 ⚠"
                    if status in warning
                    else "專案 待儲存"
                    if status in pending
                    else "專案"
                )
                self.assertEqual(app._project_menu_label(), expected)
                app.project_dirty = True
                self.assertEqual(app._project_menu_label(), expected)

        app = SupportInputApp.__new__(SupportInputApp)
        app.dxf_asset_status_report = None
        self.assertEqual(app._project_menu_label(), "專案")

    def test_pending_save_label_does_not_depend_on_dirty(self):
        for status in (
            DxfStatus.RUNTIME_READY,
            DxfStatus.VERIFIED_PENDING_SAVE,
        ):
            with self.subTest(status=status):
                app = SupportInputApp.__new__(SupportInputApp)
                app.dxf_asset_status_report = SimpleNamespace(status=status)
                app.project_dirty = False
                self.assertEqual(app._project_menu_label(), "專案 待儲存")

    def test_menu_state_and_recovery_command_follow_formal_state(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.menu_bar = MagicMock()
        app.file_menu = MagicMock()
        app.project_menu = MagicMock()
        app.project_menu_index = 7
        app.dxf_asset_status_report = SimpleNamespace(status=DxfStatus.READY)
        app.current_project_path = Path("project_cases/current/project.json")
        app._validated_current_project_target = MagicMock(
            return_value=(app.current_project_path, True)
        )
        app.projection_stale = False
        app._reprojection_menu_visible = False

        app._sync_main_menu_projection()

        app.menu_bar.entryconfigure.assert_called_with(7, label="專案")
        self.assertEqual(app.menu_bar.insert_command.call_count, 0)
        self.assertIn(
            call("刪除目前專案…", state="normal"),
            app.project_menu.entryconfigure.call_args_list,
        )

        app.projection_stale = True
        app._sync_main_menu_projection()
        app._sync_main_menu_projection()

        app.menu_bar.insert_command.assert_called_once_with(
            8,
            label="⚠ 重新整理畫面",
            command=app._reproject_all_from_committed_state,
        )
        for label in ("新建專案", "開啟專案…", "儲存專案", "另存新專案…"):
            self.assertIn(
                call(label, state="disabled"),
                app.file_menu.entryconfigure.call_args_list,
            )
        self.assertIn(
            call("專案與 DXF 狀態…", state="normal"),
            app.project_menu.entryconfigure.call_args_list,
        )
        self.assertIn(
            call("重新連結 DXF…", state="disabled"),
            app.project_menu.entryconfigure.call_args_list,
        )
        self.assertIn(
            call("刪除目前專案…", state="disabled"),
            app.project_menu.entryconfigure.call_args_list,
        )

        app.projection_stale = False
        app._sync_main_menu_projection()
        app.menu_bar.delete.assert_called_once_with(8)

    def test_window_title_projection_does_not_create_quick_status(self):
        source = inspect.getsource(SupportInputApp._refresh_project_status_display)
        self.assertNotIn("project_quick_status_var", source)


class WorkspaceNotebookStyleTests(unittest.TestCase):
    def test_main_and_nested_notebooks_use_native_default_style(self):
        source = inspect.getsource(SupportInputApp._build_ui)
        results_source = inspect.getsource(SupportInputApp._create_results_tab)

        self.assertIn("ttk.Notebook(self.left_frame)", source)
        self.assertIn("ttk.Notebook(self.engineering_workspace)", source)
        self.assertIn("ttk.Notebook(self.materials_workspace)", source)
        self.assertIn("ttk.Notebook(parent)", results_source)
        self.assertNotIn("Primary.TNotebook", inspect.getsource(main))
        self.assertNotIn("Secondary.TNotebook", inspect.getsource(main))
        self.assertNotIn("Notebook.tab", inspect.getsource(main))
        self.assertNotIn("theme_use", source)


if __name__ == "__main__":
    unittest.main()
