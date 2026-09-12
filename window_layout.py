"""Shared helpers for keeping Tk windows inside the usable desktop area."""

from __future__ import annotations

import os
import re
from typing import Any, Sequence


WorkArea = tuple[int, int, int, int]
_WINDOW_GEOMETRY_PATTERN = re.compile(
    r"^\s*(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?\s*$"
)


def _parse_window_geometry(
    geometry: str,
) -> tuple[int, int, int | None, int | None] | None:
    match = _WINDOW_GEOMETRY_PATTERN.fullmatch(str(geometry or ""))
    if match is None:
        return None
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        return None
    x = int(match.group(3)) if match.group(3) is not None else None
    y = int(match.group(4)) if match.group(4) is not None else None
    return width, height, x, y


def fit_window_geometry_to_work_areas(
    requested: str,
    fallback: str,
    work_areas: Sequence[WorkArea],
) -> str:
    """Keep a remembered Tk window rectangle fully inside an active monitor."""

    parsed = _parse_window_geometry(requested) or _parse_window_geometry(fallback)
    usable_areas = tuple(
        area
        for area in work_areas
        if area[2] > area[0] and area[3] > area[1]
    )
    if parsed is None or not usable_areas:
        return fallback

    width, height, x, y = parsed
    if x is None or y is None:
        fallback_parsed = _parse_window_geometry(fallback)
        if (
            fallback_parsed is not None
            and fallback_parsed[2] is not None
            and fallback_parsed[3] is not None
        ):
            x, y = fallback_parsed[2], fallback_parsed[3]
        else:
            left, top, right, bottom = usable_areas[0]
            x = left + max((right - left - width) // 2, 0)
            y = top + max((bottom - top - height) // 2, 0)

    assert x is not None and y is not None

    def intersection_area(area: WorkArea) -> int:
        left, top, right, bottom = area
        overlap_width = max(0, min(x + width, right) - max(x, left))
        overlap_height = max(0, min(y + height, bottom) - max(y, top))
        return overlap_width * overlap_height

    intersecting = max(usable_areas, key=intersection_area)
    if intersection_area(intersecting) > 0:
        target = intersecting
    else:
        center_x = x + width / 2
        center_y = y + height / 2

        def distance_to_area(area: WorkArea) -> float:
            left, top, right, bottom = area
            dx = max(left - center_x, 0.0, center_x - right)
            dy = max(top - center_y, 0.0, center_y - bottom)
            return dx * dx + dy * dy

        target = min(usable_areas, key=distance_to_area)

    left, top, right, bottom = target
    available_width = right - left
    available_height = bottom - top
    width = min(width, available_width)
    height = min(height, available_height)
    x = min(max(x, left), right - width)
    y = min(max(y, top), bottom - height)

    def offset(value: int) -> str:
        return f"+{value}" if value >= 0 else str(value)

    return f"{width}x{height}{offset(x)}{offset(y)}"


def _active_monitor_work_areas(window: Any) -> tuple[WorkArea, ...]:
    """Return active monitor work areas, including negative monitor positions."""

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class MonitorInfo(ctypes.Structure):
                _fields_ = (
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                )

            monitors: list[tuple[bool, WorkArea]] = []
            callback_type = ctypes.WINFUNCTYPE(
                wintypes.BOOL,
                wintypes.HANDLE,
                wintypes.HDC,
                ctypes.POINTER(wintypes.RECT),
                wintypes.LPARAM,
            )
            user32 = ctypes.windll.user32

            @callback_type
            def collect_monitor(
                monitor: Any,
                _device_context: Any,
                _monitor_rect: Any,
                _data: Any,
            ) -> bool:
                info = MonitorInfo()
                info.cbSize = ctypes.sizeof(MonitorInfo)
                if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    work = info.rcWork
                    monitors.append(
                        (
                            bool(info.dwFlags & 1),
                            (
                                int(work.left),
                                int(work.top),
                                int(work.right),
                                int(work.bottom),
                            ),
                        )
                    )
                return True

            user32.EnumDisplayMonitors(None, None, collect_monitor, 0)
            if monitors:
                monitors.sort(key=lambda item: not item[0])
                return tuple(area for _is_primary, area in monitors)
        except (AttributeError, OSError, TypeError, ValueError):
            pass

    try:
        left = int(window.winfo_vrootx())
        top = int(window.winfo_vrooty())
        width = int(window.winfo_vrootwidth())
        height = int(window.winfo_vrootheight())
        if width > 0 and height > 0:
            return ((left, top, left + width, top + height),)
    except Exception:
        pass
    return ((0, 0, 1920, 1080),)


def responsive_dialog_geometry(
    preferred_width: int,
    preferred_height: int,
    work_areas: Sequence[WorkArea],
    *,
    anchor_geometry: str | None = None,
    horizontal_chrome_allowance: int = 48,
    vertical_chrome_allowance: int = 72,
) -> str:
    """Size and center a dialog while reserving room for window decorations."""

    usable_areas = tuple(
        area
        for area in work_areas
        if area[2] > area[0] and area[3] > area[1]
    ) or ((0, 0, 1920, 1080),)
    anchor = _parse_window_geometry(anchor_geometry or "")

    target = usable_areas[0]
    if anchor is not None and anchor[2] is not None and anchor[3] is not None:
        anchor_width, anchor_height, anchor_x, anchor_y = anchor
        assert anchor_x is not None and anchor_y is not None

        def anchor_overlap(area: WorkArea) -> int:
            left, top, right, bottom = area
            return max(
                0,
                min(anchor_x + anchor_width, right) - max(anchor_x, left),
            ) * max(
                0,
                min(anchor_y + anchor_height, bottom) - max(anchor_y, top),
            )

        target = max(usable_areas, key=anchor_overlap)

    left, top, right, bottom = target
    available_width = right - left
    available_height = bottom - top
    width = min(
        max(int(preferred_width), 1),
        max(available_width - int(horizontal_chrome_allowance), 1),
    )
    height = min(
        max(int(preferred_height), 1),
        max(available_height - int(vertical_chrome_allowance), 1),
    )
    x = left + max((available_width - width) // 2, 0)
    y = top + max((available_height - height) // 2, 0)

    def offset(value: int) -> str:
        return f"+{value}" if value >= 0 else str(value)

    return f"{width}x{height}{offset(x)}{offset(y)}"


def configure_responsive_dialog(
    dialog: Any,
    parent: Any,
    *,
    preferred_width: int,
    preferred_height: int,
    minimum_width: int,
    minimum_height: int,
) -> str:
    """Apply a safe initial size and an attainable minimum size to a dialog."""

    try:
        anchor_geometry = parent.winfo_toplevel().geometry()
    except Exception:
        anchor_geometry = None
    geometry = responsive_dialog_geometry(
        preferred_width,
        preferred_height,
        _active_monitor_work_areas(parent),
        anchor_geometry=anchor_geometry,
    )
    parsed = _parse_window_geometry(geometry)
    assert parsed is not None
    width, height, _x, _y = parsed
    dialog.geometry(geometry)
    dialog.minsize(min(int(minimum_width), width), min(int(minimum_height), height))
    dialog.resizable(True, True)
    return geometry
