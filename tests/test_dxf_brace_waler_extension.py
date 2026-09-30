import unittest
from dataclasses import replace

from bracing_optimizer.application.project_data import ProjectDataModel
from dxf_import.brace_waler_connection import resolve_brace_waler_connection
from dxf_import.candidate_points import (
    CandidatePointBuilder,
    apply_candidate_point_selection,
    build_candidate_points,
    connect_components_to_walers,
    set_cad_engineering_line,
)
from dxf_import.dialog import build_waler_connected_member_summary
from dxf_import.models import (
    Brace,
    DXFImportResult,
    EngineeringLineCandidate,
    GeometryTolerances,
    Strut,
    Waler,
)
from dxf_import.waler_contact_adjustment import support_side_normal


def waler(identifier, start, end):
    return Waler(
        identifier,
        start,
        end,
        "WALER",
        (f"H-{identifier}",),
        ("LINE",),
        "line",
        False,
        0.0,
        1.0,
    )


def brace(start=(0.0, 0.0), end=(1000.0, 0.0), **changes):
    item = Brace(
        "B1",
        start,
        end,
        "BRACE",
        ("HB",),
        ("INSERT",),
        "bim_block_whole_axis",
        True,
        300.0,
        "",
        "",
        1.0,
    )
    return replace(item, **changes) if changes else item


def brace_with_source_axis(
    start=(0.0, 0.0),
    end=(1000.0, 0.0),
    **changes,
):
    """Return a Brace that retains the recognition-supported source axis."""

    candidate = EngineeringLineCandidate(
        "B1-L1",
        "自動辨識斜撐工程線",
        start,
        end,
        "recognition",
    )
    return brace(
        start,
        end,
        line_candidates=(candidate,),
        selected_candidate_id=candidate.id,
        **changes,
    )


def import_result(*, walers, braces, messages=()):
    return DXFImportResult(
        source_path="synthetic.dxf",
        layer_names=("WALER", "BRACE"),
        selected_layers={"waler": ("WALER",), "brace": ("BRACE",)},
        layer_info=(),
        walers=tuple(walers),
        struts=(),
        braces=tuple(braces),
        entity_debug=(),
        messages=tuple(messages),
        source_entity_counts={},
        layer_classification={"WALER": "waler", "BRACE": "brace"},
    )


class ExistingDirectBraceConnectionTests(unittest.TestCase):
    def test_direct_connection_snaps_within_existing_tolerance(self):
        walers = (
            waler("W1", (-100.0, -500.0), (-100.0, 500.0)),
            waler("W2", (1100.0, -500.0), (1100.0, 500.0)),
        )
        _struts, braces, messages = connect_components_to_walers(
            (), (brace(),), walers
        )
        self.assertEqual((braces[0].from_waler, braces[0].to_waler), ("W1", "W2"))
        self.assertEqual((braces[0].start, braces[0].end), ((-100.0, 0.0), (1100.0, 0.0)))
        self.assertFalse({m.code for m in messages} & {"BRACE_NOT_CONNECTED", "BRACE_ONE_END_NOT_CONNECTED"})

    def test_existing_one_and_zero_end_failures_are_characterized(self):
        _s, one, one_messages = connect_components_to_walers(
            (), (brace(),), (waler("W1", (-100.0, -500.0), (-100.0, 500.0)),)
        )
        self.assertEqual((one[0].from_waler, one[0].to_waler), ("W1", ""))
        self.assertIn("BRACE_ONE_END_NOT_CONNECTED", {m.code for m in one_messages})

        _s, none, none_messages = connect_components_to_walers((), (brace(),), ())
        self.assertEqual((none[0].from_waler, none[0].to_waler), ("", ""))
        self.assertIn("BRACE_NOT_CONNECTED", {m.code for m in none_messages})

    def test_existing_direct_ambiguity_warns_and_uses_nearest(self):
        walers = (
            waler("W1", (-100.0, -500.0), (-100.0, 500.0)),
            waler("W2", (-110.0, -500.0), (-110.0, 500.0)),
        )
        _s, connected, messages = connect_components_to_walers((), (brace(),), walers)
        self.assertEqual(connected[0].from_waler, "W1")
        self.assertIn("AMBIGUOUS_WALER_CONNECTION", {m.code for m in messages})

    def test_atomic_replay_rederives_direct_identities_and_rejects_ambiguity(self):
        walers = (
            waler("W1", (-100.0, -500.0), (-100.0, 500.0)),
            waler("W1_DUP", (-100.0, -500.0), (-100.0, 500.0)),
            waler("W2", (1100.0, -500.0), (1100.0, 500.0)),
        )
        original = brace(from_waler="W1", to_waler="W2")
        staged = build_candidate_points(
            import_result(walers=walers, braces=(original,))
        )
        target = staged.braces[0]

        replayed = apply_candidate_point_selection(
            staged,
            target.id,
            target.selected_start_point_id,
            target.selected_end_point_id,
        )
        result = replayed.braces[0]

        self.assertEqual((result.from_waler, result.to_waler), ("", ""))
        self.assertFalse(result.has_formal_connection)
        self.assertEqual(result.selected_start_point_id, "")
        self.assertEqual(result.selected_end_point_id, "")
        ambiguity = next(
            message
            for message in replayed.messages
            if message.code == "AMBIGUOUS_WALER_CONNECTION"
        )
        self.assertEqual(ambiguity.severity, "error")
        self.assertTrue(
            {"H-W1", "H-W1_DUP", "HB"}.issubset(ambiguity.source_handles)
        )


