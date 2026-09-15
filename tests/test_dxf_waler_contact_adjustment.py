from __future__ import annotations

from dataclasses import replace
import copy
import math
import unittest

from dxf_import.candidate_points import associate_components_to_struts
from dxf_import.geometry import circle_segment_intersection_points
from dxf_import.models import (
    Beam,
    Brace,
    Column,
    CoordinateSystem,
    CornerBrace,
    DXFImportError,
    DXFImportResult,
    EngineeringLineCandidate,
    SourceGeometry,
    Strut,
    ValidationMessage,
    Waler,
    apply_coordinate_system,
)
from dxf_import.waler_contact_adjustment import (
    _select_corner_brace_intersection,
    apply_waler_contact_adjustment,
    initialize_waler_contact_review,
    plan_waler_contact_adjustment,
    restore_waler_contact_review_from_debug,
    support_side_normal,
)


def _waler(identifier, start, end, width=350.0):
    return Waler(
        identifier, start, end, "WALER", (f"H-{identifier}",),
        ("LWPOLYLINE",), "inner_boundary_line", False, width, 0.99,
    )


def _strut(start=(5000.0, 0.0), end=(5000.0, 10000.0)):
    return Strut(
        "S1", start, end, "STRUT", ("H-S1",), ("LINE",),
        "existing_centerline", False, 350.0, "W1", "W2", 1.0,
    )


def _brace():
    return Brace(
        "B1", (3000.0, 0.0), (5000.0, 10000.0), "BRACE", ("H-B1",),
        ("LINE",), "existing_centerline", False, 200.0, "W1", "W2", 1.0,
    )


def _corner():
    return CornerBrace(
        "CB1", (4500.0, 0.0), (5000.0, 500.0), "CORNER", ("H-CB1",),
        ("INSERT",), "brace_centerline_intersections", True, 0.0, 0.99,
    )


def _column():
    return Column(
        "C1", (4900.0, 3900.0), (5100.0, 4100.0), "COLUMN", ("H-C1",),
        ("LWPOLYLINE",), "outline_centerline", True, 400.0, 0.99,
        reference_point=(5000.0, 4000.0),
        world_reference_point=(5000.0, 4000.0),
        local_reference_point=(5000.0, 4000.0),
    )


def _beam():
    return Beam(
        "BM1", (0.0, 3000.0), (10000.0, 3000.0), "BEAM", ("H-BM1",),
        ("LINE",), "existing_centerline", False, 300.0, 0.99,
        world_path=((0.0, 3000.0), (10000.0, 3000.0)),
    )


def _result(*, with_corner=True, with_auxiliary=False):
    walers = (
        _waler("W1", (0.0, 0.0), (10000.0, 0.0)),
        _waler("W2", (0.0, 10000.0), (10000.0, 10000.0)),
    )
    columns = (_column(),) if with_auxiliary else ()
    beams = (_beam(),) if with_auxiliary else ()
    struts, columns, beams, associations, messages = associate_components_to_struts(
        (_strut(),), columns, beams
    )
    result = DXFImportResult(
        source_path="C:/drawing/example.dxf",
        layer_names=("WALER", "STRUT"),
        selected_layers={"waler": ("WALER",), "strut": ("STRUT",)},
        layer_info=(),
        walers=walers,
        struts=struts,
        braces=(_brace(),),
        entity_debug=(),
        messages=messages,
        source_entity_counts={},
        columns=columns,
        beams=beams,
        corner_braces=(_corner(),) if with_corner else (),
        component_associations=associations,
        beam_crossings=tuple(crossing for beam in beams for crossing in beam.crossings),
    )
    return initialize_waler_contact_review(result)


def _minimal_result(waler, struts, braces=(), *, columns=(), beams=(), corners=()):
    result = DXFImportResult(
        source_path="C:/drawing/minimal.dxf",
        layer_names=(),
        selected_layers={},
        layer_info=(),
        walers=(waler,),
        struts=tuple(struts),
        braces=tuple(braces),
        entity_debug=(),
        messages=(),
        source_entity_counts={},
        columns=tuple(columns),
        beams=tuple(beams),
        corner_braces=tuple(corners),
    )
    return initialize_waler_contact_review(result)


