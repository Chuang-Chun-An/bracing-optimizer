import unittest
import inspect
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bracing_optimizer.application.waler_solver_guard import WalerSolverBusyGuard
from bracing_optimizer.presentation.dialogs.support_solver_dialog import (
    SupportSolverDialog,
)
from bracing_optimizer.presentation.dialogs.waler_global_solver_dialog import (
    WalerGlobalSolverDialog,
)
from bracing_optimizer.presentation.dialogs.waler_solver_dialog import (
    WalerSolverDialog,
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

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class _Text:
    def __init__(self):
        self.state = "disabled"
        self.deleted = False

    def configure(self, **options):
        self.state = options.get("state", self.state)

    def delete(self, *_args):
        self.deleted = True


class _Lease:
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True


class _FailingThread:
    def start(self):
        raise RuntimeError("thread start failed")


class _GlobalTree:
    @staticmethod
    def get_children(_parent):
        return ()

    @staticmethod
    def delete(_item_id):
        raise AssertionError("no rows should be deleted")


class SolverDialogClosePolicyTests(unittest.TestCase):
    DIALOG_CASES = (
        (
            "support",
            SupportSolverDialog,
            "bracing_optimizer.presentation.dialogs."
            "support_solver_dialog.messagebox.showwarning",
        ),
        (
            "single-waler",
            WalerSolverDialog,
            "bracing_optimizer.presentation.dialogs."
            "waler_solver_dialog.messagebox.showwarning",
        ),
        (
            "global-waler",
            WalerGlobalSolverDialog,
            "bracing_optimizer.presentation.dialogs."
            "waler_global_solver_dialog.messagebox.showwarning",
        ),
    )

    @staticmethod
    def _make_close_dialog(dialog_class, *, running):
        dialog = dialog_class.__new__(dialog_class)
        dialog.dialog = _Dialog()
        dialog._calculation_running = running
        dialog._close_ui_bridge = Mock()
        dialog.solution = object()
        dialog.current_results = object()
        dialog.current_result = object()
        return dialog

    def test_running_close_is_blocked_without_mutating_dialog_state(self):
        for name, dialog_class, warning_path in self.DIALOG_CASES:
            with self.subTest(dialog=name):
                dialog = self._make_close_dialog(dialog_class, running=True)
                result_snapshot = (
                    dialog.solution,
                    dialog.current_results,
                    dialog.current_result,
                )

                with patch(warning_path) as warning:
                    dialog._on_close()
                    dialog._on_close()

                self.assertFalse(dialog.dialog.destroyed)
                dialog._close_ui_bridge.assert_not_called()
                self.assertTrue(dialog._calculation_running)
                self.assertEqual(warning.call_count, 2)
                self.assertEqual(
                    (
                        dialog.solution,
                        dialog.current_results,
                        dialog.current_result,
                    ),
                    result_snapshot,
                )

    def test_non_running_close_uses_existing_destroy_path(self):
        for name, dialog_class, warning_path in self.DIALOG_CASES:
            with self.subTest(dialog=name):
                dialog = self._make_close_dialog(dialog_class, running=False)

                with patch(warning_path) as warning:
                    dialog._on_close()

                warning.assert_not_called()
                dialog._close_ui_bridge.assert_called_once_with()
                self.assertTrue(dialog.dialog.destroyed)

    def test_window_manager_and_available_close_buttons_share_close_handler(self):
        support_source = inspect.getsource(SupportSolverDialog.__init__)
        single_source = inspect.getsource(WalerSolverDialog.__init__)
        global_source = inspect.getsource(WalerGlobalSolverDialog.__init__)

        for source in (support_source, single_source, global_source):
            self.assertIn(
                'self.dialog.protocol("WM_DELETE_WINDOW", self._on_close)',
                source,
            )
        self.assertIn("command=self._on_close", support_source)
        self.assertIn("command=self._on_close", global_source)

    def test_support_success_finishes_after_result_adoption(self):
        dialog = SupportSolverDialog.__new__(SupportSolverDialog)
        dialog._calculation_running = True
        dialog.run_button = _Button()
        dialog.summary_var = _Var()
        running_during_display = []
        dialog._display_solution = lambda *_args: running_during_display.append(
            dialog._calculation_running
        )
        dialog._display_diagnostics_only = Mock()

        dialog._finish_worker(object(), object(), None)

        self.assertEqual(running_during_display, [True])
        self.assertFalse(dialog._calculation_running)
        self.assertEqual(dialog.run_button.state, "normal")

    def test_support_failure_restores_close_permission(self):
        dialog = SupportSolverDialog.__new__(SupportSolverDialog)
        dialog._calculation_running = True
        dialog.run_button = _Button()
        dialog.summary_var = _Var()
        dialog._display_solution = Mock()
        dialog._display_diagnostics_only = Mock()

        dialog._finish_worker(None, None, RuntimeError("solver failed"))

        dialog._display_solution.assert_not_called()
        dialog._display_diagnostics_only.assert_not_called()
        self.assertFalse(dialog._calculation_running)
        self.assertEqual(dialog.run_button.state, "normal")
        self.assertIn("計算發生錯誤", dialog.summary_var.get())

    def test_support_worker_keeps_running_until_queued_ui_finish(self):
        solution = object()
        diagnostics = object()
        optimizer = Mock()
        optimizer.execute.return_value = SimpleNamespace(
            solution=solution,
            diagnostics=diagnostics,
        )
        dialog = SupportSolverDialog.__new__(SupportSolverDialog)
        dialog.optimize_support_zone = optimizer
        dialog.text_writer = SimpleNamespace(write=Mock())
        dialog.summary_var = _Var()
        dialog.run_button = _Button()
        dialog._calculation_running = True
        running_during_display = []
        dialog._display_solution = lambda *_args: running_during_display.append(
            dialog._calculation_running
        )
        dialog._display_diagnostics_only = Mock()
        queued = []
        dialog._post_ui = queued.append

        dialog._solver_thread(object())

        self.assertTrue(dialog._calculation_running)
        self.assertEqual(len(queued), 1)
        queued[0]()
        self.assertEqual(running_during_display, [True])
        self.assertFalse(dialog._calculation_running)

    def test_support_display_exception_does_not_strand_running_state(self):
        dialog = SupportSolverDialog.__new__(SupportSolverDialog)
        dialog._calculation_running = True
        dialog.run_button = _Button()
        dialog.summary_var = _Var()
        dialog._display_solution = Mock(side_effect=RuntimeError("display failed"))
        dialog._display_diagnostics_only = Mock()

        with self.assertLogs(
            "bracing_optimizer.presentation.dialogs.support_solver_dialog",
            level="ERROR",
        ):
            dialog._finish_worker(object(), object(), None)

        self.assertFalse(dialog._calculation_running)
        self.assertEqual(dialog.run_button.state, "normal")

    def test_single_waler_success_finishes_after_result_adoption(self):
        dialog = WalerSolverDialog.__new__(WalerSolverDialog)
        dialog._calculation_running = True
        dialog.run_button = _Button()
        dialog.summary_var = _Var()
        running_during_display = []
        dialog._display_results = lambda *_args, **_kwargs: (
            running_during_display.append(dialog._calculation_running)
        )

        dialog._finish_worker([{"segments": [4000]}], object(), None)

        self.assertEqual(running_during_display, [True])
        self.assertFalse(dialog._calculation_running)
        self.assertEqual(dialog.run_button.state, "normal")

    def test_single_waler_failure_restores_close_permission(self):
        dialog = WalerSolverDialog.__new__(WalerSolverDialog)
        dialog._calculation_running = True
        dialog.run_button = _Button()
        dialog.summary_var = _Var()
        dialog._display_results = Mock()

        dialog._finish_worker(None, None, RuntimeError("solver failed"))

        dialog._display_results.assert_not_called()
        self.assertFalse(dialog._calculation_running)
        self.assertEqual(dialog.run_button.state, "normal")
        self.assertIn("計算發生錯誤", dialog.summary_var.get())

    def test_single_waler_worker_releases_lease_before_queued_ui_finish(self):
        diagnostics = object()
        optimizer = Mock()
        optimizer.execute.return_value = SimpleNamespace(
            config=object(),
            solutions=({"segments": [4000, 6000]},),
            diagnostics=diagnostics,
        )
        lease = _Lease()
        dialog = WalerSolverDialog.__new__(WalerSolverDialog)
        dialog.optimize_waler = optimizer
        dialog.text_writer = SimpleNamespace(write=Mock())
        dialog.summary_var = _Var()
        dialog.run_button = _Button()
        dialog.waler_id = "W1"
        dialog._calculation_running = True
        dialog._save_solver_memory = Mock()
        running_during_display = []
        dialog._display_results = lambda *_args, **_kwargs: (
            running_during_display.append(dialog._calculation_running)
        )
        queued = []
        dialog._post_ui = queued.append

        dialog._solver_thread(object(), lease)

        self.assertTrue(lease.released)
        self.assertTrue(dialog._calculation_running)
        self.assertEqual(len(queued), 1)
        queued[0]()
        self.assertEqual(running_during_display, [True])
        self.assertFalse(dialog._calculation_running)

    def test_single_waler_display_exception_does_not_strand_running_state(self):
        dialog = WalerSolverDialog.__new__(WalerSolverDialog)
        dialog._calculation_running = True
        dialog.run_button = _Button()
        dialog.summary_var = _Var()
        dialog._display_results = Mock(side_effect=RuntimeError("display failed"))

        with self.assertLogs(
            "bracing_optimizer.presentation.dialogs.waler_solver_dialog",
            level="ERROR",
        ):
            dialog._finish_worker([], object(), None)

        self.assertFalse(dialog._calculation_running)
        self.assertEqual(dialog.run_button.state, "normal")

    def test_support_thread_start_failure_returns_to_non_running(self):
        dialog = SupportSolverDialog.__new__(SupportSolverDialog)
        dialog.short_ratio_var = _Var("20")
        dialog.mid_ratio_var = _Var("50")
        dialog.long_ratio_var = _Var("30")
        dialog.result_text = _Text()
        dialog.solution = object()
        dialog.summary_var = _Var()
        dialog.support_input = object()
        dialog.run_button = _Button()
        dialog.dialog = _Dialog()
        dialog._calculation_running = False

        with (
            patch(
                "bracing_optimizer.presentation.dialogs."
                "support_solver_dialog.threading.Thread",
                return_value=_FailingThread(),
            ),
            patch(
                "bracing_optimizer.presentation.dialogs."
                "support_solver_dialog.messagebox.showerror"
            ),
        ):
            dialog._run_solver()

        self.assertFalse(dialog._calculation_running)
        self.assertEqual(dialog.run_button.state, "normal")

    def test_single_waler_thread_start_failure_returns_to_non_running(self):
        lease = _Lease()
        guard = Mock()
        guard.try_acquire.return_value = lease
        optimizer = Mock()
        optimizer.build_cache_key.return_value = ("cache-key",)
        dialog = WalerSolverDialog.__new__(WalerSolverDialog)
        dialog.short_ratio_var = _Var("20")
        dialog.mid_ratio_var = _Var("50")
        dialog.long_ratio_var = _Var("30")
        dialog.material_ratio_targets = None
        dialog.length = 10000
        dialog.purchasable_lengths = (4000, 6000)
        dialog.waler_input = object()
        dialog.optimize_waler = optimizer
        dialog.solver_memory = {}
        dialog.waler_solver_guard = guard
        dialog.waler_id = "W1"
        dialog.result_text = _Text()
        dialog.current_results = object()
        dialog.summary_var = _Var()
        dialog._append_message = Mock()
        dialog.run_button = _Button()
        dialog.dialog = _Dialog()
        dialog._calculation_running = False

        with (
            patch(
                "bracing_optimizer.presentation.dialogs."
                "waler_solver_dialog.threading.Thread",
                return_value=_FailingThread(),
            ),
            patch(
                "bracing_optimizer.presentation.dialogs."
                "waler_solver_dialog.messagebox.showerror"
            ),
        ):
            dialog._run_solver()

        self.assertTrue(lease.released)
        self.assertFalse(dialog._calculation_running)
        self.assertEqual(dialog.run_button.state, "normal")

    def test_global_waler_thread_start_failure_returns_to_non_running(self):
        lease = _Lease()
        guard = Mock()
        guard.try_acquire.return_value = lease
        dialog = WalerGlobalSolverDialog.__new__(WalerGlobalSolverDialog)
        dialog._targets = Mock(return_value=object())
        dialog.waler_solver_guard = guard
        dialog.current_result = object()
        dialog.run_button = _Button()
        dialog.summary_var = _Var()
        dialog.result_tree = _GlobalTree()
        dialog.log_text = _Text()
        dialog.waler_inputs = ()
        dialog.dialog = _Dialog()
        dialog._calculation_running = False

        with (
            patch(
                "bracing_optimizer.presentation.dialogs."
                "waler_global_solver_dialog.threading.Thread",
                return_value=_FailingThread(),
            ),
            patch(
                "bracing_optimizer.presentation.dialogs."
                "waler_global_solver_dialog.messagebox.showerror"
            ),
        ):
            dialog._run()

        self.assertTrue(lease.released)
        self.assertFalse(dialog._calculation_running)
        self.assertEqual(dialog.run_button.state, "normal")

    def test_single_waler_memory_path_never_enters_running(self):
        optimizer = Mock()
        optimizer.build_cache_key.return_value = ("cache-key",)
        guard = WalerSolverBusyGuard()
        dialog = WalerSolverDialog.__new__(WalerSolverDialog)
        dialog.short_ratio_var = _Var("20")
        dialog.mid_ratio_var = _Var("50")
        dialog.long_ratio_var = _Var("30")
        dialog.material_ratio_targets = None
        dialog.length = 10000
        dialog.purchasable_lengths = (4000, 6000)
        dialog.waler_input = object()
        dialog.optimize_waler = optimizer
        dialog.solver_memory = {("cache-key",): {"results": []}}
        dialog._ask_use_memory_result = Mock(return_value=True)
        restored_results = [{"segments": [4000, 6000]}]
        restored_diagnostics = object()
        restored_config = object()
        dialog._restore_solver_memory = Mock(
            return_value=(
                restored_results,
                restored_diagnostics,
                restored_config,
            )
        )
        dialog.waler_solver_guard = guard
        dialog.result_text = _Text()
        dialog.current_results = object()
        dialog._append_message = Mock()
        dialog._display_results = Mock()
        dialog._close_ui_bridge = Mock()
        dialog.dialog = _Dialog()
        dialog._calculation_running = False

        dialog._run_solver()

        self.assertFalse(dialog._calculation_running)
        self.assertFalse(guard.is_busy)
        dialog._display_results.assert_called_once_with(
            restored_results,
            diagnostics=restored_diagnostics,
        )
        dialog._on_close()
        dialog._close_ui_bridge.assert_called_once_with()
        self.assertTrue(dialog.dialog.destroyed)


if __name__ == "__main__":
    unittest.main()
