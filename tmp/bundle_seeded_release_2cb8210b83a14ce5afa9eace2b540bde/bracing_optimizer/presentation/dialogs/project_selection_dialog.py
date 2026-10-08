"""Modal Project selection dialog for the main-window Open command."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Iterable
from tkinter import ttk


class ProjectSelectionDialog:
    """Return one repository Project name without performing navigation."""

    def __init__(
        self,
        parent,
        project_names: Iterable[str],
        current_name: str | None = None,
    ) -> None:
        self.project_names = tuple(str(name) for name in project_names)
        self.selected: str | None = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("開啟專案")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.geometry("420x320")
        self.dialog.minsize(360, 260)

        body = ttk.Frame(self.dialog, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="請選擇要開啟的專案：").pack(anchor="w")

        list_frame = ttk.Frame(body)
        list_frame.pack(fill="both", expand=True, pady=(8, 10))
        self.listbox = tk.Listbox(
            list_frame,
            selectmode="browse",
            exportselection=False,
        )
        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.listbox.yview,
        )
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for name in self.project_names:
            self.listbox.insert("end", name)

        if not self.project_names:
            ttk.Label(
                body,
                text="目前沒有可開啟的專案。",
                foreground="#616161",
            ).pack(anchor="w", pady=(0, 8))

        button_frame = ttk.Frame(body)
        button_frame.pack(fill="x")
        self.open_button = ttk.Button(
            button_frame,
            text="開啟",
            command=self._confirm,
            state="disabled",
        )
        self.open_button.pack(side="right", padx=(6, 0))
        ttk.Button(
            button_frame,
            text="取消",
            command=self._cancel,
        ).pack(side="right")

        self.listbox.bind("<<ListboxSelect>>", self._sync_open_state)
        self.listbox.bind("<Double-Button-1>", self._confirm)
        self.dialog.bind("<Return>", self._confirm)
        self.dialog.bind("<Escape>", self._cancel)
        self.dialog.protocol("WM_DELETE_WINDOW", self._cancel)

        initial_index = 0 if self.project_names else None
        if current_name in self.project_names:
            initial_index = self.project_names.index(current_name)
        if initial_index is not None:
            self.listbox.selection_set(initial_index)
            self.listbox.activate(initial_index)
            self.listbox.see(initial_index)
        self._sync_open_state()

    def _sync_open_state(self, _event=None) -> None:
        state = "normal" if self.listbox.curselection() else "disabled"
        self.open_button.configure(state=state)

    def _confirm(self, _event=None) -> None:
        selection = self.listbox.curselection()
        if not selection:
            self._sync_open_state()
            return
        self.selected = str(self.listbox.get(selection[0]))
        self.dialog.destroy()

    def _cancel(self, _event=None) -> None:
        self.selected = None
        self.dialog.destroy()

    def open(self) -> str | None:
        self.dialog.wait_window()
        return self.selected
