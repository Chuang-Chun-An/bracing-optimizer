"""Small modal selection dialogs used by the main window."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class WalerSelectionDialog:
    def __init__(self, parent, waler_ids: list[str]):
        self.selected = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("選擇圍令")
        self.dialog.grab_set()
        self.dialog.geometry("320x140")
        self.dialog.resizable(False, False)

        label = ttk.Label(self.dialog, text="請選擇要配置的圍令：", font=(None, 12))
        label.pack(padx=12, pady=(12, 6), anchor="w")

        self.selection = tk.StringVar()
        self.combobox = ttk.Combobox(self.dialog, values=waler_ids, textvariable=self.selection, state="readonly")
        if waler_ids:
            self.combobox.set(waler_ids[0])
        self.combobox.pack(fill="x", padx=12, pady=6)

        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(padx=12, pady=12, fill="x")

        ok_btn = ttk.Button(button_frame, text="確定", command=self._on_ok)
        cancel_btn = ttk.Button(button_frame, text="取消", command=self._on_cancel)
        ok_btn.pack(side="left", expand=True, padx=6)
        cancel_btn.pack(side="left", expand=True, padx=6)

        self.dialog.bind("<Return>", lambda event: self._on_ok())
        self.dialog.bind("<Escape>", lambda event: self._on_cancel())

    def _on_ok(self):
        selection = self.selection.get().strip()
        if selection:
            self.selected = selection
        self.dialog.destroy()

    def _on_cancel(self):
        self.selected = None
        self.dialog.destroy()

    def open(self):
        self.dialog.wait_window()
        return self.selected


class ZoningSelectionDialog:
    def __init__(self, parent, zonings: list[str]):
        self.selected = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("選擇分區")
        self.dialog.grab_set()
        self.dialog.geometry("320x140")
        self.dialog.resizable(False, False)

        label = ttk.Label(
            self.dialog,
            text="請選擇要執行支撐配置的分區：",
            font=(None, 12),
        )
        label.pack(padx=12, pady=(12, 6), anchor="w")

        self.selection = tk.StringVar()
        self.combobox = ttk.Combobox(
            self.dialog,
            values=zonings,
            textvariable=self.selection,
            state="readonly",
        )
        if zonings:
            self.combobox.set(zonings[0])
        self.combobox.pack(fill="x", padx=12, pady=6)

        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(padx=12, pady=12, fill="x")
        ttk.Button(
            button_frame,
            text="確定",
            command=self._on_ok,
        ).pack(side="left", expand=True, padx=6)
        ttk.Button(
            button_frame,
            text="取消",
            command=self._on_cancel,
        ).pack(side="left", expand=True, padx=6)

        self.dialog.bind("<Return>", lambda event: self._on_ok())
        self.dialog.bind("<Escape>", lambda event: self._on_cancel())

    def _on_ok(self):
        selection = self.selection.get().strip()
        if selection:
            self.selected = selection
        self.dialog.destroy()

    def _on_cancel(self):
        self.selected = None
        self.dialog.destroy()

    def open(self):
        self.dialog.wait_window()
        return self.selected