class BraceCandidatePointAuthorityTests(unittest.TestCase):
    def test_unresolved_brace_keeps_source_evidence_without_recommendation(self):
        walers = (
            waler("W1", (-100.0, -500.0), (-100.0, 500.0)),
            waler("W2", (1100.0, -500.0), (1100.0, 500.0)),
        )

        unresolved = build_candidate_points(
            import_result(walers=walers, braces=(brace(),))
        ).braces[0]
        formal = build_candidate_points(
            import_result(
                walers=walers,
                braces=(brace(from_waler="W1", to_waler="W2"),),
            )
        ).braces[0]

        self.assertEqual(unresolved.recommended_start_point_id, "")
        self.assertEqual(unresolved.recommended_end_point_id, "")
        self.assertEqual(unresolved.selected_start_point_id, "")
        self.assertEqual(unresolved.selected_end_point_id, "")
        self.assertTrue(unresolved.candidate_points)
        self.assertFalse(any(point.recommended_for for point in unresolved.candidate_points))
        self.assertFalse(
            any(
                point.point_type
                in {"waler_intersection", "extended_axis_waler_intersection"}
                for point in unresolved.candidate_points
            )
        )
        self.assertTrue(formal.recommended_start_point_id)
        self.assertTrue(formal.recommended_end_point_id)

    def test_project_rows_use_the_single_formal_brace_predicate(self):
        walers = (
            waler("W1", (-100.0, -500.0), (-100.0, 500.0)),
            waler("W2", (1100.0, -500.0), (1100.0, 500.0)),
        )
        formal = brace(from_waler="W1", to_waler="W2")
        unresolved = replace(brace(), id="B2", source_handles=("HB2",))
        result = import_result(walers=walers, braces=(formal, unresolved))

        rows = result.to_project_rows()

        self.assertEqual(len(rows["braces"]), 1)
        self.assertEqual(rows["braces"][0]["FromWaler"], "W1")
        self.assertEqual(rows["braces"][0]["ToWaler"], "W2")

    def test_partial_defensive_brace_is_excluded_from_review_and_waler_evidence(self):
        selected_waler = waler("W1", (-100.0, -500.0), (-100.0, 500.0))
        partial = brace(from_waler="W1", to_waler="")
        result = import_result(walers=(selected_waler,), braces=(partial,))

        summary = build_waler_connected_member_summary(result, "W1")
        normal = support_side_normal(selected_waler, (), (partial,))
        rows = result.to_project_rows()

        self.assertEqual(summary.brace_ids, ())
        self.assertIsNone(normal)
        self.assertEqual(rows["braces"], [])


class PureBraceWalerResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tolerances = GeometryTolerances()

    def test_two_outward_extensions_resolve_finite_walers(self):
        result = resolve_brace_waler_connection(
            brace(),
            (
                waler("W1", (-500.0, -100.0), (-500.0, 100.0)),
                waler("W2", (1500.0, -100.0), (1500.0, 100.0)),
            ),
            self.tolerances,
        )
        self.assertEqual((result.start.status, result.end.status), ("axis_extension", "axis_extension"))
        self.assertEqual((result.start.waler_id, result.end.waler_id), ("W1", "W2"))
        self.assertEqual((result.start.adopted_point, result.end.adopted_point), ((-500.0, 0.0), (1500.0, 0.0)))

    def test_direct_and_axis_extension_distance_boundaries_are_distinct(self):
        direct = resolve_brace_waler_connection(
            brace(),
            (waler("W1", (-250.0, -100.0), (-250.0, 100.0)),),
            self.tolerances,
        )
        self.assertEqual((direct.start.status, direct.start.waler_id), ("direct", "W1"))

        extended = resolve_brace_waler_connection(
            brace(),
            (
                waler("W1", (-300.0, -100.0), (-300.0, 100.0)),
                waler("W2", (1600.0, -100.0), (1600.0, 100.0)),
            ),
            self.tolerances,
        )
        self.assertEqual(
            (extended.start.status, extended.start.extension_distance),
            ("axis_extension", 300.0),
        )
        self.assertEqual(
            (extended.end.status, extended.end.extension_distance),
            ("axis_extension", 600.0),
        )

        over_limit = resolve_brace_waler_connection(
            brace(),
            (waler("W1", (-600.001, -100.0), (-600.001, 100.0)),),
            self.tolerances,
        )
        self.assertEqual(over_limit.start.status, "missing")
        self.assertEqual(over_limit.start.adopted_point, (0.0, 0.0))

    def test_direct_precedes_extension_and_manual_disables_extension(self):
        walers = (
            waler("W1", (-100.0, -100.0), (-100.0, 100.0)),
            waler("W2", (-500.0, -100.0), (-500.0, 100.0)),
            waler("W3", (1500.0, -100.0), (1500.0, 100.0)),
        )
        automatic = resolve_brace_waler_connection(brace(), walers, self.tolerances)
        self.assertEqual((automatic.start.status, automatic.start.waler_id), ("direct", "W1"))
        self.assertEqual((automatic.end.status, automatic.end.waler_id), ("axis_extension", "W3"))
        manual = resolve_brace_waler_connection(
            brace(selection_source="manual_candidate_points"), walers, self.tolerances
        )
        self.assertEqual((manual.start.status, manual.end.status), ("direct", "missing"))

    def test_infinite_waler_line_and_inward_intersection_are_rejected(self):
        outside_segment = waler("W1", (-500.0, 200.0), (-500.0, 400.0))
        inward = waler("W2", (500.0, -100.0), (500.0, 100.0))
        result = resolve_brace_waler_connection(
            brace(), (outside_segment, inward), self.tolerances
        )
        self.assertEqual((result.start.status, result.end.status), ("missing", "missing"))

    def test_nearest_waler_wins_and_close_runner_up_is_ambiguous(self):
        nearest = waler("W1", (-500.0, -100.0), (-500.0, 100.0))
        farther = waler("W2", (-800.0, -100.0), (-800.0, 100.0))
        result = resolve_brace_waler_connection(brace(), (farther, nearest), self.tolerances)
        self.assertEqual((result.start.status, result.start.waler_id), ("axis_extension", "W1"))

        close = waler("W3", (-510.0, -100.0), (-510.0, 100.0))
        ambiguous = resolve_brace_waler_connection(
            brace(), (close, nearest), self.tolerances
        )
        self.assertEqual(ambiguous.start.status, "ambiguous")
        self.assertEqual(set(ambiguous.start.competing_waler_ids), {"W1", "W3"})

    def test_only_candidates_within_axis_extension_limit_participate_in_ambiguity(self):
        within_limit = resolve_brace_waler_connection(
            brace(),
            (
                waler("W1", (-575.0, -100.0), (-575.0, 100.0)),
                waler("W2", (-590.0, -100.0), (-590.0, 100.0)),
            ),
            self.tolerances,
        )
        self.assertEqual(within_limit.start.status, "ambiguous")

        over_limit_runner_up = resolve_brace_waler_connection(
            brace(),
            (
                waler("W1", (-590.0, -100.0), (-590.0, 100.0)),
                waler("W2", (-605.0, -100.0), (-605.0, 100.0)),
            ),
            self.tolerances,
        )
        self.assertEqual(
            (
                over_limit_runner_up.start.status,
                over_limit_runner_up.start.waler_id,
            ),
            ("axis_extension", "W1"),
        )

    def test_same_waler_and_zero_length_are_reported(self):
        crossing = waler("W1", (-100.0, 0.0), (1100.0, 0.0))
        same = resolve_brace_waler_connection(brace(), (crossing,), self.tolerances)
        self.assertTrue(same.same_waler)
        zero = resolve_brace_waler_connection(
            brace(end=(0.0, 0.0)), (waler("W2", (500.0, -10.0), (500.0, 10.0)),), self.tolerances
        )
        self.assertEqual((zero.start.status, zero.end.status), ("missing", "missing"))

    def test_start_end_waler_order_and_segment_direction_are_deterministic(self):
        walers = (
            waler("W1", (-500.0, -100.0), (-500.0, 100.0)),
            waler("W2", (1500.0, -100.0), (1500.0, 100.0)),
        )
        forward = resolve_brace_waler_connection(brace(), walers, self.tolerances)
        reversed_result = resolve_brace_waler_connection(
            brace(start=(1000.0, 0.0), end=(0.0, 0.0)),
            tuple(replace(item, start=item.end, end=item.start, world_start=item.end, world_end=item.start) for item in reversed(walers)),
            self.tolerances,
        )
        self.assertEqual(
            {(forward.start.waler_id, forward.start.adopted_point), (forward.end.waler_id, forward.end.adopted_point)},
            {(reversed_result.start.waler_id, reversed_result.start.adopted_point), (reversed_result.end.waler_id, reversed_result.end.adopted_point)},
        )

    def test_equivalent_floating_point_geometry_keeps_the_same_resolution(self):
        exact = resolve_brace_waler_connection(
            brace(),
            (waler("W1", (-500.3, -100.0), (-500.3, 100.0)),),
            self.tolerances,
        )
        arithmetically_equivalent = resolve_brace_waler_connection(
            brace(),
            (
                waler(
                    "W1",
                    (-500.1 - 0.2, 100.0),
                    (-500.1 - 0.2, -100.0),
                ),
            ),
            self.tolerances,
        )
        self.assertEqual(
            (exact.start.status, exact.start.waler_id),
            (
                arithmetically_equivalent.start.status,
                arithmetically_equivalent.start.waler_id,
            ),
        )
        self.assertAlmostEqual(
            exact.start.adopted_point[0],
            arithmetically_equivalent.start.adopted_point[0],
        )
        self.assertAlmostEqual(
            exact.start.adopted_point[1],
            arithmetically_equivalent.start.adopted_point[1],
        )

    def test_strut_is_not_part_of_pure_brace_contract(self):
        member = Strut(
            "S1", (0.0, 0.0), (1000.0, 0.0), "STRUT", ("HS",), ("LINE",),
            "line", False, 0.0, "", "", 1.0,
        )
        _struts, _braces, messages = connect_components_to_walers(
            (member,), (), (waler("W1", (-500.0, -100.0), (-500.0, 100.0)),)
        )
        self.assertIn("STRUT_NOT_CONNECTED", {m.code for m in messages})


