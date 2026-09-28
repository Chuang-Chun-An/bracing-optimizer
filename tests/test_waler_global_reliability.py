import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

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

    @staticmethod
    def winfo_exists():
        return True


class _Button:
    def __init__(self):
        self.state = "normal"

    def configure(self, **options):
        self.state = options.get("state", self.state)


class _Var:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class _Tree:
    def __init__(self):
        self.rows = []

    def insert(self, *args, **kwargs):
        self.rows.append((args, kwargs))


class WalerGlobalReliabilityTests(unittest.TestCase):
    @staticmethod
    def make_completion_dialog(callback):
        dialog = WalerGlobalSolverDialog.__new__(WalerGlobalSolverDialog)
        dialog.dialog = _Dialog()
        dialog.callback = callback
        dialog.current_result = None
        dialog._closed = False
        dialog._calculation_running = True
        dialog.run_button = _Button()
        dialog.summary_var = _Var()
        dialog.result_tree = _Tree()
        dialog._close_ui_bridge = Mock()
        return dialog

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

    def test_valid_completion_auto_applies_once_on_queued_ui_callback(self):
        result = SimpleNamespace(
            solution=solution(),
            diagnostics=WalerGlobalDiagnostics(),
        )

        class Optimizer:
            @staticmethod
            def execute(*_args, **_kwargs):
                return result

        callback = Mock(return_value=SimpleNamespace(
            committed=True,
            refreshed=True,
        ))
        dialog = self.make_completion_dialog(callback)
        dialog.optimize_waler_global = Optimizer()
        dialog.text_writer = SimpleNamespace(write=lambda _message: None)
        queued = []
        dialog._post_ui = queued.append
        guard = WalerSolverBusyGuard()
        lease = guard.try_acquire("global")

        dialog._worker(SimpleNamespace(), lease)

        callback.assert_not_called()
        self.assertEqual(len(queued), 1)
        queued[0]()
        callback.assert_called_once_with(result)
        self.assertIn("全域結果已採用", dialog.summary_var.get())
        self.assertFalse(dialog._calculation_running)

    def test_solver_exception_does_not_apply(self):
        callback = Mock()
        dialog = self.make_completion_dialog(callback)

        dialog._finish_worker(None, RuntimeError("solver failed"))

        callback.assert_not_called()
        self.assertIn("全部圍令最佳化失敗", dialog.summary_var.get())
        self.assertFalse(dialog._calculation_running)

    def test_invalid_solution_does_not_apply(self):
        callback = Mock()
        dialog = self.make_completion_dialog(callback)
        invalid_result = SimpleNamespace(
            solution=WalerGlobalSolution(valid=False, reason="no solution"),
            diagnostics=WalerGlobalDiagnostics(),
        )

        dialog._finish_worker(invalid_result, None)

        callback.assert_not_called()
        self.assertIn("no solution", dialog.summary_var.get())

    def test_missing_solution_does_not_apply(self):
        callback = Mock()
        dialog = self.make_completion_dialog(callback)

        dialog._finish_worker(None, None)

        callback.assert_not_called()
        self.assertIn("Solver 未回傳結果", dialog.summary_var.get())

    def test_auto_apply_commit_failure_reports_original_results_unchanged(self):
        callback = Mock(return_value=SimpleNamespace(
            committed=False,
            refreshed=False,
            error="commit failed",
        ))
        dialog = self.make_completion_dialog(callback)
        result = SimpleNamespace(
            solution=solution(),
            diagnostics=WalerGlobalDiagnostics(),
        )

        with patch(
            "bracing_optimizer.presentation.dialogs."
            "waler_global_solver_dialog.messagebox.showerror"
        ) as error:
            dialog._finish_worker(result, None)

        callback.assert_called_once_with(result)
        self.assertNotIn("全域結果已採用", dialog.summary_var.get())
        self.assertIn("原成果未變更", error.call_args.args[1])

    def test_auto_apply_refresh_failure_reports_data_is_in_project_memory(self):
        callback = Mock(return_value=SimpleNamespace(
            committed=True,
            refreshed=False,
            refresh_error="preview failed",
        ))
        dialog = self.make_completion_dialog(callback)
        result = SimpleNamespace(
            solution=solution(),
            diagnostics=WalerGlobalDiagnostics(),
        )

        with patch(
            "bracing_optimizer.presentation.dialogs."
            "waler_global_solver_dialog.messagebox.showwarning"
        ) as warning:
            dialog._finish_worker(result, None)

        self.assertIn("全域結果已採用", dialog.summary_var.get())
        self.assertIn("畫面更新失敗", dialog.summary_var.get())
        self.assertIn("目前專案狀態", warning.call_args.args[1])
        self.assertNotIn("磁碟", warning.call_args.args[1])

    def test_successful_auto_apply_summary_and_close_do_not_apply_twice(self):
        callback = Mock(return_value=SimpleNamespace(
            committed=True,
            refreshed=True,
        ))
        dialog = self.make_completion_dialog(callback)
        result = SimpleNamespace(
            solution=solution(),
            diagnostics=WalerGlobalDiagnostics(),
        )

        dialog._finish_worker(result, None)
        dialog._on_close()

        callback.assert_called_once_with(result)
        self.assertIn("全域結果已採用", dialog.summary_var.get())
        self.assertTrue(dialog.dialog.destroyed)

    def test_dialog_has_no_manual_apply_control_or_callback_path(self):
        init_source = inspect.getsource(WalerGlobalSolverDialog.__init__)

        self.assertNotIn("套用全域結果", init_source)
        self.assertNotIn("apply_button", init_source)
        self.assertFalse(hasattr(WalerGlobalSolverDialog, "_apply"))


if __name__ == "__main__":
    unittest.main()
