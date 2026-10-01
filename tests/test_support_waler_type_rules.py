import unittest

from bracing_optimizer.algorithms import support


def config(from_type="Steel", to_type="Steel", *, steel_lengths=None):
    return support.SupportConfig(
        support_id="S1",
        total_length=9700,
        pile_centers=[],
        waler_centers=[],
        target_jack_region=1,
        from_waler_type=from_type,
        to_waler_type=to_type,
        steel_lengths=list([4000, 5000] if steel_lengths is None else steel_lengths),
    )


class WalerTypeLayoutGenerationTests(unittest.TestCase):
    steel = [("steel", 4000), ("steel", 5000)]

    def test_steel_waler_generates_only_adjacent_jack_and_shim(self):
        layouts = support.generate_waler_rule_layouts(
            config(), self.steel, shim=100
        )

        self.assertEqual(len(layouts), 6)
        for layout in layouts:
            kinds = [kind for kind, _length in layout]
            self.assertEqual(abs(kinds.index("jack") - kinds.index("shim")), 1)
        self.assertNotIn(
            [("steel", 4000), ("shim", 100), ("steel", 5000), ("jack", 600)],
            layouts,
        )

    def test_from_rc_waler_generates_only_contact_face_shim(self):
        layouts = support.generate_waler_rule_layouts(
            config("RC", "Steel"), self.steel, shim=100
        )

        self.assertTrue(layouts)
        self.assertTrue(all(layout[0] == ("shim", 100) for layout in layouts))
        self.assertTrue(all(layout[-1] != ("shim", 100) for layout in layouts))

    def test_to_rc_waler_generates_only_contact_face_shim(self):
        layouts = support.generate_waler_rule_layouts(
            config("Steel", "RC"), self.steel, shim=100
        )

        self.assertTrue(layouts)
        self.assertTrue(all(layout[-1] == ("shim", 100) for layout in layouts))
        self.assertTrue(all(layout[0] != ("shim", 100) for layout in layouts))

    def test_two_rc_walers_generate_either_contact_face_directly(self):
        layouts = support.generate_waler_rule_layouts(
            config("RC", "RC"), self.steel, shim=100
        )

        self.assertTrue(layouts)
        self.assertTrue(all(
            layout[0] == ("shim", 100) or layout[-1] == ("shim", 100)
            for layout in layouts
        ))

    def test_zero_length_shim_does_not_add_a_shim_piece(self):
        layouts = support.generate_waler_rule_layouts(
            config("RC", "Steel"), self.steel, shim=0
        )

        self.assertEqual(len(layouts), 3)
        self.assertTrue(all(
            all(kind != "shim" for kind, _length in layout)
            for layout in layouts
        ))


