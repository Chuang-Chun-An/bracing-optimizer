"""Tkinter dialog for the Waler optimization use case."""

from __future__ import annotations

import copy
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from bracing_optimizer.algorithms import solver_search, wales
from bracing_optimizer.application.optimize_waler import OptimizeWalerRequest
from bracing_optimizer.application.solver_input_builder import WalerProblemInput
from bracing_optimizer.domain.material_rules import MaterialRatioTargets

from .solver_dialog_base import (
    SolverDialogThreadBridge,
    TextRedirector,
    _text_is_at_bottom,
)
from ..result_formatters import format_waler_score_breakdown


class WalerSolverDialog(SolverDialogThreadBridge):
    def __init__(
        self,
        parent,
        waler_input: WalerProblemInput,
        solver_memory,
        callback,
        optimize_waler,
    ):
        self.callback = callback
        self.waler_input = waler_input
        self.waler_id = waler_input.waler_id
        self.start_point = waler_input.start_point
        self.end_point = waler_input.end_point
        self.length = int(round(waler_input.total_length))
        self.forbidden_points = waler_input.forbidden_points
        self.stock_items = waler_input.stock_items
        self.purchasable_lengths = waler_input.purchasable_lengths
        self.solver_memory = solver_memory
        self.optimize_waler = optimize_waler
        self.min_piece_length = 1000
        self.max_piece_length = 10000
        self.joint_clearance = 300
        self.candidate_joint_step = 500
        self.cfg = None
        self.material_ratio_targets = MaterialRatioTargets.normalized(20, 50, 30)
        self.current_results = None
        self.solver_key = None

        waler_id = self.waler_id
        start_point = self.start_point
        end_point = self.end_point
        forbidden_points = self.forbidden_points
        purchasable_lengths = self.purchasable_lengths
        rounded_length = self.length
        (
            preview_steel_length,
            preview_tail_adjustment,
            preview_tail_gap,
        ) = wales.resolve_tail_adjustment(rounded_length)
        candidate_joint_count = len(wales.generate_candidate_joint_points(
            preview_steel_length,
            self.min_piece_length,
            self.candidate_joint_step,
        ))

        def format_number(value):
            if value is None:
                return "無資料"
            number = float(value)
            if number.is_integer():
                return f"{int(number):,}"
            return f"{number:,.2f}"

        def format_point(point):
            if not point or len(point) != 2:
                return "無資料"
            return f"({format_number(point[0])}, {format_number(point[1])})"

        forbidden_text = ", ".join(format_number(point) for point in forbidden_points) or "無"
        purchasable_text = ", ".join(format_number(item) for item in purchasable_lengths) or "無"
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"圍令配置 - {waler_id}")
        self.dialog.geometry("900x780")
        self.dialog.grab_set()

        frame = ttk.Frame(self.dialog)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        info_frame = ttk.LabelFrame(frame, text="固定資訊與設定")
        info_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        info_frame.columnconfigure(1, weight=1)
        info_frame.columnconfigure(3, weight=1)

        info_items = [
            ("圍令編號", waler_id, "總長度", f"{format_number(rounded_length)} mm"),
            ("標準鋼材總長", f"{format_number(preview_steel_length)} mm", "調整塊／餘量", f"{format_number(preview_tail_adjustment)} / {format_number(preview_tail_gap)} mm"),
            ("起點座標", format_point(start_point), "終點座標", format_point(end_point)),
            ("禁止點數量", str(len(forbidden_points)), "候選接頭點數", str(candidate_joint_count)),
            ("接頭安全距離", f"{format_number(self.joint_clearance)} mm", "最小段長", f"{format_number(self.min_piece_length)} mm"),
            ("最大段長", f"{format_number(self.max_piece_length)} mm", "", ""),
        ]
        for row_index, (left_label, left_value, right_label, right_value) in enumerate(info_items):
            ttk.Label(info_frame, text=f"{left_label}：").grid(row=row_index, column=0, sticky="ne", padx=(8, 4), pady=2)
            ttk.Label(info_frame, text=left_value).grid(row=row_index, column=1, sticky="nw", padx=(0, 12), pady=2)
            if right_label:
                ttk.Label(info_frame, text=f"{right_label}：").grid(row=row_index, column=2, sticky="ne", padx=(8, 4), pady=2)
                ttk.Label(info_frame, text=right_value).grid(row=row_index, column=3, sticky="nw", padx=(0, 8), pady=2)

        detail_items = [
            ("禁止點列表", forbidden_text),
            ("可購買材料長度", purchasable_text),
        ]
        detail_start_row = len(info_items)
        for offset, (label, value) in enumerate(detail_items):
            row_index = detail_start_row + offset
            ttk.Label(info_frame, text=f"{label}：").grid(row=row_index, column=0, sticky="ne", padx=(8, 4), pady=2)
            ttk.Label(
                info_frame,
                text=value,
                justify="left",
                wraplength=720,
            ).grid(row=row_index, column=1, columnspan=3, sticky="nw", padx=(0, 8), pady=2)

        solver_settings_row = detail_start_row + len(detail_items)
        ratio_frame = ttk.LabelFrame(info_frame, text="短／中／長段比例設定")
        ratio_frame.grid(
            row=solver_settings_row,
            column=0,
            columnspan=4,
            sticky="ew",
            padx=8,
            pady=(6, 4),
        )

        ttk.Label(ratio_frame, text="短段").grid(row=0, column=0, sticky="e", padx=(8, 4), pady=4)
        self.short_ratio_var = tk.StringVar(value="20")
        ttk.Entry(ratio_frame, textvariable=self.short_ratio_var, width=8).grid(row=0, column=1, sticky="w", padx=(0, 12), pady=4)

        ttk.Label(ratio_frame, text="中段").grid(row=0, column=2, sticky="e", padx=(8, 4), pady=4)
        self.mid_ratio_var = tk.StringVar(value="50")
        ttk.Entry(ratio_frame, textvariable=self.mid_ratio_var, width=8).grid(row=0, column=3, sticky="w", padx=(0, 12), pady=4)

        ttk.Label(ratio_frame, text="長段").grid(row=0, column=4, sticky="e", padx=(8, 4), pady=4)
        self.long_ratio_var = tk.StringVar(value="30")
        ttk.Entry(ratio_frame, textvariable=self.long_ratio_var, width=8).grid(row=0, column=5, sticky="w", padx=(0, 8), pady=4)

        ttk.Label(
            info_frame,
            text=(
                "搜尋策略：系統自動調整。系統會依合法方案、候選完整度與搜尋穩定度，"
                "自動調整計算強度；不會自行放寬工程條件。"
            ),
            foreground="#4b5563",
            wraplength=800,
            justify="left",
        ).grid(
            row=solver_settings_row + 1,
            column=0,
            columnspan=4,
            sticky="ew",
            padx=8,
            pady=(2, 7),
        )

        log_frame = ttk.LabelFrame(frame, text="求解執行資訊")
        log_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        log_frame.rowconfigure(2, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.summary_var = tk.StringVar(value="尚未開始計算。")
        summary_frame = ttk.LabelFrame(log_frame, text="一般摘要")
        summary_frame.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
        summary_frame.columnconfigure(0, weight=1)
        ttk.Label(
            summary_frame,
            textvariable=self.summary_var,
            justify="left",
            wraplength=830,
            padding=(8, 6),
        ).grid(row=0, column=0, sticky="ew")
        ttk.Label(log_frame, text="詳細執行訊息").grid(
            row=1, column=0, sticky="w", padx=6, pady=(3, 0)
        )
        self.result_text = scrolledtext.ScrolledText(log_frame, height=14, wrap="none", state="disabled", font=("Consolas", 10))
        self.result_text.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        self.text_writer = TextRedirector(self.result_text)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, sticky="ew")

        self.run_button = ttk.Button(button_frame, text="開始計算", command=self._run_solver)
        self.run_button.pack(side="left", padx=6)

        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        self._initialize_ui_bridge()

    def _append_message(self, text):
        follow_new_output = _text_is_at_bottom(self.result_text)
        self.result_text.configure(state="normal")
        self.result_text.insert("end", text)
        if follow_new_output:
            self.result_text.see("end")
        self.result_text.configure(state="disabled")

    @staticmethod
    def _format_solver_number(value):
        number = float(value)
        return str(int(number)) if number.is_integer() else f"{number:g}"

    def _ask_use_memory_result(self, solver_key):
        (
            _solver_schema,
            _policy_id,
            _policy_version,
            waler_id,
            total_length,
            forbidden_points,
            short_ratio,
            mid_ratio,
            long_ratio,
            purchasable_lengths,
        ) = solver_key
        forbidden_text = ", ".join(str(point) for point in forbidden_points) or "無"
        ratio_text = " / ".join(
            self._format_solver_number(ratio)
            for ratio in (short_ratio, mid_ratio, long_ratio)
        )
        purchasable_text = ", ".join(str(length) for length in purchasable_lengths)

        choice = {"use_memory": False}
        prompt = tk.Toplevel(self.dialog)
        prompt.title("圍令配置本次記憶")
        prompt.transient(self.dialog)
        prompt.resizable(False, False)

        content = ttk.Frame(prompt, padding=16)
        content.pack(fill="both", expand=True)
        ttk.Label(
            content,
            text="本次執行期間已計算過相同條件，是否直接使用？",
            justify="left",
        ).pack(anchor="w", pady=(0, 12))
        ttk.Separator(content).pack(fill="x", pady=(0, 10))
        ttk.Label(
            content,
            text=(
                f"圍令：{waler_id}\n"
                f"總長：{total_length}\n"
                f"禁止點：{forbidden_text}\n"
                f"比例：{ratio_text}\n"
                f"材料長度：{purchasable_text}"
            ),
            justify="left",
        ).pack(anchor="w", pady=(0, 10))
        ttk.Separator(content).pack(fill="x", pady=(0, 12))

        button_frame = ttk.Frame(content)
        button_frame.pack(fill="x")

        def close_prompt(use_memory):
            choice["use_memory"] = use_memory
            prompt.destroy()

        ttk.Button(
            button_frame,
            text="直接使用",
            command=lambda: close_prompt(True),
        ).pack(side="left", padx=(0, 8))
        ttk.Button(
            button_frame,
            text="重新計算",
            command=lambda: close_prompt(False),
        ).pack(side="left")

        prompt.protocol("WM_DELETE_WINDOW", lambda: close_prompt(False))
        prompt.grab_set()
        self.dialog.wait_window(prompt)
        if self.dialog.winfo_exists():
            self.dialog.grab_set()
        return choice["use_memory"]

    def _save_solver_memory(self, results, diagnostics=None):
        if self.solver_key is None:
            return

        best_score = min(
            (item["score"] for item in results),
            default=None,
        )
        self.solver_memory[self.solver_key] = {
            "results": copy.deepcopy(results),
            "best_score": best_score,
            "config": copy.deepcopy(self.cfg),
            "search_diagnostics": (
                diagnostics.to_dict()
                if isinstance(diagnostics, solver_search.SolverDiagnostics)
                else copy.deepcopy(diagnostics)
            ),
        }

    def _restore_solver_memory(self, memory_entry):
        return (
            copy.deepcopy(memory_entry["results"]),
            solver_search.SolverDiagnostics.from_dict(
                copy.deepcopy(memory_entry.get("search_diagnostics"))
            ),
            copy.deepcopy(memory_entry.get("config")),
        )

    def _run_solver(self):
        try:
            short_ratio = float(self.short_ratio_var.get())
            mid_ratio = float(self.mid_ratio_var.get())
            long_ratio = float(self.long_ratio_var.get())
        except ValueError:
            messagebox.showerror("輸入錯誤", "段長比例必須為數字")
            return

        try:
            material_ratio_targets = MaterialRatioTargets.normalized(
                short_ratio,
                mid_ratio,
                long_ratio,
            )
        except ValueError as exc:
            messagebox.showerror("輸入錯誤", str(exc), parent=self.dialog)
            return
        self.material_ratio_targets = material_ratio_targets

        try:
            length = self.length
            if length <= 0:
                self._append_message("錯誤：這個圍令長度無效，請檢查圍令座標。\n")
                return

            purchasable_lengths = sorted({
                int(round(item))
                for item in self.purchasable_lengths
                if item is not None
            })
            if not purchasable_lengths:
                self._append_message("錯誤：庫存表中沒有可購買長度。\n")
                return

            request = OptimizeWalerRequest(
                input=self.waler_input,
                material_ratio_targets=material_ratio_targets,
            )
        except Exception as exc:
            self._append_message(f"錯誤：無法建立求解請求：{exc}\n")
            return

        solver_key = self.optimize_waler.build_cache_key(request)
        self.solver_key = solver_key
        memory_entry = self.solver_memory.get(solver_key)

        if memory_entry is not None and self._ask_use_memory_result(solver_key):
            self.result_text.configure(state="normal")
            self.result_text.delete("1.0", "end")
            self.result_text.configure(state="disabled")
            (
                restored_results,
                restored_diagnostics,
                self.cfg,
            ) = self._restore_solver_memory(memory_entry)
            self.current_results = None
            self._append_message("已直接載入本次執行期間的相同條件結果。\n")
            self._display_results(restored_results, diagnostics=restored_diagnostics)
            return

        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.configure(state="disabled")
        self.current_results = None
        self.summary_var.set(
            "正在建立配置候選並檢查工程合法性……系統會自動判斷是否需要加強搜尋。"
        )
        self._append_message("開始計算。系統將自動調整搜尋強度。\n")
        self.run_button.configure(state="disabled")

        thread = threading.Thread(
            target=self._solver_thread,
            args=(request,),
            daemon=True,
        )
        thread.start()


    def _solver_thread(self, request):
        def gui_logger(*args):
            message = " ".join(str(arg) for arg in args)
            if not message.endswith("\n"):
                message += "\n"
            self.text_writer.write(message)

        try:
            result = self.optimize_waler.execute(
                request,
                logger=gui_logger,
                on_progress=lambda progress: self._post_ui(
                    lambda message=progress.message: self.summary_var.set(message)
                ),
            )
            self.cfg = result.config
            results = list(result.solutions)
            diagnostics = result.diagnostics
            self._save_solver_memory(results, diagnostics)
            self._post_ui(
                lambda: self._display_results(results, diagnostics=diagnostics)
            )
        except Exception:
            import traceback

            msg = traceback.format_exc()
            self.text_writer.write(msg)
            self._post_ui(
                lambda: self.summary_var.set(
                    "計算發生錯誤；這不代表工程條件無解，請查看詳細執行訊息。"
                )
            )
        finally:
            self._post_ui(lambda: self.run_button.configure(state="normal"))

    def _waler_ratio_targets(self):
        return self.material_ratio_targets.as_dict()

    def _waler_segment_counts(self, item):
        segment_counts = {"short": 0, "mid": 0, "long": 0}
        if self.cfg is None:
            return None

        for segment in item.get("segments", []) or []:
            category = wales.classify_length(segment, self.cfg)
            if category in segment_counts:
                segment_counts[category] += 1
        return segment_counts

    def _with_waler_display_metadata(self, item):
        enriched = dict(item)
        enriched["ratio_targets"] = self._waler_ratio_targets()
        segment_counts = self._waler_segment_counts(item)
        if segment_counts is not None:
            enriched["segment_counts"] = segment_counts
        return enriched

    @staticmethod
    def _format_waler_engineer_summary(diagnostics):
        if diagnostics is None:
            return "搜尋狀態：舊版結果，無診斷資料。"
        lines = []
        if diagnostics.legal_solution_found:
            lines.append("計算完成｜✓ 已找到合法方案")
            if diagnostics.search_was_escalated:
                lines.append("ℹ 初始搜尋尚未穩定，系統已自動增加計算強度。")
            if diagnostics.result_is_stable:
                lines.append("✓ 加強後結果已穩定。")
            elif diagnostics.search_limit_reached:
                lines.append("⚠ 已使用最大搜尋強度，結果尚未完全穩定，可比較其他合法方案。")
        else:
            lines.append("目前搜尋未找到合法方案。")
            if diagnostics.infeasibility_proven:
                lines.append("工程條件下無可行解。")
            else:
                lines.append("系統已使用最大搜尋強度，但不能據此證明工程條件一定無解。")
        if diagnostics.main_issue_message:
            lines.append(f"主要限制：{diagnostics.main_issue_message}")
        return "\n".join(lines)

    def _display_results(self, results, previous_results=None, diagnostics=None):
        diagnostics = diagnostics or None
        self.summary_var.set(self._format_waler_engineer_summary(diagnostics))
        if not results:
            self._append_message("找不到可顯示的方案。\n")
            return

        display_results = [
            self._with_waler_display_metadata(item)
            for item in list(results or [])[:5]
        ]

        self._append_message("\n=== 前 5 名方案 ===\n")
        for idx, item in enumerate(display_results, start=1):
            self._append_message(self._format_plan_summary(idx, item))

        self.current_results = display_results
        self.callback({
            "waler_id": self.waler_id,
            "top_results": display_results,
            "ratio_targets": self._waler_ratio_targets(),
            "required_length": int(round(self.length)),
            "forbidden_points": [int(round(point)) for point in self.forbidden_points],
            "joint_clearance": self.joint_clearance,
            "min_piece_length": self.min_piece_length,
            "max_piece_length": self.max_piece_length,
            "adjustment_lengths": list(wales.WALER_ADJUSTMENT_LENGTHS),
            "max_gap": wales.WALER_MAX_GAP,
            "search_diagnostics": (
                diagnostics.to_dict()
                if isinstance(diagnostics, solver_search.SolverDiagnostics)
                else copy.deepcopy(diagnostics)
            ),
        })
        self._append_message(
            "\n前 5 名已加入結果。請在結果頁勾選方案查看圖面，"
            "雙擊方案可直接修改鋼材配置。\n"
        )

    def _format_plan_summary(self, index, item):
        return (
            format_waler_score_breakdown(
                item,
                option_index=index,
                ratio_targets=item.get("ratio_targets"),
                segment_counts=item.get("segment_counts"),
            )
            + "\n\n"
        )

    def _on_close(self):
        self._close_ui_bridge()
        self.dialog.destroy()

    def open(self):
        self.dialog.wait_window()
        return self.current_results
