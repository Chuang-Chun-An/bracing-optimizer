from __future__ import annotations

import inspect
import unittest
from unittest.mock import MagicMock, call, patch

from bracing_optimizer.presentation.dialogs import project_selection_dialog
from bracing_optimizer.presentation.dialogs.project_selection_dialog import (
    ProjectSelectionDialog,
)


class ProjectSelectionDialogTests(unittest.TestCase):
    def build_dialog(self, names=(), current_name=None, selection=()):
        top_level = MagicMock()
        listbox = MagicMock()
        listbox.curselection.return_value = selection
        open_button = MagicMock()
        cancel_button = MagicMock()
        with (
            patch.object(
                project_selection_dialog.tk,
                "Toplevel",
                return_value=top_level,
            ),
            patch.object(
                project_selection_dialog.tk,
                "Listbox",
                return_value=listbox,
            ),
            patch.object(project_selection_dialog.ttk, "Frame"),
            patch.object(project_selection_dialog.ttk, "Label"),
            patch.object(project_selection_dialog.ttk, "Scrollbar"),
            patch.object(
                project_selection_dialog.ttk,
                "Button",
                side_effect=(open_button, cancel_button),
            ),
        ):
            dialog = ProjectSelectionDialog(
                object(),
                names,
                current_name=current_name,
            )
        return dialog, top_level, listbox, open_button

    def test_names_are_copied_and_empty_dialog_keeps_open_disabled(self):
        source_names = []
        dialog, _, listbox, open_button = self.build_dialog(source_names)
        source_names.append("late")

        self.assertEqual(dialog.project_names, ())
        listbox.insert.assert_not_called()
        open_button.configure.assert_called_with(state="disabled")

    def test_current_name_is_initial_selection(self):
        dialog, _, listbox, open_button = self.build_dialog(
            ["Alpha", "Beta"],
            current_name="Beta",
            selection=(1,),
        )

        self.assertEqual(dialog.project_names, ("Alpha", "Beta"))
        self.assertEqual(
            listbox.insert.call_args_list,
            [call("end", "Alpha"), call("end", "Beta")],
        )
        listbox.selection_set.assert_called_once_with(1)
        listbox.activate.assert_called_once_with(1)
        open_button.configure.assert_called_with(state="normal")

    def test_confirm_cancel_and_open_return_only_the_selection(self):
        dialog, top_level, listbox, _ = self.build_dialog(
            ["Alpha", "Beta"],
            selection=(1,),
        )
        listbox.get.return_value = "Beta"

        dialog._confirm()
        self.assertEqual(dialog.selected, "Beta")
        top_level.destroy.assert_called_once_with()

        top_level.reset_mock()
        dialog._cancel()
        self.assertIsNone(dialog.selected)
        top_level.destroy.assert_called_once_with()

        dialog.selected = "Alpha"
        self.assertEqual(dialog.open(), "Alpha")
        top_level.wait_window.assert_called_once_with()

    def test_keyboard_double_click_and_window_close_share_handlers(self):
        dialog, top_level, listbox, _ = self.build_dialog(
            ["Alpha"],
            selection=(0,),
        )

        listbox.bind.assert_has_calls(
            [
                call("<<ListboxSelect>>", dialog._sync_open_state),
                call("<Double-Button-1>", dialog._confirm),
            ]
        )
        top_level.bind.assert_has_calls(
            [
                call("<Return>", dialog._confirm),
                call("<Escape>", dialog._cancel),
            ]
        )
        top_level.protocol.assert_called_once_with(
            "WM_DELETE_WINDOW",
            dialog._cancel,
        )

    def test_dialog_has_no_filesystem_or_navigation_responsibility(self):
        source = inspect.getsource(ProjectSelectionDialog)

        self.assertNotIn("Path(", source)
        self.assertNotIn("load_project", source)
        self.assertNotIn("guard_unsaved", source)


if __name__ == "__main__":
    unittest.main()
