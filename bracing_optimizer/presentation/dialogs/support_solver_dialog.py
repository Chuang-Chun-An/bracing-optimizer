"""Tkinter dialog for the support-zone optimization use case."""

from __future__ import annotations

from collections import Counter
import re
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from bracing_optimizer.algorithms import solver_search, support
from bracing_optimizer.application.optimize_support_zone import OptimizeSupportZoneRequest
from bracing_optimizer.application.solver_input_builder import SupportZoneInput
from bracing_optimizer.domain.material_rules import MaterialRatioTargets

from .solver_dialog_base import (
    SolverDialogThreadBridge,
    TextRedirector,
    _text_is_at_bottom,
)
from ..result_formatters import format_result_value
from window_layout import configure_responsive_dialog


_SUPPORT_ID_PATTERN = re.compile(r"^(.*?)(\d+)$")


def _compact_support_ids(support_ids) -> str:
    """Format consecutive IDs such as S3..S10 as S3～S10."""

    labels = [str(value or "").strip() for value in support_ids]
    matches = [_SUPPORT_ID_PATTERN.fullmatch(label) for label in labels]
    if not labels or not all(matches):
        return "、".join(label for label in labels if label)

    prefixes = {match.group(1) for match in matches}
    if len(prefixes) != 1:
        return "、".join(labels)

    prefix = matches[0].group(1)
    numbers = sorted({int(match.group(2)) for match in matches})
    runs = []
    run_start = run_end = numbers[0]
    for number in numbers[1:]:
        if number == run_end + 1:
            run_end = number
            continue
        runs.append((run_start, run_end))
        run_start = run_end = number
    runs.append((run_start, run_end))
    return "、".join(
        f"{prefix}{start}～{prefix}{end}" if start != end else f"{prefix}{start}"
        for start, end in runs
    )


def duplicate_support_limit_summary(configs) -> str:
    """Describe which support IDs share the same solver restrictions."""

    grouped_ids = {}
    for config in configs:
        key = support.get_support_config_key(config)
        grouped_ids.setdefault(key, []).append(config.support_id)
    return "；".join(
        f"{_compact_support_ids(support_ids)} 為同支撐限制"
        for support_ids in grouped_ids.values()
        if len(support_ids) > 1
    )