class WalerTypeScoringIsolationTests(unittest.TestCase):
    def test_waler_type_does_not_change_single_or_phase2_score(self):
        pieces = [
            ("steel", 4000),
            ("jack", support.JACK_LENGTH),
            ("steel", 5000),
        ]
        steel_plan = support.evaluate_single_support(
            config("Steel", "Steel"), pieces
        )
        rc_plan = support.evaluate_single_support(
            config("RC", "RC"), pieces
        )

        self.assertEqual(steel_plan.score, rc_plan.score)
        self.assertEqual(steel_plan.breakdown, rc_plan.breakdown)
        self.assertEqual(
            support.steel_pattern_from_plan(steel_plan),
            support.steel_pattern_from_plan(rc_plan),
        )
        self.assertEqual(
            support.make_global_solution([steel_plan], valid=True).total_score,
            support.make_global_solution([rc_plan], valid=True).total_score,
        )

    def test_project_inventory_is_the_length_combination_source(self):
        custom = config(steel_lengths=[4500])
        custom.total_length = 5200  # 4500 steel + 600 jack + 100 shim
        combinations = support.generate_length_combinations_dp(
            custom,
            max_combinations=20,
        )

        self.assertTrue(combinations)
        self.assertTrue(all(
            set(item["steel_lengths"]) <= {4500}
            for item in combinations
        ))

    def test_explicit_empty_project_inventory_does_not_use_legacy_defaults(self):
        empty_inventory = config(steel_lengths=[])
        empty_inventory.total_length = 5200

        self.assertEqual(support.configured_steel_lengths(empty_inventory), [])
        self.assertEqual(
            support.generate_length_combinations_dp(
                empty_inventory,
                max_combinations=20,
            ),
            [],
        )

    def test_inventory_lengths_change_candidate_cache_but_waler_type_is_not_a_score_rule(self):
        steel_config = config("Steel", "Steel", steel_lengths=[4000, 5000])
        rc_config = config("RC", "Steel", steel_lengths=[4000, 5000])
        custom_inventory = config("Steel", "Steel", steel_lengths=[4500])
        kwargs = dict(
            max_length_combinations=10,
            min_candidates=10,
            beam_width=10,
            max_layouts_per_combo=10,
        )

        steel_key = support.build_support_candidate_cache_key(steel_config, **kwargs)
        rc_key = support.build_support_candidate_cache_key(rc_config, **kwargs)
        custom_key = support.build_support_candidate_cache_key(custom_inventory, **kwargs)

        self.assertNotEqual(steel_key, rc_key)
        self.assertNotEqual(steel_key, custom_key)
        single_score_section = dict(steel_key)["single_score_rules"]
        self.assertNotIn("waler", repr(single_score_section).lower())


