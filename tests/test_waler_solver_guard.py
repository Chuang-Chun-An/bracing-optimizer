import threading
import unittest

from bracing_optimizer.application.waler_solver_guard import WalerSolverBusyGuard


class WalerSolverBusyGuardTests(unittest.TestCase):
    def test_global_acquire_blocks_single(self):
        guard = WalerSolverBusyGuard()

        global_lease = guard.try_acquire("global")

        self.assertIsNotNone(global_lease)
        self.assertTrue(guard.is_busy)
        self.assertIsNone(guard.try_acquire("single"))
        global_lease.release()

    def test_single_acquire_blocks_global(self):
        guard = WalerSolverBusyGuard()

        single_lease = guard.try_acquire("single")

        self.assertIsNotNone(single_lease)
        self.assertIsNone(guard.try_acquire("global"))
        single_lease.release()

    def test_release_allows_next_acquire(self):
        guard = WalerSolverBusyGuard()
        first = guard.try_acquire("single")
        first.release()

        second = guard.try_acquire("global")

        self.assertIsNotNone(second)
        second.release()
        self.assertFalse(guard.is_busy)

    def test_context_manager_releases_after_solver_exception(self):
        guard = WalerSolverBusyGuard()

        with self.assertRaisesRegex(RuntimeError, "solver failed"):
            with guard.try_acquire("global"):
                raise RuntimeError("solver failed")

        self.assertFalse(guard.is_busy)
        replacement = guard.try_acquire("single")
        self.assertIsNotNone(replacement)
        replacement.release()

    def test_duplicate_release_is_idempotent(self):
        guard = WalerSolverBusyGuard()
        lease = guard.try_acquire("single")

        lease.release()
        lease.release()

        self.assertTrue(lease.released)
        self.assertFalse(guard.is_busy)

    def test_two_threads_cannot_acquire_at_the_same_time(self):
        guard = WalerSolverBusyGuard()
        start = threading.Barrier(3)
        attempted = threading.Barrier(3)
        results = []
        results_lock = threading.Lock()

        def contender(owner):
            start.wait()
            lease = guard.try_acquire(owner)
            with results_lock:
                results.append(lease is not None)
            attempted.wait()
            if lease is not None:
                lease.release()

        threads = [
            threading.Thread(target=contender, args=("single",)),
            threading.Thread(target=contender, args=("global",)),
        ]
        for thread in threads:
            thread.start()
        start.wait()
        attempted.wait()
        for thread in threads:
            thread.join(timeout=2)

        self.assertEqual(sorted(results), [False, True])
        self.assertFalse(guard.is_busy)


if __name__ == "__main__":
    unittest.main()
