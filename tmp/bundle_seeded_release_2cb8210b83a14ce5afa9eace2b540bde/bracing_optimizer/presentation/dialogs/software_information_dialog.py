"""Read-only modal dialog for product and release history information."""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk

from bracing_optimizer.application.software_information import (
    HISTORY_UNAVAILABLE_MESSAGE,
    SoftwareInformation,
)


def format_history_text(information: SoftwareInformation) -> str:
    """Render history entries in source order without altering their contents."""

    if not information.history.available:
        return information.history.message or HISTORY_UNAVAILABLE_MESSAGE
    return "\n\n".join(
        f"{entry.date_label}\n{entry.record}"
        for entry in information.history.entries
    )


class SoftwareInformationDialog:
    """Modal, read-only product information window."""

    def __init__(self, parent: tk.Misc, information: SoftwareInformation):
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("軟體資訊")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.geometry("760x600")
        self.dialog.minsize(560, 420)
        self.dialog.protocol("WM_DELETE_WINDOW", self._close)
        self.dialog.bind("<Escape>", self._close)

        container = ttk.Frame(self.dialog, padding=14)
        container.pack(fill="both", expand=True)

        identity_frame = ttk.LabelFrame(container, text="軟體身分", padding=10)
        identity_frame.pack(fill="x")
        ttk.Label(
            identity_frame,
            text=f"軟體名稱：{information.identity.name}",
        ).pack(anchor="w")
        ttk.Label(
            identity_frame,
            text=f"版本：{information.identity.version}",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            identity_frame,
            text=f"作者：{information.identity.author}",
        ).pack(anchor="w", pady=(4, 0))

        ttk.Label(container, text="開發歷程").pack(
            anchor="w",
            pady=(12, 4),
        )
        self.history_text = scrolledtext.ScrolledText(
            container,
            wrap="word",
            height=22,
        )
        self.history_text.pack(fill="both", expand=True)
        self.history_text.insert("1.0", format_history_text(information))
        self.history_text.configure(state="disabled")

        ttk.Button(container, text="關閉", command=self._close).pack(
            anchor="e",
            pady=(12, 0),
        )
        self.dialog.focus_set()

    def _close(self, _event=None) -> None:
        self.dialog.destroy()

    def open(self) -> None:
        self.dialog.wait_window()


__all__ = ["SoftwareInformationDialog", "format_history_text"]