class FormalBraceConnectionTests(unittest.TestCase):
    def test_two_extensions_commit_formal_endpoints_and_info_diagnostics(self):
        walers = (
            waler("W1", (-500.0, -100.0), (-500.0, 100.0)),
            waler("W2", (1500.0, -100.0), (1500.0, 100.0)),
        )
        _struts, connected, messages = connect_components_to_walers(
            (), (brace(),), walers
        )
        member = connected[0]
        self.assertEqual((member.from_waler, member.to_waler), ("W1", "W2"))
        self.assertEqual((member.start, member.end), ((-500.0, 0.0), (1500.0, 0.0)))
        self.assertEqual((member.world_start, member.world_end), (member.start, member.end))
        self.assertEqual((member.local_start, member.local_end), (member.start, member.end))
        codes = [message.code for message in messages]
        self.assertEqual(codes.count("BRACE_AXIS_EXTENDED_TO_WALER"), 2)
        self.assertNotIn("BRACE_NOT_CONNECTED", codes)
        self.assertNotIn("BRACE_ONE_END_NOT_CONNECTED", codes)
        extension_messages = tuple(
            message
            for message in messages
            if message.code == "BRACE_AXIS_EXTENDED_TO_WALER"
        )
        self.assertTrue(
            all("HB" in message.source_handles for message in extension_messages)
        )
        self.assertEqual(
            {handle for message in extension_messages for handle in message.source_handles},
            {"HB", "H-W1", "H-W2"},
        )

    def test_axis_ambiguity_is_blocking_without_contradictory_missing_message(self):
        walers = (
            waler("W1", (-500.0, -100.0), (-500.0, 100.0)),
            waler("W2", (-510.0, -100.0), (-510.0, 100.0)),
            waler("W3", (1500.0, -100.0), (1500.0, 100.0)),
        )
        _struts, connected, messages = connect_components_to_walers(
            (), (brace(),), walers
        )
        self.assertEqual((connected[0].from_waler, connected[0].to_waler), ("", "W3"))
        codes = {message.code for message in messages}
        self.assertIn("AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION", codes)
        self.assertNotIn("BRACE_NOT_CONNECTED", codes)
        self.assertNotIn("BRACE_ONE_END_NOT_CONNECTED", codes)

    def test_same_waler_is_blocking_without_generic_missing_message(self):
        _struts, connected, messages = connect_components_to_walers(
            (),
            (brace(),),
            (waler("W1", (-100.0, 0.0), (1100.0, 0.0)),),
        )
        self.assertEqual((connected[0].from_waler, connected[0].to_waler), ("W1", "W1"))
        codes = {message.code for message in messages}
        self.assertIn("BRACE_SAME_WALER_CONNECTION", codes)
        self.assertNotIn("BRACE_NOT_CONNECTED", codes)
        self.assertNotIn("BRACE_ONE_END_NOT_CONNECTED", codes)

    def test_manual_brace_keeps_direct_connection_but_is_not_extended(self):
        walers = (
            waler("W1", (-100.0, -100.0), (-100.0, 100.0)),
            waler("W2", (1500.0, -100.0), (1500.0, 100.0)),
        )
        _struts, connected, messages = connect_components_to_walers(
            (),
            (brace(selection_source="manual_candidate_points"),),
            walers,
        )
        self.assertEqual((connected[0].from_waler, connected[0].to_waler), ("W1", ""))
        self.assertEqual(connected[0].end, (1000.0, 0.0))
        codes = {message.code for message in messages}
        self.assertIn("BRACE_ONE_END_NOT_CONNECTED", codes)
        self.assertNotIn("BRACE_AXIS_EXTENDED_TO_WALER", codes)

    def test_over_limit_endpoint_preserves_source_and_blocks_import(self):
        walers = (
            waler("W1", (-100.0, -100.0), (-100.0, 100.0)),
            waler("W2", (1600.1, -100.0), (1600.1, 100.0)),
        )
        _struts, connected, messages = connect_components_to_walers(
            (),
            (brace_with_source_axis(),),
            walers,
        )
        member = connected[0]
        self.assertEqual((member.from_waler, member.to_waler), ("W1", ""))
        self.assertEqual((member.start, member.end), ((-100.0, 0.0), (1000.0, 0.0)))
        codes = [message.code for message in messages]
        self.assertNotIn("BRACE_AXIS_EXTENDED_TO_WALER", codes)
        self.assertIn("BRACE_ONE_END_NOT_CONNECTED", codes)
        self.assertFalse(
            import_result(walers=walers, braces=connected, messages=messages).can_import
        )

    def test_candidate_points_use_source_axis_and_exclude_over_limit_intersections(self):
        walers = (
            waler("W0", (-601.1, -100.0), (-601.1, 100.0)),
            waler("W1", (-500.0, -100.0), (-500.0, 100.0)),
            waler("W3", (-600.0, -100.0), (-600.0, 100.0)),
            waler("W2", (1500.0, -100.0), (1500.0, 100.0)),
        )
        _struts, connected, _messages = connect_components_to_walers(
            (), (brace_with_source_axis(),), walers
        )
        built = CandidatePointBuilder((), walers, GeometryTolerances()).build(
            connected[0]
        )
        selected_start = next(
            point
            for point in built.candidate_points
            if point.id == built.selected_start_point_id
        )
        selected_end = next(
            point
            for point in built.candidate_points
            if point.id == built.selected_end_point_id
        )
        self.assertEqual(
            (selected_start.world_point, selected_end.world_point),
            (built.start, built.end),
        )
        self.assertEqual(
            set(selected_start.source_handles),
            {"HB", "H-W1"},
        )
        boundary = next(
            point
            for point in built.candidate_points
            if point.world_point == (-600.0, 0.0)
        )
        self.assertEqual(boundary.point_type, "extended_axis_waler_intersection")
        self.assertEqual(set(boundary.source_handles), {"HB", "H-W3"})
        self.assertNotIn(
            (-601.1, 0.0),
            {point.world_point for point in built.candidate_points},
        )

    def test_candidate_mutation_rebuilds_connection_messages_without_stale_extension(self):
        walers = (
            waler("W1", (-500.0, -100.0), (-500.0, 100.0)),
            waler("W2", (1500.0, -100.0), (1500.0, 100.0)),
        )
        _struts, connected, connection_messages = connect_components_to_walers(
            (), (brace(),), walers
        )
        prepared = build_candidate_points(
            import_result(
                walers=walers,
                braces=connected,
                messages=connection_messages,
            )
        )
        member = prepared.braces[0]
        rebuilt = apply_candidate_point_selection(
            prepared,
            member.id,
            member.selected_start_point_id,
            member.selected_end_point_id,
        )
        codes = [message.code for message in rebuilt.messages]
        self.assertNotIn("BRACE_AXIS_EXTENDED_TO_WALER", codes)
        self.assertEqual(codes.count("MANUAL_POINT_SELECTION"), 1)
        self.assertEqual(
            (rebuilt.braces[0].from_waler, rebuilt.braces[0].to_waler),
            ("W1", "W2"),
        )

    def test_cad_manual_line_uses_direct_snap_but_never_auto_extension(self):
        walers = (
            waler("W1", (-500.0, -100.0), (-500.0, 100.0)),
            waler("W2", (1500.0, -100.0), (1500.0, 100.0)),
        )
        _struts, connected, connection_messages = connect_components_to_walers(
            (), (brace(),), walers
        )
        prepared = build_candidate_points(
            import_result(
                walers=walers,
                braces=connected,
                messages=connection_messages,
            )
        )
        updated = set_cad_engineering_line(
            prepared,
            "B1",
            (-300.0, 0.0),
            (1300.0, 0.0),
        )
        member = updated.braces[0]
        self.assertEqual(member.selection_source, "cad_manual")
        self.assertEqual((member.start, member.end), ((-500.0, 0.0), (1500.0, 0.0)))
        codes = [message.code for message in updated.messages]
        self.assertEqual(codes.count("CAD_MANUAL_LINE_SELECTION"), 1)
        self.assertNotIn("BRACE_AXIS_EXTENDED_TO_WALER", codes)

    def test_extended_brace_project_row_round_trips_without_schema_change(self):
        walers = (
            waler("W1", (-500.0, -100.0), (-500.0, 100.0)),
            waler("W2", (1500.0, -100.0), (1500.0, 100.0)),
        )
        _struts, connected, messages = connect_components_to_walers(
            (), (brace(),), walers
        )
        result = import_result(walers=walers, braces=connected, messages=messages)
        rows = result.to_project_rows()
        self.assertEqual(
            set(rows["braces"][0]),
            {"BraceID", "FromWaler", "ToWaler", "StartX", "StartY", "EndX", "EndY"},
        )
        self.assertEqual(
            rows["braces"][0],
            {
                "BraceID": "B1",
                "FromWaler": "W1",
                "ToWaler": "W2",
                "StartX": -500.0,
                "StartY": 0.0,
                "EndX": 1500.0,
                "EndY": 0.0,
            },
        )
        project = ProjectDataModel(
            walers=rows["walers"],
            struts=rows["struts"],
            braces=rows["braces"],
        )
        restored = ProjectDataModel.from_case_data(project.to_case_data())
        self.assertEqual(restored.braces, project.braces)


if __name__ == "__main__":
    unittest.main()
