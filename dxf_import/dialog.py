"""Tkinter dialog for reviewing and applying DXF imports."""

from __future__ import annotations

import copy
import json
import os
import time
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from bracing_optimizer.presentation.cad_view_interaction import CADViewport

from .candidate_points import (
    CandidatePointStore,
    add_cad_candidate_points,
    apply_candidate_point_selection,
    rebuild_component_associations,
)
from .controllers import ImportModelController, SelectionController
from .geometry import Point, _distance, _midpoint
from .importer import DXFImporter, default_layer_mapping_for_file
from .models import (
    AuxiliaryComponent,
    Beam,
    Brace,
    CandidatePoint,
    Column,
    CoordinateSystem,
    CornerBrace,
    DXFImportError,
    DXFImportResult,
    ERROR_SEVERITIES,
    ExcludedSource,
    ProblemRecord,
    ReviewItem,
    SelectionState,
    SourceGeometry,
    SourceText,
    Strut,
    ValidationOverviewItem,
    Waler,
    apply_coordinate_system,
    coordinate_system_from_candidate,
)
from .preview import (
    CandidateTreeAdapter,
    PerformanceDiagnostics,
    PreviewController,
    PreviewRenderer,
    PreviewScene,
    RenderDirty,
    RenderScheduler,
    TreeSelectionSynchronizer,
)
from .validation import (
    build_problem_records,
    build_review_items,
    build_validation_overview,
    problem_severity_rank,
    review_item_guidance,
    validate_candidate_point_pair,
)
from .support_pairing import (
    DoubleSupportSourceIdentity,
    apply_double_support_decisions,
    double_support_candidate_identity,
    double_support_decisions_from_review_state,
    preserve_double_support_result_decisions,
    serialize_double_support_decisions,
    set_double_support_candidate_accepted,
)
from .material_recognition import (
    material_spec_options,
)
from .waler_contact_adjustment import (
    WalerContactAdjustmentPlan,
    format_adjustment_plan,
)
from .source_exclusion import (
    ManualReplayReport,
    canonical_source_identity,
    capture_manual_overrides,
    excluded_source_from_review_item,
    exclusions_from_review_state,
    manual_overrides_from_review_state,
    normalize_excluded_sources,
    normalize_source_handles,
    replay_manual_overrides,
    result_member_counts,
    result_severity_counts,
    review_state_matches_source,
    shared_handle_conflicts,
)
from window_layout import (
    WorkArea,
    _active_monitor_work_areas,
    _parse_window_geometry,
    fit_window_geometry_to_work_areas,
)


@dataclass(frozen=True)
class DXFImportDialogOutcome:
    """Explicit boundary between pausing review and completing an import."""

    action: str
    review_state: dict[str, Any]
    import_mode: str
    result: DXFImportResult | None = None
    world_result: DXFImportResult | None = None


