import threading
import unittest

from bracing_optimizer.algorithms.cancellation import (
    CancellationSource,
    SolverCancelled,
)
from bracing_optimizer.algorithms import solver_search, wales
from bracing_optimizer.algorithms.waler_global import (
    WalerGlobalCandidate,
    merge_equivalent_candidates,
)


class SolverCancellationTests(unittest.TestCase):
    def test_unset_token_is_a_no_op(self):
        source = CancellationSource()

        source.token.raise_if_cancelled()

        self.assertFalse(source.token.is_cancelled)

    def test_cancel_is_visible_through_read_only_token(self):
        source = CancellationSource()

        source.cancel()

        self.assertTrue(source.token.is_cancelled)
        with self.assertRaises(SolverCancelled):
            source.token.raise_if_cancelled()

    def test_duplicate_cancel_is_idempotent(self):
        source = CancellationSource()

        source.cancel()
        source.cancel()

        with self.assertRaises(SolverCancelled):
            source.token.raise_if_cancelled()

    def test_cancel_is_thread_safe(self):
        source = CancellationSource()
        threads = [threading.Thread(target=source.cancel) for _ in range(8)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        self.assertTrue(source.token.is_cancelled)

    def test_stage_result_projection_has_cancellation_checkpoint(self):
        source = CancellationSource()
        source.cancel()
        config = wales.Config(
            total_length=12_000,
            support_points=[],
            candidate_joint_points=[6_000],
        )

        with self.assertRaises(SolverCancelled):
            wales._top_results(
                [{"valid": True, "score": 1.0, "segments": [12_000]}],
                config,
                cancellation_token=source.token,
            )

    def test_cross_stage_merge_has_cancellation_checkpoint(self):
        source = CancellationSource()
        source.cancel()

        with self.assertRaises(SolverCancelled):
            solver_search.merge_waler_results(
                [{"valid": True, "score": 1.0, "segments": [12_000]}],
                limit=None,
                cancellation_token=source.token,
            )

    def test_material_signature_merge_has_cancellation_checkpoint(self):
        source = CancellationSource()
        source.cancel()
        candidate = WalerGlobalCandidate(
            waler_id="W1",
            candidate_rank=1,
            segments=(12_000,),
            joints=(),
            local_score=1.0,
            local_regret=0.0,
            short_count=0,
            mid_count=0,
            long_count=0,
            out_count=1,
            out_distance_mm=2_000,
            material_signature=(0, 0, 0, 1, 2_000),
            payload={},
        )

        with self.assertRaises(SolverCancelled):
            merge_equivalent_candidates(
                (candidate,),
                cancellation_token=source.token,
            )


if __name__ == "__main__":
    unittest.main()
