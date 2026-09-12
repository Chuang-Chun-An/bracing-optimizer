"""Canvas rendering and incremental preview scheduling."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntFlag, auto
import time
from typing import Any, Callable, Sequence

from bracing_optimizer.presentation.cad_view_interaction import (
    CADViewInteractionController,
    CADViewport,
)

from .models import CandidatePoint


class PreviewController(CADViewInteractionController):
    """Backward-compatible name for the shared CAD interaction controller."""

    nearest_member = CADViewInteractionController.nearest_segment
    candidate_hits = CADViewInteractionController.point_hits


class RenderDirty(IntFlag):
    """Independent UI regions that can be refreshed in one idle flush."""

    NONE = 0
    FULL_SCENE = auto()
    COMPONENT_LAYER = auto()
    CANDIDATE_LAYER = auto()
    COMPONENT_SELECTION = auto()
    CANDIDATE_SELECTION = auto()
    HOVER = auto()
    TEMP_LINE = auto()
    DETAIL_PANEL = auto()
    TREE_SELECTION = auto()


@dataclass
class PerformanceDiagnostics:
    full_scene_rebuilds: int = 0
    engineering_member_rebuilds: int = 0
    candidate_layer_rebuilds: int = 0
    selection_overlay_updates: int = 0
    temporary_overlay_updates: int = 0
    candidate_tree_rebuilds: int = 0
    selection_controller_calls: int = 0
    idempotent_skips: int = 0
    canvas_item_count: int = 0
    render_pending: bool = False
    last_update_ms: dict[str, float] = field(default_factory=dict)

    def record(self, operation: str, started_at: float) -> None:
        self.last_update_ms[operation] = round(
            (time.perf_counter() - started_at) * 1000.0,
            3,
        )

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


class RenderScheduler:
    """Coalesce dirty regions and prevent nested preview drawing."""

    def __init__(
        self,
        after_idle: Callable[[Callable[[], None]], Any],
        render: Callable[[RenderDirty], None],
        diagnostics: PerformanceDiagnostics | None = None,
    ) -> None:
        self._after_idle = after_idle
        self._render = render
        self._diagnostics = diagnostics
        self._dirty = RenderDirty.NONE
        self._pending_token: Any = None
        self._drawing = False

    @property
    def dirty(self) -> RenderDirty:
        return self._dirty

    @property
    def pending(self) -> bool:
        return self._pending_token is not None

    def request(self, dirty: RenderDirty) -> None:
        if dirty == RenderDirty.NONE:
            return
        self._dirty |= dirty
        if self._diagnostics is not None:
            self._diagnostics.render_pending = True
        if self._drawing or self._pending_token is not None:
            return
        self._pending_token = self._after_idle(self.flush)

    def flush(self) -> None:
        self._pending_token = None
        if self._drawing:
            self.request(self._dirty)
            return
        dirty = self._dirty
        if dirty == RenderDirty.NONE:
            if self._diagnostics is not None:
                self._diagnostics.render_pending = False
            return
        self._dirty = RenderDirty.NONE
        self._drawing = True
        try:
            self._render(dirty)
        finally:
            self._drawing = False
            if self._dirty != RenderDirty.NONE:
                self.request(self._dirty)
            elif self._diagnostics is not None:
                self._diagnostics.render_pending = False


@dataclass
class PreviewScene:
    """Canvas item index; model objects never live in this view-only layer."""

    source_geometry_items: list[int] = field(default_factory=list)
    auxiliary_geometry_items: list[int] = field(default_factory=list)
    component_items: dict[str, list[int]] = field(default_factory=dict)
    candidate_point_items: dict[str, int] = field(default_factory=dict)
    selection_items: dict[str, int] = field(default_factory=dict)
    temporary_line_items: list[int] = field(default_factory=list)
    axis_items: list[int] = field(default_factory=list)
    source_handle_items: dict[str, list[int]] = field(default_factory=dict)
    item_to_component: dict[int, str] = field(default_factory=dict)
    item_to_candidate_point: dict[int, str] = field(default_factory=dict)

    def clear(self) -> None:
        self.source_geometry_items.clear()
        self.auxiliary_geometry_items.clear()
        self.component_items.clear()
        self.candidate_point_items.clear()
        self.selection_items.clear()
        self.temporary_line_items.clear()
        self.axis_items.clear()
        self.source_handle_items.clear()
        self.item_to_component.clear()
        self.item_to_candidate_point.clear()

    def clear_layer(self, layer: str) -> None:
        if layer == "engineering_members":
            for item_ids in self.component_items.values():
                for item_id in item_ids:
                    self.item_to_component.pop(item_id, None)
            self.component_items.clear()
        elif layer == "candidate_overlay":
            for item_id in self.candidate_point_items.values():
                self.item_to_candidate_point.pop(item_id, None)
            self.candidate_point_items.clear()
        elif layer == "selection_overlay":
            self.selection_items.clear()
        elif layer == "temporary_overlay":
            self.temporary_line_items.clear()
        elif layer == "source_geometry":
            self.source_geometry_items.clear()
            self.source_handle_items.clear()
        elif layer == "auxiliary_geometry":
            self.auxiliary_geometry_items.clear()
        elif layer == "coordinate_axis":
            self.axis_items.clear()


class PreviewRenderer:
    """Small Canvas drawing boundary with stable layer tags and ID indexes."""

    LAYERS = (
        "source_geometry",
        "auxiliary_geometry",
        "engineering_members",
        "candidate_overlay",
        "selection_overlay",
        "temporary_overlay",
        "coordinate_axis",
    )

    def __init__(self, canvas: Any, scene: PreviewScene) -> None:
        self.canvas = canvas
        self.scene = scene

    @staticmethod
    def _tags(layer: str, extra_tags: Sequence[str]) -> tuple[str, ...]:
        return tuple(dict.fromkeys((layer, *map(str, extra_tags))))

    def clear(self) -> None:
        self.canvas.delete("all")
        self.scene.clear()

    def delete_layer(self, layer: str) -> None:
        self.canvas.delete(layer)
        self.scene.clear_layer(layer)

    def _register(
        self,
        item_id: int,
        layer: str,
        *,
        component_id: str = "",
        candidate_point_id: str = "",
        source_handle: str = "",
        overlay_key: str = "",
    ) -> int:
        if layer == "source_geometry":
            self.scene.source_geometry_items.append(item_id)
        elif layer == "auxiliary_geometry":
            self.scene.auxiliary_geometry_items.append(item_id)
        elif layer == "engineering_members" and component_id:
            self.scene.component_items.setdefault(component_id, []).append(item_id)
            self.scene.item_to_component[item_id] = component_id
        elif layer == "candidate_overlay" and candidate_point_id:
            self.scene.candidate_point_items[candidate_point_id] = item_id
            self.scene.item_to_candidate_point[item_id] = candidate_point_id
        elif layer == "selection_overlay" and overlay_key:
            self.scene.selection_items[overlay_key] = item_id
        elif layer == "temporary_overlay":
            self.scene.temporary_line_items.append(item_id)
        elif layer == "coordinate_axis":
            self.scene.axis_items.append(item_id)
        if source_handle:
            self.scene.source_handle_items.setdefault(source_handle, []).append(
                item_id
            )
        return item_id

    def create_line(
        self,
        layer: str,
        *coordinates: float,
        component_id: str = "",
        candidate_point_id: str = "",
        source_handle: str = "",
        overlay_key: str = "",
        extra_tags: Sequence[str] = (),
        **options: Any,
    ) -> int:
        options["tags"] = self._tags(layer, extra_tags)
        item_id = self.canvas.create_line(*coordinates, **options)
        return self._register(
            item_id,
            layer,
            component_id=component_id,
            candidate_point_id=candidate_point_id,
            source_handle=source_handle,
            overlay_key=overlay_key,
        )

    def create_oval(
        self,
        layer: str,
        *coordinates: float,
        candidate_point_id: str = "",
        overlay_key: str = "",
        extra_tags: Sequence[str] = (),
        **options: Any,
    ) -> int:
        options["tags"] = self._tags(layer, extra_tags)
        item_id = self.canvas.create_oval(*coordinates, **options)
        return self._register(
            item_id,
            layer,
            candidate_point_id=candidate_point_id,
            overlay_key=overlay_key,
        )

    def create_text(
        self,
        layer: str,
        *coordinates: float,
        component_id: str = "",
        source_handle: str = "",
        overlay_key: str = "",
        extra_tags: Sequence[str] = (),
        **options: Any,
    ) -> int:
        options["tags"] = self._tags(layer, extra_tags)
        item_id = self.canvas.create_text(*coordinates, **options)
        return self._register(
            item_id,
            layer,
            component_id=component_id,
            source_handle=source_handle,
            overlay_key=overlay_key,
        )

    def create_rectangle(
        self,
        layer: str,
        *coordinates: float,
        overlay_key: str = "",
        extra_tags: Sequence[str] = (),
        **options: Any,
    ) -> int:
        options["tags"] = self._tags(layer, extra_tags)
        item_id = self.canvas.create_rectangle(*coordinates, **options)
        return self._register(
            item_id,
            layer,
            overlay_key=overlay_key,
        )


class TreeSelectionSynchronizer:
    """Suppress delayed virtual events produced by programmatic selection."""

    def __init__(
        self,
        tree: Any,
        after_idle: Callable[[Callable[[], None]], Any],
    ) -> None:
        self.tree = tree
        self._after_idle = after_idle
        self._generation = 0
        self._active_generation = 0

    @property
    def syncing(self) -> bool:
        return self._active_generation != 0

    def select(self, iid: str) -> bool:
        if not iid or not self.tree.exists(iid):
            return False
        if tuple(self.tree.selection()) == (iid,):
            self.tree.focus(iid)
            self.tree.see(iid)
            return False
        self._generation += 1
        generation = self._generation
        self._active_generation = generation
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)

        def finish() -> None:
            if self._active_generation == generation:
                self._active_generation = 0

        self._after_idle(finish)
        return True


class CandidateTreeAdapter:
    """Incremental, ID-only projection of the canonical candidate store."""

    def __init__(
        self,
        tree: Any,
        after_idle: Callable[[Callable[[], None]], Any],
    ) -> None:
        self.tree = tree
        self.selection_sync = TreeSelectionSynchronizer(tree, after_idle)
        self.point_id_by_iid: dict[str, str] = {}
        self.iid_by_point_id: dict[str, str] = {}
        self.component_id = ""
        self.hovered_point_id = ""
        self.rebuild_count = 0

    @property
    def syncing(self) -> bool:
        return self.selection_sync.syncing

    def rebuild(
        self,
        component_id: str,
        points: Sequence[CandidatePoint],
        row_values: Callable[[CandidatePoint], Sequence[Any]],
        predicate: Callable[[CandidatePoint], bool] | None = None,
    ) -> None:
        self.tree.delete(*self.tree.get_children())
        self.point_id_by_iid.clear()
        self.iid_by_point_id.clear()
        self.component_id = component_id
        self.hovered_point_id = ""
        for point in points:
            if predicate is not None and not predicate(point):
                continue
            iid = f"candidate::{component_id}::{point.id}"
            self.tree.insert("", "end", iid=iid, values=tuple(row_values(point)))
            self.point_id_by_iid[iid] = point.id
            self.iid_by_point_id[point.id] = iid
        self.rebuild_count += 1

    def point_id_for_iid(self, iid: str) -> str:
        return self.point_id_by_iid.get(iid, "")

    def sync_selection(self, point_id: str) -> bool:
        return self.selection_sync.select(self.iid_by_point_id.get(point_id, ""))

    def update_row(
        self,
        point_id: str,
        values: Sequence[Any],
    ) -> None:
        iid = self.iid_by_point_id.get(point_id, "")
        if iid and self.tree.exists(iid):
            self.tree.item(iid, values=tuple(values))

    def set_hover(self, point_id: str) -> None:
        if point_id == self.hovered_point_id:
            return
        self.tree.tag_configure("hover", background="#ffe0b2")
        previous_iid = self.iid_by_point_id.get(self.hovered_point_id, "")
        if previous_iid and self.tree.exists(previous_iid):
            self.tree.item(previous_iid, tags=())
        self.hovered_point_id = point_id
        iid = self.iid_by_point_id.get(point_id, "")
        if iid and self.tree.exists(iid):
            self.tree.item(iid, tags=("hover",))
