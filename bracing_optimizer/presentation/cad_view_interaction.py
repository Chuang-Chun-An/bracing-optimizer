"""Framework-neutral CAD-style mouse interaction primitives.

Tkinter Canvas and Matplotlib use different event objects and Y-axis screen
directions.  This controller owns the shared button contract, pan state,
cursor-centred zoom math, and pixel hit testing; each view only translates its
native event into plain coordinates and redraws itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


ScreenPoint = tuple[float, float]
ViewBounds = tuple[float, float, float, float]


@dataclass
class CADViewport:
    """One authoritative data-space viewport for a pixel canvas.

    ``content_bounds`` describes what was fitted. ``view_bounds`` describes
    the exact data rectangle visible inside the drawable canvas area and is
    always normalized to that area's aspect ratio.
    """

    content_bounds: ViewBounds | None = None
    view_bounds: ViewBounds | None = None
    canvas_width: float = 100.0
    canvas_height: float = 100.0
    margin: float = 0.0

    @property
    def plot_width(self) -> float:
        return max(float(self.canvas_width) - 2 * float(self.margin), 1.0)

    @property
    def plot_height(self) -> float:
        return max(float(self.canvas_height) - 2 * float(self.margin), 1.0)

    @property
    def aspect_ratio(self) -> float:
        return self.plot_width / self.plot_height

    @staticmethod
    def _normalized_input(bounds: ViewBounds) -> ViewBounds:
        min_x, max_x, min_y, max_y = map(float, bounds)
        if not all(math.isfinite(value) for value in (min_x, max_x, min_y, max_y)):
            raise ValueError("viewport bounds must be finite")
        if min_x > max_x:
            min_x, max_x = max_x, min_x
        if min_y > max_y:
            min_y, max_y = max_y, min_y
        if max_x - min_x < 1e-12:
            center_x = (min_x + max_x) / 2
            min_x, max_x = center_x - 0.5, center_x + 0.5
        if max_y - min_y < 1e-12:
            center_y = (min_y + max_y) / 2
            min_y, max_y = center_y - 0.5, center_y + 0.5
        return min_x, max_x, min_y, max_y

    def aspect_fit_bounds(self, bounds: ViewBounds) -> ViewBounds:
        """Expand one dimension symmetrically to match the canvas aspect."""

        min_x, max_x, min_y, max_y = self._normalized_input(bounds)
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        span_x = max_x - min_x
        span_y = max_y - min_y
        if span_x / span_y < self.aspect_ratio:
            span_x = span_y * self.aspect_ratio
        else:
            span_y = span_x / self.aspect_ratio
        return (
            center_x - span_x / 2,
            center_x + span_x / 2,
            center_y - span_y / 2,
            center_y + span_y / 2,
        )

    def configure(
        self,
        width: float,
        height: float,
        margin: float | None = None,
    ) -> None:
        """Update canvas geometry while preserving center and data scale."""

        old_plot_width = self.plot_width
        old_plot_height = self.plot_height
        old_bounds = self.view_bounds
        old_scale = None
        if old_bounds is not None:
            min_x, max_x, min_y, max_y = self._normalized_input(old_bounds)
            old_scale = min(
                old_plot_width / (max_x - min_x),
                old_plot_height / (max_y - min_y),
            )
        self.canvas_width = max(float(width), 1.0)
        self.canvas_height = max(float(height), 1.0)
        if margin is not None:
            self.margin = max(float(margin), 0.0)
        if old_bounds is None or old_scale is None or old_scale <= 1e-12:
            return
        center_x = (old_bounds[0] + old_bounds[1]) / 2
        center_y = (old_bounds[2] + old_bounds[3]) / 2
        span_x = self.plot_width / old_scale
        span_y = self.plot_height / old_scale
        self.view_bounds = (
            center_x - span_x / 2,
            center_x + span_x / 2,
            center_y - span_y / 2,
            center_y + span_y / 2,
        )

    def reset(self) -> None:
        self.content_bounds = None
        self.view_bounds = None

    def fit(self, content_bounds: ViewBounds) -> ViewBounds:
        self.content_bounds = self._normalized_input(content_bounds)
        self.view_bounds = self.aspect_fit_bounds(self.content_bounds)
        return self.view_bounds

    def set_view_bounds(self, bounds: ViewBounds | None) -> None:
        self.view_bounds = (
            None if bounds is None else self.aspect_fit_bounds(bounds)
        )

    @property
    def scale(self) -> float:
        if self.view_bounds is None:
            return 1.0
        min_x, max_x, min_y, max_y = self.view_bounds
        return min(
            self.plot_width / max(max_x - min_x, 1e-12),
            self.plot_height / max(max_y - min_y, 1e-12),
        )

    def scale_for_bounds(self, bounds: ViewBounds) -> float:
        min_x, max_x, min_y, max_y = self.aspect_fit_bounds(bounds)
        return min(
            self.plot_width / max(max_x - min_x, 1e-12),
            self.plot_height / max(max_y - min_y, 1e-12),
        )

    def data_to_screen(self, point: tuple[float, float]) -> ScreenPoint:
        if self.view_bounds is None:
            return float(point[0]), float(point[1])
        min_x, _max_x, min_y, _max_y = self.view_bounds
        scale = self.scale
        return (
            self.margin + (float(point[0]) - min_x) * scale,
            self.canvas_height - self.margin - (float(point[1]) - min_y) * scale,
        )

    def screen_to_data(self, point: ScreenPoint) -> tuple[float, float]:
        if self.view_bounds is None:
            return float(point[0]), float(point[1])
        min_x, _max_x, min_y, _max_y = self.view_bounds
        scale = max(self.scale, 1e-12)
        return (
            min_x + (float(point[0]) - self.margin) / scale,
            min_y + (self.canvas_height - self.margin - float(point[1])) / scale,
        )

    def zoom_at_screen(self, point: ScreenPoint, factor: float) -> ViewBounds | None:
        if self.view_bounds is None:
            return None
        anchor = self.screen_to_data(point)
        self.view_bounds = CADViewInteractionController.zoom_bounds(
            self.view_bounds,
            anchor,
            factor,
        )
        return self.view_bounds

    def recenter(self, point: tuple[float, float]) -> ViewBounds | None:
        if self.view_bounds is None:
            return None
        span_x = self.view_bounds[1] - self.view_bounds[0]
        span_y = self.view_bounds[3] - self.view_bounds[2]
        self.view_bounds = (
            float(point[0]) - span_x / 2,
            float(point[0]) + span_x / 2,
            float(point[1]) - span_y / 2,
            float(point[1]) + span_y / 2,
        )
        return self.view_bounds

    def intersects(self, points: Sequence[tuple[float, float]]) -> bool:
        if not points or self.view_bounds is None:
            return False
        min_x, max_x, min_y, max_y = self.view_bounds
        return not (
            max(point[0] for point in points) < min_x
            or min(point[0] for point in points) > max_x
            or max(point[1] for point in points) < min_y
            or min(point[1] for point in points) > max_y
        )

    @property
    def legacy_transform(self) -> tuple[float, float, float, float, float] | None:
        if self.view_bounds is None:
            return None
        return (
            self.view_bounds[0],
            self.view_bounds[2],
            self.scale,
            self.canvas_height,
            self.margin,
        )


class CADViewInteractionController:
    """Shared left-select, middle-pan, wheel-zoom interaction state."""

    SELECT_BUTTON = 1
    PAN_BUTTON = 2
    ZOOM_IN_FACTOR = 0.8
    ZOOM_OUT_FACTOR = 1.25

    def __init__(self) -> None:
        self._pan_origin_screen: ScreenPoint | None = None
        self._pan_origin_bounds: ViewBounds | None = None

    @staticmethod
    def button_number(button: object) -> int | None:
        """Normalize Tk integers and Matplotlib MouseButton values."""

        value = getattr(button, "value", button)
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def is_select_button(self, button: object) -> bool:
        return self.button_number(button) == self.SELECT_BUTTON

    def is_pan_button(self, button: object) -> bool:
        return self.button_number(button) == self.PAN_BUTTON

    @property
    def pan_active(self) -> bool:
        return self._pan_origin_screen is not None and self._pan_origin_bounds is not None

    def begin_pan(self, screen_point: ScreenPoint, bounds: ViewBounds) -> None:
        self._pan_origin_screen = (
            float(screen_point[0]),
            float(screen_point[1]),
        )
        self._pan_origin_bounds = tuple(float(value) for value in bounds)

    def pan_to(
        self,
        screen_point: ScreenPoint,
        pixels_per_data: tuple[float, float],
        *,
        y_axis_screen_down: bool,
    ) -> ViewBounds | None:
        """Return translated bounds from the original middle-button press."""

        if not self.pan_active:
            return None
        assert self._pan_origin_screen is not None
        assert self._pan_origin_bounds is not None
        scale_x = max(abs(float(pixels_per_data[0])), 1e-12)
        scale_y = max(abs(float(pixels_per_data[1])), 1e-12)
        dx_pixels = float(screen_point[0]) - self._pan_origin_screen[0]
        dy_pixels = float(screen_point[1]) - self._pan_origin_screen[1]
        shift_x = -dx_pixels / scale_x
        shift_y = (
            dy_pixels / scale_y
            if y_axis_screen_down
            else -dy_pixels / scale_y
        )
        min_x, max_x, min_y, max_y = self._pan_origin_bounds
        return (
            min_x + shift_x,
            max_x + shift_x,
            min_y + shift_y,
            max_y + shift_y,
        )

    def end_pan(self) -> None:
        self._pan_origin_screen = None
        self._pan_origin_bounds = None

    @classmethod
    def scroll_factor(cls, direction: float) -> float | None:
        if direction > 0:
            return cls.ZOOM_IN_FACTOR
        if direction < 0:
            return cls.ZOOM_OUT_FACTOR
        return None

    @staticmethod
    def zoom_bounds(
        bounds: ViewBounds,
        anchor: tuple[float, float],
        factor: float,
    ) -> ViewBounds:
        """Scale view bounds around one exact data/world-coordinate anchor."""

        min_x, max_x, min_y, max_y = bounds
        anchor_x, anchor_y = float(anchor[0]), float(anchor[1])
        factor = float(factor)
        return (
            anchor_x - (anchor_x - min_x) * factor,
            anchor_x + (max_x - anchor_x) * factor,
            anchor_y - (anchor_y - min_y) * factor,
            anchor_y + (max_y - anchor_y) * factor,
        )

    @staticmethod
    def _segment_distance(
        point: ScreenPoint,
        start: ScreenPoint,
        end: ScreenPoint,
    ) -> float:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length_squared = dx * dx + dy * dy
        if length_squared <= 1e-20:
            return math.hypot(point[0] - start[0], point[1] - start[1])
        ratio = (
            (point[0] - start[0]) * dx + (point[1] - start[1]) * dy
        ) / length_squared
        ratio = max(0.0, min(1.0, ratio))
        projected = start[0] + ratio * dx, start[1] + ratio * dy
        return math.hypot(point[0] - projected[0], point[1] - projected[1])

    @classmethod
    def nearest_segment(
        cls,
        point: ScreenPoint,
        hit_lines: Sequence[tuple[str, ScreenPoint, ScreenPoint]],
        tolerance_pixels: float = 12.0,
    ) -> str:
        if not hit_lines:
            return ""
        identifier, distance = min(
            (
                (identifier, cls._segment_distance(point, start, end))
                for identifier, start, end in hit_lines
            ),
            key=lambda item: item[1],
        )
        return identifier if distance <= tolerance_pixels else ""

    @staticmethod
    def point_hits(
        point: ScreenPoint,
        hit_points: Sequence[tuple[str, ScreenPoint]],
        tolerance_pixels: float = 10.0,
    ) -> tuple[str, ...]:
        hits = sorted(
            (
                (math.hypot(point[0] - target[0], point[1] - target[1]), identifier)
                for identifier, target in hit_points
                if math.hypot(point[0] - target[0], point[1] - target[1])
                <= tolerance_pixels
            ),
            key=lambda item: (item[0], item[1]),
        )
        return tuple(identifier for _distance, identifier in hits)