class SupportSolverDialog(SolverDialogThreadBridge):
    def __init__(
        self,
        parent,
        support_input: SupportZoneInput,
        callback,
        optimize_support_zone,
    ):
        self.support_input = support_input
        self.zoning = support_input.zoning
        self.configs = support_input.configs
        self.callback = callback
        self.optimize_support_zone = optimize_support_zone
        self.solution = None

        zoning = support_input.zoning
        configs = support_input.configs
        duplicate_limit_text = duplicate_support_limit_summary(configs)
        support_ids = ", ".join(config.support_id for config in configs)
        region_counts = Counter(
            config.target_jack_region
            for config in configs
        )
        region_statistics = ", ".join(
            f"區域 {region}: {count}"
            for region, count in sorted(region_counts.items())
        ) or "無"

        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"支撐配置 - 分區 {zoning}")
        self.dialog.transient(parent)
        configure_responsive_dialog(
            self.dialog,
            parent,
            preferred_width=900,
            preferred_height=720,
            minimum_width=720,
            minimum_height=480,
        )
        self.dialog.grab_set()

        frame = ttk.Frame(self.dialog)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        info_frame = ttk.LabelFrame(frame, text="固定資訊")
        info_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        info_frame.columnconfigure(1, weight=1)
        info_frame.columnconfigure(3, weight=1)

        info_items = [
            ("分區", zoning, "支撐數量", str(len(configs))),
        ]
        if duplicate_limit_text:
            info_items.append(
                (
                    "重複設定提醒",
                    duplicate_limit_text,
                    "目標千斤頂區域統計",
                    region_statistics,
                )
            )
        else:
            info_items.append(
                ("目標千斤頂區域統計", region_statistics, "", "")
            )
        for row_index, (left_label, left_value, right_label, right_value) in enumerate(info_items):
            ttk.Label(info_frame, text=f"{left_label}：").grid(
                row=row_index,
                column=0,
                sticky="ne",
                padx=(8, 4),
                pady=3,
            )
            ttk.Label(
                info_frame,
                text=left_value,
                justify="left",
                wraplength=360,
            ).grid(
                row=row_index,
                column=1,
                sticky="nw",
                padx=(0, 12),
                pady=3,
            )
            if right_label:
                ttk.Label(info_frame, text=f"{right_label}：").grid(
                    row=row_index,
                    column=2,
                    sticky="ne",
                    padx=(8, 4),
                    pady=3,
                )
                ttk.Label(info_frame, text=right_value).grid(
                    row=row_index,
                    column=3,
                    sticky="nw",
                    padx=(0, 8),
                    pady=3,
                )

        ttk.Label(info_frame, text="支撐編號清單：").grid(
            row=len(info_items),
            column=0,
            sticky="ne",
            padx=(8, 4),
            pady=3,
        )
        ttk.Label(
            info_frame,
            text=support_ids,
            justify="left",
            wraplength=700,
        ).grid(
            row=len(info_items),
            column=1,
            columnspan=3,
            sticky="nw",
            padx=(0, 8),
            pady=3,
        )

        settings_frame = ttk.LabelFrame(frame, text="材料比例設定")
        settings_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        ttk.Label(settings_frame, text="短料目標比例（%）").grid(
            row=0, column=0, sticky="e", padx=(8, 4), pady=5
        )
        self.short_ratio_var = tk.StringVar(
            value=str(support.SUPPORT_DEFAULT_SHORT_MATERIAL_RATIO)
        )
        ttk.Entry(
            settings_frame,
            textvariable=self.short_ratio_var,
            width=8,
        ).grid(row=0, column=1, sticky="w", padx=(0, 18), pady=5)

        ttk.Label(settings_frame, text="中料目標比例（%）").grid(
            row=0, column=2, sticky="e", padx=(8, 4), pady=5
        )
        self.mid_ratio_var = tk.StringVar(
            value=str(support.SUPPORT_DEFAULT_MID_MATERIAL_RATIO)
        )
        ttk.Entry(
            settings_frame,
            textvariable=self.mid_ratio_var,
            width=8,
        ).grid(row=0, column=3, sticky="w", padx=(0, 18), pady=5)

        ttk.Label(settings_frame, text="長料目標比例（%）").grid(
            row=0, column=4, sticky="e", padx=(8, 4), pady=5
        )
        self.long_ratio_var = tk.StringVar(
            value=str(support.SUPPORT_DEFAULT_LONG_MATERIAL_RATIO)
        )
        ttk.Entry(
            settings_frame,
            textvariable=self.long_ratio_var,
            width=8,
        ).grid(row=0, column=5, sticky="w", padx=(0, 8), pady=5)

        ttk.Label(
            settings_frame,
            text=(
                "搜尋策略：系統自動調整。系統會依合法方案、候選完整度與搜尋穩定度，"
                "自動調整計算強度；不會自行放寬工程條件。"
            ),
            foreground="#4b5563",
            wraplength=790,
            justify="left",
        ).grid(
            row=1,
            column=0,
            columnspan=6,
            sticky="ew",
            padx=8,
            pady=(3, 6),
        )

        log_frame = ttk.LabelFrame(frame, text="支撐求解執行訊息")
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
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

        self.result_text = scrolledtext.ScrolledText(
            log_frame,
            # Keep the requested height compact so Tk can preserve the action
            # row on short displays; grid weight still expands this on larger
            # screens and the text widget retains its own scrollbars.
            height=6,
            wrap="none",
            state="disabled",
            font=("Consolas", 10),
        )
        self.result_text.grid(row=2, column=0, sticky="nsew", padx=4, pady=4)
        self.text_writer = TextRedirector(self.result_text)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=3, column=0, sticky="ew")
        self.run_button = ttk.Button(
            button_frame,
            text="開始計算",
            command=self._run_solver,
        )
        self.run_button.pack(side="left", padx=6)
        ttk.Button(
            button_frame,
            text="關閉",
            command=self._on_close,
        ).pack(side="right", padx=6)

        self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)
        self._initialize_ui_bridge()

    def _append_message(self, text):
        follow_new_output = _text_is_at_bottom(self.result_text)
        self.result_text.configure(state="normal")
        self.result_text.insert("end", text)
        if follow_new_output:
            self.result_text.see("end")
        self.result_text.configure(state="disabled")

    def _run_solver(self):
        try:
            short_ratio = float(self.short_ratio_var.get().strip())
            mid_ratio = float(self.mid_ratio_var.get().strip())
            long_ratio = float(self.long_ratio_var.get().strip())
        except ValueError:
            messagebox.showerror(
                "輸入錯誤",
                "材料比例必須為有效數字",
                parent=self.dialog,
            )
            return

        try:
            material_ratio_targets = MaterialRatioTargets.normalized(
                short_ratio,
                mid_ratio,
                long_ratio,
            )
        except ValueError as exc:
            messagebox.showerror(
                "輸入錯誤",
                str(exc),
                parent=self.dialog,
            )
            return

        self.result_text.configure(state="normal")
        self.result_text.delete("1.0", "end")
        self.result_text.configure(state="disabled")
        self.solution = None
        self.summary_var.set(
            "正在建立材料組合與配置候選……系統會自動判斷是否需要加強搜尋。"
        )
        request = OptimizeSupportZoneRequest(
            input=self.support_input,
            material_ratio_targets=material_ratio_targets,
            material_ratio_weight=support.SUPPORT_MATERIAL_RATIO_WEIGHT,
        )
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

        def on_progress(progress):
            self._post_ui(
                lambda message=progress.message: self.summary_var.set(message)
            )

        try:
            result = self.optimize_support_zone.execute(
                request,
                on_progress=on_progress,
                logger=gui_logger,
            )
            solution = result.solution
            diagnostics = result.diagnostics
            if solution is not None:
                self._post_ui(
                    lambda: self._display_solution(solution, diagnostics),
                )
            else:
                self._post_ui(
                    lambda: self._display_diagnostics_only(diagnostics),
                )
        except Exception:
            import traceback

            message = traceback.format_exc()
            self.text_writer.write(message)
            self._post_ui(
                lambda: self.summary_var.set(
                    "計算發生錯誤；這不代表工程條件無解，請查看詳細執行訊息。"
                )
            )
        finally:
            self._post_ui(
                lambda: self.run_button.configure(state="normal"),
            )

    def _display_diagnostics_only(self, diagnostics):
        self.summary_var.set(self._format_support_engineer_summary(None, diagnostics))

    @staticmethod
    def _format_support_engineer_summary(solution, diagnostics):
        lines = []
        if diagnostics.legal_solution_found:
            lines.append("計算完成｜✓ 已找到合法方案")
            if diagnostics.search_was_escalated:
                lines.append("ℹ 初始結果仍可能改善，系統已自動增加計算強度。")
            if diagnostics.result_is_stable:
                lines.append("✓ 搜尋結果已穩定。")
            elif diagnostics.search_limit_reached:
                lines.append("⚠ 已使用最大搜尋強度，結果尚未完全穩定，可比較其他合法方案。")
            if diagnostics.main_issue_category not in {
                solver_search.CANDIDATE_INSUFFICIENT,
                solver_search.ENGINEERING_CONSTRAINT_LIMITED,
            }:
                lines.append("✓ 候選方案充足。")
        else:
            lines.append("目前搜尋未找到合法方案。")
            if diagnostics.infeasibility_proven:
                lines.append("工程條件下無可行解。")
            elif diagnostics.search_stage == "PHASE1":
                lines.append("部分支撐沒有合法單體候選，未進入全域配置。")
            else:
                lines.append("系統已使用最大搜尋強度，但不能據此證明工程條件一定無解。")

        if diagnostics.main_issue_message:
            lines.append(f"主要限制：{diagnostics.main_issue_message}")
        if diagnostics.affected_component_ids:
            component_labels = []
            for component_id in diagnostics.affected_component_ids[:8]:
                if component_id in diagnostics.component_candidate_counts:
                    component_labels.append(
                        f"{component_id}（合法候選 "
                        f"{diagnostics.component_candidate_counts[component_id]}）"
                    )
                else:
                    component_labels.append(component_id)
            lines.append(
                "需要檢查：" + "、".join(component_labels)
                + ("…" if len(diagnostics.affected_component_ids) > 8 else "")
            )
        return "\n".join(lines)

    def _display_solution(self, solution, diagnostics=None):
        self.solution = solution
        diagnostics = diagnostics or solver_search.SolverDiagnostics.from_dict(
            getattr(solution, "search_diagnostics", None)
        )
        if diagnostics is not None:
            self.summary_var.set(
                self._format_support_engineer_summary(solution, diagnostics)
            )
        plans = list(solution.plans)
        plan_scores = [float(plan.score) for plan in plans]
        minimum_score = min(plan_scores, default=0.0)
        maximum_score = max(plan_scores, default=0.0)
        baseline_plan = next(
            (plan for plan in plans if abs(float(plan.score) - minimum_score) < 1e-9),
            None,
        )
        baseline_breakdown = dict(getattr(baseline_plan, "breakdown", {}) or {})
        score_distribution = Counter(round(score, 6) for score in plan_scores)
        pattern_summary = support.pattern_diversity_summary(plans)
        min_distance = getattr(solution, "min_jack_distance", None)
        distance_at_limit = (
            min_distance is not None
            and abs(float(min_distance) - support.MIN_JACK_DISTANCE_BETWEEN_SUPPORTS) < 1e-9
        )
        lines = [
            "",
            f"=== 分區 {self.zoning} 支撐配置完成 ===",
            f"結果：{'合法' if solution.valid else '不合法'}；"
            f"成功配置 {sum(plan.valid and not plan.reason for plan in plans)}/{len(plans)} 支",
            f"單體分數合計：{getattr(solution, 'single_score_total', sum(plan_scores)):.1f}；"
            f"最低 {minimum_score:.0f}，最高 {maximum_score:.0f}",
            "分數分布：" + "、".join(
                f"{score:.0f}分×{count}支"
                for score, count in sorted(score_distribution.items())
            ),
            f"相鄰Jack最小距離："
            f"{format_result_value(min_distance if min_distance is not None else '無資料')} mm"
            f"（下限 {support.MIN_JACK_DISTANCE_BETWEEN_SUPPORTS} mm）",
            f"材料配置多樣性：{pattern_summary['pattern_kind_count']} 種Pattern；"
            f"同一Pattern最多使用 {pattern_summary['max_pattern_usage']} 次",
        ]
        if solution.reason:
            lines.append(f"說明：{solution.reason}")
        if distance_at_limit:
            lines.append("[注意] 最小Jack距離剛好等於規定下限，結果合法但沒有額外距離餘裕。")

        lines.extend(self._format_global_material_ratio_lines(solution))

        candidate_statuses = list(getattr(solution, "candidate_diagnostics", []) or [])
        if candidate_statuses:
            source_totals = Counter()
            processed_counts = []
            selected_counts = []
            pool_counts = []
            retained_counts = []
            for status in candidate_statuses:
                record = dict(status.get("diagnostics", {}) or {})
                diagnostics = dict(record.get("diagnostics", {}) or {})
                benchmark = dict(diagnostics.get("candidate_benchmark", {}) or {})
                source_totals.update(dict(diagnostics.get("selection_counts", {}) or {}))
                processed_counts.append(int(diagnostics.get("combinations_processed", 0) or 0))
                selected_counts.append(int(record.get("combination_count", 0) or 0))
                pool_counts.append(int(benchmark.get("candidate_count_before_topn", 0) or 0))
                retained_counts.append(int(status.get("actual_valid_count", 0) or 0))
            fully_processed = all(
                processed == selected
                for processed, selected in zip(processed_counts, selected_counts)
                if selected
            )
            retained_text = (
                f"{retained_counts[0]} 個"
                if retained_counts and min(retained_counts) == max(retained_counts)
                else f"{min(retained_counts, default=0)}～{max(retained_counts, default=0)} 個"
            )
            lines.extend([
                "",
                "候選生成摘要",
                f"材料組合：{'全部完整處理' if fully_processed else '有支撐未完整處理'}；"
                f"每支候選池 {min(pool_counts, default=0)}～{max(pool_counts, default=0)} 個，"
                f"最終每支保留 {retained_text}",
                f"候選來源（{len(candidate_statuses)}支合計）："
                f"Jack位置 {source_totals.get('selected_by_jack_bucket_guarantee', 0)}、"
                f"材料型態 {source_totals.get('selected_by_material_style_guarantee', 0)}、"
                f"分數補入 {source_totals.get('selected_by_score_fill', 0)}",
            ])

        lines.extend(["", "各支撐結果"])
        for plan in plans:
            steel_lengths = [
                int(length)
                for kind, length in plan.pieces
                if str(kind).lower() == "steel"
            ]
            steel_text = "+".join(str(length) for length in sorted(steel_lengths))
            plan_status = "正常"
            if not plan.valid or plan.reason:
                plan_status = "不合法"
            elif float(plan.score) > minimum_score:
                plan_status = "注意"
            lines.append(
                f"{plan.support_id}｜{steel_text}｜Jack {plan.jack_center:.0f}（區{plan.jack_region_id}）｜"
                f"Gap {plan.gap}｜分數 {plan.score:.0f}｜{plan_status}"
            )
            if float(plan.score) > minimum_score:
                extra_breakdown = []
                labels = (
                    ("short_penalty", "短料"),
                    ("joint_penalty", "接頭"),
                    ("gap_penalty", "Gap"),
                    ("jack_edge_penalty", "Jack靠邊"),
                    ("invalid_penalty", "不合法"),
                )
                for key, label in labels:
                    value = float(plan.breakdown.get(key, 0.0) or 0.0)
                    baseline_value = float(baseline_breakdown.get(key, 0.0) or 0.0)
                    difference = value - baseline_value
                    if difference <= 1e-9:
                        continue
                    if key == "joint_penalty" and support.SUPPORT_JOINT_PENALTY_WEIGHT:
                        extra_joint_count = int(round(
                            difference / support.SUPPORT_JOINT_PENALTY_WEIGHT
                        ))
                        extra_breakdown.append(
                            f"多 {extra_joint_count} 個接頭（+{difference:.0f}）"
                        )
                    else:
                        extra_breakdown.append(f"{label} +{difference:.0f}")
                difference_text = "、".join(extra_breakdown) or "評分項目組合不同"
                lines.append(
                    f"  [注意] 比最低單體分多 {plan.score - minimum_score:.0f}；"
                    + difference_text
                )
            if plan.reason:
                lines.append(f"  說明：{plan.reason}")

        self.text_writer.write("\n".join(lines) + "\n")
        self.callback(self.zoning, solution)

    @staticmethod
    def _format_global_material_ratio_lines(solution):
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

        return [
            f"材料分類：短 {int(counts.get('short', 0) or 0)}支（{percent(ratios.get('short', 0.0))}）、"
            f"中 {int(counts.get('mid', 0) or 0)}支（{percent(ratios.get('mid', 0.0))}）、"
            f"長 {int(counts.get('long', 0) or 0)}支（{percent(ratios.get('long', 0.0))}）",
            f"群組附加分數：Jack區域 {getattr(solution, 'jack_region_penalty', 0.0):.0f}、"
            f"材料比例 {penalty:.0f}",
        ]

    def _on_close(self):
        self._close_ui_bridge()
        self.dialog.destroy()

    def open(self):
        self.dialog.wait_window()
        return self.solution
