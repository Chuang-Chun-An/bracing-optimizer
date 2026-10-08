"""Tkinter dialog for reviewing and applying DXF imports."""

from __future__ import annotations

import copy
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from bracing_optimizer.presentation.cad_view_interaction import CADViewport
from bracing_optimizer.presentation.field_labels import (
    corner_brace_transfer_mode_label,
    dxf_entity_type_label,
    engineering_field_label,
    member_role_label,
    recognition_method_label,
)

from .controllers import SelectionController
from .corner_brace_repair import (
    CornerBraceRepairCandidate,
    CornerBraceRepairPlan,
)
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
    Waler,
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
    problem_severity_rank,
    review_item_guidance,
)
from .support_pairing import (
    set_double_support_candidate_accepted,
)
from .material_recognition import (
    material_spec_options,
)
from .waler_contact_adjustment import (
    WalerContactAdjustmentPlan,
    format_adjustment_plan,
)
from .waler_engineering_line_repair import (
    is_waler_engineering_line_repair_eligible,
)
from .source_exclusion import (
    normalize_source_handles,
    result_member_counts,
    result_severity_counts,
)
from .review_confirmation import (
    FORMAL_REVIEW_ROLES,
    review_item_can_be_confirmed,
)
from .review_recovery import RecoveryCategory, RecoverySummary
from .review_workflow import (
    DXFReviewSnapshot,
    DXFReviewWorkflow,
    ReviewMutation,
    ReviewMutationEffects,
    SourceExclusionPlan,
)
from window_layout import (
    _active_monitor_work_areas,
    fit_window_geometry_to_work_areas,
)


WALER_CONTACT_FACE_ADOPTION_NOTICE = (
    "此線將作為圍令接觸面（支撐頂到的面），不是圍令中心線"
)
WALER_FORMALIZATION_SOURCE_POINTS = "manual_candidate_points"
WALER_FORMALIZATION_SOURCE_CAD = "cad_manual"
WALER_CAD_UPDATED_MESSAGE = "CAD 線已更新，請重新開啟圍令正式化"


@dataclass(frozen=True)
class WalerFormalizationSession:
    """Presentation-only inputs captured when the formalization tool opens."""

    member_id: str
    opened_revision: int
    source_identity: tuple[str, ...]
    start_options: tuple[CandidatePoint, ...]
    end_options: tuple[CandidatePoint, ...]
    selected_start_point_id: str
    selected_end_point_id: str
    cad_start_point_id: str = ""
    cad_end_point_id: str = ""
    cad_pair_identity: tuple[
        tuple[str, float, float],
        tuple[str, float, float],
    ] | None = None


@dataclass(frozen=True)
class DXFImportDialogOutcome:
    """Explicit boundary between pausing review and completing an import."""

    action: str
    review_state: dict[str, Any]
    import_mode: str
    result: DXFImportResult | None = None
    world_result: DXFImportResult | None = None


@dataclass(frozen=True)
class WalerConnectedMemberSummary:
    """Presentation-only reverse projection of formal Waler connections."""

    strut_ids: tuple[str, ...] = ()
    brace_ids: tuple[str, ...] = ()
    corner_brace_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ErrorSourceHitIndexStamp:
    """Inputs that make screen-space unresolved-error hit records current."""

    viewport_transform: tuple[float, float, float, float, float] | None
    render_generation: int
    visibility_signature: tuple[bool, bool, tuple[str, ...]]
    review_items_signature: tuple[tuple[Any, ...], ...]
    active_result_signature: tuple[int, str]


def _member_id_sort_key(identifier: str) -> tuple[tuple[object, ...], ...]:
    """Sort member IDs naturally without assigning engineering meaning."""

    return tuple(
        (0, int(token), token)
        if token.isdigit()
        else (1, token.casefold(), token)
        for token in re.split(r"(\d+)", identifier)
        if token
    )


def build_waler_connected_member_summary(
    result: DXFImportResult | None,
    waler_id: str,
) -> WalerConnectedMemberSummary:
    """Project formal connection identities into an immutable UI summary."""

    if result is None or not waler_id:
        return WalerConnectedMemberSummary()

    strut_ids = {
        member.id
        for member in result.struts
        if member.id
        and (member.from_waler == waler_id or member.to_waler == waler_id)
    }
    brace_ids = {
        member.id
        for member in result.braces
        if member.id
        and member.has_formal_connection
        and (member.from_waler == waler_id or member.to_waler == waler_id)
    }
    formal_corner_ids = {
        member.id for member in result.corner_braces if member.id
    }
    corner_brace_ids = {
        connection.corner_brace_id
        for connection in result.corner_brace_connections
        if connection.corner_brace_id in formal_corner_ids
        and connection.waler_id == waler_id
    }

    return WalerConnectedMemberSummary(
        strut_ids=tuple(sorted(strut_ids, key=_member_id_sort_key)),
        brace_ids=tuple(sorted(brace_ids, key=_member_id_sort_key)),
        corner_brace_ids=tuple(
            sorted(corner_brace_ids, key=_member_id_sort_key)
        ),
    )


def format_review_recovery_summary(summary: RecoverySummary) -> str:
    """Format the planner-owned recovery meaning without recalculating it."""

    labels = {
        RecoveryCategory.PRESERVED: "已保留",
        RecoveryCategory.REQUIRES_REVIEW: "需重新檢查",
        RecoveryCategory.DISABLED: "已停用",
    }
    lines = ["候選 DXF 內容不同，但可建立恢復後的 Review："]
    for category in RecoveryCategory:
        entries = summary.entries_for(category)
        lines.append(f"\n{labels[category]}：{summary.counts[category]} 項")
        lines.extend(
            f"• {entry.label}：{entry.description}"
            for entry in entries
        )
    lines.append("\n是否採用此恢復結果並繼續 DXF Review？")
    return "\n".join(lines)


def confirm_review_recovery(
    parent: Any,
    summary: RecoverySummary,
    *,
    askyesno: Any | None = None,
) -> bool:
    """Collect the one explicit acceptance required for compatible recovery."""

    if askyesno is None:
        from tkinter import messagebox

        askyesno = messagebox.askyesno
    return bool(
        askyesno(
            "採用 DXF Review 恢復結果",
            format_review_recovery_summary(summary),
            parent=parent,
        )
    )


