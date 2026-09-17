import copy
import json
import logging
import math
import os
import shutil
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, scrolledtext, simpledialog, ttk

import ezdxf
from bracing_optimizer.algorithms import solver_search, support, wales

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
plt.rcParams["axes.unicode_minus"] = False
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from app_dependencies import AppDependencies
from bootstrap import build_dependencies, build_project_service
from bracing_optimizer.infrastructure.cad_builder import (
    POLL_INTERVAL_MS,
)
from bracing_optimizer.application.project_data import (
    DEFAULT_MATERIAL_SPECS,
    GEOMETRY_TABLES,
    REQUIRED_RC_SPEC,
    ProjectDataModel,
)
from bracing_optimizer.application.project_data import (
    TABLE_COLUMNS as PROJECT_TABLE_COLUMNS,
)
from bracing_optimizer.application.solver_input_builder import (
    InventoryLookup,
    SolverInputBuildError,
    UNLIMITED_INVENTORY_QTY,
)
from dxf_import import (
    CoordinateSystem,
    DXFImportDialog,
    DXFImportDialogOutcome,
    DXFImportError,
    _active_monitor_work_areas,
    fit_window_geometry_to_work_areas,
    review_state_matches_source,
    source_file_fingerprint,
)
from bracing_optimizer.application.waler_solver_guard import WalerSolverBusyGuard
from bracing_optimizer.presentation.cad_view_interaction import (
    CADViewInteractionController,
)
from bracing_optimizer.presentation.field_labels import build_table_column_labels
from bracing_optimizer.infrastructure.dxf_result_export import (
    DXFResultExportError,
    ExportPiece,
    MemberExportPlan,
    export_coordinate_system_from_import_state,
    export_results_to_dxf,
)
from bracing_optimizer.infrastructure.excel_result_export import (
    ExcelResultExportError,
)
from bracing_optimizer.infrastructure.project_persistence import (
    DxfStatus,
    DxfWorkflowStatus,
    PROJECT_SCHEMA_VERSION,
    ProjectPersistenceError,
    dxf_workflow_status_from_payload,
)
from bracing_optimizer.application.project_service import (
    RelinkDxfRequest,
    SaveProjectRequest,
)
from bracing_optimizer.application.plan_editing import SupportPlanEditing, WalerPlanEditing
from bracing_optimizer.application.project_results import (
    MaterialDetailBuildError,
    ProjectResultModel,
)
from bracing_optimizer.application.project_validation import ProjectDataValidator
from bracing_optimizer.presentation import (
    PreviewNavigationToolbar,
    SolverDialogThreadBridge,
    SupportSolverDialog,
    TextRedirector,
    WalerSelectionDialog,
    WalerGlobalSolverDialog,
    WalerSolverDialog,
    ZoningSelectionDialog,
    format_result_list,
    format_result_value,
    format_waler_score_breakdown,
)
from window_layout import configure_responsive_dialog


RESOURCE_DIR = Path(__file__).resolve().parent
APP_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else RESOURCE_DIR
)
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WalerGlobalApplyOutcome:
    """Distinguish data commit from best-effort UI refresh."""

    committed: bool
    refreshed: bool
    error: str = ""
    refresh_error: str = ""


def point_on_line_by_station(start_x, start_y, end_x, end_y, station):
    """
    根據起點、終點與沿線 station 距離，回傳該點的 X,Y 座標。
    station 是從起點沿著線段方向量測的距離，單位 mm。
    """
    dx = end_x - start_x
    dy = end_y - start_y
    length = math.hypot(dx, dy)
    if length <= 0:
        return None
    ratio = station / length
    x = start_x + ratio * dx
    y = start_y + ratio * dy
    return x, y


def load_ascii_art(code):
    code = str(code or "").strip()
    if not code:
        return None
    if code != Path(code).name or "/" in code or "\\" in code:
        return None

    art_path = RESOURCE_DIR / "picture" / f"{code}.txt"
    if not art_path.is_file():
        return None

    for encoding in ("utf-8", "utf-8-sig", "cp950"):
        try:
            return art_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return art_path.read_text(encoding="utf-8", errors="replace")


def calculate_ascii_art_font_size(line_count, max_width):
    font_size = 10
    if max_width > 800:
        font_size = 3
    elif max_width > 600:
        font_size = 4
    elif max_width > 450:
        font_size = 5
    elif max_width > 350:
        font_size = 6
    elif max_width > 250:
        font_size = 7
    elif max_width > 150:
        font_size = 8

    if line_count > 150:
        font_size -= 1
    if line_count > 250:
        font_size -= 1

    return max(3, font_size)


