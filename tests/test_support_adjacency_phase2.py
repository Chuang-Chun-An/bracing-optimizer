import unittest

from bracing_optimizer.algorithms import support


def plan(
    support_id,
    *,
    pieces=None,
    jack_center=1000,
    jack_region_id=1,
    score=10,
    group="",
    piles=None,
):
    return support.SupportPlan(
        support_id=support_id,
        pieces=list(pieces or [("steel", 4000), ("jack", 600)]),
        joints=[4000],
        gap=0,
        jack_center=jack_center,
        jack_region_id=jack_region_id,
        score=score,
        valid=True,
        pile_centers=list(piles or []),
        shared_layout_group=group,
    )


def normal_unit(unit_id, item):
    return support.SupportUnitCandidate(
        unit_id=unit_id,
        member_ids=(item.support_id,),
        plans=(item,),
        jack_center=item.jack_center,
        jack_region_id=item.jack_region_id,
    )


class SupportUnitAssemblyTests(unittest.TestCase):
    def test_phase1_signature_multiplicity_is_an_invariant_failure(self):
        first = plan("S1")
        duplicate = plan("S1", score=20)

        with self.assertRaises(support.SupportUnitAssemblyError) as caught:
            support.assemble_support_unit_candidates(
                "S1",
                {"S1": [first, duplicate]},
                require_shared_layout=False,
            )

        self.assertEqual(
            caught.exception.code,
            "PHASE1_SHARED_SIGNATURE_NOT_UNIQUE",
        )

    def test_shared_assembly_keeps_every_common_signature_without_pruning(self):
        layout_a = [("steel", 4000), ("jack", 600)]
        layout_b = [("jack", 600), ("steel", 4000)]
        candidates = support.assemble_support_unit_candidates(
            "G1",
            {
                "S1": [
                    plan("S1", pieces=layout_a, group="G1", score=10),
                    plan("S1", pieces=layout_b, group="G1", score=20),
                ],
                "S2": [
                    plan("S2", pieces=layout_a, group="G1", score=30),
                    plan("S2", pieces=layout_b, group="G1", score=40),
                ],
            },
            require_shared_layout=True,
        )

        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(len(candidate.plans) == 2 for candidate in candidates))
        self.assertEqual(
            sorted(sum(item.score for item in candidate.plans) for candidate in candidates),
            [40, 60],
        )

    def test_shared_region_uses_shared_station_and_merged_piles(self):
        first = plan(
            "S1", group="G1", jack_center=5000, jack_region_id=9,
            piles=[3000],
        )
        second = plan(
            "S2", group="G1", jack_center=5000, jack_region_id=8,
            piles=[7000],
        )

        forward = support.assemble_support_unit_candidates(
            "G1", {"S1": [first], "S2": [second]},
            require_shared_layout=True,
        )[0]
        reversed_lanes = support.assemble_support_unit_candidates(
            "G1", {"S2": [second], "S1": [first]},
            require_shared_layout=True,
        )[0]

        self.assertEqual(forward.jack_center, 5000)
        self.assertEqual(forward.jack_region_id, 2)
        self.assertEqual(reversed_lanes.jack_region_id, 2)
        self.assertFalse(hasattr(forward, "representative_length"))

    def test_shared_jack_mismatch_is_not_resolved_by_lane_order(self):
        first = plan("S1", group="G1", jack_center=1000)
        second = plan("S2", group="G1", jack_center=1200)

        with self.assertRaises(support.SupportUnitAssemblyError) as caught:
            support.assemble_support_unit_candidates(
                "G1", {"S1": [first], "S2": [second]},
                require_shared_layout=True,
            )

        self.assertEqual(caught.exception.code, "SHARED_JACK_INVARIANT_VIOLATION")
        self.assertEqual(caught.exception.jack_centers, (1000.0, 1200.0))


class SupportUnitPairTests(unittest.TestCase):
    def test_spacing_boundary_and_region_weight_are_unchanged(self):
        first = normal_unit("U1", plan("S1", jack_center=1000, jack_region_id=1))
        below = normal_unit("U2", plan("S2", jack_center=1499, jack_region_id=2))
        boundary = normal_unit("U2", plan("S2", jack_center=1500, jack_region_id=2))

        rejected = support.evaluate_support_unit_pair(first, below)
        accepted = support.evaluate_support_unit_pair(first, boundary)

        self.assertFalse(rejected.valid)
        self.assertTrue(accepted.valid)
        self.assertEqual(accepted.distance, 500)
        self.assertEqual(
            accepted.region_penalty,
            support.SUPPORT_JACK_REGION_PENALTY_WEIGHT,
        )

    def test_non_adjacent_units_are_not_compared(self):
        units = [
            normal_unit("U1", plan("S1", jack_center=0)),
            normal_unit("U2", plan("S2", jack_center=600)),
            normal_unit("U3", plan("S3", jack_center=0)),
        ]

        solution = support.build_global_solution([[item] for item in units])

        self.assertTrue(solution.valid)
        self.assertEqual(solution.min_jack_distance, 600)

    def test_shared_external_boundaries_are_counted_once(self):
        normal_a = normal_unit(
            "A", plan("A", jack_center=1000, jack_region_id=1)
        )
        shared = support.assemble_support_unit_candidates(
            "G1",
            {
                "G1-A": [plan(
                    "G1-A", group="G1", jack_center=2000,
                    jack_region_id=9, piles=[1500],
                )],
                "G1-B": [plan(
                    "G1-B", group="G1", jack_center=2000,
                    jack_region_id=8, piles=[1500],
                )],
            },
            require_shared_layout=True,
        )[0]
        normal_b = normal_unit(
            "B", plan("B", jack_center=3000, jack_region_id=3)
        )

        solution = support.build_global_solution(
            [[normal_a], [shared], [normal_b]]
        )

        self.assertTrue(solution.valid)
        self.assertEqual(len(solution.plans), 4)
        self.assertEqual(
            solution.jack_region_penalty,
            support.SUPPORT_JACK_REGION_PENALTY_WEIGHT * 2,
        )
        self.assertEqual(solution.min_jack_distance, 1000)

    def test_single_unit_has_no_minimum_adjacent_distance(self):
        only = normal_unit("U1", plan("S1", jack_center=1000))

        solution = support.build_global_solution([[only]])

        self.assertTrue(solution.valid)
        self.assertIsNone(solution.min_jack_distance)

    def test_diagnostics_use_the_same_external_pair_set(self):
        units = [
            normal_unit("U1", plan("S1", jack_center=0)),
            normal_unit("U2", plan("S2", jack_center=600)),
            normal_unit("U3", plan("S3", jack_center=1200)),
        ]
        diagnostics = {}

        support.build_global_solution(
            [[item] for item in units],
            diagnostics_out=diagnostics,
        )

        self.assertEqual(
            [
                (item["first_unit_id"], item["second_unit_id"])
                for item in diagnostics["adjacency_pairs"]
            ],
            [("U1", "U2"), ("U2", "U3")],
        )


if __name__ == "__main__":
    unittest.main()