class DXFImportDialog:
    """Engineer-oriented import summary, issue list, location and preview UI."""

    _REVIEW_SNAPSHOT_FIELDS = frozenset({
        "world_result",
        "result",
        "problem_records",
        "review_items",
        "excluded_sources",
        "double_support_decisions",
        "review_confirmations",
        "selected_origin_world",
        "coordinate_valid",
        "import_mode",
        "last_manual_replay_report",
    })

    def __getattr__(self, name: str) -> Any:
        """Expose workflow state through one immutable presentation snapshot."""

        if name in self._REVIEW_SNAPSHOT_FIELDS:
            snapshot = self.__dict__.get("_review_snapshot")
            if snapshot is not None:
                return getattr(snapshot, name)
        raise AttributeError(
            f"{type(self).__name__!s} object has no attribute {name!r}"
        )

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
            self._invalidate_error_source_hit_index()

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
                "保存的 DXF 檢核座標設定格式錯誤，無法繼續。"
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
        self.review_workflow = DXFReviewWorkflow(
            self.importer,
            self.file_path,
            initial_state=self.initial_state,
            material_specs=self.material_specs,
            resume_review=self.resume_review,
            initial_world_result=initial_world_result,
        )
        self._initial_state_matches_source = (
            self.review_workflow.initial_state_matches_source
        )
        self.exclusion_fingerprint_mismatch = (
            self.review_workflow.exclusion_fingerprint_mismatch
        )
        self._exclusion_fingerprint_notice_shown = False
        self._sync_review_workflow_state()
        self.dialog_action = ""
        self.review_state: dict[str, Any] = {}
        self.waler_adjustment_preview_plan: WalerContactAdjustmentPlan | None = None
        self._waler_adjustment_overlay_items: list[int] = []
        self.corner_brace_repair_plan: CornerBraceRepairPlan | None = None
        self.corner_brace_repair_candidate_id = ""
        self.corner_brace_repair_window: Any = None
        self.corner_brace_repair_tree: Any = None
        self.corner_brace_repair_audit_expanded = False
        self._corner_brace_repair_overlay_items: list[int] = []
        self.column_repair_window: Any = None
        self.column_repair_plan: Any = None
        self.column_repair_details_var: Any = None
        self._column_repair_overlay_items: list[int] = []
        self.waler_formalization_window: Any = None
        self.waler_formalization_session: WalerFormalizationSession | None = None
        self.waler_formalization_source_var: Any = None
        self.waler_formalization_start_var: Any = None
        self.waler_formalization_end_var: Any = None
        self.waler_formalization_status_var: Any = None
        self.waler_formalization_point_buttons: list[Any] = []
        self._contact_panel_waler_id = ""
        self.problem_record_by_iid: dict[str, ProblemRecord] = {}
        self.selected_problem: ProblemRecord | None = None
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
        self.canvas_error_source_hit_lines: list[
            tuple[str, Point, Point]
        ] = []
        self._error_source_hit_index_stamp: ErrorSourceHitIndexStamp | None = None
        self._preview_render_generation = 0
        self._preview_scene_revision = -1
        self._preview_source_geometry_signature: tuple[Any, ...] | None = None
        self._pending_source_style_handles: set[str] = set()
        self._pending_source_exclusion_planning = False
        self._pending_source_tree_identity_by_iid: dict[str, str] = {}
        self._pending_gate_previous_states: dict[int, tuple[Any, str]] = {}
        self._tooltip_window: Any = None
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
        self._debug_payload_revision: int | None = None
        self._debug_payload_dirty = True
        self._debug_payload_text = ""
        self.preview_cursor_var = tk.StringVar(value="游標：—")
        self.preview_coordinate_var = tk.StringVar(value="座標系統：尚未套用")
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
        self.candidate_point_store = self.review_workflow.candidate_point_store
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
        # The main Review layout is intentionally not one large scrolling page.
        # The left navigator, diagnostics header and footer remain fixed while
        # the right-hand detail column owns its vertical scrolling.
        self.form_scroll_host = ttk.Frame(self.window)
        self.form_content = ttk.Frame(self.form_scroll_host)
        self.form_content.pack(fill="both", expand=True)

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
        self.layer_use_vars: dict[str, Any] = {}
        for layer in self.importer.layer_names:
            variable = tk.StringVar(
                value=self._initial_layer_use(
                    layer,
                    saved_classification,
                    self.default_layer_mapping,
                )
            )
            self.layer_use_vars[layer] = variable
        self.mode_var = tk.StringVar(value=self.import_mode)
        self.coordinate_mode_var = tk.StringVar(
            value=("local" if self.selected_origin_world is not None else "world")
        )
        self.coordinate_error_var = tk.StringVar(value="")
        self.coordinate_info_var = tk.StringVar(value="")
        self.coordinate_example_var = tk.StringVar(value="")
        self.layer_settings_window = None
        self.coordinate_settings_window = None
        self.double_support_settings_window = None
        self._build_high_impact_settings(self.form_content)

        review_frame = ttk.Frame(self.form_content)
        review_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self._build_engineering_review(review_frame)

        diagnostics_frame = ttk.Frame(self.form_content)
        diagnostics_frame.pack(fill="x", padx=10, pady=(0, 10))
        self._build_diagnostics_tab(diagnostics_frame, scrolledtext)

        footer = ttk.Frame(self.window)
        footer.pack(side="bottom", fill="x", padx=10, pady=10)
        self.import_mode_frame = ttk.LabelFrame(
            footer,
            text="整批匯入方式",
        )
        self.import_mode_frame.pack(fill="x", pady=(0, 8))
        import_mode_options = ttk.Frame(self.import_mode_frame)
        import_mode_options.pack(fill="x", padx=8, pady=(4, 0))
        self.replace_import_mode_button = ttk.Radiobutton(
            import_mode_options,
            text="取代目前工程",
            variable=self.mode_var,
            value="replace",
            command=self._on_import_mode_changed,
        )
        self.replace_import_mode_button.pack(side="left", padx=(0, 12))
        self.append_import_mode_button = ttk.Radiobutton(
            import_mode_options,
            text="附加到目前工程",
            variable=self.mode_var,
            value="append",
            command=self._on_import_mode_changed,
        )
        self.append_import_mode_button.pack(side="left")
        ttk.Label(
            self.import_mode_frame,
            text=(
                "套用於本次所有已辨識構件，不是目前選取的單一構件。"
                "取代會以本次結果取代主畫面現有工程構件；"
                "附加會保留現有構件並加入本次結果。"
            ),
            foreground="#455a64",
            justify="left",
        ).pack(fill="x", padx=8, pady=(2, 5))

        footer_actions = ttk.Frame(footer)
        footer_actions.pack(fill="x")
        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(
            footer_actions,
            textvariable=self.status_var,
        )
        self.status_label.pack(side="left", fill="x", expand=True)
        pause_text = "暫停並返回主畫面" if self.allow_pause else "取消"
        pause_command = self._pause if self.allow_pause else self._cancel
        self.pause_button = ttk.Button(
            footer_actions,
            text=pause_text,
            command=pause_command,
            width=18,
        )
        self.apply_button = ttk.Button(
            footer_actions,
            text="完成匯入",
            command=self._apply,
            width=18,
        )
        self.apply_button.pack(side="right")
        self.pause_button.pack(side="right", padx=(6, 6))
        self.apply_button.configure(state="disabled", text="不可匯入")
        self.status_var.set("請開啟「圖層 ✓」確認用途並開始辨識。")
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

    def _sync_review_workflow_state(self) -> None:
        """Refresh the dialog's single read-only Review-state projection."""

        self._review_snapshot: DXFReviewSnapshot = self.review_workflow.snapshot
        self._invalidate_error_source_hit_index()
        self._refresh_pending_source_exclusion_controls()

    def _show_workflow_confirmation_invalidations(
        self,
        mutation: ReviewMutation,
    ) -> None:
        if not mutation.invalidated_confirmations:
            return
        from tkinter import messagebox

        messagebox.showinfo(
            "構件確認已重設",
            "以下已確認構件因本次修改受影響，已重設為未確認：\n\n"
            + "、".join(mutation.invalidated_confirmations),
            parent=self.window,
        )

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

    def _update_review_detail_scrollregion(self, _event: Any = None) -> None:
        canvas = getattr(self, "review_detail_canvas", None)
        if canvas is None:
            return
        bounds = canvas.bbox("all")
        if bounds is not None:
            canvas.configure(scrollregion=bounds)

    def _resize_review_detail_content(self, event: Any) -> None:
        self.review_detail_canvas.itemconfigure(
            self.review_detail_content_window,
            width=max(int(event.width), 1),
        )

    def _on_review_detail_mousewheel(self, event: Any) -> str | None:
        canvas = getattr(self, "review_detail_canvas", None)
        content = getattr(self, "review_detail_content", None)
        if canvas is None or content is None:
            return None
        widget = getattr(event, "widget", None)
        if widget is None or not self._widget_is_descendant(widget, content):
            return None
        try:
            if str(widget.winfo_class()) in {"Treeview", "Text", "Listbox"}:
                return None
        except Exception:
            pass
        units = self._form_wheel_units(event)
        if units == 0 or not self._widget_can_scroll(canvas, units):
            return None
        canvas.yview_scroll(units, "units")
        return "break"

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

    def _build_high_impact_settings(self, parent: Any) -> None:
        settings = self.ttk.Frame(parent)
        settings.pack(fill="x", padx=10, pady=10)
        self.layer_settings_button = self.ttk.Button(
            settings,
            text="圖層 ✓",
            command=self._open_layer_settings,
        )
        self.layer_settings_button.pack(side="left", padx=(0, 6))
        self.coordinate_settings_button = self.ttk.Button(
            settings,
            text="座標 ✓",
            command=self._open_coordinate_settings,
        )
        self.coordinate_settings_button.pack(side="left", padx=6)
        self.double_support_settings_button = self.ttk.Button(
            settings,
            text="雙路支撐 ✓",
            command=self._open_double_support_settings,
        )
        self.double_support_settings_button.pack(side="left", padx=6)

    def _focus_existing_settings_window(self, attribute: str) -> bool:
        window = getattr(self, attribute, None)
        if window is None:
            return False
        try:
            if not window.winfo_exists():
                setattr(self, attribute, None)
                return False
            window.deiconify()
            window.lift()
            window.focus_force()
            return True
        except self.tk.TclError:
            setattr(self, attribute, None)
            return False

    def _close_settings_window(self, attribute: str) -> None:
        window = getattr(self, attribute, None)
        setattr(self, attribute, None)
        if window is None:
            return
        try:
            window.destroy()
        except self.tk.TclError:
            pass

    def _open_layer_settings(self) -> None:
        if self._focus_existing_settings_window("layer_settings_window"):
            return
        window = self.tk.Toplevel(self.window)
        self.layer_settings_window = window
        window.title(f"圖層設定 — {self.file_path.name}")
        row_count = max(1, len(self.layer_use_vars))
        window.geometry(f"620x{min(720, max(260, 145 + row_count * 30))}")
        window.minsize(520, 240)
        window.protocol(
            "WM_DELETE_WINDOW",
            lambda: self._close_settings_window("layer_settings_window"),
        )

        header = self.ttk.Frame(window)
        header.pack(fill="x", padx=(12, 30), pady=(10, 4))
        self.ttk.Label(
            header,
            text="圖層名稱",
            font=("Microsoft JhengHei", 9, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.ttk.Label(
            header,
            text="用途",
            font=("Microsoft JhengHei", 9, "bold"),
        ).grid(row=0, column=1, sticky="w")
        header.columnconfigure(0, weight=1)
        header.columnconfigure(1, minsize=170)

        host = self.ttk.Frame(window)
        host.pack(fill="both", expand=True, padx=10)
        canvas = self.tk.Canvas(host, highlightthickness=0, yscrollincrement=24)
        scrollbar = self.ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        rows = self.ttk.Frame(canvas)
        rows_window = canvas.create_window((0, 0), window=rows, anchor="nw")
        rows.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(rows_window, width=event.width),
        )
        self.layer_settings_vars = {
            layer: self.tk.StringVar(value=variable.get())
            for layer, variable in self.layer_use_vars.items()
        }
        for row, (layer, variable) in enumerate(self.layer_settings_vars.items()):
            self.ttk.Label(rows, text=layer).grid(
                row=row, column=0, sticky="w", padx=(4, 10), pady=3
            )
            self.ttk.Combobox(
                rows,
                textvariable=variable,
                values=self.LAYER_USE_OPTIONS,
                state="readonly",
                width=18,
            ).grid(row=row, column=1, sticky="ew", padx=(0, 4), pady=3)
        rows.columnconfigure(0, weight=1)
        rows.columnconfigure(1, minsize=170)

        footer = self.ttk.Frame(window)
        footer.pack(fill="x", padx=10, pady=10)
        self.ttk.Button(
            footer,
            text="取消",
            command=lambda: self._close_settings_window("layer_settings_window"),
        ).pack(side="right", padx=(6, 0))
        self.ttk.Button(
            footer,
            text="套用",
            command=self._apply_layer_settings_dialog,
        ).pack(side="right")

    def _commit_layer_settings(self, selected_uses: Mapping[str, str]) -> bool:
        """Commit all temporary layer rows and start one recognition pass."""

        normalized: dict[str, str] = {}
        for layer in self.layer_use_vars:
            selected = str(selected_uses.get(layer, "") or "")
            if selected not in self.USE_TO_ROLE:
                raise DXFImportError(
                    f"圖層「{layer}」使用了不支援的用途：{selected or '空白'}"
                )
            normalized[layer] = selected
        changed = any(
            self.layer_use_vars[layer].get() != selected
            for layer, selected in normalized.items()
        )
        if not changed and getattr(self, "result", None) is not None:
            return False
        for layer, selected in normalized.items():
            self.layer_use_vars[layer].set(selected)
        self._close_settings_window("coordinate_settings_window")
        self._close_settings_window("double_support_settings_window")
        self._convert_preview()
        return True

    def _apply_layer_settings_dialog(self) -> None:
        from tkinter import messagebox

        selected_uses = {
            layer: variable.get()
            for layer, variable in getattr(self, "layer_settings_vars", {}).items()
        }
        changed = any(
            self.layer_use_vars[layer].get() != selected_uses.get(layer, "")
            for layer in self.layer_use_vars
        )
        if changed and self._confirmed_item_snapshot():
            if not messagebox.askyesno(
                "重新設定圖層",
                "重新設定圖層會重新辨識工程模型，部分已確認構件可能需要重新檢查。是否繼續？",
                parent=self.layer_settings_window,
            ):
                return
        try:
            started = self._commit_layer_settings(selected_uses)
        except DXFImportError as exc:
            messagebox.showerror(
                "圖層設定",
                str(exc),
                parent=self.layer_settings_window,
            )
            return
        self._close_settings_window("layer_settings_window")
        if not started:
            self.status_var.set("圖層用途沒有變更，沿用目前辨識結果。")

    def _build_engineering_review(self, parent: Any) -> None:
        """Build the fixed navigator and independently scrolling detail pane."""

        body = self.ttk.Frame(parent)
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        member_frame = self.ttk.LabelFrame(body, text="構件檢核")
        member_frame.configure(width=260)
        member_frame.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        member_frame.grid_propagate(False)
        member_frame.rowconfigure(0, weight=1)
        member_frame.columnconfigure(0, weight=1)
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
        self.member_tree.grid(row=0, column=0, sticky="nsew")
        member_scroll.grid(row=0, column=1, sticky="ns")
        self.member_tree.bind("<<TreeviewSelect>>", self._on_member_selected)
        self.member_tree_selection = TreeSelectionSynchronizer(
            self.member_tree,
            self.window.after_idle,
        )

        detail_host = self.ttk.LabelFrame(body, text="詳細資訊")
        detail_host.grid(row=0, column=1, sticky="nsew")
        detail_host.rowconfigure(0, weight=1)
        detail_host.columnconfigure(0, weight=1)
        detail_background = self.ttk.Style(self.window).lookup(
            "TFrame", "background"
        )
        self.review_detail_canvas = self.tk.Canvas(
            detail_host,
            background=detail_background or self.window.cget("background"),
            borderwidth=0,
            highlightthickness=0,
            yscrollincrement=24,
        )
        review_scroll = self.ttk.Scrollbar(
            detail_host,
            orient="vertical",
            command=self.review_detail_canvas.yview,
        )
        self.review_detail_canvas.configure(yscrollcommand=review_scroll.set)
        self.review_detail_canvas.grid(row=0, column=0, sticky="nsew")
        review_scroll.grid(row=0, column=1, sticky="ns")
        self.review_detail_content = self.ttk.Frame(self.review_detail_canvas)
        self.review_detail_content_window = self.review_detail_canvas.create_window(
            (0, 0),
            window=self.review_detail_content,
            anchor="nw",
        )
        self.review_detail_content.bind(
            "<Configure>", self._update_review_detail_scrollregion
        )
        self.review_detail_canvas.bind(
            "<Configure>", self._resize_review_detail_content
        )
        self.window.bind(
            "<MouseWheel>", self._on_review_detail_mousewheel, add="+"
        )
        self.window.bind(
            "<Button-4>", self._on_review_detail_mousewheel, add="+"
        )
        self.window.bind(
            "<Button-5>", self._on_review_detail_mousewheel, add="+"
        )
        self.review_detail_content.columnconfigure(0, weight=1)

        data_frame = self.ttk.Frame(self.review_detail_content)
        data_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        data_frame.columnconfigure(0, weight=38)
        data_frame.columnconfigure(2, weight=62)
        recognition_frame = self.ttk.LabelFrame(
            data_frame,
            text="DXF 辨識資料",
        )
        recognition_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.ttk.Separator(data_frame, orient="vertical").grid(
            row=0, column=1, sticky="ns", padx=2
        )
        engineering_frame = self.ttk.LabelFrame(
            data_frame,
            text="工程資料",
        )
        engineering_frame.grid(row=0, column=2, sticky="nsew", padx=(8, 0))
        engineering_frame.columnconfigure(0, weight=1)

        self.recognition_info_vars = {
            key: self.tk.StringVar(value="—")
            for key in (
                "display_id",
                "system_status",
                "human_status",
                "role",
                "layer",
                "handles",
                "entity_types",
                "method",
                "selection_source",
                "source_width",
                "confidence",
                "centerline",
                "engineering_candidate",
                "warnings",
                "exclusion_reason",
            )
        }
        # Preserve the public-ish legacy attribute used by a few integrations.
        self.member_info_vars = self.recognition_info_vars
        for row, (label, key) in enumerate(
            (
                ("檢核項目", "display_id"),
                ("系統狀態", "system_status"),
                ("人工狀態", "human_status"),
                ("角色", "role"),
                ("來源圖層", "layer"),
                ("來源圖元代碼（Handle）", "handles"),
                ("圖元類型", "entity_types"),
                ("辨識方法", "method"),
                ("選擇來源", "selection_source"),
                ("來源寬度 (mm)", "source_width"),
                ("辨識信心度", "confidence"),
                ("中心線", "centerline"),
                ("工程線候選", "engineering_candidate"),
                ("辨識警告", "warnings"),
                ("排除原因", "exclusion_reason"),
            )
        ):
            self.ttk.Label(recognition_frame, text=f"{label}：").grid(
                row=row, column=0, padx=(7, 4), pady=2, sticky="ne"
            )
            self.ttk.Label(
                recognition_frame,
                textvariable=self.recognition_info_vars[key],
                wraplength=240,
                justify="left",
            ).grid(row=row, column=1, padx=(0, 7), pady=2, sticky="nw")
        recognition_frame.columnconfigure(1, weight=1)

        self.engineering_data_rows_frame = self.ttk.Frame(engineering_frame)
        self.engineering_data_rows_frame.grid(
            row=0, column=0, sticky="ew", padx=7, pady=(5, 2)
        )
        self.engineering_data_rows_frame.columnconfigure(1, weight=1)
        self.engineering_empty_var = self.tk.StringVar(
            value="請從左側選擇檢核項目。"
        )
        self.engineering_empty_label = self.ttk.Label(
            self.engineering_data_rows_frame,
            textvariable=self.engineering_empty_var,
            foreground="#607d8b",
        )
        self.engineering_empty_label.grid(row=0, column=0, sticky="w")
        self._build_phase3_material_editor(engineering_frame)
        self._build_phase3_waler_contact_editor(engineering_frame)

        self._build_phase3_issue_section(self.review_detail_content)
        self._build_phase3_modification_tools(self.review_detail_content)
        self._build_phase3_candidate_section(self.review_detail_content)

        # Keep the per-member confirmation action outside the scrolling detail
        # canvas so it remains visible while reviewing long member data.
        self.review_confirmation_frame = self.ttk.Frame(detail_host)
        self.review_confirmation_frame.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=8,
            pady=(6, 8),
        )
        self.review_confirmation_button = self.ttk.Button(
            self.review_confirmation_frame,
            text="確認此構件",
            command=self._confirm_selected_review_item,
            state="disabled",
        )
        self.review_confirmation_button.pack(side="right")
        self.review_confirmation_frame.grid_remove()

    def _build_phase3_material_editor(self, parent: Any) -> None:
        self.material_spec_frame = self.ttk.LabelFrame(
            parent,
            text="材料規格確認",
        )
        self.material_spec_frame.grid(
            row=1, column=0, sticky="ew", padx=8, pady=(8, 2)
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
            wraplength=400,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 5))
        self.material_spec_frame.columnconfigure(1, weight=1)
        self.material_spec_frame.grid_remove()

    def _build_phase3_waler_contact_editor(self, parent: Any) -> None:
        self.waler_contact_frame = self.ttk.LabelFrame(
            parent,
            text="圍令接觸位置調整",
        )
        self.waler_contact_frame.grid(
            row=2, column=0, sticky="ew", padx=8, pady=(8, 6)
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
                ("背填厚度 (mm)", "original_backfill_mm", "adopted_backfill_mm"),
                ("圍令寬度 (mm)", "original_waler_width_mm", "adopted_waler_width_mm"),
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
            wraplength=400,
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
            wraplength=400,
            justify="left",
        ).grid(row=8, column=0, columnspan=3, sticky="w", padx=6, pady=(0, 5))
        self.waler_contact_frame.columnconfigure(1, weight=1)
        self.waler_contact_frame.columnconfigure(2, weight=1)
        self.waler_contact_frame.grid_remove()

    def _build_phase3_issue_section(self, parent: Any) -> None:
        self.review_issue_frame = self.ttk.LabelFrame(
            parent,
            text="問題／處理建議",
        )
        self.review_issue_frame.grid(
            row=1, column=0, sticky="ew", padx=8, pady=4
        )
        self.detail_problem_tree = self.ttk.Treeview(
            self.review_issue_frame,
            columns=("severity", "code", "description"),
            show="headings",
            selectmode="browse",
            height=1,
        )
        for column, title, width, anchor in (
            ("severity", "等級", 70, "center"),
            ("code", "代碼", 185, "w"),
            ("description", "說明", 410, "w"),
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
        self.detail_problem_tree.grid(
            row=0, column=0, sticky="ew", padx=6, pady=(6, 2)
        )
        self.detail_problem_tree.bind(
            "<<TreeviewSelect>>", self._on_detail_problem_activated
        )
        self.detail_problem_tree.bind(
            "<Double-Button-1>", self._on_detail_problem_activated
        )
        self.detail_problem_tree.bind("<Return>", self._on_detail_problem_activated)
        self.detail_problem_empty_var = self.tk.StringVar(
            value="請先選取檢核項目。"
        )
        self.ttk.Label(
            self.review_issue_frame,
            textvariable=self.detail_problem_empty_var,
            foreground="#455a64",
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, sticky="w", padx=6, pady=(1, 3))
        self.detail_guidance_var = self.tk.StringVar(value="")
        self.ttk.Label(
            self.review_issue_frame,
            text="處理建議",
            font=("Microsoft JhengHei", 9, "bold"),
        ).grid(row=2, column=0, sticky="w", padx=6, pady=(3, 1))
        self.ttk.Label(
            self.review_issue_frame,
            textvariable=self.detail_guidance_var,
            foreground="#37474f",
            wraplength=700,
            justify="left",
        ).grid(row=3, column=0, sticky="ew", padx=6, pady=(0, 6))
        self.review_issue_frame.columnconfigure(0, weight=1)

    def _build_phase3_modification_tools(self, parent: Any) -> None:
        self.modification_tools_frame = self.ttk.LabelFrame(
            parent,
            text="修改工具",
        )
        self.modification_tools_frame.grid(
            row=2, column=0, sticky="ew", padx=8, pady=4
        )
        self.modification_tools_frame.columnconfigure(0, weight=1)
        self.geometry_tools_frame = self.ttk.Frame(self.modification_tools_frame)
        self.geometry_tools_frame.grid(
            row=0, column=0, sticky="ew", padx=7, pady=(5, 3)
        )
        self.ttk.Label(
            self.geometry_tools_frame,
            text="幾何",
            font=("Microsoft JhengHei", 9, "bold"),
        ).pack(side="left", padx=(0, 10))
        self.candidate_pick_mode_var = self.tk.StringVar(value="")
        self.endpoint_tools_frame = self.ttk.Frame(self.geometry_tools_frame)
        self.endpoint_tools_frame.pack(side="left")
        self.candidate_pick_start_button = self.ttk.Radiobutton(
            self.endpoint_tools_frame,
            text="選起點",
            variable=self.candidate_pick_mode_var,
            value="pick_start",
            command=lambda: self._begin_candidate_pick("pick_start"),
        )
        self.candidate_pick_start_button.pack(side="left", padx=(0, 5))
        self.candidate_pick_end_button = self.ttk.Radiobutton(
            self.endpoint_tools_frame,
            text="選終點",
            variable=self.candidate_pick_mode_var,
            value="pick_end",
            command=lambda: self._begin_candidate_pick("pick_end"),
        )
        self.candidate_pick_end_button.pack(side="left", padx=5)
        self.cad_engineering_line_button = self.ttk.Button(
            self.geometry_tools_frame,
            text="從 CAD 指定工程線",
            command=self._read_cad_engineering_line,
        )
        self.cad_engineering_line_button.pack(side="left", padx=(10, 0))
        self.corner_brace_repair_button = self.ttk.Button(
            self.geometry_tools_frame,
            text="修補角撐",
            command=self._open_corner_brace_repair_preview,
            state="disabled",
        )
        self.corner_brace_repair_button.pack(side="left", padx=(10, 0))
        self.column_association_repair_button = self.ttk.Button(
            self.geometry_tools_frame,
            text="中間柱關聯修補",
            command=self._open_column_association_repair,
        )
        self.column_association_repair_button.pack(side="left", padx=(10, 0))
        self.waler_formalization_button = self.ttk.Button(
            self.geometry_tools_frame,
            text="圍令正式化",
            command=self._open_waler_formalization,
            state="disabled",
        )
        self.waler_formalization_button.pack(side="left", padx=(10, 0))

        self.source_tools_frame = self.ttk.Frame(self.modification_tools_frame)
        self.source_tools_frame.grid(
            row=1, column=0, sticky="ew", padx=7, pady=(3, 5)
        )
        self.ttk.Label(
            self.source_tools_frame,
            text="來源",
            font=("Microsoft JhengHei", 9, "bold"),
        ).pack(side="left", padx=(0, 10))
        self.source_exclusion_button = self.ttk.Button(
            self.source_tools_frame,
            text="標記待排除",
            command=self._on_source_exclusion_action,
            state="disabled",
        )
        self.source_exclusion_button.pack(side="left")
        self.source_exclusion_status_var = self.tk.StringVar(value="")
        self.source_exclusion_status_label = self.ttk.Label(
            self.modification_tools_frame,
            textvariable=self.source_exclusion_status_var,
            foreground="#795548",
            wraplength=700,
            justify="left",
        )
        self.source_exclusion_status_label.grid(
            row=2, column=0, sticky="ew", padx=7, pady=(0, 3)
        )
        self.pending_source_frame = self.ttk.LabelFrame(
            self.modification_tools_frame,
            text="待排除來源",
        )
        self.pending_source_frame.grid(
            row=3, column=0, sticky="ew", padx=7, pady=(2, 5)
        )
        self.pending_source_frame.columnconfigure(0, weight=1)
        self.pending_source_tree = self.ttk.Treeview(
            self.pending_source_frame,
            columns=("component", "source", "action"),
            show="headings",
            selectmode="browse",
            height=4,
        )
        for column, label, width, anchor in (
            ("component", "構件 ID", 150, "w"),
            ("source", "來源", 360, "w"),
            ("action", "操作", 70, "center"),
        ):
            self.pending_source_tree.heading(column, text=label)
            self.pending_source_tree.column(
                column,
                width=width,
                minwidth=60,
                anchor=anchor,
                stretch=column == "source",
            )
        self.pending_source_tree.grid(
            row=0, column=0, sticky="ew", padx=5, pady=(5, 3)
        )
        self.pending_source_tree.bind(
            "<<TreeviewSelect>>",
            self._on_pending_source_selected,
        )
        self.pending_source_tree.bind(
            "<ButtonRelease-1>",
            self._on_pending_source_tree_click,
        )
        pending_actions = self.ttk.Frame(self.pending_source_frame)
        pending_actions.grid(row=1, column=0, sticky="ew", padx=5, pady=(2, 5))
        self.pending_source_discard_button = self.ttk.Button(
            pending_actions,
            text="捨棄待排除",
            command=self._discard_pending_source_exclusions,
            state="disabled",
        )
        self.pending_source_discard_button.pack(side="right")
        self.pending_source_apply_button = self.ttk.Button(
            pending_actions,
            text="重新辨識並套用（0）",
            command=self._apply_pending_source_exclusions,
            state="disabled",
        )
        self.pending_source_apply_button.pack(side="right", padx=(0, 6))
        self.pending_source_frame.grid_remove()
        self.cad_temp_status_label = self.ttk.Label(
            self.modification_tools_frame,
            textvariable=self.cad_temp_status_var,
            foreground="#37474f",
            wraplength=700,
            justify="left",
        )
        self.cad_temp_status_label.grid(
            row=4, column=0, sticky="ew", padx=7, pady=(0, 6)
        )

    def _build_phase3_candidate_section(self, parent: Any) -> None:
        self.candidate_frame = self.ttk.LabelFrame(parent, text="候選點")
        self.candidate_action_status_var = self.tk.StringVar(
            value="請先選取構件；單擊候選點只會預覽。"
        )
        self.candidate_detail_var = self.tk.StringVar(value="候選點：—")
        self.candidate_tree = self.ttk.Treeview(
            self.candidate_frame,
            columns=("point", "x", "y", "status"),
            show="headings",
            selectmode="browse",
            height=7,
        )
        for column, label, width, anchor in (
            ("point", "點位", 180, "w"),
            ("x", "X", 125, "e"),
            ("y", "Y", 125, "e"),
            ("status", "狀態", 260, "w"),
        ):
            self.candidate_tree.heading(column, text=label)
            self.candidate_tree.column(column, width=width, anchor=anchor)
        candidate_scroll = self.ttk.Scrollbar(
            self.candidate_frame,
            orient="vertical",
            command=self.candidate_tree.yview,
        )
        self.candidate_tree.configure(yscrollcommand=candidate_scroll.set)
        self.candidate_tree.grid(
            row=0, column=0, sticky="nsew", padx=(8, 0), pady=(6, 5)
        )
        candidate_scroll.grid(
            row=0, column=1, sticky="ns", padx=(0, 6), pady=(6, 5)
        )
        self.candidate_tree.bind(
            "<<TreeviewSelect>>", self._on_candidate_point_selected
        )
        self.candidate_tree.bind("<Motion>", self._on_candidate_hover)
        self.candidate_tree.bind("<Leave>", self._clear_candidate_hover)
        self.candidate_tree_adapter = CandidateTreeAdapter(
            self.candidate_tree,
            self.window.after_idle,
        )
        self.ttk.Label(
            self.candidate_frame,
            textvariable=self.candidate_detail_var,
            foreground="#607d8b",
            wraplength=700,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 4))
        candidate_actions = self.ttk.Frame(self.candidate_frame)
        candidate_actions.grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(2, 3)
        )
        self.candidate_apply_button = self.ttk.Button(
            candidate_actions,
            text="套用選取點",
            command=self._apply_candidate_changes,
            state="disabled",
        )
        self.candidate_apply_button.pack(side="right")
        self.ttk.Label(
            self.candidate_frame,
            textvariable=self.candidate_action_status_var,
            foreground="#37474f",
            wraplength=700,
            justify="left",
        ).grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=(2, 6))
        self.candidate_frame.columnconfigure(0, weight=1)
        self.candidate_frame.grid(
            row=3, column=0, sticky="ew", padx=8, pady=4
        )
        self.candidate_frame.grid_remove()


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
        review_toolbar = self.ttk.LabelFrame(preview_window, text="目前選取")
        review_toolbar.pack(fill="x", padx=8, pady=(0, 6))
        self.ttk.Label(
            review_toolbar,
            textvariable=self.preview_selected_member_var,
            font=("Microsoft JhengHei", 10, "bold"),
        ).pack(side="left", padx=8, pady=5)
        self.preview_source_exclusion_button = self.ttk.Button(
            review_toolbar,
            text="標記待排除",
            command=self._on_source_exclusion_action,
            state="disabled",
        )
        self.preview_source_exclusion_button.pack(
            side="left", padx=(2, 8), pady=4
        )
        self.preview_pick_start_button = self.ttk.Radiobutton(
            review_toolbar,
            text="選起點",
            variable=self.candidate_pick_mode_var,
            value="pick_start",
            command=lambda: self._begin_candidate_pick("pick_start"),
        )
        self.preview_pick_start_button.pack(side="left", padx=(4, 2), pady=4)
        self.preview_pick_end_button = self.ttk.Radiobutton(
            review_toolbar,
            text="選終點",
            variable=self.candidate_pick_mode_var,
            value="pick_end",
            command=lambda: self._begin_candidate_pick("pick_end"),
        )
        self.preview_pick_end_button.pack(side="left", padx=2, pady=4)
        self.preview_apply_candidate_button = self.ttk.Button(
            review_toolbar,
            text="套用選取點",
            command=self._apply_candidate_changes,
            state="disabled",
        )
        self.preview_apply_candidate_button.pack(side="right", padx=(4, 8), pady=4)
        self.preview_cancel_candidate_button = self.ttk.Button(
            review_toolbar,
            text="取消本次選點",
            command=self._cancel_candidate_changes,
            state="disabled",
        )
        self.preview_cancel_candidate_button.pack(side="right", padx=4, pady=4)
        self._update_preview_candidate_action_state()
        self._update_source_exclusion_action_state(
            self._selected_review_item()
        )

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

    def _formal_walers_for_coordinate_picker(self) -> tuple[Waler, ...]:
        result = getattr(self, "result", None)
        return tuple(result.walers) if result is not None else ()

    def _coordinate_candidates_for_waler(
        self,
        waler_id: str,
    ) -> tuple[CandidatePoint, ...]:
        if not any(
            waler.id == waler_id
            for waler in self._formal_walers_for_coordinate_picker()
        ):
            return ()
        return tuple(self.candidate_point_store.component_points(waler_id))

    def _open_coordinate_settings(self) -> None:
        if self._focus_existing_settings_window("coordinate_settings_window"):
            return
        window = self.tk.Toplevel(self.window)
        self.coordinate_settings_window = window
        window.title("座標設定")
        window.geometry("680x560")
        window.minsize(580, 440)
        window.protocol(
            "WM_DELETE_WINDOW",
            lambda: self._close_settings_window("coordinate_settings_window"),
        )
        self.coordinate_settings_mode_var = self.tk.StringVar(
            value=self.coordinate_mode_var.get()
        )
        self.coordinate_settings_candidate = None
        self.coordinate_settings_candidate_by_iid: dict[str, CandidatePoint] = {}
        self.coordinate_settings_waler_by_iid: dict[str, str] = {}
        self.coordinate_settings_status_var = self.tk.StringVar(value="")

        mode_frame = self.ttk.LabelFrame(window, text="座標模式")
        mode_frame.pack(fill="x", padx=10, pady=(10, 6))
        self.ttk.Radiobutton(
            mode_frame,
            text="世界座標",
            variable=self.coordinate_settings_mode_var,
            value="world",
        ).pack(side="left", padx=10, pady=7)
        self.ttk.Radiobutton(
            mode_frame,
            text="局部座標",
            variable=self.coordinate_settings_mode_var,
            value="local",
        ).pack(side="left", padx=10, pady=7)

        body = self.ttk.Panedwindow(window, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=6)
        waler_frame = self.ttk.LabelFrame(body, text="① 選擇正式圍令")
        candidate_frame = self.ttk.LabelFrame(body, text="② 選擇候選點")
        body.add(waler_frame, weight=1)
        body.add(candidate_frame, weight=2)

        self.coordinate_settings_waler_tree = self.ttk.Treeview(
            waler_frame,
            columns=("waler",),
            show="headings",
            selectmode="browse",
            height=14,
        )
        self.coordinate_settings_waler_tree.heading("waler", text="正式圍令")
        self.coordinate_settings_waler_tree.column("waler", width=150, anchor="w")
        self.coordinate_settings_waler_tree.pack(fill="both", expand=True, padx=6, pady=6)
        self.coordinate_settings_waler_tree.bind(
            "<<TreeviewSelect>>",
            self._on_coordinate_waler_selected,
        )
        for index, waler in enumerate(self._formal_walers_for_coordinate_picker()):
            iid = f"coordinate_waler_{index}"
            self.coordinate_settings_waler_by_iid[iid] = waler.id
            self.coordinate_settings_waler_tree.insert(
                "", "end", iid=iid, values=(waler.id,)
            )

        self.coordinate_settings_candidate_tree = self.ttk.Treeview(
            candidate_frame,
            columns=("point", "x", "y"),
            show="headings",
            selectmode="browse",
            height=14,
        )
        for column, label, width in (
            ("point", "點位", 150),
            ("x", "X", 120),
            ("y", "Y", 120),
        ):
            self.coordinate_settings_candidate_tree.heading(column, text=label)
            self.coordinate_settings_candidate_tree.column(
                column,
                width=width,
                anchor="e" if column in {"x", "y"} else "w",
            )
        self.coordinate_settings_candidate_tree.pack(
            fill="both", expand=True, padx=6, pady=6
        )
        self.coordinate_settings_candidate_tree.bind(
            "<<TreeviewSelect>>",
            self._on_coordinate_candidate_selected,
        )

        self.ttk.Label(
            window,
            textvariable=self.coordinate_settings_status_var,
            foreground="#455a64",
        ).pack(fill="x", padx=12, pady=(0, 4))
        footer = self.ttk.Frame(window)
        footer.pack(fill="x", padx=10, pady=(4, 10))
        self.ttk.Button(
            footer,
            text="取消",
            command=lambda: self._close_settings_window(
                "coordinate_settings_window"
            ),
        ).pack(side="right", padx=(6, 0))
        self.ttk.Button(
            footer,
            text="套用",
            command=self._apply_coordinate_settings_dialog,
        ).pack(side="right")

    def _on_coordinate_waler_selected(self, _event: Any = None) -> None:
        tree = self.coordinate_settings_waler_tree
        selection = tree.selection()
        if not selection:
            return
        waler_id = self.coordinate_settings_waler_by_iid.get(selection[0], "")
        if not waler_id:
            return
        self.coordinate_settings_candidate = None
        candidate_tree = self.coordinate_settings_candidate_tree
        candidate_tree.delete(*candidate_tree.get_children())
        self.coordinate_settings_candidate_by_iid.clear()
        for index, candidate in enumerate(
            self._coordinate_candidates_for_waler(waler_id)
        ):
            iid = f"coordinate_candidate_{index}"
            self.coordinate_settings_candidate_by_iid[iid] = candidate
            candidate_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    candidate.id,
                    f"{candidate.world_point[0]:.3f}",
                    f"{candidate.world_point[1]:.3f}",
                ),
            )
        self.coordinate_settings_status_var.set(
            "請從右側選擇局部座標原點；點選只會暫存候選點，套用後才改座標。"
        )
        self._select_member(
            waler_id,
            refit=True,
            clear_problem=True,
            source="coordinate_dialog",
        )

    def _preview_coordinate_candidate(self, candidate: CandidatePoint) -> None:
        """Highlight an origin candidate without opening or focusing Preview."""

        component_id = candidate.component_id
        if component_id and component_id != self.selected_member_id:
            self._select_member(
                component_id,
                refit=True,
                clear_problem=True,
                source="coordinate_dialog",
            )
        previous_bounds = self.preview_view_bounds
        self._center_candidate_if_hidden(candidate)
        if self.preview_view_bounds != previous_bounds:
            self.render_scheduler.request(RenderDirty.FULL_SCENE)
        self.selection_controller.preview_candidate_point(
            candidate.id,
            "coordinate_dialog",
        )

    def _on_coordinate_candidate_selected(self, _event: Any = None) -> None:
        selection = self.coordinate_settings_candidate_tree.selection()
        if not selection:
            return
        candidate = self.coordinate_settings_candidate_by_iid.get(selection[0])
        if candidate is None:
            return
        self.coordinate_settings_candidate = candidate
        self.coordinate_settings_status_var.set(
            f"已選 {candidate.id}；按「套用」後才更新局部座標原點。"
        )
        self._preview_coordinate_candidate(candidate)

    def _apply_coordinate_settings_dialog(self) -> None:
        from tkinter import messagebox

        mode = self.coordinate_settings_mode_var.get()
        if mode == "world":
            self._reset_coordinate_settings()
        elif mode == "local":
            candidate = self.coordinate_settings_candidate
            if candidate is not None:
                self._set_origin_from_candidate(candidate)
            elif (
                self.coordinate_mode_var.get() == "local"
                and self.selected_origin_world is not None
            ):
                self._set_origin_from_world_point(self.selected_origin_world)
            else:
                messagebox.showwarning(
                    "座標設定",
                    "請先選擇正式圍令，再選擇一個候選點。",
                    parent=self.coordinate_settings_window,
                )
                return
        else:
            return
        self._close_settings_window("coordinate_settings_window")

    def _build_diagnostics_tab(self, parent: Any, scrolledtext: Any) -> None:
        self.all_problems_expanded = False
        self.all_problems_button = self.ttk.Button(
            parent,
            text="▶ 全部問題清單（錯誤 0／警告 0）",
            command=self._toggle_all_problems,
        )
        self.all_problems_button.pack(fill="x")

        self.all_problems_content = self.ttk.LabelFrame(
            parent,
            text="錯誤與警告（點選後自動定位）",
        )
        filters = self.ttk.Frame(self.all_problems_content)
        filters.pack(fill="x", padx=6, pady=4)
        self.problem_filter_var = self.tk.StringVar(value="all")
        for value, label in (
            ("all", "全部"),
            ("error", "只看錯誤"),
            ("warning", "只看警告"),
        ):
            self.ttk.Radiobutton(
                filters,
                text=label,
                variable=self.problem_filter_var,
                value=value,
                command=self._refresh_problem_tree,
            ).pack(side="left", padx=(0, 8))
        self.selected_only_var = self.tk.BooleanVar(value=False)
        self.ttk.Checkbutton(
            filters,
            text="只看選定構件",
            variable=self.selected_only_var,
            command=self._refresh_problem_tree,
        ).pack(side="left", padx=8)

        problem_container = self.ttk.Frame(self.all_problems_content)
        problem_container.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        problem_container.rowconfigure(0, weight=1)
        problem_container.columnconfigure(0, weight=1)
        columns = ("severity", "code", "component", "description")
        self.problem_tree = self.ttk.Treeview(
            problem_container,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=7,
        )
        headings = {
            "severity": "等級",
            "code": "類型",
            "component": "構件／來源",
            "description": "說明",
        }
        widths = {
            "severity": 85,
            "code": 250,
            "component": 180,
            "description": 520,
        }
        for column in columns:
            self.problem_tree.heading(column, text=headings[column])
            self.problem_tree.column(column, width=widths[column], anchor="w")
        self.problem_tree.tag_configure(
            "critical", background="#ffcdd2", foreground="#8e0000"
        )
        self.problem_tree.tag_configure(
            "error", background="#ffebee", foreground="#b71c1c"
        )
        self.problem_tree.tag_configure(
            "warning", background="#fff8e1", foreground="#8d6e00"
        )
        self.problem_tree.tag_configure(
            "info", background="#e3f2fd", foreground="#0d47a1"
        )
        self.problem_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = self.ttk.Scrollbar(
            problem_container,
            orient="vertical",
            command=self.problem_tree.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.problem_tree.configure(yscrollcommand=scrollbar.set)
        self.problem_tree.bind("<<TreeviewSelect>>", self._on_problem_selected)

        self.developer_button = self.ttk.Button(
            parent,
            text="▶ 開發者模式（原始資料 JSON）",
            command=self._toggle_developer_mode,
        )
        self.developer_button.pack(fill="x", pady=(3, 0))
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
        self.debug_text = scrolledtext.ScrolledText(
            self.developer_frame,
            wrap="none",
            height=12,
            font=("Consolas", 9),
        )
        self.debug_text.pack(fill="both", expand=True, padx=5, pady=5)

    def _toggle_all_problems(self) -> None:
        self.all_problems_expanded = not self.all_problems_expanded
        if self.all_problems_expanded:
            self.all_problems_content.pack(
                fill="both",
                expand=True,
                pady=(3, 0),
                before=self.developer_button,
            )
        else:
            self.all_problems_content.pack_forget()
        self._update_all_problems_header()

    def _update_all_problems_header(self) -> None:
        button = getattr(self, "all_problems_button", None)
        if button is None:
            return
        error_count = sum(
            record.severity in ERROR_SEVERITIES
            for record in getattr(self, "problem_records", ())
        )
        warning_count = sum(
            record.severity == "warning"
            for record in getattr(self, "problem_records", ())
        )
        icon = "▼" if getattr(self, "all_problems_expanded", False) else "▶"
        button.configure(
            text=(
                f"{icon} 全部問題清單（錯誤 {error_count}／"
                f"警告 {warning_count}）"
            )
        )


    def show(self) -> DXFImportDialogOutcome | None:
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
        self.review_workflow.reapply_coordinate_system(
            self.coordinate_mode_var.get()
        )
        self._sync_review_workflow_state()
        self._refresh_result_views()
        self.status_var.set("已恢復尚未完成的 DXF 檢核。")

    def _convert_preview(self) -> None:
        self._clear_waler_adjustment_preview()
        self.selection_state = SelectionState()
        self.selection_controller.state = self.selection_state
        self.preview_view_bounds = None
        self.preview_fit_all = True
        self.status_var.set("DXF 正在辨識，請稍候……")
        layer_button = getattr(
            self,
            "layer_settings_button",
            getattr(self, "recognize_button", None),
        )
        if layer_button is not None:
            layer_button.configure(state="disabled", text="圖層 …")
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

    def _perform_conversion(self) -> None:
        from tkinter import messagebox

        try:
            mutation = self.review_workflow.recognize(
                self._current_layer_roles()
            )
            self._sync_review_workflow_state()
            self._refresh_result_views()
            self._show_workflow_confirmation_invalidations(mutation)
        except Exception as exc:
            if isinstance(exc, DXFImportError):
                error_text = str(exc)
            else:
                error_text = f"辨識發生未預期錯誤：{type(exc).__name__}: {exc}"
            self._sync_review_workflow_state()
            self.status_var.set(error_text)
            self.apply_button.configure(state="disabled", text="不可匯入")
            messagebox.showerror("DXF 轉換失敗", error_text, parent=self.window)
        finally:
            try:
                self.window.configure(cursor="")
                layer_button = getattr(
                    self,
                    "layer_settings_button",
                    getattr(self, "recognize_button", None),
                )
                if layer_button is not None:
                    layer_button.configure(state="normal", text="圖層 ✓")
            except self.tk.TclError:
                pass

    def _reset_coordinate_settings(self) -> None:
        self._set_origin_from_world_point(None)

    def _set_origin_from_world_point(self, point: Point | None) -> None:
        mutation = self.review_workflow.set_coordinate_origin(point)
        self.coordinate_mode_var.set("local" if point is not None else "world")
        self._sync_review_workflow_state()
        self.coordinate_error_var.set("")
        self._refresh_result_views()
        self._show_workflow_confirmation_invalidations(mutation)

    def _set_origin_from_candidate(self, candidate: CandidatePoint) -> None:
        """Commit one explicit DXF-world candidate as the Local origin."""

        coordinate_system = coordinate_system_from_candidate(candidate)
        self._set_origin_from_world_point(
            (coordinate_system.origin_x, coordinate_system.origin_y)
        )

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
            self.review_workflow.reapply_coordinate_system("local")
            self._sync_review_workflow_state()
            self.coordinate_error_var.set("請先選取一個候選點作為局部原點。")
        else:
            point = self.selected_origin_world if mode == "local" else None
            self.review_workflow.set_coordinate_origin(point)
            self._sync_review_workflow_state()
            self.coordinate_error_var.set("")
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
        self._sync_review_workflow_state()
        if self.result is None:
            return
        previous_review_key = self.selected_review_item_key
        if self.selected_member_id and self._selected_member() is None:
            self.selection_state = SelectionState()
            self.selection_controller.state = self.selection_state
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
        self._refresh_problem_tree()
        self._refresh_member_tree()
        self._update_selected_member_panel(
            rebuild_candidates=rebuild_candidate_tree
        )
        if getattr(self, "double_support_settings_window", None) is not None:
            self.double_support_settings_candidates = (
                self._double_support_candidates_for_settings()
            )
            self._refresh_double_support_settings_tree()
            self._on_double_support_settings_selected()
        self._invalidate_debug_payload()
        self._update_coordinate_display()
        self._update_import_controls()
        self.render_scheduler.request(preview_dirty)

    def _invalidate_debug_payload(self) -> None:
        self._debug_payload_dirty = True
        if getattr(self, "developer_expanded", False):
            self._refresh_debug_payload()

    def _refresh_debug_payload(self) -> bool:
        """Render developer JSON for one stable committed workflow revision."""

        try:
            for _attempt in range(3):
                snapshot = self.review_workflow.snapshot
                revision = snapshot.revision
                if (
                    not getattr(self, "_debug_payload_dirty", True)
                    and getattr(self, "_debug_payload_revision", None) == revision
                ):
                    return True
                if snapshot.result is None:
                    payload: dict[str, Any] = {}
                else:
                    payload = snapshot.result.to_debug_dict()
                payload["review_revision"] = revision
                payload["manual_replay"] = {
                    "preserved": list(snapshot.last_manual_replay_report.preserved),
                    "needs_review": list(snapshot.last_manual_replay_report.needs_review),
                    "disabled": list(snapshot.last_manual_replay_report.disabled),
                }
                text = json.dumps(payload, ensure_ascii=False, indent=2)
                if self.review_workflow.revision != revision:
                    continue
                self.debug_text.delete("1.0", "end")
                self.debug_text.insert("1.0", text)
                self._debug_payload_text = text
                self._debug_payload_revision = revision
                self._debug_payload_dirty = False
                return True
        except Exception as exc:
            self._debug_payload_dirty = True
            status_var = getattr(self, "status_var", None)
            if status_var is not None:
                status_var.set(f"開發者資料更新失敗，可重新開啟重試：{exc}")
            return False
        self._debug_payload_dirty = True
        return False

    def _update_coordinate_display(self) -> None:
        if self.result is None:
            return
        coordinate = self.result.coordinate_system
        if self.coordinate_valid and coordinate.mode == "local":
            mode_text = "局部座標"
            origin_text = f"({coordinate.origin_x:.3f}, {coordinate.origin_y:.3f})"
        elif self.coordinate_valid:
            mode_text = "世界座標"
            origin_text = "(0.000, 0.000)"
        else:
            mode_text = "尚未套用（目前預覽世界座標）"
            origin_text = "—"
        self.coordinate_info_var.set(
            f"原始：世界座標　原點：{origin_text}　局部座標＝世界座標－原點"
        )
        self.preview_coordinate_var.set(
            f"座標系統｜原點 {origin_text}｜目前模式：{mode_text}"
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
            f"範例世界座標 ({sample_world[0]:.3f}, {sample_world[1]:.3f}) → "
            f"局部座標 ({sample_local[0]:.3f}, {sample_local[1]:.3f})"
        )


    def _open_double_support_settings(self) -> None:
        if self._focus_existing_settings_window(
            "double_support_settings_window"
        ):
            return
        window = self.tk.Toplevel(self.window)
        self.double_support_settings_window = window
        window.title("雙路支撐設定")
        window.geometry("880x440")
        window.minsize(720, 340)
        window.protocol(
            "WM_DELETE_WINDOW",
            lambda: self._close_settings_window(
                "double_support_settings_window"
            ),
        )
        self.double_support_settings_candidates = (
            self._double_support_candidates_for_settings()
        )
        self.double_support_settings_tree = self.ttk.Treeview(
            window,
            columns=(
                "first",
                "second",
                "spacing",
                "status",
                "warning",
                "accepted",
            ),
            show="headings",
            selectmode="browse",
            height=12,
        )
        for column, label, width in (
            ("first", "第一支撐", 130),
            ("second", "第二支撐", 130),
            ("spacing", "距離", 130),
            ("status", "狀態", 150),
            ("warning", "警告摘要", 260),
            ("accepted", "是否接受", 110),
        ):
            self.double_support_settings_tree.heading(column, text=label)
            self.double_support_settings_tree.column(
                column,
                width=width,
                anchor="center",
            )
        self.double_support_settings_tree.pack(
            fill="both", expand=True, padx=10, pady=(10, 6)
        )
        self.double_support_settings_tree.bind(
            "<Double-1>",
            lambda _event: self._toggle_double_support_settings_candidate(),
        )
        self.double_support_settings_tree.bind(
            "<<TreeviewSelect>>",
            self._on_double_support_settings_selected,
        )
        self._refresh_double_support_settings_tree()

        self.double_support_settings_detail_var = self.tk.StringVar(
            value="選取候選以查看狀態與端點圍令資訊。"
        )
        self.ttk.Label(
            window,
            textvariable=self.double_support_settings_detail_var,
            wraplength=640,
            justify="left",
        ).pack(fill="x", padx=10, pady=(0, 4))

        footer = self.ttk.Frame(window)
        footer.pack(fill="x", padx=10, pady=(4, 10))
        self.double_support_settings_toggle_button = self.ttk.Button(
            footer,
            text="切換接受／不接受",
            command=self._toggle_double_support_settings_candidate,
        )
        self.double_support_settings_toggle_button.pack(side="left")
        self.ttk.Button(
            footer,
            text="取消",
            command=lambda: self._close_settings_window(
                "double_support_settings_window"
            ),
        ).pack(side="right", padx=(6, 0))
        self.ttk.Button(
            footer,
            text="套用",
            command=self._apply_double_support_settings,
        ).pack(side="right")

    def _double_support_candidates_for_settings(self) -> tuple[Any, ...]:
        result = getattr(self, "result", None)
        return (
            tuple(
                candidate
                for candidate in result.double_support_candidates
                if candidate.qualification_status
                in {"eligible", "pending_waler"}
            )
            if result is not None
            else ()
        )

    @staticmethod
    def _double_support_status_text(candidate: Any) -> str:
        if candidate.qualification_status == "pending_waler":
            return "警告：圍令待確認"
        if candidate.qualification_status == "incompatible_waler":
            return "圍令不相容"
        return "可接受" if not candidate.ambiguous else "配對有歧義"

    @staticmethod
    def _double_support_detail_text(candidate: Any) -> str:
        lines = list(candidate.warnings)
        for issue in candidate.issues:
            terminal = issue.terminal_name or "配對"
            competitors = ", ".join(
                "/".join(identity)
                for identity in issue.competing_waler_source_handles
            ) or "無"
            lines.append(
                f"{issue.member_id} {terminal}：{issue.message}"
                f"（候選圍令：{competitors}；{issue.code}）"
            )
        return "\n".join(dict.fromkeys(lines)) or "此候選目前可依既有流程接受或拒絕。"

    def _refresh_double_support_settings_tree(self) -> None:
        tree = getattr(self, "double_support_settings_tree", None)
        if tree is None:
            return
        selected = tuple(tree.selection())
        tree.delete(*tree.get_children())
        for candidate in getattr(
            self,
            "double_support_settings_candidates",
            (),
        ):
            tree.insert(
                "",
                "end",
                iid=candidate.id,
                values=(
                    candidate.first_strut_id,
                    candidate.second_strut_id,
                    f"{candidate.centerline_spacing:.1f}",
                    self._double_support_status_text(candidate),
                    "；".join(candidate.warnings) or "—",
                    (
                        "接受" if candidate.accepted else "不接受"
                    )
                    if candidate.qualification_status == "eligible"
                    else "不可接受",
                ),
            )
        if selected and tree.exists(selected[0]):
            tree.selection_set(selected[0])

    def _toggle_double_support_settings_candidate(self) -> None:
        selection = self.double_support_settings_tree.selection()
        if not selection:
            return
        candidate_id = str(selection[0])
        candidates = self.double_support_settings_candidates
        candidate = next(
            (item for item in candidates if item.id == candidate_id),
            None,
        )
        if candidate is None or candidate.qualification_status != "eligible":
            return
        self.double_support_settings_candidates = (
            set_double_support_candidate_accepted(
                candidates,
                candidate_id,
                not candidate.accepted,
            )
        )
        self._refresh_double_support_settings_tree()

    def _on_double_support_settings_selected(self, _event: Any = None) -> None:
        tree = getattr(self, "double_support_settings_tree", None)
        selection = tree.selection() if tree is not None else ()
        candidate = next(
            (
                item
                for item in getattr(
                    self, "double_support_settings_candidates", ()
                )
                if selection and item.id == str(selection[0])
            ),
            None,
        )
        detail_var = getattr(self, "double_support_settings_detail_var", None)
        if detail_var is not None:
            detail_var.set(
                self._double_support_detail_text(candidate)
                if candidate is not None
                else "選取候選以查看狀態與端點圍令資訊。"
            )
        button = getattr(self, "double_support_settings_toggle_button", None)
        if button is not None:
            button.configure(
                state=(
                    "normal"
                    if candidate is not None
                    and candidate.qualification_status == "eligible"
                    else "disabled"
                )
            )

    def _apply_double_support_settings(self) -> None:
        self._commit_double_support_candidates(
            tuple(
                candidate
                for candidate in self.double_support_settings_candidates
                if candidate.qualification_status == "eligible"
            )
        )
        self._close_settings_window("double_support_settings_window")


    def _commit_double_support_candidates(
        self,
        updated: Sequence[Any],
    ) -> bool:
        """Commit all staged pair decisions with one association rebuild."""

        mutation = self.review_workflow.commit_double_support_candidates(
            updated
        )
        if not mutation.changed:
            return False
        self._sync_review_workflow_state()
        self._refresh_result_views(
            preview_dirty=RenderDirty.FULL_SCENE,
            rebuild_candidate_tree=False,
        )
        self._show_workflow_confirmation_invalidations(mutation)
        return True


    def _refresh_problem_tree(self) -> None:
        self._update_all_problems_header()
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
                values=(
                    record.severity.upper(),
                    record.display_type,
                    record.component,
                    record.description,
                ),
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
        """Apply the shared detail/global-problem preview-focus behavior."""

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

    def _normalized_import_mode(self) -> str:
        mode = str(self.mode_var.get() or "replace").strip().lower()
        return mode if mode in {"replace", "append"} else "replace"

    def _import_action_text(self, *, warning: bool = False) -> str:
        mode_label = "取代" if self._normalized_import_mode() == "replace" else "附加"
        action = "仍要完成匯入" if warning else "完成匯入"
        return f"{action}（{mode_label}）"

    def _on_import_mode_changed(self) -> None:
        """Refresh the global action label when the batch import mode changes."""

        self.review_workflow.set_import_mode(self._normalized_import_mode())
        self._sync_review_workflow_state()
        if self.result is not None:
            self._update_import_controls()

    def _update_import_controls(self) -> None:
        if self.result is None:
            return
        workflow_status = self.review_workflow.completion_status()
        if not self.coordinate_valid:
            self.apply_button.configure(state="disabled", text="不可匯入")
            self.status_var.set(
                f"✗ {self.coordinate_error_var.get() or '座標系統尚未套用'}；請完成座標系統設定。"
            )
            self._update_pending_action_gate()
            return
        error_count = workflow_status.blocking_error_count
        unconfirmed_count = workflow_status.unconfirmed_count
        warning_count = workflow_status.warning_count
        if error_count:
            self.apply_button.configure(state="disabled", text="不可匯入")
            self.status_var.set(
                f"✗ 發現 {error_count} 項阻擋錯誤，"
                "請先修正問題列表中的錯誤／嚴重錯誤。"
            )
        elif warning_count or unconfirmed_count:
            self.apply_button.configure(
                state="normal",
                text=self._import_action_text(warning=True),
            )
            reminders = []
            if warning_count:
                reminders.append(f"警告 {warning_count} 項")
            if unconfirmed_count:
                reminders.append(f"未人工確認構件 {unconfirmed_count} 個")
            self.status_var.set(
                "⚠ 目前仍有" + "、".join(reminders) + "；完成匯入前會再次確認。"
            )
        else:
            self.apply_button.configure(
                state="normal",
                text=self._import_action_text(),
            )
            self.status_var.set("✓ 圖層與工程模型檢核通過，可以匯入求解器。")
        self._update_pending_action_gate()

    def _toggle_developer_mode(self) -> None:
        self.developer_expanded = not self.developer_expanded
        if self.developer_expanded:
            self.developer_button.configure(text="▼ 開發者模式（原始資料 JSON）")
            self.developer_frame.pack(fill="both", padx=6, pady=(0, 6))
            self._refresh_debug_payload()
        else:
            self.developer_frame.pack_forget()
            self.developer_button.configure(text="▶ 開發者模式（原始資料 JSON）")

    def _all_members(
        self,
    ) -> tuple[Waler | Strut | Brace | AuxiliaryComponent, ...]:
        return self.review_workflow.all_members()

    def _selected_member(
        self,
    ) -> Waler | Strut | Brace | AuxiliaryComponent | None:
        return self._member_by_id(self.selected_member_id)

    def _review_item_for_member_id(self, member_id: str) -> ReviewItem | None:
        if not member_id:
            return None
        return self.review_workflow.review_item_for_member(member_id)

    def _selected_review_item(self) -> ReviewItem | None:
        item = getattr(self, "review_item_by_key", {}).get(
            getattr(self, "selected_review_item_key", "")
        )
        if item is not None:
            return item
        return self._review_item_for_member_id(self.selected_member_id)

    def _selected_column_repair_subject_id(self) -> str:
        """Return the selected formal Column id without evaluating eligibility."""

        item = self._selected_review_item()
        if (
            item is None
            or item.status != "recognized"
            or item.role != "column"
            or not item.member_id
        ):
            return ""
        world = self.review_workflow.world_result
        if world is None:
            return ""
        matches = [column for column in world.columns if column.id == item.member_id]
        return item.member_id if len(matches) == 1 else ""

    def _selected_waler_formalization_subject_id(self) -> str:
        """Return the uniquely selected repair-eligible Waler id."""

        item = self._selected_review_item()
        if item is None or item.role != "waler" or not item.member_id:
            return ""
        world = self.review_workflow.world_result
        if world is None:
            return ""
        matches = tuple(waler for waler in world.walers if waler.id == item.member_id)
        if len(matches) != 1:
            return ""
        target = matches[0]
        source_identity = normalize_source_handles(target.source_handles)
        if not source_identity or not is_waler_engineering_line_repair_eligible(target):
            return ""
        identity_matches = tuple(
            waler
            for waler in world.walers
            if normalize_source_handles(waler.source_handles) == source_identity
        )
        return target.id if len(identity_matches) == 1 else ""

    @staticmethod
    def _candidate_has_type(candidate: CandidatePoint, point_type: str) -> bool:
        return candidate.point_type == point_type or point_type in candidate.point_types

    @staticmethod
    def _waler_cad_pair_identity(
        pair: tuple[CandidatePoint, CandidatePoint] | None,
    ) -> tuple[tuple[str, float, float], tuple[str, float, float]] | None:
        if pair is None:
            return None
        start, end = pair
        return (
            (start.id, float(start.world_point[0]), float(start.world_point[1])),
            (end.id, float(end.world_point[0]), float(end.world_point[1])),
        )

    def _waler_cad_pair(
        self,
        member_id: str,
    ) -> tuple[CandidatePoint, CandidatePoint] | None:
        points = tuple(self.candidate_point_store.component_points(member_id))
        starts = tuple(
            point
            for point in points
            if "start" in point.valid_for
            and self._candidate_has_type(point, "cad_manual_start")
        )
        ends = tuple(
            point
            for point in points
            if "end" in point.valid_for
            and self._candidate_has_type(point, "cad_manual_end")
        )
        if len(starts) != 1 or len(ends) != 1:
            return None
        return starts[0], ends[0]

    def _build_waler_formalization_session(
        self,
        member_id: str,
    ) -> WalerFormalizationSession:
        world = self.review_workflow.world_result
        if world is None:
            raise DXFImportError("請先完成 DXF 辨識。")
        matches = tuple(waler for waler in world.walers if waler.id == member_id)
        if len(matches) != 1 or not is_waler_engineering_line_repair_eligible(matches[0]):
            raise DXFImportError("此圍令不可使用圍令正式化工具。")
        member = matches[0]
        points = tuple(self.candidate_point_store.component_points(member_id))
        start_options = tuple(point for point in points if "start" in point.valid_for)
        end_options = tuple(point for point in points if "end" in point.valid_for)
        start_ids = {point.id for point in start_options}
        end_ids = {point.id for point in end_options}
        if (
            member.selected_start_point_id not in start_ids
            or member.selected_end_point_id not in end_ids
        ):
            raise DXFImportError(
                "目前圍令起終點無法對應點位清單，請重新整理或修正 DXF Review 資料。"
            )
        cad_pair = self._waler_cad_pair(member_id)
        return WalerFormalizationSession(
            member_id=member_id,
            opened_revision=int(getattr(self.review_workflow, "revision", 0)),
            source_identity=normalize_source_handles(member.source_handles),
            start_options=start_options,
            end_options=end_options,
            selected_start_point_id=member.selected_start_point_id,
            selected_end_point_id=member.selected_end_point_id,
            cad_start_point_id=cad_pair[0].id if cad_pair else "",
            cad_end_point_id=cad_pair[1].id if cad_pair else "",
            cad_pair_identity=self._waler_cad_pair_identity(cad_pair),
        )

    @staticmethod
    def _waler_formalization_point_label(point: CandidatePoint) -> str:
        return (
            f"{point.id}｜{point.label}｜"
            f"WCS ({point.world_point[0]:.3f}, {point.world_point[1]:.3f})"
        )

    def _close_waler_formalization(self) -> None:
        window = getattr(self, "waler_formalization_window", None)
        self.waler_formalization_window = None
        self.waler_formalization_session = None
        self.waler_formalization_source_var = None
        self.waler_formalization_start_var = None
        self.waler_formalization_end_var = None
        self.waler_formalization_status_var = None
        self.waler_formalization_point_buttons = []
        if window is not None:
            try:
                window.destroy()
            except self.tk.TclError:
                pass

    def _update_waler_formalization_source_state(self) -> None:
        source_var = getattr(self, "waler_formalization_source_var", None)
        source = source_var.get() if source_var is not None else ""
        state = "normal" if source == WALER_FORMALIZATION_SOURCE_POINTS else "disabled"
        for button in getattr(self, "waler_formalization_point_buttons", ()):
            button.configure(state=state)

    def _open_waler_formalization(self) -> None:
        from tkinter import messagebox

        member_id = self._selected_waler_formalization_subject_id()
        if not member_id:
            messagebox.showwarning(
                "圍令正式化",
                "請先選取一支可修補的暫定圍令或人工正式圍令。",
                parent=self.window,
            )
            return
        try:
            session = self._build_waler_formalization_session(member_id)
        except DXFImportError as exc:
            messagebox.showwarning("圍令正式化", str(exc), parent=self.window)
            return

        self._close_waler_formalization()
        window = self.tk.Toplevel(self.window)
        self.waler_formalization_window = window
        self.waler_formalization_session = session
        window.title(f"圍令正式化 — {member_id}")
        window.transient(self.window)
        window.protocol("WM_DELETE_WINDOW", self._close_waler_formalization)
        frame = self.ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)

        self.ttk.Label(
            frame,
            text=f"{member_id}（本視窗只處理此圍令）",
            font=("Microsoft JhengHei", 10, "bold"),
        ).pack(anchor="w")
        self.ttk.Label(
            frame,
            text=WALER_CONTACT_FACE_ADOPTION_NOTICE,
            foreground="#c62828",
            wraplength=780,
            justify="left",
        ).pack(anchor="w", pady=(4, 8))

        self.waler_formalization_source_var = self.tk.StringVar(
            value=WALER_FORMALIZATION_SOURCE_POINTS
        )
        source_frame = self.ttk.LabelFrame(frame, text="線的來源")
        source_frame.pack(fill="x", pady=(0, 8))
        self.ttk.Radiobutton(
            source_frame,
            text="點位清單",
            variable=self.waler_formalization_source_var,
            value=WALER_FORMALIZATION_SOURCE_POINTS,
            command=self._update_waler_formalization_source_state,
        ).pack(side="left", padx=8, pady=5)
        self.ttk.Radiobutton(
            source_frame,
            text="已讀取的 CAD 線",
            variable=self.waler_formalization_source_var,
            value=WALER_FORMALIZATION_SOURCE_CAD,
            command=self._update_waler_formalization_source_state,
            state="normal" if session.cad_pair_identity is not None else "disabled",
        ).pack(side="left", padx=8, pady=5)
        if session.cad_pair_identity is None:
            self.ttk.Label(
                source_frame,
                text="目前沒有針對此圍令讀取的 CAD 線。",
                foreground="#616161",
            ).pack(side="left", padx=8)

        point_frame = self.ttk.Frame(frame)
        point_frame.pack(fill="both", expand=True)
        start_frame = self.ttk.LabelFrame(point_frame, text="起點")
        start_frame.pack(side="left", fill="both", expand=True, padx=(0, 4))
        end_frame = self.ttk.LabelFrame(point_frame, text="終點")
        end_frame.pack(side="left", fill="both", expand=True, padx=(4, 0))
        self.waler_formalization_start_var = self.tk.StringVar(
            value=session.selected_start_point_id
        )
        self.waler_formalization_end_var = self.tk.StringVar(
            value=session.selected_end_point_id
        )
        self.waler_formalization_point_buttons = []
        for option in session.start_options:
            button = self.ttk.Radiobutton(
                start_frame,
                text=self._waler_formalization_point_label(option),
                variable=self.waler_formalization_start_var,
                value=option.id,
            )
            button.pack(anchor="w", padx=6, pady=2)
            self.waler_formalization_point_buttons.append(button)
        for option in session.end_options:
            button = self.ttk.Radiobutton(
                end_frame,
                text=self._waler_formalization_point_label(option),
                variable=self.waler_formalization_end_var,
                value=option.id,
            )
            button.pack(anchor="w", padx=6, pady=2)
            self.waler_formalization_point_buttons.append(button)

        self.waler_formalization_status_var = self.tk.StringVar(value="")
        self.ttk.Label(
            frame,
            textvariable=self.waler_formalization_status_var,
            foreground="#c62828",
            wraplength=780,
            justify="left",
        ).pack(fill="x", pady=(8, 2))
        actions = self.ttk.Frame(frame)
        actions.pack(fill="x", pady=(6, 0))
        self.ttk.Button(
            actions,
            text="採用正式圍令",
            command=self._adopt_waler_formalization,
        ).pack(side="right", padx=(6, 0))
        self.ttk.Button(
            actions,
            text="取消",
            command=self._close_waler_formalization,
        ).pack(side="right")
        self._update_waler_formalization_source_state()

    def _adopt_waler_formalization(self) -> None:
        from tkinter import messagebox

        session = getattr(self, "waler_formalization_session", None)
        source_var = getattr(self, "waler_formalization_source_var", None)
        if session is None or source_var is None:
            return
        parent = getattr(self, "waler_formalization_window", None) or self.window
        world = self.review_workflow.world_result
        matches = tuple(
            waler for waler in getattr(world, "walers", ())
            if waler.id == session.member_id
        )
        if len(matches) != 1 or not is_waler_engineering_line_repair_eligible(matches[0]):
            message = "此圍令已變更或不再適用圍令正式化，請重新開啟工具。"
            self.waler_formalization_status_var.set(message)
            messagebox.showwarning("圍令正式化", message, parent=parent)
            return
        member = matches[0]
        current_identity = normalize_source_handles(member.source_handles)
        identity_matches = tuple(
            waler
            for waler in getattr(world, "walers", ())
            if normalize_source_handles(waler.source_handles) == current_identity
        )
        if (
            not current_identity
            or current_identity != session.source_identity
            or len(identity_matches) != 1
        ):
            message = "此圍令來源已變更或不再唯一，請重新開啟圍令正式化。"
            self.waler_formalization_status_var.set(message)
            messagebox.showwarning("圍令正式化", message, parent=parent)
            return
        source = source_var.get()
        selected_candidate_id = ""
        if source == WALER_FORMALIZATION_SOURCE_CAD:
            current_pair = self._waler_cad_pair(session.member_id)
            current_revision = int(getattr(self.review_workflow, "revision", 0))
            if (
                current_revision != session.opened_revision
                or session.cad_pair_identity is None
                or self._waler_cad_pair_identity(current_pair)
                != session.cad_pair_identity
            ):
                self.waler_formalization_status_var.set(WALER_CAD_UPDATED_MESSAGE)
                messagebox.showwarning(
                    "圍令正式化",
                    WALER_CAD_UPDATED_MESSAGE,
                    parent=parent,
                )
                return
            assert current_pair is not None
            start_point_id, end_point_id = current_pair[0].id, current_pair[1].id
            input_kind = WALER_FORMALIZATION_SOURCE_CAD
            source_label = "已讀取的 CAD 線"
        else:
            start_point_id = str(self.waler_formalization_start_var.get() or "")
            end_point_id = str(self.waler_formalization_end_var.get() or "")
            start = self.candidate_point_store.get(session.member_id, start_point_id)
            end = self.candidate_point_store.get(session.member_id, end_point_id)
            if (
                start is None
                or end is None
                or "start" not in start.valid_for
                or "end" not in end.valid_for
            ):
                message = "所選起終點已失效，請重新開啟圍令正式化。"
                self.waler_formalization_status_var.set(message)
                messagebox.showwarning("圍令正式化", message, parent=parent)
                return
            input_kind = WALER_FORMALIZATION_SOURCE_POINTS
            source_label = "點位清單"
            if (
                start_point_id == member.selected_start_point_id
                and end_point_id == member.selected_end_point_id
            ):
                selected_candidate_id = member.selected_candidate_id

        if not messagebox.askyesno(
            "採用正式圍令",
            f"{WALER_CONTACT_FACE_ADOPTION_NOTICE}\n\n"
            f"線的來源：{source_label}\n"
            "確定採用這條線嗎？",
            parent=parent,
        ):
            return
        try:
            plan = self.review_workflow.plan_waler_engineering_line_repair(
                session.member_id,
                start_point_id,
                end_point_id,
                input_kind,
                selected_candidate_id=selected_candidate_id,
            )
            mutation = self.review_workflow.commit_waler_engineering_line_repair(plan)
            self._sync_review_workflow_state()
        except DXFImportError as exc:
            self.waler_formalization_status_var.set(str(exc))
            messagebox.showerror("圍令正式化失敗", str(exc), parent=parent)
            return

        self._close_waler_formalization()
        self._refresh_result_views(
            preview_dirty=(
                RenderDirty.COMPONENT_LAYER
                | RenderDirty.COMPONENT_SELECTION
                | RenderDirty.CANDIDATE_LAYER
                | RenderDirty.CANDIDATE_SELECTION
                | RenderDirty.TEMP_LINE
                | RenderDirty.DETAIL_PANEL
                | RenderDirty.TREE_SELECTION
            ),
            rebuild_candidate_tree=True,
        )
        self.selection_controller.synchronize_formal_member()
        self._show_workflow_confirmation_invalidations(mutation)

    def _column_repair_problem_reason(self, plan: Any) -> str:
        source = normalize_source_handles(plan.column_source_handles)
        return next(
            (
                record.description
                for record in getattr(self, "problem_records", ())
                if record.code == "COLUMN_ASSOCIATION_REQUIRES_REVIEW"
                and normalize_source_handles(record.source_handles) == source
            ),
            "找不到既有失效原因，請重新整理 DXF Review。",
        )

    def _column_repair_detail_lines(self, plan: Any) -> tuple[str, ...]:
        status_label = {
            "unresolved": "待修",
            "repaired": "已修",
            "requires_review": "需重新檢查",
        }.get(plan.status, plan.status)
        lines = [f"{plan.column_id}｜{status_label}"]
        world = self.review_workflow.world_result
        column = next(
            (item for item in world.columns if item.id == plan.column_id),
            None,
        ) if world else None
        if column is not None:
            center = column.world_reference_point or _midpoint(
                column.world_start or column.start,
                column.world_end or column.end,
            )
            lines.append(f"柱中心 WCS：({center[0]:.1f}, {center[1]:.1f}) mm")
        for distance_mm, strut_id, station, projection in plan.options:
            lines.append(
                f"{strut_id}：距離 {distance_mm:.1f} mm；station {station:.1f} mm；"
                f"投影 WCS ({projection[0]:.1f}, {projection[1]:.1f})"
            )
        if plan.status == "repaired":
            lines.append("目前人工決策：" + "、".join(plan.selected_strut_ids))
        elif plan.status == "requires_review":
            lines.append("失效原因：" + self._column_repair_problem_reason(plan))
        return tuple(lines)

    def _clear_column_repair_overlay(self) -> None:
        canvas = getattr(self, "canvas", None)
        for item_id in getattr(self, "_column_repair_overlay_items", ()):
            if canvas is not None:
                try:
                    canvas.delete(item_id)
                except self.tk.TclError:
                    pass
        self._column_repair_overlay_items = []

    @staticmethod
    def _column_repair_selected_ids(plan: Any, choice: str) -> tuple[str, ...]:
        if plan is None:
            return ()
        return {
            "first": plan.candidate_strut_ids[:1],
            "second": plan.candidate_strut_ids[1:],
            "both": plan.candidate_strut_ids,
        }.get(choice, ())

    def _draw_column_repair_overlay(self, plan: Any, selected: Sequence[str]) -> None:
        self._clear_column_repair_overlay()
        if self.preview_renderer is None or self.preview_transform is None or self.result is None:
            return
        world = self.review_workflow.world_result
        if world is None:
            return
        column = next((item for item in world.columns if item.id == plan.column_id), None)
        if column is None:
            return
        center = column.world_reference_point or _midpoint(
            column.world_start or column.start, column.world_end or column.end,
        )
        transform = self.result.coordinate_system.transform
        self._column_repair_overlay_items = []
        for _distance_mm, strut_id, _station, projection in plan.options:
            start = self._project_preview_point(transform(center))
            end = self._project_preview_point(transform(projection))
            item_id = self.preview_renderer.create_line(
                "temporary_overlay", *start, *end,
                fill="#0d47a1" if strut_id in selected else "#9e9e9e",
                width=4 if strut_id in selected else 2,
                dash=() if strut_id in selected else (4, 3),
            )
            self._column_repair_overlay_items.append(item_id)

    def _close_column_association_repair(self) -> None:
        self._clear_column_repair_overlay()
        window = getattr(self, "column_repair_window", None)
        self.column_repair_window = None
        self.column_repair_plan = None
        self.column_repair_details_var = None
        if window is not None:
            try:
                window.destroy()
            except self.tk.TclError:
                pass

    def _open_column_association_repair(self) -> None:
        from tkinter import messagebox

        column_id = self._selected_column_repair_subject_id()
        if not column_id:
            messagebox.showwarning(
                "中間柱關聯修補",
                "請先選取一支目前有效的正式中間柱。",
                parent=self.window,
            )
            return
        try:
            plan = self.review_workflow.plan_column_association_repair(column_id)
        except DXFImportError as exc:
            messagebox.showinfo(
                "中間柱關聯修補",
                str(exc),
                parent=self.window,
            )
            return
        self._close_column_association_repair()
        window = self.tk.Toplevel(self.window)
        self.column_repair_window = window
        self.column_repair_plan = plan
        window.title("中間柱關聯修補")
        window.transient(self.window)
        window.protocol("WM_DELETE_WINDOW", self._close_column_association_repair)
        frame = self.ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        status_label = {
            "unresolved": "待修",
            "repaired": "已修",
            "requires_review": "需重新檢查",
        }.get(plan.status, plan.status)
        self.ttk.Label(
            frame,
            text=f"{plan.column_id}｜{status_label}（本視窗只處理此中間柱）",
        ).pack(anchor="w")
        lines = self._column_repair_detail_lines(plan)
        self.column_repair_details_var = self.tk.StringVar(value="\n".join(lines))
        self.ttk.Label(
            frame,
            textvariable=self.column_repair_details_var,
            justify="left",
        ).pack(anchor="w")
        selected = tuple(plan.selected_strut_ids)
        initial_choice = {
            tuple(plan.candidate_strut_ids[:1]): "first",
            tuple(plan.candidate_strut_ids[1:]): "second",
            tuple(plan.candidate_strut_ids): "both",
        }.get(selected, "")
        choice = self.tk.StringVar(value=initial_choice)
        options_frame = self.ttk.Frame(frame)
        options_frame.pack(fill="x", pady=8)
        buttons = []
        for label, value in (("第一支", "first"), ("第二支", "second"), ("兩支", "both")):
            button = self.ttk.Radiobutton(options_frame, text=label, variable=choice, value=value)
            button.pack(side="left", padx=(0, 12))
            buttons.append(button)

        def selected_ids() -> tuple[str, ...]:
            return self._column_repair_selected_ids(self.column_repair_plan, choice.get())

        def update_overlay(*_args: Any) -> None:
            current_plan = self.column_repair_plan
            if current_plan is not None:
                overlay_ids = (
                    current_plan.selected_strut_ids
                    if current_plan.status == "requires_review"
                    else selected_ids()
                )
                self._draw_column_repair_overlay(current_plan, overlay_ids)

        choice.trace_add("write", update_overlay)
        if plan.status == "requires_review":
            for button in buttons:
                button.configure(state="disabled")
        update_overlay()
        actions = self.ttk.Frame(frame)
        actions.pack(fill="x")

        def apply_choice() -> None:
            plan = self.column_repair_plan
            if plan is None or not selected_ids():
                messagebox.showwarning("中間柱關聯修補", "請選擇第一支、第二支或兩支。", parent=window)
                return
            try:
                mutation = self.review_workflow.commit_column_association_repair(plan, selected_ids())
            except DXFImportError as exc:
                messagebox.showwarning("中間柱關聯需重新預覽", str(exc), parent=window)
                return
            self._close_column_association_repair()
            self._refresh_result_views(preview_dirty=RenderDirty.FULL_SCENE)
            self._show_workflow_confirmation_invalidations(mutation)

        def withdraw_choice() -> None:
            plan = self.column_repair_plan
            if plan is None or plan.status == "unresolved":
                return
            try:
                mutation = self.review_workflow.withdraw_column_association_repair(plan)
            except DXFImportError as exc:
                messagebox.showwarning("中間柱關聯需重新預覽", str(exc), parent=window)
                return
            self._close_column_association_repair()
            self._refresh_result_views(preview_dirty=RenderDirty.FULL_SCENE)
            self._show_workflow_confirmation_invalidations(mutation)

        apply_button = self.ttk.Button(actions, text="套用", command=apply_choice)
        apply_button.pack(side="left")
        if plan.status == "requires_review":
            apply_button.configure(state="disabled")
        withdraw_button = self.ttk.Button(actions, text="撤銷", command=withdraw_choice)
        withdraw_button.pack(side="left", padx=8)
        if plan.status == "unresolved":
            withdraw_button.configure(state="disabled")
        self.ttk.Button(actions, text="取消", command=self._close_column_association_repair).pack(side="right")

    def _open_corner_brace_repair_preview(self) -> None:
        """Plan first; only hard-eligible candidates enter the modal preview."""

        from tkinter import messagebox

        item = self._selected_review_item()
        reason = self.corner_brace_repair_disabled_reason(item)
        if reason:
            messagebox.showwarning("修補角撐", reason, parent=self.window)
            return
        assert item is not None
        try:
            plan = self.review_workflow.plan_corner_brace_repair(item.key)
        except DXFImportError as exc:
            messagebox.showwarning("修補角撐", str(exc), parent=self.window)
            return
        self.corner_brace_repair_plan = plan
        self.corner_brace_repair_candidate_id = ""
        self._clear_corner_brace_repair_overlay()
        if not plan.candidates:
            details = "\n".join(plan.diagnostics) or "沒有候選通過全部安全條件。"
            messagebox.showwarning(
                "無可套用的角撐修補候選",
                details,
                parent=self.window,
            )
            return
        self._show_corner_brace_repair_window(plan)

    def _show_corner_brace_repair_window(
        self,
        plan: CornerBraceRepairPlan,
    ) -> None:
        existing = self.corner_brace_repair_window
        if existing is not None:
            try:
                existing.destroy()
            except self.tk.TclError:
                pass
        window = self.tk.Toplevel(self.window)
        self.corner_brace_repair_window = window
        window.title("角撐修補預覽")
        window.transient(self.window)
        window.protocol("WM_DELETE_WINDOW", self._cancel_corner_brace_repair)
        body = self.ttk.Frame(window, padding=10)
        body.pack(fill="both", expand=True)
        self.ttk.Label(
            body,
            text="下列候選均已通過目標證據、模板移植與有限構件檢查；仍需明確套用。",
            wraplength=720,
            justify="left",
        ).pack(fill="x", pady=(0, 6))
        self.corner_brace_repair_tree = None
        if len(plan.candidates) > 1:
            tree = self.ttk.Treeview(
                body,
                columns=(
                    "relationship",
                    "template",
                    "mode",
                    "offset",
                    "station",
                    "length",
                    "reference_length",
                    "primary",
                    "secondary",
                ),
                show="headings",
                height=min(max(len(plan.candidates), 2), 8),
                selectmode="browse",
            )
            self.corner_brace_repair_tree = tree
            for column, label, width in (
                ("relationship", "目標圍令／支撐", 190),
                ("template", "選用模板", 120),
                ("mode", "移植方式", 95),
                ("offset", "圍令端定位距離", 135),
                ("station", "支撐端定位距離", 135),
                ("length", "結果長度", 115),
                ("reference_length", "參考固定長度", 125),
                ("primary", "自動辨識主要依據", 155),
                ("secondary", "人工修補次要依據", 155),
            ):
                tree.heading(column, text=label)
                tree.column(column, width=width, anchor="center")
            for candidate in plan.candidates:
                tree.insert(
                    "",
                    "end",
                    iid=candidate.id,
                    values=(
                        f"{candidate.target_waler_id} / {candidate.target_strut_id}",
                        (
                            candidate.template_reference.member_id
                            if candidate.template_reference is not None
                            else "本體關係選擇"
                        ),
                        corner_brace_transfer_mode_label(candidate.transfer_mode),
                        self._format_corner_brace_repair_length(
                            candidate.reference_waler_offset_mm
                        ),
                        self._format_corner_brace_repair_length(
                            candidate.reference_strut_station_mm
                        ),
                        self._format_corner_brace_repair_length(
                            candidate.fixed_length_mm
                        ),
                        self._format_corner_brace_repair_length(
                            candidate.reference_fixed_length_mm
                        ),
                        ", ".join(
                            ref.member_id for ref in candidate.primary_references
                        ),
                        ", ".join(
                            ref.member_id for ref in candidate.secondary_references
                        )
                        or "—",
                    ),
                )
            tree.pack(fill="both", expand=True, pady=(0, 6))
            tree.bind(
                "<<TreeviewSelect>>",
                self._on_corner_brace_repair_candidate_selected,
            )

        summary = self.ttk.LabelFrame(body, text="建議修補方案")
        summary.pack(fill="x", pady=(0, 6))
        self.corner_brace_repair_summary_var = self.tk.StringVar(
            value="請選擇候選以預覽建議修補方案。"
        )
        self.ttk.Label(
            summary,
            textvariable=self.corner_brace_repair_summary_var,
            wraplength=720,
            justify="left",
        ).pack(fill="x", padx=8, pady=(6, 3))
        self.ttk.Label(
            summary,
            text=(
                "量測基準：目標圍令與支撐的交會點；"
                "支撐端定位距離沿支撐內側方向量測。"
            ),
            wraplength=720,
            justify="left",
            foreground="#455a64",
        ).pack(fill="x", padx=8, pady=(0, 6))

        audit_host = self.ttk.Frame(body)
        audit_host.pack(fill="x", pady=(0, 6))
        audit_header = self.ttk.Frame(audit_host)
        audit_header.pack(fill="x")
        self.corner_brace_repair_audit_expanded = False
        self.corner_brace_repair_audit_button = self.ttk.Button(
            audit_header,
            text="顯示稽核與診斷",
            command=self._toggle_corner_brace_repair_audit,
        )
        self.corner_brace_repair_audit_button.pack(side="left")
        self.corner_brace_repair_diagnostic_hint_var = self.tk.StringVar(value="")
        self.ttk.Label(
            audit_header,
            textvariable=self.corner_brace_repair_diagnostic_hint_var,
            foreground="#795548",
        ).pack(side="left", padx=(8, 0))
        self.corner_brace_repair_audit_frame = self.ttk.LabelFrame(
            audit_host,
            text="稽核與診斷",
        )
        self.corner_brace_repair_audit_var = self.tk.StringVar(
            value=self._corner_brace_repair_audit_text(None)
        )
        self.ttk.Label(
            self.corner_brace_repair_audit_frame,
            textvariable=self.corner_brace_repair_audit_var,
            wraplength=720,
            justify="left",
        ).pack(fill="x", padx=8, pady=6)
        actions = self.ttk.Frame(body)
        actions.pack(fill="x")
        self.corner_brace_repair_apply_button = self.ttk.Button(
            actions,
            text="套用此修補",
            command=self._apply_corner_brace_repair,
            state="disabled",
        )
        self.corner_brace_repair_apply_button.pack(side="right", padx=(6, 0))
        self.ttk.Button(
            actions,
            text="取消",
            command=self._cancel_corner_brace_repair,
        ).pack(side="right")
        if len(plan.candidates) == 1:
            self.corner_brace_repair_candidate_id = plan.candidates[0].id
            self._on_corner_brace_repair_candidate_selected()

    @staticmethod
    def _format_corner_brace_repair_scalar(value: float) -> str:
        return f"{value:.3f}"

    @classmethod
    def _format_corner_brace_repair_length(cls, value: float) -> str:
        return f"{cls._format_corner_brace_repair_scalar(value)} mm"

    @classmethod
    def _format_corner_brace_repair_point(cls, point: Point) -> str:
        return (
            f"({cls._format_corner_brace_repair_scalar(point[0])}, "
            f"{cls._format_corner_brace_repair_scalar(point[1])})"
        )

    @classmethod
    def _format_corner_brace_repair_line(
        cls,
        start: Point,
        end: Point,
    ) -> str:
        return (
            f"{cls._format_corner_brace_repair_point(start)} → "
            f"{cls._format_corner_brace_repair_point(end)}"
        )

    def _corner_brace_repair_summary_text(
        self,
        candidate: CornerBraceRepairCandidate | None,
    ) -> str:
        if candidate is None:
            return "請選擇候選以預覽建議修補方案。"
        if (
            getattr(candidate, "selection_mode", "reference_template")
            == "body_relationship_selection"
            and getattr(candidate, "relationship_assessment", None) is not None
        ):
            assessment = candidate.relationship_assessment
            return (
                "本體已辨識，工程關係有歧義；請明確選擇。\n"
                f"目標圍令／支撐：{candidate.target_waler_id} / "
                f"{candidate.target_strut_id}\n"
                "有限端點："
                f"{self._format_corner_brace_repair_line(candidate.world_start, candidate.world_end)}\n"
                "結果長度："
                f"{self._format_corner_brace_repair_length(candidate.fixed_length_mm)}；"
                f"分類：{assessment.classification}\n"
                "兩軌覆蓋率："
                f"{assessment.per_rail_union_coverage[0]:.1%} / "
                f"{assessment.per_rail_union_coverage[1]:.1%}\n"
                "Waler／Strut 端延伸："
                f"{assessment.per_end_extensions_mm[0]:.3f} / "
                f"{assessment.per_end_extensions_mm[1]:.3f} mm；"
                f"驗證：{'通過' if assessment.hard_valid else '未通過'}"
            )
        transfer_mode = corner_brace_transfer_mode_label(candidate.transfer_mode)
        return (
            f"目標圍令／支撐：{candidate.target_waler_id} / "
            f"{candidate.target_strut_id}\n"
            "選用模板："
            f"{candidate.template_reference.member_id if candidate.template_reference is not None else '不適用（本體關係選擇）'}；"
            f"移植方式：{transfer_mode}\n"
            f"結果長度：{self._format_corner_brace_repair_length(candidate.fixed_length_mm)}\n"
            "圍令端定位距離："
            f"{self._format_corner_brace_repair_length(candidate.reference_waler_offset_mm)}；"
            "支撐端定位距離："
            f"{self._format_corner_brace_repair_length(candidate.reference_strut_station_mm)}\n"
            "目標方向：有效；定位錨點：有效"
        )

    def _corner_brace_repair_audit_text(
        self,
        candidate: CornerBraceRepairCandidate | None,
    ) -> str:
        plan = self.corner_brace_repair_plan
        if candidate is None:
            plan_diagnostics = tuple(plan.diagnostics) if plan is not None else ()
            return "\n".join(plan_diagnostics) or "選取候選後顯示完整稽核資料。"
        primary = ", ".join(
            ref.member_id for ref in candidate.primary_references
        ) or "—"
        secondary = ", ".join(
            ref.member_id for ref in candidate.secondary_references
        ) or "—"
        diagnostics = tuple(candidate.diagnostics)
        if plan is not None:
            diagnostics += tuple(plan.diagnostics)
        diagnostic_text = "\n".join(diagnostics) or "無"
        relationship_text = ""
        if getattr(candidate, "relationship_assessment", None) is not None:
            assessment = candidate.relationship_assessment
            relationship_text = (
                f"Body signature：{candidate.body_signature}\n"
                f"Internal gaps：{len(assessment.internal_gaps)}；"
                f"Terminal gaps：{len(assessment.terminal_gaps)}；"
                "逐 gap evidence："
                f"{sum(bool(item.occluder_lines) for item in assessment.gap_occluder_assignments)}"
                f"/{len(assessment.gap_occluder_assignments)}\n"
            )
        return (
            relationship_text
            + "參考固定長度："
            f"{self._format_corner_brace_repair_length(candidate.reference_fixed_length_mm)}\n"
            "工程線："
            f"{self._format_corner_brace_repair_line(candidate.world_start, candidate.world_end)}\n"
            "定位錨點："
            f"{self._format_corner_brace_repair_point(candidate.positional_anchor)}\n"
            f"自動辨識主要依據：{primary}\n"
            f"人工修補次要依據：{secondary}\n"
            f"診斷：{diagnostic_text}"
        )

    def _toggle_corner_brace_repair_audit(self) -> None:
        self.corner_brace_repair_audit_expanded = not getattr(
            self,
            "corner_brace_repair_audit_expanded",
            False,
        )
        frame = getattr(self, "corner_brace_repair_audit_frame", None)
        button = getattr(self, "corner_brace_repair_audit_button", None)
        if self.corner_brace_repair_audit_expanded:
            if frame is not None:
                frame.pack(fill="x", pady=(3, 0))
            if button is not None:
                button.configure(text="隱藏稽核與診斷")
        else:
            if frame is not None:
                frame.pack_forget()
            if button is not None:
                button.configure(text="顯示稽核與診斷")

    def _selected_corner_brace_repair_candidate(
        self,
    ) -> CornerBraceRepairCandidate | None:
        plan = self.corner_brace_repair_plan
        if plan is None or not self.corner_brace_repair_candidate_id:
            return None
        return next(
            (
                candidate
                for candidate in plan.candidates
                if candidate.id == self.corner_brace_repair_candidate_id
            ),
            None,
        )

    def _on_corner_brace_repair_candidate_selected(self, _event: Any = None) -> None:
        tree = getattr(self, "corner_brace_repair_tree", None)
        if tree is not None:
            selection = tree.selection()
            self.corner_brace_repair_candidate_id = (
                str(selection[0]) if selection else ""
            )
        candidate = self._selected_corner_brace_repair_candidate()
        button = getattr(self, "corner_brace_repair_apply_button", None)
        if button is not None:
            button.configure(state="normal" if candidate is not None else "disabled")
        summary_var = getattr(self, "corner_brace_repair_summary_var", None)
        if summary_var is not None:
            summary_var.set(self._corner_brace_repair_summary_text(candidate))
        audit_var = getattr(self, "corner_brace_repair_audit_var", None)
        if audit_var is not None:
            audit_var.set(self._corner_brace_repair_audit_text(candidate))
        plan = self.corner_brace_repair_plan
        has_diagnostics = bool(
            (candidate is not None and candidate.diagnostics)
            or (plan is not None and plan.diagnostics)
        )
        hint_var = getattr(self, "corner_brace_repair_diagnostic_hint_var", None)
        if hint_var is not None:
            hint_var.set("有診斷資料" if has_diagnostics else "")
        if candidate is None:
            self._clear_corner_brace_repair_overlay()
            return
        self._draw_corner_brace_repair_overlay(candidate)

    def _apply_corner_brace_repair(self) -> None:
        from tkinter import messagebox

        plan = self.corner_brace_repair_plan
        candidate = self._selected_corner_brace_repair_candidate()
        if plan is None or candidate is None:
            return
        try:
            mutation = self.review_workflow.commit_corner_brace_repair(
                plan,
                candidate.id,
                explicit_adoption=True,
            )
        except DXFImportError as exc:
            messagebox.showwarning(
                "角撐修補需重新預覽",
                str(exc),
                parent=self.corner_brace_repair_window or self.window,
            )
            return
        self._cancel_corner_brace_repair()
        self._sync_review_workflow_state()
        self._refresh_result_views(preview_dirty=RenderDirty.FULL_SCENE)
        self._show_workflow_confirmation_invalidations(mutation)

    def _cancel_corner_brace_repair(self) -> None:
        self._clear_corner_brace_repair_overlay()
        self.corner_brace_repair_plan = None
        self.corner_brace_repair_candidate_id = ""
        self.corner_brace_repair_tree = None
        self.corner_brace_repair_audit_expanded = False
        window = self.corner_brace_repair_window
        self.corner_brace_repair_window = None
        if window is not None:
            try:
                window.destroy()
            except self.tk.TclError:
                pass

    def _is_review_item_confirmed(self, item: ReviewItem | None) -> bool:
        return self.review_workflow.is_review_item_confirmed(item)

    def _unconfirmed_formal_review_items(self) -> tuple[ReviewItem, ...]:
        return self.review_workflow.unconfirmed_formal_review_items()

    def _confirmed_item_snapshot(self) -> dict[str, str]:
        return self.review_workflow.confirmed_snapshot()

    def _confirm_selected_review_item(self) -> None:
        item = self._selected_review_item()
        if self.result is None or item is None or not review_item_can_be_confirmed(item):
            return
        try:
            if not self.review_workflow.confirm(item):
                return
        except ValueError:
            return
        self._sync_review_workflow_state()
        self._refresh_member_tree()
        self._update_recognition_data_panel(item, self._selected_member())
        self._update_review_confirmation_action_state(item)

    def _source_exclusion_disabled_reason(self, item: ReviewItem | None) -> str:
        return self.review_workflow.source_exclusion_disabled_reason(item)

    def _stage_review_item_for_identity(
        self,
        stage: SourceExclusionPlan,
        identity: str,
        *,
        excluded: bool,
    ) -> ReviewItem | None:
        return self.review_workflow.review_item_for_identity(
            stage.review_items,
            identity,
            excluded=excluded,
        )

    def _format_source_exclusion_impact(
        self,
        item: ReviewItem,
        stage: SourceExclusionPlan,
        *,
        restoring: bool,
    ) -> str:
        assert self.result is not None
        staged_result = stage.result
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
        replay = stage.manual_replay
        verb = "復原" if restoring else "排除"
        lines = [
            f"將{verb}：{item.display_id}",
            "來源 Handle：" + ", ".join(normalize_source_handles(item.source_handles)),
            "",
            "此操作不會修改或刪除原始 DXF entity。",
            "",
            "重新計算後：",
            f"• 正式構件 {before_members} → {after_members}（{after_members - before_members:+d}）",
            f"• 警告變化：{warning_delta:+d}",
            f"• 錯誤／嚴重錯誤變化：{error_delta:+d}",
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

    @staticmethod
    def _format_pending_source_exclusion_impact(
        before_result: DXFImportResult,
        before_confirmations: Mapping[str, str],
        pending_sources: Sequence[ExcludedSource],
        stage: SourceExclusionPlan,
    ) -> str:
        """Format one aggregate impact from the final canonical plan only."""

        before_members = sum(result_member_counts(before_result).values())
        after_members = sum(result_member_counts(stage.result).values())
        before_severity = result_severity_counts(before_result)
        after_severity = result_severity_counts(stage.result)
        warning_delta = after_severity.get("warning", 0) - before_severity.get(
            "warning", 0
        )
        error_delta = (
            after_severity.get("error", 0)
            + after_severity.get("critical", 0)
            - before_severity.get("error", 0)
            - before_severity.get("critical", 0)
        )
        invalidated_confirmations = tuple(
            identity
            for identity in before_confirmations
            if identity not in stage.review_confirmations
        )
        replay = stage.manual_replay
        lines = [
            "以下為所有待排除來源合併後的結果",
            "",
            "待排除來源：",
        ]
        lines.extend(
            "• "
            + (source.display_id_when_excluded or source.identity)
            + f"（{source.role} / Handle {', '.join(source.source_handles)}）"
            for source in pending_sources
        )
        lines.extend(
            (
                "",
                "重新計算後：",
                f"• 正式構件 {before_members} → {after_members}（{after_members - before_members:+d}）",
                f"• 警告變化：{warning_delta:+d}",
                f"• 錯誤／嚴重錯誤變化：{error_delta:+d}",
                f"• 人工輸入成功保留：{len(replay.preserved)}",
                f"• 人工輸入需要重新確認：{len(replay.needs_review)}",
                f"• 因來源仍被排除而停用：{len(replay.disabled)}",
                f"• 失效確認：{len(invalidated_confirmations)}",
                "",
                "若結果不如預期，可取消個別待排除後重新套用",
            )
        )
        return "\n".join(lines)

    def _commit_source_exclusion_stage(
        self,
        stage: SourceExclusionPlan,
        selected_key: str,
        *,
        initiating_member_ids: Sequence[str] = (),
    ) -> ReviewMutation:
        self._clear_waler_adjustment_preview()
        mutation = self.review_workflow.commit_source_exclusion_plan(
            stage,
            initiating_member_ids=initiating_member_ids,
        )
        self._sync_review_workflow_state()
        self.selected_review_item_key = selected_key
        self.selection_state = SelectionState(selection_source="component_tree")
        self.selection_controller.state = self.selection_state
        self.preview_fit_all = False
        self._refresh_result_views(
            preview_dirty=self._source_exclusion_render_dirty(mutation.effects),
        )
        self._show_workflow_confirmation_invalidations(mutation)
        return mutation

    @staticmethod
    def _dialog_source_geometry_signature(
        result: DXFImportResult | None,
    ) -> tuple[Any, ...] | None:
        if result is None:
            return None
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

    def _source_exclusion_render_dirty(
        self,
        effects: ReviewMutationEffects | None,
    ) -> RenderDirty:
        """Map application effects to a safe preview-layer refresh."""

        if effects is None or self.result is None:
            return RenderDirty.FULL_SCENE
        current_revision = self.review_workflow.revision
        current_signature = self._dialog_source_geometry_signature(self.result)
        if (
            effects.committed_revision != current_revision
            or effects.source_geometry_changed
            or effects.source_bounds_changed
            or getattr(self, "preview_renderer", None) is None
            or getattr(self, "preview_transform", None) is None
            or getattr(self, "_preview_scene_revision", -1)
            != effects.committed_revision - 1
            or getattr(self, "_preview_source_geometry_signature", None)
            != current_signature
        ):
            return RenderDirty.FULL_SCENE

        changed_handles = set(effects.changed_source_handles)
        indexed_handles = set(self.preview_scene.source_handle_items)
        visible_changed_handles = {
            geometry.source_handle
            for geometry in self._preview_source_geometry(self.result)
            if geometry.source_handle in changed_handles
            and self._preview_intersects(
                tuple(
                    self.result.coordinate_system.transform(point)
                    for point in geometry.points
                )
            )
        }
        if visible_changed_handles - indexed_handles:
            return RenderDirty.FULL_SCENE

        self._pending_source_style_handles.update(changed_handles)
        dirty = RenderDirty.SOURCE_STYLE
        if effects.engineering_members_changed or effects.problems_changed:
            dirty |= RenderDirty.COMPONENT_LAYER
        if effects.candidate_points_changed:
            dirty |= RenderDirty.CANDIDATE_LAYER
        if effects.selection_targets_invalidated:
            dirty |= (
                RenderDirty.COMPONENT_SELECTION
                | RenderDirty.CANDIDATE_SELECTION
                | RenderDirty.TREE_SELECTION
                | RenderDirty.DETAIL_PANEL
            )
        return dirty

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
        old_handles = set(self._pending_source_handles())
        try:
            if item.status == "excluded":
                stage, restoring, identity = (
                    self.review_workflow.plan_source_exclusion_for_item(item)
                )
                if not messagebox.askyesno(
                    "確認復原 DXF 來源",
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
                    excluded=False,
                )
                self._commit_source_exclusion_stage(
                    stage,
                    selected.key if selected is not None else "",
                    initiating_member_ids=(
                        (item.member_id,) if item.member_id else ()
                    ),
                )
                self.source_exclusion_status_var.set(
                    f"已復原 {item.display_id}；工程關聯與檢核結果已重新計算。"
                )
                return
            if self.review_workflow.pending_source_exclusion_contains(item):
                self.review_workflow.unmark_source_exclusion(item)
                action = "已取消待排除"
            else:
                self.review_workflow.mark_source_exclusion(item)
                action = "已標記待排除"
        except Exception as exc:
            error_text = (
                str(exc)
                if isinstance(exc, DXFImportError)
                else f"{type(exc).__name__}: {exc}"
            )
            messagebox.showerror(
                "DXF 來源排除失敗",
                f"目前辨識結果完全未變更。\n\n{error_text}",
                parent=self.window,
            )
            return
        self._sync_review_workflow_state()
        self._refresh_pending_source_visuals(old_handles)
        self._update_selected_member_panel(rebuild_candidates=False)
        self.source_exclusion_status_var.set(f"{action}：{item.display_id}")

    def _pending_source_handles(self) -> tuple[str, ...]:
        draft = getattr(
            getattr(self, "review_workflow", None),
            "pending_source_exclusion_draft",
            None,
        )
        sources = getattr(draft, "sources", ())
        if not isinstance(sources, (tuple, list)):
            sources = ()
        return tuple(
            sorted(
                {
                    handle
                    for source in sources
                    for handle in source.source_handles
                }
            )
        )

    def _refresh_pending_source_visuals(
        self,
        previous_handles: Sequence[str] = (),
    ) -> None:
        handles = set(previous_handles) | set(self._pending_source_handles())
        if not handles:
            return
        self._pending_source_style_handles.update(handles)
        scheduler = getattr(self, "render_scheduler", None)
        if scheduler is not None:
            scheduler.request(RenderDirty.SOURCE_STYLE)

    def _pending_review_item(self, identity: str) -> ReviewItem | None:
        return self.review_workflow.review_item_for_identity(
            self.review_items,
            identity,
            excluded=False,
        )

    @staticmethod
    def _pending_source_description(source: ExcludedSource) -> str:
        layers = ", ".join(source.source_layers) or "—"
        handles = ", ".join(source.source_handles) or "—"
        return f"{source.role}｜圖層 {layers}｜Handle {handles}"

    def _refresh_pending_source_exclusion_controls(self) -> None:
        workflow = getattr(self, "review_workflow", None)
        if workflow is None:
            return
        draft = workflow.pending_source_exclusion_draft
        tree = getattr(self, "pending_source_tree", None)
        if tree is not None:
            tree.delete(*tree.get_children())
            self._pending_source_tree_identity_by_iid = {}
            for index, source in enumerate(draft.sources):
                item = self._pending_review_item(source.identity)
                iid = f"pending_source_{index}"
                self._pending_source_tree_identity_by_iid[iid] = source.identity
                tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(
                        (
                            item.display_id
                            if item is not None
                            else source.display_id_when_excluded or source.identity
                        ),
                        self._pending_source_description(source),
                        "取消",
                    ),
                )
        frame = getattr(self, "pending_source_frame", None)
        if frame is not None:
            if draft.sources:
                frame.configure(
                    text=(
                        f"待排除來源（{len(draft.sources)}，尚未重新辨識）"
                    )
                )
                frame.grid()
            else:
                frame.configure(text="待排除來源")
                frame.grid_remove()
        planning = bool(
            getattr(self, "_pending_source_exclusion_planning", False)
        )
        apply_button = getattr(self, "pending_source_apply_button", None)
        if apply_button is not None:
            apply_button.configure(
                text=f"重新辨識並套用（{len(draft.sources)}）",
                state=(
                    "normal"
                    if draft.sources and draft.state == "ACTIVE" and not planning
                    else "disabled"
                ),
            )
        discard_button = getattr(self, "pending_source_discard_button", None)
        if discard_button is not None:
            discard_button.configure(
                state="normal" if draft.sources and not planning else "disabled"
            )
        self._update_pending_action_gate()

    def _pending_tree_identity(self) -> str:
        tree = getattr(self, "pending_source_tree", None)
        if tree is None:
            return ""
        selection = tree.selection()
        if not selection:
            return ""
        return self._pending_source_tree_identity_by_iid.get(selection[0], "")

    def _on_pending_source_selected(self, _event: Any = None) -> None:
        identity = self._pending_tree_identity()
        if not identity:
            return
        item = self._pending_review_item(identity)
        if item is None:
            return
        if item.member_id:
            self._select_member(
                item.member_id,
                refit=True,
                clear_problem=True,
                source="pending_source_list",
            )
        else:
            self._select_unresolved_review_item(
                item,
                source="pending_source_list",
            )
        self._locate_selected_member()

    def _on_pending_source_tree_click(self, event: Any) -> None:
        tree = getattr(self, "pending_source_tree", None)
        if tree is None or tree.identify_column(event.x) != "#3":
            return
        iid = tree.identify_row(event.y)
        identity = self._pending_source_tree_identity_by_iid.get(iid, "")
        if identity:
            self._cancel_pending_source(identity)

    def _cancel_pending_source(self, identity: str) -> None:
        old_handles = set(self._pending_source_handles())
        try:
            self.review_workflow.unmark_source_exclusion(identity)
        except DXFImportError as exc:
            from tkinter import messagebox

            messagebox.showerror(
                "取消待排除失敗",
                str(exc),
                parent=self.window,
            )
            return
        self._sync_review_workflow_state()
        self._refresh_pending_source_visuals(old_handles)
        self._update_source_exclusion_action_state(self._selected_review_item())

    def _discard_pending_source_exclusions(self) -> None:
        old_handles = set(self._pending_source_handles())
        self.review_workflow.discard_pending_source_exclusions()
        self._sync_review_workflow_state()
        self._refresh_pending_source_visuals(old_handles)
        self._update_selected_member_panel(rebuild_candidates=False)
        self.source_exclusion_status_var.set("已捨棄所有待排除來源。")

    def _apply_pending_source_exclusions(self) -> None:
        from tkinter import messagebox

        draft = self.review_workflow.pending_source_exclusion_draft
        if not draft.sources or self.result is None:
            return
        before_result = self.result
        before_confirmations = self.review_workflow.confirmed_snapshot()
        pending_sources = draft.sources
        initiating_member_ids = tuple(
            item.member_id
            for source in pending_sources
            for item in (self._pending_review_item(source.identity),)
            if item is not None and item.member_id
        )
        self._pending_source_exclusion_planning = True
        self._refresh_pending_source_exclusion_controls()
        stage: SourceExclusionPlan | None = None
        try:
            stage = self.review_workflow.plan_pending_source_exclusions()
            impact = self._format_pending_source_exclusion_impact(
                before_result,
                before_confirmations,
                pending_sources,
                stage,
            )
        except Exception as exc:
            if stage is not None:
                self.review_workflow.cancel_pending_source_exclusion_plan(stage)
            error_text = (
                str(exc)
                if isinstance(exc, DXFImportError)
                else f"{type(exc).__name__}: {exc}"
            )
            messagebox.showerror(
                "DXF 來源排除 staging 失敗",
                f"目前辨識結果與待排除清單完全未變更。\n\n{error_text}",
                parent=self.window,
            )
            return
        finally:
            self._pending_source_exclusion_planning = False
            self._refresh_pending_source_exclusion_controls()
        if not messagebox.askyesno(
            "確認重新辨識並套用",
            impact,
            parent=self.window,
        ):
            self.review_workflow.cancel_pending_source_exclusion_plan(stage)
            return
        selected = self._stage_review_item_for_identity(
            stage,
            pending_sources[0].identity,
            excluded=True,
        )
        try:
            self._commit_source_exclusion_stage(
                stage,
                selected.key if selected is not None else "",
                initiating_member_ids=initiating_member_ids,
            )
        except Exception as exc:
            error_text = (
                str(exc)
                if isinstance(exc, DXFImportError)
                else f"{type(exc).__name__}: {exc}"
            )
            messagebox.showerror(
                "DXF 來源排除套用失敗",
                f"目前辨識結果與待排除清單完全未變更。\n\n{error_text}",
                parent=self.window,
            )
            self._refresh_pending_source_exclusion_controls()
            return
        self.source_exclusion_status_var.set(
            f"已套用 {len(pending_sources)} 筆來源排除；工程關聯與檢核結果已重新計算。"
        )

    def _member_by_id(
        self,
        member_id: str,
    ) -> Waler | Strut | Brace | AuxiliaryComponent | None:
        if hasattr(self, "review_workflow"):
            return self.review_workflow.member_by_id(member_id)
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
                        text=self._review_item_text(
                            item,
                            confirmed=self._is_review_item_confirmed(item),
                        ),
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
    def _review_item_text(
        cls,
        item: ReviewItem,
        *,
        confirmed: bool = False,
    ) -> str:
        if item.status == "excluded":
            return f"✕ {item.display_id}"
        icon = (
            cls.LEVEL_ICONS.get(item.highest_severity, "")
            if item.highest_severity != "success"
            else ""
        )
        manual = (
            " ＊"
            if item.member_id
            and item.selection_source not in {"auto", "unresolved"}
            else ""
        )
        problem_count = f" ({item.problem_count})" if item.problem_count else ""
        confirmation = " ✓" if confirmed else ""
        prefix = f"{icon} " if icon else ""
        return f"{prefix}{item.display_id}{manual}{problem_count}{confirmation}"

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

    def _candidate_row_values(
        self,
        member: Waler | Strut | Brace | AuxiliaryComponent,
        candidate: CandidatePoint,
    ) -> tuple[str, str, str, str]:
        state = self.selection_state
        statuses: list[str] = []
        if candidate.id == member.recommended_start_point_id:
            statuses.append("推薦起點")
        if candidate.id == member.recommended_end_point_id:
            statuses.append("推薦終點")
        if candidate.id == member.selected_start_point_id:
            statuses.append("目前起點")
        if candidate.id == member.selected_end_point_id:
            statuses.append("目前終點")
        if candidate.id == state.pending_start_point_id:
            statuses.append("待套用起點")
        if candidate.id == state.pending_end_point_id:
            statuses.append("待套用終點")
        if candidate.id == state.selected_candidate_point_id:
            statuses.append("目前選取")
        return (
            f"{candidate.id}｜{candidate.label}",
            f"{candidate.local_point[0]:.3f}",
            f"{candidate.local_point[1]:.3f}",
            "、".join(statuses) or "候選",
        )

    @staticmethod
    def _review_role_label(role: str) -> str:
        return {
            "waler": "圍令",
            "strut": "支撐",
            "brace": "斜撐",
            "column": "中間柱",
            "beam": "托梁",
            "corner_brace": "角撐",
            "unknown": "未分類來源",
        }.get(role, role or "未分類來源")

    @staticmethod
    def _review_display_value(value: Any) -> str:
        if value is None or value == "":
            return "—"
        if isinstance(value, float):
            return f"{value:.3f}"
        if isinstance(value, (tuple, list, dict)):
            if not value:
                return "—"
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return str(value)

    @staticmethod
    def _engineering_path_display(value: Any) -> str:
        if not isinstance(value, (tuple, list)) or not value:
            return "—"
        points = []
        for point in value:
            if not isinstance(point, (tuple, list)) or len(point) < 2:
                continue
            try:
                points.append(f"({float(point[0]):.3f}, {float(point[1]):.3f})")
            except (TypeError, ValueError):
                continue
        return " → ".join(points) or "—"

    @classmethod
    def _engineering_crossings_display(cls, value: Any) -> str:
        if not isinstance(value, (tuple, list)) or not value:
            return "—"
        lines: list[str] = []
        for index, crossing in enumerate(value, start=1):
            if not isinstance(crossing, Mapping):
                continue
            details = [
                f"{index}. 支撐 {crossing.get('strut_id') or '—'}",
                "支撐位置 "
                + cls._review_display_value(crossing.get("strut_station"))
                + " mm",
                "托梁線段 "
                + cls._review_display_value(crossing.get("beam_segment_index")),
                "距離 "
                + cls._review_display_value(crossing.get("distance"))
                + " mm",
            ]
            local_point = crossing.get("local_point")
            if local_point:
                details.append("局部座標 " + cls._engineering_path_display((local_point,)))
            world_point = crossing.get("world_point")
            if world_point:
                details.append("世界座標 " + cls._engineering_path_display((world_point,)))
            method = str(crossing.get("recognition_method") or "")
            if method:
                details.append("辨識方式 " + recognition_method_label(method))
            lines.append("｜".join(details))
        return "\n".join(lines) or "—"

    @classmethod
    def _engineering_display_value(
        cls,
        member: Waler | Strut | Brace | AuxiliaryComponent,
        field_name: str,
        value: Any,
    ) -> str:
        if field_name in {"Path", "WorldPath", "LocalPath"}:
            return cls._engineering_path_display(value)
        if field_name == "Crossings":
            return cls._engineering_crossings_display(value)
        if field_name == "Remark" and member.recognition_method:
            return (
                f"DXF {recognition_method_label(member.recognition_method)}"
                f"（信心度 {member.confidence:.0%}）"
            )
        return cls._review_display_value(value)

    def _shared_layout_group_for_strut(self, strut_id: str) -> str:
        result = getattr(self, "result", None)
        if result is None:
            return ""
        group_number = 1
        assigned: set[str] = set()
        for candidate in result.double_support_candidates:
            if not candidate.is_formally_accepted:
                continue
            if (
                candidate.first_strut_id in assigned
                or candidate.second_strut_id in assigned
            ):
                continue
            group_id = f"G{group_number}"
            group_number += 1
            assigned.update(
                (candidate.first_strut_id, candidate.second_strut_id)
            )
            if strut_id in {
                candidate.first_strut_id,
                candidate.second_strut_id,
            }:
                return group_id
        return ""

    def _associated_strut_ids_for_member(
        self,
        member: AuxiliaryComponent,
    ) -> tuple[str, ...]:
        """Return every derived Strut relation while keeping primary first."""

        result = getattr(self, "result", None)
        identifiers: list[str] = []

        def add(identifier: str) -> None:
            value = str(identifier or "").strip()
            if value and value not in identifiers:
                identifiers.append(value)

        add(member.associated_strut_id)
        if isinstance(member, Beam):
            for identifier in member.associated_strut_ids:
                add(identifier)
        if result is None:
            return tuple(identifiers)
        role = "column" if isinstance(member, Column) else "beam"
        for association in result.component_associations:
            if (
                association.component_id == member.id
                and association.component_role == role
            ):
                add(association.strut_id)
        # The reverse fields are also persisted on Strut and provide a safe
        # fallback for older restored review snapshots without association
        # records.
        for strut in result.struts:
            associated_ids = (
                strut.associated_columns
                if isinstance(member, Column)
                else strut.associated_beams
            )
            if member.id in associated_ids:
                add(strut.id)
        return tuple(identifiers)

    def _engineering_data_rows(
        self,
        member: Waler | Strut | Brace | AuxiliaryComponent | None,
    ) -> tuple[tuple[str, str], ...]:
        if member is None:
            return ()
        row = member.to_project_row()
        if isinstance(member, Strut):
            row = {
                "StrutID": row.get("StrutID"),
                "SharedLayoutGroup": self._shared_layout_group_for_strut(
                    member.id
                ),
                **{
                    key: value
                    for key, value in row.items()
                    if key != "StrutID"
                },
            }
        elif isinstance(member, Column):
            primary_id = str(row.pop("AssociatedStrutID", "") or "")
            row = {
                **row,
                "PrimaryAssociatedStrutID": primary_id,
                "AssociatedStrutIDs": ",".join(
                    self._associated_strut_ids_for_member(member)
                ),
            }
        elif isinstance(member, Waler):
            connected = build_waler_connected_member_summary(
                getattr(self, "result", None),
                member.id,
            )
            row = {
                **row,
                "ContactFaceState": (
                    (
                        "正式接觸面（人工採用）"
                        if member.engineering_line_authority == "manual_repair"
                        else "正式接觸面（自動辨識）"
                    )
                    if member.has_formal_contact_face
                    else "暫定中心軸（尚未完成接觸面）"
                ),
                "ConnectedStrutIDs": "、".join(connected.strut_ids) or "—",
                "ConnectedBraceIDs": "、".join(connected.brace_ids) or "—",
                "ConnectedCornerBraceIDs": (
                    "、".join(connected.corner_brace_ids) or "—"
                ),
            }
        role, _role_label = self._member_role(member)
        rows = [
            (
                engineering_field_label(role, key),
                self._engineering_display_value(member, key, value),
            )
            for key, value in row.items()
        ]
        if isinstance(member, (Brace, CornerBrace)):
            rows.append(
                (
                    "構件寬度（mm）",
                    self._engineering_width_display(member.source_width),
                )
            )
        rows.append(
            (
                engineering_field_label(role, "Length"),
                f"{_distance(member.start, member.end):.3f}",
            )
        )
        return tuple(rows)

    @staticmethod
    def _engineering_width_display(value: Any) -> str:
        try:
            width = float(value)
        except (TypeError, ValueError):
            return "—"
        if not math.isfinite(width) or width <= 0.0:
            return "—"
        return f"{width:.3f}"

    def _update_engineering_data_panel(
        self,
        member: Waler | Strut | Brace | AuxiliaryComponent | None,
    ) -> None:
        frame = getattr(self, "engineering_data_rows_frame", None)
        if frame is None:
            return
        for child in frame.winfo_children():
            child.destroy()
        rows = self._engineering_data_rows(member)
        if not rows:
            self.engineering_empty_label = self.ttk.Label(
                frame,
                textvariable=self.engineering_empty_var,
                foreground="#607d8b",
            )
            self.engineering_empty_label.grid(row=0, column=0, sticky="w")
            return
        for index, (label, value) in enumerate(rows):
            self.ttk.Label(frame, text=f"{label}：").grid(
                row=index, column=0, padx=(0, 5), pady=2, sticky="ne"
            )
            self.ttk.Label(
                frame,
                text=value,
                wraplength=420,
                justify="left",
            ).grid(row=index, column=1, pady=2, sticky="nw")

    def _update_recognition_data_panel(
        self,
        item: ReviewItem | None,
        member: Waler | Strut | Brace | AuxiliaryComponent | None,
    ) -> None:
        variables = getattr(self, "recognition_info_vars", None)
        if variables is None:
            return
        severity_labels = {
            "success": "正常",
            "info": "正常",
            "warning": "警告",
            "error": "錯誤",
            "critical": "嚴重錯誤",
        }
        formal = bool(
            item is not None
            and item.status == "recognized"
            and item.role in FORMAL_REVIEW_ROLES
            and member is not None
        )
        values = {
            "display_id": (
                (item.display_id_before_exclusion or item.display_id)
                if item is not None
                else "—"
            ),
            "system_status": (
                severity_labels.get(item.highest_severity, item.highest_severity)
                if item is not None
                else "—"
            ),
            "human_status": (
                "已確認 ✓"
                if formal and self._is_review_item_confirmed(item)
                else ("未確認" if formal else "不適用")
            ),
            "role": self._review_role_label(item.role) if item else "—",
            "layer": "、".join(item.source_layers) if item else "—",
            "handles": ", ".join(item.source_handles) if item else "—",
            "entity_types": (
                "、".join(
                    dxf_entity_type_label(value)
                    for value in item.source_entity_types
                )
                if item
                else "—"
            ),
            "method": (
                recognition_method_label(member.recognition_method)
                if member is not None
                else (
                    "已停止參與工程辨識"
                    if item is not None and item.status == "excluded"
                    else (
                        "尚未形成正式工程構件"
                        if item is not None
                        else "—"
                    )
                )
            ),
            "selection_source": (
                self._selection_source_label(member.selection_source)
                if member is not None
                else (
                    self._selection_source_label(item.selection_source)
                    if item is not None
                    else "—"
                )
            ),
            "source_width": (
                f"{member.source_width:.3f}"
                if member is not None and member.source_width > 0.0
                else "—"
            ),
            "confidence": (
                f"{member.confidence:.1%}" if member is not None else "—"
            ),
            "centerline": (
                "已建立" if member is not None and member.centerline_computed
                else ("未建立" if member is not None else "—")
            ),
            "engineering_candidate": (
                member.selected_candidate_id or "—"
                if member is not None
                else "—"
            ),
            "warnings": (
                "\n".join(member.warnings) or "—"
                if member is not None
                else "—"
            ),
            "exclusion_reason": (
                item.exclusion_reason or "—" if item is not None else "—"
            ),
        }
        for key, variable in variables.items():
            variable.set(values.get(key, "—") or "—")

    @staticmethod
    def corner_brace_repair_disabled_reason(item: ReviewItem | None) -> str:
        """Return an empty string only for safely identifiable repair subjects."""

        corner_brace = member_role_label("corner_brace")
        if item is None:
            return f"請先選取{corner_brace}或待修{corner_brace}來源。"
        if item.status == "excluded":
            return f"已排除的 DXF 來源不能修補{corner_brace}。"
        if item.role != "corner_brace":
            return f"只有{corner_brace}可使用{corner_brace}修補。"
        if not normalize_source_handles(item.source_handles):
            return f"{corner_brace}修補需要明確的 DXF 來源識別。"
        if item.status == "recognized" and item.member_id:
            return ""
        if item.status == "unresolved" and item.member_id is None:
            return ""
        return f"此檢視項目不是可修補的正式{corner_brace}或待修{corner_brace}來源。"

    def _update_modification_tools(
        self,
        item: ReviewItem | None,
        member: Waler | Strut | Brace | AuxiliaryComponent | None,
    ) -> None:
        frame = getattr(self, "modification_tools_frame", None)
        if frame is None:
            return
        formal = bool(
            item is not None
            and item.status == "recognized"
            and item.role in FORMAL_REVIEW_ROLES
            and member is not None
        )
        repair_eligible = bool(
            isinstance(member, Waler)
            and is_waler_engineering_line_repair_eligible(member)
        )
        has_candidates = bool(
            (formal or repair_eligible) and getattr(member, "candidate_points", ())
        )
        cad_supported = isinstance(member, (Waler, Strut, Brace))
        source_supported = bool(
            item is not None and item.role and item.source_handles
        )
        has_pending_sources = bool(
            self.review_workflow.pending_source_exclusion_draft.sources
        )
        repair_supported = not self.corner_brace_repair_disabled_reason(item)

        self.endpoint_tools_frame.pack_forget()
        self.cad_engineering_line_button.pack_forget()
        self.corner_brace_repair_button.pack_forget()
        self.column_association_repair_button.pack_forget()
        self.waler_formalization_button.pack_forget()
        if has_candidates:
            self.endpoint_tools_frame.pack(side="left")
        if cad_supported:
            self.cad_engineering_line_button.pack(side="left", padx=(10, 0))
            self.cad_temp_status_label.grid()
        else:
            self.cad_temp_status_label.grid_remove()
        if repair_supported:
            self.corner_brace_repair_button.configure(state="normal")
            self.corner_brace_repair_button.pack(side="left", padx=(10, 0))
        else:
            self.corner_brace_repair_button.configure(state="disabled")
        column_repair_available = bool(self._selected_column_repair_subject_id())
        if column_repair_available:
            self.column_association_repair_button.configure(state="normal")
            self.column_association_repair_button.pack(side="left", padx=(10, 0))
        else:
            self.column_association_repair_button.configure(state="disabled")
        waler_formalization_available = bool(
            self._selected_waler_formalization_subject_id()
        )
        if waler_formalization_available:
            self.waler_formalization_button.configure(state="normal")
            self.waler_formalization_button.pack(side="left", padx=(10, 0))
        else:
            self.waler_formalization_button.configure(state="disabled")
        if (
            has_candidates
            or cad_supported
            or repair_supported
            or column_repair_available
            or waler_formalization_available
        ):
            self.geometry_tools_frame.grid()
        else:
            self.geometry_tools_frame.grid_remove()
        if source_supported or has_pending_sources:
            self.source_tools_frame.grid()
            self.source_exclusion_status_label.grid()
        else:
            self.source_tools_frame.grid_remove()
            self.source_exclusion_status_label.grid_remove()
        if (
            has_candidates
            or cad_supported
            or repair_supported
            or column_repair_available
            or waler_formalization_available
            or source_supported
            or has_pending_sources
        ):
            frame.grid()
        else:
            frame.grid_remove()
        self._refresh_pending_source_exclusion_controls()

    def _update_candidate_section_visibility(
        self,
        item: ReviewItem | None,
        member: Waler | Strut | Brace | AuxiliaryComponent | None,
    ) -> None:
        frame = getattr(self, "candidate_frame", None)
        if frame is None:
            return
        visible = bool(
            item is not None
            and item.role in FORMAL_REVIEW_ROLES
            and member is not None
            and getattr(member, "candidate_points", ())
            and (
                item.status == "recognized"
                or (
                    item.status == "unresolved"
                    and isinstance(member, Waler)
                    and is_waler_engineering_line_repair_eligible(member)
                )
            )
        )
        if visible:
            frame.grid()
        else:
            frame.grid_remove()

    @staticmethod
    def _widget_state(widget: Any) -> str:
        try:
            return str(widget.cget("state"))
        except (AttributeError, TypeError):
            return str(getattr(widget, "options", {}).get("state", "normal"))

    def _hide_widget_tooltip(self, _event: Any = None) -> None:
        tooltip = getattr(self, "_tooltip_window", None)
        if tooltip is not None:
            try:
                tooltip.destroy()
            except Exception:
                pass
        self._tooltip_window = None

    def _show_widget_tooltip(self, widget: Any) -> None:
        text = str(getattr(widget, "_tooltip_text", ""))
        if not text:
            return
        self._hide_widget_tooltip()
        try:
            tooltip = self.tk.Toplevel(self.window)
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(
                f"+{widget.winfo_rootx() + 12}+{widget.winfo_rooty() + widget.winfo_height() + 4}"
            )
            self.ttk.Label(
                tooltip,
                text=text,
                relief="solid",
                borderwidth=1,
                padding=(6, 3),
            ).pack()
            self._tooltip_window = tooltip
        except Exception:
            self._tooltip_window = None

    def _set_widget_tooltip(self, widget: Any, text: str) -> None:
        setattr(widget, "_tooltip_text", text)
        if getattr(widget, "_pending_tooltip_bound", False):
            return
        try:
            widget.bind(
                "<Enter>",
                lambda _event, target=widget: self._show_widget_tooltip(target),
            )
            widget.bind("<Leave>", self._hide_widget_tooltip)
            setattr(widget, "_pending_tooltip_bound", True)
        except (AttributeError, TypeError):
            pass

    def _pending_gated_widgets(self) -> tuple[Any, ...]:
        names = (
            "layer_settings_button",
            "coordinate_settings_button",
            "double_support_settings_button",
            "candidate_pick_start_button",
            "candidate_pick_end_button",
            "preview_pick_start_button",
            "preview_pick_end_button",
            "candidate_apply_button",
            "preview_apply_candidate_button",
            "cad_engineering_line_button",
            "corner_brace_repair_button",
            "column_association_repair_button",
            "waler_formalization_button",
            "review_confirmation_button",
            "material_spec_combo",
            "waler_contact_apply_button",
            "corner_brace_repair_apply_button",
            "replace_import_mode_button",
            "append_import_mode_button",
            "pause_button",
            "apply_button",
        )
        return tuple(
            widget
            for name in names
            for widget in (getattr(self, name, None),)
            if widget is not None
        )

    def _update_pending_action_gate(self) -> None:
        workflow = getattr(self, "review_workflow", None)
        if workflow is None:
            return
        reason = workflow.pending_mutation_disabled_reason()
        previous = getattr(self, "_pending_gate_previous_states", None)
        if previous is None:
            previous = {}
            self._pending_gate_previous_states = previous
        if reason:
            for widget in self._pending_gated_widgets():
                key = id(widget)
                if key not in previous:
                    previous[key] = (widget, self._widget_state(widget))
                widget.configure(state="disabled")
                self._set_widget_tooltip(widget, reason)
            return
        for widget, state in previous.values():
            try:
                widget.configure(state=state)
                self._set_widget_tooltip(widget, "")
            except Exception:
                pass
        previous.clear()

    def _update_preview_candidate_action_state(self) -> None:
        """Keep candidate commit controls consistent across both windows."""

        state = self.selection_state
        has_member = self._selected_member() is not None
        picking = state.mode in {"pick_start", "pick_end"}
        pending_changed = has_member and (
            state.pending_start_point_id != state.selected_start_point_id
            or state.pending_end_point_id != state.selected_end_point_id
        )
        apply_state = "normal" if pending_changed and not picking else "disabled"
        cancel_state = "normal" if pending_changed or picking else "disabled"
        for attribute, button_state in (
            ("candidate_apply_button", apply_state),
            ("preview_apply_candidate_button", apply_state),
            ("preview_cancel_candidate_button", cancel_state),
        ):
            button = getattr(self, attribute, None)
            if button is not None:
                options = {"state": button_state}
                if attribute != "preview_cancel_candidate_button":
                    options["text"] = "套用選取點"
                button.configure(**options)
        self._update_pending_action_gate()

    def _rebuild_candidate_tree(self) -> None:
        if not hasattr(self, "candidate_tree_adapter"):
            return
        member = self._selected_member()
        if member is None:
            self.candidate_tree_adapter.rebuild("", (), lambda _point: ())
            self.performance_diagnostics.candidate_tree_rebuilds += 1
            return
        points = self.candidate_point_store.component_points(member.id)
        self.candidate_tree_adapter.rebuild(
            member.id,
            points,
            lambda point: self._candidate_row_values(member, point),
        )
        self.performance_diagnostics.candidate_tree_rebuilds += 1
        self.candidate_tree_adapter.sync_selection(
            self.selection_state.selected_candidate_point_id
        )
        self.candidate_tree_adapter.set_hover(
            self.selection_state.hovered_candidate_point_id
        )

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
                self._update_recognition_data_panel(review_item, None)
                self.engineering_empty_var.set("此項目沒有正式工程資料。")
                self._update_engineering_data_panel(None)
            self.candidate_detail_var.set("候選點：—")
            self._update_material_spec_panel(None)
            self._update_waler_contact_panel(None)
            if rebuild_candidates:
                self._rebuild_candidate_tree()
            self._update_candidate_section_visibility(review_item, None)
            self._update_modification_tools(review_item, None)
            self._update_review_issue_panel(review_item)
            return
        _role, role_label = self._member_role(member)
        self.preview_selected_member_var.set(
            f"目前構件：{member.id}｜{role_label}｜圖層 {member.source_layer}"
        )
        self._update_recognition_data_panel(review_item, member)
        self._update_engineering_data_panel(member)
        self._update_material_spec_panel(member)
        self._update_waler_contact_panel(member)
        if rebuild_candidates:
            self._rebuild_candidate_tree()
        else:
            self._update_candidate_tree_rows()
        self._update_candidate_detail_panel()
        self._update_candidate_section_visibility(review_item, member)
        self._update_modification_tools(review_item, member)
        self._update_review_issue_panel(review_item)

    def _update_unresolved_source_panel(self, item: ReviewItem) -> None:
        self.preview_selected_member_var.set(
            f"目前來源：{item.display_id}｜{self._review_role_label(item.role)}"
        )
        self._update_recognition_data_panel(item, None)
        self.engineering_empty_var.set("—（無 active 正式工程幾何）")
        self._update_engineering_data_panel(None)

    def _update_review_issue_panel(self, item: ReviewItem | None) -> None:
        if not hasattr(self, "detail_problem_tree"):
            return
        self.detail_problem_tree.delete(
            *self.detail_problem_tree.get_children()
        )
        self.detail_problem_record_by_iid.clear()
        if item is None:
            if hasattr(self.detail_problem_tree, "configure"):
                self.detail_problem_tree.configure(height=1)
            self.detail_problem_empty_var.set("請先選取檢核項目。")
            self.detail_guidance_var.set("")
            self._update_review_confirmation_action_state(None)
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
                    record.display_type,
                    record.description,
                ),
                tags=(record.severity,),
            )
        if hasattr(self.detail_problem_tree, "configure"):
            self.detail_problem_tree.configure(height=max(1, len(item.problems)))
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
        self._update_review_confirmation_action_state(item)
        self._update_source_exclusion_action_state(item)

    def _update_review_confirmation_action_state(
        self,
        item: ReviewItem | None,
    ) -> None:
        button = getattr(self, "review_confirmation_button", None)
        if button is None:
            return
        frame = getattr(self, "review_confirmation_frame", None)
        visible = bool(
            item is not None
            and item.status == "recognized"
            and item.role in FORMAL_REVIEW_ROLES
        )
        if frame is not None:
            if visible:
                frame.grid()
            else:
                frame.grid_remove()
        confirmed = self._is_review_item_confirmed(item)
        button.configure(
            text="已確認 ✓" if confirmed else "確認此構件",
            state=(
                "normal"
                if visible
                and review_item_can_be_confirmed(item)
                and not confirmed
                else "disabled"
            ),
        )

    def _update_source_exclusion_action_state(
        self,
        item: ReviewItem | None,
    ) -> None:
        status_var = getattr(self, "source_exclusion_status_var", None)
        buttons = tuple(
            button
            for name in (
                "source_exclusion_button",
                "preview_source_exclusion_button",
            )
            for button in (getattr(self, name, None),)
            if button is not None
        )
        if not buttons and status_var is None:
            return
        reason = self._source_exclusion_disabled_reason(item)
        restoring = item is not None and item.status == "excluded"
        pending = bool(
            item is not None
            and not restoring
            and self.review_workflow.pending_source_exclusion_contains(item)
        )
        text = (
            "復原此來源"
            if restoring
            else "取消待排除"
            if pending
            else "標記待排除"
        )
        for button in buttons:
            button.configure(
                text=text,
                state="disabled" if reason else "normal",
            )
            self._set_widget_tooltip(button, reason)
        if status_var is not None:
            status_var.set(reason)
        self._refresh_pending_source_exclusion_controls()

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
        elif member.material_spec_source == "auto_hatch":
            self.material_spec_status_var.set(
                "已依 Waler 圖層填充來源自動辨認為 RC；可人工改選。"
            )
        elif member.material_spec_source == "manual":
            self.material_spec_status_var.set("已採用人工選擇。")
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
            mutation = self.review_workflow.set_material_spec(
                member.id,
                self.material_spec_var.get(),
            )
        except DXFImportError as exc:
            self.material_spec_status_var.set(str(exc))
            return
        self._sync_review_workflow_state()
        self._refresh_result_views(
            preview_dirty=RenderDirty.DETAIL_PANEL,
            rebuild_candidate_tree=False,
        )
        self._show_workflow_confirmation_invalidations(mutation)

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
            self.waler_contact_status_var.set("缺少圍令接觸位置檢核資料。")
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
                f"（圖元代碼：{review.continuous_wall_source_handle}）。"
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
            plan = self.review_workflow.preview_waler_contact_adjustment(
                member.id,
                **self._waler_contact_dimensions(),
            )
        except DXFImportError as exc:
            self._clear_waler_adjustment_preview()
            self.waler_contact_status_var.set(str(exc))
            messagebox.showerror("圍令接觸位置調整", str(exc), parent=self.window)
            return
        self.waler_adjustment_preview_plan = plan
        self.waler_contact_displacement_var.set(
            f"接觸位置調整：{plan.contact_displacement:+.3f} mm"
        )
        self.waler_contact_impact_var.set(
            "影響：支撐 {0} 支、斜撐 {1} 支、角撐 {2} 支、"
            "中間柱 {3} 支、托梁 {4} 支".format(
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
                else "目前 DXF 結果仍有阻擋錯誤，不能套用。"
            )
        )
        self.waler_contact_apply_button.configure(
            state="normal" if plan.can_apply else "disabled"
        )
        self._draw_waler_adjustment_overlay()
        repair_candidate = self._selected_corner_brace_repair_candidate()
        if repair_candidate is not None:
            self._draw_corner_brace_repair_overlay(repair_candidate)
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
            mutation = self.review_workflow.apply_waler_contact_adjustment(
                member.id,
                **self._waler_contact_dimensions(),
            )
        except DXFImportError as exc:
            self.waler_contact_status_var.set(str(exc))
            self.waler_contact_apply_button.configure(state="disabled")
            messagebox.showerror("圍令接觸位置調整", str(exc), parent=self.window)
            return
        self._clear_waler_adjustment_preview()
        self._contact_panel_waler_id = ""
        self._sync_review_workflow_state()
        self._refresh_result_views()
        self.selection_controller.synchronize_formal_member()
        self._show_workflow_confirmation_invalidations(mutation)
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
        detail = (
            self._candidate_detail_text(candidate)
            if candidate is not None
            else "候選點：—"
        )
        self.candidate_detail_var.set(detail)

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
        repair_member = (
            self.review_workflow.member_by_id(review_item.member_id)
            if review_item is not None and review_item.member_id
            else None
        )
        if (
            review_item is not None
            and review_item.status in {"unresolved", "excluded"}
            and not (
                review_item.status == "unresolved"
                and isinstance(repair_member, Waler)
                and is_waler_engineering_line_repair_eligible(repair_member)
            )
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

    def _tree_iid_for_review_item_key(self, review_key: str) -> str:
        return next(
            (
                iid
                for iid, key in getattr(
                    self,
                    "review_item_by_tree_iid",
                    {},
                ).items()
                if key == review_key
            ),
            "",
        )

    def _select_unresolved_review_item(
        self,
        item: ReviewItem,
        *,
        source: str = "component_tree",
    ) -> None:
        self.selected_problem = None
        self.selected_review_item_key = item.key
        self.focus_member_ids.clear()
        self.focus_handles = set(item.source_handles)
        revision = getattr(self.selection_state, "revision", 0) + 1
        self.selection_state = SelectionState(
            selection_source=source,
            revision=revision,
        )
        self.selection_controller.state = self.selection_state
        if source != "component_tree":
            iid = self._tree_iid_for_review_item_key(item.key)
            if iid:
                self.member_tree_selection.select(iid)
        if self.selected_only_var.get():
            self.selected_only_var.set(False)
            self._refresh_problem_tree()
        if hasattr(self, "candidate_action_status_var"):
            self.candidate_action_status_var.set(
                (
                    "此來源已排除；可於修改工具使用「復原此來源」。"
                    if item.status == "excluded"
                    else "此來源尚未形成正式構件；幾何修正工具目前不適用。"
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
            if hasattr(self, "candidate_pick_mode_var"):
                self.candidate_pick_mode_var.set("")
            self.candidate_action_status_var.set(
                "單擊候選點只會預覽；請先選擇要修改起點或終點。"
            )
        if changed or review_changed:
            # Keep the detail and candidate panels responsive when refitting a
            # large DXF such as
            # Y29.  The scheduled render still updates the preview overlays, but
            # the form must not wait for a full-scene redraw before reflecting
            # the component selected in the Review tree.
            self._update_selected_member_panel()
        if refit and (changed or review_changed):
            self.preview_view_bounds = None
            self.preview_fit_all = False
            self.render_scheduler.request(RenderDirty.FULL_SCENE)
        if changed and hasattr(self, "candidate_action_status_var"):
            self.candidate_action_status_var.set(
                "可直接在預覽圖點擊藍色起點或紅色終點，再點選新的黃色候選點。"
            )

    @staticmethod
    def _selection_source_label(source: str) -> str:
        return {
            "auto": "自動辨識",
            "unresolved": "未解析",
            "manual_candidate_points": "人工候選點",
            "cad_manual": "CAD 人工指定",
            "waler_contact_adjustment": "圍令接觸位置調整",
        }.get(source, source or "自動辨識")

    def _candidate_detail_text(self, candidate: CandidatePoint) -> str:
        return (
            f"{candidate.id}｜{candidate.label}\n"
            f"世界座標：({candidate.world_point[0]:.3f}, {candidate.world_point[1]:.3f})　"
            f"局部座標：({candidate.local_point[0]:.3f}, {candidate.local_point[1]:.3f})"
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
        if previous_mode in {"pick_start", "pick_end"} and hasattr(
            self, "candidate_pick_mode_var"
        ):
            self.candidate_pick_mode_var.set("")
        if previous_mode == "pick_start":
            self.candidate_action_status_var.set(
                f"已選擇待套用起點 {point_id}；按「套用選取點」才會重建模型。"
            )
        elif previous_mode == "pick_end":
            self.candidate_action_status_var.set(
                f"已選擇待套用終點 {point_id}；按「套用選取點」才會重建模型。"
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
        if hasattr(self, "candidate_pick_mode_var"):
            self.candidate_pick_mode_var.set(mode)
        prompt = "請選擇新的起點" if mode == "pick_start" else "請選擇新的終點"
        self.candidate_action_status_var.set(f"{prompt}（Esc 取消本次選點）")
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
        if hasattr(self, "candidate_pick_mode_var"):
            self.candidate_pick_mode_var.set("")
        self.candidate_action_status_var.set("已取消本次選點，待套用值維持不變。")
        return "break"

    def _swap_pending_points(self) -> None:
        if not self.selection_controller.swap_pending_points():
            return
        self.candidate_action_status_var.set("已交換待套用起終點；正式模型尚未修改。")

    def _cancel_candidate_changes(self) -> None:
        if not self.selection_controller.cancel_pending():
            return
        if hasattr(self, "candidate_pick_mode_var"):
            self.candidate_pick_mode_var.set("")
        self.candidate_action_status_var.set("已取消待套用修改；正式模型未變更。")

    def _restore_recommended_points(self) -> None:
        if not self.selection_controller.restore_recommended_points():
            return
        self.candidate_action_status_var.set(
            "已恢復系統推薦至待套用值；仍需按「套用選取點」。"
        )

    def _apply_candidate_changes(self) -> None:
        from tkinter import messagebox

        message_parent = self.preview_window or self.window
        member = self._selected_member()
        if member is None or self.world_result is None:
            self.candidate_action_status_var.set("請先選取構件。")
            return
        if (
            isinstance(member, Waler)
            and member.contact_face_state == "formal"
            and member.engineering_line_authority == "manual_repair"
        ):
            message = (
                "此圍令已正式化，請使用修改工具的「圍令正式化」重新採用。"
            )
            self.candidate_action_status_var.set(message)
            messagebox.showinfo(
                "請改用圍令正式化工具",
                message,
                parent=message_parent,
            )
            return
        state = self.selection_state
        validations = self.review_workflow.validate_candidate_change(
            member.id,
            state.pending_start_point_id,
            state.pending_end_point_id,
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
            mutation = self.review_workflow.apply_candidate_change(
                member.id,
                state.pending_start_point_id,
                state.pending_end_point_id,
                state.pending_selection_source,
            )
            self._sync_review_workflow_state()
        except DXFImportError as exc:
            self.candidate_action_status_var.set(str(exc))
            return
        self._refresh_result_views(
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
        self._show_workflow_confirmation_invalidations(mutation)
        self.candidate_action_status_var.set(
            f"已套用 {member.id}，並重建連接、衍生資料及求解器輸入。"
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
                "目前 CAD 暫存工程線僅支援圍令、支撐與斜撐。"
            )
            return
        try:
            event = self.cad_event_watcher.check_new_event()
            if event is None:
                self.cad_temp_status_var.set("目前沒有待讀取的 CAD 暫存工程線。")
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
                    "請關閉 DXF 匯入視窗後由主畫面套用。"
                )
                return
            if operation == "cancel":
                self.cad_temp_status_var.set(
                    "SUPCLEAR 事件已保留；請關閉 DXF 匯入視窗後由主畫面清除。"
                )
                return
            event_type = str(event.get("type", "")).strip().lower()
            if event_type not in supported_roles[role]:
                raise DXFImportError(
                    f"CAD 事件類型 {event_type or '—'} 與選取構件 {member.id} 不相符。"
                )
            data = event.get("data")
            if not isinstance(data, Mapping):
                raise DXFImportError("CAD 暫存事件缺少工程線座標資料。")
            start = float(data["StartX"]), float(data["StartY"])
            end = float(data["EndX"]), float(data["EndY"])
            start_id, end_id, mutation = (
                self.review_workflow.add_cad_candidate_line(
                    member.id,
                    start,
                    end,
                )
            )
            self._sync_review_workflow_state()
            self.cad_event_watcher.acknowledge(event)
        except (DXFImportError, KeyError, TypeError, ValueError, OSError) as exc:
            self.cad_temp_status_var.set(str(exc))
            messagebox.showerror("CAD 工程線讀取失敗", str(exc), parent=self.window)
            return
        self.cad_temp_status_var.set(
            (
                f"已讀取 {member.id} 的 CAD 指定工程線；"
                "請開啟修改工具的「圍令正式化」，選擇「已讀取的 CAD 線」後採用。"
                if isinstance(member, Waler)
                and is_waler_engineering_line_repair_eligible(member)
                else f"已讀取 {member.id} 的 CAD 指定工程線；請確認後按「套用選取點」。"
            )
        )
        self._refresh_result_views(
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
        self._show_workflow_confirmation_invalidations(mutation)

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

    def _invalidate_error_source_hit_index(self) -> None:
        """Discard screen-space records whenever one projection input changes."""

        self.canvas_error_source_hit_lines = []
        self._error_source_hit_index_stamp = None

    @staticmethod
    def _ui_boolean_value(variable: Any, default: bool) -> bool:
        try:
            return bool(variable.get())
        except (AttributeError, TypeError):
            return default

    def _current_error_source_hit_index_stamp(
        self,
    ) -> ErrorSourceHitIndexStamp:
        result = getattr(self, "result", None)
        viewport = getattr(self, "preview_viewport", None)
        viewport_transform = (
            None
            if viewport is None or viewport.view_bounds is None
            else viewport.legacy_transform
        )
        review_items_signature = tuple(
            sorted(
                (
                    item.key,
                    item.status,
                    item.highest_severity,
                    normalize_source_handles(item.source_handles),
                )
                for item in getattr(self, "review_items", ())
            )
        )
        return ErrorSourceHitIndexStamp(
            viewport_transform=viewport_transform,
            render_generation=getattr(self, "_preview_render_generation", 0),
            visibility_signature=(
                self._ui_boolean_value(
                    getattr(self, "show_source_var", None),
                    True,
                ),
                self._ui_boolean_value(
                    getattr(self, "show_auxiliary_var", None),
                    True,
                ),
                tuple(sorted(getattr(self, "focus_handles", ()))),
            ),
            review_items_signature=review_items_signature,
            active_result_signature=(
                id(result),
                str(getattr(result, "source_fingerprint", "")),
            ),
        )

    def _unresolved_error_review_keys_by_handle(
        self,
    ) -> dict[str, tuple[str, ...]]:
        keys_by_handle: dict[str, set[str]] = {}
        for item in getattr(self, "review_items", ()):
            if (
                item.status != "unresolved"
                or item.highest_severity not in ERROR_SEVERITIES
            ):
                continue
            for handle in normalize_source_handles(item.source_handles):
                keys_by_handle.setdefault(handle, set()).add(item.key)
        return {
            handle: tuple(sorted(keys))
            for handle, keys in keys_by_handle.items()
        }

    def _rebuild_error_source_hit_index(self) -> None:
        """Project only currently rendered unresolved-error source segments."""

        self.canvas_error_source_hit_lines = []
        result = getattr(self, "result", None)
        viewport = getattr(self, "preview_viewport", None)
        if result is not None and viewport is not None and viewport.view_bounds is not None:
            keys_by_handle = self._unresolved_error_review_keys_by_handle()
            visible_geometry = self._visible_preview_source_geometry(
                result,
                show_source=self._ui_boolean_value(
                    getattr(self, "show_source_var", None),
                    True,
                ),
                show_auxiliary=self._ui_boolean_value(
                    getattr(self, "show_auxiliary_var", None),
                    True,
                ),
                focus_handles=getattr(self, "focus_handles", ()),
            )
            coordinate_system = result.coordinate_system
            for geometry in visible_geometry:
                normalized = normalize_source_handles(
                    (geometry.source_handle,)
                )
                if not normalized:
                    continue
                review_keys = keys_by_handle.get(normalized[0], ())
                if not review_keys:
                    continue
                displayed_points = tuple(
                    coordinate_system.transform(point)
                    for point in geometry.points
                )
                if (
                    len(displayed_points) < 2
                    or not self._preview_intersects(displayed_points)
                ):
                    continue
                projected = tuple(
                    self._project_preview_point(point)
                    for point in displayed_points
                )
                segments = tuple(zip(projected, projected[1:]))
                if geometry.closed and len(projected) > 2:
                    segments = (*segments, (projected[-1], projected[0]))
                self.canvas_error_source_hit_lines.extend(
                    (review_key, start, end)
                    for review_key in review_keys
                    for start, end in segments
                )
        self._error_source_hit_index_stamp = (
            self._current_error_source_hit_index_stamp()
        )

    def _ensure_error_source_hit_index_current(self) -> bool:
        current_stamp = self._current_error_source_hit_index_stamp()
        if getattr(self, "_error_source_hit_index_stamp", None) != current_stamp:
            self._rebuild_error_source_hit_index()
        return self._error_source_hit_index_stamp == current_stamp

    def _error_source_hits(
        self,
        point: Point,
        tolerance_pixels: float = 12.0,
    ) -> tuple[str, ...]:
        if not self._ensure_error_source_hit_index_current():
            return ()
        hits = PreviewController.segment_hits(
            point,
            self.canvas_error_source_hit_lines,
            tolerance_pixels,
        )
        return tuple(dict.fromkeys(hits))

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
            return
        error_hits = self._error_source_hits(canvas_point)
        if len(error_hits) == 1:
            review_item = getattr(self, "review_item_by_key", {}).get(
                error_hits[0]
            )
            if (
                review_item is not None
                and review_item.status == "unresolved"
                and review_item.highest_severity in ERROR_SEVERITIES
            ):
                self._select_unresolved_review_item(
                    review_item,
                    source="canvas",
                )
            return
        if len(error_hits) > 1:
            self.candidate_action_status_var.set(
                "此位置重疊多個錯誤元件，請放大圖面後再點選，"
                "或從元件清單選取。"
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
        hovered_point_id = point_hits[0] if point_hits else ""
        hovered_member_id = ""
        if not hovered_point_id:
            hovered_member_id = self._nearest_preview_member(
                (float(event.x), float(event.y)),
                self.canvas_member_hit_lines,
            )
        error_hits = ()
        if (
            not point_hits
            and not endpoint_hits
            and not hovered_member_id
            and self.selection_state.mode == "idle"
        ):
            error_hits = self._error_source_hits(
                (float(event.x), float(event.y))
            )
        try:
            self.canvas.configure(
                cursor=(
                    "hand2"
                    if point_hits or endpoint_hits or len(error_hits) == 1
                    else "crosshair"
                )
            )
        except self.tk.TclError:
            pass
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
            if dirty & RenderDirty.SOURCE_STYLE:
                self._rebuild_changed_source_styles()
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
            if dirty & (
                RenderDirty.SOURCE_STYLE
                | RenderDirty.COMPONENT_LAYER
                | RenderDirty.CANDIDATE_LAYER
            ):
                self._preview_scene_revision = self.review_workflow.revision
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
        self._update_preview_candidate_action_state()
        self.performance_diagnostics.record("render_flush", started_at)
        self._update_performance_diagnostics_display()

    def _rebuild_changed_source_styles(self) -> None:
        handles = tuple(sorted(self._pending_source_style_handles))
        self._pending_source_style_handles.clear()
        if not handles or self.result is None or self.preview_renderer is None:
            return
        selected = set(handles)
        self.preview_renderer.delete_source_handles(handles)
        self._draw_source_geometry_layer(
            tuple(
                geometry
                for geometry in self._preview_source_geometry(self.result)
                if geometry.source_handle in selected
            )
        )
        self._draw_source_text_layer(
            tuple(
                source_text
                for source_text in self.result.source_texts
                if source_text.source_handle in selected
            )
        )
        self._update_source_layer_visibility()
        self._rebuild_error_source_hit_index()

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
        self._preview_render_generation = (
            getattr(self, "_preview_render_generation", 0) + 1
        )
        self._invalidate_error_source_hit_index()
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
        repair_candidate = self._selected_corner_brace_repair_candidate()
        if repair_candidate is not None:
            self._draw_corner_brace_repair_overlay(repair_candidate)
        self._draw_coordinate_axis_layer()
        self._update_source_layer_visibility()
        self._rebuild_error_source_hit_index()
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
        self._preview_scene_revision = self.review_workflow.revision
        self._preview_source_geometry_signature = (
            self._dialog_source_geometry_signature(self.result)
        )
        self._pending_source_style_handles.clear()

    def _preview_member_styles(
        self,
    ) -> list[tuple[Waler | Strut | Brace | AuxiliaryComponent, str, int, Any]]:
        if self.result is None:
            return []
        return [
            *(
                (
                    member,
                    (
                        "#1565c0"
                        if member.engineering_line_authority == "manual_repair"
                        else "#2e7d32"
                    )
                    if member.has_formal_contact_face
                    else "#ef6c00",
                    4 if member.has_formal_contact_face else 3,
                    None if member.has_formal_contact_face else (6, 4),
                )
                for member in self.result.walers
            ),
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
        pending_draft = getattr(
            getattr(self, "review_workflow", None),
            "pending_source_exclusion_draft",
            None,
        )
        pending_sources = getattr(pending_draft, "sources", ())
        if not isinstance(pending_sources, (tuple, list)):
            pending_sources = ()
        pending_source_keys = {
            (source.role, handle)
            for source in pending_sources
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
            is_pending = bool(
                normalized_geometry_handles
                and (geometry.role, normalized_geometry_handles[0])
                in pending_source_keys
            )
            layer = "auxiliary_geometry" if is_auxiliary else "source_geometry"
            color = (
                "#f9a825"
                if is_pending
                else "#78909c"
                if is_excluded
                else "#d7dde1"
                if is_auxiliary
                else "#b0bec5"
            )
            line_width = 3 if is_pending else 2 if is_excluded else 1
            dash = (
                (8, 4)
                if is_pending
                else (2, 5)
                if is_excluded
                else None
                if is_auxiliary
                else (4, 3)
            )
            if (
                not is_pending
                and not is_auxiliary
                and geometry.source_handle in self.focus_handles
            ):
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
        return not (
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

            def show_association(associated: object) -> None:
                if not isinstance(
                    associated,
                    (Waler, Strut, Brace, AuxiliaryComponent),
                ):
                    return
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
                    overlay_key=(
                        f"associated::{type(associated).__name__}::"
                        f"{associated.id}"
                    ),
                    fill="#1565c0",
                    width=5,
                    dash=(3, 2),
                )

            if isinstance(member, Strut):
                for associated_id in (
                    *member.associated_columns,
                    *member.associated_beams,
                ):
                    show_association(self._member_by_id(associated_id))
            elif isinstance(member, (Column, Beam)):
                for strut_id in self._associated_strut_ids_for_member(member):
                    show_association(self._member_by_id(strut_id))
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
                        f"世界座標 ({hovered_point.world_point[0]:.3f}, "
                        f"{hovered_point.world_point[1]:.3f})\n"
                        f"局部座標 ({hovered_point.local_point[0]:.3f}, "
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
                association_text = ""
                if isinstance(hovered_member, (Column, Beam)):
                    associated_strut_ids = self._associated_strut_ids_for_member(
                        hovered_member
                    )
                    if associated_strut_ids:
                        association_text = (
                            "\n關聯支撐：" + "、".join(associated_strut_ids)
                        )
                tooltip_bottom = 94 if association_text else 75
                self.canvas.coords(
                    bg_id,
                    width - 330,
                    10,
                    width - 10,
                    tooltip_bottom,
                )
                self.canvas.coords(text_id, width - 320, 17)
                self.canvas.itemconfigure(bg_id, state="normal")
                self.canvas.itemconfigure(
                    text_id,
                    text=(
                        f"{hovered_member.id}｜{role_label}\n"
                        f"圖層：{hovered_member.source_layer}\n"
                        "工程線來源："
                        f"{self._selection_source_label(hovered_member.selection_source)}"
                        f"{association_text}"
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

    def _clear_corner_brace_repair_overlay(self) -> None:
        canvas = getattr(self, "canvas", None)
        stale = set(getattr(self, "_corner_brace_repair_overlay_items", ()))
        if canvas is not None:
            for item_id in stale:
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
        self._corner_brace_repair_overlay_items = []

    def _draw_corner_brace_repair_overlay(
        self,
        candidate: CornerBraceRepairCandidate,
    ) -> None:
        """Draw residual evidence and the selected eligible proposed axis."""

        self._clear_corner_brace_repair_overlay()
        if (
            self.preview_renderer is None
            or self.preview_transform is None
            or self.result is None
            or self.corner_brace_repair_plan is None
        ):
            return
        coordinate_system = self.result.coordinate_system

        def draw(line: tuple[Point, Point], **options: Any) -> None:
            displayed = (
                coordinate_system.transform(line[0]),
                coordinate_system.transform(line[1]),
            )
            item_id = self.preview_renderer.create_line(
                "temporary_overlay",
                *self._project_preview_point(displayed[0]),
                *self._project_preview_point(displayed[1]),
                **options,
            )
            self._corner_brace_repair_overlay_items.append(item_id)

        for residual in self.corner_brace_repair_plan.residual_segments:
            draw(residual, fill="#9e9e9e", width=2, dash=(4, 3))
        draw(
            (candidate.world_start, candidate.world_end),
            fill="#0d47a1",
            width=5,
        )
        displayed_anchor = coordinate_system.transform(candidate.positional_anchor)
        anchor_x, anchor_y = self._project_preview_point(displayed_anchor)
        anchor_id = self.preview_renderer.create_oval(
            "temporary_overlay",
            anchor_x - 5,
            anchor_y - 5,
            anchor_x + 5,
            anchor_y + 5,
            fill="#fb8c00",
            outline="#e65100",
            width=2,
        )
        self._corner_brace_repair_overlay_items.append(anchor_id)
        self.canvas.tag_raise("temporary_overlay")

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
                text="X 軸",
                fill="#000000",
                anchor="e",
                font=("Arial", 9, "bold"),
            )
            renderer.create_text(
                "coordinate_axis",
                y_end[0] + 7,
                y_end[1] + 4,
                text="Y 軸",
                fill="#000000",
                anchor="nw",
                font=("Arial", 9, "bold"),
            )
        coordinate_mode = (
            "局部座標"
            if coordinate_system.mode == "local"
            else "世界座標"
        )
        information = (
            f"座標系統：{coordinate_mode}\n"
            f"原點：({coordinate_system.origin_x:.3f}, "
            f"{coordinate_system.origin_y:.3f})\n"
            f"縮放：{getattr(self, 'preview_zoom_factor', 1.0):.2f}x"
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
        self._invalidate_error_source_hit_index()
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
                        if item_id in self.preview_scene.source_geometry_items:
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
        elif getattr(self, "selected_review_item_key", ""):
            iid = self._tree_iid_for_review_item_key(
                self.selected_review_item_key
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

    def _build_review_state(self) -> dict[str, Any]:
        """Capture JSON-safe review inputs plus an optional diagnostics snapshot."""

        state = self.review_workflow.serialize_review_state(
            layer_roles=self._current_layer_roles(),
            import_mode=self.mode_var.get(),
        )
        self._sync_review_workflow_state()
        return state

    def _apply(self) -> None:
        from tkinter import messagebox

        if self.review_workflow.pending_mutation_disabled_reason():
            messagebox.showwarning(
                "尚有待排除來源",
                "請先套用或捨棄待排除來源",
                parent=self.window,
            )
            return
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
                "若繼續，求解器將使用原本正式工程線。\n\n"
                "確定不套用本次修改並繼續匯入嗎？",
                parent=self.window,
            ):
                return
        warning_count = sum(
            message.severity == "warning" for message in self.result.messages
        )
        unconfirmed_count = len(self._unconfirmed_formal_review_items())
        if warning_count or unconfirmed_count:
            reminders = []
            if warning_count:
                reminders.append(f"• 警告：{warning_count} 項")
            if unconfirmed_count:
                reminders.append(f"• 未人工確認構件：{unconfirmed_count} 個")
            if not messagebox.askyesno(
                "完成匯入前確認",
                "目前仍有：\n"
                + "\n".join(reminders)
                + "\n\n是否仍要完成匯入？",
                parent=self.window,
            ):
                return
        self.review_state = self._build_review_state()
        self.dialog_action = "complete"
        self._save_ui_state()
        self._close_waler_formalization()
        self.window.destroy()

    def _pause(self) -> None:
        """Return to Main without validation or ProjectDataModel mutation."""

        from tkinter import messagebox

        if self.review_workflow.pending_mutation_disabled_reason():
            messagebox.showwarning(
                "尚有待排除來源",
                "請先套用或捨棄待排除來源",
                parent=self.window,
            )
            return
        self.review_state = self._build_review_state()
        self.dialog_action = "pause"
        self._save_ui_state()
        self._close_waler_formalization()
        self.window.destroy()

    def _close_dialog(self) -> None:
        from tkinter import messagebox

        workflow = getattr(self, "review_workflow", None)
        if (
            workflow is not None
            and workflow.pending_mutation_disabled_reason()
        ):
            if not messagebox.askyesno(
                "捨棄待排除來源",
                "尚有待排除來源。是否捨棄待排除並關閉？",
                parent=self.window,
            ):
                return
            self.review_workflow.discard_pending_source_exclusions()
            self._sync_review_workflow_state()
        if self.allow_pause:
            self._pause()
        else:
            self._cancel()

    def _cancel(self) -> None:
        self.dialog_action = "cancel"
        self.review_state = {}
        self._save_ui_state()
        self._close_waler_formalization()
        self.window.destroy()
