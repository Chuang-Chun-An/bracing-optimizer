"""Standalone CAD Builder with testable data, JSON, watcher, and Tk GUI layers."""

from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path
from typing import Any, Sequence

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


APP_DIR = Path(__file__).resolve().parent
DEFAULT_TEMP_PATH = APP_DIR / "cad_builder_temp.json"
TEST_CASES_DIR = APP_DIR / "test_cases"
POLL_INTERVAL_MS = 500

TABLE_SPECS = {
    "walers": {
        "tab": "圍令",
        "id_field": "WalerID",
        "id_prefix": "W",
        "columns": ("WalerID", "StartX", "StartY", "EndX", "EndY", "Remark"),
        "labels": {
            "WalerID": "圍令編號",
            "StartX": "起點X",
            "StartY": "起點Y",
            "EndX": "終點X",
            "EndY": "終點Y",
            "Remark": "備註",
        },
        "defaults": {"StartX": "", "StartY": "", "EndX": "", "EndY": "", "Remark": ""},
        "copy_previous": ("Remark",),
    },
    "supports": {
        "tab": "支撐",
        "id_field": "StrutID",
        "id_prefix": "S",
        "columns": (
            "StrutID", "FromWaler", "ToWaler", "StartX", "StartY", "EndX", "EndY",
            "Beam1", "Beam2", "Column1", "Column2",
            "FromBraceToWalerStartLen", "FromBraceToWalerEndLen",
            "ToBraceToWalerStartLen", "ToBraceToWalerEndLen", "Zoning",
        ),
        "labels": {
            "StrutID": "支撐編號",
            "FromWaler": "起點圍令",
            "ToWaler": "終點圍令",
            "StartX": "起點X",
            "StartY": "起點Y",
            "EndX": "終點X",
            "EndY": "終點Y",
            "Beam1": "托梁1",
            "Beam2": "托梁2",
            "Column1": "中間柱1",
            "Column2": "中間柱2",
            "FromBraceToWalerStartLen": "起點角撐長度(往圍令起點)",
            "FromBraceToWalerEndLen": "起點角撐長度(往圍令終點)",
            "ToBraceToWalerStartLen": "終點角撐長度(往圍令起點)",
            "ToBraceToWalerEndLen": "終點角撐長度(往圍令終點)",
            "Zoning": "分區",
        },
        "defaults": {
            "FromWaler": "", "ToWaler": "", "StartX": "", "StartY": "",
            "EndX": "", "EndY": "", "Beam1": "", "Beam2": "",
            "Column1": 0, "Column2": 0,
            "FromBraceToWalerStartLen": 0, "FromBraceToWalerEndLen": 0,
            "ToBraceToWalerStartLen": 0, "ToBraceToWalerEndLen": 0, "Zoning": "",
        },
        "copy_previous": (
            "FromWaler", "ToWaler", "Beam1", "Beam2", "Column1", "Column2",
            "FromBraceToWalerStartLen", "FromBraceToWalerEndLen",
            "ToBraceToWalerStartLen", "ToBraceToWalerEndLen", "Zoning",
        ),
    },
    "braces": {
        "tab": "斜撐",
        "id_field": "BraceID",
        "id_prefix": "B",
        "columns": ("BraceID", "Type", "FromWaler", "ToWaler", "StartX", "StartY", "EndX", "EndY"),
        "labels": {
            "BraceID": "斜撐編號",
            "Type": "類型",
            "FromWaler": "起點圍令",
            "ToWaler": "終點圍令",
            "StartX": "起點X",
            "StartY": "起點Y",
            "EndX": "終點X",
            "EndY": "終點Y",
        },
        "defaults": {
            "Type": "KneeBrace", "FromWaler": "", "ToWaler": "",
            "StartX": "", "StartY": "", "EndX": "", "EndY": "",
        },
        "copy_previous": ("Type", "FromWaler", "ToWaler"),
    },
}

TABLE_ALIASES = {
    "waler": "walers", "walers": "walers",
    "support": "supports", "supports": "supports", "strut": "supports", "struts": "supports",
    "brace": "braces", "braces": "braces",
}
COORDINATE_FIELDS = ("StartX", "StartY", "EndX", "EndY")
SUPPORT_BATCH_FIELDS = TABLE_SPECS["supports"]["copy_previous"]


def _table_key(table_name: str) -> str:
    key = TABLE_ALIASES.get(str(table_name).strip().lower())
    if key is None:
        raise ValueError(f"未知資料表：{table_name}")
    return key