def _dimensions(adopted_backfill=135.0, adopted_width=400.0):
    return {
        "original_backfill_mm": 100.0,
        "adopted_backfill_mm": adopted_backfill,
        "original_waler_width_mm": 350.0,
        "adopted_waler_width_mm": adopted_width,
    }


class CircleSegmentIntersectionTests(unittest.TestCase):
    def test_zero_tangent_two_and_clipped_intersections(self):
        self.assertEqual(circle_segment_intersection_points((0, 5), 1, (-2, 0), (2, 0)), ())
        self.assertEqual(circle_segment_intersection_points((0, 1), 1, (-2, 0), (2, 0)), ((0.0, 0.0),))
        self.assertEqual(circle_segment_intersection_points((0, 0), 1, (-2, 0), (2, 0)), ((-1.0, 0.0), (1.0, 0.0)))
        self.assertEqual(circle_segment_intersection_points((0, 0), 2, (3, 0), (4, 0)), ())
        self.assertEqual(circle_segment_intersection_points((0, 0), 0, (-1, 0), (1, 0)), ())
        self.assertEqual(circle_segment_intersection_points((0, 0), 1, (1, 0), (1, 0)), ())

    def test_two_solution_selector_uses_direction_then_blocks_a_true_tie(self):
        selected = _select_corner_brace_intersection(
            ((-1.0, 0.0), (1.0, 0.0)),
            new_waler_start=(-2.0, 0.0),
            new_waler_axis=(1.0, 0.0),
            baseline_waler_station_mm=2.0,
            baseline_direction=((0.0, 1.0), (1.0, 0.0)),
            new_hole=(0.0, 1.0),
            tolerance=1e-6,
        )
        self.assertEqual(selected, (3.0, (1.0, 0.0)))
        ambiguous = _select_corner_brace_intersection(
            ((-1.0, 0.0), (1.0, 0.0)),
            new_waler_start=(-2.0, 0.0),
            new_waler_axis=(1.0, 0.0),
            baseline_waler_station_mm=2.0,
            baseline_direction=((0.0, 1.0), (0.0, 0.0)),
            new_hole=(0.0, 1.0),
            tolerance=1e-6,
        )
        self.assertIsNone(ambiguous)


