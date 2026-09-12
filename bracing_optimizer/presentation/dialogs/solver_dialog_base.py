"""Shared Tk main-thread bridge and text writer for Solver dialogs."""

from __future__ import annotations

import queue
import tkinter as tk


def _text_is_at_bottom(text_widget, tolerance: float = 0.001) -> bool:
    try:
        return text_widget.yview()[1] >= 1.0 - tolerance
    except (tk.TclError, IndexError):
        return True


class TextRedirector:
    def __init__(self, text_widget, poll_interval: int = 50):
        self.text_widget = text_widget
        self._queue = queue.Queue()
        self._poll_interval = poll_interval
        try:
            self.text_widget.after(self._poll_interval, self._flush_queue)
        except tk.TclError:
            pass

    def write(self, message):
        if not message:
            return
        self._queue.put(message)

    def _flush_queue(self):
        try:
            messages = []
            while True:
                try:
                    messages.append(self._queue.get_nowait())
                except queue.Empty:
                    break

            if messages:
                follow_new_output = _text_is_at_bottom(self.text_widget)
                self.text_widget.configure(state="normal")
                self.text_widget.insert("end", "".join(messages))
                if follow_new_output:
                    self.text_widget.see("end")
                self.text_widget.configure(state="disabled")
            self.text_widget.after(self._poll_interval, self._flush_queue)
        except tk.TclError:
            pass

    def flush(self):
        pass


class SolverDialogThreadBridge:
    """Queue worker results so only the Tk main thread touches widgets."""

    dialog: tk.Toplevel

    def _initialize_ui_bridge(self):
        self._closed = False
        self._ui_queue = queue.Queue()
        self.dialog.after(50, self._poll_ui_queue)

    def _post_ui(self, callback):
        if not self._closed:
            self._ui_queue.put(callback)

    def _poll_ui_queue(self):
        if self._closed:
            return
        try:
            while True:
                try:
                    callback = self._ui_queue.get_nowait()
                except queue.Empty:
                    break
                if not self._closed:
                    callback()
            if not self._closed and self.dialog.winfo_exists():
                self.dialog.after(50, self._poll_ui_queue)
        except tk.TclError:
            self._closed = True

    def _close_ui_bridge(self):
        self._closed = True
        try:
            while True:
                self._ui_queue.get_nowait()
        except queue.Empty:
            pass