class SupportShimValidationCharacterizationTests(unittest.TestCase):
    @staticmethod
    def _case_config(
        support_id,
        total_length,
        *,
        from_type="Steel",
        to_type="Steel",
        steel_lengths=(5000,),
        pile_centers=(),
        waler_centers=(),
    ):
        return support.SupportConfig(
            support_id=support_id,
            total_length=total_length,
            pile_centers=list(pile_centers),
            waler_centers=list(waler_centers),
            target_jack_region=1,
            from_waler_type=from_type,
            to_waler_type=to_type,
            steel_lengths=list(steel_lengths),
        )

    def test_existing_invalid_candidate_scores_are_exact_characterization(self):
        cases = [
            (
                "jack_count",
                self._case_config("J", 10100),
                [("steel", 5000), ("steel", 5000)],
                1006600.0,
                {
                    "short_penalty": 0.0,
                    "joint_penalty": 1200.0,
                    "gap_penalty": 400.0,
                    "jack_edge_penalty": 5000.0,
                    "invalid_penalty": 1000000.0,
                },
            ),
            (
                "multi_shim",
                self._case_config(
                    "M",
                    10880,
                    from_type="RC",
                    to_type="RC",
                ),
                [
                    ("shim", 100),
                    ("steel", 5000),
                    ("jack", 600),
                    ("steel", 5000),
                    ("shim", 100),
                ],
                4800.0,
                {
                    "short_penalty": 0.0,
                    "joint_penalty": 4800.0,
                    "gap_penalty": 0.0,
                    "jack_edge_penalty": 0.0,
                    "invalid_penalty": 0.0,
                },
            ),
            (
                "forbidden_joint",
                self._case_config(
                    "F",
                    6680,
                    steel_lengths=(1000, 5000),
                ),
                [("steel", 1000), ("jack", 600), ("steel", 5000)],
                1215400.0,
                {
                    "short_penalty": 8000.0,
                    "joint_penalty": 2400.0,
                    "gap_penalty": 0.0,
                    "jack_edge_penalty": 5000.0,
                    "invalid_penalty": 1200000.0,
                },
            ),
            (
                "steel_length",
                self._case_config(
                    "S",
                    10180,
                    steel_lengths=(4000, 5000),
                ),
                [("steel", 4500), ("jack", 600), ("steel", 5000)],
                1002400.0,
                {
                    "short_penalty": 0.0,
                    "joint_penalty": 2400.0,
                    "gap_penalty": 0.0,
                    "jack_edge_penalty": 0.0,
                    "invalid_penalty": 1000000.0,
                },
            ),
        ]

        plans = []
        for name, cfg, pieces, expected_score, expected_breakdown in cases:
            with self.subTest(name=name):
                plan = support.evaluate_single_support(cfg, pieces)
                self.assertEqual(plan.score, expected_score)
                self.assertEqual(plan.breakdown, expected_breakdown)
                plans.append(plan)

        self.assertEqual(
            [plan.support_id for plan in sorted(plans, key=lambda item: item.score)],
            ["M", "S", "J", "F"],
        )

    def test_shim_count_and_placement_matrix(self):
        cases = [
            (
                "no_shim",
                self._case_config("none", 9680, steel_lengths=(4000, 5000)),
                [("steel", 4000), ("jack", 600), ("steel", 5000)],
                True,
                "",
            ),
            (
                "steel_adjacent",
                self._case_config("steel-ok", 9780, steel_lengths=(4000, 5000)),
                [
                    ("steel", 4000),
                    ("shim", 100),
                    ("jack", 600),
                    ("steel", 5000),
                ],
                True,
                "",
            ),
            (
                "steel_separated",
                self._case_config("steel-bad", 9780, steel_lengths=(4000, 5000)),
                [
                    ("shim", 100),
                    ("steel", 4000),
                    ("jack", 600),
                    ("steel", 5000),
                ],
                False,
                "Shim 位置",
            ),
            (
                "from_rc",
                self._case_config(
                    "from-rc",
                    9780,
                    from_type="RC",
                    steel_lengths=(4000, 5000),
                ),
                [
                    ("shim", 100),
                    ("steel", 4000),
                    ("jack", 600),
                    ("steel", 5000),
                ],
                True,
                "",
            ),
            (
                "to_rc",
                self._case_config(
                    "to-rc",
                    9780,
                    to_type="RC",
                    steel_lengths=(4000, 5000),
                ),
                [
                    ("steel", 4000),
                    ("jack", 600),
                    ("steel", 5000),
                    ("shim", 100),
                ],
                True,
                "",
            ),
            (
                "both_rc",
                self._case_config(
                    "both-rc",
                    9780,
                    from_type="RC",
                    to_type="RC",
                    steel_lengths=(4000, 5000),
                ),
                [
                    ("steel", 4000),
                    ("jack", 600),
                    ("steel", 5000),
                    ("shim", 100),
                ],
                True,
                "",
            ),
        ]

        for name, cfg, pieces, expected_valid, reason_part in cases:
            with self.subTest(name=name):
                plan = support.evaluate_single_support(cfg, pieces)
                self.assertEqual(plan.valid, expected_valid, plan.reason)
                if reason_part:
                    self.assertIn(reason_part, plan.reason)

    def test_multiple_nonzero_shims_report_only_count_without_score_change(self):
        cfg = self._case_config(
            "M",
            10880,
            from_type="RC",
            to_type="RC",
        )
        pieces = [
            ("shim", 100),
            ("steel", 5000),
            ("jack", 600),
            ("steel", 5000),
            ("shim", 100),
        ]

        plan = support.evaluate_single_support(cfg, pieces)

        self.assertFalse(plan.valid)
        self.assertEqual(plan.reason, "非零 Shim 數量超過 1")
        self.assertEqual(plan.score, 4800.0)
        self.assertEqual(plan.breakdown["invalid_penalty"], 0.0)

    def test_missing_blank_and_unknown_waler_types_use_steel_rules(self):
        pieces = [
            ("shim", 100),
            ("steel", 4000),
            ("jack", 600),
            ("steel", 5000),
        ]

        for raw_type in (None, "", "mystery"):
            with self.subTest(raw_type=raw_type):
                cfg = self._case_config(
                    "missing-type",
                    9780,
                    from_type=raw_type,
                    steel_lengths=(4000, 5000),
                )
                plan = support.evaluate_single_support(cfg, pieces)

                self.assertFalse(plan.valid)
                self.assertIn("Shim 位置", plan.reason)
                self.assertIn("接頭落入禁止區", plan.reason)

    def test_reason_gates_do_not_change_existing_penalties(self):
        cfg = self._case_config(
            "gate",
            100,
            steel_lengths=(5000,),
            pile_centers=(5000,),
        )
        pieces = [("steel", 5000), ("steel", 4500)]

        plan = support.evaluate_single_support(cfg, pieces)

        self.assertEqual(plan.reason, "千斤頂數量不是 1")
        self.assertEqual(plan.breakdown["invalid_penalty"], 10500000.0)
        self.assertGreater(
            support.count_forbidden_piece_joints(pieces, cfg),
            0,
        )

    def test_remaining_issue_reason_order_is_stable_across_piece_order(self):
        cfg = self._case_config(
            "stable",
            20000,
            steel_lengths=(5000,),
            waler_centers=(8100,),
        )
        first = support.evaluate_single_support(
            cfg,
            [
                ("steel", 4500),
                ("shim", 100),
                ("steel", 3500),
                ("jack", 600),
            ],
        )
        second = support.evaluate_single_support(
            cfg,
            [
                ("steel", 3500),
                ("shim", 100),
                ("steel", 4500),
                ("jack", 600),
            ],
        )

        self.assertEqual(first.reason, second.reason)
        self.assertEqual(first.score, second.score)
        self.assertEqual(first.breakdown, second.breakdown)
        issue_markers = (
            "Shim 位置",
            "餘長(mm)",
            "接頭落入禁止區",
            "鋼材長度不合法: 3500",
            "鋼材長度不合法: 4500",
        )
        offsets = [first.reason.index(marker) for marker in issue_markers]
        self.assertEqual(offsets, sorted(offsets))