def _next_identifier(rows: Sequence[dict], id_field: str, prefix: str) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$", re.IGNORECASE)
    numbers = []
    for row in rows:
        match = pattern.fullmatch(str(row.get(id_field, "")).strip())
        if match:
            numbers.append(int(match.group(1)))
    return f"{prefix}{max(numbers, default=0) + 1}"


class BuilderModel:
    """Own all CAD Builder data and mutations without depending on Tkinter."""

    def __init__(self) -> None:
        self.walers: list[dict] = []
        self.supports: list[dict] = []
        self.braces: list[dict] = []

    def _rows(self, table_name: str) -> list[dict]:
        return getattr(self, _table_key(table_name))

    def get_rows(self, table_name: str) -> list[dict]:
        """Return a snapshot so callers cannot mutate model data accidentally."""
        return copy.deepcopy(self._rows(table_name))

    def _new_row(self, table_name: str, values: dict[str, Any]) -> dict:
        key = _table_key(table_name)
        rows = self._rows(key)
        spec = TABLE_SPECS[key]
        row = copy.deepcopy(spec["defaults"])
        row[spec["id_field"]] = _next_identifier(rows, spec["id_field"], spec["id_prefix"])
        for column in spec["columns"]:
            if column != spec["id_field"] and column in values:
                row[column] = values[column]
        row = {column: row.get(column, "") for column in spec["columns"]}
        rows.append(row)
        return copy.deepcopy(row)

    def add_waler(self, start_x: Any, start_y: Any, end_x: Any, end_y: Any) -> dict:
        return self._new_row("walers", {
            "StartX": start_x, "StartY": start_y, "EndX": end_x, "EndY": end_y,
        })

    def add_support(self, start_x: Any, start_y: Any, end_x: Any, end_y: Any) -> dict:
        return self._new_row("supports", {
            "StartX": start_x, "StartY": start_y, "EndX": end_x, "EndY": end_y,
        })

    def add_brace(self, start_x: Any, start_y: Any, end_x: Any, end_y: Any) -> dict:
        return self._new_row("braces", {
            "StartX": start_x, "StartY": start_y, "EndX": end_x, "EndY": end_y,
        })

    def add_empty_row(self, table_name: str) -> dict:
        return self._new_row(table_name, {})

    def add_temp_event(self, event: dict) -> tuple[str, dict]:
        event_type = str(event.get("type", "")).strip().lower()
        table_name = _table_key(event_type)
        values = event.get("data")
        if not isinstance(values, dict):
            raise ValueError("暫存事件的 data 必須是物件。")
        row = self._new_row(table_name, values)
        return table_name, row

    def update_cell(self, table_name: str, index: int, field: str, value: Any) -> None:
        key = _table_key(table_name)
        if field not in TABLE_SPECS[key]["columns"]:
            raise ValueError(f"{field} 不是 {key} 欄位。")
        self._rows(key)[index][field] = value

    def delete_row(self, table_name: str, index: int) -> dict:
        return self._rows(table_name).pop(index)

    def copy_row(self, table_name: str, index: int) -> dict:
        key = _table_key(table_name)
        rows = self._rows(key)
        spec = TABLE_SPECS[key]
        row = copy.deepcopy(rows[index])
        row[spec["id_field"]] = _next_identifier(rows, spec["id_field"], spec["id_prefix"])
        rows.insert(index + 1, row)
        return copy.deepcopy(row)

    def move_row_up(self, table_name: str, index: int) -> int:
        if index <= 0:
            return index
        rows = self._rows(table_name)
        rows[index - 1], rows[index] = rows[index], rows[index - 1]
        return index - 1

    def move_row_down(self, table_name: str, index: int) -> int:
        rows = self._rows(table_name)
        if index < 0 or index >= len(rows) - 1:
            return index
        rows[index + 1], rows[index] = rows[index], rows[index + 1]
        return index + 1

    def apply_previous_properties(self, table_name: str, index: int) -> None:
        key = _table_key(table_name)
        if index <= 0:
            raise IndexError("第一列沒有上一列。")
        rows = self._rows(key)
        for field in TABLE_SPECS[key]["copy_previous"]:
            rows[index][field] = copy.deepcopy(rows[index - 1].get(field, ""))

    def apply_previous_support_properties(self, index: int) -> None:
        self.apply_previous_properties("supports", index)

    def batch_apply_support_properties(self, indices: Sequence[int], values: dict[str, Any]) -> None:
        for field, value in values.items():
            if field not in SUPPORT_BATCH_FIELDS:
                raise ValueError(f"{field} 不可批次套用。")
            if value == "":
                continue
            for index in indices:
                self.supports[index][field] = copy.deepcopy(value)

    def clear_all(self) -> None:
        self.walers.clear()
        self.supports.clear()
        self.braces.clear()

    def get_counts(self) -> dict[str, int]:
        return {
            "walers": len(self.walers),
            "supports": len(self.supports),
            "braces": len(self.braces),
        }

    def to_draft_dict(self) -> dict:
        return {
            "version": 1,
            "source": "cad_builder",
            "walers": copy.deepcopy(self.walers),
            "supports": copy.deepcopy(self.supports),
            "braces": copy.deepcopy(self.braces),
        }

    def load_from_draft_dict(self, data: dict) -> None:
        if not isinstance(data, dict):
            raise ValueError("草稿 JSON 最上層必須是物件。")
        loaded: dict[str, list[dict]] = {}
        for table_name, spec in TABLE_SPECS.items():
            rows = data.get(table_name, [])
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError(f"{table_name} 必須是物件陣列。")
            normalized = []
            for source in rows:
                row = copy.deepcopy(spec["defaults"])
                for field in spec["columns"]:
                    if field in source:
                        row[field] = source[field]
                normalized.append({field: row.get(field, "") for field in spec["columns"]})
            loaded[table_name] = normalized
        self.walers = loaded["walers"]
        self.supports = loaded["supports"]
        self.braces = loaded["braces"]

    def to_solver_case_dict(self, case_name: str) -> dict:
        return {
            "version": 1,
            "case_name": str(case_name),
            "walers": copy.deepcopy(self.walers),
            "supports": copy.deepcopy(self.supports),
            "braces": copy.deepcopy(self.braces),
            "forbidden_points": [],
            "settings": {},
        }

    def validate_before_export(self) -> list[str]:
        errors: list[str] = []
        waler_ids: set[str] = set()
        for table_name, spec in TABLE_SPECS.items():
            ids: set[str] = set()
            for row_number, row in enumerate(self._rows(table_name), start=1):
                label = f"{spec['tab']}第 {row_number} 列"
                row_id = str(row.get(spec["id_field"], "")).strip()
                if not row_id:
                    errors.append(f"{label}：{spec['labels'][spec['id_field']]}不可空白")
                elif row_id in ids:
                    errors.append(f"{label}：編號 {row_id} 重複")
                else:
                    ids.add(row_id)

                coordinates = []
                for field in COORDINATE_FIELDS:
                    try:
                        number = float(row.get(field, ""))
                        if not math.isfinite(number):
                            raise ValueError
                        coordinates.append(number)
                    except (TypeError, ValueError):
                        errors.append(f"{label}：{spec['labels'][field]}必須是數字")
                if len(coordinates) == 4 and math.hypot(
                    coordinates[2] - coordinates[0], coordinates[3] - coordinates[1]
                ) <= 0:
                    errors.append(f"{label}：線段長度不可為 0")
            if table_name == "walers":
                waler_ids = ids

        for table_name in ("supports", "braces"):
            spec = TABLE_SPECS[table_name]
            for row_number, row in enumerate(self._rows(table_name), start=1):
                for field in ("FromWaler", "ToWaler"):
                    value = str(row.get(field, "")).strip()
                    if value and value not in waler_ids:
                        errors.append(
                            f"{spec['tab']}第 {row_number} 列：{spec['labels'][field]} {value} 不存在於圍令表"
                        )
        return errors


