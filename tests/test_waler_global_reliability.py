import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bracing_optimizer.algorithms.waler_global import (
    WalerGlobalDiagnostics,
    WalerGlobalSolution,
)
from bracing_optimizer.application.waler_solver_guard import WalerSolverBusyGuard
from bracing_optimizer.presentation.dialogs.waler_global_solver_dialog import (
    WalerGlobalSolverDialog,
    format_waler_global_result_summary,
)


def solution():
    return WalerGlobalSolution(
        total_short=2,
        total_mid=5,
        total_long=3,
        total_out=0,
        short_ratio=0.2,
        mid_ratio=0.5,
        long_ratio=0.3,
        ratio_deviation=0.0,
        total_out_distance_mm=0,
        total_local_regret=1.5,
        changed_waler_count=1,
        valid=True,
    )


class _Dialog:
    def __init__(self):
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


class _Button:
    def __init__(self):
        self.state = "normal"

    def configure(self, **options):
        self.state = options.get("state", self.state)


class WalerGlobalReliabilityTests(unittest.TestCase):
    def test_summary_uses_25_50_25_diagnostics_target(self):
        diagnostics = WalerGlobalDiagnostics(
            target_ratio={"short": 0.25, "mid": 0.50, "long": 0.25}
        )

        text = format_waler_global_result_summary(solution(), diagnostics)

        self.assertIn("目標 25.00%／50.00%／25.00%", text)
        self.assertNotIn("目標 20%／50%／30%", text)

    def test_summary_uses_10_60_30_diagnostics_target(self):
        diagnostics = WalerGlobalDiagnostics(
            target_ratio={"short": 0.10, "mid": 0.60, "long": 0.30}
        )

        text = format_waler_global_result_summary(solution(), diagnostics)

        self.assertIn("目標 10.00%／60.00%／30.00%", text)

    def test_close_is_blocked_while_global_solver_is_running(self):
        dialog = WalerGlobalSolverDialog.__new__(WalerGlobalSolverDialog)
        dialog.dialog = _Dialog()
        dialog._calculation_running = True
        dialog._close_ui_bridge = lambda: self.fail("bridge must remain open")

        with self.assertLogs(
            "bracing_optimizer.presentation.dialogs."
            "waler_global_solver_dialog",
            level="WARNING",
        ):
            with patch(
                "bracing_optimizer.presentation.dialogs."
                "waler_global_solver_dialog.messagebox.showwarning"
            ) as warning:
                dialog._on_close()

        self.assertFalse(dialog.dialog.destroyed)
        warning.assert_called_once()
        self.assertIn("仍在計算中", warning.call_args.args[1])

    def test_worker_exception_releases_guard_before_any_ui_callback(self):
        class FailingOptimizer:
            @staticmethod
            def execute(*_args, **_kwargs):
                raise RuntimeError("solver failed")

        guard = WalerSolverBusyGuard()
        lease = guard.try_acquire("global")
        dialog = WalerGlobalSolverDialog.__new__(WalerGlobalSolverDialog)
        dialog.optimize_waler_global = FailingOptimizer()
        dialog.text_writer = SimpleNamespace(write=lambda _message: None)
        dialog._post_ui = lambda _callback: None

        with self.assertLogs(
            "bracing_optimizer.presentation.dialogs."
            "waler_global_solver_dialog",
            level="ERROR",
        ):
            dialog._worker(SimpleNamespace(), lease)

        self.assertFalse(guard.is_busy)
        next_lease = guard.try_acquire("single")
        self.assertIsNotNone(next_lease)
        next_lease.release()

    def test_apply_commit_failure_reports_original_results_unchanged(self):
        dialog = WalerGlobalSolverDialog.__new__(WalerGlobalSolverDialog)
        dialog.dialog = _Dialog()
        dialog.current_result = SimpleNamespace(solution=solution())
        dialog.apply_button = _Button()
        dialog.callback = lambda _result: SimpleNamespace(
            committed=False,
            refreshed=False,
            error="commit failed",
        )

        with patch(
            "bracing_optimizer.presentation.dialogs."
            "waler_global_solver_dialog.messagebox.showerror"
        ) as error:
            dialog._apply()

        self.assertEqual(dialog.apply_button.state, "normal")
        self.assertIn("原成果未變更", error.call_args.args[1])

    def test_apply_refresh_failure_reports_data_is_in_project_memory(self):
        dialog = WalerGlobalSolverDialog.__new__(WalerGlobalSolverDialog)
        dialog.dialog = _Dialog()
        dialog.current_result = SimpleNamespace(solution=solution())
        dialog.apply_button = _Button()
        dialog.callback = lambda _result: SimpleNamespace(
            committed=True,
            refreshed=False,
            refresh_error="preview failed",
        )

        with patch(
            "bracing_optimizer.presentation.dialogs."
            "waler_global_solver_dialog.messagebox.showwarning"
        ) as warning:
            dialog._apply()

        self.assertEqual(dialog.apply_button.state, "disabled")
        self.assertIn("目前專案狀態", warning.call_args.args[1])
        self.assertNotIn("磁碟", warning.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
