"""Matplotlib toolbar customized for the project preview."""

from __future__ import annotations

import math

from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk


class PreviewNavigationToolbar(NavigationToolbar2Tk):
    """現場圖面只保留全圖與匯出；滑鼠互動由共用控制器處理。"""

    toolitems = (
        ("全圖", "回到完整圖面", "home", "home"),
        ("儲存", "儲存圖片", "filesave", "save_figure"),
    )

    def __init__(
        self,
        canvas,
        window=None,
        *,
        pack_toolbar=True,
        export_callback=None,
        zoom_getter=None,
    ):
        self.export_callback = export_callback
        self.zoom_getter = zoom_getter
        self._zoom_percent = 100.0
        self._base_message = ""
        super().__init__(canvas, window, pack_toolbar=pack_toolbar)

    @staticmethod
    def _format_zoom_percent(percent):
        if math.isclose(percent, round(percent), abs_tol=0.05):
            return f"{int(round(percent))}%"
        return f"{percent:.1f}%"

    def set_zoom_percent(self, percent):
        self._zoom_percent = float(percent)
        self._refresh_message()

    def sync_zoom_display(self):
        if self.zoom_getter is not None:
            self.set_zoom_percent(self.zoom_getter())

    def set_message(self, message):
        self._base_message = message
        self._refresh_message()

    def _refresh_message(self):
        percent = self._zoom_percent
        if self.zoom_getter is not None:
            percent = float(self.zoom_getter())
            self._zoom_percent = percent
        zoom_text = self._format_zoom_percent(percent)
        prefix = f"{self._base_message}   " if self._base_message else ""
        if hasattr(self, "message"):
            self.message.set(f"{prefix}倍率={zoom_text}")

    def home(self, *args):
        super().home(*args)
        self.after_idle(self.sync_zoom_display)

    def pan(self, *args):
        """Left-button pan is intentionally disabled; middle drag owns Pan."""

        return None

    def zoom(self, *args):
        """Rectangle zoom is disabled so the left button always means Select."""

        return None

    def save_figure(self, *args):
        if self.export_callback is not None:
            return self.export_callback()
        return super().save_figure(*args)