class DXFImportDialog:
    """Engineer-oriented import summary, issue list, location and preview UI."""

    @property
    def preview_view_bounds(self) -> tuple[float, float, float, float] | None:
        viewport = getattr(self, "preview_viewport", None)
        return None if viewport is None else viewport.view_bounds

    @preview_view_bounds.setter
    def preview_view_bounds(
        self,
        bounds: tuple[float, float, float, float] | None,
    ) -> None:
        viewport = getattr(self, "preview_viewport", None)
        if viewport is not None:
            viewport.set_view_bounds(bounds)

    LAYER_USE_OPTIONS = (
        "圍令",
        "支撐",
        "斜撐",
        "中間柱",
        "托梁",
        "角撐",
        "連續壁",
        "輔助線",
        "忽略",
    )
    USE_TO_ROLE = {
        "圍令": "waler",
        "支撐": "strut",
        "斜撐": "brace",
        "中間柱": "column",
        "托梁": "beam",
        "角撐": "corner_brace",
        "連續壁": "continuous_wall",
        "輔助線": "auxiliary",
        "忽略": "ignore",
    }
    ROLE_TO_USE = {role: label for label, role in USE_TO_ROLE.items()}
    LEVEL_COLORS = {
        "success": "#2e7d32",
        "info": "#1565c0",
        "warning": "#9a6700",
        "error": "#c62828",
        "critical": "#8e0000",
    }
    LEVEL_ICONS = {"success": "✓", "info": "ℹ", "warning": "⚠", "error": "✗", "critical": "✗"}

    @property
    def selected_member_id(self) -> str:
        return self.selection_state.selected_component_id

    @classmethod
    def _initial_layer_use(
        cls,
        layer: str,
        saved_classification: Mapping[str, Any],
        default_mapping: Mapping[str, str] | None = None,
    ) -> str:
        if layer in saved_classification:
            saved_role = str(saved_classification[layer])
            return cls.ROLE_TO_USE.get(saved_role, "忽略")
        return (default_mapping or {}).get(layer, "忽略")

    @staticmethod
    def _saved_classification_matches_file(
        file_path: str | Path,
        initial_state: Mapping[str, Any],
    ) -> bool:
        saved_path = str(initial_state.get("source_path", "") or "").strip()
        if not saved_path:
            return True
        saved_name = saved_path.replace("\\", "/").rsplit("/", 1)[-1]
        current_name = str(file_path).replace("\\", "/").rsplit("/", 1)[-1]
        return saved_name.casefold() == current_name.casefold()

    @staticmethod
    def _coordinate_system_from_review_state(
        state: Mapping[str, Any] | None,
    ) -> CoordinateSystem:
        if not isinstance(state, Mapping):
            return CoordinateSystem()
        raw = state.get("coordinate_system")
        if not isinstance(raw, Mapping):
            return CoordinateSystem()
        mode = str(raw.get("mode", "world") or "world").strip().lower()
        try:
            return CoordinateSystem(
                mode=mode,
                origin_x=float(raw.get("origin_x", 0.0) or 0.0),
                origin_y=float(raw.get("origin_y", 0.0) or 0.0),
                source=str(raw.get("source", "cad_world") or "cad_world"),
            )
        except (TypeError, ValueError) as exc:
            raise DXFImportError(
                "保存的 DXF Review 座標設定格式錯誤，無法繼續。"
            ) from exc

    @staticmethod
    def _ui_state_path() -> Path:
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        return base / "SupportDistributionUV" / "dxf_import_ui_state.json"

    @classmethod
    def _load_ui_state(cls) -> dict[str, Any]:
        try:
            payload = json.loads(cls._ui_state_path().read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _restore_visible_geometry(
        window: Any,
        requested: str,
        fallback: str,
    ) -> str:
        geometry = fit_window_geometry_to_work_areas(
            requested,
            fallback,
            _active_monitor_work_areas(window),
        )
        try:
            window.geometry(geometry)
            return geometry
        except Exception:
            window.geometry(fallback)
            return fallback

    def __init__(
        self,
        parent: Any,
        file_path: str | Path,
        initial_state: Mapping[str, Any] | None = None,
        cad_event_watcher: Any = None,
        material_specs: Sequence[Mapping[str, Any]] = (),
        restore_saved_layer_classification: bool | None = None,
        resume_review: bool = False,
        initial_world_result: DXFImportResult | None = None,
        allow_pause: bool = True,
    ):
        import tkinter as tk
        from tkinter import scrolledtext, ttk

        from bracing_optimizer.infrastructure.cad_builder import (
            DEFAULT_TEMP_PATH,
            TempEventWatcher,
        )

        self.tk = tk
        self.ttk = ttk
        self.file_path = Path(file_path)
        self.default_layer_mapping = default_layer_mapping_for_file(self.file_path)
        self.initial_state = dict(initial_state or {})
        self.restore_saved_layer_classification = (
            self._saved_classification_matches_file(
                self.file_path,
                self.initial_state,
            )
            if restore_saved_layer_classification is None
            else bool(restore_saved_layer_classification)
        )
        self.material_specs = tuple(
            dict(row) for row in material_specs if isinstance(row, Mapping)
        )
        self.ui_state = self._load_ui_state()
        self.cad_event_watcher = cad_event_watcher or TempEventWatcher(
            DEFAULT_TEMP_PATH
        )
        self.importer = DXFImporter(file_path).read()
        self.resume_review = bool(resume_review)
        self.allow_pause = bool(allow_pause)
        self._initial_state_matches_source = review_state_matches_source(
            self.initial_state,
            self.importer.source_fingerprint,
            self.file_path,
        )
        if self.resume_review and not self._initial_state_matches_source:
            raise DXFImportError(
                "此專案保存的 DXF Review 使用的是不同版本的 DXF。"
                "為避免人工修正套用到錯誤來源，目前無法直接繼續此 Review。"
            )
        restore_decision = exclusions_from_review_state(
            self.initial_state,
            self.importer.source_fingerprint,
        )
        self.excluded_sources: tuple[ExcludedSource, ...] = (
            restore_decision.excluded_sources
        )
        self.exclusion_fingerprint_mismatch = (
            restore_decision.fingerprint_mismatch
        )
        self._exclusion_fingerprint_notice_shown = False
        self.result: DXFImportResult | None = None
        self.world_result: DXFImportResult | None = (
            initial_world_result
            if (
                initial_world_result is not None
                and str(initial_world_result.source_fingerprint).strip().upper()
                == str(self.importer.source_fingerprint).strip().upper()
            )
            else None
        )
        self.dialog_action = ""
        self.review_state: dict[str, Any] = {}
        self.double_support_decisions: dict[
            DoubleSupportSourceIdentity,
            bool,
        ] = (
            double_support_decisions_from_review_state(self.initial_state)
            if self._initial_state_matches_source
            else {}
        )
        self.waler_adjustment_preview_plan: WalerContactAdjustmentPlan | None = None
        self._waler_adjustment_overlay_items: list[int] = []
        self._contact_panel_waler_id = ""
        self.coordinate_valid = False
        saved_coordinate = self._coordinate_system_from_review_state(
            self.initial_state
            if self._initial_state_matches_source
            else None
        )
        self.selected_origin_world: Point | None = (
            (saved_coordinate.origin_x, saved_coordinate.origin_y)
            if saved_coordinate.mode == "local"
            else None
        )
        saved_import_mode = str(
            self.initial_state.get("import_mode", "replace")
            if self._initial_state_matches_source
            else "replace"
        ).strip().lower()
        self.import_mode = (
            saved_import_mode
            if saved_import_mode in {"replace", "append"}
            else "replace"
        )
        self.problem_records: tuple[ProblemRecord, ...] = ()
        self.problem_record_by_iid: dict[str, ProblemRecord] = {}
        self.selected_problem: ProblemRecord | None = None
        self.review_items: tuple[ReviewItem, ...] = ()
        self.review_item_by_key: dict[str, ReviewItem] = {}
        self.review_item_by_tree_iid: dict[str, str] = {}
        self.selected_review_item_key = ""
        self.detail_problem_record_by_iid: dict[str, ProblemRecord] = {}
        self.focus_member_ids: set[str] = set()
        self.focus_handles: set[str] = set()
        self.selection_state = SelectionState()
        self.member_by_tree_iid: dict[str, str] = {}
        self.member_tree_iid_by_member_id: dict[str, str] = {}
        self._updating_member_tree = False
        self.preview_viewport = CADViewport()
        self.preview_view_bounds: tuple[float, float, float, float] | None = None
        self.preview_fit_all = True
        self.preview_interaction = PreviewController()
        self.preview_transform: tuple[float, float, float, float, float] | None = None
        self.canvas_member_hit_lines: list[
            tuple[str, tuple[float, float], tuple[float, float]]
        ] = []
        self.canvas_candidate_hit_points: list[tuple[str, Point]] = []
        self.preview_scene = PreviewScene()
        self.preview_renderer: PreviewRenderer | None = None
        self.preview_window: Any = None
        self._last_normal_geometry = str(
            self.ui_state.get("main_geometry", "1180x930")
        )
        self._last_preview_geometry = str(
            self.ui_state.get("preview_geometry", "1100x800+80+80")
        )
        self.developer_expanded = False
        self.preview_cursor_var = tk.StringVar(value="游標：—")
        self.preview_coordinate_var = tk.StringVar(value="Coordinate System：尚未套用")
        self.preview_selected_member_var = tk.StringVar(value="目前構件：—")
        self.show_source_var = tk.BooleanVar(
            value=bool(self.ui_state.get("show_source", True))
        )
        self.show_auxiliary_var = tk.BooleanVar(
            value=bool(self.ui_state.get("show_auxiliary", True))
        )
        self.performance_diagnostics_enabled_var = tk.BooleanVar(
            value=bool(self.ui_state.get("performance_diagnostics", False))
        )
        self.performance_diagnostics_var = tk.StringVar(value="效能診斷：未啟用")
        self.cad_temp_status_var = tk.StringVar(value="請先選取構件，再由 CAD 指定工程線。")

        self.window = tk.Toplevel(parent)
        self.window.title("DXF 匯入與工程模型檢核")
        self._last_normal_geometry = self._restore_visible_geometry(
            self.window,
            self._last_normal_geometry,
            "1180x930",
        )
        self.window.minsize(920, 680)
        self.window.resizable(True, True)
        self.window.protocol("WM_DELETE_WINDOW", self._close_dialog)
        self.window.bind("<Configure>", self._on_main_window_configure)
        self.window.bind("<Escape>", self._cancel_active_pick)
        self.performance_diagnostics = PerformanceDiagnostics()
        self.candidate_point_store = CandidatePointStore(
            min(
                self.importer.tolerances.duplicate_tolerance_mm,
                self.importer.tolerances.endpoint_tolerance_mm,
                1.0,
            )
        )
        self.render_scheduler = RenderScheduler(
            self.window.after_idle,
            self._flush_render_updates,
            self.performance_diagnostics,
        )
        self.selection_controller = SelectionController(
            self.selection_state,
            self.candidate_point_store,
            self._member_by_id,
            self.render_scheduler.request,
            self.performance_diagnostics,
        )
        self.import_model_controller = ImportModelController(
            self.importer.tolerances,
            self.candidate_point_store,
        )

        self.form_scroll_host = ttk.Frame(self.window)
        form_background = ttk.Style(self.window).lookup("TFrame", "background")
        self.form_canvas = tk.Canvas(
            self.form_scroll_host,
            background=form_background or self.window.cget("background"),
            borderwidth=0,
            highlightthickness=0,
            yscrollincrement=24,
        )
        self.form_scrollbar = ttk.Scrollbar(
            self.form_scroll_host,
            orient="vertical",
            command=self.form_canvas.yview,
        )
        self.form_canvas.configure(yscrollcommand=self.form_scrollbar.set)
        self.form_canvas.pack(side="left", fill="both", expand=True)
        self.form_scrollbar.pack(side="right", fill="y")
        self.form_content = ttk.Frame(self.form_canvas)
        self.form_content_window = self.form_canvas.create_window(
            (0, 0),
            window=self.form_content,
            anchor="nw",
        )
        self.form_content.bind("<Configure>", self._update_form_scrollregion)
        self.form_canvas.bind("<Configure>", self._resize_form_content)
        self.window.bind("<MouseWheel>", self._on_form_mousewheel, add="+")
        self.window.bind("<Button-4>", self._on_form_mousewheel, add="+")
        self.window.bind("<Button-5>", self._on_form_mousewheel, add="+")

        controls = ttk.LabelFrame(
            self.form_content,
            text=f"STEP1 圖層用途分類 — {self.file_path.name}",
        )
        controls.pack(fill="x", padx=10, pady=10)
        ttk.Label(
            controls,
            text="測試圖層可能預填用途；使用者可自由修改，辨識時以目前選擇為準。",
            foreground="#37474f",
        ).pack(anchor="w", padx=8, pady=(6, 3))
        classification_body = ttk.Frame(controls)
        classification_body.pack(fill="x", padx=8, pady=(0, 5))
        classification_header = ttk.Frame(classification_body)
        classification_header.pack(fill="x", padx=(0, 16))
        ttk.Label(
            classification_header,
            text="圖層名稱",
            font=("Microsoft JhengHei", 9, "bold"),
        ).grid(row=0, column=0, padx=8, pady=4, sticky="w")
        ttk.Label(
            classification_header,
            text="DXF 圖元數量",
            font=("Microsoft JhengHei", 9, "bold"),
        ).grid(row=0, column=1, padx=8, pady=4, sticky="e")
        ttk.Label(
            classification_header,
            text="用途",
            font=("Microsoft JhengHei", 9, "bold"),
        ).grid(row=0, column=2, padx=8, pady=4, sticky="w")
        classification_header.columnconfigure(0, weight=1)
        classification_header.columnconfigure(1, minsize=120)
        classification_header.columnconfigure(2, minsize=150)

        classification_list = ttk.Frame(classification_body)
        classification_list.pack(fill="x", expand=True)
        classification_canvas = tk.Canvas(
            classification_list,
            height=245,
            highlightthickness=1,
            highlightbackground="#b0bec5",
            yscrollincrement=24,
        )
        self.classification_canvas = classification_canvas
        classification_scroll = ttk.Scrollbar(
            classification_list,
            orient="vertical",
            command=classification_canvas.yview,
        )
        classification_canvas.configure(yscrollcommand=classification_scroll.set)
        classification_canvas.pack(side="left", fill="x", expand=True)
        classification_scroll.pack(side="right", fill="y")
        classification_rows = ttk.Frame(classification_canvas)
        classification_window = classification_canvas.create_window(
            (0, 0),
            window=classification_rows,
            anchor="nw",
        )
        classification_rows.bind(
            "<Configure>",
            lambda _event: classification_canvas.configure(
                scrollregion=classification_canvas.bbox("all")
            ),
        )
        classification_canvas.bind(
            "<Configure>",
            lambda event: classification_canvas.itemconfigure(
                classification_window,
                width=event.width,
            ),
        )
        saved_classification = self.initial_state.get("layer_classification", {})
        if not isinstance(saved_classification, Mapping):
            saved_classification = {}
        if not self.restore_saved_layer_classification:
            saved_classification = {}
        if not saved_classification:
            assignments = self.initial_state.get("layer_assignments", ())
            if self.restore_saved_layer_classification and isinstance(
                assignments, Sequence
            ) and not isinstance(
                assignments,
                (str, bytes),
            ):
                saved_classification = {
                    str(item.get("layer_name")): str(item.get("layer_type"))
                    for item in assignments
                    if isinstance(item, Mapping) and item.get("layer_name")
                }
        layer_counts = {
            item.name: item.entity_count for item in self.importer.layer_information()
        }
        self.layer_use_vars: dict[str, Any] = {}
        names = self.importer.layer_names
        for row, layer in enumerate(names):
            ttk.Label(classification_rows, text=layer).grid(
                row=row,
                column=0,
                padx=8,
                pady=2,
                sticky="w",
            )
            ttk.Label(
                classification_rows,
                text=str(layer_counts.get(layer, 0)),
            ).grid(row=row, column=1, padx=8, pady=2, sticky="e")
            variable = tk.StringVar(
                value=self._initial_layer_use(
                    layer,
                    saved_classification,
                    self.default_layer_mapping,
                )
            )
            combo = ttk.Combobox(
                classification_rows,
                textvariable=variable,
                values=self.LAYER_USE_OPTIONS,
                state="readonly",
                width=14,
            )
            combo.grid(row=row, column=2, padx=8, pady=2, sticky="w")
            self.layer_use_vars[layer] = variable
        classification_rows.columnconfigure(0, weight=1)
        classification_rows.columnconfigure(1, minsize=120)
        classification_rows.columnconfigure(2, minsize=150)

        action_row = ttk.Frame(controls)
        action_row.pack(fill="x", padx=8, pady=(0, 7))
        self.mode_var = tk.StringVar(value=self.import_mode)
        ttk.Radiobutton(action_row, text="取代目前工程模型", variable=self.mode_var, value="replace").pack(side="left")
        ttk.Radiobutton(action_row, text="附加到目前工程模型", variable=self.mode_var, value="append").pack(side="left", padx=12)
        self.recognize_button = ttk.Button(
            action_row,
            text="完成分類並開始辨識／重新辨識",
            command=self._convert_preview,
        )
        self.recognize_button.pack(side="right")

        self._build_coordinate_system_settings(self.form_content)

        review_frame = ttk.Frame(self.form_content)
        review_frame.pack(fill="x", padx=10, pady=(0, 8))
        self._build_engineering_review(review_frame)

        diagnostics_frame = ttk.LabelFrame(
            self.form_content,
            text="STEP7 匯入檢核結果",
        )
        diagnostics_frame.pack(fill="x", padx=10, pady=(0, 10))
        self._build_diagnostics_tab(diagnostics_frame, scrolledtext)

        footer = ttk.Frame(self.window)
        footer.pack(side="bottom", fill="x", padx=10, pady=10)
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(footer, textvariable=self.status_var)
        self.status_label.pack(side="left", fill="x", expand=True)
        pause_text = "返回主畫面" if self.allow_pause else "取消"
        pause_command = self._pause if self.allow_pause else self._cancel
        ttk.Button(footer, text=pause_text, command=pause_command).pack(
            side="right",
            padx=(6, 0),
        )
        self.apply_button = ttk.Button(footer, text="完成匯入", command=self._apply)
        self.apply_button.pack(side="right")
        self.apply_button.configure(state="disabled", text="不可匯入")
        self.status_var.set("請先完成圖層用途分類，再按下「開始辨識」。")
        self.form_scroll_host.pack(fill="both", expand=True)
        if bool(self.ui_state.get("main_maximized", False)):
            self.window.after_idle(lambda: self._set_maximized(True))
        self.window.after_idle(self._open_preview_window)
        if self.exclusion_fingerprint_mismatch:
            self.window.after_idle(self._show_exclusion_fingerprint_notice)
        if self.resume_review:
            if self.world_result is not None:
                self.window.after_idle(self._restore_memory_review)
            else:
                self.window.after_idle(self._convert_preview)

    def _is_maximized(self) -> bool:
        try:
            return self.window.state() == "zoomed"
        except self.tk.TclError:
            try:
                return bool(self.window.attributes("-zoomed"))
            except self.tk.TclError:
                return False

    def _set_maximized(self, maximized: bool) -> None:
        try:
            self.window.state("zoomed" if maximized else "normal")
        except self.tk.TclError:
            try:
                self.window.attributes("-zoomed", maximized)
            except self.tk.TclError:
                return

    def _update_form_scrollregion(self, _event: Any = None) -> None:
        bounds = self.form_canvas.bbox("all")
        if bounds is not None:
            self.form_canvas.configure(scrollregion=bounds)

    def _resize_form_content(self, event: Any) -> None:
        self.form_canvas.itemconfigure(
            self.form_content_window,
            width=max(int(event.width), 1),
        )

    @staticmethod
    def _form_wheel_units(event: Any) -> int:
        button = getattr(event, "num", None)
        if button == 4:
            return -1
        if button == 5:
            return 1
        delta = float(getattr(event, "delta", 0) or 0)
        if delta == 0:
            return 0
        return -1 if delta > 0 else 1

    @staticmethod
    def _widget_can_scroll(widget: Any, units: int) -> bool:
        try:
            first, last = widget.yview()
        except Exception:
            return False
        if units < 0:
            return float(first) > 1e-9
        return float(last) < 1.0 - 1e-9

    @staticmethod
    def _widget_is_descendant(widget: Any, ancestor: Any) -> bool:
        current = widget
        while current is not None:
            if current is ancestor:
                return True
            current = getattr(current, "master", None)
        return False

    def _on_form_mousewheel(self, event: Any) -> str | None:
        units = self._form_wheel_units(event)
        if units == 0:
            return None

        widget = getattr(event, "widget", None)
        if widget is not None and widget is not self.form_canvas:
            classification_canvas = getattr(self, "classification_canvas", None)
            if (
                classification_canvas is not None
                and self._widget_is_descendant(widget, classification_canvas)
            ):
                if self._widget_can_scroll(classification_canvas, units):
                    classification_canvas.yview_scroll(units, "units")
                    return "break"
                # At the top or bottom, fall through to the page canvas.
            try:
                widget_class = str(widget.winfo_class())
            except Exception:
                widget_class = ""
            if widget_class in {"Treeview", "Text", "Listbox"}:
                return None
            if widget_class == "Canvas":
                if self._widget_can_scroll(widget, units):
                    widget.yview_scroll(units, "units")
                    return "break"
                # The inner list reached its boundary; continue with the
                # STEP1–STEP7 page instead of trapping the mouse wheel.

        if not self._widget_can_scroll(self.form_canvas, units):
            return None
        self.form_canvas.yview_scroll(units, "units")
        return "break"

    def _on_main_window_configure(self, event: Any) -> None:
        if event.widget is not self.window:
            return
        maximized = self._is_maximized()
        if not maximized:
            geometry = self.window.geometry()
            if geometry:
                self._last_normal_geometry = geometry

    def _save_ui_state(self) -> None:
        if self.preview_window is not None:
            try:
                self._last_preview_geometry = self.preview_window.geometry()
            except self.tk.TclError:
                pass
        payload = {
            "main_geometry": self._last_normal_geometry,
            "main_maximized": self._is_maximized(),
            "preview_geometry": self._last_preview_geometry,
            "show_source": bool(self.show_source_var.get()),
            "show_auxiliary": bool(self.show_auxiliary_var.get()),
            "performance_diagnostics": bool(
                self.performance_diagnostics_enabled_var.get()
            ),
        }
        try:
            path = self._ui_state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _build_engineering_review(self, parent: Any) -> None:
        body = self.ttk.Panedwindow(parent, orient="horizontal")

        member_frame = self.ttk.LabelFrame(body, text="STEP3 工程檢核項目")
        self.member_tree = self.ttk.Treeview(
            member_frame,
            show="tree",
            selectmode="browse",
            height=20,
        )
        member_scroll = self.ttk.Scrollbar(
            member_frame,
            orient="vertical",
            command=self.member_tree.yview,
        )
        self.member_tree.configure(yscrollcommand=member_scroll.set)
        for level in ("info", "warning", "error", "critical"):
            self.member_tree.tag_configure(
                level,
                foreground=self.LEVEL_COLORS[level],
            )
        self.member_tree.tag_configure("excluded", foreground="#78909c")
        self.member_tree.pack(side="left", fill="both", expand=True)
        member_scroll.pack(side="right", fill="y")
        self.member_tree.bind("<<TreeviewSelect>>", self._on_member_selected)
        self.member_tree_selection = TreeSelectionSynchronizer(
            self.member_tree,
            self.window.after_idle,
        )

        detail_frame = self.ttk.LabelFrame(
            body,
            text="STEP4 項目明細、問題與既有調整",
        )
        self.member_info_vars = {
            key: self.tk.StringVar(value="—")
            for key in (
                "id",
                "status",
                "role",
                "layer",
                "entities",
                "method",
                "reason",
                "source_width",
                "start_x",
                "start_y",
                "end_x",
                "end_y",
            )
        }
        info_rows = (
            ("構件編號", "id"),
            ("狀態", "status"),
            ("構件類型", "role"),
            ("來源圖層", "layer"),
            ("來源 DXF 圖元", "entities"),
            ("辨識方法", "method"),
            ("排除原因", "reason"),
            ("圖面寬度 (mm)", "source_width"),
            ("StartX", "start_x"),
            ("StartY", "start_y"),
            ("EndX", "end_x"),
            ("EndY", "end_y"),
        )
        for row, (label, key) in enumerate(info_rows):
            self.ttk.Label(detail_frame, text=f"{label}：").grid(
                row=row,
                column=0,
                padx=(8, 4),
                pady=2,
                sticky="ne",
            )
            self.ttk.Label(
                detail_frame,
                textvariable=self.member_info_vars[key],
                wraplength=300,
                justify="left",
            ).grid(row=row, column=1, padx=(0, 8), pady=2, sticky="nw")

        detail_frame.columnconfigure(1, weight=1)

        material_row = len(info_rows)
        self.material_spec_frame = self.ttk.LabelFrame(
            detail_frame,
            text="材料規格確認",
        )
        self.material_spec_frame.grid(
            row=material_row + 1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(8, 2),
        )
        self.material_spec_var = self.tk.StringVar(value="")
        self.material_spec_status_var = self.tk.StringVar(value="")
        self.ttk.Label(self.material_spec_frame, text="材料規格：").grid(
            row=0, column=0, sticky="w", padx=(6, 4), pady=5
        )
        self.material_spec_combo = self.ttk.Combobox(
            self.material_spec_frame,
            textvariable=self.material_spec_var,
            state="readonly",
        )
        self.material_spec_combo.grid(
            row=0, column=1, sticky="ew", padx=(0, 6), pady=5
        )
        self.material_spec_combo.bind(
            "<<ComboboxSelected>>", self._on_material_spec_selected
        )
        self.ttk.Label(
            self.material_spec_frame,
            textvariable=self.material_spec_status_var,
            foreground="#455a64",
            wraplength=300,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 5))
        self.material_spec_frame.columnconfigure(1, weight=1)
        self.material_spec_frame.grid_remove()

        self.waler_contact_frame = self.ttk.LabelFrame(
            detail_frame,
            text="Waler 接觸位置調整",
        )
        self.waler_contact_frame.grid(
            row=material_row + 2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(8, 6),
        )
        self.waler_contact_title_var = self.tk.StringVar(value="")
        self.waler_contact_displacement_var = self.tk.StringVar(
            value="接觸位置調整：—"
        )
        self.waler_contact_impact_var = self.tk.StringVar(value="影響：—")
        self.waler_contact_status_var = self.tk.StringVar(value="")
        self.waler_contact_value_vars = {
            "original_backfill_mm": self.tk.StringVar(value=""),
            "adopted_backfill_mm": self.tk.StringVar(value=""),
            "original_waler_width_mm": self.tk.StringVar(value=""),
            "adopted_waler_width_mm": self.tk.StringVar(value=""),
        }
        self.ttk.Label(
            self.waler_contact_frame,
            textvariable=self.waler_contact_title_var,
            font=("Microsoft JhengHei", 9, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=6, pady=(5, 2))
        self.ttk.Label(self.waler_contact_frame, text="").grid(row=1, column=0)
        self.ttk.Label(self.waler_contact_frame, text="圖面值").grid(row=1, column=1)
        self.ttk.Label(self.waler_contact_frame, text="採用值").grid(row=1, column=2)
        for row, (label, original_key, adopted_key) in enumerate(
            (
                (
                    "背填厚度 (mm)",
                    "original_backfill_mm",
                    "adopted_backfill_mm",
                ),
                (
                    "圍令寬度 (mm)",
                    "original_waler_width_mm",
                    "adopted_waler_width_mm",
                ),
            ),
            start=2,
        ):
            self.ttk.Label(self.waler_contact_frame, text=label).grid(
                row=row, column=0, sticky="w", padx=6, pady=2
            )
            for column, key in ((1, original_key), (2, adopted_key)):
                entry = self.ttk.Entry(
                    self.waler_contact_frame,
                    textvariable=self.waler_contact_value_vars[key],
                    width=12,
                )
                entry.grid(row=row, column=column, sticky="ew", padx=4, pady=2)
                entry.bind("<KeyRelease>", self._on_waler_contact_value_changed)
        self.ttk.Separator(self.waler_contact_frame).grid(
            row=4, column=0, columnspan=3, sticky="ew", padx=6, pady=5
        )
        self.ttk.Label(
            self.waler_contact_frame,
            textvariable=self.waler_contact_displacement_var,
        ).grid(row=5, column=0, columnspan=3, sticky="w", padx=6, pady=2)
        self.ttk.Label(
            self.waler_contact_frame,
            textvariable=self.waler_contact_impact_var,
            wraplength=300,
            justify="left",
        ).grid(row=6, column=0, columnspan=3, sticky="w", padx=6, pady=2)
        action = self.ttk.Frame(self.waler_contact_frame)
        action.grid(row=7, column=0, columnspan=3, sticky="ew", padx=6, pady=4)
        self.ttk.Button(
            action,
            text="預覽影響",
            command=self._preview_waler_contact_adjustment,
        ).pack(side="left")
        self.waler_contact_apply_button = self.ttk.Button(
            action,
            text="套用",
            command=self._apply_waler_contact_adjustment,
            state="disabled",
        )
        self.waler_contact_apply_button.pack(side="right")
        self.ttk.Label(
            self.waler_contact_frame,
            textvariable=self.waler_contact_status_var,
            foreground="#9a6700",
            wraplength=300,
            justify="left",
        ).grid(row=8, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 5))
        self.waler_contact_frame.columnconfigure(1, weight=1)
        self.waler_contact_frame.columnconfigure(2, weight=1)
        self.waler_contact_frame.grid_remove()

        self.review_issue_frame = self.ttk.LabelFrame(
            detail_frame,
            text="此項目問題與建議處理方式",
        )
        self.review_issue_frame.grid(
            row=material_row,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(8, 2),
        )
        self.detail_problem_tree = self.ttk.Treeview(
            self.review_issue_frame,
            columns=("severity", "code", "description"),
            show="headings",
            selectmode="browse",
            height=5,
        )
        for column, title, width, anchor in (
            ("severity", "等級", 60, "center"),
            ("code", "代碼", 150, "w"),
            ("description", "說明", 280, "w"),
        ):
            self.detail_problem_tree.heading(column, text=title)
            self.detail_problem_tree.column(
                column,
                width=width,
                anchor=anchor,
                stretch=column == "description",
            )
        for level in ("info", "warning", "error", "critical"):
            self.detail_problem_tree.tag_configure(
                level,
                foreground=self.LEVEL_COLORS[level],
            )
        detail_problem_scroll = self.ttk.Scrollbar(
            self.review_issue_frame,
            orient="vertical",
            command=self.detail_problem_tree.yview,
        )
        self.detail_problem_tree.configure(
            yscrollcommand=detail_problem_scroll.set,
        )
        self.detail_problem_tree.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(6, 0),
            pady=(6, 2),
        )
        detail_problem_scroll.grid(
            row=0,
            column=1,
            sticky="ns",
            padx=(0, 6),
            pady=(6, 2),
        )
        self.detail_problem_tree.bind(
            "<Double-Button-1>",
            self._on_detail_problem_activated,
        )
        self.detail_problem_tree.bind(
            "<Return>",
            self._on_detail_problem_activated,
        )
        self.detail_problem_empty_var = self.tk.StringVar(value="請先選取檢核項目。")
        self.ttk.Label(
            self.review_issue_frame,
            textvariable=self.detail_problem_empty_var,
            foreground="#455a64",
            wraplength=420,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(1, 3))
        self.detail_guidance_var = self.tk.StringVar(value="")
        self.ttk.Label(
            self.review_issue_frame,
            text="建議處理方式",
            font=("Microsoft JhengHei", 9, "bold"),
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=(3, 1))
        self.ttk.Label(
            self.review_issue_frame,
            textvariable=self.detail_guidance_var,
            foreground="#37474f",
            wraplength=420,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))
        exclusion_action = self.ttk.Frame(self.review_issue_frame)
        exclusion_action.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=6,
            pady=(2, 4),
        )
        self.source_exclusion_button = self.ttk.Button(
            exclusion_action,
            text="排除此 DXF 來源",
            command=self._on_source_exclusion_action,
            state="disabled",
        )
        self.source_exclusion_button.pack(side="right")
        self.source_exclusion_status_var = self.tk.StringVar(value="")
        self.ttk.Label(
            self.review_issue_frame,
            textvariable=self.source_exclusion_status_var,
            foreground="#795548",
            wraplength=420,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))
        self.review_issue_frame.columnconfigure(0, weight=1)

        candidate_frame = self.ttk.LabelFrame(
            body,
            text="STEP5 候選點（確認後才套用）",
        )
        self.candidate_filter_var = self.tk.StringVar(value="all")
        self.candidate_action_status_var = self.tk.StringVar(
            value="請先選取構件；單擊候選點只會預覽。"
        )
        self.candidate_detail_var = self.tk.StringVar(value="候選點：—")
        filter_row = self.ttk.Frame(candidate_frame)
        filter_row.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(6, 2),
        )
        for text, value in (
            ("全部", "all"),
            ("起點", "start"),
            ("終點", "end"),
            ("推薦", "recommended"),
        ):
            self.ttk.Radiobutton(
                filter_row,
                text=text,
                variable=self.candidate_filter_var,
                value=value,
                command=self._on_candidate_filter_changed,
            ).pack(side="left", padx=(0, 5))
        self.candidate_tree = self.ttk.Treeview(
            candidate_frame,
            columns=("id", "type", "world", "local", "status"),
            show="headings",
            selectmode="browse",
            height=11,
        )
        for column, text in (
            ("id", "點"),
            ("type", "用途／類型"),
            ("world", "World X, Y"),
            ("local", "Local X, Y"),
            ("status", "狀態"),
        ):
            self.candidate_tree.heading(column, text=text)
        self.candidate_tree.column("id", width=54, anchor="center", stretch=False)
        self.candidate_tree.column("type", width=185, anchor="w")
        self.candidate_tree.column("world", width=165, anchor="e")
        self.candidate_tree.column("local", width=155, anchor="e")
        self.candidate_tree.column("status", width=180, anchor="w")
        candidate_scroll = self.ttk.Scrollbar(
            candidate_frame,
            orient="vertical",
            command=self.candidate_tree.yview,
        )
        self.candidate_tree.configure(yscrollcommand=candidate_scroll.set)
        self.candidate_tree.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(8, 0),
            pady=(6, 5),
        )
        candidate_scroll.grid(
            row=1,
            column=1,
            sticky="ns",
            padx=(0, 6),
            pady=(6, 5),
        )
        self.candidate_tree.bind("<<TreeviewSelect>>", self._on_candidate_point_selected)
        self.candidate_tree.bind("<Motion>", self._on_candidate_hover)
        self.candidate_tree.bind("<Leave>", self._clear_candidate_hover)
        self.candidate_tree_adapter = CandidateTreeAdapter(
            self.candidate_tree,
            self.window.after_idle,
        )
        self.ttk.Label(
            candidate_frame,
            textvariable=self.candidate_detail_var,
            foreground="#607d8b",
            wraplength=680,
            justify="left",
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 4))
        pick_buttons = self.ttk.Frame(candidate_frame)
        pick_buttons.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=2)
        self.ttk.Button(
            pick_buttons,
            text="重新選擇起點",
            command=lambda: self._begin_candidate_pick("pick_start"),
        ).pack(side="left", padx=(0, 4))
        self.ttk.Button(
            pick_buttons,
            text="重新選擇終點",
            command=lambda: self._begin_candidate_pick("pick_end"),
        ).pack(side="left", padx=4)
        self.ttk.Button(
            pick_buttons,
            text="交換起終點",
            command=self._swap_pending_points,
        ).pack(side="left", padx=4)
        commit_buttons = self.ttk.Frame(candidate_frame)
        commit_buttons.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=2)
        self.ttk.Button(
            commit_buttons,
            text="恢復系統推薦",
            command=self._restore_recommended_points,
        ).pack(side="left", padx=(0, 4))
        self.ttk.Button(
            commit_buttons,
            text="取消修改",
            command=self._cancel_candidate_changes,
        ).pack(side="left", padx=4)
        self.ttk.Button(
            commit_buttons,
            text="套用修改",
            command=self._apply_candidate_changes,
        ).pack(side="right", padx=(4, 0))
        self.ttk.Label(
            candidate_frame,
            textvariable=self.candidate_action_status_var,
            foreground="#37474f",
            wraplength=680,
            justify="left",
        ).grid(row=5, column=0, columnspan=2, sticky="ew", padx=8, pady=(2, 6))
        candidate_frame.rowconfigure(1, weight=1)
        candidate_frame.columnconfigure(0, weight=1)

        # Candidate picking is now primarily graphical in the independent
        # preview. Keep this table as a compact precision/overlap fallback.
        candidate_frame.configure(text="STEP5 候選點明細（精確選擇／備援）")
        filter_row.grid_remove()
        pick_buttons.grid_remove()
        commit_buttons.grid_remove()
        for widget in candidate_frame.grid_slaves(row=5):
            widget.grid_remove()
        self.candidate_tree.configure(
            displaycolumns=("id", "type", "status"),
            height=9,
        )
        self.candidate_tree.column("type", width=205, anchor="w")
        self.candidate_tree.column("status", width=145, anchor="w")
        self.candidate_tree.grid_configure(row=0, pady=(6, 4))
        candidate_scroll.grid_configure(row=0, pady=(6, 4))
        for widget in candidate_frame.grid_slaves(row=2):
            widget.grid_configure(row=1, pady=(2, 6))
        origin_action = self.ttk.Frame(candidate_frame)
        origin_action.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(0, 7),
        )
        self.set_origin_button = self.ttk.Button(
            origin_action,
            text="以選定點設定局部原點",
            command=self._set_selected_point_as_origin,
            state="disabled",
        )
        self.set_origin_button.pack(side="left", padx=(0, 8))
        self.ttk.Label(
            origin_action,
            text="此按鈕只使用表格目前選定的候選點，不使用預覽窗格點選。",
            foreground="#455a64",
            wraplength=360,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        candidate_frame.rowconfigure(0, weight=1)
        candidate_frame.rowconfigure(1, weight=0)
        candidate_frame.rowconfigure(2, weight=0)

        body.add(member_frame, weight=1)
        body.add(detail_frame, weight=1)
        body.add(candidate_frame, weight=1)

        cad_frame = self.ttk.LabelFrame(parent, text="STEP6 從 CAD 重新指定工程線")
        cad_frame.pack(side="bottom", fill="x", padx=6, pady=(0, 6))
        self.ttk.Label(
            cad_frame,
            textvariable=self.cad_temp_status_var,
            foreground="#37474f",
        ).pack(side="left", fill="x", expand=True, padx=8, pady=6)
        self.ttk.Button(
            cad_frame,
            text="從 CAD 指定工程線",
            command=self._read_cad_engineering_line,
        ).pack(side="right", padx=8, pady=5)
        body.pack(fill="both", expand=True, padx=5, pady=5)

    def _create_preview_canvas(self, parent: Any) -> None:
        old_canvas = getattr(self, "canvas", None)
        if old_canvas is not None:
            try:
                if old_canvas.winfo_exists():
                    old_canvas.destroy()
            except self.tk.TclError:
                pass
        self.canvas = self.tk.Canvas(
            parent,
            background="white",
            highlightthickness=1,
            highlightbackground="#999",
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw_preview())
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind(
            "<Leave>",
            self._on_canvas_leave,
        )
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Escape>", self._cancel_active_pick)
        self.canvas.bind("<MouseWheel>", self._on_canvas_mousewheel)
        self.canvas.bind(
            "<Button-4>",
            lambda event: self._on_canvas_mousewheel(event, 1),
        )
        self.canvas.bind(
            "<Button-5>",
            lambda event: self._on_canvas_mousewheel(event, -1),
        )
        self.canvas.bind("<ButtonPress-2>", self._start_canvas_pan)
        self.canvas.bind("<B2-Motion>", self._drag_canvas_pan)
        self.canvas.bind("<ButtonRelease-2>", self._end_canvas_pan)
        self.canvas.bind("<Double-Button-2>", self._on_canvas_middle_double_click)
        self.canvas_member_hit_lines = []
        self.canvas_candidate_hit_points = []
        self.preview_transform = None
        self.preview_scene = PreviewScene()
        self.preview_renderer = PreviewRenderer(self.canvas, self.preview_scene)
        self._draw_preview()

    def _open_preview_window(self) -> None:
        if self.preview_window is not None:
            try:
                if self.preview_window.winfo_exists():
                    self._last_preview_geometry = self._restore_visible_geometry(
                        self.preview_window,
                        self._last_preview_geometry,
                        "1100x800+80+80",
                    )
                    self.preview_window.deiconify()
                    self.preview_window.lift()
                    return
            except self.tk.TclError:
                pass

        preview_window = self.tk.Toplevel(self.window)
        self.preview_window = preview_window
        preview_window.title(f"DXF 圖面預覽 — {self.file_path.name}")
        preview_window.minsize(640, 480)
        self._last_preview_geometry = self._restore_visible_geometry(
            preview_window,
            self._last_preview_geometry,
            "1100x800+80+80",
        )
        preview_window.protocol("WM_DELETE_WINDOW", self._hide_preview_window)
        preview_window.bind("<Configure>", self._on_preview_window_configure)
        preview_window.bind("<Escape>", self._cancel_active_pick)

        toolbar = self.ttk.Frame(preview_window)
        toolbar.pack(fill="x", padx=8, pady=6)
        self.ttk.Button(
            toolbar,
            text="定位至構件",
            command=self._locate_selected_member,
        ).pack(side="left")
        self.ttk.Checkbutton(
            toolbar,
            text="疊加原始外框",
            variable=self.show_source_var,
            command=self._update_source_layer_visibility,
        ).pack(side="left")
        self.ttk.Checkbutton(
            toolbar,
            text="顯示輔助線",
            variable=self.show_auxiliary_var,
            command=self._update_source_layer_visibility,
        ).pack(side="left", padx=(8, 0))
        self.ttk.Label(
            toolbar,
            textvariable=self.preview_cursor_var,
            foreground="#455a64",
        ).pack(side="right", padx=6)
        self.ttk.Label(
            toolbar,
            text="滾輪縮放｜中鍵平移｜雙擊中鍵顯示全部",
            foreground="#555555",
        ).pack(side="right", padx=12)
        review_toolbar = self.ttk.LabelFrame(
            preview_window,
            text="候選點與工程線修正",
        )
        review_toolbar.pack(fill="x", padx=8, pady=(0, 6))
        review_actions = self.ttk.Frame(review_toolbar)
        review_actions.pack(fill="x")
        self.ttk.Label(
            review_actions,
            textvariable=self.preview_selected_member_var,
            font=("Microsoft JhengHei", 10, "bold"),
        ).pack(side="left", padx=(8, 12), pady=5)
        self.ttk.Button(
            review_actions,
            text="選起點",
            command=lambda: self._begin_candidate_pick("pick_start"),
        ).pack(side="left", padx=3, pady=4)
        self.ttk.Button(
            review_actions,
            text="選終點",
            command=lambda: self._begin_candidate_pick("pick_end"),
        ).pack(side="left", padx=3, pady=4)
        self.ttk.Button(
            review_actions,
            text="交換",
            command=self._swap_pending_points,
        ).pack(side="left", padx=3, pady=4)
        self.ttk.Button(
            review_actions,
            text="恢復推薦",
            command=self._restore_recommended_points,
        ).pack(side="left", padx=(12, 3), pady=4)
        self.ttk.Button(
            review_actions,
            text="取消修改",
            command=self._cancel_candidate_changes,
        ).pack(side="left", padx=3, pady=4)
        self.ttk.Button(
            review_actions,
            text="套用修改",
            command=self._apply_candidate_changes,
        ).pack(side="left", padx=(12, 3), pady=4)

        preview_filter = self.ttk.Frame(review_toolbar)
        preview_filter.pack(fill="x", padx=8, pady=(0, 4))
        self.ttk.Label(preview_filter, text="候選點：").pack(side="left")
        for text, value in (
            ("全部", "all"),
            ("起點", "start"),
            ("終點", "end"),
            ("推薦", "recommended"),
        ):
            self.ttk.Radiobutton(
                preview_filter,
                text=text,
                variable=self.candidate_filter_var,
                value=value,
                command=self._on_candidate_filter_changed,
            ).pack(side="left", padx=2)

        # Keep the instruction on its own line so tool controls remain usable
        # on a single, narrower monitor.
        self.ttk.Label(
            preview_window,
            textvariable=self.candidate_action_status_var,
            foreground="#c62828",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 5))

        canvas_host = self.ttk.Frame(preview_window)
        canvas_host.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._create_preview_canvas(canvas_host)

    def _hide_preview_window(self) -> None:
        if self.preview_window is None:
            return
        try:
            self._last_preview_geometry = self.preview_window.geometry()
            self.preview_window.iconify()
        except self.tk.TclError:
            pass

    def _on_preview_window_configure(self, event: Any) -> None:
        if self.preview_window is None or event.widget is not self.preview_window:
            return
        try:
            self._last_preview_geometry = self.preview_window.geometry()
        except self.tk.TclError:
            pass

    def _build_coordinate_system_settings(self, parent: Any) -> None:
        frame = self.ttk.LabelFrame(parent, text="STEP2 座標系統狀態")
        frame.pack(fill="x", padx=10, pady=(0, 8))
        self.coordinate_mode_var = self.tk.StringVar(
            value=("local" if self.selected_origin_world is not None else "world")
        )
        self.coordinate_error_var = self.tk.StringVar(value="")
        self.coordinate_info_var = self.tk.StringVar(value="")
        self.coordinate_example_var = self.tk.StringVar(value="")

        self.ttk.Button(
            frame,
            text="使用原始 CAD 座標",
            command=self._reset_coordinate_settings,
        ).grid(row=0, column=0, padx=8, pady=(7, 3), sticky="w")
        self.ttk.Label(
            frame,
            text="預設使用原始 CAD 座標。完成構件辨識後，可在 STEP5 候選點明細表格選取一點並設定為局部原點。",
            foreground="#455a64",
        ).grid(row=0, column=1, columnspan=4, padx=(12, 8), pady=(7, 3), sticky="w")

        self.tk.Label(frame, textvariable=self.coordinate_error_var, foreground="#c62828", anchor="w").grid(
            row=1, column=0, columnspan=2, padx=8, pady=(1, 5), sticky="w"
        )
        self.ttk.Label(frame, textvariable=self.coordinate_info_var).grid(
            row=1, column=2, columnspan=2, padx=8, pady=(1, 5), sticky="w"
        )
        self.ttk.Label(frame, textvariable=self.coordinate_example_var, foreground="#455a64").grid(
            row=1, column=4, padx=8, pady=(1, 5), sticky="e"
        )
        frame.columnconfigure(4, weight=1)

    def _build_diagnostics_tab(self, parent: Any, scrolledtext: Any) -> None:
        summary_frame = self.ttk.LabelFrame(parent, text="DXF 匯入摘要")
        summary_frame.pack(fill="x", padx=6, pady=(6, 3))
        self.summary_file_var = self.tk.StringVar()
        self.summary_totals_var = self.tk.StringVar()
        self.ttk.Label(summary_frame, textvariable=self.summary_file_var, font=("Microsoft JhengHei", 10, "bold")).pack(anchor="w", padx=8, pady=(5, 2))
        columns = ("role", "layer", "source", "recognized", "skipped")
        self.summary_tree = self.ttk.Treeview(summary_frame, columns=columns, show="headings", height=7)
        headings = {"role": "類別", "layer": "選定圖層", "source": "原始 DXF 圖元", "recognized": "辨識成功", "skipped": "略過"}
        widths = {"role": 75, "layer": 460, "source": 105, "recognized": 105, "skipped": 80}
        for column in columns:
            self.summary_tree.heading(column, text=headings[column])
            self.summary_tree.column(column, width=widths[column], anchor="center" if column != "layer" else "w")
        self.summary_tree.pack(fill="x", padx=8, pady=2)
        self.ttk.Label(summary_frame, textvariable=self.summary_totals_var).pack(anchor="w", padx=8, pady=(2, 5))

        double_support_frame = self.ttk.LabelFrame(
            parent,
            text="雙路支撐候選（中心距離約 1000 mm）",
        )
        double_support_frame.pack(fill="x", padx=6, pady=3)
        pair_columns = (
            "status",
            "members",
            "spacing",
            "angle",
            "overlap",
            "confidence",
        )
        self.double_support_tree = self.ttk.Treeview(
            double_support_frame,
            columns=pair_columns,
            show="headings",
            selectmode="browse",
            height=3,
        )
        pair_headings = {
            "status": "採用",
            "members": "支撐",
            "spacing": "中心距離(mm)",
            "angle": "角度差",
            "overlap": "重疊率",
            "confidence": "可信度",
        }
        pair_widths = {
            "status": 70,
            "members": 180,
            "spacing": 125,
            "angle": 95,
            "overlap": 95,
            "confidence": 95,
        }
        for column in pair_columns:
            self.double_support_tree.heading(
                column,
                text=pair_headings[column],
            )
            self.double_support_tree.column(
                column,
                width=pair_widths[column],
                anchor="center",
            )
        self.double_support_tree.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(8, 4),
            pady=5,
        )
        self.ttk.Button(
            double_support_frame,
            text="切換採用／取消",
            command=self._toggle_selected_double_support,
        ).pack(side="right", padx=(4, 8), pady=5)
        self.double_support_tree.bind(
            "<Double-1>",
            lambda _event: self._toggle_selected_double_support(),
        )

        validation_frame = self.ttk.LabelFrame(parent, text="驗證結果")
        validation_frame.pack(fill="x", padx=6, pady=3)
        self.validation_content = self.ttk.Frame(validation_frame)
        self.validation_content.pack(fill="x", padx=8, pady=5)

        problem_frame = self.ttk.LabelFrame(parent, text="錯誤與警告（點選後自動定位）")
        problem_frame.pack(fill="both", expand=True, padx=6, pady=3)
        filters = self.ttk.Frame(problem_frame)
        filters.pack(fill="x", padx=6, pady=4)
        self.problem_filter_var = self.tk.StringVar(value="all")
        for value, label in (("all", "全部"), ("error", "只看 Error"), ("warning", "只看 Warning")):
            self.ttk.Radiobutton(filters, text=label, variable=self.problem_filter_var, value=value, command=self._refresh_problem_tree).pack(side="left", padx=(0, 8))
        self.selected_only_var = self.tk.BooleanVar(value=False)
        self.ttk.Checkbutton(filters, text="只看選定構件", variable=self.selected_only_var, command=self._refresh_problem_tree).pack(side="left", padx=8)

        problem_container = self.ttk.Frame(problem_frame)
        problem_container.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        problem_container.rowconfigure(0, weight=1)
        problem_container.columnconfigure(0, weight=1)
        columns = ("severity", "code", "component", "description")
        self.problem_tree = self.ttk.Treeview(problem_container, columns=columns, show="headings", selectmode="browse", height=7)
        headings = {"severity": "等級", "code": "類型", "component": "構件／來源", "description": "說明"}
        widths = {"severity": 85, "code": 250, "component": 180, "description": 520}
        for column in columns:
            self.problem_tree.heading(column, text=headings[column])
            self.problem_tree.column(column, width=widths[column], anchor="w")
        self.problem_tree.tag_configure("critical", background="#ffcdd2", foreground="#8e0000")
        self.problem_tree.tag_configure("error", background="#ffebee", foreground="#b71c1c")
        self.problem_tree.tag_configure("warning", background="#fff8e1", foreground="#8d6e00")
        self.problem_tree.tag_configure("info", background="#e3f2fd", foreground="#0d47a1")
        self.problem_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = self.ttk.Scrollbar(problem_container, orient="vertical", command=self.problem_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.problem_tree.configure(yscrollcommand=scrollbar.set)
        self.problem_tree.bind("<<TreeviewSelect>>", self._on_problem_selected)

        self.developer_button = self.ttk.Button(parent, text="▶ 開發者模式（原始 JSON）", command=self._toggle_developer_mode)
        self.developer_button.pack(fill="x", padx=6, pady=(3, 6))
        self.developer_frame = self.ttk.LabelFrame(parent, text="開發者模式")
        performance_row = self.ttk.Frame(self.developer_frame)
        performance_row.pack(fill="x", padx=5, pady=(5, 0))
        self.ttk.Checkbutton(
            performance_row,
            text="效能診斷",
            variable=self.performance_diagnostics_enabled_var,
            command=self._update_performance_diagnostics_display,
        ).pack(side="left")
        self.ttk.Label(
            performance_row,
            textvariable=self.performance_diagnostics_var,
            foreground="#455a64",
        ).pack(side="left", fill="x", expand=True, padx=8)
        self.debug_text = scrolledtext.ScrolledText(self.developer_frame, wrap="none", height=12, font=("Consolas", 9))
        self.debug_text.pack(fill="both", expand=True, padx=5, pady=5)

    def show(self) -> DXFImportDialogOutcome | None:
        self.window.grab_set()
        self.window.wait_window()
        if self.dialog_action not in {"pause", "complete"}:
            return None
        return DXFImportDialogOutcome(
            action=self.dialog_action,
            review_state=copy.deepcopy(self.review_state),
            import_mode=self.import_mode,
            result=self.result,
            world_result=self.world_result,
        )

    def _restore_memory_review(self) -> None:
        """Reopen a valid in-memory result without repeating recognition."""

        if self.world_result is None:
            return
        self._apply_coordinate_settings(show_error=False)
        self.status_var.set("已恢復尚未完成的 DXF Review。")

    def _convert_preview(self) -> None:
        self._clear_waler_adjustment_preview()
        self.selection_state = SelectionState()
        self.selection_controller.state = self.selection_state
        self.preview_view_bounds = None
        self.preview_fit_all = True
        self.status_var.set("DXF 正在辨識，請稍候……")
        self.recognize_button.configure(state="disabled", text="辨識中……")
        self.apply_button.configure(state="disabled", text="不可匯入")
        try:
            self.window.configure(cursor="watch")
            self.window.update_idletasks()
        except self.tk.TclError:
            pass
        self.window.after_idle(self._perform_conversion)

    def _current_layer_roles(self) -> dict[str, str]:
        layer_roles: dict[str, str] = {}
        for layer, variable in self.layer_use_vars.items():
            selected_use = variable.get()
            role = self.USE_TO_ROLE.get(selected_use)
            if role is None:
                raise DXFImportError(
                    f"圖層「{layer}」使用了不支援的用途：{selected_use or '空白'}"
                )
            layer_roles[layer] = role
        return layer_roles

    def _recognize_staged_result(
        self,
        excluded_sources: Sequence[ExcludedSource],
        manual_overrides: Sequence[Any] = (),
        *,
        layer_roles: Mapping[str, str] | None = None,
    ) -> tuple[DXFImportResult, ManualReplayReport]:
        """Build a complete WCS result without changing dialog state."""

        staged = self.importer.convert(
            layer_roles=layer_roles or self._current_layer_roles(),
            coordinate_system=CoordinateSystem(),
            material_specs=self.material_specs,
            excluded_sources=excluded_sources,
        )
        staged, replay_report = replay_manual_overrides(
            staged,
            manual_overrides,
            material_specs=self.material_specs,
            tolerances=self.importer.tolerances,
        )
        candidates = staged.double_support_candidates
        previous_result = getattr(self, "world_result", None)
        if previous_result is not None:
            candidates = preserve_double_support_result_decisions(
                previous_result,
                staged,
            )
        saved_double_support_decisions = getattr(
            self,
            "double_support_decisions",
            {},
        )
        if saved_double_support_decisions:
            decision_result = replace(
                staged,
                double_support_candidates=candidates,
            )
            candidates = apply_double_support_decisions(
                decision_result,
                saved_double_support_decisions,
            )
        if candidates != staged.double_support_candidates:
            staged = rebuild_component_associations(
                replace(
                    staged,
                    double_support_candidates=candidates,
                ),
                self.importer.tolerances,
            )
        return staged, replay_report

    def _perform_conversion(self) -> None:
        from tkinter import messagebox

        try:
            if self.world_result is not None:
                overrides = capture_manual_overrides(self.world_result)
            elif review_state_matches_source(
                self.initial_state,
                self.importer.source_fingerprint,
                self.file_path,
            ):
                overrides = manual_overrides_from_review_state(self.initial_state)
            else:
                overrides = ()
            staged, replay_report = self._recognize_staged_result(
                self.excluded_sources,
                overrides,
            )
            self.world_result = staged
            self.excluded_sources = staged.excluded_sources
            self.last_manual_replay_report = replay_report
            self._apply_coordinate_settings(show_error=False)
        except Exception as exc:
            if isinstance(exc, DXFImportError):
                error_text = str(exc)
            else:
                error_text = f"辨識發生未預期錯誤：{type(exc).__name__}: {exc}"
            self.world_result = None
            self.result = None
            self.status_var.set(error_text)
            self.apply_button.configure(state="disabled", text="不可匯入")
            messagebox.showerror("DXF 轉換失敗", error_text, parent=self.window)
        finally:
            try:
                self.window.configure(cursor="")
                self.recognize_button.configure(
                    state="normal",
                    text="完成分類並開始辨識／重新辨識",
                )
            except self.tk.TclError:
                pass

    def _reset_coordinate_settings(self) -> None:
        self.coordinate_mode_var.set("world")
        self.selected_origin_world = None
        self._apply_coordinate_settings(show_error=False)

    def _set_selected_point_as_origin(self) -> None:
        if self.world_result is None:
            self.coordinate_error_var.set("請先完成 DXF 辨識。")
            return
        state = self.selection_state
        if state.selected_candidate_source != "candidate_tree":
            self.coordinate_error_var.set(
                "請在 STEP5 候選點明細表格中選取原點；預覽窗格選點僅用於修正起終點。"
            )
            return
        candidate = self.candidate_point_store.get(
            state.selected_component_id,
            state.selected_candidate_point_id,
        )
        if candidate is None:
            self.coordinate_error_var.set(
                "請先選取構件，再於 STEP5 候選點明細表格選取要作為原點的點。"
            )
            return
        coordinate_system = coordinate_system_from_candidate(candidate)
        self.selected_origin_world = (
            coordinate_system.origin_x,
            coordinate_system.origin_y,
        )
        self.coordinate_mode_var.set("local")
        self._apply_coordinate_settings(show_error=False)

    def _update_set_origin_button_state(self) -> None:
        button = getattr(self, "set_origin_button", None)
        if button is None:
            return
        state = self.selection_state
        candidate = self.candidate_point_store.get(
            state.selected_component_id,
            state.selected_candidate_point_id,
        )
        enabled = (
            self.world_result is not None
            and state.selected_candidate_source == "candidate_tree"
            and candidate is not None
        )
        button.configure(state="normal" if enabled else "disabled")

    def _apply_coordinate_settings(
        self,
        show_error: bool = True,
        *,
        preview_dirty: RenderDirty = RenderDirty.FULL_SCENE,
        rebuild_candidate_tree: bool = True,
    ) -> None:
        if self.world_result is None:
            return
        mode = self.coordinate_mode_var.get()
        if mode == "local" and self.selected_origin_world is None:
            self.coordinate_valid = False
            self.result = self.world_result
            self.coordinate_error_var.set("請先選取一個候選點作為局部原點。")
            self._refresh_result_views(
                preview_dirty=preview_dirty,
                rebuild_candidate_tree=rebuild_candidate_tree,
            )
            return
        if mode == "local":
            coordinate_system = CoordinateSystem(
                "local",
                self.selected_origin_world[0],
                self.selected_origin_world[1],
                "selected_candidate_point",
            )
        else:
            coordinate_system = CoordinateSystem()
        self.coordinate_valid = True
        self.coordinate_error_var.set("")
        self.result = apply_coordinate_system(self.world_result, coordinate_system)
        self._refresh_result_views(
            preview_dirty=preview_dirty,
            rebuild_candidate_tree=rebuild_candidate_tree,
        )

    def _refresh_result_views(
        self,
        *,
        preview_dirty: RenderDirty = RenderDirty.FULL_SCENE,
        rebuild_candidate_tree: bool = True,
    ) -> None:
        if self.result is None:
            return
        previous_review_key = self.selected_review_item_key
        self.candidate_point_store.rebuild(self._all_members())
        if self.selected_member_id and self._selected_member() is None:
            self.selection_state = SelectionState()
            self.selection_controller.state = self.selection_state
        self.problem_records = build_problem_records(self.result)
        self.review_items = build_review_items(self.result, self.problem_records)
        self.review_item_by_key = {item.key: item for item in self.review_items}
        selected_member_item = self._review_item_for_member_id(
            self.selected_member_id
        )
        if selected_member_item is not None:
            self.selected_review_item_key = selected_member_item.key
        elif previous_review_key in self.review_item_by_key:
            self.selected_review_item_key = previous_review_key
        else:
            self.selected_review_item_key = ""
        self.selected_problem = None
        self.focus_member_ids.clear()
        self.focus_handles.clear()
        selected_review_item = self._selected_review_item()
        if (
            selected_review_item is not None
            and selected_review_item.status in {"unresolved", "excluded"}
        ):
            self.focus_handles.update(selected_review_item.source_handles)
        self._update_summary()
        self._update_validation_overview()
        self._refresh_problem_tree()
        self._refresh_member_tree()
        self._update_selected_member_panel(
            rebuild_candidates=rebuild_candidate_tree
        )
        self.debug_text.delete("1.0", "end")
        self.debug_text.insert("1.0", json.dumps(self.result.to_debug_dict(), ensure_ascii=False, indent=2))
        self._update_coordinate_display()
        self._update_import_controls()
        self.render_scheduler.request(preview_dirty)

    def _update_coordinate_display(self) -> None:
        if self.result is None:
            return
        coordinate = self.result.coordinate_system
        if self.coordinate_valid and coordinate.mode == "local":
            mode_text = "Local Coordinates"
            origin_text = f"({coordinate.origin_x:.3f}, {coordinate.origin_y:.3f})"
        elif self.coordinate_valid:
            mode_text = "World Coordinates"
            origin_text = "(0.000, 0.000)"
        else:
            mode_text = "尚未套用（目前預覽 World Coordinates）"
            origin_text = "—"
        self.coordinate_info_var.set(
            f"原始：World Coordinates　Origin：{origin_text}　Local = World - Origin"
        )
        self.preview_coordinate_var.set(
            f"Coordinate System｜Origin {origin_text}｜Current Mode：{mode_text}"
        )

        members = self._all_members()
        if members:
            sample_world = members[0].world_start or members[0].start
        else:
            sample_world = (0.0, 0.0)
        sample_local = (
            coordinate.transform(sample_world)
            if self.coordinate_valid
            else sample_world
        )
        self.coordinate_example_var.set(
            f"範例 World ({sample_world[0]:.3f}, {sample_world[1]:.3f}) → "
            f"Local ({sample_local[0]:.3f}, {sample_local[1]:.3f})"
        )

    def _update_summary(self) -> None:
        if self.result is None:
            return
        self.summary_file_var.set(f"檔名：{self.file_path.name}")
        self.summary_tree.delete(*self.summary_tree.get_children())
        recognized = {
            "strut": len(self.result.struts),
            "waler": len(self.result.walers),
            "brace": len(self.result.braces),
            "column": len(self.result.columns),
            "beam": len(self.result.beams),
            "corner_brace": len(self.result.corner_braces),
            "continuous_wall": "—",
            "auxiliary": 0,
        }
        skipped: Counter[str] = Counter()
        skipped_keys: set[tuple[str, str, str]] = set()
        for item in self.result.entity_debug:
            if item.status not in {"ignored", "unsupported", "error"} or item.entity_type == "TEXT_SUMMARY":
                continue
            key = (item.role, item.handle, item.entity_type)
            if key not in skipped_keys:
                skipped_keys.add(key)
                skipped[item.role] += 1
        role_labels = {
            "strut": "支撐",
            "waler": "圍令",
            "brace": "斜撐",
            "column": "中間柱",
            "beam": "托梁",
            "corner_brace": "角撐",
            "continuous_wall": "連續壁",
            "auxiliary": "輔助線",
        }
        for role in (
            "waler",
            "strut",
            "brace",
            "column",
            "beam",
            "corner_brace",
            "continuous_wall",
            "auxiliary",
        ):
            self.summary_tree.insert(
                "",
                "end",
                values=(
                    role_labels[role],
                    "、".join(self.result.selected_layers.get(role, ())) or "—",
                    self.result.source_entity_counts[role],
                    recognized[role],
                    skipped[role],
                ),
            )
        counts = Counter(message.severity for message in self.result.messages)
        self.summary_totals_var.set(
            f"略過：{sum(skipped.values())}　　Warning：{counts['warning']}　　"
            f"Error：{counts['error']}　　Critical：{counts['critical']}"
        )
        self._refresh_double_support_tree()

    def _refresh_double_support_tree(self) -> None:
        tree = getattr(self, "double_support_tree", None)
        if tree is None:
            return
        tree.delete(*tree.get_children())
        if self.result is None:
            return
        for candidate in self.result.double_support_candidates:
            status = "採用" if candidate.accepted else "未採用"
            if candidate.ambiguous:
                status += "／歧義"
            tree.insert(
                "",
                "end",
                iid=candidate.id,
                values=(
                    status,
                    f"{candidate.first_strut_id} + {candidate.second_strut_id}",
                    f"{candidate.centerline_spacing:.1f}",
                    f"{candidate.angle_difference_deg:.2f}°",
                    f"{candidate.overlap_ratio:.1%}",
                    f"{candidate.confidence:.0%}",
                ),
            )

    def _toggle_selected_double_support(self) -> None:
        if self.result is None:
            return
        selection = self.double_support_tree.selection()
        if not selection:
            return
        candidate_id = str(selection[0])
        candidate = next(
            (
                item
                for item in self.result.double_support_candidates
                if item.id == candidate_id
            ),
            None,
        )
        if candidate is None:
            return
        updated = set_double_support_candidate_accepted(
            self.result.double_support_candidates,
            candidate_id,
            not candidate.accepted,
        )
        identity_result = self.world_result or self.result
        if not hasattr(self, "double_support_decisions"):
            self.double_support_decisions = {}
        previous_by_id = {
            item.id: item for item in self.result.double_support_candidates
        }
        for item in updated:
            previous = previous_by_id.get(item.id)
            if previous is None or previous.accepted == item.accepted:
                continue
            identity = double_support_candidate_identity(identity_result, item)
            if identity is not None:
                self.double_support_decisions[identity] = item.accepted
        if self.world_result is not None:
            coordinate_system = self.result.coordinate_system
            self.world_result = rebuild_component_associations(
                replace(
                    self.world_result,
                    double_support_candidates=updated,
                ),
                self.importer.tolerances,
            )
            self.result = apply_coordinate_system(
                self.world_result,
                coordinate_system,
            )
        else:
            self.result = rebuild_component_associations(
                replace(
                    self.result,
                    double_support_candidates=updated,
                ),
                self.importer.tolerances,
            )
        self._refresh_result_views(
            preview_dirty=RenderDirty.FULL_SCENE,
            rebuild_candidate_tree=False,
        )
        if self.double_support_tree.exists(candidate_id):
            self.double_support_tree.selection_set(candidate_id)

    def _update_validation_overview(self) -> None:
        for child in self.validation_content.winfo_children():
            child.destroy()
        if self.result is None:
            return
        items = list(build_validation_overview(self.result))
        if not self.coordinate_valid:
            items = [
                item
                for item in items
                if not item.text.startswith(("使用局部座標", "使用原始 CAD 座標"))
            ]
            items.insert(
                1,
                ValidationOverviewItem(
                    "error",
                    self.coordinate_error_var.get() or "座標系統尚未套用",
                ),
            )
        columns = 2
        for index, item in enumerate(items):
            icon = self.LEVEL_ICONS[item.level]
            label = self.tk.Label(
                self.validation_content,
                text=f"{icon}  {item.text}",
                foreground=self.LEVEL_COLORS[item.level],
                anchor="w",
                justify="left",
            )
            label.grid(row=index // columns, column=index % columns, sticky="w", padx=(0, 24), pady=2)
        for column in range(columns):
            self.validation_content.columnconfigure(column, weight=1)

    def _refresh_problem_tree(self) -> None:
        if not hasattr(self, "problem_tree"):
            return
        self.problem_tree.delete(*self.problem_tree.get_children())
        self.problem_record_by_iid.clear()
        severity_filter = self.problem_filter_var.get()
        for index, record in enumerate(self.problem_records):
            if severity_filter == "error" and record.severity not in ERROR_SEVERITIES:
                continue
            if severity_filter == "warning" and record.severity != "warning":
                continue
            if self.selected_only_var.get() and self.selected_problem is not None:
                same_member = bool(set(record.member_ids).intersection(self.selected_problem.member_ids))
                same_source = bool(set(record.source_handles).intersection(self.selected_problem.source_handles))
                if not (same_member or same_source):
                    continue
            elif self.selected_only_var.get():
                continue
            iid = f"problem_{index}"
            self.problem_record_by_iid[iid] = record
            self.problem_tree.insert(
                "",
                "end",
                iid=iid,
                values=(record.severity.upper(), record.code, record.component, record.description),
                tags=(record.severity,),
            )

    def _on_problem_selected(self, _event: Any = None) -> None:
        selection = self.problem_tree.selection()
        if not selection:
            return
        record = self.problem_record_by_iid.get(selection[0])
        if record is None:
            return
        self._focus_problem_record(record)
        if self.selected_only_var.get():
            self._refresh_problem_tree()

    def _on_detail_problem_activated(self, _event: Any = None) -> None:
        selection = self.detail_problem_tree.selection()
        if not selection:
            return
        record = self.detail_problem_record_by_iid.get(selection[0])
        if record is not None:
            self._focus_problem_record(record)

    def _focus_problem_record(self, record: ProblemRecord) -> None:
        """Apply the shared STEP4/STEP7 preview-focus behavior."""

        self.selected_problem = record
        self.focus_member_ids = set(record.member_ids)
        self.focus_handles = set(record.source_handles)
        if record.member_ids:
            selected_member_id = self.selected_member_id
            target_member_id = (
                selected_member_id
                if selected_member_id in record.member_ids
                else record.member_ids[0]
            )
            self._select_member(
                target_member_id,
                refit=True,
                clear_problem=False,
                source="error_list",
            )
        self.preview_view_bounds = None
        self.preview_fit_all = False
        self._open_preview_window()
        self.render_scheduler.request(RenderDirty.FULL_SCENE)

    def _update_import_controls(self) -> None:
        if self.result is None:
            return
        if not self.coordinate_valid:
            self.apply_button.configure(state="disabled", text="不可匯入")
            self.status_var.set(
                f"✗ {self.coordinate_error_var.get() or '座標系統尚未套用'}；請完成座標系統設定。"
            )
            return
        counts = Counter(message.severity for message in self.result.messages)
        error_count = counts["error"] + counts["critical"]
        if error_count:
            self.apply_button.configure(state="disabled", text="不可匯入")
            self.status_var.set(f"✗ 發現 {error_count} 項阻擋錯誤，請先修正問題列表中的 Error／Critical。")
        elif counts["warning"]:
            self.apply_button.configure(state="normal", text="仍要完成匯入")
            self.status_var.set(f"⚠ 目前有 {counts['warning']} 項警告；建議先修正警告後再匯入。")
        else:
            self.apply_button.configure(state="normal", text="完成匯入")
            self.status_var.set("✓ 圖層與工程模型檢核通過，可以匯入 Solver。")

    def _toggle_developer_mode(self) -> None:
        self.developer_expanded = not self.developer_expanded
        if self.developer_expanded:
            self.developer_button.configure(text="▼ 開發者模式（原始 JSON）")
            self.developer_frame.pack(fill="both", padx=6, pady=(0, 6))
        else:
            self.developer_frame.pack_forget()
            self.developer_button.configure(text="▶ 開發者模式（原始 JSON）")

    def _all_members(
        self,
    ) -> tuple[Waler | Strut | Brace | AuxiliaryComponent, ...]:
        if self.result is None:
            return ()
        return (
            *self.result.walers,
            *self.result.struts,
            *self.result.braces,
            *self.result.columns,
            *self.result.beams,
            *self.result.corner_braces,
        )

    def _selected_member(
        self,
    ) -> Waler | Strut | Brace | AuxiliaryComponent | None:
        return self._member_by_id(self.selected_member_id)

    def _review_item_for_member_id(self, member_id: str) -> ReviewItem | None:
        if not member_id:
            return None
        return next(
            (
                item
                for item in getattr(self, "review_items", ())
                if item.member_id == member_id
            ),
            None,
        )

    def _selected_review_item(self) -> ReviewItem | None:
        item = getattr(self, "review_item_by_key", {}).get(
            getattr(self, "selected_review_item_key", "")
        )
        if item is not None:
            return item
        return self._review_item_for_member_id(self.selected_member_id)

    def _excluded_source_for_review_item(
        self,
        item: ReviewItem,
    ) -> ExcludedSource | None:
        identity = canonical_source_identity(item.role, item.source_handles)
        return next(
            (
                source
                for source in self.excluded_sources
                if source.identity == identity
            ),
            None,
        )

    def _source_exclusion_disabled_reason(self, item: ReviewItem | None) -> str:
        if item is None:
            return "請先選取 Formal、待修或已排除來源。"
        if not item.role or not normalize_source_handles(item.source_handles):
            return "此項目沒有可安全識別的 DXF 來源，無法使用來源排除。"
        if item.status == "excluded":
            return ""
        conflicts = shared_handle_conflicts(item, self.review_items)
        if not conflicts:
            return ""
        details = "；".join(
            f"Handle {conflict.handle} 同時由 {', '.join(conflict.owner_labels)} 使用"
            for conflict in conflicts
        )
        return f"此來源有共用 Handle，不能安全單獨排除：{details}。"

    @staticmethod
    def _source_geometry_signature(result: DXFImportResult) -> tuple[Any, ...]:
        return tuple(
            (
                geometry.role,
                geometry.source_handle,
                geometry.points,
                geometry.closed,
                geometry.source_layer,
                geometry.source_entity_type,
            )
            for geometry in result.source_geometry
        )

    def _stage_source_exclusion_change(
        self,
        candidate_exclusions: Sequence[ExcludedSource],
    ) -> dict[str, Any]:
        if self.world_result is None or self.result is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        normalized = normalize_excluded_sources(candidate_exclusions)
        overrides = [*capture_manual_overrides(self.world_result)]
        overrides.extend(
            source.manual_override
            for source in self.excluded_sources
            if source.manual_override is not None
        )
        overrides.extend(
            source.manual_override
            for source in normalized
            if source.manual_override is not None
        )
        staged_world, replay_report = self._recognize_staged_result(
            normalized,
            overrides,
            layer_roles=self.world_result.layer_classification,
        )
        if staged_world.source_fingerprint != self.world_result.source_fingerprint:
            raise DXFImportError("Staging 的 DXF source fingerprint 不一致。")
        if self._source_geometry_signature(staged_world) != self._source_geometry_signature(
            self.world_result
        ):
            raise DXFImportError("Staging 未完整保留原始 DXF source geometry。")
        staged_result = apply_coordinate_system(
            staged_world,
            self.result.coordinate_system,
        )
        staged_records = build_problem_records(staged_result)
        staged_review_items = build_review_items(staged_result, staged_records)
        return {
            "excluded_sources": normalized,
            "world_result": staged_world,
            "result": staged_result,
            "problem_records": staged_records,
            "review_items": staged_review_items,
            "manual_replay": replay_report,
        }

    @staticmethod
    def _review_item_identity(item: ReviewItem) -> str:
        return canonical_source_identity(item.role, item.source_handles)

    def _stage_review_item_for_identity(
        self,
        stage: Mapping[str, Any],
        identity: str,
        *,
        excluded: bool,
    ) -> ReviewItem | None:
        return next(
            (
                item
                for item in stage.get("review_items", ())
                if self._review_item_identity(item) == identity
                and (item.status == "excluded") == excluded
            ),
            None,
        )

    def _format_source_exclusion_impact(
        self,
        item: ReviewItem,
        stage: Mapping[str, Any],
        *,
        restoring: bool,
    ) -> str:
        assert self.result is not None
        staged_result = stage["result"]
        before_members = sum(result_member_counts(self.result).values())
        after_members = sum(result_member_counts(staged_result).values())
        before_severity = result_severity_counts(self.result)
        after_severity = result_severity_counts(staged_result)
        warning_delta = after_severity.get("warning", 0) - before_severity.get(
            "warning", 0
        )
        error_delta = (
            after_severity.get("error", 0)
            + after_severity.get("critical", 0)
            - before_severity.get("error", 0)
            - before_severity.get("critical", 0)
        )
        replay: ManualReplayReport = stage["manual_replay"]
        verb = "復原" if restoring else "排除"
        lines = [
            f"將{verb}：{item.display_id}",
            "來源 Handle：" + ", ".join(normalize_source_handles(item.source_handles)),
            "",
            "此操作不會修改或刪除原始 DXF entity。",
            "",
            "重新計算後：",
            f"• 正式構件 {before_members} → {after_members}（{after_members - before_members:+d}）",
            f"• Warning 變化：{warning_delta:+d}",
            f"• Error／Critical 變化：{error_delta:+d}",
            f"• 人工輸入成功保留：{len(replay.preserved)}",
            f"• 人工輸入需要重新確認：{len(replay.needs_review)}",
            f"• 因來源仍被排除而停用：{len(replay.disabled)}",
        ]
        if replay.needs_review:
            lines.extend(("", "需要重新確認：", *(
                f"• {label}" for label in replay.needs_review
            )))
        if replay.disabled:
            lines.extend(("", "目前停用但已保留快照：", *(
                f"• {label}" for label in replay.disabled
            )))
        return "\n".join(lines)

    def _commit_source_exclusion_stage(
        self,
        stage: Mapping[str, Any],
        selected_key: str,
    ) -> None:
        self._clear_waler_adjustment_preview()
        self.excluded_sources = tuple(stage["excluded_sources"])
        self.world_result = stage["world_result"]
        self.result = stage["result"]
        self.selected_review_item_key = selected_key
        self.selection_state = SelectionState(selection_source="component_tree")
        self.selection_controller.state = self.selection_state
        self.preview_view_bounds = None
        self.preview_fit_all = False
        self._refresh_result_views()

    def _on_source_exclusion_action(self) -> None:
        from tkinter import messagebox

        item = self._selected_review_item()
        disabled_reason = self._source_exclusion_disabled_reason(item)
        if item is None or disabled_reason:
            if disabled_reason:
                messagebox.showwarning(
                    "DXF 來源排除",
                    disabled_reason,
                    parent=self.window,
                )
            return
        identity = self._review_item_identity(item)
        restoring = item.status == "excluded"
        try:
            if restoring:
                candidate_exclusions = tuple(
                    source
                    for source in self.excluded_sources
                    if source.identity != identity
                )
            else:
                candidate_exclusions = (
                    *self.excluded_sources,
                    excluded_source_from_review_item(item, self.world_result),
                )
            stage = self._stage_source_exclusion_change(candidate_exclusions)
        except Exception as exc:
            error_text = (
                str(exc)
                if isinstance(exc, DXFImportError)
                else f"{type(exc).__name__}: {exc}"
            )
            messagebox.showerror(
                "DXF 來源排除 staging 失敗",
                f"目前辨識結果完全未變更。\n\n{error_text}",
                parent=self.window,
            )
            return
        title = "確認復原 DXF 來源" if restoring else "確認排除 DXF 來源"
        if not messagebox.askyesno(
            title,
            self._format_source_exclusion_impact(
                item,
                stage,
                restoring=restoring,
            ),
            parent=self.window,
        ):
            return
        selected = self._stage_review_item_for_identity(
            stage,
            identity,
            excluded=not restoring,
        )
        self._commit_source_exclusion_stage(
            stage,
            selected.key if selected is not None else "",
        )
        action = "復原" if restoring else "排除"
        self.source_exclusion_status_var.set(
            f"已{action} {item.display_id}；工程關聯與 Validation 已重新計算。"
        )

    def _member_by_id(
        self,
        member_id: str,
    ) -> Waler | Strut | Brace | AuxiliaryComponent | None:
        return next(
            (member for member in self._all_members() if member.id == member_id),
            None,
        )

    @staticmethod
    def _preview_source_geometry(
        result: DXFImportResult,
    ) -> tuple[SourceGeometry, ...]:
        """Return source geometry from user-selected, non-ignored layers only."""

        return tuple(
            geometry
            for geometry in result.source_geometry
            if geometry.role != "ignore"
        )

    @classmethod
    def _visible_preview_source_geometry(
        cls,
        result: DXFImportResult,
        *,
        show_source: bool,
        show_auxiliary: bool,
        focus_handles: Sequence[str] = (),
    ) -> tuple[SourceGeometry, ...]:
        """Apply independent visibility rules to engineering and auxiliary lines."""

        focused = set(focus_handles)
        return tuple(
            geometry
            for geometry in cls._preview_source_geometry(result)
            if (
                show_auxiliary
                if geometry.role == "auxiliary"
                else show_source or geometry.source_handle in focused
            )
        )

    @staticmethod
    def _member_role(
        member: Waler | Strut | Brace | AuxiliaryComponent,
    ) -> tuple[str, str]:
        if isinstance(member, Waler):
            return "waler", "圍令"
        if isinstance(member, Strut):
            return "strut", "支撐"
        if isinstance(member, Brace):
            return "brace", "斜撐"
        if isinstance(member, Column):
            return "column", "中間柱"
        if isinstance(member, Beam):
            return "beam", "托梁"
        return "corner_brace", "角撐"

    def _refresh_member_tree(self) -> None:
        if not hasattr(self, "member_tree"):
            return
        self._updating_member_tree = True
        try:
            self.member_tree.delete(*self.member_tree.get_children())
            self.member_by_tree_iid.clear()
            if not hasattr(self, "member_tree_iid_by_member_id"):
                self.member_tree_iid_by_member_id = {}
            self.member_tree_iid_by_member_id.clear()
            if not hasattr(self, "review_item_by_tree_iid"):
                self.review_item_by_tree_iid = {}
            self.review_item_by_tree_iid.clear()
            if self.result is None:
                return
            groups = (
                ("waler", "圍令"),
                ("strut", "支撐"),
                ("brace", "斜撐"),
                ("column", "中間柱"),
                ("beam", "托梁"),
                ("corner_brace", "角撐"),
                ("unknown", "未分類來源"),
            )
            selected_iid = ""
            for role, label in groups:
                review_items = tuple(
                    item
                    for item in self.review_items
                    if item.role == role and item.status != "excluded"
                )
                if not review_items:
                    continue
                group_iid = f"group_{role}"
                self.member_tree.insert(
                    "",
                    "end",
                    iid=group_iid,
                    text=self._review_group_text(label, review_items),
                    open=True,
                )
                for index, item in enumerate(review_items):
                    iid = f"review_{role}_{index}"
                    tags = (
                        (item.highest_severity,)
                        if item.highest_severity != "success"
                        else ()
                    )
                    self.member_tree.insert(
                        group_iid,
                        "end",
                        iid=iid,
                        text=self._review_item_text(item),
                        tags=tags,
                    )
                    self.review_item_by_tree_iid[iid] = item.key
                    if item.member_id:
                        self.member_by_tree_iid[iid] = item.member_id
                        self.member_tree_iid_by_member_id[item.member_id] = iid
                    if item.key == self.selected_review_item_key:
                        selected_iid = iid
            excluded_items = tuple(
                item for item in self.review_items if item.status == "excluded"
            )
            if excluded_items:
                group_iid = "group_excluded"
                self.member_tree.insert(
                    "",
                    "end",
                    iid=group_iid,
                    text=f"已排除來源（{len(excluded_items)}）",
                    open=True,
                    tags=("excluded",),
                )
                for index, item in enumerate(excluded_items):
                    iid = f"review_excluded_{index}"
                    self.member_tree.insert(
                        group_iid,
                        "end",
                        iid=iid,
                        text=self._review_item_text(item),
                        tags=("excluded",),
                    )
                    self.review_item_by_tree_iid[iid] = item.key
                    if item.key == self.selected_review_item_key:
                        selected_iid = iid
            if selected_iid:
                self.member_tree_selection.select(selected_iid)
        finally:
            self._updating_member_tree = False

    @classmethod
    def _review_item_text(cls, item: ReviewItem) -> str:
        if item.status == "excluded":
            return f"✕ {item.display_id}"
        icon = (
            cls.LEVEL_ICONS.get(item.highest_severity, "")
            if item.highest_severity != "success"
            else ""
        )
        manual = " ＊" if item.member_id and item.selection_source != "auto" else ""
        problem_count = f" ({item.problem_count})" if item.problem_count else ""
        prefix = f"{icon} " if icon else ""
        return f"{prefix}{item.display_id}{manual}{problem_count}"

    @staticmethod
    def _review_group_text(
        label: str,
        items: Sequence[ReviewItem],
    ) -> str:
        error_count = sum(
            item.highest_severity in ERROR_SEVERITIES for item in items
        )
        warning_count = sum(
            item.highest_severity == "warning" for item in items
        )
        summary = []
        if error_count:
            summary.append(f"✗{error_count}")
        if warning_count:
            summary.append(f"⚠{warning_count}")
        suffix = f"｜{' '.join(summary)}" if summary else ""
        return f"{label}（{len(items)}）{suffix}"

    def _candidate_filter_accepts(self, candidate: CandidatePoint) -> bool:
        member = self._selected_member()
        if member is None:
            return False
        filter_mode = self.candidate_filter_var.get()
        if filter_mode in {"start", "end"}:
            return filter_mode in candidate.valid_for
        if filter_mode == "recommended":
            return bool(
                candidate.recommended_for
                or candidate.id
                in {
                    member.recommended_start_point_id,
                    member.recommended_end_point_id,
                }
            )
        return True

    def _candidate_row_values(
        self,
        member: Waler | Strut | Brace | AuxiliaryComponent,
        candidate: CandidatePoint,
    ) -> tuple[str, str, str, str, str]:
        state = self.selection_state
        statuses: list[str] = []
        if candidate.id == member.recommended_start_point_id:
            statuses.append("推薦起點")
        if candidate.id == member.recommended_end_point_id:
            statuses.append("推薦終點")
        if candidate.id == member.selected_start_point_id:
            statuses.append("正式起點")
        if candidate.id == member.selected_end_point_id:
            statuses.append("正式終點")
        if candidate.id == state.pending_start_point_id:
            statuses.append("待套用起點")
        if candidate.id == state.pending_end_point_id:
            statuses.append("待套用終點")
        if candidate.id == state.selected_candidate_point_id:
            statuses.append("目前選取")
        marker = (
            "●"
            if candidate.id
            in {state.pending_start_point_id, state.pending_end_point_id}
            else "○"
        )
        return (
            f"{marker} {candidate.id}",
            candidate.label,
            f"{candidate.world_point[0]:.3f}, {candidate.world_point[1]:.3f}",
            f"{candidate.local_point[0]:.3f}, {candidate.local_point[1]:.3f}",
            "、".join(statuses) or "候選",
        )

    def _rebuild_candidate_tree(self) -> None:
        if not hasattr(self, "candidate_tree_adapter"):
            return
        member = self._selected_member()
        if member is None:
            self.candidate_tree_adapter.rebuild("", (), lambda _point: ())
            self.performance_diagnostics.candidate_tree_rebuilds += 1
            self._update_set_origin_button_state()
            return
        points = self.candidate_point_store.component_points(member.id)
        self.candidate_tree_adapter.rebuild(
            member.id,
            points,
            lambda point: self._candidate_row_values(member, point),
            self._candidate_filter_accepts,
        )
        self.performance_diagnostics.candidate_tree_rebuilds += 1
        self.candidate_tree_adapter.sync_selection(
            self.selection_state.selected_candidate_point_id
        )
        self.candidate_tree_adapter.set_hover(
            self.selection_state.hovered_candidate_point_id
        )
        self._update_set_origin_button_state()

    def _update_candidate_tree_rows(self) -> None:
        member = self._selected_member()
        if member is None or not hasattr(self, "candidate_tree_adapter"):
            return
        for point in self.candidate_point_store.component_points(member.id):
            self.candidate_tree_adapter.update_row(
                point.id,
                self._candidate_row_values(member, point),
            )

    def _update_selected_member_panel(
        self,
        *,
        rebuild_candidates: bool = True,
    ) -> None:
        if not hasattr(self, "candidate_tree"):
            return
        member = self._selected_member()
        review_item = self._selected_review_item()
        if member is None:
            if (
                review_item is not None
                and review_item.status in {"unresolved", "excluded"}
            ):
                self._update_unresolved_source_panel(review_item)
            else:
                self.preview_selected_member_var.set("目前構件：—")
                for variable in self.member_info_vars.values():
                    variable.set("—")
            self.candidate_detail_var.set("候選點：—")
            self._update_material_spec_panel(None)
            self._update_waler_contact_panel(None)
            if rebuild_candidates:
                self._rebuild_candidate_tree()
            self._update_review_issue_panel(review_item)
            return
        _role, role_label = self._member_role(member)
        self.preview_selected_member_var.set(
            f"目前構件：{member.id}｜{role_label}｜圖層 {member.source_layer}"
        )
        values = {
            "id": member.id,
            "status": "正式構件",
            "role": role_label,
            "layer": member.source_layer,
            "entities": (
                f"{', '.join(member.source_entity_types)}\n"
                f"Handle: {', '.join(member.source_handles)}"
            ),
            "method": (
                f"{member.recognition_method}｜"
                f"{self._selection_source_label(member.selection_source)}"
            ),
            "reason": "—",
            "source_width": (
                f"{member.source_width:.3f}"
                if member.source_width > 0.0
                else "—"
            ),
            "start_x": f"{member.start[0]:.3f}",
            "start_y": f"{member.start[1]:.3f}",
            "end_x": f"{member.end[0]:.3f}",
            "end_y": f"{member.end[1]:.3f}",
        }
        for key, value in values.items():
            self.member_info_vars[key].set(value)
        self._update_material_spec_panel(member)
        self._update_waler_contact_panel(member)
        if rebuild_candidates:
            self._rebuild_candidate_tree()
        else:
            self._update_candidate_tree_rows()
        self._update_candidate_detail_panel()
        self._update_review_issue_panel(review_item)

    def _update_unresolved_source_panel(self, item: ReviewItem) -> None:
        role_labels = {
            "waler": "圍令",
            "strut": "支撐",
            "brace": "斜撐",
            "column": "中間柱",
            "beam": "托梁",
            "corner_brace": "角撐",
            "unknown": "未分類來源",
        }
        layer_text = "、".join(item.source_layers) or "—"
        entity_text = "、".join(item.source_entity_types) or "—"
        handle_text = ", ".join(item.source_handles) or "—"
        self.preview_selected_member_var.set(
            f"目前來源：{item.display_id}｜{role_labels.get(item.role, item.role or '未分類')}"
        )
        excluded = item.status == "excluded"
        values = {
            "id": item.display_id_before_exclusion or item.display_id,
            "status": "已排除" if excluded else "待修來源",
            "role": role_labels.get(item.role, item.role or "未分類來源"),
            "layer": layer_text,
            "entities": f"{entity_text}\nHandle: {handle_text}",
            "method": (
                "已停止參與工程辨識"
                if excluded
                else "尚未形成正式工程構件"
            ),
            "reason": item.exclusion_reason or "—",
            "source_width": "—",
            "start_x": "—（無 active 正式工程幾何）",
            "start_y": "—（無 active 正式工程幾何）",
            "end_x": "—（無 active 正式工程幾何）",
            "end_y": "—（無 active 正式工程幾何）",
        }
        for key, value in values.items():
            self.member_info_vars[key].set(value)

    def _update_review_issue_panel(self, item: ReviewItem | None) -> None:
        if not hasattr(self, "detail_problem_tree"):
            return
        self.detail_problem_tree.delete(
            *self.detail_problem_tree.get_children()
        )
        self.detail_problem_record_by_iid.clear()
        if item is None:
            self.detail_problem_empty_var.set("請先選取檢核項目。")
            self.detail_guidance_var.set("")
            self._update_source_exclusion_action_state(None)
            return
        for index, record in enumerate(item.problems):
            iid = f"detail_problem_{index}"
            self.detail_problem_record_by_iid[iid] = record
            self.detail_problem_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    record.severity.upper(),
                    record.code,
                    record.description,
                ),
                tags=(record.severity,),
            )
        if item.problems:
            self.detail_problem_empty_var.set(
                f"共 {item.problem_count} 項；雙擊問題或按 Enter 可在預覽中定位。"
            )
        else:
            self.detail_problem_empty_var.set("✓ 此構件目前沒有檢核問題")
        guidance = review_item_guidance(item)
        self.detail_guidance_var.set(
            "\n".join(f"• {text}" for text in guidance)
            if guidance
            else "目前不需要額外處理。"
        )
        self._update_source_exclusion_action_state(item)

    def _update_source_exclusion_action_state(
        self,
        item: ReviewItem | None,
    ) -> None:
        button = getattr(self, "source_exclusion_button", None)
        status_var = getattr(self, "source_exclusion_status_var", None)
        if button is None or status_var is None:
            return
        reason = self._source_exclusion_disabled_reason(item)
        restoring = item is not None and item.status == "excluded"
        button.configure(
            text="復原此來源" if restoring else "排除此 DXF 來源",
            state="disabled" if reason else "normal",
        )
        status_var.set(reason)

    @staticmethod
    def _dimension_text(value: float | None) -> str:
        return "" if value is None else f"{value:g}"

    def _update_material_spec_panel(
        self,
        member: Waler | Strut | Brace | AuxiliaryComponent | None,
    ) -> None:
        if not hasattr(self, "material_spec_frame"):
            return
        if not isinstance(member, (Waler, Strut)):
            self.material_spec_frame.grid_remove()
            return
        self.material_spec_frame.grid()
        usage = "圍令" if isinstance(member, Waler) else "支撐"
        options = material_spec_options(self.material_specs, usage)
        self.material_spec_combo.configure(values=("", *options))
        self.material_spec_var.set(member.material_spec)
        if member.material_spec_source == "auto_width":
            self.material_spec_status_var.set(
                f"已依圖面寬度 {member.source_width:g} mm 自動辨認；可人工改選。"
            )
        elif member.material_spec_source == "manual":
            self.material_spec_status_var.set("已採用 STEP4 人工選擇。")
        elif member.source_width <= 0.0:
            self.material_spec_status_var.set("圖面沒有可靠寬度，請人工選擇。")
        else:
            self.material_spec_status_var.set(
                f"圖面寬度 {member.source_width:g} mm 無法唯一對應材料規格，請人工選擇。"
            )

    def _on_material_spec_selected(self, _event: Any = None) -> None:
        member = self._selected_member()
        if not isinstance(member, (Waler, Strut)) or self.world_result is None:
            return
        try:
            self.world_result = self.import_model_controller.apply_material_spec(
                self.world_result,
                member.id,
                self.material_spec_var.get(),
            )
        except DXFImportError as exc:
            self.material_spec_status_var.set(str(exc))
            return
        self._apply_coordinate_settings(
            show_error=False,
            preview_dirty=RenderDirty.DETAIL_PANEL,
            rebuild_candidate_tree=False,
        )

    def _update_waler_contact_panel(
        self,
        member: Waler | Strut | Brace | AuxiliaryComponent | None,
    ) -> None:
        if not hasattr(self, "waler_contact_frame"):
            return
        if not isinstance(member, Waler) or self.world_result is None:
            self.waler_contact_frame.grid_remove()
            self._contact_panel_waler_id = ""
            self._clear_waler_adjustment_preview()
            return
        self.waler_contact_frame.grid()
        self.waler_contact_title_var.set(f"{member.id}｜接觸位置調整")
        if self._contact_panel_waler_id == member.id:
            return
        review = next(
            (
                item
                for item in self.world_result.waler_contact_reviews
                if item.waler_id == member.id
            ),
            None,
        )
        self._contact_panel_waler_id = member.id
        self._clear_waler_adjustment_preview()
        if review is None:
            self.waler_contact_status_var.set("缺少 Waler contact review state。")
            return
        for key, variable in self.waler_contact_value_vars.items():
            variable.set(self._dimension_text(getattr(review, key)))
        if review.support_normal_world is None:
            self.waler_contact_status_var.set(
                "無可靠支撐側證據；可預覽問題，但不能套用。"
            )
        elif review.backfill_recognition_method:
            self.waler_contact_status_var.set(
                "背填圖面值已由連續壁內側線至圍令外側線量得"
                f"（Handle: {review.continuous_wall_source_handle}）。"
            )
        else:
            self.waler_contact_status_var.set(
                "未找到可唯一量測的連續壁內側線／圍令外側線，請人工輸入背填厚度。"
            )

    def _on_waler_contact_value_changed(self, _event: Any = None) -> None:
        self._clear_waler_adjustment_preview()
        self.waler_contact_status_var.set("數值已變更，請重新預覽。")

    def _clear_waler_adjustment_preview(self) -> None:
        self.waler_adjustment_preview_plan = None
        if hasattr(self, "waler_contact_apply_button"):
            self.waler_contact_apply_button.configure(state="disabled")
        if hasattr(self, "waler_contact_displacement_var"):
            self.waler_contact_displacement_var.set("接觸位置調整：—")
            self.waler_contact_impact_var.set("影響：—")
        canvas = getattr(self, "canvas", None)
        if canvas is not None:
            stale = set(self._waler_adjustment_overlay_items)
            for item_id in self._waler_adjustment_overlay_items:
                try:
                    canvas.delete(item_id)
                except self.tk.TclError:
                    pass
            if hasattr(self, "preview_scene"):
                self.preview_scene.temporary_line_items[:] = [
                    item_id
                    for item_id in self.preview_scene.temporary_line_items
                    if item_id not in stale
                ]
        self._waler_adjustment_overlay_items.clear()

    def _waler_contact_dimensions(self) -> dict[str, str]:
        return {
            key: variable.get().strip()
            for key, variable in self.waler_contact_value_vars.items()
        }

    def _preview_waler_contact_adjustment(self) -> None:
        from tkinter import messagebox

        member = self._selected_member()
        if not isinstance(member, Waler) or self.world_result is None:
            return
        try:
            plan = self.import_model_controller.preview_waler_contact_adjustment(
                self.world_result,
                member.id,
                **self._waler_contact_dimensions(),
            )
        except DXFImportError as exc:
            self._clear_waler_adjustment_preview()
            self.waler_contact_status_var.set(str(exc))
            messagebox.showerror("Waler 接觸位置調整", str(exc), parent=self.window)
            return
        self.waler_adjustment_preview_plan = plan
        self.waler_contact_displacement_var.set(
            f"接觸位置調整：{plan.contact_displacement:+.3f} mm"
        )
        self.waler_contact_impact_var.set(
            "影響：Strut {0} 支、Brace {1} 支、CornerBrace {2} 支、"
            "Column {3} 支、Beam {4} 支".format(
                len(plan.strut_changes),
                len(plan.brace_changes),
                len(plan.corner_brace_changes),
                len(plan.changed_column_ids),
                len(plan.changed_beam_ids),
            )
        )
        errors = [
            item.message
            for item in plan.messages
            if item.severity in ERROR_SEVERITIES
        ]
        self.waler_contact_status_var.set(
            errors[0]
            if errors
            else (
                "預覽完成；套用時會從最新正式資料重新計算。"
                if plan.can_apply
                else "目前 DXF 結果仍有 blocking error，不能套用。"
            )
        )
        self.waler_contact_apply_button.configure(
            state="normal" if plan.can_apply else "disabled"
        )
        self._draw_waler_adjustment_overlay()
        self._show_waler_adjustment_plan(plan)

    def _show_waler_adjustment_plan(
        self, plan: WalerContactAdjustmentPlan
    ) -> None:
        from tkinter import scrolledtext

        preview = self.tk.Toplevel(self.window)
        preview.title(f"{plan.waler_id} 接觸位置調整預覽")
        preview.geometry("760x620")
        text_widget = scrolledtext.ScrolledText(
            preview, wrap="word", font=("Microsoft JhengHei", 10)
        )
        text_widget.pack(fill="both", expand=True, padx=8, pady=8)
        text_widget.insert("1.0", format_adjustment_plan(plan))
        text_widget.configure(state="disabled")
        self.ttk.Button(preview, text="關閉", command=preview.destroy).pack(
            pady=(0, 8)
        )

    def _apply_waler_contact_adjustment(self) -> None:
        from tkinter import messagebox

        member = self._selected_member()
        if not isinstance(member, Waler) or self.world_result is None:
            return
        try:
            # Deliberately ignore preview coordinates: the controller builds a
            # fresh plan from the current formal world_result before commit.
            self.world_result = (
                self.import_model_controller.apply_waler_contact_adjustment(
                    self.world_result,
                    member.id,
                    **self._waler_contact_dimensions(),
                )
            )
        except DXFImportError as exc:
            self.waler_contact_status_var.set(str(exc))
            self.waler_contact_apply_button.configure(state="disabled")
            messagebox.showerror("Waler 接觸位置調整", str(exc), parent=self.window)
            return
        self._clear_waler_adjustment_preview()
        self._contact_panel_waler_id = ""
        self._apply_coordinate_settings(show_error=False)
        self.selection_controller.synchronize_formal_member()
        self.waler_contact_status_var.set("已一次套用全部連動幾何與衍生資料。")

    def _update_candidate_detail_panel(self) -> None:
        state = self.selection_state
        point_id = (
            state.hovered_candidate_point_id
            or state.selected_candidate_point_id
        )
        candidate = self.candidate_point_store.get(
            state.selected_component_id,
            point_id,
        )
        self.candidate_detail_var.set(
            self._candidate_detail_text(candidate)
            if candidate is not None
            else "候選點：—"
        )

    def _on_candidate_filter_changed(self) -> None:
        self._rebuild_candidate_tree()
        self.render_scheduler.request(
            RenderDirty.CANDIDATE_LAYER
            | RenderDirty.CANDIDATE_SELECTION
            | RenderDirty.TEMP_LINE
        )

    def _on_member_selected(self, _event: Any = None) -> None:
        if self._updating_member_tree or self.member_tree_selection.syncing:
            return
        selection = self.member_tree.selection()
        if not selection:
            return
        review_key = getattr(self, "review_item_by_tree_iid", {}).get(
            selection[0],
            "",
        )
        review_item = getattr(self, "review_item_by_key", {}).get(review_key)
        if (
            review_item is not None
            and review_item.status in {"unresolved", "excluded"}
        ):
            self._select_unresolved_review_item(review_item)
            return
        member_id = (
            review_item.member_id
            if review_item is not None
            else self.member_by_tree_iid.get(selection[0], "")
        )
        if not member_id:
            return
        self._select_member(
            member_id,
            refit=True,
            clear_problem=True,
            source="component_tree",
        )

    def _select_unresolved_review_item(self, item: ReviewItem) -> None:
        self.selected_problem = None
        self.selected_review_item_key = item.key
        self.focus_member_ids.clear()
        self.focus_handles = set(item.source_handles)
        revision = getattr(self.selection_state, "revision", 0) + 1
        self.selection_state = SelectionState(
            selection_source="component_tree",
            revision=revision,
        )
        self.selection_controller.state = self.selection_state
        if self.selected_only_var.get():
            self.selected_only_var.set(False)
            self._refresh_problem_tree()
        if hasattr(self, "candidate_action_status_var"):
            self.candidate_action_status_var.set(
                (
                    "此來源已排除；可於 STEP4 使用「復原此來源」。"
                    if item.status == "excluded"
                    else "此來源尚未形成正式構件；STEP5、STEP6 目前不適用。"
                )
            )
        self._update_selected_member_panel()
        self.preview_view_bounds = None
        self.preview_fit_all = False
        self._open_preview_window()
        self.render_scheduler.request(RenderDirty.FULL_SCENE)

    def _select_member(
        self,
        member_id: str,
        *,
        refit: bool,
        clear_problem: bool,
        source: str = "programmatic",
    ) -> None:
        if clear_problem:
            self.selected_problem = None
            self.focus_member_ids.clear()
            self.focus_handles.clear()
            if self.selected_only_var.get():
                self.selected_only_var.set(False)
                self._refresh_problem_tree()
        review_item = self._review_item_for_member_id(member_id)
        review_changed = bool(
            review_item is not None
            and review_item.key
            != getattr(self, "selected_review_item_key", "")
        )
        if review_item is not None:
            self.selected_review_item_key = review_item.key
        changed = self.selection_controller.select_component(member_id, source)
        if changed and hasattr(self, "candidate_action_status_var"):
            self.candidate_action_status_var.set(
                "單擊候選點只會預覽；請先選擇要修改起點或終點。"
            )
        if changed or review_changed:
            # Keep STEP4/STEP5 responsive even when refitting a large DXF such as
            # Y29.  The scheduled render still updates the preview overlays, but
            # the form must not wait for a full-scene redraw before reflecting
            # the component selected in STEP3.
            self._update_selected_member_panel()
        if refit and (changed or review_changed):
            self.preview_view_bounds = None
            self.preview_fit_all = False
            self.render_scheduler.request(RenderDirty.FULL_SCENE)
        if changed and hasattr(self, "candidate_action_status_var"):
            self.candidate_action_status_var.set(
                "可直接在預覽圖點擊藍色起點或紅色終點，再點選新的黃色候選點。"
            )
        self._update_set_origin_button_state()

    @staticmethod
    def _selection_source_label(source: str) -> str:
        return {
            "auto": "自動辨識",
            "manual_candidate_points": "人工候選點",
            "cad_manual": "CAD 人工指定",
            "waler_contact_adjustment": "Waler 接觸位置調整",
        }.get(source, source or "自動辨識")

    def _candidate_detail_text(self, candidate: CandidatePoint) -> str:
        return (
            f"{candidate.id}｜{candidate.label}\n"
            f"World：({candidate.world_point[0]:.3f}, {candidate.world_point[1]:.3f})　"
            f"Local：({candidate.local_point[0]:.3f}, {candidate.local_point[1]:.3f})"
        )

    def _on_candidate_point_selected(self, _event: Any = None) -> None:
        if self.world_result is None or self.candidate_tree_adapter.syncing:
            return
        selection = self.candidate_tree.selection()
        if not selection or not self.selected_member_id:
            return
        point_id = self.candidate_tree_adapter.point_id_for_iid(selection[0])
        if not point_id:
            return
        self._select_candidate_point(
            point_id,
            center_if_hidden=True,
            source="candidate_tree",
        )
        self._update_set_origin_button_state()

    def _select_candidate_point(
        self,
        point_id: str,
        *,
        center_if_hidden: bool = False,
        source: str = "programmatic",
    ) -> None:
        candidate = self.candidate_point_store.get(
            self.selection_state.selected_component_id,
            point_id,
        )
        if candidate is None:
            return
        previous_bounds = self.preview_view_bounds
        if center_if_hidden:
            self._center_candidate_if_hidden(candidate)
        view_changed = self.preview_view_bounds != previous_bounds
        previous_mode = self.selection_state.mode
        changed = self.selection_controller.select_candidate_point(point_id, source)
        if view_changed:
            self.render_scheduler.request(RenderDirty.FULL_SCENE)
        if not changed:
            return
        if previous_mode == "pick_start":
            self.candidate_action_status_var.set(
                f"已選擇待套用起點 {point_id}；按「套用修改」才會重建模型。"
            )
        elif previous_mode == "pick_end":
            self.candidate_action_status_var.set(
                f"已選擇待套用終點 {point_id}；按「套用修改」才會重建模型。"
            )

        if changed and previous_mode == "pick_start":
            self.candidate_action_status_var.set(
                f"已選擇待套用起點 {point_id}；橘色虛線為待套用工程線，尚未修改正式模型。"
            )
        elif changed and previous_mode == "pick_end":
            self.candidate_action_status_var.set(
                f"已選擇待套用終點 {point_id}；橘色虛線為待套用工程線，尚未修改正式模型。"
            )

    def _center_candidate_if_hidden(self, candidate: CandidatePoint) -> None:
        if self.preview_view_bounds is None or self.result is None:
            return
        point = self.result.coordinate_system.transform(candidate.world_point)
        min_x, max_x, min_y, max_y = self.preview_view_bounds
        if min_x <= point[0] <= max_x and min_y <= point[1] <= max_y:
            return
        self.preview_viewport.recenter(point)

    def _begin_candidate_pick(self, mode: str) -> None:
        member = self._selected_member()
        if member is None:
            self.candidate_action_status_var.set("請先選取構件。")
            return
        changed = (
            self.selection_controller.begin_pick_start()
            if mode == "pick_start"
            else self.selection_controller.begin_pick_end()
        )
        if not changed:
            return
        prompt = "請選擇新的起點" if mode == "pick_start" else "請選擇新的終點"
        self.candidate_filter_var.set("start" if mode == "pick_start" else "end")
        self.candidate_action_status_var.set(f"{prompt}（Esc 取消本次選點）")
        self._rebuild_candidate_tree()
        self._open_preview_window()
        try:
            self.canvas.focus_set()
        except self.tk.TclError:
            pass
        self.candidate_action_status_var.set(
            (
                "請在預覽圖點選新的起點（Esc 取消本次選點）"
                if mode == "pick_start"
                else "請在預覽圖點選新的終點（Esc 取消本次選點）"
            )
        )

    def _cancel_active_pick(self, _event: Any = None) -> str | None:
        if not self.selection_controller.cancel_pick():
            return None
        self.candidate_action_status_var.set("已取消本次選點，待套用值維持不變。")
        return "break"

    def _swap_pending_points(self) -> None:
        if not self.selection_controller.swap_pending_points():
            return
        self.candidate_action_status_var.set("已交換待套用起終點；正式模型尚未修改。")

    def _cancel_candidate_changes(self) -> None:
        if not self.selection_controller.cancel_pending():
            return
        self.candidate_action_status_var.set("已取消待套用修改；正式模型未變更。")

    def _restore_recommended_points(self) -> None:
        if not self.selection_controller.restore_recommended_points():
            return
        self.candidate_action_status_var.set(
            "已恢復系統推薦至待套用值；仍需按「套用修改」。"
        )

    def _apply_candidate_changes(self) -> None:
        from tkinter import messagebox

        message_parent = self.preview_window or self.window
        member = self._selected_member()
        if member is None or self.world_result is None:
            self.candidate_action_status_var.set("請先選取構件。")
            return
        state = self.selection_state
        validations = validate_candidate_point_pair(
            member,
            state.pending_start_point_id,
            state.pending_end_point_id,
            self.importer.tolerances,
            self.result.walers if self.result is not None else (),
        )
        errors = [item for item in validations if item.severity in ERROR_SEVERITIES]
        if errors:
            self.candidate_action_status_var.set(errors[0].message)
            messagebox.showerror(
                "候選點組合無法套用",
                errors[0].message,
                parent=message_parent,
            )
            return
        warnings = [item.message for item in validations if item.severity == "warning"]
        if warnings and not messagebox.askyesno(
            "候選點組合警告",
            "\n".join(f"⚠ {message}" for message in warnings)
            + "\n\n仍要套用嗎？",
            parent=message_parent,
        ):
            return
        try:
            self._clear_waler_adjustment_preview()
            self.world_result = self.import_model_controller.apply_pending(
                self.world_result,
                state,
            )
        except DXFImportError as exc:
            self.candidate_action_status_var.set(str(exc))
            return
        self._apply_coordinate_settings(
            show_error=False,
            preview_dirty=(
                RenderDirty.COMPONENT_LAYER
                | RenderDirty.COMPONENT_SELECTION
                | RenderDirty.CANDIDATE_SELECTION
                | RenderDirty.TEMP_LINE
                | RenderDirty.DETAIL_PANEL
                | RenderDirty.TREE_SELECTION
            ),
            rebuild_candidate_tree=False,
        )
        self.selection_controller.synchronize_formal_member()
        self.candidate_action_status_var.set(
            f"已套用 {member.id}，並重建連接、衍生資料及 Solver 輸入。"
        )

    def _read_cad_engineering_line(self) -> None:
        from tkinter import messagebox

        member = self._selected_member()
        if member is None or self.world_result is None:
            self.cad_temp_status_var.set("請先完成辨識並選取要修正的構件。")
            return
        role, _role_label = self._member_role(member)
        supported_roles = {
            "waler": {"waler", "walers"},
            "strut": {"strut", "struts", "support", "supports"},
            "brace": {"brace", "braces"},
        }
        if role not in supported_roles:
            self.cad_temp_status_var.set(
                "目前 CAD Temp 僅支援圍令、支撐與斜撐工程線。"
            )
            return
        try:
            event = self.cad_event_watcher.check_new_event()
            if event is None:
                self.cad_temp_status_var.set("目前沒有待讀取的 CAD Temp 工程線。")
                return
            operation = str(event.get("operation", "") or "").strip().lower()
            if operation == "update":
                command_name = {
                    "waler": "UPDWALER",
                    "walers": "UPDWALER",
                    "strut": "UPDSTRUT",
                    "struts": "UPDSTRUT",
                    "support": "UPDSTRUT",
                    "supports": "UPDSTRUT",
                    "brace": "UPDBRACE",
                    "braces": "UPDBRACE",
                }.get(str(event.get("type", "") or "").strip().lower(), "CAD update")
                self.cad_temp_status_var.set(
                    f"{command_name} 事件已保留；"
                    "請關閉 DXF 匯入視窗後由 Main 套用。"
                )
                return
            if operation == "cancel":
                self.cad_temp_status_var.set(
                    "SUPCLEAR 事件已保留；請關閉 DXF 匯入視窗後由 Main 清除。"
                )
                return
            event_type = str(event.get("type", "")).strip().lower()
            if event_type not in supported_roles[role]:
                raise DXFImportError(
                    f"CAD 事件類型 {event_type or '—'} 與選取構件 {member.id} 不相符。"
                )
            data = event.get("data")
            if not isinstance(data, Mapping):
                raise DXFImportError("CAD Temp 缺少工程線座標資料。")
            start = float(data["StartX"]), float(data["StartY"])
            end = float(data["EndX"]), float(data["EndY"])
            self.world_result, start_id, end_id = add_cad_candidate_points(
                self.world_result,
                member.id,
                start,
                end,
                self.importer.tolerances,
            )
            self.cad_event_watcher.acknowledge(event)
        except (DXFImportError, KeyError, TypeError, ValueError, OSError) as exc:
            self.cad_temp_status_var.set(str(exc))
            messagebox.showerror("CAD 工程線讀取失敗", str(exc), parent=self.window)
            return
        self.cad_temp_status_var.set(
            f"已讀取 {member.id} 的 CAD 指定工程線；請確認後按「套用修改」。"
        )
        self._apply_coordinate_settings(
            show_error=False,
            preview_dirty=(
                RenderDirty.CANDIDATE_LAYER
                | RenderDirty.CANDIDATE_SELECTION
                | RenderDirty.TEMP_LINE
                | RenderDirty.DETAIL_PANEL
                | RenderDirty.TREE_SELECTION
            ),
            rebuild_candidate_tree=True,
        )
        self.selection_controller.set_pending_pair(
            start_id,
            end_id,
            "cad_manual",
        )

    def _on_candidate_hover(self, event: Any) -> None:
        iid = self.candidate_tree.identify_row(event.y)
        point_id = self.candidate_tree_adapter.point_id_for_iid(iid)
        self.selection_controller.set_hovered_candidate(point_id)

    def _clear_candidate_hover(self, _event: Any = None) -> None:
        self.selection_controller.set_hovered_candidate("")

    @staticmethod
    def _nearest_preview_member(
        point: Point,
        hit_lines: Sequence[tuple[str, Point, Point]],
        tolerance: float = 12.0,
    ) -> str:
        return PreviewController.nearest_member(point, hit_lines, tolerance)

    @staticmethod
    def _preview_candidate_hits(
        point: Point,
        hit_points: Sequence[tuple[str, Point]],
        tolerance_pixels: float = 10.0,
    ) -> tuple[str, ...]:
        return PreviewController.candidate_hits(
            point,
            hit_points,
            tolerance_pixels,
        )

    @staticmethod
    def _preview_endpoint_hits(
        point: Point,
        endpoints: Sequence[tuple[str, Point]],
        tolerance_pixels: float = 12.0,
    ) -> tuple[str, ...]:
        """Hit-test the visible pending endpoint markers in screen pixels."""

        return PreviewController.candidate_hits(
            point,
            endpoints,
            tolerance_pixels,
        )

    def _pending_endpoint_hits(self, point: Point) -> tuple[str, ...]:
        component_id = self.selection_state.selected_component_id
        if not component_id:
            return ()
        endpoint_points: list[tuple[str, Point]] = []
        for role, point_id in (
            ("start", self.selection_state.pending_start_point_id),
            ("end", self.selection_state.pending_end_point_id),
        ):
            candidate = self.candidate_point_store.get(component_id, point_id)
            if candidate is not None:
                endpoint_points.append((role, self._candidate_canvas_point(candidate)))
        return self._preview_endpoint_hits(point, endpoint_points)

    def _sync_candidate_tree_hover(self, point_id: str) -> None:
        if hasattr(self, "candidate_tree_adapter"):
            self.candidate_tree_adapter.set_hover(point_id)

    def _on_canvas_click(self, event: Any) -> None:
        canvas_point = (float(event.x), float(event.y))
        if self.selection_state.mode == "idle":
            endpoint_hits = self._pending_endpoint_hits(canvas_point)
            if len(endpoint_hits) == 1:
                self._begin_candidate_pick(
                    "pick_start"
                    if endpoint_hits[0] == "start"
                    else "pick_end"
                )
                return
            if len(endpoint_hits) > 1:
                self.candidate_action_status_var.set(
                    "起點與終點標記在畫面上重疊，請放大圖面後再點選，或使用主視窗按鈕。"
                )
                return
        hits = self._preview_candidate_hits(
            canvas_point,
            self.canvas_candidate_hit_points,
        )
        if len(hits) == 1:
            self._select_candidate_point(hits[0], source="canvas")
            return
        if len(hits) > 1:
            self.candidate_action_status_var.set(
                "此處命中多個候選點："
                + "、".join(hits)
                + "。請由右側候選點清單精確選擇。"
            )
            return
        if self.selection_state.mode in {"pick_start", "pick_end"}:
            self.candidate_action_status_var.set(
                "選點模式只能點選黃色候選點；不能使用空白位置。"
            )
            return
        member_id = self._nearest_preview_member(
            canvas_point,
            self.canvas_member_hit_lines,
        )
        if member_id:
            self._select_member(
                member_id,
                refit=False,
                clear_problem=True,
                source="canvas",
            )

    def _locate_selected_member(self) -> None:
        self._open_preview_window()
        if self._selected_member() is not None:
            self.preview_view_bounds = None
            self.preview_fit_all = False
        self._draw_preview()

    def _on_canvas_motion(self, event: Any) -> None:
        if self.preview_viewport.view_bounds is None:
            self.preview_cursor_var.set("游標：—")
            return
        x, y = self.preview_viewport.screen_to_data(
            (float(event.x), float(event.y))
        )
        self.preview_cursor_var.set(f"游標：X={x:.3f}  Y={y:.3f}")
        point_hits = self._preview_candidate_hits(
            (float(event.x), float(event.y)),
            self.canvas_candidate_hit_points,
        )
        endpoint_hits = (
            self._pending_endpoint_hits((float(event.x), float(event.y)))
            if self.selection_state.mode == "idle"
            else ()
        )
        try:
            self.canvas.configure(
                cursor=("hand2" if point_hits or endpoint_hits else "crosshair")
            )
        except self.tk.TclError:
            pass
        hovered_point_id = point_hits[0] if point_hits else ""
        hovered_member_id = ""
        if not hovered_point_id:
            hovered_member_id = self._nearest_preview_member(
                (float(event.x), float(event.y)),
                self.canvas_member_hit_lines,
            )
        self.selection_controller.set_hovered_candidate(hovered_point_id)
        self.selection_controller.set_hovered_component(hovered_member_id)

    def _on_canvas_leave(self, _event: Any = None) -> None:
        self.preview_cursor_var.set("游標：—")
        self.selection_controller.set_hovered_candidate("")
        self.selection_controller.set_hovered_component("")

    def _on_canvas_mousewheel(self, event: Any, direction: int | None = None) -> None:
        if self.preview_viewport.view_bounds is None:
            return
        if direction is None:
            direction = 1 if getattr(event, "delta", 0) > 0 else -1
        factor = self.preview_interaction.scroll_factor(direction)
        if factor is None:
            return
        self.preview_viewport.zoom_at_screen(
            (float(event.x), float(event.y)),
            factor,
        )
        self.preview_fit_all = False
        self._draw_preview()

    def _start_canvas_pan(self, event: Any) -> None:
        if self.preview_view_bounds is not None:
            self.preview_interaction.begin_pan(
                (float(event.x), float(event.y)),
                self.preview_view_bounds,
            )
            self.canvas.configure(cursor="fleur")

    def _drag_canvas_pan(self, event: Any) -> None:
        if not self.preview_interaction.pan_active:
            return
        scale = self.preview_viewport.scale
        updated = self.preview_interaction.pan_to(
            (float(event.x), float(event.y)),
            (scale, scale),
            y_axis_screen_down=True,
        )
        if updated is None:
            return
        self.preview_view_bounds = updated
        self.preview_fit_all = False
        self._draw_preview()

    def _end_canvas_pan(self, _event: Any = None) -> None:
        self.preview_interaction.end_pan()
        try:
            self.canvas.configure(cursor="crosshair")
        except self.tk.TclError:
            pass

    def _on_canvas_middle_double_click(self, _event: Any = None) -> str:
        self._end_canvas_pan()
        self._zoom_extents()
        return "break"

    def _zoom_extents(self) -> None:
        self.preview_view_bounds = None
        self.preview_fit_all = True
        self._draw_preview()

    def _draw_preview(self) -> None:
        self.render_scheduler.request(RenderDirty.FULL_SCENE)

    def _flush_render_updates(self, dirty: RenderDirty) -> None:
        started_at = time.perf_counter()
        if dirty & RenderDirty.FULL_SCENE:
            self._rebuild_preview_scene()
            if (
                dirty & RenderDirty.CANDIDATE_LAYER
                and hasattr(self, "candidate_tree_adapter")
                and self.candidate_tree_adapter.component_id
                != self.selection_state.selected_component_id
            ):
                self._rebuild_candidate_tree()
        else:
            if dirty & RenderDirty.COMPONENT_LAYER:
                self._rebuild_engineering_member_layer()
            if dirty & RenderDirty.CANDIDATE_LAYER:
                if (
                    hasattr(self, "candidate_tree_adapter")
                    and self.candidate_tree_adapter.component_id
                    != self.selection_state.selected_component_id
                ):
                    self._rebuild_candidate_tree()
                self._rebuild_candidate_overlay()
            if dirty & (
                RenderDirty.COMPONENT_SELECTION
                | RenderDirty.CANDIDATE_SELECTION
                | RenderDirty.HOVER
            ):
                self._update_preview_selection_overlay(
                    update_associations=bool(
                        dirty & RenderDirty.COMPONENT_SELECTION
                    )
                )
            if dirty & RenderDirty.TEMP_LINE:
                self._update_temporary_line_overlay()
        if dirty & RenderDirty.TREE_SELECTION:
            self._sync_tree_selections_from_state()
        if dirty & RenderDirty.HOVER:
            self._sync_candidate_tree_hover(
                self.selection_state.hovered_candidate_point_id
            )
        if dirty & RenderDirty.COMPONENT_SELECTION:
            self._update_selected_member_panel(rebuild_candidates=False)
        elif dirty & RenderDirty.CANDIDATE_SELECTION:
            self._update_candidate_tree_rows()
            self._update_candidate_detail_panel()
        elif dirty & RenderDirty.DETAIL_PANEL:
            self._update_candidate_detail_panel()
        self.performance_diagnostics.record("render_flush", started_at)
        self._update_performance_diagnostics_display()

    def _rebuild_preview_scene(self) -> None:
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        try:
            if not canvas.winfo_exists():
                return
        except self.tk.TclError:
            return
        started_at = time.perf_counter()
        if self.preview_renderer is None:
            self.preview_renderer = PreviewRenderer(canvas, self.preview_scene)
        renderer = self.preview_renderer
        renderer.clear()
        self._waler_adjustment_overlay_items.clear()
        self.canvas_member_hit_lines = []
        self.canvas_candidate_hit_points = []
        self.preview_transform = None
        if self.result is None:
            return
        member_styles = self._preview_member_styles()
        raw = self._preview_source_geometry(self.result)
        coordinate_system = self.result.coordinate_system
        all_points = [
            point
            for member, *_style in member_styles
            for point in (
                member.path
                if isinstance(member, Beam) and member.path
                else (member.start, member.end)
            )
        ]
        all_points.extend(
            coordinate_system.transform(point)
            for geometry in raw
            for point in geometry.points
        )
        all_points.extend(
            coordinate_system.transform(source_text.position)
            for source_text in self.result.source_texts
        )
        selected_member = self._selected_member()
        if selected_member is not None:
            all_points.extend(
                coordinate_system.transform(candidate.world_point)
                for candidate in self.candidate_point_store.component_points(
                    selected_member.id
                )
            )
        focus_points = [
            point
            for member, *_style in member_styles
            if member.id in self.focus_member_ids
            or member.id == self.selected_member_id
            for point in (
                member.path
                if isinstance(member, Beam) and member.path
                else (member.start, member.end)
            )
        ]
        focus_points.extend(
            coordinate_system.transform(point)
            for geometry in raw
            if geometry.source_handle in self.focus_handles
            for point in geometry.points
        )
        if not all_points:
            renderer.create_text(
                "coordinate_axis",
                20,
                20,
                text="沒有可預覽的工程模型",
                anchor="nw",
            )
            return
        width, height = max(canvas.winfo_width(), 100), max(canvas.winfo_height(), 100)
        margin = 48
        self.preview_viewport.configure(width, height, margin)

        def padded_bounds(points: Sequence[Point]) -> tuple[float, float, float, float]:
            bounds_min_x = min(point[0] for point in points)
            bounds_max_x = max(point[0] for point in points)
            bounds_min_y = min(point[1] for point in points)
            bounds_max_y = max(point[1] for point in points)
            span_x = bounds_max_x - bounds_min_x
            span_y = bounds_max_y - bounds_min_y
            pad_x = max(span_x * 0.18, span_y * 0.05, 50)
            pad_y = max(span_y * 0.18, span_x * 0.05, 50)
            return (
                bounds_min_x - pad_x,
                bounds_max_x + pad_x,
                bounds_min_y - pad_y,
                bounds_max_y + pad_y,
            )

        full_min_x, full_max_x, full_min_y, full_max_y = padded_bounds(
            all_points
        )
        full_content_bounds = (
            full_min_x,
            full_max_x,
            full_min_y,
            full_max_y,
        )
        if self.preview_view_bounds is None:
            view_points = all_points if self.preview_fit_all else (focus_points or all_points)
            min_x, max_x, min_y, max_y = padded_bounds(view_points)
            self.preview_viewport.fit((min_x, max_x, min_y, max_y))
            self.preview_fit_all = False
        assert self.preview_view_bounds is not None
        min_x, max_x, min_y, max_y = self.preview_view_bounds
        scale = self.preview_viewport.scale
        full_scale = self.preview_viewport.scale_for_bounds(full_content_bounds)
        zoom_factor = scale / max(full_scale, 1e-12)

        self.preview_transform = self.preview_viewport.legacy_transform
        self.preview_zoom_factor = zoom_factor
        self._draw_source_geometry_layer(raw)
        self._draw_source_text_layer(self.result.source_texts)
        self._draw_engineering_members()
        self._rebuild_candidate_overlay(update_overlays=False)
        self._ensure_preview_overlay_items()
        self._update_preview_selection_overlay(update_associations=True)
        self._update_temporary_line_overlay()
        self._draw_waler_adjustment_overlay()
        self._draw_coordinate_axis_layer()
        self._update_source_layer_visibility()
        for layer in PreviewRenderer.LAYERS:
            try:
                canvas.tag_raise(layer)
            except self.tk.TclError:
                pass
        self.performance_diagnostics.full_scene_rebuilds += 1
        try:
            self.performance_diagnostics.canvas_item_count = len(canvas.find_all())
        except self.tk.TclError:
            self.performance_diagnostics.canvas_item_count = 0
        self.performance_diagnostics.record("full_scene", started_at)

    def _preview_member_styles(
        self,
    ) -> list[tuple[Waler | Strut | Brace | AuxiliaryComponent, str, int, Any]]:
        if self.result is None:
            return []
        return [
            *((member, "#2e7d32", 4, None) for member in self.result.walers),
            *((member, "#2e7d32", 3, None) for member in self.result.struts),
            *((member, "#2e7d32", 3, (8, 4)) for member in self.result.braces),
            *((member, "#2e7d32", 3, (10, 3)) for member in self.result.beams),
            *((member, "#2e7d32", 3, (5, 2)) for member in self.result.corner_braces),
        ]

    def _project_preview_point(self, point: Point) -> Point:
        return self.preview_viewport.data_to_screen(point)

    def _candidate_canvas_point(self, candidate: CandidatePoint) -> Point:
        assert self.result is not None
        return self._project_preview_point(
            self.result.coordinate_system.transform(candidate.world_point)
        )

    def _preview_intersects(self, points: Sequence[Point]) -> bool:
        return self.preview_viewport.intersects(points)

    def _draw_source_geometry_layer(
        self,
        geometries: Sequence[SourceGeometry],
    ) -> None:
        if self.result is None or self.preview_renderer is None:
            return
        renderer = self.preview_renderer
        coordinate_system = self.result.coordinate_system
        source_issue_levels = self._unresolved_source_issue_levels()
        excluded_source_keys = {
            (source.role, handle)
            for source in self.result.excluded_sources
            for handle in source.source_handles
        }
        for geometry in geometries:
            displayed_points = [
                coordinate_system.transform(point) for point in geometry.points
            ]
            if not self._preview_intersects(displayed_points):
                continue
            projected = [
                coordinate
                for point in displayed_points
                for coordinate in self._project_preview_point(point)
            ]
            if len(projected) < 4:
                continue
            is_auxiliary = geometry.role == "auxiliary"
            normalized_geometry_handles = normalize_source_handles(
                (geometry.source_handle,)
            )
            is_excluded = bool(
                normalized_geometry_handles
                and (geometry.role, normalized_geometry_handles[0])
                in excluded_source_keys
            )
            layer = "auxiliary_geometry" if is_auxiliary else "source_geometry"
            color = (
                "#78909c"
                if is_excluded
                else "#d7dde1"
                if is_auxiliary
                else "#b0bec5"
            )
            line_width = 2 if is_excluded else 1
            dash = (2, 5) if is_excluded else None if is_auxiliary else (4, 3)
            if not is_auxiliary and geometry.source_handle in self.focus_handles:
                color, line_width = "#1565c0", 4
            options: dict[str, Any] = {"fill": color, "width": line_width}
            if dash is not None:
                options["dash"] = dash
            issue_level = source_issue_levels.get(geometry.source_handle)
            issue_options: dict[str, Any] | None = None
            if issue_level:
                issue_options = {
                    "fill": (
                        "#d32f2f"
                        if issue_level in ERROR_SEVERITIES
                        else "#f9a825"
                    ),
                    "width": 7,
                }
                if dash is not None:
                    issue_options["dash"] = dash
                renderer.create_line(
                    layer,
                    *projected,
                    source_handle=geometry.source_handle,
                    **issue_options,
                )
            renderer.create_line(
                layer,
                *projected,
                source_handle=geometry.source_handle,
                **options,
            )
            if geometry.closed and len(displayed_points) > 2:
                closing_coordinates = (
                    *self._project_preview_point(displayed_points[-1]),
                    *self._project_preview_point(displayed_points[0]),
                )
                if issue_options is not None:
                    renderer.create_line(
                        layer,
                        *closing_coordinates,
                        source_handle=geometry.source_handle,
                        **issue_options,
                    )
                renderer.create_line(
                    layer,
                    *closing_coordinates,
                    source_handle=geometry.source_handle,
                    **options,
                )

    def _draw_source_text_layer(
        self,
        source_texts: Sequence[SourceText],
    ) -> None:
        if self.result is None or self.preview_renderer is None:
            return
        renderer = self.preview_renderer
        coordinate_system = self.result.coordinate_system
        for source_text in source_texts:
            displayed_position = coordinate_system.transform(source_text.position)
            if not self._preview_intersects((displayed_position,)):
                continue
            x, y = self._project_preview_point(displayed_position)
            font_size = max(
                8,
                min(
                    28,
                    round(source_text.height * self.preview_viewport.scale),
                ),
            )
            renderer.create_text(
                "auxiliary_geometry",
                x,
                y,
                text=source_text.text,
                fill="#66757f",
                anchor="center",
                justify="center",
                font=("Microsoft JhengHei", font_size),
                angle=-source_text.rotation,
                source_handle=source_text.source_handle,
            )

    def _member_issue_levels(self) -> dict[str, str]:
        severity_rank = {"warning": 1, "error": 2, "critical": 3}
        member_levels: dict[str, str] = {}
        for record in self.problem_records:
            if record.severity not in severity_rank:
                continue
            for member_id in record.member_ids:
                if severity_rank[record.severity] > severity_rank.get(
                    member_levels.get(member_id, ""),
                    0,
                ):
                    member_levels[member_id] = record.severity
        return member_levels

    def _unresolved_source_issue_levels(self) -> dict[str, str]:
        levels: dict[str, str] = {}
        for item in getattr(self, "review_items", ()):
            if (
                item.status != "unresolved"
                or item.highest_severity not in {"warning", "error", "critical"}
            ):
                continue
            for handle in item.source_handles:
                if problem_severity_rank(item.highest_severity) > problem_severity_rank(
                    levels.get(handle, "")
                ):
                    levels[handle] = item.highest_severity
        return levels

    def _draw_engineering_members(self) -> None:
        if self.preview_renderer is None:
            return
        renderer = self.preview_renderer
        member_levels = self._member_issue_levels()
        self.canvas_member_hit_lines = []
        for member, color, line_width, dash in self._preview_member_styles():
            member_points = (
                member.path
                if isinstance(member, Beam) and member.path
                else (member.start, member.end)
            )
            if not self._preview_intersects(member_points):
                continue
            projected = tuple(
                self._project_preview_point(point) for point in member_points
            )
            for start, end in zip(projected, projected[1:]):
                self.canvas_member_hit_lines.append((member.id, start, end))
            options: dict[str, Any] = {
                "fill": color,
                "width": line_width,
            }
            if dash is not None:
                options["dash"] = dash
            renderer.create_line(
                "engineering_members",
                *(coordinate for point in projected for coordinate in point),
                component_id=member.id,
                **options,
            )
            level = member_levels.get(member.id)
            if level:
                renderer.create_line(
                    "engineering_members",
                    *(coordinate for point in projected for coordinate in point),
                    component_id=member.id,
                    fill=(
                        "#d32f2f"
                        if level in ERROR_SEVERITIES
                        else "#f9a825"
                    ),
                    width=7,
                    **({"dash": dash} if dash is not None else {}),
                )
            if member.id in self.focus_member_ids:
                renderer.create_line(
                    "engineering_members",
                    *(coordinate for point in projected for coordinate in point),
                    component_id=member.id,
                    fill="#1565c0",
                    width=4,
                    dash=(3, 2),
                )
            # A two-point component used to place its label at index 1, i.e.
            # exactly on its endpoint.  Corner-brace labels then covered the
            # connection to the Strut centreline and made a correct junction
            # look offset.  Place labels at the geometric half-length of the
            # displayed path instead.
            segment_lengths = [
                _distance(start, end)
                for start, end in zip(projected, projected[1:])
            ]
            half_length = sum(segment_lengths) / 2.0
            travelled = 0.0
            label_point = projected[0]
            for (start, end), segment_length in zip(
                zip(projected, projected[1:]),
                segment_lengths,
            ):
                if segment_length <= 1e-12:
                    continue
                if travelled + segment_length >= half_length:
                    fraction = (half_length - travelled) / segment_length
                    label_point = (
                        start[0] + (end[0] - start[0]) * fraction,
                        start[1] + (end[1] - start[1]) * fraction,
                    )
                    break
                travelled += segment_length
            renderer.create_text(
                "engineering_members",
                label_point[0],
                label_point[1] - 9,
                component_id=member.id,
                text=member.id,
                fill=("#1565c0" if member.id in self.focus_member_ids else color),
                font=("Arial", 9, "bold"),
            )

        # A Column is perpendicular to this plan view, so its DXF geometry is
        # a section footprint rather than a linear member.  Show the section
        # reference point instead of drawing the compatibility start/end axis.
        if self.result is None:
            return
        for member in self.result.columns:
            reference = member.reference_point or _midpoint(member.start, member.end)
            if not self._preview_intersects((reference,)):
                continue
            x, y = self._project_preview_point(reference)
            self.canvas_member_hit_lines.append(
                (member.id, (x - 8, y), (x + 8, y))
            )
            level = member_levels.get(member.id)
            if member.id in self.focus_member_ids:
                color = "#1565c0"
            elif level in ERROR_SEVERITIES:
                color = "#d32f2f"
            elif level:
                color = "#f9a825"
            else:
                color = "#2e7d32"
            renderer.create_line(
                "engineering_members",
                x - 6,
                y,
                x + 6,
                y,
                component_id=member.id,
                fill=color,
                width=3,
            )
            renderer.create_line(
                "engineering_members",
                x,
                y - 6,
                x,
                y + 6,
                component_id=member.id,
                fill=color,
                width=3,
            )
            renderer.create_text(
                "engineering_members",
                x + 9,
                y - 9,
                component_id=member.id,
                text=member.id,
                fill=color,
                anchor="sw",
                font=("Arial", 9, "bold"),
            )

    def _rebuild_engineering_member_layer(self) -> None:
        if self.preview_renderer is None or self.preview_transform is None:
            return
        started_at = time.perf_counter()
        self.preview_renderer.delete_layer("engineering_members")
        self._draw_engineering_members()
        self._update_preview_selection_overlay(update_associations=True)
        self.performance_diagnostics.engineering_member_rebuilds += 1
        self.performance_diagnostics.record("engineering_members", started_at)

    def _candidate_visible_in_preview(self, candidate: CandidatePoint) -> bool:
        mode = self.selection_state.mode
        return self._candidate_filter_accepts(candidate) and not (
            mode == "pick_start" and "start" not in candidate.valid_for
            or mode == "pick_end" and "end" not in candidate.valid_for
        )

    def _rebuild_candidate_overlay(self, *, update_overlays: bool = True) -> None:
        if self.preview_renderer is None or self.preview_transform is None:
            return
        started_at = time.perf_counter()
        renderer = self.preview_renderer
        renderer.delete_layer("candidate_overlay")
        self.canvas_candidate_hit_points = []
        member = self._selected_member()
        if member is not None:
            for candidate in self.candidate_point_store.component_points(member.id):
                if not self._candidate_visible_in_preview(candidate):
                    continue
                x, y = self._candidate_canvas_point(candidate)
                self.canvas_candidate_hit_points.append((candidate.id, (x, y)))
                renderer.create_oval(
                    "candidate_overlay",
                    x - 5,
                    y - 5,
                    x + 5,
                    y + 5,
                    candidate_point_id=candidate.id,
                    fill="#ffffff",
                    outline="#f9a825",
                    width=2,
                )
        if update_overlays:
            self._ensure_preview_overlay_items()
            self._update_preview_selection_overlay()
            self._update_temporary_line_overlay()
        self.performance_diagnostics.candidate_layer_rebuilds += 1
        self.performance_diagnostics.record("candidate_layer", started_at)

    def _ensure_preview_overlay_items(self) -> None:
        if self.preview_renderer is None:
            return
        renderer = self.preview_renderer
        scene = self.preview_scene

        def line(key: str, layer: str, **options: Any) -> None:
            if key in scene.selection_items or (
                key == "pending_line" and scene.temporary_line_items
            ):
                return
            renderer.create_line(
                layer,
                0,
                0,
                0,
                0,
                overlay_key=key,
                state="hidden",
                **options,
            )

        def oval(key: str, **options: Any) -> None:
            if key in scene.selection_items:
                return
            renderer.create_oval(
                "selection_overlay",
                0,
                0,
                0,
                0,
                overlay_key=key,
                state="hidden",
                **options,
            )

        line("selected_component", "selection_overlay", fill="#c62828", width=5)
        line("hovered_component", "selection_overlay", fill="#00838f", width=7)
        oval("selected_candidate", fill="", outline="#1565c0", width=3)
        oval("formal_start", fill="", outline="#1b5e20", width=2)
        oval("formal_end", fill="", outline="#1b5e20", width=2)
        oval("pending_start", fill="#1565c0", outline="#0d47a1", width=2)
        oval("pending_end", fill="#d32f2f", outline="#8e0000", width=2)
        oval("hovered_candidate", fill="#fb8c00", outline="#e65100", width=3)
        if "candidate_tooltip" not in scene.selection_items:
            renderer.create_text(
                "selection_overlay",
                0,
                0,
                overlay_key="candidate_tooltip",
                text="",
                fill="#e65100",
                anchor="sw",
                justify="left",
                font=("Arial", 9, "bold"),
                state="hidden",
            )
        if "component_tooltip_bg" not in scene.selection_items:
            renderer.create_rectangle(
                "selection_overlay",
                0,
                0,
                0,
                0,
                overlay_key="component_tooltip_bg",
                fill="#e0f7fa",
                outline="#00838f",
                state="hidden",
            )
        if "component_tooltip" not in scene.selection_items:
            renderer.create_text(
                "selection_overlay",
                0,
                0,
                overlay_key="component_tooltip",
                text="",
                fill="#004d40",
                anchor="nw",
                justify="left",
                font=("Arial", 9),
                state="hidden",
            )
        if not scene.temporary_line_items:
            line(
                "pending_line",
                "temporary_overlay",
                fill="#ef6c00",
                width=3,
                dash=(8, 4),
            )

    def _set_overlay_line(
        self,
        key: str,
        member: Waler | Strut | Brace | AuxiliaryComponent | None,
    ) -> None:
        if self.preview_renderer is None:
            return
        item_id = self.preview_scene.selection_items.get(key)
        if not item_id:
            return
        if member is None:
            self.canvas.itemconfigure(item_id, state="hidden")
            return
        if isinstance(member, Column):
            reference = member.reference_point or _midpoint(member.start, member.end)
            x, y = self._project_preview_point(reference)
            self.canvas.coords(item_id, x - 7, y, x + 7, y)
            self.canvas.itemconfigure(item_id, state="normal")
            return
        if isinstance(member, Beam) and member.path:
            self.canvas.coords(
                item_id,
                *(
                    coordinate
                    for point in member.path
                    for coordinate in self._project_preview_point(point)
                ),
            )
            self.canvas.itemconfigure(item_id, state="normal")
            return
        self.canvas.coords(
            item_id,
            *self._project_preview_point(member.start),
            *self._project_preview_point(member.end),
        )
        self.canvas.itemconfigure(item_id, state="normal")

    def _set_overlay_marker(
        self,
        key: str,
        candidate: CandidatePoint | None,
        radius: int,
    ) -> None:
        item_id = self.preview_scene.selection_items.get(key)
        if not item_id:
            return
        if candidate is None:
            self.canvas.itemconfigure(item_id, state="hidden")
            return
        x, y = self._candidate_canvas_point(candidate)
        self.canvas.coords(
            item_id,
            x - radius,
            y - radius,
            x + radius,
            y + radius,
        )
        self.canvas.itemconfigure(item_id, state="normal")

    def _update_preview_selection_overlay(
        self,
        *,
        update_associations: bool = False,
    ) -> None:
        if self.preview_transform is None or self.preview_renderer is None:
            return
        started_at = time.perf_counter()
        self._ensure_preview_overlay_items()
        state = self.selection_state
        member = self._selected_member()
        hovered_member = self._member_by_id(state.hovered_component_id)
        self._set_overlay_line("selected_component", member)
        self._set_overlay_line("hovered_component", hovered_member)
        if update_associations:
            for key in tuple(self.preview_scene.selection_items):
                if not key.startswith("associated::"):
                    continue
                item_id = self.preview_scene.selection_items.pop(key)
                self.canvas.delete(item_id)
            if isinstance(member, Strut):
                associated_ids = (
                    *member.associated_columns,
                    *member.associated_beams,
                )
                for associated_id in associated_ids:
                    associated = self._member_by_id(associated_id)
                    if associated is None:
                        continue
                    associated_points = (
                        associated.path
                        if isinstance(associated, Beam) and associated.path
                        else (associated.start, associated.end)
                    )
                    self.preview_renderer.create_line(
                        "selection_overlay",
                        *(
                            coordinate
                            for point in associated_points
                            for coordinate in self._project_preview_point(point)
                        ),
                        overlay_key=f"associated::{associated_id}",
                        fill="#1565c0",
                        width=5,
                        dash=(3, 2),
                    )
        point = lambda point_id: self.candidate_point_store.get(
            state.selected_component_id,
            point_id,
        )
        self._set_overlay_marker(
            "selected_candidate",
            point(state.selected_candidate_point_id),
            9,
        )
        self._set_overlay_marker("formal_start", point(state.selected_start_point_id), 8)
        self._set_overlay_marker("formal_end", point(state.selected_end_point_id), 8)
        self._set_overlay_marker("pending_start", point(state.pending_start_point_id), 6)
        self._set_overlay_marker("pending_end", point(state.pending_end_point_id), 6)
        hovered_point = point(state.hovered_candidate_point_id)
        self._set_overlay_marker("hovered_candidate", hovered_point, 9)
        tooltip_id = self.preview_scene.selection_items.get("candidate_tooltip")
        if tooltip_id:
            if hovered_point is None:
                self.canvas.itemconfigure(tooltip_id, state="hidden")
            else:
                x, y = self._candidate_canvas_point(hovered_point)
                endpoint_hint = ""
                if state.mode == "idle":
                    if hovered_point.id == state.pending_start_point_id:
                        endpoint_hint = "\n點擊此藍色點：重新選擇起點"
                    elif hovered_point.id == state.pending_end_point_id:
                        endpoint_hint = "\n點擊此紅色點：重新選擇終點"
                elif state.mode == "pick_start":
                    endpoint_hint = "\n點擊：設為待套用起點"
                elif state.mode == "pick_end":
                    endpoint_hint = "\n點擊：設為待套用終點"
                self.canvas.coords(tooltip_id, x + 10, y - 10)
                self.canvas.itemconfigure(
                    tooltip_id,
                    text=(
                        f"{hovered_point.id}  {hovered_point.label}\n"
                        f"World ({hovered_point.world_point[0]:.3f}, "
                        f"{hovered_point.world_point[1]:.3f})\n"
                        f"Local ({hovered_point.local_point[0]:.3f}, "
                        f"{hovered_point.local_point[1]:.3f})"
                        f"{endpoint_hint}"
                    ),
                    state="normal",
                )
        bg_id = self.preview_scene.selection_items.get("component_tooltip_bg")
        text_id = self.preview_scene.selection_items.get("component_tooltip")
        if bg_id and text_id:
            if hovered_member is None:
                self.canvas.itemconfigure(bg_id, state="hidden")
                self.canvas.itemconfigure(text_id, state="hidden")
            else:
                width = max(self.canvas.winfo_width(), 100)
                _role, role_label = self._member_role(hovered_member)
                self.canvas.coords(bg_id, width - 330, 10, width - 10, 75)
                self.canvas.coords(text_id, width - 320, 17)
                self.canvas.itemconfigure(bg_id, state="normal")
                self.canvas.itemconfigure(
                    text_id,
                    text=(
                        f"{hovered_member.id}｜{role_label}\n"
                        f"圖層：{hovered_member.source_layer}\n"
                        "工程線來源："
                        f"{self._selection_source_label(hovered_member.selection_source)}"
                    ),
                    state="normal",
                )
        self.canvas.tag_raise("selection_overlay")
        self.performance_diagnostics.selection_overlay_updates += 1
        self.performance_diagnostics.record("selection_overlay", started_at)

    def _update_temporary_line_overlay(self) -> None:
        if self.preview_transform is None or self.preview_renderer is None:
            return
        started_at = time.perf_counter()
        self._ensure_preview_overlay_items()
        item_id = (
            self.preview_scene.temporary_line_items[0]
            if self.preview_scene.temporary_line_items
            else 0
        )
        member = self._selected_member()
        state = self.selection_state
        if not item_id or member is None:
            if item_id:
                self.canvas.itemconfigure(item_id, state="hidden")
            return
        start = self.candidate_point_store.get(
            member.id,
            state.pending_start_point_id,
        )
        end = self.candidate_point_store.get(
            member.id,
            state.pending_end_point_id,
        )
        hovered = self.candidate_point_store.get(
            member.id,
            state.hovered_candidate_point_id,
        )
        preview_start = hovered if state.mode == "pick_start" and hovered else start
        preview_end = hovered if state.mode == "pick_end" and hovered else end
        pending_changed = (
            state.pending_start_point_id != state.selected_start_point_id
            or state.pending_end_point_id != state.selected_end_point_id
            or state.mode in {"pick_start", "pick_end"}
        )
        if preview_start is None or preview_end is None or not pending_changed:
            self.canvas.itemconfigure(item_id, state="hidden")
        else:
            self.canvas.coords(
                item_id,
                *self._candidate_canvas_point(preview_start),
                *self._candidate_canvas_point(preview_end),
            )
            self.canvas.itemconfigure(item_id, state="normal")
            self.canvas.tag_raise("temporary_overlay")
        self.performance_diagnostics.temporary_overlay_updates += 1
        self.performance_diagnostics.record("temporary_overlay", started_at)

    def _draw_waler_adjustment_overlay(self) -> None:
        """Draw proposed affected geometry without replacing the formal result."""

        if (
            self.preview_renderer is None
            or self.preview_transform is None
            or self.result is None
        ):
            return
        for item_id in self._waler_adjustment_overlay_items:
            try:
                self.canvas.delete(item_id)
            except self.tk.TclError:
                pass
        stale = set(self._waler_adjustment_overlay_items)
        self.preview_scene.temporary_line_items[:] = [
            item_id
            for item_id in self.preview_scene.temporary_line_items
            if item_id not in stale
        ]
        self._waler_adjustment_overlay_items.clear()
        plan = self.waler_adjustment_preview_plan
        if plan is None:
            return
        coordinate_system = self.result.coordinate_system
        proposed_members = (
            plan.new_waler,
            *(item.new_member for item in plan.strut_changes),
            *(item.new_member for item in plan.brace_changes),
            *(item.new_member for item in plan.corner_brace_changes),
        )
        for member in proposed_members:
            world_start = member.world_start or member.start
            world_end = member.world_end or member.end
            displayed = (
                coordinate_system.transform(world_start),
                coordinate_system.transform(world_end),
            )
            item_id = self.preview_renderer.create_line(
                "temporary_overlay",
                *self._project_preview_point(displayed[0]),
                *self._project_preview_point(displayed[1]),
                fill="#ef6c00",
                width=4,
                dash=(8, 4),
            )
            self._waler_adjustment_overlay_items.append(item_id)
        self.canvas.tag_raise("temporary_overlay")

    def _show_exclusion_fingerprint_notice(self) -> None:
        if (
            not self.exclusion_fingerprint_mismatch
            or self._exclusion_fingerprint_notice_shown
        ):
            return
        from tkinter import messagebox

        self._exclusion_fingerprint_notice_shown = True
        messagebox.showwarning(
            "DXF 來源排除需要重新確認",
            "目前 DXF 內容已變更，先前的來源排除設定未自動套用，請重新確認。",
            parent=self.window,
        )

    def _draw_coordinate_axis_layer(self) -> None:
        if (
            self.result is None
            or self.preview_renderer is None
            or self.preview_view_bounds is None
        ):
            return
        renderer = self.preview_renderer
        coordinate_system = self.result.coordinate_system
        min_x, max_x, min_y, max_y = self.preview_view_bounds
        display_origin = coordinate_system.transform(
            (coordinate_system.origin_x, coordinate_system.origin_y)
        )
        if (
            min_x <= display_origin[0] <= max_x
            and min_y <= display_origin[1] <= max_y
        ):
            x_start = self._project_preview_point((min_x, display_origin[1]))
            x_end = self._project_preview_point((max_x, display_origin[1]))
            y_start = self._project_preview_point((display_origin[0], min_y))
            y_end = self._project_preview_point((display_origin[0], max_y))
            renderer.create_line(
                "coordinate_axis", *x_start, *x_end, fill="#000000", width=1
            )
            renderer.create_line(
                "coordinate_axis", *y_start, *y_end, fill="#000000", width=1
            )
            renderer.create_text(
                "coordinate_axis",
                x_end[0] - 4,
                x_end[1] - 10,
                text="X Axis",
                fill="#000000",
                anchor="e",
                font=("Arial", 9, "bold"),
            )
            renderer.create_text(
                "coordinate_axis",
                y_end[0] + 7,
                y_end[1] + 4,
                text="Y Axis",
                fill="#000000",
                anchor="nw",
                font=("Arial", 9, "bold"),
            )
        coordinate_mode = (
            "Local Coordinates"
            if coordinate_system.mode == "local"
            else "World Coordinates"
        )
        information = (
            f"Coordinate System: {coordinate_mode}\n"
            f"Origin: ({coordinate_system.origin_x:.3f}, "
            f"{coordinate_system.origin_y:.3f})\n"
            f"Zoom: {getattr(self, 'preview_zoom_factor', 1.0):.2f}x"
        )
        renderer.create_rectangle(
            "coordinate_axis",
            10,
            10,
            305,
            72,
            fill="#ffffff",
            outline="#cfd8dc",
        )
        renderer.create_text(
            "coordinate_axis",
            18,
            16,
            text=information,
            fill="#000000",
            anchor="nw",
            justify="left",
            font=("Arial", 9),
        )

    def _update_source_layer_visibility(self) -> None:
        canvas = getattr(self, "canvas", None)
        if canvas is None:
            return
        try:
            canvas.itemconfigure(
                "source_geometry",
                state="normal" if self.show_source_var.get() else "hidden",
            )
            canvas.itemconfigure(
                "auxiliary_geometry",
                state="normal" if self.show_auxiliary_var.get() else "hidden",
            )
            if not self.show_source_var.get():
                for handle in self.focus_handles:
                    for item_id in self.preview_scene.source_handle_items.get(
                        handle,
                        (),
                    ):
                        canvas.itemconfigure(item_id, state="normal")
        except self.tk.TclError:
            return

    def _sync_tree_selections_from_state(self) -> None:
        member_id = self.selection_state.selected_component_id
        if member_id:
            iid = getattr(self, "member_tree_iid_by_member_id", {}).get(
                member_id,
                "",
            )
            if iid:
                self.member_tree_selection.select(iid)
        if hasattr(self, "candidate_tree_adapter"):
            self.candidate_tree_adapter.sync_selection(
                self.selection_state.selected_candidate_point_id
            )

    def _update_performance_diagnostics_display(self) -> None:
        if not hasattr(self, "performance_diagnostics_var"):
            return
        if not self.performance_diagnostics_enabled_var.get():
            self.performance_diagnostics_var.set("效能診斷：未啟用")
            return
        item_count = self.performance_diagnostics.canvas_item_count
        try:
            if getattr(self, "canvas", None) is not None:
                item_count = len(self.canvas.find_all())
        except self.tk.TclError:
            pass
        self.performance_diagnostics.canvas_item_count = item_count
        values = self.performance_diagnostics
        self.performance_diagnostics_var.set(
            "Full {0}｜Members {1}｜Candidates {2}｜Selection {3}｜"
            "Temp {4}｜Tree {5}｜Items {6}｜Pending {7}｜Calls {8}｜No-op {9}".format(
                values.full_scene_rebuilds,
                values.engineering_member_rebuilds,
                values.candidate_layer_rebuilds,
                values.selection_overlay_updates,
                values.temporary_overlay_updates,
                values.candidate_tree_rebuilds,
                values.canvas_item_count,
                "是" if self.render_scheduler.pending else "否",
                values.selection_controller_calls,
                values.idempotent_skips,
            )
        )

    def _current_review_coordinate_system(self) -> CoordinateSystem:
        mode = str(self.coordinate_mode_var.get() or "world").strip().lower()
        if mode == "local" and self.selected_origin_world is not None:
            return CoordinateSystem(
                "local",
                float(self.selected_origin_world[0]),
                float(self.selected_origin_world[1]),
                "selected_candidate_point",
            )
        return CoordinateSystem()

    def _build_review_state(self) -> dict[str, Any]:
        """Capture JSON-safe review inputs plus an optional diagnostics snapshot."""

        if self.result is not None:
            state = self.result.to_debug_dict()
        elif self._initial_state_matches_source:
            state = copy.deepcopy(self.initial_state)
        else:
            state = {}

        layer_roles = self._current_layer_roles()
        coordinate_system = self._current_review_coordinate_system()
        import_mode = str(self.mode_var.get() or "replace").strip().lower()
        if import_mode not in {"replace", "append"}:
            import_mode = "replace"

        replay_source = self.world_result or self.result
        manual_overrides = (
            capture_manual_overrides(replay_source)
            if replay_source is not None
            else manual_overrides_from_review_state(self.initial_state)
        )
        state.update(
            {
                "review_state_version": 1,
                "source_path": str(self.file_path.resolve()),
                "source_fingerprint": self.importer.source_fingerprint,
                "layer_names": list(self.importer.layer_names),
                "layer_classification": dict(layer_roles),
                "layer_assignments": [
                    {
                        "layer_name": layer_name,
                        "layer_type": layer_type,
                    }
                    for layer_name, layer_type in layer_roles.items()
                ],
                "coordinate_system": asdict(coordinate_system),
                "import_mode": import_mode,
                "excluded_sources": [
                    asdict(source) for source in self.excluded_sources
                ],
                "manual_overrides": [
                    asdict(override) for override in manual_overrides
                ],
                "double_support_decisions": (
                    serialize_double_support_decisions(
                        self.double_support_decisions
                    )
                ),
            }
        )
        return state

    def _apply(self) -> None:
        from tkinter import messagebox

        if self.result is None or not self.result.can_import or not self.coordinate_valid:
            return
        member = self._selected_member()
        if member is not None and (
            self.selection_state.pending_start_point_id
            != member.selected_start_point_id
            or self.selection_state.pending_end_point_id
            != member.selected_end_point_id
        ):
            if not messagebox.askyesno(
                "尚有未套用的工程線修正",
                "目前起終點只存在於待套用狀態。\n"
                "若繼續，Solver 將使用原本正式工程線。\n\n"
                "確定不套用本次修改並繼續匯入嗎？",
                parent=self.window,
            ):
                return
        warning_count = sum(message.severity == "warning" for message in self.result.messages)
        if warning_count and not messagebox.askyesno(
            "仍有警告",
            f"目前仍有 {warning_count} 項警告。\n建議先修正警告後再匯入。\n\n確定仍要匯入嗎？",
            parent=self.window,
        ):
            return
        self.import_mode = self.mode_var.get()
        self.review_state = self._build_review_state()
        self.dialog_action = "complete"
        self._save_ui_state()
        self.window.destroy()

    def _pause(self) -> None:
        """Return to Main without validation or ProjectDataModel mutation."""

        self.import_mode = self.mode_var.get()
        self.review_state = self._build_review_state()
        self.dialog_action = "pause"
        self._save_ui_state()
        self.window.destroy()

    def _close_dialog(self) -> None:
        if self.allow_pause:
            self._pause()
        else:
            self._cancel()

    def _cancel(self) -> None:
        self.dialog_action = "cancel"
        self.result = None
        self.world_result = None
        self.review_state = {}
        self._save_ui_state()
        self.window.destroy()
