import itertools
import math
import unittest

from bracing_optimizer.algorithms.waler_global import (
    analyze_candidate_materials,
    build_global_candidate,
    material_out_distance,
    merge_equivalent_candidates,
    project_ratio_values,
    solve_global_waler_candidates,
)
from bracing_optimizer.domain.material_rules import MaterialRatioTargets


TARGETS = MaterialRatioTargets.normalized(20, 50, 30)


def candidate(waler_id, rank, segments, *, score=None, best_score=0.0):
    if score is None:
        score = best_score + rank - 1
    joints = []
    position = 0
    for length in segments[:-1]:
        position += length
        joints.append(position)
    return build_global_candidate(
        waler_id=waler_id,
        candidate_rank=rank,
        payload={
            "valid": True,
            "segments": list(segments),
            "joints": joints,
            "score": score,
        },
        local_best_score=best_score,
    )


def solve(groups):
    order = tuple(groups)
    return solve_global_waler_candidates(groups, TARGETS, waler_order=order)


class WalerGlobalMaterialMetadataTests(unittest.TestCase):
    def test_shared_classification_and_out_distance_boundaries(self):
        metadata = analyze_candidate_materials(
            [5000, 7000, 9000, 3500, 1000, 10500]
        )

        self.assertEqual(metadata.short_count, 1)
        self.assertEqual(metadata.mid_count, 1)
        self.assertEqual(metadata.long_count, 1)
        self.assertEqual(metadata.out_count, 3)
        self.assertEqual(metadata.out_distance_mm, 500 + 3000 + 500)
        self.assertEqual(material_out_distance(3500), 500)
        self.assertEqual(material_out_distance(1000), 3000)
        self.assertEqual(material_out_distance(10500), 500)

    def test_out_does_not_enter_project_ratio_denominator(self):
        short, mid, long, deviation = project_ratio_values(2, 2, 2, TARGETS)

        self.assertEqual((short, mid, long), (1 / 3, 1 / 3, 1 / 3))
        self.assertAlmostEqual(
            deviation,
            abs(1 / 3 - 0.2) + abs(1 / 3 - 0.5) + abs(1 / 3 - 0.3),
        )

    def test_no_classified_material_has_infinite_deviation(self):
        *_, deviation = project_ratio_values(0, 0, 0, TARGETS)

        self.assertTrue(math.isinf(deviation))

    def test_non_finite_local_score_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "單支分數無效"):
            candidate("W1", 1, [5000], score=math.nan)


class WalerGlobalLexicographicTests(unittest.TestCase):
    def test_out_count_wins_before_ratio(self):
        groups = {
            "W1": (
                candidate("W1", 1, [5000, 7000]),
                candidate("W1", 2, [3500, 5000, 7000, 9000]),
            )
        }

        solution, _ = solve(groups)

        self.assertEqual(solution.selected_candidates[0].candidate_rank, 1)
        self.assertEqual(solution.total_out, 0)

    def test_out_distance_wins_before_ratio(self):
        groups = {
            "W1": (
                candidate("W1", 1, [3500, 5000]),
                candidate("W1", 2, [1000, 5000, 7000, 9000]),
            )
        }

        solution, _ = solve(groups)

        self.assertEqual(solution.selected_candidates[0].candidate_rank, 1)
        self.assertEqual(solution.total_out_distance_mm, 500)

    def test_ratio_wins_when_out_terms_are_equal(self):
        groups = {
            "W1": (
                candidate("W1", 1, [5000, 7000, 9000]),
                candidate("W1", 2, [5000, 7000, 7000, 9000]),
            )
        }

        solution, _ = solve(groups)

        self.assertEqual(solution.selected_candidates[0].candidate_rank, 2)

    def test_local_regret_wins_after_out_and_ratio(self):
        groups = {
            "W1": (
                candidate("W1", 1, [5000], score=100, best_score=100),
                candidate("W1", 2, [5000], score=110, best_score=100),
            )
        }

        solution, _ = solve(groups)

        self.assertEqual(solution.selected_candidates[0].candidate_rank, 1)
        self.assertEqual(solution.total_local_regret, 0)

    def test_changed_waler_count_wins_after_equal_regret(self):
        groups = {
            "W1": (
                candidate("W1", 1, [5000], score=0),
                candidate("W1", 2, [7000], score=0),
            ),
            "W2": (
                candidate("W2", 1, [7000], score=0),
                candidate("W2", 2, [5000], score=0),
            ),
        }

        solution, _ = solve(groups)

        self.assertEqual(
            tuple(item.candidate_rank for item in solution.selected_candidates),
            (1, 1),
        )
        self.assertEqual(solution.changed_waler_count, 0)

    def test_rank_path_is_final_deterministic_tie_break(self):
        groups = {
            "W1": (
                candidate("W1", 1, [1000], score=0),
                candidate("W1", 2, [5000], score=10),
                candidate("W1", 3, [7000], score=10),
            ),
            "W2": (
                candidate("W2", 1, [1000], score=0),
                candidate("W2", 2, [7000], score=10),
                candidate("W2", 3, [5000], score=10),
            ),
        }

        first, _ = solve(groups)
        second, _ = solve(groups)

        self.assertEqual(first.objective_tuple, second.objective_tuple)
        self.assertEqual(first.objective_tuple[-1], (2, 2))


