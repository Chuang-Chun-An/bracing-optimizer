import unittest
import copy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bracing_optimizer.application.solver_operation_registry import (
    SnapshotState,
    SolverKind,
    SolverOperationRegistry,
)
from bracing_optimizer.application.waler_solver_guard import WalerSolverBusyGuard
from bracing_optimizer.presentation.dialogs.support_solver_dialog import (
    ADOPTION_BLOCKED_MESSAGE,
    CAD_STALE_OPEN_MESSAGE,
    CAD_STALE_RUNNING_MESSAGE,
    SupportSolverDialog,
)
from bracing_optimizer.presentation.dialogs.waler_global_solver_dialog import (
    WalerGlobalSolverDialog,
)
from bracing_optimizer.presentation.dialogs.waler_solver_dialog import (
    WALER_SOLVER_STOPPING_MESSAGE,
    WalerSolverDialog,
)
from main import SupportInputApp


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


class _Dialog:
    @staticmethod
    def winfo_exists():
        return True


class _Text:
    def configure(self, **_options):
        pass

    def delete(self, *_args):
        pass


class _Tree:
    @staticmethod
    def get_children(_parent):
        return ()

    @staticmethod
    def delete(_item):
        pass


class SolverDialogOperationGateTests(unittest.TestCase):
    def _registry_execution(self, kind):
        registry = SolverOperationRegistry()
        handle = registry.register_snapshot(kind)
        execution = registry.start_execution(handle)
        return registry, handle, execution

    @staticmethod
    def _unresolved_app():
        app = SupportInputApp.__new__(SupportInputApp)
        app.cad_ack_unresolved_event_id = "unresolved-event"
        app.projection_stale = False
        app.result_items = {"existing": {"diagnostics": {"stable": True}}}
        app.project_result = {"existing": True}
        app.last_calculated_time = "before"
        app.project_dirty = False
        app.project_dirty_reason = ""
        app.support_candidate_cache = {"existing": [1]}
        app.solver_memory = {"existing": {"score": 1}}
        return app

    @staticmethod
    def _formal_state(app):
        return (
            copy.deepcopy(app.result_items),
            copy.deepcopy(app.project_result),
            app.last_calculated_time,
            app.project_dirty,
            app.project_dirty_reason,
            copy.deepcopy(app.support_candidate_cache),
            copy.deepcopy(app.solver_memory),
        )

    @staticmethod
    def _contaminate_formal_state(app):
        app.result_items = {"late": {"diagnostics": {"stale": True}}}
        app.project_result = {"late": True}
        app.last_calculated_time = "late"
        app.project_dirty = True
        app.project_dirty_reason = "late"

    @staticmethod
    def _support_dialog(registry, handle):
        dialog = SupportSolverDialog.__new__(SupportSolverDialog)
        dialog.operation_registry = registry
        dialog.snapshot_handle = handle
        dialog.adoption_guard = Mock()
        dialog.callback = Mock()
        dialog.optimize_support_zone = Mock()
        dialog.zoning = "Z1"
        dialog._snapshot_stale = False
        dialog._calculation_running = True
        dialog.run_button = _Button()
        dialog.summary_var = _Var()
        dialog._display_solution = Mock()
        dialog._display_diagnostics_only = Mock()
        return dialog

    @staticmethod
    def _single_dialog(registry, handle):
        dialog = WalerSolverDialog.__new__(WalerSolverDialog)
        dialog.operation_registry = registry
        dialog.snapshot_handle = handle
        dialog.adoption_guard = Mock()
        dialog._snapshot_stale = False
        dialog._calculation_running = True
        dialog.run_button = _Button()
        dialog.summary_var = _Var()
        dialog._display_results = Mock()
        dialog._save_solver_memory = Mock()
        dialog.cfg = None
        return dialog

    @staticmethod
    def _global_dialog(registry, handle):
        dialog = WalerGlobalSolverDialog.__new__(WalerGlobalSolverDialog)
        dialog.operation_registry = registry
        dialog.snapshot_handle = handle
        dialog.adoption_guard = Mock()
        dialog._snapshot_stale = False
        dialog._calculation_running = True
        dialog.run_button = _Button()
        dialog.summary_var = _Var()
        dialog.current_result = None
        dialog._display_result = Mock(return_value=True)
        dialog._adopt_current_result = Mock()
        dialog._display_error = Mock()
        dialog._closed = False
        dialog.dialog = _Dialog()
        return dialog

    def test_open_dialogs_become_stale_without_starting_workers(self):
        for dialog_class, kind in (
            (SupportSolverDialog, SolverKind.SUPPORT),
            (WalerSolverDialog, SolverKind.SINGLE_WALER),
            (WalerGlobalSolverDialog, SolverKind.GLOBAL_WALER),
        ):
            with self.subTest(kind=kind.value):
                registry = SolverOperationRegistry()
                handle = registry.register_snapshot(kind)
                dialog = dialog_class.__new__(dialog_class)
                dialog.operation_registry = registry
                dialog.snapshot_handle = handle
                dialog._snapshot_stale = False
                dialog._calculation_running = False
                dialog.run_button = _Button()
                dialog.summary_var = _Var()
                registry.set_stale_listener(handle, dialog._on_snapshot_stale)

                invalidated = registry.invalidate_open_and_running("cad_update")

                self.assertEqual(len(invalidated), 1)
                self.assertFalse(invalidated[0].was_running)
                self.assertEqual(dialog.run_button.state, "disabled")
                self.assertEqual(dialog.summary_var.get(), CAD_STALE_OPEN_MESSAGE)
                self.assertEqual(registry.status(handle).state, SnapshotState.STALE)

    def test_support_stale_completion_discards_result_and_cache(self):
        registry, handle, execution = self._registry_execution(SolverKind.SUPPORT)
        dialog = self._support_dialog(registry, handle)
        registry.invalidate_open_and_running("cad_update")
        operation_result = SimpleNamespace(candidate_cache_updates={"stale": 1})

        dialog._finish_worker(
            object(),
            object(),
            None,
            execution=execution,
            operation_result=operation_result,
        )

        dialog.adoption_guard.assert_not_called()
        dialog.callback.assert_not_called()
        dialog.optimize_support_zone.adopt_candidate_cache_updates.assert_not_called()
        dialog._display_solution.assert_not_called()
        self.assertEqual(dialog.summary_var.get(), CAD_STALE_RUNNING_MESSAGE)
        self.assertEqual(dialog.run_button.state, "disabled")

    def test_support_unresolved_guard_blocks_result_diagnostics_and_cache(self):
        registry, handle, execution = self._registry_execution(SolverKind.SUPPORT)
        dialog = self._support_dialog(registry, handle)
        app = self._unresolved_app()
        before = self._formal_state(app)
        dialog.adoption_guard = app._ensure_mutation_allowed
        dialog.callback = Mock(
            side_effect=lambda *_args: self._contaminate_formal_state(app)
        )
        dialog.optimize_support_zone.adopt_candidate_cache_updates.side_effect = (
            lambda _result: app.support_candidate_cache.update({"late": True})
        )
        operation_result = SimpleNamespace(candidate_cache_updates={"new": 1})
        self.assertEqual(registry.status(handle).state, SnapshotState.RUNNING)

        dialog._finish_worker(
            object(),
            object(),
            None,
            execution=execution,
            operation_result=operation_result,
        )

        dialog.callback.assert_not_called()
        dialog.optimize_support_zone.adopt_candidate_cache_updates.assert_not_called()
        dialog._display_solution.assert_not_called()
        self.assertEqual(dialog.summary_var.get(), ADOPTION_BLOCKED_MESSAGE)
        self.assertEqual(dialog.run_button.state, "normal")
        self.assertEqual(self._formal_state(app), before)
        self.assertEqual(registry.status(handle).state, SnapshotState.OPEN)

    def test_support_normal_completion_adopts_result_then_cache(self):
        registry, handle, execution = self._registry_execution(SolverKind.SUPPORT)
        dialog = self._support_dialog(registry, handle)
        operation_result = SimpleNamespace(candidate_cache_updates={"new": 1})

        dialog._finish_worker(
            object(),
            object(),
            None,
            execution=execution,
            operation_result=operation_result,
        )

        dialog.adoption_guard.assert_called_once_with()
        dialog.callback.assert_called_once()
        dialog.optimize_support_zone.adopt_candidate_cache_updates.assert_called_once_with(
            operation_result
        )
        dialog._display_solution.assert_called_once()
        self.assertEqual(registry.status(handle).state, SnapshotState.OPEN)

    def test_single_unresolved_guard_blocks_result_and_memory(self):
        registry, handle, execution = self._registry_execution(
            SolverKind.SINGLE_WALER
        )
        dialog = self._single_dialog(registry, handle)
        app = self._unresolved_app()
        before = self._formal_state(app)
        dialog.adoption_guard = app._ensure_mutation_allowed
        dialog._display_results.side_effect = lambda *_args, **_kwargs: (
            self._contaminate_formal_state(app)
        )
        dialog._save_solver_memory.side_effect = lambda *_args: (
            app.solver_memory.update({"late": True})
        )
        self.assertEqual(registry.status(handle).state, SnapshotState.RUNNING)

        dialog._finish_worker(
            [{"segments": [4000]}],
            object(),
            None,
            config=object(),
            execution=execution,
        )

        dialog._display_results.assert_not_called()
        dialog._save_solver_memory.assert_not_called()
        self.assertEqual(dialog.summary_var.get(), ADOPTION_BLOCKED_MESSAGE)
        self.assertEqual(dialog.run_button.state, "normal")
        self.assertEqual(self._formal_state(app), before)
        self.assertEqual(registry.status(handle).state, SnapshotState.OPEN)

    def test_single_stale_completion_does_not_write_memory(self):
        registry, handle, execution = self._registry_execution(
            SolverKind.SINGLE_WALER
        )
        dialog = self._single_dialog(registry, handle)
        registry.invalidate_open_and_running("cad_update")

        dialog._finish_worker(
            [{"segments": [4000]}],
            object(),
            None,
            config=object(),
            execution=execution,
        )

        dialog._display_results.assert_not_called()
        dialog._save_solver_memory.assert_not_called()
        self.assertEqual(dialog.run_button.state, "disabled")

    def test_single_normal_completion_saves_memory_only_after_adoption(self):
        registry, handle, execution = self._registry_execution(
            SolverKind.SINGLE_WALER
        )
        dialog = self._single_dialog(registry, handle)
        config = object()
        call_order = []
        dialog._display_results.side_effect = lambda *_args, **_kwargs: call_order.append(
            "result"
        )
        dialog._save_solver_memory.side_effect = lambda *_args: call_order.append(
            "memory"
        )

        dialog._finish_worker(
            [{"segments": [4000]}],
            object(),
            None,
            config=config,
            execution=execution,
        )

        self.assertIs(dialog.cfg, config)
        self.assertEqual(call_order, ["result", "memory"])
        self.assertEqual(registry.status(handle).state, SnapshotState.OPEN)

    def test_global_unresolved_guard_skips_display_and_auto_apply(self):
        registry, handle, execution = self._registry_execution(
            SolverKind.GLOBAL_WALER
        )
        dialog = self._global_dialog(registry, handle)
        app = self._unresolved_app()
        before = self._formal_state(app)
        dialog.adoption_guard = app._ensure_mutation_allowed
        dialog._display_result.side_effect = lambda _result: (
            self._contaminate_formal_state(app) or True
        )
        dialog._adopt_current_result.side_effect = lambda: (
            self._contaminate_formal_state(app)
        )
        self.assertEqual(registry.status(handle).state, SnapshotState.RUNNING)

        dialog._finish_worker(object(), None, execution=execution)

        dialog._display_result.assert_not_called()
        dialog._adopt_current_result.assert_not_called()
        self.assertEqual(dialog.summary_var.get(), ADOPTION_BLOCKED_MESSAGE)
        self.assertEqual(dialog.run_button.state, "normal")
        self.assertEqual(self._formal_state(app), before)
        self.assertEqual(registry.status(handle).state, SnapshotState.OPEN)

    def test_global_normal_valid_completion_runs_gate_and_auto_apply(self):
        registry, handle, execution = self._registry_execution(
            SolverKind.GLOBAL_WALER
        )
        dialog = self._global_dialog(registry, handle)

        dialog._finish_worker(object(), None, execution=execution)

        dialog.adoption_guard.assert_called_once_with()
        dialog._display_result.assert_called_once()
        dialog._adopt_current_result.assert_called_once_with()
        self.assertEqual(registry.status(handle).state, SnapshotState.OPEN)

    def test_global_stale_completion_skips_display_and_auto_apply(self):
        registry, handle, execution = self._registry_execution(
            SolverKind.GLOBAL_WALER
        )
        dialog = self._global_dialog(registry, handle)
        registry.invalidate_open_and_running("cad_update")

        dialog._finish_worker(object(), None, execution=execution)

        dialog._display_result.assert_not_called()
        dialog._adopt_current_result.assert_not_called()
        self.assertEqual(dialog.run_button.state, "disabled")

    def test_global_worker_does_not_mutate_single_waler_memory(self):
        registry, handle, execution = self._registry_execution(
            SolverKind.GLOBAL_WALER
        )
        dialog = WalerGlobalSolverDialog.__new__(WalerGlobalSolverDialog)
        dialog.optimize_waler_global = Mock(
            return_value=None,
        )
        dialog.optimize_waler_global.execute.return_value = object()
        dialog.text_writer = SimpleNamespace(write=Mock())
        queued = []
        dialog._post_ui = queued.append
        guard = WalerSolverBusyGuard()
        lease = guard.try_acquire("global")
        solver_memory = {("existing",): {"results": [{"score": 1}]}}
        before = copy.deepcopy(solver_memory)
        dialog.solver_memory = solver_memory

        dialog._worker(object(), lease, execution)

        self.assertEqual(solver_memory, before)
        self.assertTrue(lease.released)
        self.assertEqual(len(queued), 1)

    def test_running_close_does_not_cancel_registry_execution(self):
        registry, handle, execution = self._registry_execution(SolverKind.SUPPORT)
        dialog = SupportSolverDialog.__new__(SupportSolverDialog)
        dialog.operation_registry = registry
        dialog.snapshot_handle = handle
        dialog._calculation_running = True
        dialog.dialog = _Dialog()

        with patch(
            "bracing_optimizer.presentation.dialogs."
            "support_solver_dialog.messagebox.showwarning"
        ):
            dialog._on_close()

        self.assertFalse(execution.cancellation_token.is_cancelled)
        self.assertEqual(registry.status(handle).state, SnapshotState.RUNNING)

    @staticmethod
    def _make_single_busy_dialog(registry, handle, guard):
        dialog = WalerSolverDialog.__new__(WalerSolverDialog)
        dialog.short_ratio_var = _Var("20")
        dialog.mid_ratio_var = _Var("50")
        dialog.long_ratio_var = _Var("30")
        dialog.material_ratio_targets = None
        dialog.length = 10000
        dialog.purchasable_lengths = (4000, 6000)
        dialog.waler_input = object()
        dialog.optimize_waler = Mock()
        dialog.optimize_waler.build_cache_key.return_value = ("cache-key",)
        dialog.solver_memory = {}
        dialog.waler_solver_guard = guard
        dialog.waler_id = "W1"
        dialog.result_text = _Text()
        dialog.current_results = None
        dialog.summary_var = _Var()
        dialog._append_message = Mock()
        dialog.run_button = _Button()
        dialog.dialog = _Dialog()
        dialog._calculation_running = False
        dialog._snapshot_stale = False
        dialog.operation_registry = registry
        dialog.snapshot_handle = handle
        dialog.adoption_guard = Mock()
        return dialog

    def test_single_busy_failure_keeps_old_stopping_lease(self):
        registry = SolverOperationRegistry()
        old_handle = registry.register_snapshot(SolverKind.SINGLE_WALER)
        old_execution = registry.start_execution(old_handle)
        registry.invalidate_open_and_running("cad_update")
        new_handle = registry.register_snapshot(SolverKind.SINGLE_WALER)
        guard = WalerSolverBusyGuard()
        old_lease = guard.try_acquire("single")
        dialog = self._make_single_busy_dialog(registry, new_handle, guard)

        with patch(
            "bracing_optimizer.presentation.dialogs."
            "waler_solver_dialog.messagebox.showwarning"
        ) as warning:
            dialog._run_solver()

        self.assertTrue(old_execution.cancellation_token.is_cancelled)
        self.assertTrue(guard.is_busy)
        self.assertFalse(old_lease.released)
        self.assertEqual(registry.status(new_handle).state, SnapshotState.OPEN)
        self.assertEqual(warning.call_args.args[1], WALER_SOLVER_STOPPING_MESSAGE)
        old_lease.release()
        replacement_lease = guard.try_acquire("single")
        self.assertIsNotNone(replacement_lease)
        replacement_lease.release()

    def test_global_busy_failure_keeps_old_stopping_lease(self):
        registry = SolverOperationRegistry()
        old_handle = registry.register_snapshot(SolverKind.GLOBAL_WALER)
        registry.start_execution(old_handle)
        registry.invalidate_open_and_running("cad_update")
        new_handle = registry.register_snapshot(SolverKind.GLOBAL_WALER)
        guard = WalerSolverBusyGuard()
        old_lease = guard.try_acquire("global")
        dialog = WalerGlobalSolverDialog.__new__(WalerGlobalSolverDialog)
        dialog._targets = Mock(return_value=object())
        dialog.waler_solver_guard = guard
        dialog.operation_registry = registry
        dialog.snapshot_handle = new_handle
        dialog._snapshot_stale = False
        dialog.dialog = _Dialog()

        with patch(
            "bracing_optimizer.presentation.dialogs."
            "waler_global_solver_dialog.messagebox.showwarning"
        ) as warning:
            dialog._run()

        self.assertTrue(guard.is_busy)
        self.assertFalse(old_lease.released)
        self.assertEqual(registry.status(new_handle).state, SnapshotState.OPEN)
        self.assertEqual(warning.call_args.args[1], WALER_SOLVER_STOPPING_MESSAGE)
        old_lease.release()
        replacement_lease = guard.try_acquire("global")
        self.assertIsNotNone(replacement_lease)
        replacement_lease.release()

    def test_main_waler_entry_reports_stopping_worker(self):
        registry = SolverOperationRegistry()
        handle = registry.register_snapshot(SolverKind.SINGLE_WALER)
        registry.start_execution(handle)
        registry.invalidate_open_and_running("cad_update")
        guard = WalerSolverBusyGuard()
        guard.try_acquire("single")
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = object()
        app._ensure_waler_solver_guard = Mock(return_value=guard)
        app._ensure_solver_operation_registry = Mock(return_value=registry)
        app.show_result = Mock()

        with patch("main.messagebox.showwarning") as warning:
            for open_workflow in (
                app._open_waler_solver,
                app._open_waler_global_solver,
            ):
                with self.subTest(workflow=open_workflow.__name__):
                    open_workflow()

        self.assertEqual(warning.call_count, 2)
        self.assertTrue(all(
            call.args[1] == WALER_SOLVER_STOPPING_MESSAGE
            for call in warning.call_args_list
        ))


if __name__ == "__main__":
    unittest.main()