class WalerContactAdjustmentTests(unittest.TestCase):
    def test_backfill_prefills_from_waler_outer_and_continuous_wall_inner_faces(self):
        waler = replace(
            _waler("W1", (0.0, 0.0), (10000.0, 0.0)),
            line_candidates=(
                EngineeringLineCandidate(
                    "line_1", "內側線", (0.0, 0.0), (10000.0, 0.0),
                    "inner_boundary_line",
                ),
                EngineeringLineCandidate(
                    "line_2", "外側線", (0.0, -350.0),
                    (10000.0, -350.0), "recognized_boundary",
                ),
            ),
        )
        strut = replace(
            _strut((5000.0, 0.0), (5000.0, 10000.0)),
            to_waler="",
        )
        wall = SourceGeometry(
            "continuous_wall",
            "WALL-1",
            (
                (-500.0, -450.0),
                (10500.0, -450.0),
                (10500.0, -950.0),
                (-500.0, -950.0),
            ),
            True,
            "WALL",
            "LWPOLYLINE",
        )
        result = DXFImportResult(
            source_path="C:/drawing/backfill.dxf",
            layer_names=(),
            selected_layers={},
            layer_info=(),
            walers=(waler,),
            struts=(strut,),
            braces=(),
            entity_debug=(),
            messages=(),
            source_entity_counts={},
            source_geometry=(wall,),
        )
        reviewed = initialize_waler_contact_review(result)
        review = reviewed.waler_contact_reviews[0]
        self.assertEqual(review.original_backfill_mm, 100.0)
        self.assertEqual(review.adopted_backfill_mm, 100.0)
        self.assertEqual(review.waler_outer_start, (0.0, -350.0))
        self.assertEqual(review.continuous_wall_inner_start, (-500.0, -450.0))
        self.assertEqual(review.continuous_wall_source_handle, "WALL-1")
        self.assertEqual(
            review.backfill_recognition_method,
            "waler_outer_to_continuous_wall_inner",
        )

    def test_backfill_is_not_guessed_without_recognized_waler_outer_face(self):
        waler = _waler("W1", (0.0, 0.0), (10000.0, 0.0))
        strut = replace(_strut(), to_waler="")
        wall = SourceGeometry(
            "continuous_wall",
            "WALL-1",
            ((0.0, -450.0), (10000.0, -450.0)),
            False,
        )
        result = DXFImportResult(
            source_path="C:/drawing/no_outer.dxf",
            layer_names=(),
            selected_layers={},
            layer_info=(),
            walers=(waler,),
            struts=(strut,),
            braces=(),
            entity_debug=(),
            messages=(),
            source_entity_counts={},
            source_geometry=(wall,),
        )
        review = initialize_waler_contact_review(result).waler_contact_reviews[0]
        self.assertIsNone(review.original_backfill_mm)

    def test_width_prefills_and_unknown_backfill_is_not_guessed(self):
        review = _result().waler_contact_reviews[0]
        self.assertIsNone(review.original_backfill_mm)
        self.assertIsNone(review.adopted_backfill_mm)
        self.assertEqual(review.original_waler_width_mm, 350.0)
        self.assertEqual(review.adopted_waler_width_mm, 350.0)
        unknown = _minimal_result(
            _waler("W1", (0.0, 0.0), (10000.0, 0.0), 0.0),
            (replace(_strut(), to_waler=""),),
        )
        self.assertIsNone(unknown.waler_contact_reviews[0].original_waler_width_mm)
        self.assertIsNone(unknown.waler_contact_reviews[0].adopted_waler_width_mm)

    def test_support_normal_does_not_depend_on_waler_order(self):
        result = _result(with_corner=False)
        forward = support_side_normal(result.walers[0], result.struts, result.braces)
        reverse = support_side_normal(
            replace(result.walers[0], start=(10000.0, 0.0), end=(0.0, 0.0)),
            result.struts,
            result.braces,
        )
        self.assertEqual(forward, (0.0, 1.0))
        self.assertEqual(reverse, (0.0, 1.0))

    def test_plus_85_and_repeated_edit_always_use_baseline(self):
        first = apply_waler_contact_adjustment(_result(), "W1", **_dimensions())
        self.assertEqual(first.walers[0].start, (0.0, 85.0))
        second = apply_waler_contact_adjustment(
            first, "W1", **_dimensions(adopted_backfill=145.0, adopted_width=410.0)
        )
        self.assertEqual(second.walers[0].start, (0.0, 105.0))

    def test_invalid_value_and_external_baseline_change_are_blocked(self):
        result = _result()
        with self.assertRaises(DXFImportError):
            plan_waler_contact_adjustment(result, "W1", **_dimensions(adopted_width=0.0))
        changed = replace(
            result,
            walers=(
                replace(
                    result.walers[0],
                    start=(2.0, 0.0),
                    world_start=(2.0, 0.0),
                ),
                result.walers[1],
            ),
        )
        plan = plan_waler_contact_adjustment(changed, "W1", **_dimensions())
        self.assertFalse(plan.can_apply)
        self.assertIn("WALER_CONTACT_BASELINE_CHANGED", {item.code for item in plan.messages})

    def test_three_member_types_follow_distinct_geometry_rules(self):
        plan = plan_waler_contact_adjustment(_result(), "W1", **_dimensions())
        self.assertTrue(plan.can_apply, [item.message for item in plan.messages])
        strut = plan.strut_changes[0]
        self.assertEqual(strut.new_member.start, (5000.0, 85.0))
        self.assertEqual(strut.new_member.end, strut.old_member.end)
        brace = plan.brace_changes[0]
        self.assertEqual(brace.waler_station_mm, 3000.0)
        self.assertEqual(brace.new_member.start, (3000.0, 85.0))
        self.assertEqual(brace.new_member.end, brace.old_member.end)
        corner = plan.corner_brace_changes[0]
        self.assertAlmostEqual(corner.strut_hole_station_mm, 500.0)
        self.assertAlmostEqual(corner.fixed_length_mm, 500.0 * 2 ** 0.5)
        self.assertAlmostEqual(corner.new_member.end[1], 585.0)
        self.assertAlmostEqual(
            ((corner.new_member.end[0] - corner.new_member.start[0]) ** 2
             + (corner.new_member.end[1] - corner.new_member.start[1]) ** 2) ** 0.5,
            corner.fixed_length_mm,
        )
        updated_strut = plan.proposed_result.struts[0]
        self.assertEqual(updated_strut.from_brace_to_waler_start_len, 500)
        self.assertEqual(updated_strut.from_brace_to_waler_end_len, 0)
        self.assertAlmostEqual(corner.new_waler_station_mm, 4500.0)

    def test_beam_and_column_station_rebuild_uses_new_strut_origin(self):
        result = _result(with_corner=False, with_auxiliary=True)
        plan = plan_waler_contact_adjustment(result, "W1", **_dimensions())
        self.assertTrue(plan.can_apply)
        updated = plan.proposed_result.struts[0]
        self.assertAlmostEqual(updated.beam_positions[0], 2915.0)
        self.assertAlmostEqual(updated.column_positions[0], 3915.0)
        self.assertEqual(plan.changed_beam_ids, ("BM1",))
        self.assertEqual(plan.changed_column_ids, ("C1",))

    def test_preview_is_pure_and_apply_is_atomic(self):
        result = _result()
        snapshot = copy.deepcopy(result)
        plan_waler_contact_adjustment(result, "W1", **_dimensions())
        self.assertEqual(result, snapshot)
        bad_corner = replace(
            result.corner_braces[0],
            start=(0.0, 0.0),
            end=(10.0, 10.0),
            world_start=(0.0, 0.0),
            world_end=(10.0, 10.0),
        )
        bad = replace(result, corner_braces=(bad_corner,))
        with self.assertRaises(DXFImportError):
            apply_waler_contact_adjustment(bad, "W1", **_dimensions())
        self.assertEqual(bad.walers[0].start, (0.0, 0.0))

    def test_existing_blocking_validation_prevents_atomic_apply(self):
        result = _result(with_corner=False)
        result = replace(
            result,
            messages=(
                *result.messages,
                ValidationMessage("error", "EXISTING_ERROR", "existing"),
            ),
        )
        plan = plan_waler_contact_adjustment(result, "W1", **_dimensions())
        self.assertFalse(plan.can_apply)
        with self.assertRaises(DXFImportError):
            apply_waler_contact_adjustment(result, "W1", **_dimensions())

    def test_review_state_serializes_but_never_enters_project_rows(self):
        result = apply_waler_contact_adjustment(_result(), "W1", **_dimensions())
        debug = result.to_debug_dict()
        self.assertEqual(debug["waler_contact_reviews"][0]["adopted_backfill_mm"], 135.0)
        self.assertIn("corner_brace_connections", debug)
        rows = result.to_project_rows()
        self.assertNotIn("original_backfill_mm", rows["walers"][0])
        self.assertNotIn("adopted_waler_width_mm", rows["walers"][0])

    def test_local_coordinate_result_and_debug_restore(self):
        local = apply_coordinate_system(_result(), CoordinateSystem("local", 1000.0, 2000.0))
        adjusted = apply_waler_contact_adjustment(local, "W1", **_dimensions())
        self.assertEqual(adjusted.walers[0].world_start, (0.0, 85.0))
        self.assertEqual(adjusted.walers[0].local_start, (-1000.0, -1915.0))
        restored = restore_waler_contact_review_from_debug(
            _result(), adjusted.to_debug_dict()
        )
        self.assertEqual(restored.walers[0].start, (0.0, 85.0))

    def test_vertical_and_diagonal_walers_translate_along_support_side(self):
        vertical = _waler("W1", (0.0, 0.0), (0.0, 1000.0))
        vertical_strut = replace(
            _strut((0.0, 500.0), (1000.0, 500.0)), to_waler=""
        )
        vertical_result = _minimal_result(vertical, (vertical_strut,))
        vertical_plan = plan_waler_contact_adjustment(
            vertical_result, "W1", **_dimensions()
        )
        self.assertEqual(vertical_plan.new_waler.start, (85.0, 0.0))

        diagonal = _waler("W1", (0.0, 0.0), (1000.0, 1000.0))
        normal = (-2 ** -0.5, 2 ** -0.5)
        diagonal_strut = replace(
            _strut(
                (500.0, 500.0),
                (500.0 + normal[0] * 1000.0, 500.0 + normal[1] * 1000.0),
            ),
            to_waler="",
        )
        diagonal_result = _minimal_result(diagonal, (diagonal_strut,))
        diagonal_plan = plan_waler_contact_adjustment(
            diagonal_result, "W1", **_dimensions()
        )
        self.assertAlmostEqual(diagonal_plan.new_waler.start[0], normal[0] * 85.0)
        self.assertAlmostEqual(diagonal_plan.new_waler.start[1], normal[1] * 85.0)

    def test_parallel_or_outside_strut_intersection_blocks_plan(self):
        waler = _waler("W1", (0.0, 0.0), (100.0, 0.0))
        cases = (
            replace(_strut((10.0, 0.0), (90.0, 0.0)), to_waler=""),
            replace(_strut((200.0, 0.0), (200.0, 100.0)), to_waler=""),
            replace(_strut((50.0, 0.0), (50.0, 0.0)), to_waler=""),
        )
        for strut in cases:
            with self.subTest(strut=strut.start):
                result = _minimal_result(waler, (strut,))
                review = replace(
                    result.waler_contact_reviews[0], support_normal_world=(0.0, 1.0)
                )
                result = replace(result, waler_contact_reviews=(review,))
                plan = plan_waler_contact_adjustment(result, "W1", **_dimensions())
                self.assertFalse(plan.can_apply)
                self.assertIn(
                    "STRUT_WALER_INTERSECTION_FAILED",
                    {item.code for item in plan.messages},
                )

    def test_reversed_strut_updates_the_endpoint_bound_to_target_waler(self):
        waler = _waler("W1", (0.0, 0.0), (10000.0, 0.0))
        reversed_strut = replace(
            _strut((5000.0, 10000.0), (5000.0, 0.0)),
            from_waler="",
            to_waler="W1",
        )
        result = _minimal_result(waler, (reversed_strut,))
        plan = plan_waler_contact_adjustment(result, "W1", **_dimensions())
        self.assertEqual(plan.strut_changes[0].new_member.start, (5000.0, 10000.0))
        self.assertEqual(plan.strut_changes[0].new_member.end, (5000.0, 85.0))

    def test_to_waler_updates_end_and_preserves_station_from_start(self):
        base = _result(with_corner=False, with_auxiliary=True)
        top_corner = replace(
            _corner(),
            start=(4500.0, 10000.0),
            end=(5000.0, 9500.0),
            world_start=(4500.0, 10000.0),
            world_end=(5000.0, 9500.0),
        )
        result = initialize_waler_contact_review(
            replace(base, corner_braces=(top_corner,))
        )
        plan = plan_waler_contact_adjustment(result, "W2", **_dimensions())
        self.assertTrue(plan.can_apply, [item.message for item in plan.messages])
        strut = plan.proposed_result.struts[0]
        self.assertEqual(strut.start, (5000.0, 0.0))
        self.assertEqual(strut.end, (5000.0, 9915.0))
        self.assertAlmostEqual(strut.beam_positions[0], 3000.0)
        self.assertEqual(strut.to_brace_to_waler_start_len, 500)

    def test_support_side_requires_nonparallel_consistent_evidence(self):
        waler = _waler("W1", (0.0, 0.0), (1000.0, 0.0))
        parallel = replace(
            _strut((100.0, 0.0), (900.0, 0.0)), to_waler=""
        )
        self.assertIsNone(support_side_normal(waler, (parallel,), ()))
        up = replace(_strut((400.0, 0.0), (400.0, 1000.0)), to_waler="")
        down = replace(
            _strut((600.0, 0.0), (600.0, -1000.0)),
            id="S2",
            source_handles=("H-S2",),
            to_waler="",
        )
        self.assertIsNone(support_side_normal(waler, (up, down), ()))

    def test_brace_station_outside_finite_waler_blocks_plan(self):
        waler = _waler("W1", (0.0, 0.0), (1000.0, 0.0))
        strut = replace(_strut((500.0, 0.0), (500.0, 1000.0)), to_waler="")
        brace = replace(
            _brace(),
            start=(1200.0, 0.0),
            end=(500.0, 1000.0),
            world_start=(1200.0, 0.0),
            world_end=(500.0, 1000.0),
            to_waler="",
        )
        result = _minimal_result(waler, (strut,), (brace,))
        plan = plan_waler_contact_adjustment(result, "W1", **_dimensions())
        self.assertFalse(plan.can_apply)
        self.assertIn("BRACE_STATION_INVALID", {item.code for item in plan.messages})

    def test_reversed_corner_endpoint_order_keeps_explicit_connection(self):
        result = _result()
        corner = replace(
            result.corner_braces[0],
            start=(5000.0, 500.0),
            end=(4500.0, 0.0),
            world_start=(5000.0, 500.0),
            world_end=(4500.0, 0.0),
        )
        rebuilt = initialize_waler_contact_review(
            replace(result, corner_braces=(corner,))
        )
        connection = rebuilt.corner_brace_connections[0]
        self.assertEqual(connection.corner_waler_endpoint_name, "end")
        plan = plan_waler_contact_adjustment(rebuilt, "W1", **_dimensions())
        self.assertTrue(plan.can_apply)
        self.assertAlmostEqual(plan.corner_brace_changes[0].new_member.start[1], 585.0)

    def test_two_corner_braces_fill_distinct_derived_fields(self):
        result = _result()
        second = replace(
            _corner(),
            id="CB2",
            start=(5000.0, 500.0),
            end=(5500.0, 0.0),
            world_start=(5000.0, 500.0),
            world_end=(5500.0, 0.0),
            source_handles=("H-CB2",),
        )
        result = initialize_waler_contact_review(
            replace(result, corner_braces=(_corner(), second))
        )
        plan = plan_waler_contact_adjustment(result, "W1", **_dimensions())
        self.assertTrue(plan.can_apply, [item.message for item in plan.messages])
        self.assertEqual(len(plan.corner_brace_changes), 2)
        strut = plan.proposed_result.struts[0]
        self.assertEqual(strut.from_brace_to_waler_start_len, 500)
        self.assertEqual(strut.from_brace_to_waler_end_len, 500)

    def test_corner_brace_keeps_each_measured_fractional_length(self):
        for measured in (1498.7, 1501.4):
            with self.subTest(measured=measured):
                horizontal = math.sqrt(measured * measured - 500.0 * 500.0)
                corner = replace(
                    _corner(),
                    start=(5000.0 - horizontal, 0.0),
                    end=(5000.0, 500.0),
                    world_start=(5000.0 - horizontal, 0.0),
                    world_end=(5000.0, 500.0),
                )
                result = initialize_waler_contact_review(
                    replace(_result(), corner_braces=(corner,))
                )
                connection = result.corner_brace_connections[0]
                self.assertAlmostEqual(connection.fixed_length_mm, measured)
                plan = plan_waler_contact_adjustment(
                    result, "W1", **_dimensions()
                )
                self.assertAlmostEqual(
                    plan.corner_brace_changes[0].fixed_length_mm,
                    measured,
                )

    def test_ambiguous_corner_connection_and_no_circle_solution_block(self):
        waler = _waler("W1", (0.0, 0.0), (10000.0, 0.0))
        first = replace(
            _strut((4990.0, 0.0), (4990.0, 10000.0)),
            id="S1",
            to_waler="",
        )
        second = replace(
            _strut((5010.0, 0.0), (5010.0, 10000.0)),
            id="S2",
            source_handles=("H-S2",),
            to_waler="",
        )
        ambiguous = _minimal_result(waler, (first, second), corners=(_corner(),))
        self.assertEqual(ambiguous.corner_brace_connections, ())
        ambiguous_plan = plan_waler_contact_adjustment(
            ambiguous, "W1", **_dimensions()
        )
        self.assertFalse(ambiguous_plan.can_apply)
        self.assertIn(
            "CORNER_BRACE_CONNECTION_INVALID",
            {item.code for item in ambiguous_plan.messages},
        )

        result = _result()
        connection = replace(
            result.corner_brace_connections[0], fixed_length_mm=10.0
        )
        impossible = replace(result, corner_brace_connections=(connection,))
        impossible_plan = plan_waler_contact_adjustment(
            impossible, "W1", **_dimensions()
        )
        self.assertFalse(impossible_plan.can_apply)
        self.assertIn(
            "CORNER_BRACE_INTERSECTION_FAILED",
            {item.code for item in impossible_plan.messages},
        )

    def test_double_support_candidates_are_recomputed(self):
        waler = _waler("W1", (0.0, 0.0), (10000.0, 0.0))
        first = replace(_strut(), to_waler="")
        second = replace(
            _strut((6000.0, 0.0), (6000.0, 10000.0)),
            id="S2",
            source_handles=("H-S2",),
            to_waler="",
        )
        # The detector requires the same two Waler relationships, so supply a
        # remote W2 while only W1 is adjusted.
        first = replace(first, to_waler="W2")
        second = replace(second, to_waler="W2")
        result = _result(with_corner=False)
        result = initialize_waler_contact_review(
            replace(result, struts=(first, second), braces=())
        )
        plan = plan_waler_contact_adjustment(result, "W1", **_dimensions())
        self.assertTrue(plan.can_apply)
        self.assertEqual(len(plan.proposed_result.double_support_candidates), 1)
        self.assertTrue(plan.proposed_result.double_support_candidates[0].accepted)

    def test_column_loss_blocks_but_beam_loss_remains_warning(self):
        base = _result(with_corner=False)
        near_column = replace(
            _column(),
            start=(4900.0, -50.0),
            end=(5100.0, 150.0),
            reference_point=(5000.0, 50.0),
            world_reference_point=(5000.0, 50.0),
            local_reference_point=(5000.0, 50.0),
        )
        struts, columns, _beams, associations, messages = associate_components_to_struts(
            base.struts, (near_column,), ()
        )
        column_result = replace(
            base,
            struts=struts,
            columns=columns,
            component_associations=associations,
            messages=messages,
        )
        column_plan = plan_waler_contact_adjustment(
            column_result, "W1", **_dimensions()
        )
        self.assertFalse(column_plan.can_apply)
        self.assertIn("COLUMN_NOT_ASSOCIATED", {item.code for item in column_plan.messages})

        near_beam = replace(
            _beam(),
            start=(0.0, 50.0),
            end=(10000.0, 50.0),
            world_start=(0.0, 50.0),
            world_end=(10000.0, 50.0),
            world_path=((0.0, 50.0), (10000.0, 50.0)),
            local_path=((0.0, 50.0), (10000.0, 50.0)),
            path=((0.0, 50.0), (10000.0, 50.0)),
        )
        struts, _columns, beams, associations, messages = associate_components_to_struts(
            base.struts, (), (near_beam,)
        )
        beam_result = replace(
            base,
            struts=struts,
            beams=beams,
            component_associations=associations,
            messages=messages,
        )
        beam_plan = plan_waler_contact_adjustment(
            beam_result, "W1", **_dimensions(adopted_width=500.0)
        )
        self.assertTrue(beam_plan.can_apply)
        self.assertIn("BEAM_NOT_ASSOCIATED", {item.code for item in beam_plan.messages})

    def test_unaffected_manual_candidate_selection_is_preserved(self):
        result = _result(with_corner=False)
        manual_w2 = replace(
            result.walers[1], selection_source="manual_candidate_points"
        )
        result = replace(result, walers=(result.walers[0], manual_w2))
        plan = plan_waler_contact_adjustment(result, "W1", **_dimensions())
        self.assertEqual(
            plan.proposed_result.walers[1].selection_source,
            "manual_candidate_points",
        )


if __name__ == "__main__":
    unittest.main()