class TypedSupportBoundaryTests(unittest.TestCase):
    @staticmethod
    def _config(
        total_length,
        *,
        from_type="Steel",
        to_type="Steel",
        piles=(),
        walers=(),
        steel_lengths=(1000, 1600, 4000, 5000),
    ):
        return support.SupportConfig(
            support_id="boundary",
            total_length=total_length,
            pile_centers=list(piles),
            waler_centers=list(walers),
            from_waler_type=from_type,
            to_waler_type=to_type,
            steel_lengths=list(steel_lengths),
        )

    def test_terminal_shim_to_jack_is_not_an_rc_exception(self):
        cfg = self._config(7180, from_type="RC")
        pieces = [("shim", 100), ("jack", 2000), ("steel", 5000)]

        self.assertEqual(support.count_forbidden_piece_joints(pieces, cfg), 1)
        plan = support.evaluate_single_support(cfg, pieces)
        self.assertFalse(plan.valid)
        self.assertEqual(plan.score, 7400.0)
        self.assertEqual(
            plan.breakdown,
            {
                "short_penalty": 0.0,
                "joint_penalty": 2400.0,
                "gap_penalty": 0.0,
                "jack_edge_penalty": 5000.0,
                "invalid_penalty": 0.0,
            },
        )

    def test_only_terminal_shim_first_steel_boundary_is_exempt(self):
        cfg = self._config(6780, from_type="RC")
        pieces = [
            ("shim", 100),
            ("steel", 1000),
            ("jack", 600),
            ("steel", 5000),
        ]

        self.assertEqual(support.count_forbidden_piece_joints(pieces, cfg), 1)

    def test_exact_1600_boundary_is_forbidden(self):
        cfg = self._config(7280)
        pieces = [("steel", 1600), ("jack", 600), ("steel", 5000)]

        self.assertEqual(support.count_forbidden_piece_joints(pieces, cfg), 1)

    def test_rc_exception_does_not_override_column_or_beam_zones(self):
        pieces = [
            ("shim", 100),
            ("steel", 4000),
            ("jack", 600),
            ("steel", 5000),
        ]
        column = self._config(9780, from_type="RC", piles=(100,))
        beam = self._config(9780, from_type="RC", walers=(100,))

        self.assertEqual(support.count_forbidden_piece_joints(pieces, column), 1)
        self.assertEqual(support.count_forbidden_piece_joints(pieces, beam), 1)

    def test_missing_type_does_not_receive_rc_exception(self):
        cfg = self._config(9780, from_type=None)
        pieces = [
            ("shim", 100),
            ("steel", 4000),
            ("jack", 600),
            ("steel", 5000),
        ]

        self.assertEqual(support.count_forbidden_piece_joints(pieces, cfg), 1)