class WalerGlobalDynamicProgrammingTests(unittest.TestCase):
    def test_exact_dp_matches_brute_force(self):
        groups = {
            "W1": (
                candidate("W1", 1, [5000], score=10, best_score=10),
                candidate("W1", 2, [7000], score=12, best_score=10),
            ),
            "W2": (
                candidate("W2", 1, [7000, 9000], score=20, best_score=20),
                candidate("W2", 2, [9000, 3500], score=21, best_score=20),
            ),
            "W3": (
                candidate("W3", 1, [7000], score=30, best_score=30),
                candidate("W3", 2, [9000], score=34, best_score=30),
            ),
        }
        solution, diagnostics = solve(groups)

        brute_force = []
        for selected in itertools.product(*groups.values()):
            short_count = sum(item.short_count for item in selected)
            mid_count = sum(item.mid_count for item in selected)
            long_count = sum(item.long_count for item in selected)
            out_count = sum(item.out_count for item in selected)
            out_distance = sum(item.out_distance_mm for item in selected)
            *_, deviation = project_ratio_values(
                short_count,
                mid_count,
                long_count,
                TARGETS,
            )
            if not math.isfinite(deviation):
                continue
            regret = round(sum(item.local_regret for item in selected), 9)
            changed = sum(item.candidate_rank != 1 for item in selected)
            ranks = tuple(item.candidate_rank for item in selected)
            brute_force.append((
                (out_count, out_distance, deviation, regret, changed, ranks),
                selected,
            ))
        expected_objective, expected_selected = min(brute_force, key=lambda item: item[0])

        self.assertEqual(solution.objective_tuple, expected_objective)
        self.assertEqual(solution.selected_candidates, expected_selected)
        self.assertTrue(diagnostics.exact_search)
        self.assertEqual(diagnostics.pruning_type, "exact_duplicate_state_merge")

    def test_duplicate_state_merge_uses_out_distance_then_regret(self):
        groups = {
            "W1": (
                candidate("W1", 1, [3500, 5000], score=100, best_score=0),
                candidate("W1", 2, [3000, 5000], score=0, best_score=0),
            )
        }

        solution, diagnostics = solve(groups)

        self.assertEqual(solution.selected_candidates[0].candidate_rank, 1)
        self.assertGreaterEqual(diagnostics.merged_state_count, 1)

        equal_distance_groups = {
            "W1": (
                candidate("W1", 1, [3500, 5000], score=100, best_score=0),
                candidate("W1", 2, [10500, 5000], score=10, best_score=0),
            )
        }
        solution, _ = solve(equal_distance_groups)
        self.assertEqual(solution.selected_candidates[0].candidate_rank, 2)

    def test_signature_merge_preserves_different_out_distances(self):
        candidates = (
            candidate("W1", 1, [5000, 7000, 7000, 9000], score=10, best_score=10),
            candidate("W1", 2, [5000, 7000, 7000, 9000], score=20, best_score=10),
            candidate("W1", 3, [7000, 7000, 7000, 9000], score=30, best_score=10),
        )
        merged = merge_equivalent_candidates(candidates)
        self.assertEqual(tuple(item.candidate_rank for item in merged), (1, 3))

        out_candidates = (
            candidate("W1", 1, [3500, 5000]),
            candidate("W1", 2, [1000, 5000]),
        )
        self.assertEqual(len(merge_equivalent_candidates(out_candidates)), 2)

    def test_walers_with_one_candidate_are_a_normal_baseline(self):
        groups = {
            "W1": (candidate("W1", 1, [5000]),),
            "W2": (candidate("W2", 1, [7000]),),
            "W3": (candidate("W3", 1, [9000]),),
        }

        solution, _ = solve(groups)

        self.assertTrue(solution.valid)
        self.assertEqual(len(solution.selected_candidates), 3)
        self.assertEqual(solution.changed_waler_count, 0)

    def test_zero_candidate_waler_fails_without_fallback(self):
        solution, diagnostics = solve({"W1": (), "W2": (candidate("W2", 1, [5000]),)})

        self.assertFalse(solution.valid)
        self.assertEqual(diagnostics.failed_waler_ids, ("W1",))
        self.assertIn("沒有合法候選", solution.reason)

    def test_all_out_materials_fail_instead_of_dividing_by_zero(self):
        solution, diagnostics = solve({
            "W1": (candidate("W1", 1, [1000, 3500]),),
        })

        self.assertFalse(solution.valid)
        self.assertIn("沒有可計算比例", solution.reason)
        self.assertEqual(diagnostics.final_state_count, 1)


if __name__ == "__main__":
    unittest.main()
