"""Minimal Tkinter workflow for project-wide Waler optimization."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from bracing_optimizer.algorithms.cancellation import SolverCancelled
from bracing_optimizer.application.optimize_waler_global import (
    OptimizeWalerGlobalRequest,
)
from bracing_optimizer.domain.material_rules import (
    MaterialRatioTargets,
    classify_length,
)
from bracing_optimizer.application.waler_solver_guard import WalerSolverBusyGuard
from bracing_optimizer.application.solver_operation_registry import (
    CompletionDisposition,
    SolverExecution,
    SolverOperationRegistry,
    SolverOperationUnavailable,
    SolverSnapshotHandle,
)

from .solver_dialog_base import SolverDialogThreadBridge, TextRedirector


LOGGER = logging.getLogger(__name__)
WALER_SOLVER_BUSY_MESSAGE = "目前已有圍令計算正在執行，請等待完成後再試。"
WALER_SOLVER_CLOSE_BUSY_MESSAGE = (
    "圍令最佳化仍在計算中，請等待計算完成後再關閉。"
)
WALER_SOLVER_STOPPING_MESSAGE = "前一次計算正在停止，請稍後再試"
CAD_STALE_OPEN_MESSAGE = "CAD 已更新；請關閉後重新開啟 Solver"
CAD_STALE_RUNNING_MESSAGE = "CAD 更新，計算已停止；請關閉後重新開啟 Solver"
ADOPTION_BLOCKED_MESSAGE = "計算完成，但CAD ACK尚未完成，結果未採用"


def format_waler_global_result_summary(solution, diagnostics) -> str:
    """Format the result from persisted diagnostics, without Tk state."""

    out_lengths = [
        length
        for item in solution.selected_candidates
        for length in item.segments
        if classify_length(length) == "out"
    ]
    out_text = "、".join(f"{length} mm" for length in out_lengths) or "無"
    target_ratio = dict(getattr(diagnostics, "target_ratio", {}) or {})
    target_values = tuple(
        target_ratio.get(name)
        for name in ("short", "mid", "long")
    )
    target_text = (
        "／".join(f"{float(value):.2%}" for value in target_values)
        if all(value is not None for value in target_values)
        else "未提供"
    )
    return (
        "全場材料："
        f"短 {solution.total_short}／中 {solution.total_mid}／長 {solution.total_long}／"
        f"非目標材料區間 {solution.total_out} 支（{out_text}）\n"
        "比例："
        f"{solution.short_ratio:.2%}／{solution.mid_ratio:.2%}／"
        f"{solution.long_ratio:.2%}；目標 {target_text}；"
        f"偏差 {solution.ratio_deviation:.6f}\n"
        f"非目標距離合計：{solution.total_out_distance_mm} mm；"
        f"單支品質犧牲：{solution.total_local_regret:.6f}；"
        f"調整圍令：{solution.changed_waler_count} 支"
    )


class WalerGlobalSolverDialog(SolverDialogThreadBridge):
    """Generate, display, and immediately adopt a valid global result."""

    def __init__(
        self,
        parent,
        waler_inputs,
        callback,
        optimize_waler_global,
        waler_solver_guard: WalerSolverBusyGuard,
        operation_registry: SolverOperationRegistry,
        snapshot_handle: SolverSnapshotHandle,
        adoption_guard,
    ):
        self.waler_inputs = tuple(waler_inputs)
        self.callback = callback
        self.optimize_waler_global = optimize_waler_global
        self.waler_solver_guard = waler_solver_guard
        self.operation_registry = operation_registry
        self.snapshot_handle = snapshot_handle
        self.adoption_guard = adoption_guard
        self.current_result = None
        self._calculation_running = False
        self._snapshot_stale = False

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("全部圍令最佳化")
        self.dialog.geometry("980x760")
        self.dialog.minsize(800, 600)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        frame = ttk.Frame(self.dialog, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        frame.rowconfigure(3, weight=1)

        settings = ttk.LabelFrame(frame, text="全場材料比例目標")
        settings.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(settings, text=f"圍令數：{len(self.waler_inputs)}").grid(
            row=0, column=0, padx=(8, 18), pady=6
        )
        self.short_ratio_var = tk.StringVar(value="20")
        self.mid_ratio_var = tk.StringVar(value="50")
        self.long_ratio_var = tk.StringVar(value="30")
        for column, (label, variable) in enumerate((
            ("短料", self.short_ratio_var),
            ("中料", self.mid_ratio_var),
            ("長料", self.long_ratio_var),
        ), start=1):
            ttk.Label(settings, text=f"{label}：").grid(
                row=0, column=column * 2 - 1, sticky="e", pady=6
            )
            ttk.Entry(settings, textvariable=variable, width=8).grid(
                row=0, column=column * 2, sticky="w", padx=(0, 12), pady=6
            )
        ttk.Label(
            settings,
            text=(
                "第一版會先避免非目標材料，再比較全場比例、單支品質犧牲與調整圍令數；"
                "只在目前單支求解器保留的候選內做精確選擇，尚未共用扣除全場庫存。"
            ),
            foreground="#4b5563",
            wraplength=900,
            justify="left",
        ).grid(row=1, column=0, columnspan=7, sticky="ew", padx=8, pady=(0, 7))

        self.summary_var = tk.StringVar(value="尚未開始計算。")
        ttk.Label(
            frame,
            textvariable=self.summary_var,
            wraplength=920,
            justify="left",
            padding=(8, 6),
        ).grid(row=1, column=0, sticky="ew", pady=(0, 8))

        result_frame = ttk.LabelFrame(frame, text="全域選擇結果")
        result_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)
        columns = ("candidate", "segments", "counts", "regret")
        self.result_tree = ttk.Treeview(
            result_frame,
            columns=columns,
            show="tree headings",
            height=10,
        )
        self.result_tree.heading("#0", text="圍令")
        self.result_tree.heading("candidate", text="單支候選")
        self.result_tree.heading("segments", text="材料分段 (mm)")
        self.result_tree.heading("counts", text="短／中／長／非目標")
        self.result_tree.heading("regret", text="單支品質犧牲")
        self.result_tree.column("#0", width=90, stretch=False)
        self.result_tree.column("candidate", width=90, anchor="center", stretch=False)
        self.result_tree.column("segments", width=390)
        self.result_tree.column("counts", width=150, anchor="center", stretch=False)
        self.result_tree.column("regret", width=120, anchor="e", stretch=False)
        result_scroll = ttk.Scrollbar(
            result_frame,
            orient="vertical",
            command=self.result_tree.yview,
        )
        self.result_tree.configure(yscrollcommand=result_scroll.set)
        self.result_tree.grid(row=0, column=0, sticky="nsew")
        result_scroll.grid(row=0, column=1, sticky="ns")

        log_frame = ttk.LabelFrame(frame, text="執行訊息")
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=10,
            wrap="none",
            state="disabled",
            font=("Consolas", 9),
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.text_writer = TextRedirector(self.log_text)

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, sticky="ew")
        self.run_button = ttk.Button(
            buttons,
            text="開始全部圍令最佳化",
            command=self._run,
        )
        self.run_button.pack(side="left", padx=(0, 8))
        ttk.Button(
            buttons,
            text="關閉",
            command=self._on_close,
        ).pack(side="right")

        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        self._initialize_ui_bridge()
        self.operation_registry.set_stale_listener(
            self.snapshot_handle,
            self._on_snapshot_stale,
        )

    def _targets(self):
        try:
            values = (
                float(self.short_ratio_var.get()),
                float(self.mid_ratio_var.get()),
                float(self.long_ratio_var.get()),
            )
            return MaterialRatioTargets.normalized(*values)
        except ValueError as exc:
            messagebox.showerror("輸入錯誤", str(exc), parent=self.dialog)
            return None

    def _run(self):
        targets = self._targets()
        if targets is None:
            return
        execution = None
        if hasattr(self, "operation_registry"):
            try:
                execution = self.operation_registry.start_execution(
                    self.snapshot_handle
                )
            except SolverOperationUnavailable:
                self._on_snapshot_stale("cad_update")
                return
        lease = self.waler_solver_guard.try_acquire("global")
        if lease is None:
            if execution is not None:
                self.operation_registry.abort_execution(
                    self.snapshot_handle,
                    execution.identity,
                )
            LOGGER.warning("Global Waler blocked by busy guard")
            busy_message = (
                WALER_SOLVER_STOPPING_MESSAGE
                if hasattr(self, "operation_registry")
                and self.operation_registry.has_stale_running_waler()
                else WALER_SOLVER_BUSY_MESSAGE
            )
            messagebox.showwarning(
                "圍令計算中",
                busy_message,
                parent=self.dialog,
            )
            return
        self._calculation_running = True
        LOGGER.info("Global Waler Solver start")
        try:
            self.current_result = None
            self.run_button.configure(state="disabled")
            self.summary_var.set("正在依序建立各圍令候選……")
            for item_id in self.result_tree.get_children(""):
                self.result_tree.delete(item_id)
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.configure(state="disabled")

            request = OptimizeWalerGlobalRequest(
                waler_inputs=self.waler_inputs,
                material_ratio_targets=targets,
            )
            worker = threading.Thread(
                target=self._worker,
                args=(request, lease, execution),
                daemon=True,
            )
            worker.start()
        except Exception:
            lease.release()
            if execution is not None:
                self.operation_registry.abort_execution(
                    self.snapshot_handle,
                    execution.identity,
                )
            self._calculation_running = False
            self.run_button.configure(
                state=(
                    "disabled"
                    if getattr(self, "_snapshot_stale", False)
                    else "normal"
                )
            )
            LOGGER.exception("Global Waler Solver thread start failed")
            messagebox.showerror(
                "全部圍令最佳化失敗",
                "無法啟動圍令最佳化背景工作。",
                parent=self.dialog,
            )

    def _worker(
        self,
        request,
        lease,
        execution: SolverExecution | None = None,
    ):
        def logger(*args):
            self.text_writer.write(" ".join(str(item) for item in args) + "\n")

        result = None
        worker_error = None
        try:
            result = self.optimize_waler_global.execute(
                request,
                logger=logger,
                on_progress=lambda progress: self._post_ui(
                    lambda message=progress.message: self._show_progress_if_current(
                        execution,
                        message,
                    )
                ),
                cancellation_token=(
                    execution.cancellation_token
                    if execution is not None
                    else None
                ),
            )
        except SolverCancelled as exc:
            worker_error = exc
        except Exception as exc:
            worker_error = exc
            LOGGER.exception("Global Waler Solver failed")
        finally:
            lease.release()
            LOGGER.info("Global Waler Solver finish")
            self._post_ui(
                lambda result=result,
                error=worker_error,
                execution=execution: (
                    self._finish_worker(result, error, execution=execution)
                )
            )

    def _show_progress_if_current(self, execution, message):
        if execution is None or self.operation_registry.can_adopt(
            self.snapshot_handle,
            execution.identity,
        ):
            self.summary_var.set(message)

    def _finish_worker(
        self,
        result,
        error,
        *,
        execution: SolverExecution | None = None,
    ):
        if self._closed:
            return
        try:
            if not self.dialog.winfo_exists():
                self._closed = True
                return
        except tk.TclError:
            self._closed = True
            return
        disposition = CompletionDisposition.ADOPTABLE
        if execution is not None:
            disposition = self.operation_registry.complete_execution(
                self.snapshot_handle,
                execution.identity,
            )
        if disposition is CompletionDisposition.IGNORED:
            return
        try:
            if disposition is CompletionDisposition.STALE or getattr(
                self,
                "_snapshot_stale",
                False,
            ):
                self._snapshot_stale = True
                self.current_result = None
                self.summary_var.set(CAD_STALE_RUNNING_MESSAGE)
            elif isinstance(error, SolverCancelled):
                self.current_result = None
                self.summary_var.set("計算已取消。")
            elif error is not None:
                self._display_error(error)
            elif result is not None:
                if execution is not None:
                    try:
                        self.adoption_guard()
                    except RuntimeError:
                        self.current_result = None
                        self.summary_var.set(ADOPTION_BLOCKED_MESSAGE)
                        return
                if self._display_result(result):
                    self._adopt_current_result()
            else:
                self._display_error(RuntimeError("Solver 未回傳結果。"))
        except Exception as exc:
            LOGGER.exception("Global Waler result UI callback failed")
            self._display_error(exc)
        finally:
            self._calculation_running = False
            self.run_button.configure(
                state=(
                    "disabled"
                    if getattr(self, "_snapshot_stale", False)
                    else "normal"
                )
            )

    def _on_snapshot_stale(self, _reason):
        self._snapshot_stale = True
        self.run_button.configure(state="disabled")
        self.summary_var.set(
            CAD_STALE_RUNNING_MESSAGE
            if self._calculation_running
            else CAD_STALE_OPEN_MESSAGE
        )

    def _display_error(self, exc):
        self.current_result = None
        self.summary_var.set(f"全部圍令最佳化失敗：{exc}")

    def _display_result(self, result):
        self.current_result = result if result.solution.valid else None
        solution = result.solution
        if not solution.valid:
            self.summary_var.set(f"全部圍令最佳化失敗：{solution.reason}")
            return False

        self.summary_var.set(
            format_waler_global_result_summary(solution, result.diagnostics)
        )
        for item in solution.selected_candidates:
            self.result_tree.insert(
                "",
                "end",
                text=item.waler_id,
                values=(
                    f"#{item.candidate_rank}",
                    ", ".join(str(length) for length in item.segments),
                    (
                        f"{item.short_count}／{item.mid_count}／"
                        f"{item.long_count}／{item.out_count}"
                    ),
                    f"{item.local_regret:.6f}",
                ),
            )
        return True

    def _adopt_current_result(self):
        if self.current_result is None or not self.current_result.solution.valid:
            return
        result_summary = format_waler_global_result_summary(
            self.current_result.solution,
            self.current_result.diagnostics,
        )
        try:
            outcome = self.callback(self.current_result)
        except Exception as exc:
            LOGGER.exception("Global Waler apply callback failed")
            self.summary_var.set(
                "全域結果未採用：套用失敗，原成果未變更。\n"
                + result_summary
            )
            messagebox.showerror(
                "套用失敗",
                "全域圍令成果套用失敗，原成果未變更。\n"
                f"原因：{exc}",
                parent=self.dialog,
            )
            return
        if not bool(getattr(outcome, "committed", False)):
            detail = str(getattr(outcome, "error", "") or "").strip()
            self.summary_var.set(
                "全域結果未採用：套用失敗，原成果未變更。\n"
                + result_summary
            )
            messagebox.showerror(
                "套用失敗",
                "全域圍令成果套用失敗，原成果未變更。"
                + (f"\n原因：{detail}" if detail else ""),
                parent=self.dialog,
            )
            return
        if not bool(getattr(outcome, "refreshed", False)):
            self.summary_var.set(
                "全域結果已採用（畫面更新失敗）。\n" + result_summary
            )
            messagebox.showwarning(
                "畫面更新失敗",
                "圍令成果已成功套用，但畫面更新失敗。"
                "資料已套用到目前專案狀態，請重新整理畫面或重新開啟專案。",
                parent=self.dialog,
            )
            return
        self.summary_var.set(
            "全域結果已採用。\n" + result_summary
        )

    def _on_close(self):
        if self._calculation_running:
            LOGGER.warning("Global dialog close blocked while calculating")
            messagebox.showwarning(
                "圍令計算中",
                WALER_SOLVER_CLOSE_BUSY_MESSAGE,
                parent=self.dialog,
            )
            return
        if hasattr(self, "operation_registry"):
            self.operation_registry.set_stale_listener(
                self.snapshot_handle,
                None,
            )
            self.operation_registry.close_snapshot(self.snapshot_handle)
        self._close_ui_bridge()
        self.dialog.destroy()

    def open(self):
        self.dialog.wait_window()
        return self.current_result


__all__ = [
    "WalerGlobalSolverDialog",
    "format_waler_global_result_summary",
]