class RCWalerEndClearanceTests(unittest.TestCase):
    def test_from_rc_terminal_shim_ignores_only_left_end_clearance(self):
        pieces = [
            ("shim", 100),
            ("steel", 4000),
            ("jack", support.JACK_LENGTH),
            ("steel", 5000),
        ]

        rc_plan = support.evaluate_single_support(
            config("RC", "Steel"), pieces
        )
        steel_plan = support.evaluate_single_support(
            config("Steel", "Steel"), pieces
        )

        self.assertTrue(rc_plan.valid, rc_plan.reason)
        self.assertFalse(steel_plan.valid)
        self.assertIn("接頭落入禁止區", steel_plan.reason)

    def test_to_rc_terminal_shim_ignores_only_right_end_clearance(self):
        pieces = [
            ("steel", 4000),
            ("jack", support.JACK_LENGTH),
            ("steel", 5000),
            ("shim", 100),
        ]

        rc_plan = support.evaluate_single_support(
            config("Steel", "RC"), pieces
        )
        steel_plan = support.evaluate_single_support(
            config("Steel", "Steel"), pieces
        )

        self.assertTrue(rc_plan.valid, rc_plan.reason)
        self.assertFalse(steel_plan.valid)

    def test_joint_after_rc_contact_assembly_still_obeys_end_clearance(self):
        pieces = [
            ("shim", 100),
            ("jack", support.JACK_LENGTH),
            ("steel", 4000),
            ("steel", 5000),
        ]

        plan = support.evaluate_single_support(
            config("RC", "Steel"), pieces
        )

        self.assertFalse(plan.valid)
        self.assertIn("接頭落入禁止區", plan.reason)

    def test_rc_contact_shim_does_not_ignore_pile_forbidden_zone(self):
        cfg = config("RC", "Steel")
        cfg.pile_centers = [100]
        pieces = [
            ("shim", 100),
            ("steel", 4000),
            ("jack", support.JACK_LENGTH),
            ("steel", 5000),
        ]

        plan = support.evaluate_single_support(cfg, pieces)

        self.assertFalse(plan.valid)
        self.assertIn("接頭落入禁止區", plan.reason)

    def test_formal_phase1_and_phase2_run_with_rc_walers(self):
        candidate_sets = []
        for index, (from_type, to_type) in enumerate(
            (("RC", "Steel"), ("Steel", "RC"), ("RC", "RC")),
            start=1,
        ):
            cfg = support.SupportConfig(
                support_id=f"S{index}",
                total_length=21300,
                pile_centers=[8550, 12750],
                waler_centers=[8550, 12750],
                target_jack_region=2,
                from_waler_type=from_type,
                to_waler_type=to_type,
                steel_lengths=list(range(1000, 10001, 500)),
            )
            candidates = support.generate_single_support_candidates(
                cfg,
                min_candidates=20,
                final_candidate_count=20,
                max_length_combinations=100,
            )
            self.assertEqual(len(candidates), 20)
            self.assertTrue(all(plan.valid and not plan.reason for plan in candidates))
            candidate_sets.append(candidates)

        solution = support.build_global_solution(candidate_sets[:2])
        self.assertTrue(solution.valid, solution.reason)
        self.assertEqual(len(solution.plans), 2)


if __name__ == "__main__":
    unittest.main()
