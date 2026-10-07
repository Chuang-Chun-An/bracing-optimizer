import unittest

from bracing_optimizer.application.solver_operation_registry import (
    CompletionDisposition,
    SnapshotState,
    SolverKind,
    SolverOperationRegistry,
    SolverOperationUnavailable,
)


class SolverOperationRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = SolverOperationRegistry()

    def test_open_snapshot_is_invalidated_without_worker_cancellation(self):
        handle = self.registry.register_snapshot(SolverKind.SUPPORT)

        invalidated = self.registry.invalidate_open_and_running("cad_update")

        self.assertEqual(len(invalidated), 1)
        self.assertFalse(invalidated[0].was_running)
        self.assertEqual(self.registry.status(handle).state, SnapshotState.STALE)
        with self.assertRaises(SolverOperationUnavailable):
            self.registry.start_execution(handle)

    def test_running_snapshot_is_cancelled_and_completion_is_stale(self):
        handle = self.registry.register_snapshot(SolverKind.SINGLE_WALER)
        execution = self.registry.start_execution(handle)

        self.registry.invalidate_open_and_running("cad_update")

        self.assertTrue(execution.cancellation_token.is_cancelled)
        self.assertEqual(
            self.registry.complete_execution(handle, execution.identity),
            CompletionDisposition.STALE,
        )
        self.assertEqual(self.registry.status(handle).state, SnapshotState.STALE)

    def test_normal_completion_returns_snapshot_to_open(self):
        handle = self.registry.register_snapshot(SolverKind.GLOBAL_WALER)
        execution = self.registry.start_execution(handle)

        disposition = self.registry.complete_execution(handle, execution.identity)

        self.assertEqual(disposition, CompletionDisposition.ADOPTABLE)
        self.assertEqual(self.registry.status(handle).state, SnapshotState.OPEN)

    def test_thread_start_abort_is_idempotent(self):
        handle = self.registry.register_snapshot(SolverKind.SUPPORT)
        execution = self.registry.start_execution(handle)

        self.assertTrue(self.registry.abort_execution(handle, execution.identity))
        self.assertFalse(self.registry.abort_execution(handle, execution.identity))
        self.assertEqual(self.registry.status(handle).state, SnapshotState.OPEN)

    def test_old_execution_cannot_complete_new_execution(self):
        handle = self.registry.register_snapshot(SolverKind.SUPPORT)
        first = self.registry.start_execution(handle)
        self.registry.complete_execution(handle, first.identity)
        second = self.registry.start_execution(handle)

        self.assertEqual(
            self.registry.complete_execution(handle, first.identity),
            CompletionDisposition.IGNORED,
        )
        self.assertTrue(self.registry.can_adopt(handle, second.identity))

    def test_multiple_handles_are_invalidated_together(self):
        handles = [
            self.registry.register_snapshot(kind)
            for kind in SolverKind
        ]
        execution = self.registry.start_execution(handles[1])

        invalidated = self.registry.invalidate_open_and_running("cad_update")

        self.assertEqual({item.handle for item in invalidated}, set(handles))
        self.assertTrue(execution.cancellation_token.is_cancelled)
        self.assertEqual(
            [item.was_running for item in invalidated].count(True),
            1,
        )

    def test_stale_listener_runs_and_late_registration_observes_stale(self):
        first = self.registry.register_snapshot(SolverKind.SUPPORT)
        second = self.registry.register_snapshot(SolverKind.SINGLE_WALER)
        observed = []
        self.registry.set_stale_listener(first, observed.append)

        self.registry.invalidate_open_and_running("cad_update")
        self.registry.set_stale_listener(second, observed.append)

        self.assertEqual(observed, ["cad_update", "cad_update"])

    def test_close_and_duplicate_cleanup_are_idempotent(self):
        handle = self.registry.register_snapshot(SolverKind.SUPPORT)

        self.assertTrue(self.registry.close_snapshot(handle))
        self.assertTrue(self.registry.close_snapshot(handle))
        self.assertIsNone(self.registry.status(handle))

    def test_running_snapshot_cannot_close_before_terminal_cleanup(self):
        handle = self.registry.register_snapshot(SolverKind.SINGLE_WALER)
        execution = self.registry.start_execution(handle)

        self.assertFalse(self.registry.close_snapshot(handle))
        self.registry.abort_execution(handle, execution.identity)
        self.assertTrue(self.registry.close_snapshot(handle))

    def test_stale_running_waler_is_reported_until_cleanup(self):
        handle = self.registry.register_snapshot(SolverKind.GLOBAL_WALER)
        execution = self.registry.start_execution(handle)
        self.registry.invalidate_open_and_running("cad_update")

        self.assertTrue(self.registry.has_stale_running_waler())
        self.registry.complete_execution(handle, execution.identity)
        self.assertFalse(self.registry.has_stale_running_waler())

    def test_reopen_uses_new_snapshot_identity_and_old_callback_isolated(self):
        old_handle = self.registry.register_snapshot(SolverKind.SUPPORT)
        old_execution = self.registry.start_execution(old_handle)
        self.registry.invalidate_open_and_running("cad_update")
        self.assertEqual(
            self.registry.complete_execution(old_handle, old_execution.identity),
            CompletionDisposition.STALE,
        )
        self.assertTrue(self.registry.close_snapshot(old_handle))

        new_handle = self.registry.register_snapshot(SolverKind.SUPPORT)
        new_execution = self.registry.start_execution(new_handle)

        self.assertNotEqual(old_handle, new_handle)
        self.assertNotEqual(old_execution.identity, new_execution.identity)
        self.assertEqual(
            self.registry.complete_execution(old_handle, old_execution.identity),
            CompletionDisposition.IGNORED,
        )
        self.assertTrue(self.registry.can_adopt(new_handle, new_execution.identity))


if __name__ == "__main__":
    unittest.main()