class JSONManager:
    """Read and write CAD Builder JSON without any GUI dependency."""

    @staticmethod
    def load_temp_event(path: str | Path) -> dict:
        event = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if not isinstance(event, dict):
            raise ValueError("暫存 JSON 最上層必須是物件。")
        if event.get("event_id") is None:
            raise ValueError("暫存 JSON 缺少 event_id。")
        _table_key(str(event.get("type", "")).strip().lower())
        if not isinstance(event.get("data"), dict):
            raise ValueError("暫存 JSON 的 data 必須是物件。")
        return event

    @staticmethod
    def save_draft(path: str | Path, model: BuilderModel) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(model.to_draft_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return target

    @staticmethod
    def load_draft(path: str | Path, model: BuilderModel) -> dict:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        model.load_from_draft_dict(data)
        return data

    @staticmethod
    def export_solver_json(path: str | Path, model: BuilderModel, case_name: str) -> Path:
        errors = model.validate_before_export()
        if errors:
            raise ValueError("輸出前驗證失敗：\n" + "\n".join(errors))
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(model.to_solver_case_dict(case_name), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target


class TempEventWatcher:
    """Detect new AutoLISP events without scheduling or GUI dependencies."""

    def __init__(self, temp_path: str | Path = DEFAULT_TEMP_PATH) -> None:
        self.temp_path = Path(temp_path)
        self.last_event_id: Any = None

    def check_new_event(self) -> dict | None:
        if not self.temp_path.is_file():
            return None
        event = JSONManager.load_temp_event(self.temp_path)
        event_id = event["event_id"]
        if event_id == self.last_event_id:
            return None
        self.last_event_id = event_id
        return event


class EditableTable:
    """Treeview adapter; every mutation is delegated to BuilderModel."""

    def __init__(self, app: "CADBuilderGUI", parent: Any, table_name: str) -> None:
        self.app = app
        self.table_name = table_name
        self.spec = TABLE_SPECS[table_name]
        self.editor: Any = None
        self.edit_context: tuple[int, str] | None = None

        actions = ttk.Frame(parent)
        actions.pack(fill="x", padx=6, pady=(6, 2))
        for text, command in (
            ("新增列", self.add_row), ("刪除列", self.delete_rows), ("複製列", self.copy_row),
            ("上移", lambda: self.move_row(-1)), ("下移", lambda: self.move_row(1)),
            ("套用上一列", self.apply_previous),
        ):
            ttk.Button(actions, text=text, command=command).pack(side="left", padx=(0, 5))
        if table_name == "supports":
            ttk.Button(actions, text="批次套用", command=self.open_batch_dialog).pack(
                side="left", padx=(8, 5)
            )

        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        columns = self.spec["columns"]
        self.tree = ttk.Treeview(container, columns=columns, show="headings", selectmode="extended")
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(container, orient="horizontal", command=self.tree.xview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        for column in columns:
            self.tree.heading(column, text=self.spec["labels"][column])
            width = 210 if "BraceToWaler" in column else 105
            self.tree.column(column, width=width, minwidth=70, anchor="center", stretch=False)
        self.tree.bind("<Double-1>", self.begin_edit)

    def selected_indices(self) -> list[int]:
        return sorted(int(item) for item in self.tree.selection())

    def refresh(self, selected: Sequence[int] | None = None) -> None:
        self.cancel_edit()
        rows = self.app.model.get_rows(self.table_name)
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(rows):
            self.tree.insert(
                "", "end", iid=str(index), values=[row.get(column, "") for column in self.spec["columns"]]
            )
        if selected:
            valid = [str(index) for index in selected if 0 <= index < len(rows)]
            if valid:
                self.tree.selection_set(valid)
                self.tree.focus(valid[0])
                self.tree.see(valid[0])
        self.app.update_status()

    def add_row(self) -> None:
        row = self.app.model.add_empty_row(self.table_name)
        self.app.last_added = str(row[self.spec["id_field"]])
        index = self.app.model.get_counts()[self.table_name] - 1
        self.refresh([index])

    def delete_rows(self) -> None:
        selected = self.selected_indices()
        if not selected:
            messagebox.showwarning("刪除列", "請先選取要刪除的列。", parent=self.app.root)
            return
        for index in reversed(selected):
            self.app.model.delete_row(self.table_name, index)
        count = self.app.model.get_counts()[self.table_name]
        next_index = min(selected[0], count - 1)
        self.refresh([next_index] if next_index >= 0 else None)

    def copy_row(self) -> None:
        selected = self.selected_indices()
        if not selected:
            messagebox.showwarning("複製列", "請先選取要複製的列。", parent=self.app.root)
            return
        index = selected[0]
        row = self.app.model.copy_row(self.table_name, index)
        self.app.last_added = str(row[self.spec["id_field"]])
        self.refresh([index + 1])

    def move_row(self, direction: int) -> None:
        selected = self.selected_indices()
        if len(selected) != 1:
            messagebox.showwarning("移動列", "請選取一列。", parent=self.app.root)
            return
        index = selected[0]
        if direction < 0:
            target = self.app.model.move_row_up(self.table_name, index)
        else:
            target = self.app.model.move_row_down(self.table_name, index)
        self.refresh([target])

    def apply_previous(self) -> None:
        selected = self.selected_indices()
        if len(selected) != 1:
            messagebox.showwarning("套用上一列", "請選取一列。", parent=self.app.root)
            return
        try:
            self.app.model.apply_previous_properties(self.table_name, selected[0])
        except IndexError as exc:
            messagebox.showwarning("套用上一列", str(exc), parent=self.app.root)
            return
        self.refresh(selected)

    def begin_edit(self, event: Any) -> None:
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        item = self.tree.identify_row(event.y)
        column_id = self.tree.identify_column(event.x)
        if not item or not column_id:
            return
        column_index = int(column_id[1:]) - 1
        if not 0 <= column_index < len(self.spec["columns"]):
            return
        bbox = self.tree.bbox(item, column_id)
        if not bbox:
            return
        self.cancel_edit()
        index = int(item)
        column = self.spec["columns"][column_index]
        rows = self.app.model.get_rows(self.table_name)
        self.edit_context = (index, column)
        self.editor = ttk.Entry(self.tree)
        self.editor.insert(0, str(rows[index].get(column, "")))
        self.editor.select_range(0, "end")
        self.editor.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        self.editor.focus_set()
        self.editor.bind("<Return>", self.commit_edit)
        self.editor.bind("<Escape>", self.cancel_edit)
        self.editor.bind("<FocusOut>", self.commit_edit)

    def commit_edit(self, _event: Any = None) -> str:
        if self.editor is None or self.edit_context is None:
            return "break"
        value = self.editor.get()
        index, column = self.edit_context
        self.app.model.update_cell(self.table_name, index, column, value)
        self._destroy_editor()
        self.refresh([index])
        return "break"

    def cancel_edit(self, _event: Any = None) -> str:
        self._destroy_editor()
        return "break"

    def _destroy_editor(self) -> None:
        editor = self.editor
        self.editor = None
        self.edit_context = None
        if editor is not None:
            editor.destroy()

    def open_batch_dialog(self) -> None:
        selected = self.selected_indices()
        if not selected:
            messagebox.showwarning("批次套用", "請先選取一列或多列支撐。", parent=self.app.root)
            return
        dialog = tk.Toplevel(self.app.root)
        dialog.title(f"批次套用到 {len(selected)} 列支撐")
        dialog.transient(self.app.root)
        dialog.grab_set()
        entries = {}
        for row_number, field in enumerate(SUPPORT_BATCH_FIELDS):
            ttk.Label(dialog, text=self.spec["labels"][field]).grid(
                row=row_number, column=0, sticky="e", padx=8, pady=3
            )
            entry = ttk.Entry(dialog, width=34)
            entry.grid(row=row_number, column=1, sticky="ew", padx=8, pady=3)
            entries[field] = entry
        ttk.Label(dialog, text="空白欄位不修改").grid(
            row=len(entries), column=0, columnspan=2, sticky="w", padx=8, pady=(8, 3)
        )
        buttons = ttk.Frame(dialog)
        buttons.grid(row=len(entries) + 1, column=0, columnspan=2, pady=8)

        def apply_values() -> None:
            values = {field: entry.get() for field, entry in entries.items()}
            self.app.model.batch_apply_support_properties(selected, values)
            dialog.destroy()
            self.refresh(selected)

        ttk.Button(buttons, text="確認", command=apply_values).pack(side="left", padx=4)
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="left", padx=4)
        dialog.columnconfigure(1, weight=1)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        next(iter(entries.values())).focus_set()


class CADBuilderGUI:
    """Tkinter presentation layer backed exclusively by BuilderModel."""

    def __init__(
        self,
        root: Any,
        model: BuilderModel | None = None,
        watcher: TempEventWatcher | None = None,
    ) -> None:
        self.root = root
        self.model = model or BuilderModel()
        self.json_manager = JSONManager()
        self.watcher = watcher or TempEventWatcher(DEFAULT_TEMP_PATH)
        self.last_added = "無"
        self.tables: dict[str, EditableTable] = {}
        self.status_var = tk.StringVar()
        self.root.title("CAD Builder")
        self.root.geometry("1450x780")
        self.root.minsize(900, 520)
        self._build_ui()
        self.refresh_all()
        self.root.after(POLL_INTERVAL_MS, self.poll_temp_event)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill="x", padx=8, pady=8)
        for text, command in (
            ("重新讀取", lambda: self.read_temp_event(report_errors=True)),
            ("匯入草稿", self.import_draft),
            ("儲存草稿", self.save_draft),
            ("輸出 Solver JSON", self.export_solver_json),
            ("清空資料", self.clear_data),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=(0, 6))

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        for table_name, spec in TABLE_SPECS.items():
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=spec["tab"])
            self.tables[table_name] = EditableTable(self, frame, table_name)

        ttk.Label(self.root, textvariable=self.status_var, anchor="w", relief="sunken").pack(
            fill="x", side="bottom"
        )

    def update_status(self) -> None:
        counts = self.model.get_counts()
        self.status_var.set(
            f"圍令 {counts['walers']} | 支撐 {counts['supports']} | "
            f"斜撐 {counts['braces']} | 最近新增：{self.last_added}"
        )

    def refresh_all(self) -> None:
        for table in self.tables.values():
            table.refresh()

    def poll_temp_event(self) -> None:
        try:
            self.read_temp_event()
        finally:
            self.root.after(POLL_INTERVAL_MS, self.poll_temp_event)

    def read_temp_event(self, report_errors: bool = False) -> bool:
        try:
            event = self.watcher.check_new_event()
            if event is None:
                return False
            table_name, row = self.model.add_temp_event(event)
            self.last_added = str(row[TABLE_SPECS[table_name]["id_field"]])
            index = self.model.get_counts()[table_name] - 1
            self.tables[table_name].refresh([index])
            return True
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            if report_errors:
                messagebox.showerror("讀取暫存檔失敗", str(exc), parent=self.root)
            return False

    def import_draft(self) -> None:
        path = filedialog.askopenfilename(
            title="匯入草稿 JSON", initialdir=APP_DIR,
            filetypes=(("JSON", "*.json"), ("所有檔案", "*.*")),
        )
        if not path:
            return
        try:
            self.json_manager.load_draft(path, self.model)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            messagebox.showerror("匯入草稿失敗", str(exc), parent=self.root)
            return
        self.last_added = "無"
        self.refresh_all()
        messagebox.showinfo("匯入草稿", f"已載入：\n{path}", parent=self.root)

    def save_draft(self) -> None:
        path = filedialog.asksaveasfilename(
            title="儲存草稿 JSON", initialdir=APP_DIR, initialfile="cad_builder_draft.json",
            defaultextension=".json", filetypes=(("JSON", "*.json"),),
        )
        if not path:
            return
        try:
            self.json_manager.save_draft(path, self.model)
        except OSError as exc:
            messagebox.showerror("儲存草稿失敗", str(exc), parent=self.root)
            return
        messagebox.showinfo("儲存草稿", f"已儲存：\n{path}", parent=self.root)

    def export_solver_json(self) -> None:
        errors = self.model.validate_before_export()
        if errors:
            messagebox.showerror(
                "無法輸出 Solver JSON",
                "請先修正以下錯誤：\n\n" + "\n".join(f"• {error}" for error in errors),
                parent=self.root,
            )
            return
        case_name = simpledialog.askstring("輸出 Solver JSON", "案例名稱：", parent=self.root)
        if case_name is None:
            return
        case_name = case_name.strip()
        if not case_name:
            messagebox.showwarning("輸出 Solver JSON", "案例名稱不可空白。", parent=self.root)
            return
        TEST_CASES_DIR.mkdir(exist_ok=True)
        path = TEST_CASES_DIR / f"{sanitize_case_name(case_name)}.json"
        if path.exists() and not messagebox.askyesno(
            "覆蓋案例", f"{path.name} 已存在，是否覆蓋？", parent=self.root
        ):
            return
        try:
            self.json_manager.export_solver_json(path, self.model, case_name)
        except (OSError, ValueError) as exc:
            messagebox.showerror("輸出失敗", str(exc), parent=self.root)
            return
        messagebox.showinfo("輸出 Solver JSON", f"已輸出：\n{path}", parent=self.root)

    def clear_data(self) -> None:
        if any(self.model.get_counts().values()) and not messagebox.askyesno(
            "清空資料", "確定要清空所有圍令、支撐與斜撐資料？", parent=self.root
        ):
            return
        self.model.clear_all()
        self.last_added = "無"
        self.refresh_all()


def sanitize_case_name(case_name: str) -> str:
    translation = str.maketrans({
        "<": "＜", ">": "＞", ":": "：", '"': "＂", "/": "／", "\\": "＼",
        "|": "｜", "?": "？", "*": "＊",
    })
    name = case_name.translate(translation).strip().rstrip(".")
    name = re.sub(r"[\x00-\x1f]", "", name)
    return name or "未命名案例"


def main() -> None:
    root = tk.Tk()
    app = CADBuilderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
