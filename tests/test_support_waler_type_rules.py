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