class SupportInputApp:
    WINDOW_TITLE = "開挖支撐系統幾何資料輸入介面"
    EXPORT_BASE_FIGSIZE = (16, 10)
    EXPORT_DPI = 100
    EXPORT_SCALE_OPTIONS = (100, 200, 400, 800)
    PREVIEW_SCROLL_DEBOUNCE_MS = 60
    TABLE_COLUMNS = PROJECT_TABLE_COLUMNS
    STRUT_BRACE_LENGTH_FIELDS = (
        ("FromBraceToWalerStartLen", "起點角撐長度(往圍令起點)"),
        ("FromBraceToWalerEndLen", "起點角撐長度(往圍令終點)"),
        ("ToBraceToWalerStartLen", "終點角撐長度(往圍令起點)"),
        ("ToBraceToWalerEndLen", "終點角撐長度(往圍令終點)"),
    )
    STRUT_SUMMARY_COLUMNS = (
        "No",
        "StrutID",
        "SharedLayoutGroup",
        "FromWaler",
        "ToWaler",
        "material_spec",
        "TargetJackRegion",
        "Zoning",
    )
    GEOMETRY_SUMMARY_COLUMNS = {
        "walers": ("No", "WalerID", "material_spec"),
        "braces": ("No", "BraceID", "FromWaler", "ToWaler"),
    }
    DXF_BINDING_FIELDS = {
        "walers": frozenset(
            ("WalerID", "StartX", "StartY", "EndX", "EndY")
        ),
        "struts": frozenset(
            (
                "StrutID",
                "FromWaler",
                "ToWaler",
                "StartX",
                "StartY",
                "EndX",
                "EndY",
            )
        ),
        "braces": frozenset(
            (
                "BraceID",
                "FromWaler",
                "ToWaler",
                "StartX",
                "StartY",
                "EndX",
                "EndY",
            )
        ),
    }
    DXF_BINDING_STALE_KEY = "project_binding_stale"
    DXF_BINDING_STALE_REASON_KEY = "project_binding_stale_reason"

    def _current_dxf_workflow_status(self):
        raw = getattr(self, "dxf_workflow_status", None)
        if isinstance(raw, DxfWorkflowStatus):
            return raw
        if raw is not None:
            try:
                return DxfWorkflowStatus(str(raw).strip().upper())
            except ValueError:
                pass
        return (
            DxfWorkflowStatus.COMPLETED
            if isinstance(getattr(self, "dxf_last_import_debug", None), Mapping)
            else DxfWorkflowStatus.NONE
        )

    def _transition_dxf_workflow(self, target):
        target = (
            target
            if isinstance(target, DxfWorkflowStatus)
            else DxfWorkflowStatus(str(target).strip().upper())
        )
        current = self._current_dxf_workflow_status()
        legal = {
            DxfWorkflowStatus.NONE: {
                DxfWorkflowStatus.NONE,
                DxfWorkflowStatus.REVIEW,
            },
            DxfWorkflowStatus.REVIEW: {
                DxfWorkflowStatus.REVIEW,
                DxfWorkflowStatus.COMPLETED,
            },
            DxfWorkflowStatus.COMPLETED: {DxfWorkflowStatus.COMPLETED},
        }
        if target not in legal[current]:
            raise RuntimeError(
                f"不允許的 DXF workflow transition：{current.value} → {target.value}"
            )
        self.dxf_workflow_status = target
        self._refresh_dxf_workflow_ui()

    def _project_display_name(self):
        path = getattr(self, "current_project_path", None)
        if path is None:
            return "未命名專案"
        path = Path(path)
        return path.parent.name if path.name == "project.json" else path.stem

    def _project_is_saved(self):
        return (
            getattr(self, "current_project_path", None) is not None
            and not getattr(self, "project_dirty", False)
        )

    def _update_window_title(self):
        dirty = " *" if getattr(self, "project_dirty", False) else ""
        title = f"{self.WINDOW_TITLE} - {self._project_display_name()}{dirty}"
        root = getattr(self, "root", None)
        if root is not None and hasattr(root, "title"):
            root.title(title)
        self._refresh_project_status_display()

    def _mark_project_dirty(self, reason=""):
        self.project_dirty = True
        if reason:
            self.project_dirty_reason = str(reason)
        self._update_window_title()

    def _clear_project_dirty(self):
        self.project_dirty = False
        self.project_dirty_reason = ""
        self._update_window_title()

    def _ensure_project_services(self):
        service = getattr(self, "project_service", None)
        if service is not None:
            if not hasattr(self, "dxf_asset_manager"):
                self.dxf_asset_manager = service.dxf_asset_manager
            if not hasattr(self, "dxf_compatibility_checker"):
                self.dxf_compatibility_checker = (
                    service.dxf_compatibility_checker
                )
            return self.dxf_asset_manager

        manager = getattr(self, "dxf_asset_manager", None)
        checker = getattr(self, "dxf_compatibility_checker", None)
        service = build_project_service(manager, checker)
        self.project_service = service
        self.dxf_asset_manager = service.dxf_asset_manager
        self.dxf_compatibility_checker = service.dxf_compatibility_checker
        return self.dxf_asset_manager

    def _ensure_project_service(self):
        self._ensure_project_services()
        service = getattr(self, "project_service", None)
        if (
            service is None
            or service.dxf_asset_manager is not self.dxf_asset_manager
            or service.dxf_compatibility_checker
            is not self.dxf_compatibility_checker
        ):
            service = build_project_service(
                self.dxf_asset_manager,
                self.dxf_compatibility_checker,
            )
            self.project_service = service
        return service

    def _ensure_project_data(self):
        model = self.__dict__.get("project_data")
        if model is None:
            model = ProjectDataModel()
            self.project_data = model
        return model

    def _ensure_project_results(self):
        model = self.__dict__.get("_project_results")
        if model is None:
            model = ProjectResultModel()
            self._project_results = model
        return model

    def _ensure_solver_input_builders(self):
        try:
            return self.support_input_builder, self.waler_input_builder
        except AttributeError as exc:
            raise RuntimeError("Solver Input Builder 尚未由 bootstrap 注入。") from exc

    def _ensure_waler_solver_guard(self):
        guard = getattr(self, "waler_solver_guard", None)
        if guard is None:
            guard = WalerSolverBusyGuard()
            self.waler_solver_guard = guard
        return guard

    def _show_waler_solver_busy(self, workflow):
        LOGGER.warning("%s Waler blocked by busy guard", workflow)
        message = "目前已有圍令計算正在執行，請等待完成後再試。"
        messagebox.showwarning("圍令計算中", message, parent=self.root)
        self.show_result(message)

    def _apply_dependencies(self, dependencies: AppDependencies) -> None:
        """Attach one dependency graph without constructing implementations."""

        self.dependencies = dependencies
        self.inventory_repository = dependencies.inventory_repository
        self.project_service = dependencies.project_service
        # Compatibility aliases remain while the last status-only calls move
        # behind ProjectService.  They always point at the same injected graph.
        self.dxf_asset_manager = self.project_service.dxf_asset_manager
        self.dxf_compatibility_checker = (
            self.project_service.dxf_compatibility_checker
        )
        self.support_input_builder = dependencies.support_input_builder
        self.waler_input_builder = dependencies.waler_input_builder
        self.cad_event_watcher = dependencies.cad_event_watcher
        self.cad_event_mapper = dependencies.cad_event_mapper
        self.excel_result_exporter = dependencies.excel_result_exporter
        self.make_waler_optimizer = dependencies.make_waler_optimizer
        self.make_waler_global_optimizer = dependencies.make_waler_global_optimizer
        self.waler_solver_guard = dependencies.waler_solver_guard
        self.make_support_optimizer = dependencies.make_support_optimizer
        self.default_inventory_path = Path(dependencies.default_inventory_path)
        self.data_dir = self.default_inventory_path.parent
        self.project_cases_dir = Path(dependencies.project_cases_dir)

    @property
    def walers(self):
        return self._ensure_project_data().walers

    @walers.setter
    def walers(self, rows):
        self._ensure_project_data().replace_table("walers", rows)

    @property
    def struts(self):
        return self._ensure_project_data().struts

    @struts.setter
    def struts(self, rows):
        self._ensure_project_data().replace_table("struts", rows)

    @property
    def braces(self):
        return self._ensure_project_data().braces

    @braces.setter
    def braces(self, rows):
        self._ensure_project_data().replace_table("braces", rows)

    @property
    def inventory(self):
        return self._ensure_project_data().inventory

    @inventory.setter
    def inventory(self, rows):
        self._ensure_project_data().replace_table("inventory", rows)

    @property
    def material_specs(self):
        return self._ensure_project_data().material_specs

    @material_specs.setter
    def material_specs(self, rows):
        self._ensure_project_data().replace_table("material_specs", rows)

    @property
    def result_items(self):
        return self._ensure_project_results().result_items

    @result_items.setter
    def result_items(self, items):
        self._ensure_project_results().result_items = items

    @property
    def project_result(self):
        return self._ensure_project_results().persisted_payload

    @project_result.setter
    def project_result(self, payload):
        self._ensure_project_results().persisted_payload = payload

    @property
    def last_calculated_time(self):
        return self._ensure_project_results().last_calculated_time

    @last_calculated_time.setter
    def last_calculated_time(self, value):
        self._ensure_project_results().last_calculated_time = value

    def __init__(
        self,
        root,
        dependencies: AppDependencies | None = None,
    ):
        self.root = root
        self.root.title(self.WINDOW_TITLE)
        self.main_ui_state = self._load_main_ui_state()
        self._last_normal_geometry = self._restore_main_window_geometry()
        primary_area = self._main_work_areas[0]
        self.root.minsize(
            min(900, primary_area[2] - primary_area[0]),
            min(600, primary_area[3] - primary_area[1]),
        )
        self.root.resizable(True, True)
        self.root.bind("<Configure>", self._on_main_window_configure)

        dependencies = dependencies or build_dependencies(
            resource_dir=RESOURCE_DIR,
            app_dir=APP_DIR,
        )
        self.project_data = ProjectDataModel()
        self._project_results = ProjectResultModel()
        self._apply_dependencies(dependencies)
        self.current_project_path = None
        self.project_dirty = False
        self.project_dirty_reason = ""
        self.dxf_asset = None
        self.dxf_asset_status_report = self.project_service.inspect_dxf_state(
            None, None, None
        )
        self.last_dxf_compatibility_report = None
        self.solver_memory = {}
        self.support_candidate_cache = {}
        self.cad_import_enabled = True
        self.dxf_dialog_active = False
        self.dxf_import_status = "尚未執行 DXF 批次匯入"
        self.dxf_import_error = ""
        self.cad_import_status = "等待 CAD 事件"
        self.cad_last_event = None
        self.cad_last_error = None
        self.last_cad_validation_report = None
        self.dxf_last_import_debug = None
        self.dxf_workflow_status = DxfWorkflowStatus.NONE
        self.dxf_review_session = None
        self._cad_poll_after_id = None
        self.project_cases_dir.mkdir(exist_ok=True)
        self.inventory = self._load_default_inventory()

        self.table_columns = {
            table_name: list(columns)
            for table_name, columns in self.TABLE_COLUMNS.items()
        }

        self.table_tab_labels = {
            "walers": "圍令",
            "struts": "支撐",
            "braces": "斜撐",
            "inventory": "機料庫存",
            "material_specs": "材料規格",
        }
        self.workspace_tab_labels = {
            "engineering": "工程配置",
            "materials": "材料設定",
            "analysis": "分析結果",
        }
        self.settings_tab_label = self.workspace_tab_labels["materials"]

        self.table_column_labels = build_table_column_labels()

        self.numeric_columns = {
            "walers": ["StartX", "StartY", "EndX", "EndY"],
            "struts": [
                "StartX",
                "StartY",
                "EndX",
                "EndY",
                "FromBraceToWalerStartLen",
                "FromBraceToWalerEndLen",
                "ToBraceToWalerStartLen",
                "ToBraceToWalerEndLen",
                "TargetJackRegion",
            ],
            "braces": ["StartX", "StartY", "EndX", "EndY"],
            "inventory": ["Length", "Qty"],
            "material_specs": [],
        }

        self.treeviews = {}
        self.current_table = "walers"
        self.editing_entry = None

        self._build_ui()
        self._load_initial_data()
        self.root.after(300, self._restore_main_paned_position)
        if bool(self.main_ui_state.get("maximized", False)):
            self.root.after_idle(lambda: self._set_main_window_maximized(True))
        self.update_preview()
        self._schedule_cad_event_poll()
        self.root.protocol("WM_DELETE_WINDOW", self._on_main_window_close)

    def _build_ui(self):
        self._build_project_menu_and_toolbar()

        self.main_paned = ttk.PanedWindow(self.root, orient="horizontal")
        self.main_paned.pack(fill="both", expand=True)

        self.left_frame = ttk.Frame(self.main_paned, width=800)
        self.right_frame = ttk.Frame(self.main_paned, width=800)
        self.main_paned.add(self.left_frame, weight=1)
        self.main_paned.add(self.right_frame, weight=1)

        self.notebook = ttk.Notebook(self.left_frame)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.engineering_workspace = ttk.Frame(self.notebook)
        self.notebook.add(
            self.engineering_workspace,
            text=self.workspace_tab_labels["engineering"],
        )
        self.engineering_notebook = ttk.Notebook(self.engineering_workspace)
        self.engineering_notebook.pack(fill="both", expand=True, padx=4, pady=4)
        self.engineering_notebook.bind(
            "<<NotebookTabChanged>>",
            self._on_engineering_tab_changed,
        )
        self._create_strut_tab(parent_notebook=self.engineering_notebook)
        self._create_geometry_table_tab(
            "walers",
            self.table_tab_labels["walers"],
            parent_notebook=self.engineering_notebook,
        )
        self._create_geometry_table_tab(
            "braces",
            self.table_tab_labels["braces"],
            parent_notebook=self.engineering_notebook,
        )
        self._create_dxf_import_tab(parent_notebook=self.engineering_notebook)
        self._create_cad_import_tab(parent_notebook=self.engineering_notebook)

        self.materials_workspace = ttk.Frame(self.notebook)
        self.notebook.add(
            self.materials_workspace,
            text=self.workspace_tab_labels["materials"],
        )
        self.materials_notebook = ttk.Notebook(self.materials_workspace)
        self.materials_notebook.pack(fill="both", expand=True, padx=4, pady=4)
        self.settings_notebook = self.materials_notebook
        self._create_table_tab(
            "material_specs",
            self.table_tab_labels["material_specs"],
            parent_notebook=self.materials_notebook,
        )
        self._create_table_tab(
            "inventory",
            self.table_tab_labels["inventory"],
            parent_notebook=self.materials_notebook,
        )
        self.materials_notebook.bind(
            "<<NotebookTabChanged>>",
            self._on_settings_tab_changed,
        )

        self.analysis_workspace = ttk.Frame(self.notebook)
        self.results_tab = self.analysis_workspace
        self.notebook.add(
            self.analysis_workspace,
            text=self.workspace_tab_labels["analysis"],
        )
        self._create_results_tab(parent=self.analysis_workspace)

        self.context_toolbar = ttk.Frame(self.root)
        # Reserve the action row before the expanding workspace is laid out.
        # Otherwise the workspace's requested height can push these controls
        # below the visible client area on 1024x768 projectors.
        self.context_toolbar.pack(
            side="bottom",
            fill="x",
            padx=8,
            pady=4,
            before=self.main_paned,
        )

        self.context_toolbar_context_var = tk.StringVar(value="目前區域：圍令")
        ttk.Label(
            self.context_toolbar,
            textvariable=self.context_toolbar_context_var,
            font=("Microsoft JhengHei", 9, "bold"),
            foreground="#37474f",
        ).pack(side="left", padx=(4, 10))
        ttk.Separator(self.context_toolbar, orient="vertical").pack(
            side="left",
            fill="y",
            padx=(0, 6),
        )

        self.context_toolbar_buttons = {}

        def add_context_button(name, text, command):
            button = ttk.Button(self.context_toolbar, text=text, command=command)
            self.context_toolbar_buttons[name] = button
            return button

        add_context_button("add", "新增列", self.add_row)
        add_context_button("delete", "刪除選取列", self.delete_row)
        add_context_button("up", "上移", lambda: self._move_current_table_row(-1))
        add_context_button("down", "下移", lambda: self._move_current_table_row(1))
        add_context_button("validate", "驗證資料", self.validate_data)
        add_context_button("redraw", "更新圖面", self.update_preview)
        add_context_button("waler_solver", "執行圍令配置", self._open_waler_solver)
        add_context_button(
            "waler_global_solver",
            "全部圍令最佳化",
            self._open_waler_global_solver,
        )
        self.run_support_solver_button = ttk.Button(
            self.context_toolbar,
            text="支撐配置",
            command=self._open_support_solver,
        )
        self.context_toolbar_buttons["support_solver"] = self.run_support_solver_button

        self._build_preview(self.right_frame)
        self._update_context_toolbar()

    def _build_execution_messages(self, parent):
        self.execution_message_frame = ttk.LabelFrame(parent, text="Solver 診斷與執行訊息")
        self.execution_message_frame.pack(fill="both", expand=True, padx=8, pady=8)

        message_header = ttk.Frame(self.execution_message_frame)
        message_header.pack(fill="x", padx=4, pady=4)
        self.execution_message_summary_var = tk.StringVar(value="狀態：尚未執行計算")
        ttk.Label(
            message_header,
            textvariable=self.execution_message_summary_var,
        ).pack(side="left", fill="x", expand=True)
        self.execution_message_expanded = True
        self.execution_message_toggle_button = ttk.Button(
            message_header,
            text="隱藏詳細訊息 ▲",
            command=self._toggle_execution_messages,
        )
        self.execution_message_toggle_button.pack(side="right")

        self.execution_message_body = ttk.Frame(self.execution_message_frame)
        self.execution_message_body.pack(fill="both", expand=True)

        self.ascii_art_code_var = tk.StringVar()
        self.ascii_art_entry = tk.Entry(
            self.execution_message_body,
            textvariable=self.ascii_art_code_var,
            width=7,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            insertwidth=1,
            bg="white",
            fg="black",
            insertbackground="black",
            selectbackground="#d9e8ff",
            selectforeground="black",
        )
        self.ascii_art_entry.place(relx=1.0, x=-42, y=14, anchor="ne")
        self.ascii_art_entry.bind("<Return>", self._on_ascii_art_code_enter)
        self.ascii_art_entry.bind("<FocusIn>", self._on_ascii_art_entry_focus_in)
        self.ascii_art_entry.bind("<FocusOut>", self._on_ascii_art_entry_focus_out)

        self.result_text = scrolledtext.ScrolledText(
            self.execution_message_body,
            height=10,
            wrap="none",
            state="disabled",
            font=("Consolas", 10),
        )
        self.result_text.pack(fill="both", expand=True, padx=4, pady=4)
        self.ascii_art_entry.lift()

    def _create_table_tab(self, table_name, tab_text, parent_notebook=None):
        notebook = parent_notebook or self.notebook
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=tab_text)
        if not hasattr(self, "table_tabs"):
            self.table_tabs = {}
        self.table_tabs[table_name] = frame

        container = ttk.Frame(frame)
        container.pack(fill="both", expand=True, padx=4, pady=4)

        columns = ("No", *self.table_columns[table_name])
        tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="browse")
        tree.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        x_scroll = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        ttk.Label(
            container,
            text="提示：雙擊儲存格可編輯；新增、刪除與檢查請使用下方的目前區域工具列。",
            foreground="#546e7a",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 0))

        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        for col in columns:
            tree.heading(col, text=self.table_column_labels.get(table_name, {}).get(col, col))
            if col == "No":
                tree.column(col, width=55, minwidth=50, anchor="center", stretch=False)
            elif col in ("BeamPositions", "ColumnPositions"):
                tree.column(col, width=150, minwidth=130, anchor="center")
            else:
                tree.column(col, width=90, anchor="center")

        tree.tag_configure("error", background="#ffdddd")
        tree.bind("<Double-1>", self._on_tree_double_click)
        if table_name in ("walers", "braces"):
            tree.bind(
                "<<TreeviewSelect>>",
                lambda _event, name=table_name: self._on_geometry_tree_select(
                    name
                ),
            )
        self.treeviews[table_name] = tree

    def _create_geometry_table_tab(
        self,
        table_name,
        tab_text,
        parent_notebook=None,
    ):
        """Create a consistent summary-and-detail editor for line members."""

        notebook = parent_notebook or self.notebook
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=tab_text)
        if not hasattr(self, "table_tabs"):
            self.table_tabs = {}
        self.table_tabs[table_name] = frame

        paned = ttk.PanedWindow(frame, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=4, pady=4)
        list_frame = ttk.Frame(paned)
        detail_outer = ttk.LabelFrame(paned, text=f"{tab_text}詳細資訊")
        paned.add(list_frame, weight=3)
        paned.add(detail_outer, weight=2)

        columns = self.GEOMETRY_SUMMARY_COLUMNS[table_name]
        tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=y_scroll.set)
        ttk.Label(
            list_frame,
            text="提示：選取列可在右側編輯；也可雙擊摘要欄位快速修改。",
            foreground="#546e7a",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5, 0))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        widths = {
            "No": (52, False),
            "WalerID": (120, True),
            "BraceID": (120, True),
            "FromWaler": (110, True),
            "ToWaler": (110, True),
            "material_spec": (150, True),
        }
        for column in columns:
            label = self.table_column_labels[table_name].get(column, column)
            width, stretch = widths.get(column, (100, True))
            tree.heading(column, text=label)
            tree.column(
                column,
                width=width,
                minwidth=max(45, width - 20),
                anchor="center",
                stretch=stretch,
            )
        tree.tag_configure("error", background="#ffdddd")
        tree.bind("<Double-1>", self._on_tree_double_click)
        tree.bind(
            "<<TreeviewSelect>>",
            lambda _event, name=table_name: self._on_geometry_tree_select(name),
        )
        self.treeviews[table_name] = tree

        detail_frame = ttk.Frame(detail_outer, padding=(8, 6))
        detail_frame.pack(fill="both", expand=True)
        detail_frame.columnconfigure(1, weight=1)

        if not hasattr(self, "geometry_detail_vars"):
            self.geometry_detail_vars = {}
            self.geometry_detail_widgets = {}
            self.geometry_detail_status_vars = {}
            self.geometry_detail_status_labels = {}
            self.geometry_detail_headers = {}
            self.selected_geometry_indices = {}
            self._loading_geometry_detail = False

        fields = (
            (
                ("WalerID", "entry"),
                ("material_spec", "material"),
                ("StartX", "entry"),
                ("StartY", "entry"),
                ("EndX", "entry"),
                ("EndY", "entry"),
                ("Remark", "entry"),
            )
            if table_name == "walers"
            else (
                ("BraceID", "entry"),
                ("FromWaler", "waler"),
                ("ToWaler", "waler"),
                ("StartX", "entry"),
                ("StartY", "entry"),
                ("EndX", "entry"),
                ("EndY", "entry"),
            )
        )
        header_var = tk.StringVar(value=f"請先從左側列表選取一筆{tab_text}。")
        self.geometry_detail_headers[table_name] = header_var
        ttk.Label(
            detail_frame,
            textvariable=header_var,
            foreground="#555555",
            wraplength=360,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        detail_vars = {}
        detail_widgets = {}
        for row_index, (column, kind) in enumerate(fields, start=1):
            ttk.Label(
                detail_frame,
                text=self._field_label(table_name, column),
            ).grid(row=row_index, column=0, sticky="e", padx=(0, 6), pady=4)
            variable = tk.StringVar()
            if kind in ("material", "waler"):
                widget = ttk.Combobox(
                    detail_frame,
                    textvariable=variable,
                    state="readonly",
                )
            else:
                widget = ttk.Entry(detail_frame, textvariable=variable)
            widget.grid(row=row_index, column=1, sticky="ew", pady=4)
            widget.bind(
                "<Return>",
                lambda _event, name=table_name, field=column: self._commit_geometry_detail_field(name, field),
            )
            widget.bind(
                "<FocusOut>",
                lambda _event, name=table_name, field=column: self._commit_geometry_detail_field(name, field),
            )
            widget.bind(
                "<Escape>",
                lambda _event, name=table_name, field=column: self._reload_geometry_detail_field(name, field),
            )
            if isinstance(widget, ttk.Combobox):
                widget.bind(
                    "<<ComboboxSelected>>",
                    lambda _event, name=table_name, field=column: self._commit_geometry_detail_field(name, field),
                )
            detail_vars[column] = variable
            detail_widgets[column] = widget

        status_var = tk.StringVar(value="")
        status_label = ttk.Label(
            detail_frame,
            textvariable=status_var,
            foreground="#b71c1c",
            wraplength=360,
            justify="left",
        )
        status_label.grid(
            row=len(fields) + 1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 3),
        )
        ttk.Label(
            detail_frame,
            text="輸入後按 Enter 或移開游標即可儲存；按 Esc 還原目前欄位。",
            foreground="#555555",
            wraplength=360,
            justify="left",
        ).grid(row=len(fields) + 2, column=0, columnspan=2, sticky="ew")

        self.geometry_detail_vars[table_name] = detail_vars
        self.geometry_detail_widgets[table_name] = detail_widgets
        self.geometry_detail_status_vars[table_name] = status_var
        self.geometry_detail_status_labels[table_name] = status_label
        self.selected_geometry_indices[table_name] = None
        self._set_geometry_detail_enabled(table_name, False)

    def _create_strut_tab(self, parent_notebook=None):
        """Create the compact strut list and its single-field edit panel."""

        notebook = parent_notebook or self.notebook
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=self.table_tab_labels["struts"])
        if not hasattr(self, "table_tabs"):
            self.table_tabs = {}
        self.table_tabs["struts"] = frame

        paned = ttk.PanedWindow(frame, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=4, pady=4)

        list_frame = ttk.Frame(paned)
        detail_outer = ttk.LabelFrame(paned, text="支撐詳細資訊")
        paned.add(list_frame, weight=3)
        paned.add(detail_outer, weight=2)
        self.strut_content_paned = paned

        columns = self.STRUT_SUMMARY_COLUMNS
        tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=y_scroll.set)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        widths = {
            "No": (52, False),
            "StrutID": (82, True),
            "SharedLayoutGroup": (82, True),
            "FromWaler": (82, True),
            "ToWaler": (82, True),
            "material_spec": (110, True),
            "TargetJackRegion": (86, False),
            "Zoning": (72, True),
        }
        for column in columns:
            label = self.table_column_labels["struts"].get(column, column)
            if column == "No":
                label = "順序"
            width, stretch = widths[column]
            tree.heading(column, text=label)
            tree.column(
                column,
                width=width,
                minwidth=max(45, width - 18),
                anchor="center",
                stretch=stretch,
            )
        tree.tag_configure("error", background="#ffdddd")
        tree.bind("<Double-1>", self._on_tree_double_click)
        tree.bind("<<TreeviewSelect>>", self._on_strut_tree_select)
        self.treeviews["struts"] = tree

        detail_canvas = tk.Canvas(detail_outer, highlightthickness=0)
        detail_scroll = ttk.Scrollbar(
            detail_outer,
            orient="vertical",
            command=detail_canvas.yview,
        )
        detail_canvas.configure(yscrollcommand=detail_scroll.set)
        detail_canvas.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

        detail_frame = ttk.Frame(detail_canvas, padding=(6, 4))
        detail_window = detail_canvas.create_window(
            (0, 0),
            window=detail_frame,
            anchor="nw",
        )
        detail_frame.bind(
            "<Configure>",
            lambda _event: detail_canvas.configure(
                scrollregion=detail_canvas.bbox("all")
            ),
        )
        detail_canvas.bind(
            "<Configure>",
            lambda event: detail_canvas.itemconfigure(
                detail_window,
                width=event.width,
            ),
        )

        self.strut_detail_vars = {}
        self.strut_detail_widgets = {}
        self.selected_strut_index = None
        self._loading_strut_detail = False

        self.strut_detail_empty_var = tk.StringVar(
            value="請先從左側列表選取一支支撐。"
        )
        ttk.Label(
            detail_frame,
            textvariable=self.strut_detail_empty_var,
            foreground="#555555",
            wraplength=330,
            justify="left",
        ).pack(fill="x", pady=(0, 6))

        def add_section(title, fields):
            section = ttk.LabelFrame(detail_frame, text=title)
            section.pack(fill="x", pady=(0, 7))
            section.columnconfigure(1, weight=1)
            for row_index, (column, label, kind) in enumerate(fields):
                ttk.Label(section, text=label).grid(
                    row=row_index,
                    column=0,
                    sticky="e",
                    padx=(7, 5),
                    pady=3,
                )
                variable = tk.StringVar()
                self.strut_detail_vars[column] = variable
                if kind == "material":
                    widget = ttk.Combobox(
                        section,
                        textvariable=variable,
                        state="readonly",
                    )
                elif kind == "waler":
                    widget = ttk.Combobox(
                        section,
                        textvariable=variable,
                        state="readonly",
                    )
                elif kind == "jack":
                    widget = ttk.Spinbox(
                        section,
                        from_=1,
                        to=99,
                        textvariable=variable,
                    )
                else:
                    widget = ttk.Entry(section, textvariable=variable)
                widget.grid(
                    row=row_index,
                    column=1,
                    sticky="ew",
                    padx=(0, 7),
                    pady=3,
                )
                widget.bind(
                    "<Return>",
                    lambda _event, field=column: self._commit_strut_detail_field(field),
                )
                widget.bind(
                    "<FocusOut>",
                    lambda _event, field=column: self._commit_strut_detail_field(field),
                )
                widget.bind(
                    "<Escape>",
                    lambda _event, field=column: self._reload_strut_detail_field(field),
                )
                if isinstance(widget, ttk.Combobox):
                    widget.bind(
                        "<<ComboboxSelected>>",
                        lambda _event, field=column: self._commit_strut_detail_field(field),
                    )
                self.strut_detail_widgets[column] = widget
            return section

        add_section(
            "基本資訊",
            (
                ("StrutID", "支撐編號", "entry"),
                ("SharedLayoutGroup", "雙路共用配置群組", "entry"),
                ("material_spec", "材料規格", "material"),
                ("TargetJackRegion", "目標千斤頂區域", "jack"),
                ("Zoning", "分區", "entry"),
            ),
        )
        geometry = add_section(
            "幾何資訊",
            (
                ("FromWaler", "起點圍令", "waler"),
                ("ToWaler", "終點圍令", "waler"),
                ("StartX", "起點 X", "entry"),
                ("StartY", "起點 Y", "entry"),
                ("EndX", "終點 X", "entry"),
                ("EndY", "終點 Y", "entry"),
            ),
        )
        length_row = len(("FromWaler", "ToWaler", "StartX", "StartY", "EndX", "EndY"))
        ttk.Label(geometry, text="支撐長度").grid(
            row=length_row,
            column=0,
            sticky="e",
            padx=(7, 5),
            pady=3,
        )
        self.strut_length_var = tk.StringVar(value="—")
        ttk.Label(geometry, textvariable=self.strut_length_var).grid(
            row=length_row,
            column=1,
            sticky="w",
            padx=(0, 7),
            pady=3,
        )
        add_section(
            "構件資訊",
            (
                ("BeamPositions", "托梁位置 (mm)", "entry"),
                ("ColumnPositions", "中間柱位置 (mm)", "entry"),
                ("AssociatedBeamIDs", "關聯托梁", "entry"),
                ("AssociatedColumnIDs", "關聯中間柱", "entry"),
            ),
        )
        add_section(
            "角撐資訊",
            tuple(
                (field, label, "entry")
                for field, label in self.STRUT_BRACE_LENGTH_FIELDS
            ),
        )

        self.strut_detail_status_var = tk.StringVar(value="")
        self.strut_detail_status_label = ttk.Label(
            detail_frame,
            textvariable=self.strut_detail_status_var,
            foreground="#b71c1c",
            wraplength=330,
            justify="left",
        )
        self.strut_detail_status_label.pack(fill="x", pady=(0, 5))
        ttk.Label(
            detail_frame,
            text="每個欄位在按 Enter、選擇完成或離開欄位時立即儲存；按 Esc 可還原目前欄位。",
            foreground="#555555",
            wraplength=330,
            justify="left",
        ).pack(fill="x")
        self._set_strut_detail_enabled(False)

    def _set_strut_detail_enabled(self, enabled):
        for column, widget in getattr(self, "strut_detail_widgets", {}).items():
            if not enabled:
                widget.configure(state="disabled")
            elif column in ("material_spec", "FromWaler", "ToWaler"):
                widget.configure(state="readonly")
            else:
                widget.configure(state="normal")

    def _on_strut_tree_select(self, _event=None):
        tree = self.treeviews.get("struts")
        if tree is None:
            return
        selection = tree.selection()
        index = self._item_id_to_index(selection[0]) if selection else None
        previous_index = getattr(self, "selected_strut_index", None)
        if index != previous_index and previous_index is not None:
            focused = tree.focus_get()
            for column, widget in self.strut_detail_widgets.items():
                if focused is widget:
                    self._commit_strut_detail_field(column)
                    break
        if index is None or not (0 <= index < len(self.struts)):
            self.selected_strut_index = None
            self._set_strut_detail_enabled(False)
            self.strut_detail_empty_var.set("請先從左側列表選取一支支撐。")
            self.strut_length_var.set("—")
            return
        self._load_strut_detail(index)
        self._sync_preview_to_strut_selection(index)

    def _sync_preview_to_strut_selection(self, index):
        self._sync_preview_to_geometry_selection("struts", "strut", index)

    def _on_geometry_tree_select(self, table_name):
        tree = self.treeviews.get(table_name)
        if tree is None:
            return
        selection = tree.selection()
        index = self._item_id_to_index(selection[0]) if selection else None
        rows = getattr(self, table_name, None)
        has_detail = table_name in getattr(self, "geometry_detail_widgets", {})
        invalid_index = index is None or (
            has_detail and rows is not None and not (0 <= index < len(rows))
        )
        if invalid_index:
            if table_name in getattr(self, "geometry_detail_widgets", {}):
                self.selected_geometry_indices[table_name] = None
                self._set_geometry_detail_enabled(table_name, False)
                self.geometry_detail_headers[table_name].set(
                    f"請先從左側列表選取一筆{self._table_label(table_name)}。"
                )
            return
        if rows is not None and has_detail:
            self._load_geometry_detail(table_name, index)
        kind = {
            "walers": "waler",
            "struts": "strut",
            "braces": "brace",
        }.get(table_name)
        if kind is not None:
            self._sync_preview_to_geometry_selection(table_name, kind, index)

    def _set_geometry_detail_enabled(self, table_name, enabled):
        for column, widget in self.geometry_detail_widgets.get(table_name, {}).items():
            if not enabled:
                widget.configure(state="disabled")
            elif column in ("material_spec", "FromWaler", "ToWaler"):
                widget.configure(state="readonly")
            else:
                widget.configure(state="normal")

    def _load_geometry_detail(self, table_name, index):
        rows = getattr(self, table_name, ())
        if not (0 <= index < len(rows)):
            return
        row = rows[index]
        self.selected_geometry_indices[table_name] = index
        self._loading_geometry_detail = True
        try:
            widgets = self.geometry_detail_widgets[table_name]
            if table_name == "walers":
                material_options = tuple(self._material_spec_options("圍令"))
                current = str(row.get("material_spec", "") or "").strip()
                if current and current not in material_options:
                    material_options = (*material_options, current)
                widgets["material_spec"].configure(values=("", *material_options))
            elif table_name == "braces":
                waler_ids = tuple(
                    str(item.get("WalerID", "") or "").strip()
                    for item in self.walers
                    if str(item.get("WalerID", "") or "").strip()
                )
                for column in ("FromWaler", "ToWaler"):
                    current = str(row.get(column, "") or "").strip()
                    choices = waler_ids
                    if current and current not in choices:
                        choices = (*choices, current)
                    widgets[column].configure(values=("", *choices))
            for column, variable in self.geometry_detail_vars[table_name].items():
                variable.set(self._format_display_value(row.get(column, "")))
        finally:
            self._loading_geometry_detail = False

        identifier_column = "WalerID" if table_name == "walers" else "BraceID"
        identifier = str(row.get(identifier_column, "") or "").strip()
        if not identifier:
            identifier = f"未命名{self._table_label(table_name)}"
        self.geometry_detail_headers[table_name].set(
            f"{identifier}（第 {index + 1} 列）"
        )
        self.geometry_detail_status_vars[table_name].set("")
        self.geometry_detail_status_labels[table_name].configure(
            foreground="#2e7d32"
        )
        self._set_geometry_detail_enabled(table_name, True)

    def _reload_geometry_detail_field(self, table_name, column):
        index = self.selected_geometry_indices.get(table_name)
        rows = getattr(self, table_name, ())
        if index is None or not (0 <= index < len(rows)):
            return "break"
        self._loading_geometry_detail = True
        try:
            self.geometry_detail_vars[table_name][column].set(
                self._format_display_value(rows[index].get(column, ""))
            )
        finally:
            self._loading_geometry_detail = False
        self.geometry_detail_status_vars[table_name].set("")
        return "break"

    def _validate_geometry_detail_value(
        self,
        table_name,
        index,
        column,
        raw_value,
        value,
    ):
        identifier_column = "WalerID" if table_name == "walers" else "BraceID"
        if column == identifier_column:
            if not raw_value:
                return f"{self._field_label(table_name, column)}不可空白。"
            duplicate = any(
                row_index != index
                and str(row.get(identifier_column, "") or "").strip() == raw_value
                for row_index, row in enumerate(getattr(self, table_name))
            )
            if duplicate:
                return f"{self._field_label(table_name, column)}「{raw_value}」已存在。"
        if column in self.numeric_columns.get(table_name, ()):
            if raw_value == "" or isinstance(value, str):
                return f"{self._field_label(table_name, column)}必須是數字。"
            if not math.isfinite(float(value)):
                return f"{self._field_label(table_name, column)}必須是有限數字。"
        if table_name == "braces" and column in ("FromWaler", "ToWaler") and raw_value:
            other = "ToWaler" if column == "FromWaler" else "FromWaler"
            if raw_value == str(self.braces[index].get(other, "") or "").strip():
                return "起點圍令與終點圍令不可相同。"
        return ""

    def _commit_geometry_detail_field(self, table_name, column):
        if getattr(self, "_loading_geometry_detail", False):
            return
        index = self.selected_geometry_indices.get(table_name)
        rows = getattr(self, table_name, ())
        if index is None or not (0 <= index < len(rows)):
            return
        raw_value = self.geometry_detail_vars[table_name][column].get().strip()
        changed, value, error = self._commit_project_field_edit(
            table_name,
            index,
            column,
            raw_value,
        )
        status_label = self.geometry_detail_status_labels[table_name]
        status_var = self.geometry_detail_status_vars[table_name]
        if error:
            status_label.configure(foreground="#b71c1c")
            status_var.set(error + " 已保留原值；按 Esc 可還原欄位。")
            return
        if not changed:
            status_var.set("")
            return

        tree = self.treeviews[table_name]
        row_id = f"{table_name}_{index}"
        if row_id in tree.get_children() and column in tree["columns"]:
            tree.set(row_id, column, self._format_display_value(value))
        self._load_geometry_detail(table_name, index)
        status_label.configure(foreground="#2e7d32")
        status_var.set(f"已儲存：{self._field_label(table_name, column)}")
        kind = "waler" if table_name == "walers" else "brace"
        self._sync_preview_to_geometry_selection(table_name, kind, index)

    def _sync_preview_to_geometry_selection(self, table_name, kind, index):
        if not hasattr(self, "canvas"):
            return
        target = next(
            (
                item
                for item in getattr(self, "_preview_selection_targets", ())
                if item.get("table_name") == table_name
                and item.get("row_index") == index
                and item.get("kind") == kind
            ),
            None,
        )
        if target is None:
            return
        self._preview_selected_key = target["key"]
        self._draw_preview_selection_highlight()
        self.canvas.draw_idle()

    def _load_strut_detail(self, index):
        if not (0 <= index < len(self.struts)):
            return
        row = self.struts[index]
        self._migrate_strut_position_fields(row)
        self.selected_strut_index = index
        self._loading_strut_detail = True
        try:
            waler_ids = tuple(
                str(item.get("WalerID", "") or "").strip()
                for item in self.walers
                if str(item.get("WalerID", "") or "").strip()
            )
            material_options = tuple(self._material_spec_options("支撐"))
            current_material = str(row.get("material_spec", "") or "").strip()
            if current_material and current_material not in material_options:
                material_options = (*material_options, current_material)
            self.strut_detail_widgets["material_spec"].configure(
                values=("", *material_options)
            )
            for column in ("FromWaler", "ToWaler"):
                current = str(row.get(column, "") or "").strip()
                choices = waler_ids
                if current and current not in choices:
                    choices = (*choices, current)
                self.strut_detail_widgets[column].configure(values=("", *choices))
            for column, variable in self.strut_detail_vars.items():
                variable.set(self._format_display_value(row.get(column, "")))
        finally:
            self._loading_strut_detail = False

        strut_id = str(row.get("StrutID", "") or "").strip() or "未命名支撐"
        self.strut_detail_empty_var.set(f"{strut_id}（第 {index + 1} 列）")
        self.strut_detail_status_var.set("")
        self.strut_detail_status_label.configure(foreground="#2e7d32")
        self._set_strut_detail_enabled(True)
        self._update_strut_detail_length(row)

    def _update_strut_detail_length(self, row=None):
        if row is None:
            index = getattr(self, "selected_strut_index", None)
            if index is None or not (0 <= index < len(self.struts)):
                self.strut_length_var.set("—")
                return
            row = self.struts[index]
        coordinates = [
            self._to_number(row.get(column, ""))
            for column in ("StartX", "StartY", "EndX", "EndY")
        ]
        if any(value is None for value in coordinates):
            self.strut_length_var.set("資料未完整")
            return
        length = self._line_length(*coordinates)
        self.strut_length_var.set(f"{length:,.1f} mm")

    def _reload_strut_detail_field(self, column):
        index = getattr(self, "selected_strut_index", None)
        if index is None or not (0 <= index < len(self.struts)):
            return "break"
        self._loading_strut_detail = True
        try:
            self.strut_detail_vars[column].set(
                self._format_display_value(self.struts[index].get(column, ""))
            )
        finally:
            self._loading_strut_detail = False
        self.strut_detail_status_var.set("")
        return "break"

    def _validate_strut_detail_value(self, index, column, raw_value, value):
        label = self._field_label("struts", column)
        if column == "StrutID":
            if not raw_value:
                return "支撐編號不可空白。"
            duplicate = any(
                row_index != index
                and str(row.get("StrutID", "") or "").strip() == raw_value
                for row_index, row in enumerate(self.struts)
            )
            if duplicate:
                return f"支撐編號「{raw_value}」已存在。"
        if column in ("BeamPositions", "ColumnPositions"):
            _positions, error = self._parse_position_list(raw_value)
            if error:
                return f"{label}格式錯誤：{error}。"
        if column in self.numeric_columns["struts"]:
            if raw_value == "" or isinstance(value, str):
                return f"{label}必須是數字。"
            if not math.isfinite(float(value)):
                return f"{label}必須是有限數字。"
            if column in dict(self.STRUT_BRACE_LENGTH_FIELDS) and float(value) < 0:
                return f"{label}不可為負數。"
            if column == "TargetJackRegion":
                if not float(value).is_integer() or value <= 0:
                    return "目標千斤頂區域必須是大於 0 的整數。"
        if column in ("FromWaler", "ToWaler") and raw_value:
            other = "ToWaler" if column == "FromWaler" else "FromWaler"
            if raw_value == str(self.struts[index].get(other, "") or "").strip():
                return "起點圍令與終點圍令不可相同。"
        return ""

    def _validate_project_field_value(
        self,
        table_name,
        index,
        column,
        raw_value,
        value,
    ):
        """Apply the same local field checks for both Main editing surfaces."""

        if table_name == "struts":
            return self._validate_strut_detail_value(
                index,
                column,
                raw_value,
                value,
            )
        if table_name in ("walers", "braces"):
            return self._validate_geometry_detail_value(
                table_name,
                index,
                column,
                raw_value,
                value,
            )
        return ""

    def _commit_project_field_edit(
        self,
        table_name,
        index,
        column,
        raw_value,
    ):
        """Parse, locally validate, commit, and run shared post-processing."""

        rows = getattr(self, table_name, ())
        if not (0 <= index < len(rows)):
            return False, None, "找不到要修改的資料列。"
        raw_value = "" if raw_value is None else str(raw_value).strip()
        value = self._parse_cell_value(table_name, column, raw_value)
        error = self._validate_project_field_value(
            table_name,
            index,
            column,
            raw_value,
            value,
        )
        if error:
            return False, value, error
        if value == rows[index].get(column, ""):
            return False, value, ""

        rows[index][column] = value
        self._handle_input_data_changed(
            preserve_view=True,
            table_name=table_name,
            field_name=column,
        )
        return True, value, ""

    def _commit_strut_detail_field(self, column):
        if getattr(self, "_loading_strut_detail", False):
            return
        index = getattr(self, "selected_strut_index", None)
        if index is None or not (0 <= index < len(self.struts)):
            return
        raw_value = self.strut_detail_vars[column].get().strip()
        changed, value, error = self._commit_project_field_edit(
            "struts",
            index,
            column,
            raw_value,
        )
        if error:
            self.strut_detail_status_label.configure(foreground="#b71c1c")
            self.strut_detail_status_var.set(error + " 已保留原值；按 Esc 可還原欄位。")
            return

        row = self.struts[index]
        if not changed:
            self.strut_detail_status_var.set("")
            return
        tree = self.treeviews["struts"]
        row_id = f"struts_{index}"
        if row_id in tree.get_children() and column in tree["columns"]:
            tree.set(row_id, column, self._format_display_value(value))
        self._update_strut_detail_length(row)
        self.strut_detail_status_label.configure(foreground="#2e7d32")
        self.strut_detail_status_var.set(f"已儲存：{self._field_label('struts', column)}")
        self._sync_preview_to_strut_selection(index)

    def _build_project_menu_and_toolbar(self):
        """Expose project file operations without consuming a workspace tab."""

        menu_bar = tk.Menu(self.root)
        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="新建專案", command=self._new_project)
        file_menu.add_command(label="開啟選取專案", command=self._load_selected_project_case)
        file_menu.add_command(label="儲存專案", command=self._save_current_project)
        file_menu.add_command(label="另存新專案", command=self._save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="重新連結 DXF", command=self._relink_dxf)
        file_menu.add_command(label="專案與 DXF 狀態", command=self._show_project_status)
        file_menu.add_command(label="刪除選取專案", command=self._delete_selected_project_case)
        file_menu.add_separator()
        file_menu.add_command(label="結束", command=self._on_main_window_close)
        menu_bar.add_cascade(label="檔案", menu=file_menu)
        self.root.configure(menu=menu_bar)
        self.file_menu = file_menu

        toolbar = ttk.Frame(self.root, padding=(8, 5))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="新建", command=self._new_project).pack(
            side="left",
            padx=(0, 4),
        )
        ttk.Label(toolbar, text="專案：").pack(side="left", padx=(8, 3))
        self.project_case_var = tk.StringVar(value="")
        self.project_case_selector = ttk.Combobox(
            toolbar,
            textvariable=self.project_case_var,
            state="readonly",
            width=26,
        )
        self.project_case_selector.pack(side="left", padx=(0, 4))
        self.project_case_selector.bind(
            "<<ComboboxSelected>>",
            self._update_project_action_states,
        )
        self.open_project_button = ttk.Button(
            toolbar,
            text="開啟",
            command=self._load_selected_project_case,
        )
        self.open_project_button.pack(side="left", padx=(0, 4))
        ttk.Button(toolbar, text="儲存", command=self._save_current_project).pack(
            side="left",
            padx=(0, 4),
        )
        ttk.Button(toolbar, text="另存", command=self._save_project_as).pack(
            side="left",
            padx=(0, 8),
        )

        self.project_quick_status_var = tk.StringVar(value="目前專案：未命名專案")
        ttk.Label(
            toolbar,
            textvariable=self.project_quick_status_var,
            foreground="#455a64",
        ).pack(side="right", padx=(8, 4))
        self.project_asset_status_var = tk.StringVar(value="")
        self._refresh_project_case_list()
        self._refresh_project_status_display()
        self._update_project_action_states()

    def _show_project_status(self):
        self._refresh_project_status_display()
        messagebox.showinfo(
            "專案與 DXF 狀態",
            self.project_asset_status_var.get() or "目前沒有專案狀態。",
            parent=self.root,
        )

    def _create_dxf_import_tab(self, parent_notebook=None):
        notebook = parent_notebook or self.notebook
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="DXF 批次匯入")
        self.dxf_import_tab = frame

        intro = ttk.LabelFrame(frame, text="建立或更新工程模型")
        intro.pack(fill="x", padx=12, pady=12)
        ttk.Label(
            intro,
            text=(
                "讀取整張 DXF，完成圖層用途分類、構件辨識、人工確認與工程線修正後，"
                "再匯入圍令、支撐與斜撐工程模型。"
            ),
            wraplength=900,
            justify="left",
        ).pack(fill="x", padx=10, pady=(10, 6))
        action_row = ttk.Frame(intro)
        action_row.pack(fill="x", padx=10, pady=(0, 10))
        self.dxf_start_import_button = ttk.Button(
            action_row,
            text="選擇 DXF 並開始批次匯入…",
            command=self._import_dxf_file,
        )
        self.dxf_start_import_button.pack(side="left")
        self.dxf_continue_import_button = ttk.Button(
            action_row,
            text="繼續 DXF 匯入",
            command=self._continue_dxf_import,
        )

        status_frame = ttk.LabelFrame(frame, text="最近一次 DXF 匯入")
        status_frame.pack(fill="x", padx=12, pady=(0, 12))
        self.dxf_import_status_var = tk.StringVar(value=self.dxf_import_status)
        self.dxf_import_error_var = tk.StringVar(value=self.dxf_import_error)
        self.dxf_import_source_var = tk.StringVar(value="來源檔案：—")
        ttk.Label(
            status_frame,
            textvariable=self.dxf_import_source_var,
            wraplength=900,
            justify="left",
        ).pack(fill="x", padx=10, pady=(10, 4))
        ttk.Label(
            status_frame,
            textvariable=self.dxf_import_status_var,
            wraplength=900,
            justify="left",
        ).pack(fill="x", padx=10, pady=4)
        ttk.Label(
            status_frame,
            textvariable=self.dxf_import_error_var,
            foreground="#b71c1c",
            wraplength=900,
            justify="left",
        ).pack(fill="x", padx=10, pady=(4, 10))
        self._refresh_dxf_workflow_ui()

    def _refresh_dxf_workflow_ui(self):
        workflow = self._current_dxf_workflow_status()
        start_button = getattr(self, "dxf_start_import_button", None)
        continue_button = getattr(self, "dxf_continue_import_button", None)
        if start_button is not None and continue_button is not None:
            if workflow == DxfWorkflowStatus.NONE:
                continue_button.pack_forget()
                if not start_button.winfo_manager():
                    start_button.pack(side="left")
            elif workflow == DxfWorkflowStatus.REVIEW:
                start_button.pack_forget()
                if not continue_button.winfo_manager():
                    continue_button.pack(side="left")
            else:
                start_button.pack_forget()
                continue_button.pack_forget()

        status_var = getattr(self, "dxf_import_status_var", None)
        if status_var is not None:
            if workflow == DxfWorkflowStatus.REVIEW:
                status_var.set("DXF 匯入：尚未完成")
            elif workflow == DxfWorkflowStatus.COMPLETED:
                status_var.set("DXF 匯入：已完成")

    def _create_cad_import_tab(self, parent_notebook=None):
        notebook = parent_notebook or self.notebook
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="CAD 新增構件")
        self.cad_add_tab = frame

        self.cad_import_enabled_var = tk.BooleanVar(value=self.cad_import_enabled)
        self.cad_import_status_var = tk.StringVar(value=self.cad_import_status)
        self.cad_import_last_event_var = tk.StringVar(value="尚無匯入紀錄")
        self.cad_import_error_var = tk.StringVar(value="")

        status_frame = ttk.LabelFrame(frame, text="AutoLISP 事件同步")
        status_frame.pack(fill="x", padx=12, pady=12)
        status_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            status_frame,
            text="自動接收 CAD 事件",
            variable=self.cad_import_enabled_var,
            command=self._toggle_cad_import,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 6))

        ttk.Label(status_frame, text="事件檔：").grid(
            row=1, column=0, sticky="ne", padx=(10, 4), pady=4
        )
        path_entry = ttk.Entry(status_frame)
        path_entry.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=4)
        path_entry.insert(0, str(self.cad_event_watcher.temp_path))
        path_entry.configure(state="readonly")

        ttk.Label(status_frame, text="目前狀態：").grid(
            row=2, column=0, sticky="ne", padx=(10, 4), pady=4
        )
        ttk.Label(
            status_frame,
            textvariable=self.cad_import_status_var,
            wraplength=760,
            justify="left",
        ).grid(row=2, column=1, sticky="w", padx=(0, 10), pady=4)

        ttk.Label(status_frame, text="最近事件：").grid(
            row=3, column=0, sticky="ne", padx=(10, 4), pady=4
        )
        ttk.Label(
            status_frame,
            textvariable=self.cad_import_last_event_var,
            wraplength=760,
            justify="left",
        ).grid(row=3, column=1, sticky="w", padx=(0, 10), pady=4)

        ttk.Label(status_frame, text="錯誤：").grid(
            row=4, column=0, sticky="ne", padx=(10, 4), pady=4
        )
        ttk.Label(
            status_frame,
            textvariable=self.cad_import_error_var,
            foreground="#b71c1c",
            wraplength=760,
            justify="left",
        ).grid(row=4, column=1, sticky="w", padx=(0, 10), pady=4)

        action_frame = ttk.Frame(status_frame)
        action_frame.grid(row=5, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 10))
        ttk.Button(
            action_frame,
            text="立即讀取",
            command=self._manual_read_cad_event,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            action_frame,
            text="重新顯示狀態",
            command=self._refresh_cad_import_status,
        ).pack(side="left")

        instructions = (
            "本頁只負責在既有工程模型中新增單一構件。使用方式：先在 progeCAD 載入 "
            "cad_builder.lsp，再執行 "
            "ADDWALER、ADDSTRUT 或 ADDBRACE，依 CAD 指令列提示點選起點與終點。"
            "匯入資料會直接加入"
            "既有圍令／支撐／斜撐分頁，並更新預覽；本頁不保存第二份資料。"
        )
        ttk.Label(
            frame,
            text=instructions,
            wraplength=900,
            justify="left",
        ).pack(fill="x", padx=16, pady=(0, 12))

    def _create_results_tab(self, parent=None):
        parent = parent or self.notebook
        self.analysis_notebook = ttk.Notebook(parent)
        self.analysis_notebook.pack(fill="both", expand=True, padx=4, pady=4)
        self.analysis_notebook.bind(
            "<<NotebookTabChanged>>",
            self._on_analysis_tab_changed,
        )

        frame = ttk.Frame(self.analysis_notebook)
        self.configuration_results_tab = frame
        self.analysis_notebook.add(frame, text="配置結果")
        material_tab = ttk.Frame(self.analysis_notebook)
        self.material_results_tab = material_tab
        self.analysis_notebook.add(material_tab, text="材料統計")
        diagnostics_tab = ttk.Frame(self.analysis_notebook)
        self.solver_diagnostics_tab = diagnostics_tab
        self.analysis_notebook.add(diagnostics_tab, text="Solver 診斷")
        export_tab = ttk.Frame(self.analysis_notebook)
        self.result_export_tab = export_tab
        self.analysis_notebook.add(export_tab, text="成果匯出")

        container = ttk.Frame(frame)
        container.pack(fill="both", expand=True, padx=4, pady=4)
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)

        columns = ("Visible", "Type", "ID", "Description")
        self.results_tree = ttk.Treeview(
            container,
            columns=columns,
            show="tree headings",
            selectmode="browse",
        )
        self.results_tree.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(
            container,
            orient="vertical",
            command=self.results_tree.yview,
        )
        x_scroll = ttk.Scrollbar(
            container,
            orient="horizontal",
            command=self.results_tree.xview,
        )
        self.results_tree.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
        )
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        self.results_tree.heading("#0", text="項目")
        self.results_tree.column("#0", width=130, minwidth=100, anchor="w", stretch=False)
        result_column_labels = {
            "Visible": "顯示",
            "Type": "類型",
            "ID": "編號",
            "Description": "摘要",
        }
        for column in columns:
            self.results_tree.heading(column, text=result_column_labels.get(column, column))
        self.results_tree.column("Visible", width=70, minwidth=70, anchor="center", stretch=False)
        self.results_tree.column("Type", width=90, minwidth=80, anchor="center", stretch=False)
        self.results_tree.column("ID", width=110, minwidth=80, anchor="center", stretch=False)
        self.results_tree.column("Description", width=430, minwidth=220, anchor="w")

        self.results_tree.bind("<ButtonRelease-1>", self._on_results_tree_click)
        self.results_tree.bind("<space>", self._on_results_tree_space)
        self.results_tree.bind("<Double-1>", self._on_results_tree_double_click)
        self.results_tree.bind(
            "<<TreeviewSelect>>",
            self._update_result_action_states,
        )

        ttk.Label(
            frame,
            text=(
                "點選「顯示」欄切換結果顯示；雙擊群組可展開/收合；"
                "雙擊圍令方案可直接編輯，雙擊支撐方案可編輯配置。"
                "可同時統計多筆圍令與支撐結果。"
            ),
        ).pack(fill="x", padx=6, pady=(0, 4))

        self.result_scope_var = tk.StringVar(value="目前沒有顯示中的配置成果。")
        self.result_scope_label = ttk.Label(
            frame,
            textvariable=self.result_scope_var,
            foreground="#37474f",
            wraplength=900,
            justify="left",
        )
        self.result_scope_label.pack(fill="x", padx=6, pady=(0, 5))

        result_action_frame = ttk.Frame(frame)
        result_action_frame.pack(fill="x", padx=4, pady=(0, 6))
        self.export_results_excel_button = ttk.Button(
            result_action_frame,
            text="匯出目前 0 個配置成果 Excel",
            command=self._export_visible_results_to_excel,
        )
        self.export_results_excel_button.pack(side="left", padx=(0, 6))
        material_frame = ttk.LabelFrame(material_tab, text="目前顯示方案的材料用量與庫存比較")
        material_frame.pack(fill="both", expand=True, padx=8, pady=8)
        material_frame.rowconfigure(1, weight=1)
        material_frame.columnconfigure(0, weight=1)
        ttk.Label(
            material_frame,
            text="統計範圍：目前顯示方案",
            foreground="#455a64",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 2))

        material_columns = (
            "Material Spec",
            "Length",
            "Used Qty",
            "Inventory Qty",
            "Remaining Qty",
        )
        self.material_summary_tree = ttk.Treeview(
            material_frame,
            columns=material_columns,
            show="headings",
            height=7,
        )
        self.material_summary_tree.grid(row=1, column=0, sticky="nsew")
        material_scroll = ttk.Scrollbar(
            material_frame,
            orient="vertical",
            command=self.material_summary_tree.yview,
        )
        material_scroll.grid(row=1, column=1, sticky="ns")
        self.material_summary_tree.configure(yscrollcommand=material_scroll.set)

        material_column_labels = {
            "Material Spec": "材料規格",
            "Length": "料長(mm)",
            "Used Qty": "使用數量",
            "Inventory Qty": "庫存數量",
            "Remaining Qty": "剩餘數量",
        }
        for column in material_columns:
            self.material_summary_tree.heading(column, text=material_column_labels.get(column, column))
            self.material_summary_tree.column(
                column,
                width=110,
                minwidth=90,
                anchor="center",
            )
        self.material_summary_tree.tag_configure(
            "shortage",
            foreground="#c62828",
        )

        self._build_execution_messages(diagnostics_tab)

        export_frame = ttk.LabelFrame(export_tab, text="DXF 配置成果")
        export_frame.pack(fill="x", padx=12, pady=12)
        ttk.Label(
            export_frame,
            text=(
                "將「配置結果」中目前勾選顯示的圍令與支撐方案寫回 DXF。"
                "右側共用預覽圖仍顯示相同的最終工程模型與配置結果。"
            ),
            wraplength=900,
            justify="left",
        ).pack(fill="x", padx=10, pady=(10, 8))
        self.export_results_dxf_button = ttk.Button(
            export_frame,
            text="匯出目前 0 個配置成果 DXF",
            command=self._export_visible_results_to_dxf,
        )
        self.export_results_dxf_button.pack(anchor="w", padx=10, pady=(0, 10))

    def _on_ascii_art_entry_focus_in(self, event=None):
        if hasattr(self, "ascii_art_entry"):
            self.ascii_art_entry.configure(
                bg="white",
                fg="black",
                insertbackground="black",
                selectbackground="#d9e8ff",
                selectforeground="black",
            )

    def _on_ascii_art_entry_focus_out(self, event=None):
        if hasattr(self, "ascii_art_entry"):
            self.ascii_art_entry.configure(
                bg="white",
                fg="black",
                insertbackground="black",
                selectbackground="#d9e8ff",
                selectforeground="black",
            )

    def _on_ascii_art_code_enter(self, event=None):
        code = self.ascii_art_code_var.get().strip()
        art_text = load_ascii_art(code)
        if art_text is None:
            return "break"
        self._show_ascii_art_window(code, art_text)
        self.ascii_art_code_var.set("")
        return "break"

    def _show_ascii_art_window(self, code, art_text):
        families = set(tkfont.families(self.root))
        font_family = "Consolas" if "Consolas" in families else "Courier New"

        lines = art_text.splitlines() or [""]
        line_count = len(lines)
        max_width = max(len(line) for line in lines)
        font_size = calculate_ascii_art_font_size(line_count, max_width)
        text_width = min(max(max_width, 40), 160)
        text_height = min(max(line_count, 10), 45)

        window = tk.Toplevel(self.root)
        window.title(f"ASCII Art - {code}")
        window.transient(self.root)
        window.resizable(True, True)
        window.state("zoomed")

        frame = ttk.Frame(window)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        ttk.Label(
            frame,
            text=(
                f"[ASCII]  File: {code}.txt   Lines: {line_count}   "
                f"Max Width: {max_width}   Font Size: {font_size}"
            ),
            font=(font_family, 9),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        text_widget = tk.Text(
            frame,
            width=text_width,
            height=text_height,
            wrap="none",
            font=(font_family, font_size),
            bg="black",
            fg="white",
            insertbackground="white",
            padx=8,
            pady=8,
        )
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=text_widget.yview)
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=text_widget.xview)
        text_widget.configure(
            yscrollcommand=y_scroll.set,
            xscrollcommand=x_scroll.set,
        )
        text_widget.grid(row=1, column=0, sticky="nsew")
        y_scroll.grid(row=1, column=1, sticky="ns")
        x_scroll.grid(row=2, column=0, sticky="ew")

        text_widget.insert("1.0", art_text)
        text_widget.configure(state="disabled")

    def _project_case_json_files(self):
        self.project_cases_dir.mkdir(exist_ok=True)
        managed = {
            path.parent.name: path
            for path in self.project_cases_dir.glob("*/project.json")
            if path.is_file()
        }
        legacy = {
            path.stem: path
            for path in self.project_cases_dir.glob("*.json")
            if path.is_file() and path.stem not in managed
        }
        return [
            {**legacy, **managed}[name]
            for name in sorted({*legacy, *managed})
        ]

    @staticmethod
    def _sanitize_project_case_name(project_name):
        name = str(project_name or "").strip()
        translation = str.maketrans({
            "<": "＜",
            ">": "＞",
            ":": "：",
            '"': "＂",
            "/": "／",
            "\\": "＼",
            "|": "｜",
            "?": "？",
            "*": "＊",
        })
        return name.translate(translation).strip()

    def _managed_project_case_path(self, project_name):
        safe_name = self._sanitize_project_case_name(project_name)
        if not safe_name:
            return None
        if safe_name.lower().endswith(".json"):
            safe_name = safe_name[:-5]
        return self.project_cases_dir / safe_name / "project.json"

    def _project_case_path(self, project_name):
        managed = self._managed_project_case_path(project_name)
        if managed is None:
            return None
        if managed.is_file():
            return managed
        legacy = self.project_cases_dir / f"{managed.parent.name}.json"
        return legacy if legacy.is_file() else managed

    @staticmethod
    def _project_case_name_from_path(path):
        path = Path(path)
        return path.parent.name if path.name == "project.json" else path.stem

    def _refresh_project_case_list(self, selected_name=None, select_first=False):
        project_names = [
            self._project_case_name_from_path(path)
            for path in self._project_case_json_files()
        ]
        selector = getattr(self, "project_case_selector", None)
        if selector is not None:
            current_var = getattr(self, "project_case_var", None)
            current = str(current_var.get() or "") if current_var is not None else ""
            selector.configure(values=project_names)
            target = selected_name
            if target is None and current in project_names:
                target = current
            if target is None and select_first and project_names:
                target = project_names[0]
            self.project_case_var.set(target if target in project_names else "")

        if not hasattr(self, "project_case_listbox"):
            self._update_project_action_states()
            return
        self.project_case_listbox.delete(0, "end")
        selected_index = None
        for index, display_name in enumerate(project_names):
            self.project_case_listbox.insert("end", display_name)
            if selected_name is not None and display_name == selected_name:
                selected_index = index
        if selected_index is None and select_first and self.project_case_listbox.size() > 0:
            selected_index = 0
        if selected_index is not None:
            self.project_case_listbox.selection_set(selected_index)
            self.project_case_listbox.see(selected_index)
        self._update_project_action_states()

    def _selected_project_case_name(self):
        variable = getattr(self, "project_case_var", None)
        if variable is not None:
            selected = str(variable.get() or "").strip()
            if selected:
                return selected
        if not hasattr(self, "project_case_listbox"):
            return None
        selection = self.project_case_listbox.curselection()
        if not selection:
            return None
        return self.project_case_listbox.get(selection[0])

    def _update_project_action_states(self, _event=None):
        has_selection = bool(self._selected_project_case_name())
        state = "normal" if has_selection else "disabled"
        for attribute in ("open_project_button", "delete_project_button"):
            button = getattr(self, attribute, None)
            if button is not None:
                button.configure(state=state)
        file_menu = getattr(self, "file_menu", None)
        if file_menu is not None:
            for label in ("開啟選取專案", "刪除選取專案"):
                try:
                    file_menu.entryconfigure(label, state=state)
                except tk.TclError:
                    pass

    def _refresh_project_status_display(self):
        variable = getattr(self, "project_asset_status_var", None)
        if variable is None:
            return
        report = getattr(self, "dxf_asset_status_report", None)
        status_labels = {
            DxfStatus.READY: "可使用",
            DxfStatus.RUNTIME_READY: "已匯入，尚未保存管理副本",
            DxfStatus.VERIFIED_PENDING_SAVE: "重新連結已驗證，尚未儲存",
            DxfStatus.MANAGED_COPY_MODIFIED: "管理副本內容異常",
            DxfStatus.SOURCE_MODIFIED: "原始來源已修改",
            DxfStatus.MISSING: "管理副本遺失",
            DxfStatus.RELINK_REQUIRED: "需要重新連結",
            DxfStatus.BINDING_REQUIRED: "需要重新建立構件綁定",
            DxfStatus.LEGACY_NO_STATE: "舊專案缺少 DXF 綁定資訊",
            DxfStatus.INCOMPATIBLE: "DXF 與工程資料不相容",
            DxfStatus.GEOMETRY_COMPATIBLE: "幾何相容，等待確認",
            DxfStatus.NO_DXF: "未建立 DXF 關聯",
        }
        lines = [
            f"專案：{self._project_display_name()}",
            f"是否儲存：{'是' if self._project_is_saved() else '否'}",
            (
                "DXF 匯入流程："
                + {
                    DxfWorkflowStatus.NONE: "無進行中的 Review",
                    DxfWorkflowStatus.REVIEW: "尚未完成，可繼續",
                    DxfWorkflowStatus.COMPLETED: "已完成",
                }[self._current_dxf_workflow_status()]
            ),
        ]
        if report is None:
            lines.append("DXF 狀態：尚未檢查")
        else:
            lines.extend([
                f"DXF 狀態：{status_labels.get(report.status, report.status.value)}",
                f"管理副本：{'存在' if report.managed_exists else '找不到或尚未建立'}",
                f"原始來源：{'存在' if report.original_exists else '找不到或未記錄'}",
                f"狀態說明：{report.summary}",
            ])
            lines.extend(report.messages)
        if self._dxf_binding_is_stale():
            lines.append(
                "DXF 綁定：工程資料已修改；僅影響來源追蹤與重新確認，"
                "不阻止目前 Project 成果匯出"
            )
        compatibility = getattr(self, "last_dxf_compatibility_report", None)
        if compatibility is not None:
            lines.append(
                "最近 DXF 相容性："
                + status_labels.get(compatibility.status, compatibility.status.value)
            )
            lines.append(
                "構件匹配："
                f"{len(compatibility.matches)}/{compatibility.total_saved_components}"
            )
            lines.append(
                "需要人工處理："
                + (", ".join(compatibility.binding_required_ids) or "無")
            )
            if compatibility.incompatible_items:
                lines.append(
                    "不相容項目：" + "；".join(compatibility.incompatible_items)
                )
        lines.append(
            f"Solver 結果：{'已保留，未重新計算' if self.result_items else '目前無結果'}"
        )
        variable.set("\n".join(lines))
        quick_variable = getattr(self, "project_quick_status_var", None)
        if quick_variable is not None:
            dxf_text = (
                status_labels.get(report.status, report.status.value)
                if report is not None
                else "尚未檢查"
            )
            if self._dxf_binding_is_stale():
                dxf_text += "／工程資料已修改"
            quick_variable.set(
                f"目前專案：{self._project_display_name()}｜DXF：{dxf_text}"
            )
        source_variable = getattr(self, "dxf_import_source_var", None)
        if source_variable is not None:
            state = getattr(self, "dxf_last_import_debug", None)
            source = state.get("source_path") if isinstance(state, dict) else None
            source_variable.set(f"來源檔案：{source or '—'}")

    def _load_selected_project_case(self):
        project_name = self._selected_project_case_name()
        if not project_name:
            messagebox.showwarning("載入專案", "請先選擇要載入的專案。")
            return
        if getattr(self, "project_dirty", False) and not messagebox.askyesno(
            "尚未儲存",
            "目前專案有尚未儲存的變更，確定要開啟另一個專案嗎？",
            parent=self.root,
        ):
            return
        try:
            self.load_project_case(project_name)
        except Exception as exc:
            messagebox.showerror("載入專案失敗", str(exc))

    def _delete_selected_project_case(self):
        project_name = self._selected_project_case_name()
        if not project_name:
            messagebox.showwarning("刪除專案", "請先選擇要刪除的專案。")
            return

        path = self._project_case_path(project_name)
        if path is None:
            messagebox.showwarning("刪除專案", "請先選擇要刪除的專案。")
            return

        try:
            project_cases_dir = self.project_cases_dir.resolve()
            target_path = path.resolve(strict=False)
        except Exception as exc:
            messagebox.showerror(
                "刪除專案",
                f"無法刪除：\n{path}\n\n原因：\n{exc}",
            )
            return

        is_legacy = (
            target_path.parent == project_cases_dir
            and target_path.suffix.lower() == ".json"
        )
        is_managed = (
            target_path.name == "project.json"
            and target_path.parent.parent == project_cases_dir
        )
        if not (is_legacy or is_managed):
            messagebox.showerror(
                "刪除專案",
                f"無法刪除：\n{path}\n\n原因：\n目標不是有效的專案檔案。",
            )
            return

        if not target_path.is_file():
            messagebox.showwarning("刪除專案", "找不到專案檔案。")
            self._refresh_project_case_list(select_first=True)
            return

        managed_dxf = target_path.parent / "source" / "source.dxf"
        managed_dxf_text = (
            "是（將連同專案資料夾刪除）"
            if is_managed and managed_dxf.is_file()
            else "否"
        )
        confirmed = messagebox.askyesno(
            "確認刪除",
            (
                f"確定要刪除專案：{project_name}\n\n"
                f"專案路徑：\n{target_path}\n\n"
                f"包含管理 DXF：{managed_dxf_text}\n\n"
                "此動作無法復原。"
            ),
        )
        if not confirmed:
            return

        try:
            if is_managed:
                shutil.rmtree(target_path.parent)
            else:
                target_path.unlink()
        except Exception as exc:
            messagebox.showerror(
                "刪除專案",
                f"無法刪除：\n{target_path}\n\n原因：\n{exc}",
            )
            return

        self._refresh_project_case_list(select_first=True)
        messagebox.showinfo("刪除專案", f"已刪除專案：\n{project_name}")

    def _save_project_as(self):
        project_name = simpledialog.askstring(
            "另存新專案",
            "專案名稱：",
            parent=self.root,
        )
        if project_name is None:
            return
        project_name = project_name.strip()
        if not project_name:
            messagebox.showwarning("儲存專案", "專案名稱不可空白。")
            return

        path = self._project_case_path(project_name)
        if path is None:
            messagebox.showwarning("儲存專案", "專案名稱不可空白。")
            return
        if path.exists():
            confirmed = messagebox.askyesno(
                "覆蓋專案",
                f"專案「{project_name}」已存在。\n是否覆蓋？",
                parent=self.root,
            )
            if not confirmed:
                return

        try:
            saved_path = self.save_project_case(project_name)
        except Exception as exc:
            messagebox.showerror("儲存專案失敗", str(exc))
            return

        saved_name = self._project_case_name_from_path(saved_path)
        self._refresh_project_case_list(selected_name=saved_name)
        messagebox.showinfo("儲存專案", f"已儲存：\n{saved_path}")
        return saved_path

    def _save_current_project_case_from_prompt(self):
        """Backward-compatible command name used by older tests/extensions."""

        return self._save_project_as()

    def _save_current_project(self):
        current = getattr(self, "current_project_path", None)
        if current is None:
            return self._save_project_as()
        project_name = self._project_case_name_from_path(current)
        try:
            saved_path = self.save_project_case(project_name)
        except Exception as exc:
            messagebox.showerror("儲存專案失敗", str(exc), parent=self.root)
            return None
        self._refresh_project_case_list(selected_name=project_name)
        messagebox.showinfo("儲存專案", f"已儲存：\n{saved_path}", parent=self.root)
        return saved_path

    def _new_project(self):
        if getattr(self, "project_dirty", False) and not messagebox.askyesno(
            "尚未儲存",
            "目前專案有尚未儲存的變更，確定要建立新專案嗎？",
            parent=self.root,
        ):
            return
        self.project_data = ProjectDataModel(inventory=self._load_default_inventory())
        self.result_items.clear()
        self.project_result = None
        self.last_calculated_time = None
        self.current_project_path = None
        if hasattr(self, "project_case_var"):
            self.project_case_var.set("")
        self.dxf_last_import_debug = None
        self.dxf_workflow_status = DxfWorkflowStatus.NONE
        self.dxf_review_session = None
        self.dxf_asset = None
        self.dxf_asset_status_report = self._ensure_project_service().inspect_dxf_state(
            None, None, None
        )
        self.last_dxf_compatibility_report = None
        self.solver_memory.clear()
        self.support_candidate_cache.clear()
        for table_name in (
            "walers",
            "struts",
            "braces",
            "inventory",
            "material_specs",
        ):
            self._refresh_tree(table_name)
        self._refresh_results_tree()
        self.update_preview()
        self._refresh_dxf_workflow_ui()
        self._clear_project_dirty()

    def _relink_dxf(self):
        if self._current_dxf_workflow_status() == DxfWorkflowStatus.REVIEW:
            messagebox.showwarning(
                "DXF Review 尚未完成",
                "請先繼續目前的 DXF 匯入；Review 期間不能改用重新連結取代來源。",
                parent=self.root,
            )
            return
        file_path = filedialog.askopenfilename(
            title="重新連結 DXF",
            filetypes=(("DXF 圖檔", "*.dxf"), ("所有檔案", "*.*")),
            parent=self.root,
        )
        if not file_path:
            return
        service = self._ensure_project_service()
        saved_state = getattr(self, "dxf_last_import_debug", None)
        try:
            request = RelinkDxfRequest(
                candidate_path=Path(file_path),
                saved_state=saved_state,
                existing_asset=getattr(self, "dxf_asset", None),
                current_dxf_report=getattr(
                    self,
                    "dxf_asset_status_report",
                    None,
                ),
                project_rows=self._project_rows_by_table(),
            )
            result = service.try_exact_relink(request)
            if result is None:
                self.dxf_dialog_active = True
                try:
                    payload = DXFImportDialog(
                        self.root,
                        file_path,
                        initial_state=saved_state,
                        cad_event_watcher=self.cad_event_watcher,
                        material_specs=self.material_specs,
                        restore_saved_layer_classification=True,
                        allow_pause=False,
                    ).show()
                finally:
                    self.dxf_dialog_active = False
                if payload is None:
                    return
                if isinstance(payload, DXFImportDialogOutcome):
                    if payload.action != "complete" or payload.result is None:
                        return
                    candidate_result = payload.result
                else:
                    candidate_result, _unused_mode = payload
                result = service.relink_dxf(
                    RelinkDxfRequest(
                        candidate_path=Path(file_path),
                        saved_state=saved_state,
                        existing_asset=getattr(self, "dxf_asset", None),
                        current_dxf_report=getattr(
                            self,
                            "dxf_asset_status_report",
                            None,
                        ),
                        project_rows=request.project_rows,
                        candidate_state=candidate_result.to_debug_dict(),
                    )
                )

            self.last_dxf_compatibility_report = result.compatibility_report
            self.dxf_asset_status_report = result.dxf_status_report
            self._refresh_project_status_display()
            if not result.accepted:
                details = "\n".join(result.detail_lines)
                self._set_dxf_import_status(
                    "DXF 重新連結尚未通過",
                    source=file_path,
                    error=details,
                )
                self.show_result(
                    "DXF 重新連結未套用；原專案、Solver 結果與材料配置均未變更。\n"
                    + details
                )
                return

            self.dxf_last_import_debug = result.relinked_state
            self._mark_project_dirty("DXF 已重新連結，尚未保存管理副本")
            self._set_dxf_import_status(
                "DXF 重新連結成功，等待儲存專案",
                source=file_path,
            )
            self.show_result(
                "DXF 重新連結已驗證；Solver 結果、材料配置與既有人工修正均已保留。\n"
                + "\n".join(result.detail_lines)
                + "\n請儲存專案以更新 source/source.dxf。"
            )
        except (
            DXFImportError,
            ProjectPersistenceError,
            OSError,
            ValueError,
        ) as exc:
            self._set_dxf_import_status(
                "DXF 重新連結失敗",
                source=file_path,
                error=exc,
            )
            self.show_result(f"DXF 重新連結失敗：{exc}")

    def _load_default_inventory(self):
        repository = getattr(self, "inventory_repository", None)
        if repository is None:
            return []
        return repository.list_items()

    def save_project_case(self, project_name):
        path = self._managed_project_case_path(project_name)
        if path is None:
            raise ValueError("專案名稱不可空白。")
        payload = self._build_project_payload(path)
        result = self._ensure_project_service().save_project(
            SaveProjectRequest(
                project_path=path,
                payload=payload,
                current_project_path=getattr(self, "current_project_path", None),
                existing_asset=getattr(self, "dxf_asset", None),
                import_state=getattr(self, "dxf_last_import_debug", None),
                current_dxf_report=getattr(
                    self,
                    "dxf_asset_status_report",
                    None,
                ),
                has_solver_result=bool(self.result_items),
            )
        )
        self.dxf_asset = copy.deepcopy(result.dxf_asset)
        self.current_project_path = result.project_path
        self.project_result = copy.deepcopy(result.payload.get("result"))
        self.dxf_asset_status_report = result.dxf_status_report
        self._clear_project_dirty()
        return result.project_path

    def load_project_case(self, project_name, *, silent=False):
        path = self._project_case_path(project_name)
        if path is None or not path.is_file():
            raise FileNotFoundError(f"找不到專案：{project_name}")

        result = self._ensure_project_service().load_project(path)
        payload = result.payload
        self._apply_project_payload(payload, result.project_path)
        self.dxf_asset_status_report = result.dxf_status_report
        self.last_dxf_compatibility_report = None
        self._clear_project_dirty()
        display_name = self._project_case_name_from_path(path)
        self._refresh_project_case_list(selected_name=display_name)
        if not silent:
            dxf_notice = f"DXF 狀態：{self.dxf_asset_status_report.summary}"
            if self.dxf_asset_status_report.status == DxfStatus.LEGACY_NO_STATE:
                dxf_notice = (
                    "此專案建立於舊版，未保存 DXF 構件綁定資訊。"
                    "既有 Solver 輸入、最佳化結果與材料配置仍可使用。"
                    "若要匯出 DXF，請重新建立 DXF 關聯。"
                    "此操作不會重新執行 Solver，也不會清除既有最佳化結果，"
                    "但可能需要重新確認構件對應。"
                )
            if self.result_items:
                self.show_result(
                    f"已載入專案：{display_name}\n已恢復計算結果與材料統計。\n"
                    f"{dxf_notice}"
                )
            else:
                self.show_result(
                    f"已載入專案：{display_name}\n此專案尚無計算結果。\n"
                    f"{dxf_notice}"
                )
        return payload

    def _build_material_summary_payload(self):
        return ProjectResultModel.build_material_summary(
            self._collect_visible_material_usage(),
            self._inventory_quantity,
            unlimited_quantity=UNLIMITED_INVENTORY_QTY,
        )

    @staticmethod
    def _serialize_support_plan(plan):
        return ProjectResultModel.serialize_support_plan(plan)

    @staticmethod
    def _deserialize_support_plan(data):
        return ProjectResultModel.deserialize_support_plan(data)

    @staticmethod
    def _serialize_result_item(result_id, item):
        return ProjectResultModel.serialize_result_item(result_id, item)

    @staticmethod
    def _deserialize_result_item(payload):
        return ProjectResultModel.deserialize_result_item(payload)

    def _build_project_result_payload(self):
        model = ProjectResultModel(
            result_items=self.result_items,
            last_calculated_time=self.last_calculated_time,
            persisted_payload=self.project_result,
        )
        return model.to_payload(self._build_material_summary_payload())

    def _mark_results_updated(self):
        self.last_calculated_time = datetime.now().isoformat(timespec="seconds")
        self.project_result = self._build_project_result_payload()
        self._mark_project_dirty("成果配置已變更")

    def _build_project_payload(self, path=None):
        project_name = (
            self._project_case_name_from_path(path)
            if path
            else "未命名專案"
        )
        return {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "project_information": {
                "project_name": project_name,
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "application": "SupportSolver",
            },
            "input_data": self._ensure_project_data().to_case_data(),
            "dxf_workflow_status": self._current_dxf_workflow_status().value,
            "dxf_import_state": copy.deepcopy(
                getattr(self, "dxf_last_import_debug", None)
            ),
            "dxf_asset": copy.deepcopy(getattr(self, "dxf_asset", None)),
            "result": self._build_project_result_payload(),
        }

    def _apply_project_payload(self, payload, path=None):
        input_data = payload["input_data"]
        result_payload = payload.get("result", None)
        dxf_import_state = payload.get("dxf_import_state")
        dxf_asset = payload.get("dxf_asset")
        self.dxf_workflow_status = dxf_workflow_status_from_payload(payload)
        self.dxf_review_session = None
        self.dxf_last_import_debug = (
            copy.deepcopy(dxf_import_state)
            if isinstance(dxf_import_state, dict)
            else None
        )
        self.dxf_asset = (
            copy.deepcopy(dxf_asset)
            if isinstance(dxf_asset, dict)
            else None
        )

        self.walers = copy.deepcopy(input_data["walers"])
        self.struts = copy.deepcopy(input_data["struts"])
        self.braces = copy.deepcopy(input_data["braces"])
        self.inventory = copy.deepcopy(
            input_data.get("inventory", self._load_default_inventory())
        )
        self.material_specs = copy.deepcopy(
            input_data.get("material_specs", DEFAULT_MATERIAL_SPECS)
        )

        self.result_items.clear()
        if isinstance(result_payload, dict):
            best_solution = result_payload.get("best_solution", {})
            for item_payload in list(best_solution.get("result_items", []) or []):
                if not isinstance(item_payload, dict):
                    continue
                result_id = str(item_payload.get("id", "") or "").strip()
                if result_id:
                    self.result_items[result_id] = self._deserialize_result_item(item_payload)
            self.project_result = copy.deepcopy(result_payload)
            self.last_calculated_time = result_payload.get("last_calculated_time")
        else:
            self.project_result = None
            self.last_calculated_time = None

        self.solver_memory.clear()
        self.support_candidate_cache.clear()
        self.current_project_path = path
        for table_name in (
            "walers",
            "struts",
            "braces",
            "inventory",
            "material_specs",
        ):
            self._refresh_tree(table_name)
        self._refresh_results_tree()
        self.update_preview()
        self._refresh_dxf_workflow_ui()

    def _on_results_tree_click(self, event):
        if self.results_tree.identify_region(event.x, event.y) != "cell":
            return
        column_id = self.results_tree.identify_column(event.x)
        if self._tree_column_key(self.results_tree, column_id) != "Visible":
            return
        item_id = self.results_tree.identify_row(event.y)
        if not item_id:
            return
        self.results_tree.selection_set(item_id)
        if self._is_result_group_iid(item_id):
            self._toggle_result_group_visibility(item_id)
        elif self._is_support_plan_iid(item_id):
            zoning, support_id = self._parse_support_plan_iid(item_id)
            self._toggle_support_plan_visibility(zoning, support_id)
        else:
            self._toggle_result_visibility(item_id)
        return "break"

    def _visible_result_scope(self):
        counts = {"waler": 0, "support": 0}
        member_occurrences = Counter()
        for result_id, item in self.result_items.items():
            result_type = item.get("type")
            result = item.get("result")
            if result_type == "waler":
                if not item.get("visible", True) or not isinstance(result, dict):
                    continue
                member_id = str(result.get("waler_id", "") or result_id).strip()
                counts["waler"] += 1
                member_occurrences[("圍令", member_id)] += 1
                continue
            if result_type != "support" or result is None:
                continue
            for plan in list(getattr(result, "plans", []) or []):
                support_id = str(getattr(plan, "support_id", "") or "").strip()
                if support_id and self._support_plan_visible(item, support_id):
                    counts["support"] += 1
                    member_occurrences[("支撐", support_id)] += 1
        conflicts = tuple(
            (kind, member_id, quantity)
            for (kind, member_id), quantity in sorted(member_occurrences.items())
            if quantity > 1
        )
        return counts, conflicts

    def _update_result_action_states(self, _event=None):
        if not hasattr(self, "results_tree"):
            return

        counts, conflicts = self._visible_result_scope()
        total = counts["waler"] + counts["support"]
        can_export_excel = total > 0 and not conflicts
        self.export_results_excel_button.configure(
            text=f"匯出目前 {total} 個配置成果 Excel",
            state="normal" if can_export_excel else "disabled",
        )
        has_coordinate_metadata = isinstance(
            getattr(self, "dxf_last_import_debug", None),
            dict,
        )
        can_export = total > 0 and not conflicts
        self.export_results_dxf_button.configure(
            text=f"匯出目前 {total} 個配置成果 DXF",
            state="normal" if can_export else "disabled",
        )

        scope_text = (
            f"目前顯示：圍令 {counts['waler']} 個、支撐 {counts['support']} 支；"
            "材料統計、Excel 與 DXF 匯出皆以這些顯示方案為範圍。"
        )
        if conflicts:
            conflict_text = "、".join(
                f"{kind} {member_id} 同時顯示 {quantity} 個方案"
                for kind, member_id, quantity in conflicts
            )
            scope_text += f"  ⚠ {conflict_text}；匯出前請每個構件只保留一個方案。"
            color = "#b71c1c"
        elif total and not has_coordinate_metadata:
            scope_text += (
                "  目前缺少 Project → World 座標資訊；按下 DXF 匯出時"
                "會顯示需要補齊的資料。Excel 材料明細仍可匯出。"
            )
            color = "#8a5a00"
        else:
            color = "#37474f"
        self.result_scope_var.set(scope_text)
        self.result_scope_label.configure(foreground=color)

    def _on_results_tree_space(self, event=None):
        selected = self.results_tree.selection()
        if selected:
            selected_id = selected[0]
            if self._is_result_group_iid(selected_id):
                self._toggle_result_group_visibility(selected_id)
            elif self._is_support_plan_iid(selected_id):
                zoning, support_id = self._parse_support_plan_iid(selected_id)
                self._toggle_support_plan_visibility(zoning, support_id)
            else:
                self._toggle_result_visibility(selected_id)
        return "break"

    def _on_results_tree_double_click(self, event):
        if self.results_tree.identify_region(event.x, event.y) not in ("cell", "tree"):
            return
        result_id = self.results_tree.identify_row(event.y)
        if not result_id:
            return
        self.results_tree.selection_set(result_id)
        if self._is_result_group_iid(result_id):
            is_open = bool(self.results_tree.item(result_id, "open"))
            self.results_tree.item(result_id, open=not is_open)
            return "break"
        if self._is_support_plan_iid(result_id):
            zoning, support_id = self._parse_support_plan_iid(result_id)
            self._open_support_plan_editor(zoning, support_id)
            return "break"
        item = self.result_items.get(result_id)
        if item and item.get("type") == "waler":
            self._open_waler_plan_editor(result_id)
            return "break"
        self._show_result_details(result_id)
        return "break"

    @staticmethod
    def _tree_column_key(tree, column_id):
        if column_id == "#0":
            return None
        try:
            column_index = int(str(column_id).lstrip("#")) - 1
        except ValueError:
            return None
        columns = list(tree["columns"])
        if not 0 <= column_index < len(columns):
            return None
        return columns[column_index]

    def _show_result_details(self, result_id):
        item = self.result_items.get(result_id)
        if item is None:
            return

        result_type = item.get("type", "")
        type_name = "圍令" if result_type == "waler" else "支撐"
        detail_window = tk.Toplevel(self.root)
        detail_window.title(f"結果詳細資料 - {type_name} {result_id}")
        detail_window.geometry("760x620")
        detail_window.minsize(560, 420)
        detail_window.transient(self.root)

        detail_text = scrolledtext.ScrolledText(
            detail_window,
            wrap="word",
            font=("Microsoft JhengHei", 10),
            padx=12,
            pady=12,
        )
        detail_text.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        detail_text.insert("1.0", self._format_result_details(result_id, item))
        detail_text.configure(state="disabled")

        ttk.Button(
            detail_window,
            text="關閉",
            command=detail_window.destroy,
        ).pack(anchor="e", padx=8, pady=(4, 8))

    def _visible_dxf_export_plans(self):
        plans = []
        for result_id, item in self.result_items.items():
            if not item.get("visible", True):
                continue
            result_type = item.get("type")
            result = item.get("result")
            if result_type == "waler" and isinstance(result, dict):
                plan = result.get("selected_plan") or {}
                member_id = str(result.get("waler_id", "") or "").strip()
                if not member_id or not isinstance(plan, dict):
                    continue
                raw_pieces = list(plan.get("pieces", []) or [])
                if not raw_pieces:
                    raw_pieces = [
                        ("steel", length)
                        for length in list(plan.get("segments", []) or [])
                    ]
                    adjustment = float(plan.get("tail_adjustment", 0) or 0)
                    if adjustment > 0:
                        raw_pieces.append(("shim", adjustment))
                pieces = tuple(
                    ExportPiece(str(kind).lower(), float(length))
                    for kind, length in raw_pieces
                )
                if pieces:
                    plans.append(
                        MemberExportPlan(
                            member_id,
                            "waler",
                            pieces,
                            float(plan.get("gap", 0) or 0),
                            str(result_id),
                        )
                    )
                continue

            if result_type != "support" or result is None:
                continue
            for plan in list(getattr(result, "plans", []) or []):
                member_id = str(getattr(plan, "support_id", "") or "").strip()
                if not member_id or not self._support_plan_visible(item, member_id):
                    continue
                pieces = tuple(
                    ExportPiece(str(kind).lower(), float(length))
                    for kind, length in list(getattr(plan, "pieces", []) or [])
                )
                if pieces:
                    plans.append(
                        MemberExportPlan(
                            member_id,
                            "strut",
                            pieces,
                            float(getattr(plan, "gap", 0) or 0),
                            str(result_id),
                        )
                    )
        return plans

    def _export_visible_results_to_excel(self):
        counts, conflicts = self._visible_result_scope()
        total = counts["waler"] + counts["support"]
        if not total:
            messagebox.showwarning(
                "匯出 Excel",
                "目前沒有勾選為可見的圍令或支撐配置。",
                parent=self.root,
            )
            return
        if conflicts:
            details = "\n".join(
                f"- {kind} {member_id}：{quantity} 個方案"
                for kind, member_id, quantity in conflicts
            )
            messagebox.showwarning(
                "匯出範圍衝突",
                (
                    "同一構件不能同時匯出多個方案：\n\n"
                    f"{details}\n\n請先取消多餘方案的顯示。"
                ),
                parent=self.root,
            )
            return

        try:
            detail_rows = ProjectResultModel(
                result_items=self.result_items,
            ).collect_visible_material_details()
            summary_rows = self._build_material_summary_payload()
        except MaterialDetailBuildError as exc:
            messagebox.showerror(
                "匯出 Excel 失敗",
                f"可見方案含有無法匯出的材料資料：\n{exc}",
                parent=self.root,
            )
            return
        if not detail_rows:
            messagebox.showwarning(
                "匯出 Excel",
                "目前顯示的配置成果沒有可匯出的材料。",
                parent=self.root,
            )
            return

        initial_directory = Path.cwd()
        project_path = getattr(self, "current_project_path", None)
        if project_path is not None and Path(project_path).parent.is_dir():
            initial_directory = Path(project_path).parent
        project_name = self._project_display_name()
        output_path = filedialog.asksaveasfilename(
            parent=self.root,
            title="匯出配置材料明細 Excel",
            initialdir=str(initial_directory),
            initialfile=f"{project_name}_配置材料明細.xlsx",
            defaultextension=".xlsx",
            filetypes=(("Excel 活頁簿", "*.xlsx"), ("所有檔案", "*.*")),
        )
        if not output_path:
            return

        try:
            report = self.excel_result_exporter.export(
                output_path,
                detail_rows,
                summary_rows,
                project_name=project_name,
            )
        except (ExcelResultExportError, OSError) as exc:
            messagebox.showerror(
                "匯出 Excel 失敗",
                str(exc),
                parent=self.root,
            )
            return

        messagebox.showinfo(
            "配置材料明細已匯出",
            (
                f"已匯出 {report.detail_row_count} 筆逐根材料明細，"
                f"共 {self._format_result_value(report.material_quantity)} 件材料。\n"
                f"材料彙總：{report.summary_row_count} 筆。\n\n"
                f"成果檔：\n{report.output_path}"
            ),
            parent=self.root,
        )

    def _export_visible_results_to_dxf(self):
        dxf_state = getattr(self, "dxf_last_import_debug", None)
        try:
            coordinate_system = export_coordinate_system_from_import_state(
                dxf_state
            )
        except DXFResultExportError as exc:
            messagebox.showwarning(
                "缺少 Project → World 座標資訊",
                (
                    f"{exc}\n\n"
                    "目前 schema 3 尚未把座標系獨立保存為 Project metadata；"
                    "請先由 DXF Import 建立明確的 world/local 座標資訊。"
                ),
                parent=self.root,
            )
            return

        try:
            plans = self._visible_dxf_export_plans()
        except (TypeError, ValueError) as exc:
            messagebox.showerror(
                "匯出 DXF 失敗",
                f"可見方案含有無法匯出的分段資料：\n{exc}",
                parent=self.root,
            )
            return
        if not plans:
            messagebox.showwarning(
                "匯出 DXF",
                "目前沒有勾選為可見的圍令或支撐配置。",
                parent=self.root,
            )
            return
        duplicate_members = [
            (role, member_id, quantity)
            for (role, member_id), quantity in Counter(
                (plan.role, plan.member_id) for plan in plans
            ).items()
            if quantity > 1
        ]
        if duplicate_members:
            labels = {"waler": "圍令", "strut": "支撐"}
            details = "\n".join(
                f"- {labels.get(role, role)} {member_id}：{quantity} 個方案"
                for role, member_id, quantity in duplicate_members
            )
            messagebox.showwarning(
                "匯出範圍衝突",
                f"同一構件不能同時匯出多個方案：\n\n{details}\n\n請先取消多餘方案的顯示。",
                parent=self.root,
            )
            return

        source_text = (
            str(dxf_state.get("source_path", "") or "").strip()
            if isinstance(dxf_state, Mapping)
            else ""
        )
        source_hint = Path(source_text) if source_text else None
        dxf_asset = getattr(self, "dxf_asset", None)
        asset_name = (
            str(dxf_asset.get("original_file_name", "") or "").strip()
            if isinstance(dxf_asset, dict)
            else ""
        )
        if source_hint is not None and source_hint.stem:
            source_stem = source_hint.stem
        elif asset_name:
            source_stem = Path(asset_name).stem
        else:
            source_stem = "支撐配置"

        initial_directory = Path.cwd()
        if source_hint is not None and source_hint.parent.is_dir():
            initial_directory = source_hint.parent
        else:
            project_path = getattr(self, "current_project_path", None)
            if project_path is not None and Path(project_path).parent.is_dir():
                initial_directory = Path(project_path).parent

        default_name = f"{source_stem}_支撐配置成果.dxf"
        output_path = filedialog.asksaveasfilename(
            parent=self.root,
            title="建立乾淨支撐配置成果DXF",
            initialdir=str(initial_directory),
            initialfile=default_name,
            defaultextension=".dxf",
            filetypes=(("DXF 圖檔", "*.dxf"), ("所有檔案", "*.*")),
        )
        if not output_path:
            return

        try:
            report = export_results_to_dxf(
                output_path,
                plans,
                self.walers,
                self.struts,
                self.braces,
                coordinate_system,
                background_state=(
                    dxf_state if isinstance(dxf_state, Mapping) else None
                ),
            )
        except (DXFResultExportError, OSError, ezdxf.DXFError) as exc:
            messagebox.showerror(
                "匯出 DXF 失敗",
                str(exc),
                parent=self.root,
            )
            return

        role_labels = {
            "waler": "圍令",
            "strut": "支撐",
            "brace": "斜撐",
            "corner_brace": "角撐",
            "column": "中間柱",
            "beam": "托梁",
            "auxiliary": "輔助線",
            "continuous_wall": "連續壁",
        }
        background_summary = "、".join(
            f"{role_labels.get(role, role)} {count}"
            for role, count in report.background_counts
        ) or "無"
        fallback_summary = ""
        if report.layer_name_fallbacks:
            fallback_summary = "\n圖層名稱替代：\n" + "\n".join(
                f"- {item.original_name or '<空白>'} → {item.output_name}"
                for item in report.layer_name_fallbacks
            )
        messagebox.showinfo(
            "支撐配置成果DXF已建立",
            (
                "已建立乾淨DXF成果檔；原始DXF未被重新儲存或修改。\n"
                f"DXF版本：{report.dxf_version}\n"
                f"座標：原始世界座標；單位：{report.coordinate_units}\n"
                f"背景：{report.background_layer_count}個圖層、"
                f"{report.background_segment_count}條線段\n"
                f"背景內容：{background_summary}\n"
                f"目前 Project 工程線：{report.project_geometry_count} 條\n"
                "Project 圖層：SD_PROJECT_WALER、SD_PROJECT_STRUT、"
                "SD_PROJECT_BRACE\n"
                f"成果圖層：SD_RESULT_WALER、SD_RESULT_SUPPORT\n"
                f"最終結構檢查：{report.final_audit.error_count}項錯誤、"
                f"{report.final_audit.fix_count}項修復\n"
                f"Dimension：{report.actual_dimension_count}／"
                f"{report.dimension_count}\n"
                f"Jack Block Reference：{report.actual_jack_count}／"
                f"{report.jack_count}\n\n"
                f"成果構件：圍令{report.result_waler_count}、"
                f"支撐{report.result_support_count}\n"
                f"成果檔：\n{report.output_path}\n\n"
                f"{report.merge_guidance}"
                f"{fallback_summary}"
            ),
            parent=self.root,
        )

    def _support_config_by_id(self, support_id):
        support_builder, _ = self._ensure_solver_input_builders()
        return support_builder.build_one(self.project_data, support_id)

    @staticmethod
    def _support_plan_piece_rows(plan):
        return [
            (str(piece_type).lower(), int(round(length)))
            for piece_type, length in list(getattr(plan, "pieces", []) or [])
        ]

    @staticmethod
    def _support_kind_label(kind):
        return {
            "steel": "鋼材",
            "shim": "調整塊",
            "jack": "千斤頂",
        }.get(str(kind).lower(), str(kind))

    @staticmethod
    def _support_kind_key(value):
        text = str(value or "").strip().lower()
        return {
            "steel": "steel",
            "鋼材": "steel",
            "shim": "shim",
            "墊片": "shim",
            "調整塊": "shim",
            "jack": "jack",
            "千斤頂": "jack",
        }.get(text, "")

    def _replace_support_plan(self, zoning, support_id, new_plan):
        item = self.result_items.get(zoning)
        solution = item.get("result") if isinstance(item, dict) else None
        plans = list(getattr(solution, "plans", []) or [])
        original = next(
            (
                plan
                for plan in plans
                if str(getattr(plan, "support_id", "")) == str(support_id)
            ),
            None,
        )
        shared_group = str(
            getattr(original, "shared_layout_group", "") or ""
        ).strip()
        if shared_group:
            pieces = self._support_plan_piece_rows(new_plan)
            replaced = False
            for index, plan in enumerate(plans):
                if str(getattr(plan, "shared_layout_group", "") or "").strip() != shared_group:
                    continue
                member_id = str(getattr(plan, "support_id", "") or "")
                config = self._support_config_by_id(member_id)
                if config is None:
                    return False
                plans[index] = support.evaluate_single_support(config, pieces)
                replaced = True
            if replaced:
                solution.plans = plans
                self._recalculate_support_global_solution(solution)
                self._mark_results_updated()
                return True
            return False
        for index, plan in enumerate(plans):
            if str(getattr(plan, "support_id", "")) == str(support_id):
                plans[index] = new_plan
                solution.plans = plans
                self._recalculate_support_global_solution(solution)
                self._mark_results_updated()
                return True
        return False

    @staticmethod
    def _recalculate_support_global_solution(solution):
        return SupportPlanEditing.recalculate_global_solution(solution)

    @staticmethod
    def _find_support_forbidden_zone_hit(plan, config):
        return SupportPlanEditing.find_forbidden_zone_hit(plan, config)

    def _format_support_status(self, plan, config):
        valid = bool(getattr(plan, "valid", False)) and not getattr(plan, "reason", "")
        if valid:
            return "狀態：✅ 合法\n✅ 所有檢查均符合規範"

        lines = ["狀態：❌ 不合法"]
        reason = str(getattr(plan, "reason", "") or "").strip()
        if reason:
            for part in reason.split(";"):
                part = part.strip()
                if part:
                    lines.append(f"❌ {part}")

        zone_hit = self._find_support_forbidden_zone_hit(plan, config)
        if zone_hit:
            joint, zone_start, zone_end, zone_type = zone_hit
            lines.extend([
                "",
                "違規位置說明",
                f"接頭位置：{self._format_result_value(joint)} mm",
                f"禁止區：{self._format_result_value(zone_start)} ~ {self._format_result_value(zone_end)} mm",
                f"類型：{zone_type}",
            ])
        return "\n".join(lines)

    def _format_support_plan_breakdown(self, plan, config, neighbor_checks=None, solution=None):
        breakdown = dict(getattr(plan, "breakdown", {}) or {})
        short_penalty = breakdown.get("short_penalty", 0.0)
        joint_penalty = breakdown.get("joint_penalty", 0.0)
        gap_penalty = breakdown.get("gap_penalty", 0.0)
        jack_edge_penalty = breakdown.get("jack_edge_penalty", 0.0)
        invalid_penalty = breakdown.get("invalid_penalty", 0.0)
        steel_lengths = [length for kind, length in getattr(plan, "pieces", []) if kind == "steel"]
        short_count = sum(1 for length in steel_lengths if length < 4000)
        joint_count = len(getattr(plan, "joints", []) or [])
        gap_delta = abs(getattr(plan, "gap", 0) - support.TARGET_GAP)
        quality_score = (
            float(short_penalty)
            + float(joint_penalty)
            + float(gap_penalty)
            + float(jack_edge_penalty)
        )
        region_group_penalty = sum(float(item.get("penalty", 0.0) or 0.0) for item in neighbor_checks or [])
        material_ratio_penalty = float(getattr(solution, "material_ratio_penalty", 0.0) or 0.0) if solution is not None else 0.0
        group_penalty = region_group_penalty + material_ratio_penalty
        ranking_score = quality_score + float(invalid_penalty) + group_penalty
        lines = [
            f"支撐：{getattr(plan, 'support_id', '')}",
            f"總長：{self._format_result_value(getattr(config, 'total_length', '無資料'))} mm",
            f"目標千斤頂區域：{getattr(config, 'target_jack_region', '無資料')}",
            "",
            self._format_support_status(plan, config),
            "",
            f"千斤頂中心：{self._format_result_value(getattr(plan, 'jack_center', '無資料'))}",
            f"千斤頂區域：{getattr(plan, 'jack_region_id', '無資料')}",
            f"接頭位置：{self._format_result_list(getattr(plan, 'joints', []))}",
            f"餘長(mm)：{self._format_result_value(getattr(plan, 'gap', '無資料'))}",
            "",
            "【品質評分】",
            f"短鋼材：{short_count} × 8000 = {self._format_result_value(short_penalty)}",
            f"接頭數：{joint_count} × 1200 = {self._format_result_value(joint_penalty)}",
            f"餘長：|{self._format_result_value(getattr(plan, 'gap', 0))} - {support.TARGET_GAP}| × 20 = {self._format_result_value(gap_penalty)}",
            f"千斤頂靠近端部：{self._format_result_value(jack_edge_penalty)}",
            "-" * 50,
            f"品質分數：{self._format_result_value(quality_score)}",
            "",
            "【群組檢查】",
        ]
        if neighbor_checks:
            for item in neighbor_checks:
                relation = item.get("relation", "相鄰支撐")
                lines.extend([
                    f"與{relation}：{item.get('support_id', '')}",
                    f"千斤頂距離：{self._format_result_value(item.get('distance', '無資料'))} mm",
                    "✅ 合法" if item.get("ok") else f"❌ 小於規定 {support.MIN_JACK_DISTANCE_BETWEEN_SUPPORTS} mm",
                    (
                        f"區域差異：|{item.get('current_region')} - {item.get('neighbor_region')}| × 3000 "
                        f"= {self._format_result_value(item.get('region_penalty', 0))}"
                    ),
                    "",
                ])
        else:
            lines.append("無相鄰支撐")
            lines.append("")
        lines.extend([
            "【求解器排序分數】",
            f"品質分數：{self._format_result_value(quality_score)}",
            f"不合法懲罰：{self._format_result_value(invalid_penalty)}",
            f"Jack Region 群組懲罰：{self._format_result_value(region_group_penalty)}",
            f"材料比例懲罰：{self._format_result_value(material_ratio_penalty)}",
            f"群組懲罰合計：{self._format_result_value(group_penalty)}",
            "-" * 50,
            f"排序用總分：{self._format_result_value(ranking_score)}",
        ])
        if solution is not None:
            lines.extend(self._format_support_global_analysis_lines(solution))
        return "\n".join(lines)

    def _support_neighbor_penalty_for_plan(self, zoning, support_id):
        item = self.result_items.get(zoning)
        solution = item.get("result") if isinstance(item, dict) else None
        plans = list(getattr(solution, "plans", []) or [])
        if not any(
            str(getattr(plan, "support_id", "")) == str(support_id)
            for plan in plans
        ):
            return 0.0, []
        return SupportPlanEditing.neighbor_checks(solution, support_id)

    def _open_support_plan_editor(self, zoning, support_id):
        item = self.result_items.get(zoning)
        solution = item.get("result") if isinstance(item, dict) else None
        plan = next(
            (
                plan
                for plan in list(getattr(solution, "plans", []) or [])
                if str(getattr(plan, "support_id", "")) == str(support_id)
            ),
            None,
        )
        config = self._support_config_by_id(support_id)
        if plan is None or config is None:
            messagebox.showwarning("支撐編輯器", "找不到支撐方案或支撐設定資料。")
            return
        allowed_steel_lengths = support.configured_steel_lengths(config)

        editor = tk.Toplevel(self.root)
        editor.title(f"支撐配置編輯器 - {zoning} / {support_id}")
        editor.transient(self.root)
        configure_responsive_dialog(
            editor,
            self.root,
            preferred_width=780,
            preferred_height=760,
            minimum_width=680,
            minimum_height=520,
        )
        footer_frame = ttk.Frame(editor)
        footer_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        ttk.Button(
            footer_frame,
            text="關閉",
            command=editor.destroy,
        ).pack(side="right")
        editor.protocol("WM_DELETE_WINDOW", editor.destroy)

        status_var = tk.StringVar(value="狀態：檢查中...")
        ttk.Label(
            editor,
            text=(
                f"支撐：{support_id}\n"
                f"總長：{config.total_length} mm\n"
                f"目標千斤頂區域：{config.target_jack_region}"
            ),
            font=("Microsoft JhengHei", 10, "bold"),
            justify="left",
        ).pack(fill="x", padx=10, pady=(10, 4))

        ttk.Label(
            editor,
            textvariable=status_var,
            font=("Microsoft JhengHei", 11, "bold"),
        ).pack(fill="x", padx=10, pady=(0, 6))

        ttk.Label(
            editor,
            text=(
                "雙擊「類型」可選鋼材／調整塊／千斤頂；雙擊「長度」可修改。"
                "鋼材長度必須存在於可用鋼材長度；調整塊使用下拉選單；千斤頂長度固定。"
            ),
            wraplength=680,
        ).pack(fill="x", padx=10, pady=(10, 6))

        table_frame = ttk.Frame(editor)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        columns = ("index", "type", "length")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        tree.heading("index", text="段次")
        tree.heading("type", text="類型")
        tree.heading("length", text="長度(mm)")
        tree.column("index", width=70, anchor="center", stretch=False)
        tree.column("type", width=130, anchor="center")
        tree.column("length", width=130, anchor="center")
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=y_scroll.set)

        button_frame = ttk.Frame(editor)
        button_frame.pack(fill="x", padx=10, pady=(0, 6))

        summary_text = scrolledtext.ScrolledText(
            editor,
            height=10,
            wrap="word",
            font=("Microsoft JhengHei", 10),
            state="disabled",
        )
        summary_text.pack(fill="both", padx=10, pady=(0, 8))

        editing_entry = {"widget": None}

        def normalize_kind(value):
            return self._support_kind_key(value)

        def rows():
            data = []
            for child in tree.get_children(""):
                kind = normalize_kind(tree.set(child, "type"))
                raw_length = tree.set(child, "length")
                try:
                    length = int(round(float(raw_length)))
                except ValueError:
                    return None
                if kind not in ("steel", "shim", "jack") or length <= 0:
                    return None
                if kind == "jack":
                    length = support.JACK_LENGTH
                    tree.set(child, "length", length)
                data.append((kind, length))
            return data

        def refresh_rows(piece_rows):
            tree.delete(*tree.get_children(""))
            for index, (kind, length) in enumerate(piece_rows, start=1):
                tree.insert("", "end", iid=f"piece_{index}", values=(index, self._support_kind_label(kind), length))

        def renumber():
            for index, child in enumerate(tree.get_children(""), start=1):
                tree.set(child, "index", index)

        def validate_piece_inputs(piece_rows):
            if piece_rows is None:
                return "❌ 類型或長度格式錯誤"
            jack_count = sum(1 for kind, _length in piece_rows if kind == "jack")
            if jack_count != 1:
                return "❌ 千斤頂數量不是 1"
            for kind, length in piece_rows:
                if kind == "steel" and length not in allowed_steel_lengths:
                    return f"❌ 鋼材長度不合法：{length} mm"
                if kind == "shim" and length not in support.SHIM_LENGTHS:
                    return f"❌ 調整塊長度不合法：{length} mm"
                if kind == "jack" and length != support.JACK_LENGTH:
                    return f"❌ 千斤頂長度必須固定為 {support.JACK_LENGTH} mm"
            return None

        def evaluate_and_refresh():
            piece_rows = rows()
            if piece_rows is None:
                status_var.set("狀態：❌ 類型或長度格式錯誤")
                summary_text.configure(state="normal")
                summary_text.delete("1.0", "end")
                summary_text.insert("1.0", "❌ 類型或長度格式錯誤，請修正表格內容。")
                summary_text.configure(state="disabled")
                return
            input_error = validate_piece_inputs(piece_rows)
            new_plan = support.evaluate_single_support(config, piece_rows)
            self._replace_support_plan(zoning, support_id, new_plan)
            neighbor_checks = self._support_neighbor_penalty_for_plan(zoning, support_id)

            valid = bool(getattr(new_plan, "valid", False)) and not getattr(new_plan, "reason", "") and not input_error
            if valid:
                status_var.set("狀態：✅ 合法")
            else:
                reason = input_error or getattr(new_plan, "reason", "") or "不合法"
                status_var.set(f"狀態：❌ {reason}")

            summary_text.configure(state="normal")
            summary_text.delete("1.0", "end")
            summary_text.insert("1.0", self._format_support_plan_breakdown(
                new_plan,
                config,
                neighbor_checks,
                solution=solution,
            ))
            summary_text.configure(state="disabled")
            self._refresh_results_tree(selected_id=self._support_plan_iid(zoning, support_id))
            parent_id = self.results_tree.parent(self._support_plan_iid(zoning, support_id)) if self.results_tree.exists(self._support_plan_iid(zoning, support_id)) else ""
            if parent_id:
                self.results_tree.item(parent_id, open=True)
            self.update_preview(preserve_view=True)

        def add_piece(kind, length):
            index = len(tree.get_children("")) + 1
            if kind == "jack":
                length = support.JACK_LENGTH
            tree.insert("", "end", iid=f"piece_{index}", values=(index, self._support_kind_label(kind), length))
            evaluate_and_refresh()

        def delete_piece():
            selected = tree.selection()
            if not selected:
                return
            tree.delete(selected[0])
            renumber()
            evaluate_and_refresh()

        def move_piece(delta):
            selected = tree.selection()
            if not selected:
                return
            child = selected[0]
            children = list(tree.get_children(""))
            index = children.index(child)
            new_index = index + delta
            if not 0 <= new_index < len(children):
                return
            tree.move(child, "", new_index)
            renumber()
            evaluate_and_refresh()

        default_steel_length = allowed_steel_lengths[0] if allowed_steel_lengths else 5000
        ttk.Button(
            button_frame,
            text="新增鋼材",
            command=lambda: add_piece("steel", default_steel_length),
        ).pack(side="left", padx=(0, 5))
        ttk.Button(button_frame, text="新增調整塊", command=lambda: add_piece("shim", 150)).pack(side="left", padx=5)
        ttk.Button(button_frame, text="新增千斤頂", command=lambda: add_piece("jack", support.JACK_LENGTH)).pack(side="left", padx=5)
        ttk.Button(button_frame, text="刪除構件", command=delete_piece).pack(side="left", padx=5)
        ttk.Button(button_frame, text="上移", command=lambda: move_piece(-1)).pack(side="left", padx=5)
        ttk.Button(button_frame, text="下移", command=lambda: move_piece(1)).pack(side="left", padx=5)

        def finish_edit(row_id, column, widget):
            if not widget.winfo_exists():
                return
            value = widget.get().strip()
            widget.destroy()
            editing_entry["widget"] = None
            if column == "type":
                normalized = normalize_kind(value)
                if normalized not in ("steel", "shim", "jack"):
                    messagebox.showerror("輸入錯誤", "類型必須是鋼材、調整塊或千斤頂。", parent=editor)
                    return
                tree.set(row_id, "type", self._support_kind_label(normalized))
                if normalized == "jack":
                    tree.set(row_id, "length", support.JACK_LENGTH)
                elif normalized == "shim":
                    current_length = self._to_number(tree.set(row_id, "length"))
                    if current_length not in support.SHIM_LENGTHS:
                        tree.set(row_id, "length", support.SHIM_LENGTHS[0])
            elif column == "length":
                kind = normalize_kind(tree.set(row_id, "type"))
                if kind == "jack":
                    tree.set(row_id, "length", support.JACK_LENGTH)
                    evaluate_and_refresh()
                    return
                try:
                    length = int(round(float(value)))
                except ValueError:
                    messagebox.showerror("輸入錯誤", "長度(mm) 必須是數字。", parent=editor)
                    return
                if length <= 0:
                    messagebox.showerror("輸入錯誤", "長度(mm) 必須大於 0。", parent=editor)
                    return
                if kind == "steel" and length not in allowed_steel_lengths:
                    messagebox.showerror(
                        "輸入錯誤",
                        f"鋼材長度必須存在於可用鋼材長度：{allowed_steel_lengths}",
                        parent=editor,
                    )
                    return
                if kind == "shim" and length not in support.SHIM_LENGTHS:
                    messagebox.showerror(
                        "輸入錯誤",
                        f"調整塊長度必須存在於可用調整塊長度：{support.SHIM_LENGTHS}",
                        parent=editor,
                    )
                    return
                tree.set(row_id, "length", length)
            evaluate_and_refresh()

        def start_edit(event):
            if tree.identify_region(event.x, event.y) != "cell":
                return
            row_id = tree.identify_row(event.y)
            column_id = tree.identify_column(event.x)
            column = self._tree_column_key(tree, column_id)
            if not row_id or column not in ("type", "length"):
                return
            if column == "length" and normalize_kind(tree.set(row_id, "type")) == "jack":
                messagebox.showinfo("千斤頂長度固定", f"千斤頂長度固定為 {support.JACK_LENGTH} mm，不可修改。", parent=editor)
                return
            bbox = tree.bbox(row_id, column_id)
            if not bbox:
                return
            if editing_entry["widget"] is not None and editing_entry["widget"].winfo_exists():
                editing_entry["widget"].destroy()
            x, y, width, height = bbox
            if column == "type":
                widget = ttk.Combobox(tree, values=("鋼材", "調整塊", "千斤頂"), state="readonly")
                widget.set(tree.set(row_id, column))
            elif normalize_kind(tree.set(row_id, "type")) == "shim":
                widget = ttk.Combobox(tree, values=[str(value) for value in support.SHIM_LENGTHS], state="readonly")
                widget.set(tree.set(row_id, column))
            else:
                widget = tk.Entry(tree)
                widget.insert(0, tree.set(row_id, column))
            widget.place(x=x, y=y, width=width, height=height)
            widget.focus_set()
            widget.bind("<Return>", lambda _event: finish_edit(row_id, column, widget))
            widget.bind("<FocusOut>", lambda _event: finish_edit(row_id, column, widget))
            if isinstance(widget, ttk.Combobox):
                widget.bind("<<ComboboxSelected>>", lambda _event: finish_edit(row_id, column, widget))
            editing_entry["widget"] = widget

        tree.bind("<Double-1>", start_edit)
        refresh_rows(self._support_plan_piece_rows(plan))
        evaluate_and_refresh()

    def _open_waler_plan_editor(self, result_id):
        item = self.result_items.get(result_id)
        if not item or item.get("type") != "waler":
            return

        result = item.get("result") or {}
        plan = result.get("selected_plan") or {}
        waler_id = str(result.get("waler_id", "")).strip()
        option_index = result.get("option_index")
        option_label = (
            f"方案{option_index}"
            if option_index is not None
            else str(result_id).replace(f"{waler_id}-", "")
        )
        ratio_targets = result.get("ratio_targets") or plan.get("ratio_targets")
        material_spec = str(result.get("material_spec", "") or "").strip()
        allowed_steel_lengths = InventoryLookup(
            self._ensure_project_data().inventory
        ).purchasable_lengths(material_spec, "圍令")
        if not list(plan.get("segments", []) or []):
            messagebox.showwarning(
                "圍令方案編輯",
                "選取的圍令方案沒有可編輯的鋼材分段資料。",
                parent=self.root,
            )
            return

        editor = tk.Toplevel(self.root)
        editor.title(f"圍令方案編輯 - {waler_id} / {option_label}")
        editor.transient(self.root)
        configure_responsive_dialog(
            editor,
            self.root,
            preferred_width=720,
            preferred_height=720,
            minimum_width=620,
            minimum_height=500,
        )
        footer_frame = ttk.Frame(editor)
        footer_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        ttk.Button(
            footer_frame,
            text="關閉",
            command=editor.destroy,
        ).pack(side="right")
        editor.protocol("WM_DELETE_WINDOW", editor.destroy)

        ttk.Label(
            editor,
            text=(
                "雙擊「料長(mm)」可更換鋼材；也可新增、刪除、上移或下移。"
                "每次修改都會立即檢查接頭禁止區、完成長度與庫存，並重新計分及更新預覽。"
            ),
            wraplength=660,
        ).pack(fill="x", padx=10, pady=(10, 6))

        status_var = tk.StringVar(value="方案狀態：檢查中")
        status_label = ttk.Label(
            editor,
            textvariable=status_var,
            font=("Microsoft JhengHei", 11, "bold"),
        )
        status_label.pack(fill="x", padx=10, pady=(0, 8))

        table_frame = ttk.Frame(editor)
        table_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("segment_index", "length")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        tree.heading("segment_index", text="段次")
        tree.heading("length", text="料長(mm)")
        tree.column("segment_index", width=80, minwidth=60, anchor="center", stretch=False)
        tree.column("length", width=160, minwidth=100, anchor="center")
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=y_scroll.set)

        button_frame = ttk.Frame(editor)
        button_frame.pack(fill="x", padx=10, pady=(0, 6))

        summary_text = scrolledtext.ScrolledText(
            editor,
            height=10,
            wrap="word",
            font=("Microsoft JhengHei", 10),
            state="disabled",
        )
        summary_text.pack(fill="both", padx=10, pady=(0, 8))

        editing_entry = {"widget": None}

        def current_segments():
            values = []
            for child_id in tree.get_children(""):
                raw_value = tree.set(child_id, "length")
                try:
                    value = int(round(float(raw_value)))
                except ValueError:
                    return None
                if value <= 0:
                    return None
                values.append(value)
            return values

        def refresh_table(segments):
            tree.delete(*tree.get_children(""))
            for index, length in enumerate(segments, start=1):
                tree.insert("", "end", values=(index, length))

        def renumber():
            for index, child_id in enumerate(tree.get_children(""), start=1):
                tree.set(child_id, "segment_index", index)

        def update_summary():
            latest_result = self.result_items.get(result_id, {}).get("result") or {}
            latest_plan = latest_result.get("selected_plan") or {}
            legality = latest_plan.get("legality") or {}
            if legality.get("summary"):
                status_summary = legality["summary"]
                is_valid = bool(legality.get("valid"))
            else:
                is_valid = bool(latest_plan.get("valid", False))
                status_summary = "✅ 合法" if is_valid else "❌ 不合法"
            status_var.set(f"方案狀態：{status_summary}")
            status_label.configure(
                foreground="#2e7d32" if is_valid else "#c62828"
            )
            steel_length = sum(latest_plan.get("segments", []) or [])
            assembled_length = (
                steel_length
                + int(latest_plan.get("tail_adjustment", 0) or 0)
                + int(latest_plan.get("gap", 0) or 0)
            )
            required_length = latest_result.get(
                "required_length",
                latest_plan.get("required_length", "無資料"),
            )
            modified_text = " [已修改]" if latest_result.get("manual_modified") else ""
            lines = [
                f"{waler_id}-{option_label}{modified_text}",
                f"方案狀態：{status_summary}",
                (
                    f"鋼材總長：{self._format_result_value(steel_length)} mm；"
                    f"完成長度：{self._format_result_value(assembled_length)} mm；"
                    f"圍令需求長度：{self._format_result_value(required_length)} mm"
                ),
                "",
                self._format_waler_score_breakdown(
                    latest_plan,
                    option_index=option_index,
                    ratio_targets=ratio_targets,
                    segment_counts=latest_plan.get("segment_counts"),
                ),
            ]
            errors = list(latest_plan.get("errors", []) or [])
            legality_details = list(legality.get("details", []) or [])
            if legality_details:
                lines.extend(["", "合法性檢查：", *legality_details])
            legality_warnings = list(legality.get("warnings", []) or [])
            if legality_warnings:
                lines.extend(["", "庫存檢查：", *[f"- {warning}" for warning in legality_warnings]])
            if errors:
                lines.extend(["", "提醒：", *[f"- {error}" for error in errors]])
            summary_text.configure(state="normal")
            summary_text.delete("1.0", "end")
            summary_text.insert("1.0", "\n".join(lines))
            summary_text.configure(state="disabled")

        def apply_segments(segments):
            self._apply_waler_plan_segments(result_id, segments)
            self._refresh_results_tree(selected_id=result_id)
            parent_id = (
                self.results_tree.parent(result_id)
                if self.results_tree.exists(result_id)
                else ""
            )
            if parent_id:
                self.results_tree.item(parent_id, open=True)
            self.update_preview(preserve_view=True)
            update_summary()

        def apply_tree_segments():
            segments = current_segments()
            if segments is not None:
                apply_segments(segments)

        def add_segment():
            try:
                length = int(selected_length_var.get())
            except (TypeError, ValueError):
                messagebox.showwarning(
                    "新增鋼材",
                    "目前沒有可新增的圍令庫存料長。",
                    parent=editor,
                )
                return
            child_id = tree.insert(
                "",
                "end",
                values=(len(tree.get_children("")) + 1, length),
            )
            tree.selection_set(child_id)
            tree.focus(child_id)
            apply_tree_segments()

        def delete_segment():
            selected = tree.selection()
            if not selected:
                return
            children = list(tree.get_children(""))
            index = children.index(selected[0])
            tree.delete(selected[0])
            renumber()
            remaining = list(tree.get_children(""))
            if remaining:
                next_id = remaining[min(index, len(remaining) - 1)]
                tree.selection_set(next_id)
                tree.focus(next_id)
            apply_tree_segments()

        def move_segment(delta):
            selected = tree.selection()
            if not selected:
                return
            child_id = selected[0]
            children = list(tree.get_children(""))
            index = children.index(child_id)
            new_index = index + delta
            if not 0 <= new_index < len(children):
                return
            tree.move(child_id, "", new_index)
            renumber()
            tree.selection_set(child_id)
            tree.focus(child_id)
            apply_tree_segments()

        selected_length_var = tk.StringVar(
            value=str(allowed_steel_lengths[0]) if allowed_steel_lengths else ""
        )
        ttk.Label(button_frame, text="新增料長：").pack(side="left")
        length_selector = ttk.Combobox(
            button_frame,
            textvariable=selected_length_var,
            values=[str(length) for length in allowed_steel_lengths],
            state="readonly" if allowed_steel_lengths else "disabled",
            width=10,
        )
        length_selector.pack(side="left", padx=(0, 5))
        ttk.Button(
            button_frame,
            text="新增鋼材",
            command=add_segment,
            state="normal" if allowed_steel_lengths else "disabled",
        ).pack(side="left", padx=(0, 5))
        ttk.Button(
            button_frame,
            text="刪除鋼材",
            command=delete_segment,
        ).pack(side="left", padx=5)
        ttk.Button(
            button_frame,
            text="上移",
            command=lambda: move_segment(-1),
        ).pack(side="left", padx=5)
        ttk.Button(
            button_frame,
            text="下移",
            command=lambda: move_segment(1),
        ).pack(side="left", padx=5)

        def finish_edit(row_id, widget):
            if not widget.winfo_exists():
                return
            new_value = widget.get().strip()
            widget.destroy()
            editing_entry["widget"] = None
            try:
                parsed = int(round(float(new_value)))
            except ValueError:
                messagebox.showerror("輸入錯誤", "料長(mm) 必須是大於 0 的數字", parent=editor)
                return
            if parsed <= 0:
                messagebox.showerror("輸入錯誤", "料長(mm) 必須大於 0", parent=editor)
                return
            if parsed not in allowed_steel_lengths:
                messagebox.showerror(
                    "輸入錯誤",
                    f"鋼材料長必須存在於可用庫存料長：{allowed_steel_lengths}",
                    parent=editor,
                )
                return
            current_value = int(round(float(tree.set(row_id, "length"))))
            if parsed == current_value:
                return
            tree.set(row_id, "length", parsed)
            apply_tree_segments()

        def start_edit(event):
            if tree.identify_region(event.x, event.y) != "cell":
                return
            row_id = tree.identify_row(event.y)
            column_id = tree.identify_column(event.x)
            if not row_id or column_id != "#2":
                return
            bbox = tree.bbox(row_id, column_id)
            if not bbox:
                return
            if editing_entry["widget"] is not None and editing_entry["widget"].winfo_exists():
                editing_entry["widget"].destroy()
            x, y, width, height = bbox
            widget = ttk.Combobox(
                tree,
                values=[str(length) for length in allowed_steel_lengths],
                state="readonly",
            )
            widget.set(tree.set(row_id, "length"))
            widget.place(x=x, y=y, width=width, height=height)
            widget.focus_set()
            widget.bind("<Return>", lambda _event: finish_edit(row_id, widget))
            widget.bind("<FocusOut>", lambda _event: finish_edit(row_id, widget))
            widget.bind(
                "<<ComboboxSelected>>",
                lambda _event: finish_edit(row_id, widget),
            )
            editing_entry["widget"] = widget

        tree.bind("<Double-1>", start_edit)
        refresh_table(plan.get("segments", []) or [])
        update_summary()

    @staticmethod
    def _result_group_iid(result_type, group_id):
        return f"__result_group__:{result_type}:{group_id}"

    @staticmethod
    def _is_result_group_iid(item_id):
        return str(item_id).startswith("__result_group__:")

    @staticmethod
    def _support_plan_iid(zoning, support_id):
        return f"__support_plan__:{zoning}:{support_id}"

    @staticmethod
    def _is_support_plan_iid(item_id):
        return str(item_id).startswith("__support_plan__:")

    @staticmethod
    def _parse_support_plan_iid(item_id):
        parts = str(item_id).split(":", 2)
        if len(parts) != 3:
            return "", ""
        return parts[1], parts[2]

    def _get_result_tree_info(self, result_id, item):
        result_type = item.get("type", "")
        result = item.get("result")

        if result_type == "waler":
            waler_id = ProjectResultModel.waler_result_identity(
                result_id,
                item,
            )
            option_index = None
            if isinstance(result, dict):
                option_index = result.get("option_index")
            if option_index is None:
                child_label = str(result_id).replace(f"{waler_id}-", "")
            elif isinstance(result, dict) and result.get("global_selected"):
                child_label = f"全域方案{option_index}"
            elif (
                isinstance(result, dict)
                and result.get("result_series") == "single"
            ):
                child_label = f"單支方案{option_index}"
            else:
                child_label = f"方案{option_index}"
            if isinstance(result, dict) and result.get("manual_modified"):
                plan = result.get("selected_plan") or {}
                legality = plan.get("legality") or {}
                is_valid = legality.get("valid", plan.get("valid", False))
                child_label += f" [已修改] {'✅' if is_valid else '❌'}"
            try:
                option_sort = int(option_index)
            except (TypeError, ValueError):
                option_sort = 9999
            series_sort = (
                0
                if isinstance(result, dict) and result.get("global_selected")
                else 1
            )
            return {
                "group_iid": self._result_group_iid("waler", waler_id),
                "group_id": waler_id,
                "group_label": waler_id,
                "child_label": child_label,
                "type_label": "圍令",
                "sort_key": (
                    0,
                    waler_id,
                    series_sort,
                    option_sort,
                    str(result_id),
                ),
            }

        group_id = str(result_id).split("-方案", 1)[0]
        child_label = str(result_id).replace(f"{group_id}-", "")
        if child_label == str(result_id):
            child_label = "配置"
        return {
            "group_iid": self._result_group_iid(result_type or "support", group_id),
            "group_id": group_id,
            "group_label": group_id,
            "child_label": child_label,
            "type_label": "支撐" if result_type == "support" else str(result_type),
            "sort_key": (
                {"waler": 0, "support": 1}.get(result_type, 2),
                group_id,
                str(result_id),
            ),
        }

    def _get_result_group_entries(self, group_iid):
        grouped_entries = []
        for result_id, item in self.result_items.items():
            info = self._get_result_tree_info(result_id, item)
            if info["group_iid"] == group_iid:
                grouped_entries.append((result_id, item, info))
        grouped_entries.sort(key=lambda entry: entry[2]["sort_key"])
        return grouped_entries

    @staticmethod
    def _result_group_visible_mark(items):
        if not items:
            return "☐"
        visible_count = sum(1 for item in items if item.get("visible", True))
        if visible_count == len(items):
            return "☑"
        if visible_count == 0:
            return "☐"
        return "▣"

    @staticmethod
    def _result_item_visible_mark(item):
        return "☑" if item.get("visible", True) else "☐"

    @staticmethod
    def _support_plan_ids(item):
        result = item.get("result") if isinstance(item, dict) else None
        return [
            str(getattr(plan, "support_id", "") or "").strip()
            for plan in list(getattr(result, "plans", []) or [])
            if str(getattr(plan, "support_id", "") or "").strip()
        ]

    def _support_plan_visible(self, item, support_id):
        if not isinstance(item, dict):
            return False
        visibility = item.setdefault("support_visibility", {})
        support_id = str(support_id)
        if support_id not in visibility:
            visibility[support_id] = item.get("visible", True)
        return bool(visibility.get(support_id, True))

    def _support_group_visible_mark(self, group_items):
        visible_states = []
        for item in group_items:
            for support_id in self._support_plan_ids(item):
                visible_states.append(self._support_plan_visible(item, support_id))
        if not visible_states:
            return "☐"
        if all(visible_states):
            return "☑"
        if not any(visible_states):
            return "☐"
        return "▣"

    def _toggle_result_group_visibility(self, group_iid):
        grouped_entries = self._get_result_group_entries(group_iid)
        if not grouped_entries:
            return

        if all(item.get("type") == "support" for _result_id, item, _info in grouped_entries):
            all_support_ids = [
                (item, support_id)
                for _result_id, item, _info in grouped_entries
                for support_id in self._support_plan_ids(item)
            ]
            make_visible = not all(
                self._support_plan_visible(item, support_id)
                for item, support_id in all_support_ids
            )
            for item, support_id in all_support_ids:
                item.setdefault("support_visibility", {})[support_id] = make_visible
            for _result_id, item, _info in grouped_entries:
                item["visible"] = make_visible
            self._mark_project_dirty("結果顯示狀態已變更")
            self._refresh_results_tree(selected_id=group_iid)
            self.update_preview(preserve_view=True)
            return

        make_visible = not all(item.get("visible", True) for _result_id, item, _info in grouped_entries)
        for _result_id, item, _info in grouped_entries:
            item["visible"] = make_visible

        self._mark_project_dirty("結果顯示狀態已變更")
        self._refresh_results_tree(selected_id=group_iid)
        self.update_preview(preserve_view=True)

    def _toggle_result_visibility(self, result_id):
        item = self.result_items.get(result_id)
        if item is None:
            return

        item["visible"] = not item.get("visible", True)
        self._mark_project_dirty("結果顯示狀態已變更")
        self._refresh_results_tree(selected_id=result_id)
        self.update_preview(preserve_view=True)

    def _toggle_support_plan_visibility(self, zoning, support_id):
        item = self.result_items.get(zoning)
        if not item or item.get("type") != "support":
            return
        visibility = item.setdefault("support_visibility", {})
        support_id = str(support_id)
        visibility[support_id] = not self._support_plan_visible(item, support_id)
        item["visible"] = any(
            self._support_plan_visible(item, plan_id)
            for plan_id in self._support_plan_ids(item)
        )
        self._mark_project_dirty("結果顯示狀態已變更")
        self._refresh_results_tree(selected_id=self._support_plan_iid(zoning, support_id))
        parent_id = self.results_tree.parent(self._support_plan_iid(zoning, support_id)) if self.results_tree.exists(self._support_plan_iid(zoning, support_id)) else ""
        if parent_id:
            self.results_tree.item(parent_id, open=True)
        self.update_preview(preserve_view=True)

    _format_result_value = staticmethod(format_result_value)
    _format_result_list = staticmethod(format_result_list)
    _format_waler_score_breakdown = staticmethod(
        format_waler_score_breakdown
    )

    def _recalculate_waler_plan(
        self,
        base_plan,
        segments,
        ratio_targets=None,
        *,
        waler_id=None,
        result_context=None,
    ):
        return WalerPlanEditing(self._ensure_project_data()).recalculate(
            base_plan,
            segments,
            ratio_targets,
            waler_id=waler_id,
            result_context=result_context,
        )

    def _apply_waler_plan_segments(self, result_id, segments):
        item = self.result_items.get(result_id)
        if not item or item.get("type") != "waler":
            raise ValueError("找不到要修改的圍令方案")
        result = item.get("result")
        if not isinstance(result, dict):
            raise ValueError("圍令方案資料格式不正確")

        waler_id = str(result.get("waler_id", "") or "").strip()
        base_plan = result.get("selected_plan") or {}
        ratio_targets = result.get("ratio_targets") or base_plan.get("ratio_targets")
        edited_plan = self._recalculate_waler_plan(
            base_plan,
            segments,
            ratio_targets=ratio_targets,
            waler_id=waler_id,
            result_context=result,
        )
        edited_plan.pop("custom", None)
        result["selected_plan"] = edited_plan
        result["ratio_targets"] = ratio_targets or edited_plan.get("ratio_targets")
        result["manual_modified"] = True
        for legacy_key in ("custom", "custom_label", "source_result_id"):
            result.pop(legacy_key, None)
        self._mark_results_updated()
        return edited_plan

    def _get_waler_required_length(self, waler_id, result=None):
        return WalerPlanEditing(self._ensure_project_data()).required_length(
            waler_id,
            result,
        )

    def _validate_waler_plan(
        self,
        *,
        waler_id,
        segments,
        joints,
        result=None,
    ):
        return WalerPlanEditing(self._ensure_project_data()).validate(
            waler_id=waler_id,
            segments=segments,
            joints=joints,
            result=result,
        )

    @staticmethod
    def _format_support_global_analysis_lines(solution):
        analysis = dict(getattr(solution, "material_ratio_analysis", {}) or {})
        counts = dict(analysis.get("counts", {}) or {})
        ratios = dict(analysis.get("ratios", {}) or {})
        targets = dict(analysis.get("targets", {}) or {})
        total = int(analysis.get("classified_total", 0) or 0)
        deviation = float(analysis.get("ratio_deviation", 0.0) or 0.0)
        weight = float(analysis.get("weight", support.SUPPORT_MATERIAL_RATIO_WEIGHT) or 0.0)
        penalty = float(analysis.get("penalty", 0.0) or 0.0)
        min_distance = getattr(solution, "min_jack_distance", None)
        jack_distance_ok = (
            min_distance is None
            or float(min_distance) >= support.MIN_JACK_DISTANCE_BETWEEN_SUPPORTS
        )

        def percent(value):
            return f"{float(value):.2%}"

        min_distance = getattr(solution, "min_jack_distance", None)
        min_distance_text = (
            SupportInputApp._format_result_value(min_distance)
            if min_distance is not None
            else "無資料"
        )
        jack_distance_ok = (
            min_distance is None
            or float(min_distance) >= support.MIN_JACK_DISTANCE_BETWEEN_SUPPORTS
        )
        lines = [
            "",
            "材料比例",
            "類別　實際比例　　　　　　目標比例",
        ]
        for key, label in (("short", "短料"), ("mid", "中料"), ("long", "長料")):
            lines.append(
                f"{label}　{percent(ratios.get(key, 0.0))}"
                f"（{int(counts.get(key, 0) or 0)}支/{total}支）　"
                f"{percent(targets.get(key, 0.0))}"
            )
        lines.extend([
            "",
            "比例偏差：",
            f"|{percent(ratios.get('short', 0.0))} - {percent(targets.get('short', 0.0))}|",
            f"+ |{percent(ratios.get('mid', 0.0))} - {percent(targets.get('mid', 0.0))}|",
            f"+ |{percent(ratios.get('long', 0.0))} - {percent(targets.get('long', 0.0))}|",
            f"= {deviation:.4f}",
            "",
            "材料比例懲罰：",
            f"{deviation:.4f} × {weight:.0f} = {penalty:.2f}",
            "",
            "群組評分",
            f"Jack Region 懲罰：{SupportInputApp._format_result_value(getattr(solution, 'jack_region_penalty', 0.0), decimals=2)}",
            f"材料比例懲罰：{SupportInputApp._format_result_value(penalty, decimals=2)}",
            f"群組懲罰合計：{SupportInputApp._format_result_value(getattr(solution, 'jack_region_penalty', 0.0) + penalty, decimals=2)}",
            "",
            "Jack 距離檢查：",
            f"最小相鄰 Jack 距離：{min_distance_text} mm",
            f"規定最小距離：{support.MIN_JACK_DISTANCE_BETWEEN_SUPPORTS} mm",
            f"狀態：{'合法' if jack_distance_ok else '不合法'}",
            f"Material Ratio Weight：{weight:.0f}",
        ])
        return lines

    @staticmethod
    def _solver_diagnostic_summary_lines(value):
        diagnostics = solver_search.SolverDiagnostics.from_dict(value)
        if diagnostics is None:
            return ["搜尋狀態：舊版結果，無診斷資料"]
        lines = [
            f"搜尋狀態：{'已找到合法方案' if diagnostics.legal_solution_found else '未找到合法方案'}"
        ]
        if diagnostics.search_was_escalated:
            lines.append("搜尋調整：系統已自動增加計算強度")
        if diagnostics.result_is_stable:
            lines.append("搜尋穩定度：已穩定")
        elif diagnostics.search_limit_reached:
            lines.append("搜尋穩定度：已達搜尋上限，尚未完全穩定")
        else:
            lines.append("搜尋穩定度：未確認")
        if diagnostics.main_issue_message:
            lines.append(f"主要限制：{diagnostics.main_issue_message}")
        if diagnostics.affected_component_ids:
            component_labels = []
            for component_id in diagnostics.affected_component_ids:
                if component_id in diagnostics.component_candidate_counts:
                    component_labels.append(
                        f"{component_id}（合法候選 "
                        f"{diagnostics.component_candidate_counts[component_id]}）"
                    )
                else:
                    component_labels.append(component_id)
            lines.append("需要檢查：" + "、".join(component_labels))
        return lines

    @classmethod
    def _format_result_details(cls, result_id, item):
        result = item.get("result")
        if item.get("type") == "waler":
            plan = (result.get("selected_plan") or {}) if isinstance(result, dict) else {}
            option_index = result.get("option_index") if isinstance(result, dict) else None
            ratio_targets = result.get("ratio_targets") if isinstance(result, dict) else None
            segment_counts = plan.get("segment_counts") if isinstance(plan, dict) else None
            lines = [
                f"圍令：{result.get('waler_id', result_id) if isinstance(result, dict) else result_id}",
            ]
            lines.extend(cls._solver_diagnostic_summary_lines(
                result.get("search_diagnostics") if isinstance(result, dict) else None
            ))
            if isinstance(result, dict) and result.get("manual_modified"):
                lines.append("[已修改]")
                legality = plan.get("legality") or {}
                lines.append(f"方案狀態：{legality.get('summary', '未檢查')}")
                legality_details = list(legality.get("details", []) or [])
                if legality_details:
                    lines.extend(["合法性檢查：", *legality_details])
                legality_warnings = list(legality.get("warnings", []) or [])
                if legality_warnings:
                    lines.extend(["庫存檢查：", *[f"- {warning}" for warning in legality_warnings]])
            lines.extend([
                "",
                cls._format_waler_score_breakdown(
                    plan,
                    option_index=option_index,
                    ratio_targets=ratio_targets,
                    segment_counts=segment_counts,
                ),
                "",
                f"接頭位置 (mm)：{cls._format_result_list(plan.get('joints', []))}",
            ])
            return "\n".join(lines)

        plans = list(getattr(result, "plans", []) or [])
        lines = [
            f"分區：{result_id}",
            f"支撐數量：{len(plans)}",
            f"總分：{cls._format_result_value(getattr(result, 'total_score', '無資料'), decimals=2)}",
            f"整體是否合法：{'是' if getattr(result, 'valid', False) else '否'}",
        ]
        lines.extend(cls._solver_diagnostic_summary_lines(
            getattr(result, "search_diagnostics", None)
        ))
        reason = str(getattr(result, "reason", "") or "").strip()
        if reason:
            lines.append(f"說明：{reason}")
        lines.extend(cls._format_support_global_analysis_lines(result))

        piece_names = {"steel": "鋼材", "shim": "調整塊", "jack": "千斤頂"}
        for index, plan in enumerate(plans, start=1):
            pieces = list(getattr(plan, "pieces", []) or [])
            arrangement = " → ".join(
                f"{piece_names.get(piece_type, piece_type)}:{cls._format_result_value(length)}"
                for piece_type, length in pieces
            ) or "無"
            steel_lengths = [length for piece_type, length in pieces if piece_type == "steel"]
            shim_lengths = [length for piece_type, length in pieces if piece_type == "shim"]
            jack_lengths = [length for piece_type, length in pieces if piece_type == "jack"]
            plan_valid = bool(getattr(plan, "valid", False)) and not getattr(plan, "reason", "")

            lines.extend([
                "",
                "-" * 56,
                f"支撐 {index}：{getattr(plan, 'support_id', '')}",
                f"鋼材排列：{arrangement}",
                f"鋼材 (mm)：{cls._format_result_list(steel_lengths)}",
                f"調整塊 (mm)：{cls._format_result_list(shim_lengths)}",
                f"千斤頂 (mm)：{cls._format_result_list(jack_lengths)}",
                f"接頭位置 (mm)：{cls._format_result_list(getattr(plan, 'joints', []))}",
                f"分數：{cls._format_result_value(getattr(plan, 'score', '無資料'), decimals=2)}",
                f"是否合法：{'是' if plan_valid else '否'}",
                f"千斤頂區域：{getattr(plan, 'jack_region_id', '無資料')}",
            ])
            plan_reason = str(getattr(plan, "reason", "") or "").strip()
            if plan_reason:
                lines.append(f"不合法原因：{plan_reason}")
        return "\n".join(lines)

    def _refresh_results_tree(self, selected_id=None):
        if not hasattr(self, "results_tree"):
            return

        open_groups = {
            child_id
            for child_id in self.results_tree.get_children("")
            if self._is_result_group_iid(child_id)
            and bool(self.results_tree.item(child_id, "open"))
        }
        if selected_id is None:
            selected = self.results_tree.selection()
            selected_id = selected[0] if selected else None
        force_open_groups = set()
        if selected_id:
            if self._is_result_group_iid(selected_id):
                force_open_groups.add(selected_id)
            elif self._is_support_plan_iid(selected_id):
                zoning, _support_id = self._parse_support_plan_iid(selected_id)
                force_open_groups.add(self._result_group_iid("support", zoning))
            elif selected_id in self.result_items:
                selected_item = self.result_items.get(selected_id)
                if selected_item:
                    force_open_groups.add(
                        self._get_result_tree_info(selected_id, selected_item)["group_iid"]
                    )

        children = self.results_tree.get_children()
        if children:
            self.results_tree.delete(*children)

        groups = {}
        for result_id, item in self.result_items.items():
            info = self._get_result_tree_info(result_id, item)
            group = groups.setdefault(
                info["group_iid"],
                {
                    "group_id": info["group_id"],
                    "group_label": info["group_label"],
                    "type_label": info["type_label"],
                    "sort_key": info["sort_key"][:2],
                    "items": [],
                },
            )
            group["items"].append((result_id, item, info))

        for group_iid, group in sorted(
            groups.items(),
            key=lambda pair: pair[1]["sort_key"],
        ):
            group_items = [item for _result_id, item, _info in group["items"]]
            item_count = len(group_items)
            description = "1 個結果" if item_count == 1 else f"{item_count} 個方案"
            if group_items and all(item.get("type") == "support" for item in group_items):
                support_count = sum(
                    len(list(getattr(item.get("result"), "plans", []) or []))
                    for item in group_items
                )
                description = f"{support_count} 支支撐"
                visible_mark = self._support_group_visible_mark(group_items)
            else:
                visible_mark = self._result_group_visible_mark(group_items)
            self.results_tree.insert(
                "",
                "end",
                iid=group_iid,
                text=group["group_label"],
                open=group_iid in open_groups or group_iid in force_open_groups,
                values=(
                    visible_mark,
                    group["type_label"],
                    group["group_id"],
                    description,
                ),
            )

            for result_id, item, info in sorted(
                group["items"],
                key=lambda entry: entry[2]["sort_key"],
            ):
                if item.get("type") == "support":
                    solution = item.get("result")
                    for plan in list(getattr(solution, "plans", []) or []):
                        support_id = str(getattr(plan, "support_id", "") or "").strip()
                        if not support_id:
                            continue
                        plan_valid = bool(getattr(plan, "valid", False)) and not getattr(plan, "reason", "")
                        self.results_tree.insert(
                            group_iid,
                            "end",
                            iid=self._support_plan_iid(result_id, support_id),
                            text=support_id,
                            values=(
                                "☑" if self._support_plan_visible(item, support_id) else "☐",
                                info["type_label"],
                                support_id,
                                (
                                    f"單體分數：{self._format_result_value(getattr(plan, 'score', '無資料'), decimals=2)}；"
                                    f"千斤頂：{self._format_result_value(getattr(plan, 'jack_center', '無資料'))}；"
                                    f"合法：{'是' if plan_valid else '否'}"
                                ),
                            ),
                        )
                    continue

                item_result = item.get("result")
                is_modified_result = (
                    isinstance(item_result, dict)
                    and item_result.get("manual_modified")
                )
                modified_status = ""
                if is_modified_result:
                    plan = item_result.get("selected_plan") or {}
                    legality = plan.get("legality") or {}
                    is_valid = legality.get("valid", plan.get("valid", False))
                    modified_status = " ✅" if is_valid else " ❌"
                self.results_tree.insert(
                    group_iid,
                    "end",
                    iid=result_id,
                    text=info["child_label"],
                    values=(
                        self._result_item_visible_mark(item),
                        info["type_label"],
                        (
                            f"{result_id} [已修改]{modified_status}"
                            if is_modified_result
                            else result_id
                        ),
                        self._describe_result_item(item),
                    ),
                )

        if selected_id and self.results_tree.exists(selected_id):
            self.results_tree.selection_set(selected_id)
            self.results_tree.focus(selected_id)
            parent_id = self.results_tree.parent(selected_id)
            if parent_id:
                self.results_tree.item(parent_id, open=True)
            elif self._is_result_group_iid(selected_id):
                self.results_tree.item(selected_id, open=True)

        self._update_material_summary()
        self._update_result_action_states()

    def _select_results_tab(self):
        if hasattr(self, "notebook") and hasattr(self, "results_tab"):
            self.notebook.select(self.results_tab)
        if hasattr(self, "analysis_notebook") and hasattr(
            self,
            "configuration_results_tab",
        ):
            self.analysis_notebook.select(self.configuration_results_tab)

    def _describe_result_item(self, item):
        result = item.get("result")
        if item.get("type") == "waler":
            plan = (result.get("selected_plan") or {}) if isinstance(result, dict) else {}
            score = self._format_result_value(plan.get("score", "無資料"), decimals=2)
            joint_count = plan.get("joint_count")
            if joint_count is None:
                joint_count = len(plan.get("joints", []) or [])
            distinct_groups = plan.get("distinct_groups", "無資料")
            buy_count = plan.get("buy_count", "無資料")
            modified_text = ""
            is_manually_modified = (
                isinstance(result, dict) and result.get("manual_modified")
            )
            if is_manually_modified:
                legality = plan.get("legality") or {}
                is_valid = legality.get("valid", plan.get("valid", False))
                modified_text = f"[已修改] {'✅' if is_valid else '❌'}；"
            diagnostics = solver_search.SolverDiagnostics.from_dict(
                result.get("search_diagnostics") if isinstance(result, dict) else None
            )
            search_text = (
                "；搜尋已穩定"
                if not is_manually_modified
                and diagnostics
                and diagnostics.result_is_stable
                else "；搜尋達上限"
                if not is_manually_modified
                and diagnostics
                and diagnostics.search_limit_reached
                else ""
            )
            return (
                f"{modified_text}總分：{score}；接頭：{joint_count}；"
                f"材料種類：{distinct_groups}；購買數：{buy_count}{search_text}"
            )

        plans = getattr(result, "plans", [])
        total_score = getattr(result, "total_score", 0.0)
        valid = getattr(result, "valid", False)
        diagnostics = solver_search.SolverDiagnostics.from_dict(
            getattr(result, "search_diagnostics", None)
        )
        search_text = (
            "；搜尋已穩定"
            if diagnostics and diagnostics.result_is_stable
            else "；搜尋達上限"
            if diagnostics and diagnostics.search_limit_reached
            else ""
        )
        return (
            f"支撐數量={len(plans)}；總分={total_score:.1f}；"
            f"合法={'是' if valid else '否'}{search_text}"
        )

    _material_length_key = staticmethod(
        ProjectResultModel.material_length_key
    )

    def _collect_visible_material_usage(self):
        return ProjectResultModel(
            result_items=self.result_items,
        ).collect_visible_material_usage()

    def _collect_inventory_quantities(self):
        return ProjectResultModel.collect_inventory_quantities(self.inventory)

    def _inventory_quantity(self, material_spec, usage, length):
        return InventoryLookup(self.project_data.inventory).quantity(
            material_spec,
            usage,
            length,
        )

    def _update_material_summary(self):
        if not hasattr(self, "material_summary_tree"):
            return

        children = self.material_summary_tree.get_children()
        if children:
            self.material_summary_tree.delete(*children)

        usage = self._collect_visible_material_usage()
        for usage_name, material_spec, length in sorted(usage):
            used_quantity = usage[(usage_name, material_spec, length)]
            inventory_quantity = self._inventory_quantity(
                material_spec,
                usage_name,
                length,
            )
            remaining_quantity = (
                UNLIMITED_INVENTORY_QTY
                if not material_spec
                else inventory_quantity - used_quantity
            )
            tags = (
                ("shortage",)
                if material_spec and remaining_quantity < 0
                else ()
            )
            self.material_summary_tree.insert(
                "",
                "end",
                values=(
                    f"=== {material_spec} ===" if material_spec else "=== 未填材料 ===",
                    self._format_result_value(length),
                    self._format_result_value(used_quantity),
                    self._format_result_value(inventory_quantity),
                    self._format_result_value(remaining_quantity),
                ),
                tags=tags,
            )

    def _store_result_item(self, result_id, result_type, result):
        result_id = str(result_id).strip()
        if not result_id:
            return
        self.result_items[result_id] = {
            "type": result_type,
            "result": result,
            "visible": True,
        }
        self._mark_results_updated()
        group_iid = self._get_result_tree_info(result_id, self.result_items[result_id])["group_iid"]
        self._refresh_results_tree(selected_id=group_iid)
        self._select_results_tab()
        self.update_preview()

    def _build_preview(self, parent):
        self._preview_scroll_after_id = None
        self._preview_interaction_artist_states = None
        self.preview_interaction = CADViewInteractionController()
        self._preview_pan_pixels_per_data = None
        self._preview_selection_targets = []
        self._preview_selected_key = ""
        self._preview_selection_overlay = []
        self.figure = Figure(figsize=(7, 6), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("開挖支撐系統輸入預覽")
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.grid(True)
        self.ax.set_aspect("equal", adjustable="datalim")
        self.ax.format_coord = self._format_preview_coordinates

        self.preview_counts_text = self.ax.text(
            0.01,
            0.99,
            "",
            transform=self.ax.transAxes,
            verticalalignment="top",
            horizontalalignment="left",
            fontsize=10,
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "black"},
        )

        self.canvas = FigureCanvasTkAgg(self.figure, master=parent)
        self.ax.plot([0, 100], [0, 100], color="red")
        self.canvas.draw()
        self._capture_preview_home_view()
        self.preview_toolbar = PreviewNavigationToolbar(
            self.canvas,
            parent,
            pack_toolbar=False,
            export_callback=self._export_preview_image,
            zoom_getter=self._get_preview_zoom_percent,
        )
        self.preview_toolbar.update()
        self.preview_toolbar.pack(side="bottom", fill="x", padx=8, pady=(0, 4))
        self.canvas.get_tk_widget().pack(
            side="top",
            fill="both",
            expand=True,
            padx=8,
            pady=(8, 4),
        )
        self.canvas.mpl_connect("scroll_event", self._on_preview_scroll)
        self.canvas.mpl_connect("button_press_event", self._on_preview_button_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_preview_motion)
        self.canvas.mpl_connect("button_release_event", self._on_preview_button_release)
        self.preview_toolbar.push_current()

    @staticmethod
    def _format_preview_coordinates(x, y):
        return f"X={x:.0f}  Y={y:.0f}"

    def _capture_preview_home_view(self):
        self._preview_home_xlim = tuple(self.ax.get_xlim())
        self._preview_home_ylim = tuple(self.ax.get_ylim())

    def _get_preview_zoom_percent(self):
        home_xlim = getattr(self, "_preview_home_xlim", self.ax.get_xlim())
        home_ylim = getattr(self, "_preview_home_ylim", self.ax.get_ylim())
        current_xlim = self.ax.get_xlim()
        current_ylim = self.ax.get_ylim()

        home_width = abs(home_xlim[1] - home_xlim[0])
        home_height = abs(home_ylim[1] - home_ylim[0])
        current_width = abs(current_xlim[1] - current_xlim[0])
        current_height = abs(current_ylim[1] - current_ylim[0])
        if min(home_width, home_height, current_width, current_height) <= 0:
            return 100.0
        return math.sqrt(
            (home_width / current_width) * (home_height / current_height)
        ) * 100.0

    def _begin_preview_interaction(self):
        """互動期間暫時隱藏文字、標註框與圖例以降低重畫成本。"""
        if self._preview_interaction_artist_states is not None:
            return

        artists = list(self.ax.texts)
        artists.extend([
            self.ax.title,
            self.ax.xaxis.label,
            self.ax.yaxis.label,
            self.ax.xaxis.get_offset_text(),
            self.ax.yaxis.get_offset_text(),
        ])
        artists.extend(self.ax.get_xticklabels())
        artists.extend(self.ax.get_yticklabels())
        legend = self.ax.get_legend()
        if legend is not None:
            artists.append(legend)

        states = []
        seen = set()
        for artist in artists:
            artist_id = id(artist)
            if artist_id in seen:
                continue
            seen.add(artist_id)
            states.append((artist, artist.get_visible()))
            artist.set_visible(False)
        self._preview_interaction_artist_states = states

    def _begin_preview_pan_interaction(self):
        """開始平移時接管尚未結束的滾輪互動，避免計時器提早恢復標註。"""
        self._cancel_preview_scroll_redraw()
        self._begin_preview_interaction()

    def _end_preview_interaction(self, redraw=True):
        states = self._preview_interaction_artist_states
        if states is None:
            return
        self._preview_interaction_artist_states = None
        for artist, was_visible in states:
            artist.set_visible(was_visible)
        if redraw:
            self.canvas.draw_idle()

    def _ask_export_scale(self):
        selected = {"scale": None}
        dialog = tk.Toplevel(self.root)
        dialog.title("匯出圖片")
        dialog.resizable(False, False)
        dialog.transient(self.root)

        content = ttk.Frame(dialog, padding=14)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text="匯出倍率").grid(
            row=0,
            column=0,
            padx=(0, 10),
            pady=(0, 12),
            sticky="w",
        )
        scale_var = tk.StringVar(value="400%")
        scale_combo = ttk.Combobox(
            content,
            textvariable=scale_var,
            values=[f"{scale}%" for scale in self.EXPORT_SCALE_OPTIONS],
            state="readonly",
            width=10,
        )
        scale_combo.grid(row=0, column=1, pady=(0, 12), sticky="ew")
        scale_combo.focus_set()

        base_width, base_height = self.EXPORT_BASE_FIGSIZE
        ttk.Label(
            content,
            text=(
                f"100% = {base_width * self.EXPORT_DPI} × "
                f"{base_height * self.EXPORT_DPI} px"
            ),
            foreground="#555555",
        ).grid(row=1, column=0, columnspan=2, pady=(0, 12), sticky="w")

        button_frame = ttk.Frame(content)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="e")

        def confirm():
            selected["scale"] = int(scale_var.get().rstrip("%"))
            dialog.destroy()

        ttk.Button(button_frame, text="取消", command=dialog.destroy).pack(
            side="right",
            padx=(6, 0),
        )
        ttk.Button(button_frame, text="選擇儲存位置", command=confirm).pack(
            side="right",
        )

        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.bind("<Return>", lambda _event: confirm())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.grab_set()
        dialog.wait_window()
        return selected["scale"]

    def _export_preview_image(self):
        scale_percent = self._ask_export_scale()
        if scale_percent is None:
            return

        file_path = filedialog.asksaveasfilename(
            parent=self.root,
            title="匯出完整配置圖",
            defaultextension=".png",
            filetypes=[
                ("PNG 圖片", "*.png"),
                ("JPEG 圖片", "*.jpg *.jpeg"),
                ("所有檔案", "*.*"),
            ],
        )
        if not file_path:
            return

        original_size = tuple(self.figure.get_size_inches())
        original_xlim = self.ax.get_xlim()
        original_ylim = self.ax.get_ylim()
        scale = scale_percent / 100.0
        base_width, base_height = self.EXPORT_BASE_FIGSIZE
        export_size = (base_width * scale, base_height * scale)

        try:
            # 先重建完整圖面，確保匯出不受目前 Pan／Zoom 視窗影響。
            self.update_preview()
            self.figure.set_size_inches(*export_size, forward=False)
            self.figure.savefig(
                file_path,
                dpi=self.EXPORT_DPI,
                bbox_inches=None,
                facecolor=self.figure.get_facecolor(),
            )
        except Exception as exc:
            messagebox.showerror("匯出失敗", f"無法匯出圖片：\n{exc}")
            return
        finally:
            self.figure.set_size_inches(*original_size, forward=False)
            self.ax.set_xlim(original_xlim)
            self.ax.set_ylim(original_ylim)
            self.canvas.draw_idle()
            self.preview_toolbar.push_current()
            self.preview_toolbar.set_zoom_percent(self._get_preview_zoom_percent())

        pixel_width = int(round(export_size[0] * self.EXPORT_DPI))
        pixel_height = int(round(export_size[1] * self.EXPORT_DPI))
        messagebox.showinfo(
            "匯出完成",
            f"已匯出完整配置圖。\n倍率：{scale_percent}%\n尺寸："
            f"{pixel_width} × {pixel_height} px",
        )

    def _register_preview_segment(
        self,
        kind,
        identifier,
        start,
        end,
        *,
        table_name=None,
        row_index=None,
        key=None,
    ):
        target_key = key or f"{kind}:{identifier}"
        self._preview_selection_targets.append(
            {
                "key": target_key,
                "kind": kind,
                "identifier": str(identifier),
                "geometry": "segment",
                "start": (float(start[0]), float(start[1])),
                "end": (float(end[0]), float(end[1])),
                "table_name": table_name,
                "row_index": row_index,
            }
        )

    def _register_preview_point(
        self,
        kind,
        identifier,
        point,
        *,
        table_name=None,
        row_index=None,
        key=None,
    ):
        target_key = key or f"{kind}:{identifier}"
        self._preview_selection_targets.append(
            {
                "key": target_key,
                "kind": kind,
                "identifier": str(identifier),
                "geometry": "point",
                "point": (float(point[0]), float(point[1])),
                "table_name": table_name,
                "row_index": row_index,
            }
        )

    @staticmethod
    def _preview_kind_label(kind):
        return {
            "waler": "圍令",
            "strut": "支撐",
            "brace": "斜撐",
            "beam": "托梁",
            "column": "中間柱",
            "jack": "Jack",
        }.get(kind, str(kind))

    def _preview_target_at_event(self, event):
        if event.inaxes is not self.ax:
            return None
        screen_point = float(event.x), float(event.y)
        point_targets = []
        segment_targets = []
        target_by_key = {
            target["key"]: target for target in self._preview_selection_targets
        }
        for target in self._preview_selection_targets:
            if target["geometry"] == "point":
                screen = self.ax.transData.transform(target["point"])
                point_targets.append(
                    (target["key"], (float(screen[0]), float(screen[1])))
                )
            else:
                start = self.ax.transData.transform(target["start"])
                end = self.ax.transData.transform(target["end"])
                segment_targets.append(
                    (
                        target["key"],
                        (float(start[0]), float(start[1])),
                        (float(end[0]), float(end[1])),
                    )
                )
        point_hits = self.preview_interaction.point_hits(
            screen_point,
            point_targets,
            10.0,
        )
        if point_hits:
            return target_by_key.get(point_hits[0])
        segment_key = self.preview_interaction.nearest_segment(
            screen_point,
            segment_targets,
            10.0,
        )
        return target_by_key.get(segment_key)

    def _draw_preview_selection_highlight(self):
        for artist in getattr(self, "_preview_selection_overlay", ()):
            try:
                artist.remove()
            except (ValueError, AttributeError):
                pass
        self._preview_selection_overlay = []
        selected_key = getattr(self, "_preview_selected_key", "")
        target = next(
            (
                item
                for item in self._preview_selection_targets
                if item["key"] == selected_key
            ),
            None,
        )
        if target is None:
            if selected_key:
                self._preview_selected_key = ""
            return
        if target["geometry"] == "point":
            artist = self.ax.scatter(
                [target["point"][0]],
                [target["point"][1]],
                s=150,
                facecolors="none",
                edgecolors="#1565c0",
                linewidths=3,
                zorder=30,
            )
            self._preview_selection_overlay.append(artist)
        else:
            artist, = self.ax.plot(
                [target["start"][0], target["end"][0]],
                [target["start"][1], target["end"][1]],
                color="#1565c0",
                linewidth=7,
                alpha=0.75,
                solid_capstyle="round",
                zorder=30,
            )
            self._preview_selection_overlay.append(artist)

    def _select_preview_target(self, target):
        self._preview_selected_key = target["key"] if target is not None else ""
        if target is None:
            for table_name in ("walers", "struts", "braces"):
                tree = self.treeviews.get(table_name)
                if tree is None:
                    continue
                selection = tree.selection()
                if selection:
                    tree.selection_remove(*selection)
            self.preview_toolbar.set_message("左鍵選取｜中鍵平移｜滾輪縮放")
        else:
            table_name = target.get("table_name")
            row_index = target.get("row_index")
            if table_name in self.treeviews and isinstance(row_index, int):
                self.current_table = table_name
                if hasattr(self, "engineering_workspace"):
                    self.notebook.select(self.engineering_workspace)
                member_tab = getattr(self, "table_tabs", {}).get(table_name)
                if member_tab is not None and hasattr(self, "engineering_notebook"):
                    self.engineering_notebook.select(member_tab)
                elif not hasattr(self, "engineering_workspace"):
                    expected_tab_text = self.table_tab_labels.get(table_name)
                    for tab_id in self.notebook.tabs():
                        if self.notebook.tab(tab_id, "text") == expected_tab_text:
                            self.notebook.select(tab_id)
                            break
                self._select_input_row(table_name, row_index)
            label = self._preview_kind_label(target["kind"])
            self.preview_toolbar.set_message(
                f"已選取 {label} {target['identifier']}｜中鍵平移｜滾輪縮放"
            )
        self._draw_preview_selection_highlight()
        self.canvas.draw_idle()

    def _on_preview_button_press(self, event):
        if self.preview_interaction.is_select_button(event.button):
            target = (
                self._preview_target_at_event(event)
                if event.inaxes is self.ax
                else None
            )
            self._select_preview_target(target)
            return
        if event.inaxes is not self.ax:
            return
        if not self.preview_interaction.is_pan_button(event.button):
            return
        if getattr(event, "dblclick", False):
            return
        self.preview_interaction.begin_pan(
            (float(event.x), float(event.y)),
            (
                *self.ax.get_xlim(),
                *self.ax.get_ylim(),
            ),
        )
        x_limits = self.ax.get_xlim()
        y_limits = self.ax.get_ylim()
        self._preview_pan_pixels_per_data = (
            max(
                float(self.ax.bbox.width)
                / max(abs(x_limits[1] - x_limits[0]), 1e-12),
                1e-12,
            ),
            max(
                float(self.ax.bbox.height)
                / max(abs(y_limits[1] - y_limits[0]), 1e-12),
                1e-12,
            ),
        )
        self._begin_preview_pan_interaction()
        try:
            self.canvas.get_tk_widget().configure(cursor="fleur")
        except tk.TclError:
            pass

    def _on_preview_motion(self, event):
        if not self.preview_interaction.pan_active:
            return
        bounds = self.preview_interaction.pan_to(
            (float(event.x), float(event.y)),
            self._preview_pan_pixels_per_data,
            y_axis_screen_down=False,
        )
        if bounds is None:
            return
        self.ax.set_xlim(bounds[0], bounds[1])
        self.ax.set_ylim(bounds[2], bounds[3])
        self.canvas.draw_idle()

    def _on_preview_button_release(self, event):
        if not self.preview_interaction.pan_active:
            self.preview_toolbar.sync_zoom_display()
            return
        self.preview_interaction.end_pan()
        self._preview_pan_pixels_per_data = None
        try:
            self.canvas.get_tk_widget().configure(cursor="arrow")
        except tk.TclError:
            pass
        self._end_preview_interaction()
        self.preview_toolbar.push_current()
        self.preview_toolbar.sync_zoom_display()

    def _on_preview_scroll(self, event):
        if event.inaxes is not self.ax:
            return
        if event.xdata is None or event.ydata is None:
            return

        direction = getattr(event, "step", 0)
        if not direction:
            direction = 1 if event.button == "up" else -1 if event.button == "down" else 0
        scale_factor = self.preview_interaction.scroll_factor(direction)
        if scale_factor is None:
            return

        self._begin_preview_interaction()

        x_min, x_max = self.ax.get_xlim()
        y_min, y_max = self.ax.get_ylim()
        mouse_x = event.xdata
        mouse_y = event.ydata

        bounds = self.preview_interaction.zoom_bounds(
            (x_min, x_max, y_min, y_max),
            (mouse_x, mouse_y),
            scale_factor,
        )
        self.ax.set_xlim(bounds[0], bounds[1])
        self.ax.set_ylim(bounds[2], bounds[3])
        self.canvas.draw_idle()
        self._schedule_preview_scroll_redraw()

    def _schedule_preview_scroll_redraw(self):
        if self._preview_scroll_after_id is not None:
            try:
                self.root.after_cancel(self._preview_scroll_after_id)
            except tk.TclError:
                pass
        self._preview_scroll_after_id = self.root.after(
            self.PREVIEW_SCROLL_DEBOUNCE_MS,
            self._flush_preview_scroll_redraw,
        )

    def _flush_preview_scroll_redraw(self):
        self._preview_scroll_after_id = None
        self._end_preview_interaction(redraw=False)
        self.canvas.draw_idle()
        self.preview_toolbar.push_current()
        self.preview_toolbar.set_zoom_percent(self._get_preview_zoom_percent())

    def _cancel_preview_scroll_redraw(self):
        if self._preview_scroll_after_id is None:
            return
        try:
            self.root.after_cancel(self._preview_scroll_after_id)
        except tk.TclError:
            pass
        self._preview_scroll_after_id = None

    def _schedule_cad_event_poll(self):
        if self._cad_poll_after_id is not None:
            return
        try:
            self._cad_poll_after_id = self.root.after(
                POLL_INTERVAL_MS,
                self._poll_cad_event,
            )
        except tk.TclError:
            self._cad_poll_after_id = None

    def _poll_cad_event(self):
        self._cad_poll_after_id = None
        try:
            if self.cad_import_enabled and not getattr(
                self, "dxf_dialog_active", False
            ):
                self.read_cad_event()
        finally:
            self._schedule_cad_event_poll()

    def _set_dxf_import_status(self, status, *, source=None, error=None):
        self.dxf_import_status = str(status)
        self.dxf_import_error = str(error) if error is not None else ""
        if hasattr(self, "dxf_import_status_var"):
            self.dxf_import_status_var.set(self.dxf_import_status)
        if hasattr(self, "dxf_import_error_var"):
            self.dxf_import_error_var.set(self.dxf_import_error)
        if source is not None and hasattr(self, "dxf_import_source_var"):
            self.dxf_import_source_var.set(f"來源檔案：{Path(source)}")
        self._refresh_project_status_display()

    def _set_cad_import_status(self, status, *, event=None, error=None):
        self.cad_import_status = status
        if event is not None:
            self.cad_last_event = copy.deepcopy(event)
        self.cad_last_error = str(error) if error is not None else None
        self._refresh_cad_import_status()

    def _refresh_cad_import_status(self):
        if hasattr(self, "cad_import_status_var"):
            self.cad_import_status_var.set(self.cad_import_status)
        if hasattr(self, "cad_import_error_var"):
            self.cad_import_error_var.set(self.cad_last_error or "")
        if hasattr(self, "cad_import_last_event_var"):
            if self.cad_last_event is None:
                text = "尚無匯入紀錄"
            else:
                event_type = str(self.cad_last_event.get("type", "")).strip()
                event_id = str(self.cad_last_event.get("event_id", "")).strip()
                text = f"{event_type}｜event_id={event_id}"
            self.cad_import_last_event_var.set(text)

    def _toggle_cad_import(self):
        self.cad_import_enabled = bool(self.cad_import_enabled_var.get())
        status = "等待 CAD 事件" if self.cad_import_enabled else "CAD 自動接收已停止"
        self._set_cad_import_status(status)

    def _import_dxf_file(self):
        workflow = self._current_dxf_workflow_status()
        if workflow == DxfWorkflowStatus.REVIEW:
            return self._continue_dxf_import()
        if workflow == DxfWorkflowStatus.COMPLETED:
            messagebox.showwarning(
                "DXF 匯入已完成",
                "此專案已完成 DXF 匯入，後續請在主畫面修改工程資料。",
                parent=self.root,
            )
            return None
        file_path = filedialog.askopenfilename(
            title="選擇 DXF 檔案",
            filetypes=(("DXF 圖檔", "*.dxf"), ("所有檔案", "*.*")),
            parent=self.root,
        )
        if not file_path:
            return None
        try:
            outcome = self._run_dxf_review_dialog(
                Path(file_path),
                initial_state=None,
                resume_review=False,
            )
            return self._handle_dxf_review_outcome(outcome, Path(file_path))
        except (DXFImportError, ProjectPersistenceError, OSError, ValueError) as exc:
            self._set_dxf_import_status(
                "DXF 匯入失敗",
                source=file_path,
                error=exc,
            )
            messagebox.showerror("DXF 匯入失敗", str(exc), parent=self.root)
            return None

    def _run_dxf_review_dialog(
        self,
        file_path,
        *,
        initial_state,
        resume_review,
        initial_world_result=None,
    ):
        workflow = self._current_dxf_workflow_status()
        if resume_review and workflow != DxfWorkflowStatus.REVIEW:
            raise RuntimeError("只有 REVIEW 狀態可以繼續 DXF 匯入。")
        if not resume_review and workflow == DxfWorkflowStatus.COMPLETED:
            raise RuntimeError("COMPLETED 狀態不可重新開啟 DXF Review。")
        self.dxf_dialog_active = True
        try:
            return DXFImportDialog(
                self.root,
                file_path,
                initial_state=initial_state,
                cad_event_watcher=self.cad_event_watcher,
                material_specs=self.material_specs,
                restore_saved_layer_classification=(True if resume_review else None),
                resume_review=resume_review,
                initial_world_result=initial_world_result,
            ).show()
        finally:
            self.dxf_dialog_active = False

    @staticmethod
    def _coerce_dxf_dialog_outcome(payload):
        if isinstance(payload, DXFImportDialogOutcome):
            return payload
        if isinstance(payload, tuple) and len(payload) == 2:
            result, mode = payload
            if hasattr(result, "to_debug_dict"):
                return DXFImportDialogOutcome(
                    action="complete",
                    review_state=result.to_debug_dict(),
                    import_mode=str(mode),
                    result=result,
                    world_result=None,
                )
        return None

    def _remember_dxf_review(self, outcome, file_path):
        if self._current_dxf_workflow_status() == DxfWorkflowStatus.COMPLETED:
            raise RuntimeError("COMPLETED 狀態不可重新建立 DXF Review。")
        state = copy.deepcopy(dict(outcome.review_state))
        fingerprint = str(state.get("source_fingerprint", "") or "").strip().upper()
        current_fingerprint = source_file_fingerprint(file_path)
        if not fingerprint or fingerprint != current_fingerprint:
            raise DXFImportError(
                "DXF Review 狀態與目前來源內容不一致，已停止保存人工修正。"
            )
        self.dxf_last_import_debug = state
        self.dxf_review_session = {
            "source_fingerprint": fingerprint,
            "world_result": outcome.world_result,
        }
        report = getattr(self, "dxf_asset_status_report", None)
        active_source = getattr(report, "active_source", None)
        if (
            active_source is None
            or str(active_source.sha256).strip().upper() != fingerprint
        ):
            self.dxf_asset_status_report = (
                self._ensure_project_service().runtime_dxf_report(file_path)
            )
        self.last_dxf_compatibility_report = None
        self._transition_dxf_workflow(DxfWorkflowStatus.REVIEW)
        self._mark_project_dirty("DXF Review 尚未完成")

    def _handle_dxf_review_outcome(self, payload, file_path):
        outcome = self._coerce_dxf_dialog_outcome(payload)
        if outcome is None:
            return None
        if outcome.action not in {"pause", "complete"}:
            return None
        self._remember_dxf_review(outcome, file_path)
        if outcome.action == "pause":
            self._set_dxf_import_status(
                "DXF 匯入：尚未完成",
                source=outcome.review_state.get("source_path", file_path),
            )
            return "pause"
        if outcome.action != "complete" or outcome.result is None:
            return None
        self._complete_dxf_review(outcome, file_path)
        return "complete"

    def _complete_dxf_review(self, outcome, file_path):
        result = outcome.result
        mode = outcome.import_mode
        existing = self._project_rows_by_table() if mode == "append" else None
        imported = result.to_project_rows(existing)

        previous_project_data = self._ensure_project_data()
        previous_results = copy.deepcopy(self._ensure_project_results())
        previous_solver_memory = copy.deepcopy(self.solver_memory)
        previous_support_cache = copy.deepcopy(self.support_candidate_cache)
        case_data = previous_project_data.to_case_data()
        if mode == "append":
            walers = [*case_data["walers"], *imported["walers"]]
            struts = [*case_data["struts"], *imported["struts"]]
            braces = [*case_data["braces"], *imported["braces"]]
        else:
            walers = imported["walers"]
            struts = imported["struts"]
            braces = imported["braces"]
        staged_project_data = ProjectDataModel(
            walers=walers,
            struts=struts,
            braces=braces,
            inventory=case_data["inventory"],
            material_specs=case_data["material_specs"],
        )

        try:
            self.project_data = staged_project_data
            for table_name in ("walers", "struts", "braces"):
                self._refresh_tree(table_name)
            self._handle_input_data_changed(preserve_view=False)
        except Exception:
            self.project_data = previous_project_data
            self._project_results = previous_results
            self.solver_memory = previous_solver_memory
            self.support_candidate_cache = previous_support_cache
            for table_name in ("walers", "struts", "braces"):
                self._refresh_tree(table_name)
            self.update_preview(preserve_view=False)
            raise

        self._transition_dxf_workflow(DxfWorkflowStatus.COMPLETED)
        self.dxf_review_session = None
        self._set_dxf_import_status(
            f"DXF 匯入成功：圍令 {len(imported['walers'])}、"
            f"支撐 {len(imported['struts'])}、斜撐 {len(imported['braces'])}、"
            f"中間柱 {len(imported['columns'])}、托梁 {len(imported['beams'])}、"
            f"角撐 {len(imported['corner_braces'])}、"
            f"連續壁圖元 {result.source_entity_counts.get('continuous_wall', 0)}、"
            f"輔助線圖元 {result.source_entity_counts.get('auxiliary', 0)}",
            source=file_path,
        )

    def _review_resume_source(self):
        if self._current_dxf_workflow_status() != DxfWorkflowStatus.REVIEW:
            raise RuntimeError("目前沒有可繼續的 DXF Review。")
        state = getattr(self, "dxf_last_import_debug", None)
        if not isinstance(state, Mapping):
            raise DXFImportError("DXF Review 缺少可恢復的狀態。")
        candidates = []
        report = getattr(self, "dxf_asset_status_report", None)
        active_source = getattr(report, "active_source", None)
        if active_source is not None:
            candidates.append(Path(active_source.path))
        source_text = str(state.get("source_path", "") or "").strip()
        if source_text:
            candidates.append(Path(source_text))
        source = next((path for path in candidates if path.is_file()), None)
        if source is None:
            raise DXFImportError(
                "找不到 DXF Review 的來源或專案管理副本，請先重新連結 DXF。"
            )
        fingerprint = source_file_fingerprint(source)
        if not review_state_matches_source(state, fingerprint, source):
            raise DXFImportError(
                "此專案保存的 DXF Review 使用的是不同版本的 DXF。"
                "為避免人工修正套用到錯誤來源，目前無法直接繼續此 Review。"
            )
        return source, fingerprint

    def _continue_dxf_import(self):
        if self._current_dxf_workflow_status() != DxfWorkflowStatus.REVIEW:
            messagebox.showwarning(
                "無法繼續 DXF 匯入",
                "目前專案沒有尚未完成的 DXF Review。",
                parent=self.root,
            )
            return None
        try:
            source, fingerprint = self._review_resume_source()
            session = getattr(self, "dxf_review_session", None)
            initial_world_result = None
            if (
                isinstance(session, Mapping)
                and str(session.get("source_fingerprint", "")).strip().upper()
                == fingerprint
            ):
                candidate_result = session.get("world_result")
                saved_layers = self.dxf_last_import_debug.get(
                    "layer_classification",
                    {},
                )
                if (
                    candidate_result is not None
                    and dict(candidate_result.layer_classification)
                    == dict(saved_layers)
                ):
                    initial_world_result = candidate_result
            outcome = self._run_dxf_review_dialog(
                source,
                initial_state=self.dxf_last_import_debug,
                resume_review=True,
                initial_world_result=initial_world_result,
            )
            return self._handle_dxf_review_outcome(outcome, source)
        except (DXFImportError, ProjectPersistenceError, OSError, ValueError) as exc:
            self._set_dxf_import_status(
                "DXF Review 無法繼續",
                error=exc,
            )
            messagebox.showerror(
                "DXF Review 無法繼續",
                str(exc),
                parent=self.root,
            )
            return None

    def _manual_read_cad_event(self):
        imported = self.read_cad_event(report_errors=True)
        if not imported and self.cad_last_error is None:
            self._set_cad_import_status("目前沒有待匯入的 CAD 事件")

    def _project_rows_by_table(self):
        return self._ensure_project_data().geometry_rows()

    def _cad_coordinate_system(self):
        state = getattr(self, "dxf_last_import_debug", None)
        if not isinstance(state, Mapping):
            return CoordinateSystem()
        coordinate = state.get("coordinate_system")
        if coordinate is None:
            return CoordinateSystem()
        if not isinstance(coordinate, Mapping):
            raise ValueError("DXF coordinate_system 格式錯誤，無法套用 CAD 事件。")
        mode = str(coordinate.get("mode", "world") or "world").strip().lower()
        try:
            origin_x = float(coordinate.get("origin_x", 0.0) or 0.0)
            origin_y = float(coordinate.get("origin_y", 0.0) or 0.0)
        except (TypeError, ValueError) as exc:
            raise ValueError("DXF local coordinate origin 格式錯誤。") from exc
        return CoordinateSystem(
            mode=mode,
            origin_x=origin_x,
            origin_y=origin_y,
            source=str(coordinate.get("source", "cad_world") or "cad_world"),
        )

    def _stage_stale_dxf_state(self, state, reason):
        if not isinstance(state, Mapping):
            return None
        staged = copy.deepcopy(dict(state))
        staged[self.DXF_BINDING_STALE_KEY] = True
        staged[self.DXF_BINDING_STALE_REASON_KEY] = str(reason)
        return staged

    @classmethod
    def _project_field_affects_dxf_binding(cls, table_name, field_name):
        return field_name in cls.DXF_BINDING_FIELDS.get(table_name, ())

    def _dxf_binding_is_stale(self):
        state = getattr(self, "dxf_last_import_debug", None)
        return bool(
            isinstance(state, dict)
            and state.get(self.DXF_BINDING_STALE_KEY, False)
        )

    def _mark_dxf_binding_stale(self, reason=""):
        state = getattr(self, "dxf_last_import_debug", None)
        if not isinstance(state, dict):
            return
        state[self.DXF_BINDING_STALE_KEY] = True
        if reason:
            state[self.DXF_BINDING_STALE_REASON_KEY] = str(reason)
        self.last_dxf_compatibility_report = None

    def _check_dxf_export_compatibility(self, dxf_state):
        checker = getattr(self, "dxf_compatibility_checker", None)
        if checker is None:
            checker = self._ensure_project_service().dxf_compatibility_checker
        report = checker.compare(
            dxf_state,
            dxf_state,
            self._project_rows_by_table(),
        )
        self.last_dxf_compatibility_report = report
        self._refresh_project_status_display()
        return report.compatible and not self._dxf_binding_is_stale(), report

    def _invalidate_solver_state_after_input_change(self):
        had_result = bool(self.result_items) or self.project_result is not None
        self.result_items.clear()
        self.project_result = None
        self.last_calculated_time = None
        self.solver_memory.clear()
        self.support_candidate_cache.clear()
        self._refresh_results_tree()
        if had_result and hasattr(self, "result_text"):
            self.show_result("結果已失效，請重新計算")

    def _handle_input_data_changed(
        self,
        *,
        preserve_view=True,
        table_name=None,
        field_name=None,
        dxf_binding_changed=None,
    ):
        if dxf_binding_changed is None:
            dxf_binding_changed = self._project_field_affects_dxf_binding(
                table_name,
                field_name,
            )
        if dxf_binding_changed:
            self._mark_dxf_binding_stale(
                f"{table_name or 'project'}.{field_name or 'member'} 已修改"
            )
        metadata_only = table_name == "material_specs"
        if not metadata_only and table_name in (
            None,
            "walers",
            "struts",
            "braces",
            "inventory",
        ):
            self._invalidate_solver_state_after_input_change()
        if table_name == "inventory":
            self._update_material_summary()
        self._mark_project_dirty("輸入資料已變更")
        self.update_preview(preserve_view=preserve_view)

    def _select_input_row(self, table_name, index):
        tree = self.treeviews.get(table_name)
        if tree is None:
            return
        item_id = f"{table_name}_{index}"
        if item_id not in tree.get_children():
            return
        tree.selection_set(item_id)
        tree.focus(item_id)
        tree.see(item_id)
        if table_name == "struts":
            self._load_strut_detail(index)

    def _apply_cad_event(self, event):
        if self.cad_event_mapper.is_cancel_event(event):
            self.cad_event_mapper.validate_cancel_event(event)
            self.cad_event_watcher.acknowledge(event)
            self._set_cad_import_status(
                "已清除待處理的 CAD 事件；Project 資料未變更。",
                event=event,
            )
            return "control", {}

        project_rows = self._project_rows_by_table()
        mapped = self.cad_event_mapper.map_command(
            event,
            project_rows,
            coordinate_system=self._cad_coordinate_system(),
        )
        table_name = mapped.table_name
        rows = getattr(self, table_name)
        old_state = getattr(self, "dxf_last_import_debug", None)
        old_row = None
        binding_synced = False
        binding_report = None
        member_label = {
            "walers": "圍令",
            "struts": "支撐",
            "braces": "斜撐",
        }[table_name]

        if mapped.operation == "add":
            staged_state = self._stage_stale_dxf_state(
                old_state,
                f"CAD add 已新增 {table_name}，尚無對應的 DXF binding",
            )
            rows.append(mapped.row)
            committed_index = len(rows) - 1
            committed_row = rows[committed_index]
        else:
            if mapped.row_index is None:
                raise ValueError(f"{member_label} update 缺少原資料列索引。")
            committed_index = mapped.row_index
            old_row = copy.deepcopy(rows[committed_index])
            linear_noop = (
                table_name in ("walers", "braces")
                and not mapped.endpoints_changed
            )
            if mapped.row == old_row or linear_noop:
                self.cad_event_watcher.acknowledge(event)
                identifier_field = self.table_columns[table_name][0]
                identifier = str(old_row.get(identifier_field, "")).strip()
                self._set_cad_import_status(
                    f"{member_label} {identifier} 幾何未變更。",
                    event=event,
                )
                return table_name, rows[committed_index]

            if self._dxf_binding_is_stale():
                binding_reason = (
                    str(
                        old_state.get(self.DXF_BINDING_STALE_REASON_KEY, "")
                        if isinstance(old_state, Mapping)
                        else ""
                    ).strip()
                    or "DXF Review state 在更新前已過期"
                )
                staged_state = self._stage_stale_dxf_state(
                    old_state,
                    binding_reason,
                )
            else:
                try:
                    staged_state, binding_synced, binding_reason = (
                        self.cad_event_mapper.stage_dxf_update_binding(
                            old_state,
                            mapped,
                            old_row,
                            event_id=event.get("event_id", ""),
                        )
                    )
                except (AttributeError, KeyError, TypeError, ValueError) as exc:
                    staged_state = None
                    binding_synced = False
                    binding_reason = f"DXF binding 無法建立：{exc}"
            if binding_synced and isinstance(staged_state, Mapping):
                staged_rows = copy.deepcopy(project_rows)
                staged_rows[table_name][committed_index] = copy.deepcopy(mapped.row)
                try:
                    checker = getattr(self, "dxf_compatibility_checker", None)
                    if checker is None:
                        checker = self._ensure_project_service().dxf_compatibility_checker
                    binding_report = checker.compare(
                        staged_state,
                        staged_state,
                        staged_rows,
                    )
                    if not binding_report.compatible:
                        binding_synced = False
                        binding_reason = "DXF compatibility check 未通過"
                except (AttributeError, KeyError, TypeError, ValueError) as exc:
                    binding_synced = False
                    binding_reason = f"DXF compatibility check 無法確認：{exc}"
            if not binding_synced:
                staged_state = self._stage_stale_dxf_state(
                    old_state,
                    binding_reason
                    or f"無法可靠同步 {member_label} DXF binding",
                )
            committed_row = self._ensure_project_data().replace_row(
                table_name,
                committed_index,
                mapped.row,
            )

        self.dxf_last_import_debug = staged_state
        try:
            self.cad_event_watcher.acknowledge(event)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            if mapped.operation == "add":
                rows.pop()
            else:
                self._ensure_project_data().replace_row(
                    table_name,
                    committed_index,
                    old_row,
                )
            self.dxf_last_import_debug = old_state
            raise

        self._refresh_tree(table_name)
        self._select_input_row(table_name, committed_index)
        self.last_dxf_compatibility_report = (
            binding_report if binding_synced else None
        )
        self._handle_input_data_changed(
            preserve_view=False,
            table_name=table_name,
            dxf_binding_changed=False,
        )
        validation_report = None
        if mapped.operation == "update":
            validation_report = ProjectDataValidator().validate(
                self._ensure_project_data()
            )
            self.last_cad_validation_report = validation_report

        identifier_field = self.table_columns[table_name][0]
        identifier = str(committed_row.get(identifier_field, "")).strip()
        if mapped.operation == "add":
            status = f"匯入成功：{identifier}"
        else:
            binding_ready = binding_synced and not self._dxf_binding_is_stale()
            status = (
                f"已更新{member_label} {identifier}；DXF 工程線已同步"
                if binding_ready
                else f"已更新{member_label} {identifier}；DXF 圖面定位需重新確認"
            )
            notes = []
            if mapped.associated_ids_cleared:
                notes.append("柱/托梁關聯 ID 已清除")
            if mapped.corner_brace_lengths_cleared:
                notes.append("角撐長度已清除")
            if notes:
                status += "；" + "；".join(notes)
            if validation_report is not None and validation_report.errors:
                status += (
                    f"；Validation 發現 "
                    f"{len(validation_report.errors)} 項錯誤"
                )
            status += "。"
        self._set_cad_import_status(status, event=event)
        return table_name, committed_row

    def read_cad_event(self, *, report_errors=False):
        try:
            event = self.cad_event_watcher.check_new_event()
            if event is None:
                return False
            self._apply_cad_event(event)
            return True
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            error_message = (
                f"{exc}\n事件仍保留；若要放棄這次事件，請在 CAD 執行 SUPCLEAR。"
            )
            self._set_cad_import_status(
                "CAD 事件匯入失敗",
                error=error_message,
            )
            if report_errors:
                messagebox.showerror(
                    "CAD 匯入失敗",
                    error_message,
                    parent=self.root,
                )
        return False

    @staticmethod
    def _main_ui_state_path():
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        return base / "SupportDistributionUV" / "main_ui_state.json"

    @classmethod
    def _load_main_ui_state(cls):
        try:
            payload = json.loads(
                cls._main_ui_state_path().read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _default_main_window_geometry(self):
        areas = _active_monitor_work_areas(self.root)
        self._main_work_areas = areas
        left, top, right, bottom = areas[0]
        available_width = max(right - left, 1)
        available_height = max(bottom - top, 1)
        width = min(1600, available_width, max(720, int(available_width * 0.90)))
        height = min(900, available_height, max(560, int(available_height * 0.90)))
        x = left + max((available_width - width) // 2, 0)
        y = top + max((available_height - height) // 2, 0)
        x_offset = f"+{x}" if x >= 0 else str(x)
        y_offset = f"+{y}" if y >= 0 else str(y)
        return f"{width}x{height}{x_offset}{y_offset}"

    def _restore_main_window_geometry(self):
        fallback = self._default_main_window_geometry()
        requested = str(self.main_ui_state.get("geometry", fallback))
        geometry = fit_window_geometry_to_work_areas(
            requested,
            fallback,
            self._main_work_areas,
        )
        try:
            self.root.geometry(geometry)
        except tk.TclError:
            self.root.geometry(fallback)
            geometry = fallback
        return geometry

    def _is_main_window_maximized(self):
        try:
            return self.root.state() == "zoomed"
        except tk.TclError:
            try:
                return bool(self.root.attributes("-zoomed"))
            except tk.TclError:
                return False

    def _set_main_window_maximized(self, maximized):
        try:
            self.root.state("zoomed" if maximized else "normal")
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", bool(maximized))
            except tk.TclError:
                pass

    def _on_main_window_configure(self, event):
        if event.widget is not self.root or self._is_main_window_maximized():
            return
        geometry = self.root.geometry()
        if geometry:
            self._last_normal_geometry = geometry

    def _restore_main_paned_position(self):
        paned = getattr(self, "main_paned", None)
        if paned is None:
            return
        try:
            ratio = float(self.main_ui_state.get("main_sash_ratio", 0.60))
        except (TypeError, ValueError):
            ratio = 0.60
        ratio = min(max(ratio, 0.30), 0.80)
        try:
            width = paned.winfo_width()
            if width > 1:
                paned.sashpos(0, int(width * ratio))
        except tk.TclError:
            pass

    def _save_main_ui_state(self):
        paned = getattr(self, "main_paned", None)
        sash_ratio = 0.60
        if paned is not None:
            try:
                width = paned.winfo_width()
                if width > 1:
                    sash_ratio = paned.sashpos(0) / width
            except tk.TclError:
                pass
        payload = {
            "geometry": self._last_normal_geometry,
            "maximized": self._is_main_window_maximized(),
            "main_sash_ratio": min(max(float(sash_ratio), 0.30), 0.80),
        }
        try:
            path = self._main_ui_state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _on_main_window_close(self):
        if getattr(self, "project_dirty", False):
            decision = messagebox.askyesnocancel(
                "尚未儲存",
                "目前專案有尚未儲存的變更。\n是否先儲存再關閉？",
                parent=self.root,
            )
            if decision is None:
                return
            if decision:
                saved = self._save_current_project()
                if saved is None or getattr(self, "project_dirty", False):
                    return
        if self._cad_poll_after_id is not None:
            try:
                self.root.after_cancel(self._cad_poll_after_id)
            except tk.TclError:
                pass
            self._cad_poll_after_id = None
        self._save_main_ui_state()
        self.root.destroy()

    def _on_tab_changed(self, event):
        self._sync_current_table_from_active_tabs()
        self._update_context_toolbar()

    def _on_engineering_tab_changed(self, _event=None):
        self._sync_current_table_from_active_tabs()
        self._update_context_toolbar()

    def _on_settings_tab_changed(self, event):
        self._sync_current_table_from_active_tabs()
        self._update_context_toolbar()

    def _on_analysis_tab_changed(self, _event=None):
        self._sync_current_table_from_active_tabs()
        self._update_context_toolbar()

    @staticmethod
    def _selected_notebook_text(notebook):
        if notebook is None:
            return ""
        selected_tab = notebook.select()
        return notebook.tab(selected_tab, "text") if selected_tab else ""

    def _sync_current_table_from_active_tabs(self):
        workspace = self._selected_notebook_text(getattr(self, "notebook", None))
        self.current_table = None
        if workspace == self.workspace_tab_labels["engineering"]:
            selected = self._selected_notebook_text(
                getattr(self, "engineering_notebook", None)
            )
            for table_name in ("struts", "walers", "braces"):
                if selected == self.table_tab_labels[table_name]:
                    self.current_table = table_name
                    break
        elif workspace == self.workspace_tab_labels["materials"]:
            self._sync_current_settings_table()
        return self.current_table

    def _sync_current_settings_table(self):
        notebook = getattr(self, "materials_notebook", None)
        if notebook is None:
            notebook = getattr(self, "settings_notebook", None)
        if notebook is None:
            return
        selected_tab = notebook.select()
        if not selected_tab:
            return
        selected = notebook.tab(selected_tab, "text")
        for table_name in ("material_specs", "inventory"):
            if selected == self.table_tab_labels[table_name]:
                self.current_table = table_name
                return

    def _update_context_toolbar(self):
        toolbar = getattr(self, "context_toolbar", None)
        if toolbar is None:
            return
        self._sync_current_table_from_active_tabs()
        selected = self._selected_notebook_text(self.notebook)
        context_name = selected
        child_notebook = None
        if selected == self.workspace_tab_labels["engineering"]:
            child_notebook = getattr(self, "engineering_notebook", None)
        elif selected == self.workspace_tab_labels["materials"]:
            child_notebook = getattr(self, "materials_notebook", None)
        elif selected == self.workspace_tab_labels["analysis"]:
            child_notebook = getattr(self, "analysis_notebook", None)
        child_name = self._selected_notebook_text(child_notebook)
        if child_name:
            context_name = f"{selected}／{child_name}"
        if hasattr(self, "context_toolbar_context_var"):
            self.context_toolbar_context_var.set(f"目前區域：{context_name}")
        actions = {
            "walers": (
                "add", "delete", "up", "down", "validate", "redraw",
                "waler_solver", "waler_global_solver"
            ),
            "struts": (
                "add", "delete", "up", "down", "validate", "redraw", "support_solver"
            ),
            "braces": (
                "add", "delete", "up", "down", "validate", "redraw"
            ),
            "material_specs": ("add", "delete", "validate"),
            "inventory": ("add", "delete", "validate"),
        }.get(self.current_table, ())
        for button in self.context_toolbar_buttons.values():
            button.pack_forget()
        for name in actions:
            self.context_toolbar_buttons[name].pack(side="left", padx=6)

    def _toggle_execution_messages(self):
        self.execution_message_expanded = not self.execution_message_expanded
        if self.execution_message_expanded:
            self.execution_message_body.pack(fill="both", expand=True)
            self.execution_message_toggle_button.configure(text="隱藏詳細訊息 ▲")
            self.ascii_art_entry.lift()
        else:
            self.execution_message_body.pack_forget()
            self.execution_message_toggle_button.configure(text="顯示詳細訊息 ▼")

    def _load_initial_data(self):
        for table_name in (
            "walers",
            "struts",
            "braces",
            "inventory",
            "material_specs",
        ):
            self._refresh_tree(table_name)
        self._refresh_results_tree()
        self._refresh_project_case_list()

    def _refresh_tree(self, table_name):
        tree = self.treeviews[table_name]
        selected_index = None
        selection = tree.selection()
        if selection:
            selected_index = self._item_id_to_index(selection[0])
        tree.delete(*tree.get_children())
        data = getattr(self, table_name)
        display_columns = tuple(tree["columns"])
        row_columns = tuple(column for column in display_columns if column != "No")
        for index, row in enumerate(data):
            if table_name == "struts":
                self._migrate_strut_position_fields(row)
            values = [index + 1] + [
                self._format_display_value(row.get(col, ""))
                for col in row_columns
            ]
            tree.insert("", "end", iid=f"{table_name}_{index}", values=values)
        if selected_index is not None and data:
            selected_index = min(selected_index, len(data) - 1)
            item_id = f"{table_name}_{selected_index}"
            tree.selection_set(item_id)
            tree.focus(item_id)
        if table_name == "struts":
            self._on_strut_tree_select()
        elif table_name in ("walers", "braces"):
            self._on_geometry_tree_select(table_name)
        if table_name == "inventory":
            self._update_material_summary()

    @staticmethod
    def _format_display_value(value):
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _format_position_value(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value).strip()
        if number.is_integer():
            return str(int(number))
        return str(number)

    def _format_position_list(self, values):
        return ",".join(
            self._format_position_value(value)
            for value in values
            if value not in (None, "")
        )

    def _migrate_strut_position_fields(self, row):
        if not isinstance(row, dict):
            return row

        if str(row.get("BeamPositions", "") or "").strip() == "":
            beam_values = [
                row.get("Beam1"),
                row.get("Beam2"),
            ]
            migrated = self._format_position_list(beam_values)
            if migrated:
                row["BeamPositions"] = migrated

        if str(row.get("ColumnPositions", "") or "").strip() == "":
            column_values = [
                row.get("Column1"),
                row.get("Column2"),
            ]
            migrated = self._format_position_list(column_values)
            if migrated:
                row["ColumnPositions"] = migrated

        for old_key in ("Beam1", "Beam2", "Column1", "Column2"):
            row.pop(old_key, None)

        return row

    def _parse_position_list(self, value):
        if value is None:
            return [], None

        text = str(value).strip().replace("，", ",")
        if text == "":
            return [], None

        parts = text.split(",")
        if any(part.strip() == "" for part in parts):
            return [], "位置格式錯誤"

        positions = []
        for part in parts:
            token = part.strip()
            try:
                number = float(token)
            except ValueError:
                return [], f"{token} 不是有效數字"
            if not math.isfinite(number):
                return [], f"{token} 不是有效數字"
            positions.append(int(number) if number.is_integer() else number)

        return positions, None

    def _table_label(self, table_name):
        return self.table_tab_labels.get(table_name, table_name)

    def _field_label(self, table_name, field_name):
        return self.table_column_labels.get(table_name, {}).get(field_name, field_name)

    def _material_spec_options(self, usage):
        options = []
        seen = set()
        for row in self.material_specs:
            if str(row.get("Usage", "") or "").strip() != usage:
                continue
            spec = str(row.get("Spec", "") or "").strip()
            key = spec.casefold()
            if spec and key not in seen:
                options.append(spec)
                seen.add(key)
        return options

    @staticmethod
    def _material_spec_key(usage, spec):
        return (
            str(usage or "").strip().casefold(),
            str(spec or "").strip().casefold(),
        )

    def _material_spec_key_exists(self, usage, spec, *, exclude_index=None):
        target = self._material_spec_key(usage, spec)
        if not target[1]:
            return False
        return any(
            index != exclude_index
            and self._material_spec_key(row.get("Usage"), row.get("Spec"))
            == target
            for index, row in enumerate(self.material_specs)
        )

    def _material_spec_references(self, usage, spec):
        """Return every current string reference to one (Usage, Spec) key."""

        target = self._material_spec_key(usage, spec)
        references = {
            "inventory": [],
            "walers": [],
            "struts": [],
        }
        if not target[1]:
            return references
        references["inventory"] = [
            index
            for index, row in enumerate(self.inventory)
            if self._material_spec_key(row.get("Usage"), row.get("Spec"))
            == target
        ]
        if target[0] == "圍令".casefold():
            references["walers"] = [
                index
                for index, row in enumerate(self.walers)
                if self._material_spec_key("圍令", row.get("material_spec"))
                == target
            ]
        if target[0] == "支撐".casefold():
            references["struts"] = [
                index
                for index, row in enumerate(self.struts)
                if self._material_spec_key("支撐", row.get("material_spec"))
                == target
            ]
        return references

    @staticmethod
    def _material_spec_reference_count(references):
        return sum(len(indices) for indices in references.values())

    @staticmethod
    def _material_spec_reference_text(references):
        return (
            f"庫存：{len(references.get('inventory', ()))} 筆\n"
            f"圍令：{len(references.get('walers', ()))} 筆\n"
            f"支撐：{len(references.get('struts', ()))} 筆"
        )

    def _rename_material_spec_references(
        self,
        usage,
        old_spec,
        new_spec,
        *,
        references=None,
    ):
        references = references or self._material_spec_references(
            usage,
            old_spec,
        )
        for index in references["inventory"]:
            self.inventory[index]["Spec"] = new_spec
        for index in references["walers"]:
            self.walers[index]["material_spec"] = new_spec
        for index in references["struts"]:
            self.struts[index]["material_spec"] = new_spec
        return references

    @staticmethod
    def _is_required_rc_spec(row):
        return (
            str(row.get("Usage", "") or "").strip() == REQUIRED_RC_SPEC["Usage"]
            and str(row.get("Spec", "") or "").strip().upper() == "RC"
        )

    def _cell_editor_options(self, table_name, column, index):
        """Return (choices, state) for table cells with controlled values."""

        if table_name == "material_specs" and column == "Usage":
            return ("支撐", "圍令"), "readonly"
        if table_name == "inventory" and column == "Usage":
            return ("支撐", "圍令"), "readonly"
        if table_name == "inventory" and column == "Spec":
            usage = str(self.inventory[index].get("Usage", "") or "").strip()
            return ("", *self._material_spec_options(usage)), "readonly"
        if column == "material_spec" and table_name in ("walers", "struts"):
            usage = "圍令" if table_name == "walers" else "支撐"
            return ("", *self._material_spec_options(usage)), "readonly"
        return None, "normal"

    def _on_tree_double_click(self, event):
        tree = event.widget
        row_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if not row_id or not column_id:
            return

        column = self._tree_column_key(tree, column_id)
        if column in (None, "No"):
            return
        table_name = self._get_table_name_by_tree(tree)
        index = self._item_id_to_index(row_id)
        if table_name is None or index is None:
            return
        self._begin_cell_edit(table_name, index, column, row_id=row_id)

    def _begin_cell_edit(self, table_name, index, column, *, row_id=None):
        """Open the shared in-place editor for mouse and programmatic use."""

        tree = self.treeviews.get(table_name)
        rows = getattr(self, table_name, None)
        if tree is None or rows is None or not (0 <= index < len(rows)):
            return False
        if column in (None, "No"):
            return False
        row_id = row_id or f"{table_name}_{index}"
        if (
            table_name == "material_specs"
            and self._is_required_rc_spec(self.material_specs[index])
            and column in ("Usage", "Spec")
        ):
            messagebox.showinfo(
                "必要規格",
                "圍令規格 RC 為必要施工規格，不可修改或刪除。",
                parent=self.root,
            )
            return False
        tree.see(row_id)
        tree.update_idletasks()
        bbox = tree.bbox(row_id, column)
        if not bbox:
            return False

        x, y, width, height = bbox
        current_value = tree.set(row_id, column)

        if self.editing_entry is not None:
            self.editing_entry.destroy()

        combobox_values, combobox_state = self._cell_editor_options(
            table_name,
            column,
            index,
        )

        if combobox_values is None:
            entry = tk.Entry(tree)
            entry.insert(0, current_value)
        else:
            entry = ttk.Combobox(
                tree,
                values=combobox_values,
                state=combobox_state,
            )
            entry.set(current_value)
        entry.place(x=x, y=y, width=width, height=height)
        entry.focus_set()

        def save_edit(event=None):
            self._finish_edit(tree, row_id, column, entry)

        entry.bind("<Return>", save_edit)
        if isinstance(entry, ttk.Combobox):
            entry.bind("<<ComboboxSelected>>", save_edit)
        entry.bind("<FocusOut>", save_edit)
        self.editing_entry = entry
        return True

    def _finish_edit(self, tree, row_id, column, entry_widget):
        if not entry_widget.winfo_exists():
            return
        new_value = entry_widget.get().strip()
        entry_widget.destroy()
        self.editing_entry = None

        table_name = self._get_table_name_by_tree(tree)
        if table_name is None:
            return

        index = self._item_id_to_index(row_id)
        if index is None:
            return

        rows = getattr(self, table_name)
        project_field_committed = table_name in GEOMETRY_TABLES
        if project_field_committed:
            changed, value, error = self._commit_project_field_edit(
                table_name,
                index,
                column,
                new_value,
            )
            if error:
                messagebox.showwarning(
                    "輸入錯誤",
                    error + " 已保留原值。",
                    parent=self.root,
                )
                return
            if not changed:
                return
        else:
            value = self._parse_cell_value(table_name, column, new_value)
            old_value = rows[index].get(column, "")
            if value == old_value:
                return

        if table_name == "material_specs":
            row = self.material_specs[index]
            old_usage = str(row.get("Usage", "") or "").strip()
            old_spec = str(row.get("Spec", "") or "").strip()
            proposed_usage = value if column == "Usage" else old_usage
            proposed_spec = value if column == "Spec" else old_spec
            if proposed_spec and self._material_spec_key_exists(
                proposed_usage,
                proposed_spec,
                exclude_index=index,
            ):
                messagebox.showwarning(
                    "規格重複",
                    f"{proposed_usage}的材料規格「{proposed_spec}」已存在。",
                    parent=self.root,
                )
                return

            references = self._material_spec_references(old_usage, old_spec)
            reference_count = self._material_spec_reference_count(references)
            if column == "Usage" and reference_count:
                messagebox.showwarning(
                    "用途不可變更",
                    (
                        f"材料規格「{old_spec}」仍被使用，不可直接變更用途。\n\n"
                        f"{self._material_spec_reference_text(references)}\n\n"
                        "請先移除或更換引用。"
                    ),
                    parent=self.root,
                )
                return
            if column == "Spec" and old_spec and not proposed_spec:
                messagebox.showwarning(
                    "材料規格不可空白",
                    "既有材料規格不可改為空白。",
                    parent=self.root,
                )
                return
            references_changed = False
            if column == "Spec" and reference_count:
                confirmed = messagebox.askyesno(
                    "同步更新材料規格",
                    (
                        f"材料規格「{old_spec}」目前正在被引用。\n\n"
                        f"{self._material_spec_reference_text(references)}\n\n"
                        f"是否同步更新為「{proposed_spec}」？"
                    ),
                    parent=self.root,
                )
                if not confirmed:
                    return
                self._rename_material_spec_references(
                    old_usage,
                    old_spec,
                    proposed_spec,
                    references=references,
                )
                references_changed = True

            row[column] = value
            tree.set(row_id, column, self._format_display_value(value))
            if references_changed:
                for changed_table in ("inventory", "walers", "struts"):
                    if references[changed_table]:
                        self._refresh_tree(changed_table)
                if references["inventory"]:
                    self._update_material_summary()
                self._handle_input_data_changed(
                    preserve_view=True,
                    table_name=None,
                    field_name="material_spec",
                )
            else:
                self._handle_input_data_changed(
                    preserve_view=True,
                    table_name="material_specs",
                    field_name=column,
                )
            return

        if not project_field_committed:
            rows[index][column] = value
        tree_columns = (
            tuple(tree["columns"])
            if hasattr(tree, "__getitem__")
            else tuple(
                getattr(self, "table_columns", self.TABLE_COLUMNS).get(
                    table_name,
                    (),
                )
            )
        )
        if column in tree_columns:
            tree.set(row_id, column, self._format_display_value(value))
        if table_name == "inventory":
            if column == "Usage":
                current_spec = str(rows[index].get("Spec", "") or "").strip()
                if (
                    current_spec
                    and not any(
                        self._material_spec_key(value, option)
                        == self._material_spec_key(value, current_spec)
                        for option in self._material_spec_options(value)
                    )
                ):
                    rows[index]["Spec"] = ""
                    tree.set(row_id, "Spec", "")
            self._update_material_summary()
        if not project_field_committed:
            self._handle_input_data_changed(
                preserve_view=True,
                table_name=table_name,
                field_name=column,
            )
        if table_name == "struts" and index == getattr(self, "selected_strut_index", None):
            self._load_strut_detail(index)
            self._sync_preview_to_strut_selection(index)
        elif table_name in ("walers", "braces"):
            if index == getattr(self, "selected_geometry_indices", {}).get(table_name):
                self._load_geometry_detail(table_name, index)
            kind = "waler" if table_name == "walers" else "brace"
            self._sync_preview_to_geometry_selection(table_name, kind, index)

    def _item_id_to_index(self, item_id):
        try:
            return int(str(item_id).rsplit("_", 1)[1])
        except (IndexError, ValueError):
            return None

    def _get_table_name_by_tree(self, tree_widget):
        for name, tree in self.treeviews.items():
            if tree is tree_widget:
                return name
        return None

    def _parse_cell_value(self, table_name, column, value):
        if value == "":
            return ""

        if table_name == "struts" and column in ("BeamPositions", "ColumnPositions"):
            return value.replace("，", ",")

        if column in self.numeric_columns.get(table_name, []):
            try:
                number = float(value)
                if number.is_integer():
                    return int(number)
                return number
            except ValueError:
                return value

        return value

    def add_row(self):
        table_name = self.current_table
        if table_name not in self.table_columns:
            return
        new_row = {col: "" for col in self.table_columns[table_name]}
        if table_name == "struts":
            new_row["TargetJackRegion"] = 2
        elif table_name == "material_specs":
            new_row["Usage"] = "支撐"
        elif table_name == "inventory":
            new_row["Usage"] = "支撐"
        getattr(self, table_name).append(new_row)
        self._refresh_tree(table_name)
        new_index = len(getattr(self, table_name)) - 1
        self._select_input_row(table_name, new_index)
        self._handle_input_data_changed(preserve_view=True, table_name=table_name)
        if table_name == "material_specs":
            def edit_new_material_spec():
                self._begin_cell_edit(
                    "material_specs",
                    new_index,
                    "Spec",
                )

            self.root.after_idle(edit_new_material_spec)

    def delete_row(self):
        table_name = self.current_table
        if table_name not in self.treeviews:
            return
        tree = self.treeviews[table_name]
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("刪除列", "請先選取要刪除的列。")
            return

        index = self._item_id_to_index(selection[0])
        if index is None:
            return

        if (
            table_name == "material_specs"
            and self._is_required_rc_spec(self.material_specs[index])
        ):
            messagebox.showwarning(
                "不可刪除",
                "圍令規格 RC 為必要施工規格，不可刪除。",
                parent=self.root,
            )
            return

        if table_name == "material_specs":
            row = self.material_specs[index]
            usage = str(row.get("Usage", "") or "").strip()
            spec = str(row.get("Spec", "") or "").strip()
            references = self._material_spec_references(usage, spec)
            if self._material_spec_reference_count(references):
                messagebox.showwarning(
                    "材料規格仍被使用",
                    (
                        f"材料規格「{spec}」仍被使用。\n\n"
                        f"{self._material_spec_reference_text(references)}\n\n"
                        "請先移除或更換引用後再刪除。"
                    ),
                    parent=self.root,
                )
                return

        getattr(self, table_name).pop(index)
        self._refresh_tree(table_name)
        self._handle_input_data_changed(
            preserve_view=True,
            table_name=table_name,
            dxf_binding_changed=table_name in GEOMETRY_TABLES,
        )

    def _move_current_table_row(self, direction):
        if self.current_table not in ("walers", "struts", "braces"):
            return

        tree = self.treeviews.get(self.current_table)
        if tree is None:
            return
        data_list = getattr(self, self.current_table, None)
        if data_list is None:
            return

        moved_index = self.move_selected_row(tree, data_list, direction)
        if moved_index is None:
            return

        self._refresh_tree(self.current_table)

        moved_item_id = f"{self.current_table}_{moved_index}"
        if moved_item_id in tree.get_children():
            tree.selection_set(moved_item_id)
            tree.focus(moved_item_id)
            tree.see(moved_item_id)

        self._handle_input_data_changed(preserve_view=True, table_name=self.current_table)

    def move_selected_row(self, tree, data_list, direction):
        selection = tree.selection()
        if not selection:
            return None

        index = self._item_id_to_index(selection[0])
        if index is None:
            return None

        target_index = index + direction
        if target_index < 0 or target_index >= len(data_list):
            return None

        data_list[index], data_list[target_index] = data_list[target_index], data_list[index]
        return target_index

    def validate_data(self):
        self._clear_error_tags()
        report = ProjectDataValidator(
            field_label=self._field_label,
        ).validate(self._ensure_project_data())

        tagged_rows = set()
        for issue in report.errors:
            key = (issue.table, issue.row_index)
            if key not in tagged_rows:
                self._tag_error_row(issue.table, issue.row_index - 1)
                tagged_rows.add(key)

        def report_lines(title, issues):
            lines = [title]
            for issue in issues:
                lines.append(
                    f"{self._table_label(issue.table)} "
                    f"第 {issue.row_index} 列：{issue.message}"
                )
            return lines

        if report.errors:
            messages = report_lines("【錯誤】", report.errors)
            if report.warnings:
                messages.extend(["", *report_lines("【警告】", report.warnings)])
            messagebox.showerror("驗證失敗", "\n".join(messages))
            return False
        if report.warnings:
            messages = report_lines("【警告】", report.warnings)
            messagebox.showwarning("驗證完成", "\n".join(messages))
            return True
        messagebox.showinfo("驗證成功", "所有資料皆通過驗證。")
        return True

    def _clear_error_tags(self):
        for tree in self.treeviews.values():
            for item in tree.get_children():
                tree.item(item, tags=())

    def _tag_error_row(self, table_name, index):
        tree = self.treeviews[table_name]
        item_id = f"{table_name}_{index}"
        if item_id in tree.get_children():
            tree.item(item_id, tags=("error",))

    def _waler_coords(self, waler_row):
        x1 = self._to_number(waler_row.get("StartX"))
        y1 = self._to_number(waler_row.get("StartY"))
        x2 = self._to_number(waler_row.get("EndX"))
        y2 = self._to_number(waler_row.get("EndY"))
        if None in (x1, y1, x2, y2):
            return None
        if not self._line_length_positive(x1, y1, x2, y2):
            return None
        return x1, y1, x2, y2

    def _to_number(self, value):
        if isinstance(value, (int, float)):
            return value
        if value is None:
            return None
        text = str(value).strip()
        if text == "":
            return None
        try:
            number = float(text)
            return int(number) if number.is_integer() else number
        except ValueError:
            return None

    @staticmethod
    def _line_length(x1, y1, x2, y2):
        return math.hypot(x2 - x1, y2 - y1)

    @staticmethod
    def _line_length_positive(x1, y1, x2, y2):
        return math.hypot(x2 - x1, y2 - y1) > 0

    @staticmethod
    def _readable_line_angle(start_x, start_y, end_x, end_y):
        angle = math.degrees(math.atan2(end_y - start_y, end_x - start_x))
        if angle > 90:
            angle -= 180
        elif angle < -90:
            angle += 180
        return angle

    def _draw_segment_length_label(
        self,
        start_x,
        start_y,
        end_x,
        end_y,
        length,
        color,
        fontsize=8,
        zorder=11,
    ):
        center_x = (start_x + end_x) / 2
        center_y = (start_y + end_y) / 2
        angle = self._readable_line_angle(start_x, start_y, end_x, end_y)
        return self.ax.annotate(
            f"{length:g}",
            (center_x, center_y),
            xytext=(0, -14),
            textcoords="offset points",
            color=color,
            fontsize=fontsize,
            fontweight="bold",
            horizontalalignment="center",
            verticalalignment="top",
            rotation=angle,
            rotation_mode="anchor",
            bbox={
                "facecolor": "white",
                "alpha": 0.78,
                "edgecolor": "none",
                "pad": 1.2,
            },
            zorder=zorder,
        )

    def _waler_direction_unit(self, waler_row):
        coords = self._waler_coords(waler_row)
        if coords is None:
            return None
        x1, y1, x2, y2 = coords
        length = math.hypot(x2 - x1, y2 - y1)
        if length <= 0:
            return None
        return (x2 - x1) / length, (y2 - y1) / length

    def _draw_strut_angle_brace(
        self,
        strut_start_x,
        strut_start_y,
        strut_end_x,
        strut_end_y,
        from_start_endpoint,
        waler_row,
        length,
        toward_start,
        plotted_labels,
        all_x,
        all_y,
    ):
        if length is None or length <= 0:
            return
        waler_unit = self._waler_direction_unit(waler_row)
        if waler_unit is None:
            return

        strut_dx = strut_end_x - strut_start_x
        strut_dy = strut_end_y - strut_start_y
        strut_length = math.hypot(strut_dx, strut_dy)
        if strut_length <= 0:
            return

        strut_ux = strut_dx / strut_length
        strut_uy = strut_dy / strut_length
        inset = min(1500, strut_length)
        if from_start_endpoint:
            waler_base_x = strut_start_x
            waler_base_y = strut_start_y
            support_x = strut_start_x + strut_ux * inset
            support_y = strut_start_y + strut_uy * inset
        else:
            waler_base_x = strut_end_x
            waler_base_y = strut_end_y
            support_x = strut_end_x - strut_ux * inset
            support_y = strut_end_y - strut_uy * inset

        waler_ux, waler_uy = waler_unit
        direction = -1 if toward_start else 1
        waler_x = waler_base_x + waler_ux * direction * length
        waler_y = waler_base_y + waler_uy * direction * length
        self.ax.plot(
            [support_x, waler_x],
            [support_y, waler_y],
            color="#1565c0",
            linewidth=2.1,
            solid_capstyle="round",
            label="角撐" if "角撐" not in plotted_labels else None,
            zorder=5,
        )
        plotted_labels.add("角撐")
        all_x.extend([support_x, waler_x])
        all_y.extend([support_y, waler_y])

    def update_preview(self, preserve_view=False):
        self._cancel_preview_scroll_redraw()
        self._end_preview_interaction(redraw=False)
        if hasattr(self, "preview_interaction"):
            self.preview_interaction.end_pan()
        self._preview_pan_pixels_per_data = None
        preserved_xlim = None
        preserved_ylim = None
        if preserve_view:
            try:
                preserved_xlim = tuple(self.ax.get_xlim())
                preserved_ylim = tuple(self.ax.get_ylim())
            except Exception:
                preserved_xlim = None
                preserved_ylim = None

        self.ax.clear()
        self._preview_selection_targets = []
        self._preview_selection_overlay = []
        self.ax.set_title("開挖支撐系統輸入預覽")
        self.ax.set_xlabel("X")
        self.ax.set_ylabel("Y")
        self.ax.grid(True)
        self.ax.set_aspect("equal", adjustable="datalim")
        self.ax.format_coord = self._format_preview_coordinates

        legend_handles = []
        plotted_labels = set()

        all_x = []
        all_y = []
        waler_by_id = {
            str(row.get("WalerID", "")).strip(): row
            for row in self.walers
            if str(row.get("WalerID", "")).strip()
        }

        for row_index, row in enumerate(self.walers):
            x1 = self._to_number(row.get("StartX"))
            y1 = self._to_number(row.get("StartY"))
            x2 = self._to_number(row.get("EndX"))
            y2 = self._to_number(row.get("EndY"))
            if None in (x1, y1, x2, y2):
                continue
            line, = self.ax.plot([x1, x2], [y1, y2], color="black", linewidth=3, label="圍令" if "圍令" not in plotted_labels else None)
            waler_id = str(row.get("WalerID", "") or f"W{row_index + 1}")
            self._register_preview_segment(
                "waler",
                waler_id,
                (x1, y1),
                (x2, y2),
                table_name="walers",
                row_index=row_index,
            )
            plotted_labels.add("圍令")
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            self.ax.text(mid_x, mid_y, str(row.get("WalerID", "")), color="black", fontsize=9, verticalalignment="center", horizontalalignment="center")
            all_x.extend([x1, x2])
            all_y.extend([y1, y2])

        beam_x = []
        beam_y = []
        column_x = []
        column_y = []
        for row_index, row in enumerate(self.struts):
            self._migrate_strut_position_fields(row)
            x1 = self._to_number(row.get("StartX"))
            y1 = self._to_number(row.get("StartY"))
            x2 = self._to_number(row.get("EndX"))
            y2 = self._to_number(row.get("EndY"))
            if None in (x1, y1, x2, y2):
                continue
            line, = self.ax.plot([x1, x2], [y1, y2], color="black", linewidth=3, label="支撐" if "支撐" not in plotted_labels else None)
            strut_id = str(row.get("StrutID", "") or f"S{row_index + 1}")
            self._register_preview_segment(
                "strut",
                strut_id,
                (x1, y1),
                (x2, y2),
                table_name="struts",
                row_index=row_index,
            )
            plotted_labels.add("支撐")
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            self.ax.text(mid_x, mid_y, str(row.get("StrutID", "")), color="black", fontsize=9, verticalalignment="bottom", horizontalalignment="center")
            all_x.extend([x1, x2])
            all_y.extend([y1, y2])

            length = self._line_length(x1, y1, x2, y2)
            beam_positions, _ = self._parse_position_list(row.get("BeamPositions", ""))
            column_positions, _ = self._parse_position_list(row.get("ColumnPositions", ""))
            for positions, point_x, point_y, color, label_name in [
                (beam_positions, beam_x, beam_y, "purple", "Bm"),
                (column_positions, column_x, column_y, "green", "C"),
            ]:
                for station_num in positions:
                    if length <= 0 or not (0 <= station_num <= length):
                        continue
                    point = point_on_line_by_station(x1, y1, x2, y2, station_num)
                    if point is None:
                        continue
                    px, py = point
                    point_x.append(px)
                    point_y.append(py)
                    point_kind = "beam" if label_name == "Bm" else "column"
                    self._register_preview_point(
                        point_kind,
                        f"{strut_id}@{station_num:g}",
                        (px, py),
                        table_name="struts",
                        row_index=row_index,
                        key=f"{point_kind}:{strut_id}:{station_num:g}",
                    )
                    self.ax.text(px, py, label_name, color=color, fontsize=8, verticalalignment="bottom", horizontalalignment="left")
                    all_x.append(px)
                    all_y.append(py)

            from_waler = str(row.get("FromWaler", "") or "").strip()
            to_waler = str(row.get("ToWaler", "") or "").strip()
            if from_waler in waler_by_id:
                self._draw_strut_angle_brace(
                    x1,
                    y1,
                    x2,
                    y2,
                    True,
                    waler_by_id[from_waler],
                    self._to_number(row.get("FromBraceToWalerStartLen")),
                    True,
                    plotted_labels,
                    all_x,
                    all_y,
                )
                self._draw_strut_angle_brace(
                    x1,
                    y1,
                    x2,
                    y2,
                    True,
                    waler_by_id[from_waler],
                    self._to_number(row.get("FromBraceToWalerEndLen")),
                    False,
                    plotted_labels,
                    all_x,
                    all_y,
                )
            if to_waler in waler_by_id:
                self._draw_strut_angle_brace(
                    x1,
                    y1,
                    x2,
                    y2,
                    False,
                    waler_by_id[to_waler],
                    self._to_number(row.get("ToBraceToWalerStartLen")),
                    True,
                    plotted_labels,
                    all_x,
                    all_y,
                )
                self._draw_strut_angle_brace(
                    x1,
                    y1,
                    x2,
                    y2,
                    False,
                    waler_by_id[to_waler],
                    self._to_number(row.get("ToBraceToWalerEndLen")),
                    False,
                    plotted_labels,
                    all_x,
                    all_y,
                )

        if beam_x:
            self.ax.scatter(
                beam_x,
                beam_y,
                color="purple",
                marker="o",
                s=60,
                label="托梁" if "托梁" not in plotted_labels else None,
            )
            plotted_labels.add("托梁")
        if column_x:
            self.ax.scatter(
                column_x,
                column_y,
                color="green",
                marker="s",
                s=60,
                label="中間柱" if "中間柱" not in plotted_labels else None,
            )
            plotted_labels.add("中間柱")

        for row_index, row in enumerate(self.braces):
            x1 = self._to_number(row.get("StartX"))
            y1 = self._to_number(row.get("StartY"))
            x2 = self._to_number(row.get("EndX"))
            y2 = self._to_number(row.get("EndY"))
            if None in (x1, y1, x2, y2):
                continue
            line, = self.ax.plot([x1, x2], [y1, y2], color="orange", linestyle="--", linewidth=2, label="斜撐" if "斜撐" not in plotted_labels else None)
            brace_id = str(row.get("BraceID", "") or f"B{row_index + 1}")
            self._register_preview_segment(
                "brace",
                brace_id,
                (x1, y1),
                (x2, y2),
                table_name="braces",
                row_index=row_index,
            )
            plotted_labels.add("斜撐")
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2
            self.ax.text(mid_x, mid_y, str(row.get("BraceID", "")), color="orange", fontsize=9, verticalalignment="center", horizontalalignment="center")
            all_x.extend([x1, x2])
            all_y.extend([y1, y2])

        self._draw_result_overlays()

        if all_x and all_y:
            padding_x = (max(all_x) - min(all_x)) * 0.05 if max(all_x) != min(all_x) else 100
            padding_y = (max(all_y) - min(all_y)) * 0.05 if max(all_y) != min(all_y) else 100
            self.ax.set_xlim(min(all_x) - padding_x, max(all_x) + padding_x)
            self.ax.set_ylim(min(all_y) - padding_y, max(all_y) + padding_y)

        home_xlim = tuple(self.ax.get_xlim())
        home_ylim = tuple(self.ax.get_ylim())

        legend_handles, _legend_labels = self.ax.get_legend_handles_labels()
        if legend_handles:
            self.ax.legend()
        self.preview_counts_text = self.ax.text(
            0.01,
            0.99,
            f"圍令：{len(self.walers)}\n支撐：{len(self.struts)}\n斜撐：{len(self.braces)}",
            transform=self.ax.transAxes,
            verticalalignment="top",
            horizontalalignment="left",
            fontsize=10,
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "black"},
        )
        self._preview_home_xlim = home_xlim
        self._preview_home_ylim = home_ylim
        if preserve_view and preserved_xlim is not None and preserved_ylim is not None:
            self.ax.set_xlim(preserved_xlim)
            self.ax.set_ylim(preserved_ylim)

        self._draw_preview_selection_highlight()
        self.canvas.draw()
        if hasattr(self, "preview_toolbar"):
            self.preview_toolbar.update()
            self.preview_toolbar.push_current()
            if preserve_view and preserved_xlim is not None and preserved_ylim is not None:
                self.preview_toolbar.set_zoom_percent(self._get_preview_zoom_percent())
            else:
                self.preview_toolbar.set_zoom_percent(100)

    def _draw_result_overlays(self):
        for result_id, item in self.result_items.items():
            if not item.get("visible", True):
                continue
            result_type = item.get("type")
            result = item.get("result")
            if result_type == "waler":
                self._draw_single_waler_solution_overlay(result)
            elif result_type == "support":
                self._draw_support_solution_overlay(result_id, result, item)

    def _draw_single_waler_solution_overlay(self, result):
        plan = result.get("selected_plan")
        waler_id = str(result.get("waler_id", "")).strip()
        if not plan or not waler_id:
            return

        waler_row = next(
            (row for row in self.walers if str(row.get("WalerID", "")).strip() == waler_id),
            None,
        )
        if not waler_row:
            return

        x1 = self._to_number(waler_row.get("StartX"))
        y1 = self._to_number(waler_row.get("StartY"))
        x2 = self._to_number(waler_row.get("EndX"))
        y2 = self._to_number(waler_row.get("EndY"))
        if None in (x1, y1, x2, y2):
            return

        total_length = self._line_length(x1, y1, x2, y2)
        if total_length <= 0:
            return

        segments = [int(round(v)) for v in plan.get("segments", []) if isinstance(v, (int, float))]
        joints = [int(round(v)) for v in plan.get("joints", []) if isinstance(v, (int, float))]
        if not segments:
            return

        if len(joints) != len(segments) - 1:
            joints = []
            position = 0
            for seg in segments[:-1]:
                position += seg
                joints.append(position)

        steel_length = sum(segments)
        boundaries = [0] + joints + [steel_length]
        colors = ["red", "green", "blue", "orange", "purple", "cyan", "magenta", "brown"]

        for idx, (seg_len, start_pos, end_pos) in enumerate(zip(segments, boundaries, boundaries[1:])):
            if total_length == 0:
                continue
            frac_start = start_pos / total_length
            frac_end = end_pos / total_length
            sx = x1 + (x2 - x1) * frac_start
            sy = y1 + (y2 - y1) * frac_start
            ex = x1 + (x2 - x1) * frac_end
            ey = y1 + (y2 - y1) * frac_end
            color = colors[idx % len(colors)]
            self.ax.plot([sx, ex], [sy, ey], color=color, linewidth=6, alpha=0.7, solid_capstyle="round")
            self._draw_segment_length_label(
                sx,
                sy,
                ex,
                ey,
                seg_len,
                color=color,
                fontsize=9,
            )

        tail_adjustment = int(round(float(plan.get("tail_adjustment", 0) or 0)))
        tail_gap = int(round(float(plan.get("gap", 0) or 0)))

        def point_at(position):
            fraction = max(0.0, min(1.0, position / total_length))
            return (
                x1 + (x2 - x1) * fraction,
                y1 + (y2 - y1) * fraction,
            )

        if tail_adjustment > 0:
            shim_start = steel_length
            shim_end = steel_length + tail_adjustment
            sx, sy = point_at(shim_start)
            ex, ey = point_at(shim_end)
            self.ax.plot(
                [sx, ex],
                [sy, ey],
                color="#f9a825",
                linewidth=8,
                alpha=0.9,
                solid_capstyle="butt",
                zorder=14,
            )
            self._draw_segment_length_label(
                sx,
                sy,
                ex,
                ey,
                tail_adjustment,
                color="#9a6700",
                fontsize=9,
            )

        if tail_gap > 0:
            gap_start = steel_length + tail_adjustment
            gap_end = gap_start + tail_gap
            sx, sy = point_at(gap_start)
            ex, ey = point_at(gap_end)
            self.ax.plot(
                [sx, ex],
                [sy, ey],
                color="#616161",
                linewidth=4,
                linestyle="--",
                alpha=0.9,
                zorder=14,
            )
            self._draw_segment_length_label(
                sx,
                sy,
                ex,
                ey,
                tail_gap,
                color="#424242",
                fontsize=9,
            )

        direction_x = (x2 - x1) / total_length
        direction_y = (y2 - y1) / total_length
        normal_x = -direction_y
        normal_y = direction_x
        joint_half_length = max(80.0, total_length * 0.008)
        for joint_pos in joints:
            frac = joint_pos / total_length
            jx = x1 + (x2 - x1) * frac
            jy = y1 + (y2 - y1) * frac
            self.ax.plot(
                [
                    jx - normal_x * joint_half_length,
                    jx + normal_x * joint_half_length,
                ],
                [
                    jy - normal_y * joint_half_length,
                    jy + normal_y * joint_half_length,
                ],
                color="#d62728",
                linewidth=3.5,
                solid_capstyle="butt",
                zorder=13,
            )

    def _draw_support_solution_overlay(self, zoning, solution, item=None):
        plans = getattr(solution, "plans", None)
        if not plans:
            return

        struts_by_id = {
            str(row.get("SupportID") or row.get("StrutID") or "").strip(): row
            for row in self.struts
            if str(row.get("SupportID") or row.get("StrutID") or "").strip()
        }

        for plan in plans:
            support_id = str(getattr(plan, "support_id", "") or "").strip()
            if item is not None and not self._support_plan_visible(item, support_id):
                continue
            strut_row = struts_by_id.get(support_id)
            if not strut_row:
                continue

            x1 = self._to_number(strut_row.get("StartX"))
            y1 = self._to_number(strut_row.get("StartY"))
            x2 = self._to_number(strut_row.get("EndX"))
            y2 = self._to_number(strut_row.get("EndY"))
            if None in (x1, y1, x2, y2):
                continue

            pieces = list(plan.pieces)
            line_length = self._line_length(x1, y1, x2, y2)
            result_length = sum(length for _, length in pieces) + plan.gap
            if line_length <= 0 or result_length <= 0:
                continue

            def point_at_station(station):
                ratio = min(1.0, max(0.0, float(station) / result_length))
                return (
                    x1 + (x2 - x1) * ratio,
                    y1 + (y2 - y1) * ratio,
                )

            self.ax.plot(
                [x1, x2],
                [y1, y2],
                color="#607d8b",
                linewidth=3,
                alpha=0.35,
                solid_capstyle="round",
                zorder=8,
            )

            piece_colors = {
                "steel": "#1f77b4",
                "shim": "#2ca02c",
                "jack": "#f2c811",
            }
            piece_text_colors = {
                "steel": "#0b3d91",
                "shim": "#176b2c",
                "jack": "#7a5b00",
            }
            station = 0.0
            for piece_type, piece_length in pieces:
                next_station = station + piece_length
                segment_start = point_at_station(station)
                segment_end = point_at_station(next_station)
                color = piece_colors.get(piece_type, "#7f7f7f")
                text_color = piece_text_colors.get(piece_type, "#444444")
                self.ax.plot(
                    [segment_start[0], segment_end[0]],
                    [segment_start[1], segment_end[1]],
                    color=color,
                    linewidth=6,
                    alpha=0.92,
                    solid_capstyle="butt",
                    zorder=9,
                )

                self._draw_segment_length_label(
                    segment_start[0],
                    segment_start[1],
                    segment_end[0],
                    segment_end[1],
                    piece_length,
                    color=text_color,
                    fontsize=8,
                    zorder=11,
                )
                station = next_station

            direction_x = (x2 - x1) / line_length
            direction_y = (y2 - y1) / line_length
            normal_x = -direction_y
            normal_y = direction_x
            joint_half_length = max(80.0, line_length * 0.008)
            for joint_position in plan.joints:
                jx, jy = point_at_station(joint_position)
                self.ax.plot(
                    [
                        jx - normal_x * joint_half_length,
                        jx + normal_x * joint_half_length,
                    ],
                    [
                        jy - normal_y * joint_half_length,
                        jy + normal_y * joint_half_length,
                    ],
                    color="#d62728",
                    linewidth=3.5,
                    solid_capstyle="butt",
                    zorder=13,
                )

            jack_center = plan.jack_center
            if jack_center < 0:
                continue
            jack_x, jack_y = point_at_station(jack_center)
            strut_index = next(
                (
                    index
                    for index, row in enumerate(self.struts)
                    if str(row.get("SupportID") or row.get("StrutID") or "").strip()
                    == support_id
                ),
                None,
            )
            self._register_preview_point(
                "jack",
                support_id,
                (jack_x, jack_y),
                table_name="struts",
                row_index=strut_index,
                key=f"jack:{zoning}:{support_id}",
            )
            self.ax.annotate(
                f"★{jack_center:.0f}",
                (jack_x, jack_y),
                xytext=(0, 18),
                textcoords="offset points",
                color="#7a5b00",
                fontsize=8,
                fontweight="bold",
                horizontalalignment="center",
                verticalalignment="bottom",
                bbox={
                    "facecolor": "white",
                    "alpha": 0.78,
                    "edgecolor": "none",
                    "pad": 1.2,
                },
                zorder=15,
            )

    def _has_modified_waler_results(self, waler_id, *, include_global=True):
        return any(
            item.get("type") == "waler"
            and isinstance(item.get("result"), dict)
            and ProjectResultModel.waler_result_identity(result_id, item)
            == str(waler_id or "").strip()
            and bool(item["result"].get("manual_modified"))
            and (
                include_global
                or not bool(item["result"].get("global_selected"))
            )
            for result_id, item in self.result_items.items()
        )

    def _open_waler_solver(self):
        waler_solver_guard = self._ensure_waler_solver_guard()
        if waler_solver_guard.is_busy:
            self._show_waler_solver_busy("Single")
            return
        if not self.validate_data():
            return

        _, waler_builder = self._ensure_solver_input_builders()
        try:
            waler_inputs = waler_builder.build_all(self.project_data)
        except SolverInputBuildError as exc:
            self.show_result(f"無法建立圍令 Solver 輸入：\n{exc}")
            return
        if not waler_inputs:
            self.show_result("錯誤：找不到圍令輸入資料")
            return

        waler_ids = list(waler_inputs.keys())
        dialog = WalerSelectionDialog(self.root, waler_ids)
        selected_waler = dialog.open()
        if selected_waler is None:
            return
        if self._has_modified_waler_results(
            selected_waler,
            include_global=False,
        ):
            confirmed = messagebox.askyesno(
                "重新計算圍令",
                (
                    f"圍令 {selected_waler} 有已修改的方案。\n"
                    "重新計算會以新的五個方案取代先前的單支方案；"
                    "全域方案會保留。是否繼續？"
                ),
                parent=self.root,
            )
            if not confirmed:
                return

        waler_input = waler_inputs[selected_waler]
        if waler_input.material_spec and not waler_input.purchasable_lengths:
            self.show_result(
                f"錯誤：圍令 {selected_waler} 所選規格 "
                f"{waler_input.material_spec} 沒有可用庫存料長"
            )
            return
        solver_dialog = WalerSolverDialog(
            self.root,
            waler_input,
            self.solver_memory,
            self._store_waler_result,
            optimize_waler=self.make_waler_optimizer(),
            waler_solver_guard=waler_solver_guard,
        )
        solver_dialog.open()

    def _open_waler_global_solver(self):
        """Open the project-wide exact selector without changing local scoring."""

        waler_solver_guard = self._ensure_waler_solver_guard()
        if waler_solver_guard.is_busy:
            self._show_waler_solver_busy("Global")
            return
        if not self.validate_data():
            return

        _, waler_builder = self._ensure_solver_input_builders()
        try:
            waler_inputs = waler_builder.build_all(self.project_data)
        except SolverInputBuildError as exc:
            self.show_result(f"無法建立全部圍令最佳化輸入：\n{exc}")
            return
        if not waler_inputs:
            self.show_result("錯誤：找不到圍令輸入資料")
            return

        missing_inventory = [
            waler_id
            for waler_id, waler_input in waler_inputs.items()
            if waler_input.material_spec and not waler_input.purchasable_lengths
        ]
        if missing_inventory:
            self.show_result(
                "錯誤：下列圍令所選規格沒有可用庫存料長："
                + "、".join(missing_inventory)
            )
            return

        modified_waler_ids = [
            waler_id
            for waler_id in waler_inputs
            if self._has_modified_waler_results(waler_id)
        ]
        if modified_waler_ids:
            confirmed = messagebox.askyesno(
                "全部圍令最佳化",
                (
                    "下列圍令有已人工修改的成果方案：\n"
                    + "、".join(modified_waler_ids)
                    + "\n\n套用全域結果時會取代這些方案，是否繼續計算？"
                ),
                parent=self.root,
            )
            if not confirmed:
                return

        dialog = WalerGlobalSolverDialog(
            self.root,
            tuple(waler_inputs.values()),
            self._apply_waler_global_result,
            optimize_waler_global=self.make_waler_global_optimizer(),
            waler_solver_guard=waler_solver_guard,
        )
        dialog.open()

    def _apply_waler_global_result(self, global_result):
        """Commit selected Waler data, then refresh the UI independently."""

        solution = getattr(global_result, "solution", None)
        diagnostics = getattr(global_result, "diagnostics", None)
        try:
            if solution is None or not bool(getattr(solution, "valid", False)):
                raise ValueError("全域圍令結果無效，未套用任何成果。")

            selected_candidates = tuple(
                getattr(solution, "selected_candidates", ()) or ()
            )
            selected_ids = [
                str(candidate.waler_id or "").strip()
                for candidate in selected_candidates
            ]
            if (
                not selected_candidates
                or any(not waler_id for waler_id in selected_ids)
                or len(selected_ids) != len(set(selected_ids))
            ):
                raise ValueError("全域圍令結果未對每支圍令提供唯一候選。")

            targets = dict(getattr(diagnostics, "target_ratio", {}) or {})
            raw_global_diagnostics = (
                diagnostics.to_dict()
                if diagnostics is not None and hasattr(diagnostics, "to_dict")
                else copy.deepcopy(diagnostics)
            )
            global_diagnostics = (
                dict(raw_global_diagnostics)
                if isinstance(raw_global_diagnostics, Mapping)
                else {}
            )
            changed_ids = tuple(
                getattr(solution, "changed_waler_ids", ()) or ()
            )
            global_diagnostics["solution_summary"] = {
                "total_short": solution.total_short,
                "total_mid": solution.total_mid,
                "total_long": solution.total_long,
                "total_out": solution.total_out,
                "short_ratio": solution.short_ratio,
                "mid_ratio": solution.mid_ratio,
                "long_ratio": solution.long_ratio,
                "ratio_deviation": solution.ratio_deviation,
                "total_out_distance_mm": solution.total_out_distance_mm,
                "changed_waler_count": solution.changed_waler_count,
                "changed_waler_ids": list(changed_ids),
            }

            staged_items = copy.deepcopy(self.result_items)
            selected_id_set = set(selected_ids)
            for result_id in list(staged_items):
                if ProjectResultModel.waler_result_identity(
                    result_id,
                    staged_items[result_id],
                ) in selected_id_set:
                    staged_items.pop(result_id)

            for candidate in selected_candidates:
                record = global_result.local_result_for(candidate.waler_id)
                if record is None:
                    raise ValueError(
                        f"全域結果缺少圍令 {candidate.waler_id} 的單支求解資料。"
                    )
                waler_input = record.waler_input
                plan = copy.deepcopy(dict(candidate.payload))
                plan["ratio_targets"] = dict(targets)
                plan["segment_counts"] = {
                    "short": candidate.short_count,
                    "mid": candidate.mid_count,
                    "long": candidate.long_count,
                }
                plan["global_candidate_rank"] = candidate.candidate_rank
                plan["global_local_regret"] = candidate.local_regret
                plan["global_material_counts"] = {
                    "short": candidate.short_count,
                    "mid": candidate.mid_count,
                    "long": candidate.long_count,
                    "out": candidate.out_count,
                }
                plan["global_out_distance_mm"] = candidate.out_distance_mm
                local_diagnostics = getattr(record.result, "diagnostics", None)
                result_id = (
                    f"{candidate.waler_id}-方案{candidate.candidate_rank}"
                )
                staged_items[result_id] = {
                    "type": "waler",
                    "result": {
                        "waler_id": candidate.waler_id,
                        "option_index": candidate.candidate_rank,
                        "selected_plan": plan,
                        "ratio_targets": dict(targets),
                        "required_length": int(round(waler_input.total_length)),
                        "forbidden_points": list(waler_input.forbidden_points),
                        "joint_clearance": 300,
                        "min_piece_length": 1000,
                        "max_piece_length": 10000,
                        "material_spec": waler_input.material_spec,
                        "search_diagnostics": (
                            local_diagnostics.to_dict()
                            if local_diagnostics is not None
                            and hasattr(local_diagnostics, "to_dict")
                            else copy.deepcopy(local_diagnostics)
                        ),
                        "global_search_diagnostics": copy.deepcopy(
                            global_diagnostics
                        ),
                        "global_selected": True,
                        "result_series": "global",
                    },
                    "visible": True,
                }
        except Exception as exc:
            LOGGER.exception("Global Waler apply staging failed")
            return WalerGlobalApplyOutcome(
                committed=False,
                refreshed=False,
                error=str(exc),
            )

        previous_items = copy.deepcopy(self.result_items)
        previous_project_result = copy.deepcopy(self.project_result)
        previous_calculated_time = self.last_calculated_time
        previous_dirty = bool(getattr(self, "project_dirty", False))
        previous_dirty_reason = str(
            getattr(self, "project_dirty_reason", "") or ""
        )
        try:
            self.result_items = staged_items
            self._mark_results_updated()
        except Exception as exc:
            self.result_items = previous_items
            self.project_result = previous_project_result
            self.last_calculated_time = previous_calculated_time
            self.project_dirty = previous_dirty
            self.project_dirty_reason = previous_dirty_reason
            LOGGER.exception("Global Waler apply commit failed")
            return WalerGlobalApplyOutcome(
                committed=False,
                refreshed=False,
                error=str(exc),
            )

        LOGGER.info("Global Waler apply commit success")
        try:
            first_id = selected_candidates[0].waler_id
            self._refresh_results_tree(
                selected_id=self._result_group_iid("waler", first_id),
            )
            self._select_results_tab()
            self.update_preview()
            changed_text = (
                "、".join(changed_ids)
                if changed_ids
                else "無（皆採用單支 #1）"
            )
            self.show_result(
                "已一次套用全部圍令最佳化結果。\n"
                f"短／中／長／非目標材料：{solution.total_short}／"
                f"{solution.total_mid}／{solution.total_long}／"
                f"{solution.total_out}\n"
                f"比例：{solution.short_ratio:.2%}／"
                f"{solution.mid_ratio:.2%}／{solution.long_ratio:.2%}\n"
                f"全域比例偏差：{solution.ratio_deviation:.6f}\n"
                f"非目標距離合計："
                f"{solution.total_out_distance_mm} mm\n"
                f"改用非 #1 的圍令：{changed_text}\n"
                "注意：第一版未進行全場共用庫存扣除。"
            )
        except Exception as exc:
            LOGGER.exception("Global Waler apply UI refresh failed")
            return WalerGlobalApplyOutcome(
                committed=True,
                refreshed=False,
                refresh_error=str(exc),
            )

        return WalerGlobalApplyOutcome(committed=True, refreshed=True)

    def _open_support_solver(self):
        if not self.validate_data():
            return

        zonings = sorted({
            str(row.get("Zoning", "") or "").strip()
            for row in self.struts
            if str(row.get("Zoning", "") or "").strip()
        })
        if not zonings:
            self.show_result("錯誤：支撐表中沒有可選取的分區")
            return

        dialog = ZoningSelectionDialog(self.root, zonings)
        selected_zoning = dialog.open()
        if selected_zoning is None:
            return

        support_builder, _ = self._ensure_solver_input_builders()
        try:
            support_input = support_builder.build_zone(
                self.project_data,
                selected_zoning,
            )
        except SolverInputBuildError as exc:
            self.show_result(f"無法建立支撐 Solver 輸入：\n{exc}")
            return
        if not support_input.configs:
            self.show_result(f"錯誤：分區 {selected_zoning} 沒有可供計算的支撐")
            return
        missing_inventory = [
            config.support_id
            for config in support_input.configs
            if config.material_spec and not config.steel_lengths
        ]
        if missing_inventory:
            self.show_result(
                "錯誤：下列支撐所選規格沒有可用庫存料長："
                + ", ".join(missing_inventory)
            )
            return

        solver_dialog = SupportSolverDialog(
            self.root,
            support_input,
            self._store_support_solution,
            optimize_support_zone=self.make_support_optimizer(
                self.support_candidate_cache
            ),
        )
        solver_dialog.open()

    def _store_support_solution(self, zoning, solution):
        self._store_result_item(zoning, "support", solution)
        diagnostics = solver_search.SolverDiagnostics.from_dict(
            getattr(solution, "search_diagnostics", None)
        )
        search_status = ""
        if diagnostics is not None:
            if diagnostics.result_is_stable:
                search_status = "，搜尋已穩定"
            elif diagnostics.search_limit_reached:
                search_status = "，搜尋已達上限"
        self.show_result(
            f"已完成分區 {zoning} 支撐配置："
            f"支撐數量={len(solution.plans)}，"
            f"總分={solution.total_score:.1f}，"
            f"合法={'是' if solution.valid else '否'}{search_status}"
        )

    def _store_waler_result(self, result):
        waler_id = str(result.get("waler_id", "")).strip()
        if not waler_id:
            self.show_result("錯誤：圍令結果缺少圍令編號")
            return

        top_results = result.get("top_results")
        if top_results is None:
            selected_plan = result.get("selected_plan")
            top_results = [selected_plan] if selected_plan else []
        top_results = list(top_results or [])[:5]
        if not top_results:
            self.show_result(f"錯誤：{waler_id} 沒有可儲存的圍令方案")
            return

        ratio_targets = result.get("ratio_targets")
        required_length = result.get("required_length")
        forbidden_points = list(result.get("forbidden_points") or [])
        joint_clearance = result.get("joint_clearance", 300)
        min_piece_length = result.get("min_piece_length", 1000)
        max_piece_length = result.get("max_piece_length", 10000)
        search_diagnostics = copy.deepcopy(result.get("search_diagnostics"))
        stored_diagnostics = solver_search.SolverDiagnostics.from_dict(
            search_diagnostics
        )
        material_spec = str(result.get("material_spec", "") or "").strip()
        if not material_spec:
            for row in self.walers:
                if str(row.get("WalerID", "") or "").strip() == waler_id:
                    material_spec = str(row.get("material_spec", "") or "").strip()
                    break
        existing_waler_results = [
            (result_id, item)
            for result_id, item in self.result_items.items()
            if ProjectResultModel.waler_result_identity(
                result_id,
                item,
            )
            == waler_id
        ]
        has_global_result = any(
            bool(item["result"].get("global_selected"))
            for _result_id, item in existing_waler_results
        )
        old_result_ids = [
            result_id
            for result_id, item in existing_waler_results
            if not bool(item["result"].get("global_selected"))
        ]
        for result_id in old_result_ids:
            self.result_items.pop(result_id, None)
        for index, plan in enumerate(top_results, start=1):
            result_id = (
                f"{waler_id}-單支方案{index}"
                if has_global_result
                else f"{waler_id}-方案{index}"
            )
            self.result_items[result_id] = {
                "type": "waler",
                "result": {
                    "waler_id": waler_id,
                    "option_index": index,
                    "selected_plan": plan,
                    "ratio_targets": ratio_targets or plan.get("ratio_targets"),
                    "required_length": required_length,
                    "forbidden_points": forbidden_points,
                    "joint_clearance": joint_clearance,
                    "min_piece_length": min_piece_length,
                    "max_piece_length": max_piece_length,
                    "material_spec": material_spec,
                    "search_diagnostics": search_diagnostics,
                    "result_series": (
                        "single" if has_global_result else ""
                    ),
                },
                "visible": False,
            }

        self._mark_results_updated()
        self._refresh_results_tree(
            selected_id=self._result_group_iid("waler", waler_id),
        )
        self.update_preview()
        self.show_result(
            f"已產生 {waler_id} 前 {len(top_results)} 名單支方案並加入結果。"
            + (
                "原全域方案已保留。"
                if has_global_result
                else ""
            )
            + (
                "搜尋已穩定。"
                if stored_diagnostics and stored_diagnostics.result_is_stable
                else ""
            )
            + "請在結果頁勾選方案查看圖面，雙擊方案可直接修改鋼材配置。"
        )

    def show_result(self, text):
        message = str(text or "").rstrip()
        if not message:
            return
        summary = next(
            (line.strip() for line in message.splitlines() if line.strip()),
            "已更新執行訊息",
        )
        if len(summary) > 90:
            summary = summary[:87] + "..."
        if hasattr(self, "execution_message_summary_var"):
            self.execution_message_summary_var.set(f"狀態：{summary}")
        self.result_text.configure(state="normal")
        existing = self.result_text.get("1.0", "end-1c")
        if existing.strip():
            self.result_text.insert("end", "\n\n" + "-" * 60 + "\n")
        self.result_text.insert("end", message)
        self.result_text.see("end")
        self.result_text.configure(state="disabled")

def main():
    root = tk.Tk()
    dependencies = build_dependencies(
        resource_dir=RESOURCE_DIR,
        app_dir=APP_DIR,
    )
    app = SupportInputApp(root, dependencies=dependencies)
    root.mainloop()


if __name__ == "__main__":
    main()
