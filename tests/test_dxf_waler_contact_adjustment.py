from __future__ import annotations

from dataclasses import replace
import copy
import math
import unittest
from types import SimpleNamespace

from dxf_import.candidate_points import associate_components_to_struts
from dxf_import.geometry import circle_segment_intersection_points
from dxf_import.models import (
    Beam,
    Brace,
    BraceAdjustmentBaseline,
    Column,
    CoordinateSystem,
    CornerBrace,
    DXFImportError,
    DXFImportResult,
    EngineeringLineCandidate,
    GeometryTolerances,
    SourceGeometry,
    Strut,
    ValidationMessage,
    Waler,
    apply_coordinate_system,
)
from dxf_import.review_workflow import DXFReviewWorkflow
from dxf_import.source_exclusion import (
    capture_manual_overrides,
    replay_manual_overrides,
)
from dxf_import.waler_contact_adjustment import (
    _select_corner_brace_intersection,
    BraceRigidTranslationError,
    apply_waler_contact_adjustment,
    format_adjustment_plan,
    initialize_waler_contact_review,
    plan_waler_contact_adjustment,
    restore_waler_contact_review_from_debug,
    solve_brace_rigid_translation,
    support_side_normal,
)
from dxf_import.waler_engineering_line_repair import (
    formalize_waler_engineering_line,
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
        _waler("W2", (0.0, 9500.0), (10000.0, 10500.0)),
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


class BraceRigidTranslationTests(unittest.TestCase):
    def baseline(self, start=(2.0, 0.0), end=(10.0, 4.0)):
        return BraceAdjustmentBaseline(
            "B1", ("H-B1",), start, end, "W1", "W2"
        )

    def test_nonparallel_solution_is_one_common_translation(self):
        solution = solve_brace_rigid_translation(
            self.baseline(),
            ((0.0, 0.0), (20.0, 0.0)),
            ((10.0, -10.0), (10.0, 10.0)),
            ((20.0, 3.0), (0.0, 3.0)),
            ((12.0, 10.0), (12.0, -10.0)),
        )
        self.assertEqual(solution.translation, (2.0, 3.0))
        self.assertEqual(solution.start, (4.0, 3.0))
        self.assertEqual(solution.end, (12.0, 7.0))
        self.assertEqual(
            (
                solution.end[0] - solution.start[0],
                solution.end[1] - solution.start[1],
            ),
            (8.0, 4.0),
        )
        reversed_solution = solve_brace_rigid_translation(
            BraceAdjustmentBaseline(
                "B1", ("H-B1",), (10.0, 4.0), (2.0, 0.0), "W2", "W1"
            ),
            ((10.0, 10.0), (10.0, -10.0)),
            ((20.0, 0.0), (0.0, 0.0)),
            ((12.0, -10.0), (12.0, 10.0)),
            ((0.0, 3.0), (20.0, 3.0)),
        )
        self.assertEqual(reversed_solution.translation, (2.0, 3.0))
        self.assertEqual(reversed_solution.start, solution.end)
        self.assertEqual(reversed_solution.end, solution.start)

    def test_parallel_compatible_uses_minimum_norm(self):
        baseline = self.baseline((2.0, 0.0), (8.0, 10.0))
        solution = solve_brace_rigid_translation(
            baseline,
            ((0.0, 0.0), (20.0, 0.0)),
            ((0.0, 10.0), (20.0, 10.0)),
            ((0.0, 5.0), (20.0, 5.0)),
            ((0.0, 15.0), (20.0, 15.0)),
        )
        self.assertEqual(solution.translation, (0.0, 5.0))

    def test_parallel_incompatible_fails_without_fallback(self):
        baseline = self.baseline((2.0, 0.0), (8.0, 10.0))
        with self.assertRaisesRegex(
            BraceRigidTranslationError, "不相容"
        ) as caught:
            solve_brace_rigid_translation(
                baseline,
                ((0.0, 0.0), (20.0, 0.0)),
                ((0.0, 10.0), (20.0, 10.0)),
                ((0.0, 5.0), (20.0, 5.0)),
                ((0.0, 20.0), (20.0, 20.0)),
            )
        self.assertEqual(caught.exception.reason, "parallel_incompatible")

    def test_invalid_identity_degenerate_and_outside_segment_fail(self):
        invalid = replace(self.baseline(), to_waler_id="W1")
        with self.assertRaises(BraceRigidTranslationError) as identity:
            solve_brace_rigid_translation(
                invalid,
                ((0.0, 0.0), (20.0, 0.0)),
                ((10.0, -10.0), (10.0, 10.0)),
                ((0.0, 0.0), (20.0, 0.0)),
                ((10.0, -10.0), (10.0, 10.0)),
            )
        self.assertEqual(identity.exception.reason, "identity_invalid")

        degenerate = self.baseline((0.0, 0.0), (0.0, 0.0))
        with self.assertRaises(BraceRigidTranslationError) as drift:
            solve_brace_rigid_translation(
                degenerate,
                ((0.0, 0.0), (1.0, 0.0)),
                ((0.0, 0.0), (0.0, 1.0)),
                ((0.0, 0.0), (1.0, 0.0)),
                ((0.0, 0.0), (0.0, 1.0)),
            )
        self.assertEqual(drift.exception.reason, "baseline_drift")

        outside = self.baseline((0.0, 0.0), (2.0, 1.0))
        with self.assertRaises(BraceRigidTranslationError) as finite:
            solve_brace_rigid_translation(
                outside,
                ((0.0, 0.0), (1.0, 0.0)),
                ((2.0, 0.0), (2.0, 1.0)),
                ((0.0, 3.0), (4.0, 3.0)),
                ((5.0, 0.0), (5.0, 1.0)),
            )
        self.assertEqual(finite.exception.reason, "outside_finite_segment")


class WalerContactAdjustmentTests(unittest.TestCase):
    def workflow(self, result=None):
        return DXFReviewWorkflow(
            SimpleNamespace(
                tolerances=GeometryTolerances(),
                source_fingerprint="",
            ),
            "C:/drawing/example.dxf",
            initial_world_result=result or _result(with_corner=False),
        )

    @staticmethod
    def provisional_manual_repair_result(struts=()):
        waler = replace(
            _waler("W1", (0.0, 0.0), (1000.0, 0.0)),
            contact_face_state="provisional",
        )
        return DXFImportResult(
            source_path="C:/drawing/manual-repair.dxf",
            layer_names=("WALER", "STRUT"),
            selected_layers={"waler": ("WALER",), "strut": ("STRUT",)},
            layer_info=(),
            walers=(waler,),
            struts=tuple(struts),
            braces=(),
            entity_debug=(),
            messages=(),
            source_entity_counts={},
        )

    def test_manual_contact_line_rebuilds_same_side_or_unknown_support_normal(self):
        up = replace(
            _strut((400.0, 0.0), (400.0, 1000.0)),
            from_waler="",
            to_waler="",
        )
        down = replace(
            _strut((600.0, 0.0), (600.0, -1000.0)),
            id="S2",
            source_handles=("H-S2",),
            from_waler="",
            to_waler="",
        )

        same_side = formalize_waler_engineering_line(
            self.provisional_manual_repair_result((up,)),
            ("H-W1",),
            (0.0, 0.0),
            (1000.0, 0.0),
            input_kind="manual_candidate_points",
        )
        conflicting = formalize_waler_engineering_line(
            self.provisional_manual_repair_result((up, down)),
            ("H-W1",),
            (0.0, 0.0),
            (1000.0, 0.0),
            input_kind="manual_candidate_points",
        )
        no_evidence = formalize_waler_engineering_line(
            self.provisional_manual_repair_result(),
            ("H-W1",),
            (0.0, 0.0),
            (1000.0, 0.0),
            input_kind="manual_candidate_points",
        )

        self.assertEqual(
            same_side.waler_contact_reviews[0].support_normal_world,
            (0.0, 1.0),
        )
        self.assertIsNone(
            conflicting.waler_contact_reviews[0].support_normal_world
        )
        self.assertIsNone(
            no_evidence.waler_contact_reviews[0].support_normal_world
        )
        self.assertTrue(
            all(
                result.walers[0].contact_face_state == "formal"
                and result.walers[0].engineering_line_authority == "manual_repair"
                for result in (same_side, conflicting, no_evidence)
            )
        )

    def test_manual_formalization_rebuilds_brace_baseline_and_keeps_rigid_translation(self):
        base = _result(with_corner=False)
        provisional = replace(
            base,
            walers=(
                replace(base.walers[0], contact_face_state="provisional"),
                base.walers[1],
            ),
            waler_contact_reviews=(),
            brace_adjustment_baselines=(),
        )
        repaired = formalize_waler_engineering_line(
            provisional,
            ("H-W1",),
            (0.0, 0.0),
            (10000.0, 0.0),
            input_kind="cad_manual",
        )
        baseline = next(
            item for item in repaired.brace_adjustment_baselines
            if item.brace_id == "B1"
        )
        before = repaired.braces[0]

        adjusted = apply_waler_contact_adjustment(
            repaired,
            "W1",
            **_dimensions(),
        )
        after = adjusted.braces[0]

        self.assertEqual(baseline.from_waler_id, "W1")
        self.assertEqual(baseline.to_waler_id, "W2")
        start_delta = (
            after.world_start[0] - before.world_start[0],
            after.world_start[1] - before.world_start[1],
        )
        end_delta = (
            after.world_end[0] - before.world_end[0],
            after.world_end[1] - before.world_end[1],
        )
        self.assertAlmostEqual(start_delta[0], end_delta[0])
        self.assertAlmostEqual(start_delta[1], end_delta[1])
        self.assertAlmostEqual(
            math.dist(after.world_start, after.world_end),
            math.dist(before.world_start, before.world_end),
        )

    def test_unknown_manual_support_side_blocks_adjustment_without_mutation(self):
        repaired = formalize_waler_engineering_line(
            self.provisional_manual_repair_result(),
            ("H-W1",),
            (0.0, 0.0),
            (1000.0, 0.0),
            input_kind="cad_manual",
        )
        snapshot = copy.deepcopy(repaired)

        plan = plan_waler_contact_adjustment(
            repaired,
            "W1",
            **_dimensions(),
        )

        self.assertFalse(plan.can_apply)
        self.assertIn(
            "WALER_SUPPORT_SIDE_UNKNOWN",
            {message.code for message in plan.messages},
        )
        with self.assertRaises(DXFImportError):
            apply_waler_contact_adjustment(repaired, "W1", **_dimensions())
        self.assertEqual(repaired, snapshot)

    def test_baseline_is_formal_only_and_is_not_recaptured_after_adjustment(self):
        base = _result(with_corner=False)
        formal = base.braces[0]
        invalid = (
            replace(formal, id="B-SAME", from_waler="W1", to_waler="W1"),
            replace(formal, id="B-MISSING", from_waler="", to_waler="W2"),
            replace(
                formal,
                id="B-OUTSIDE",
                start=(20000.0, 0.0),
                world_start=(20000.0, 0.0),
            ),
        )
        initialized = initialize_waler_contact_review(
            replace(
                base,
                braces=(formal, *invalid),
                brace_adjustment_baselines=(),
            ),
            rebuild_baselines=True,
        )
        self.assertEqual(
            tuple(item.brace_id for item in initialized.brace_adjustment_baselines),
            ("B1",),
        )
        provisional = initialize_waler_contact_review(
            replace(
                base,
                walers=(
                    replace(base.walers[0], contact_face_state="provisional"),
                    base.walers[1],
                ),
                brace_adjustment_baselines=(),
            ),
            rebuild_baselines=True,
        )
        self.assertEqual(provisional.brace_adjustment_baselines, ())
        adjusted = apply_waler_contact_adjustment(base, "W1", **_dimensions())
        reinitialized = initialize_waler_contact_review(adjusted)
        self.assertEqual(
            reinitialized.brace_adjustment_baselines,
            initialized.brace_adjustment_baselines,
        )

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
        self.assertAlmostEqual(second.braces[0].start[0], 4050.0)
        self.assertEqual(second.braces[0].start[1], 105.0)

    def test_two_waler_edit_order_and_preview_apply_are_equivalent(self):
        first_order = apply_waler_contact_adjustment(
            apply_waler_contact_adjustment(_result(), "W1", **_dimensions()),
            "W2",
            **_dimensions(),
        )
        reverse_order = apply_waler_contact_adjustment(
            apply_waler_contact_adjustment(_result(), "W2", **_dimensions()),
            "W1",
            **_dimensions(),
        )
        self.assertEqual(
            (first_order.braces[0].start, first_order.braces[0].end),
            (reverse_order.braces[0].start, reverse_order.braces[0].end),
        )
        preview = plan_waler_contact_adjustment(
            _result(), "W1", **_dimensions()
        )
        directly_applied = apply_waler_contact_adjustment(
            _result(), "W1", **_dimensions()
        )
        self.assertEqual(preview.proposed_result, directly_applied)
        reordered = _result()
        reordered = replace(
            reordered,
            walers=tuple(reversed(reordered.walers)),
            waler_contact_reviews=tuple(
                reversed(reordered.waler_contact_reviews)
            ),
        )
        reordered_plan = plan_waler_contact_adjustment(
            reordered, "W1", **_dimensions()
        )
        self.assertEqual(
            (
                reordered_plan.brace_changes[0].new_member.start,
                reordered_plan.brace_changes[0].new_member.end,
            ),
            (
                preview.brace_changes[0].new_member.start,
                preview.brace_changes[0].new_member.end,
            ),
        )

    def test_parallel_incompatible_brace_blocks_the_whole_apply_atomically(self):
        base = _result()
        horizontal = initialize_waler_contact_review(
            replace(
                base,
                walers=(
                    base.walers[0],
                    _waler("W2", (0.0, 10000.0), (10000.0, 10000.0)),
                ),
                waler_contact_reviews=(),
                brace_adjustment_baselines=(),
                corner_brace_connections=(),
            )
        )
        snapshot = copy.deepcopy(horizontal)
        plan = plan_waler_contact_adjustment(
            horizontal, "W1", **_dimensions()
        )
        self.assertFalse(plan.can_apply)
        diagnostic = next(
            item
            for item in plan.messages
            if item.code == "BRACE_RIGID_TRANSLATION_UNRESOLVED"
        )
        self.assertIn("parallel_incompatible", diagnostic.message)
        with self.assertRaises(DXFImportError):
            apply_waler_contact_adjustment(horizontal, "W1", **_dimensions())
        self.assertEqual(horizontal, snapshot)

    def test_baseline_drift_and_missing_baseline_are_traceable(self):
        result = _result(with_corner=False)
        drifted_brace = replace(
            result.braces[0],
            start=(result.braces[0].start[0] + 10.0, result.braces[0].start[1]),
            world_start=(
                result.braces[0].world_start[0] + 10.0,
                result.braces[0].world_start[1],
            ),
        )
        drifted = replace(result, braces=(drifted_brace,))
        drift_plan = plan_waler_contact_adjustment(
            drifted, "W1", **_dimensions()
        )
        self.assertTrue(
            any(
                item.code == "BRACE_RIGID_TRANSLATION_UNRESOLVED"
                and "baseline_drift" in item.message
                for item in drift_plan.messages
            )
        )
        missing = replace(result, brace_adjustment_baselines=())
        missing_plan = plan_waler_contact_adjustment(
            missing, "W1", **_dimensions()
        )
        self.assertTrue(
            any(
                item.code == "BRACE_RIGID_TRANSLATION_UNRESOLVED"
                and "identity_invalid" in item.message
                for item in missing_plan.messages
            )
        )

    def test_manual_endpoints_before_adjustment_become_the_baseline(self):
        workflow = self.workflow()
        start_id, end_id, _mutation = workflow.add_cad_candidate_line(
            "B1", (3200.0, 0.0), (5200.0, 10020.0)
        )
        workflow.apply_candidate_change(
            "B1", start_id, end_id, "cad_manual"
        )
        baseline = workflow.world_result.brace_adjustment_baselines[0]
        self.assertEqual(baseline.start, (3200.0, 0.0))
        self.assertEqual(baseline.end, (5200.0, 10020.0))

        workflow.apply_waler_contact_adjustment("W1", **_dimensions())
        brace = workflow.world_result.braces[0]
        self.assertEqual(brace.start, (4050.0, 85.0))
        self.assertEqual(brace.end, (6050.0, 10105.0))

    def test_manual_endpoints_after_adjustment_are_saved_as_baseline_wcs(self):
        workflow = self.workflow()
        workflow.apply_waler_contact_adjustment("W1", **_dimensions())
        start_id, end_id, _mutation = workflow.add_cad_candidate_line(
            "B1", (4050.0, 85.0), (6050.0, 10105.0)
        )
        workflow.apply_candidate_change(
            "B1", start_id, end_id, "cad_manual"
        )
        baseline = workflow.world_result.brace_adjustment_baselines[0]
        self.assertEqual(baseline.start, (3200.0, 0.0))
        self.assertEqual(baseline.end, (5200.0, 10020.0))
        self.assertAlmostEqual(workflow.world_result.braces[0].start[0], 4050.0)
        self.assertAlmostEqual(workflow.world_result.braces[0].start[1], 85.0)

        workflow.apply_waler_contact_adjustment("W1", **_dimensions())
        self.assertAlmostEqual(workflow.world_result.braces[0].start[0], 4050.0)
        self.assertAlmostEqual(workflow.world_result.braces[0].start[1], 85.0)
        self.assertAlmostEqual(workflow.world_result.braces[0].end[0], 6050.0)
        self.assertAlmostEqual(workflow.world_result.braces[0].end[1], 10105.0)

        overrides = capture_manual_overrides(workflow.world_result)
        brace_override = next(item for item in overrides if item.role == "brace")
        self.assertEqual(brace_override.geometry_coordinate_space, "baseline_wcs")
        self.assertEqual(brace_override.world_start, (3200.0, 0.0))
        self.assertEqual(brace_override.world_end, (5200.0, 10020.0))

        replayed, report = replay_manual_overrides(
            _result(with_corner=False),
            overrides,
        )
        self.assertEqual(report.needs_review, ())
        self.assertAlmostEqual(replayed.braces[0].start[0], 4050.0)
        self.assertAlmostEqual(replayed.braces[0].start[1], 85.0)
        self.assertAlmostEqual(replayed.braces[0].end[0], 6050.0)
        self.assertAlmostEqual(replayed.braces[0].end[1], 10105.0)

        legacy = tuple(
            replace(item, geometry_coordinate_space="")
            if item.role == "brace"
            else item
            for item in overrides
        )
        legacy_replayed, legacy_report = replay_manual_overrides(
            _result(with_corner=False),
            legacy,
        )
        self.assertTrue(
            any("工程線" in item for item in legacy_report.needs_review)
        )
        self.assertEqual(
            next(
                item.adopted_backfill_mm
                for item in legacy_replayed.waler_contact_reviews
                if item.waler_id == "W1"
            ),
            135.0,
        )
        self.assertNotEqual(
            legacy_replayed.brace_adjustment_baselines[0].start,
            (3200.0, 0.0),
        )

    def test_manual_endpoint_conversion_outside_baseline_is_atomic(self):
        workflow = self.workflow()
        workflow.apply_waler_contact_adjustment("W1", **_dimensions())
        start_id, end_id, _mutation = workflow.add_cad_candidate_line(
            "B1", (0.0, 85.0), (2000.0, 9700.0)
        )
        snapshot = copy.deepcopy(workflow.snapshot)
        revision = workflow.revision
        with self.assertRaisesRegex(DXFImportError, "不會吸附、截斷或保存"):
            workflow.apply_candidate_change(
                "B1", start_id, end_id, "cad_manual"
            )
        self.assertEqual(workflow.snapshot, snapshot)
        self.assertEqual(workflow.revision, revision)
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
        self.assertAlmostEqual(brace.translation[0], 850.0)
        self.assertAlmostEqual(brace.translation[1], 85.0)
        self.assertEqual(brace.baseline_start, (3000.0, 0.0))
        self.assertEqual(brace.baseline_end, (5000.0, 10000.0))
        self.assertEqual(brace.proposed_start, brace.new_member.start)
        self.assertEqual(brace.proposed_end, brace.new_member.end)
        self.assertNotEqual(
            brace.from_old_station_mm, brace.from_new_station_mm
        )
        self.assertNotEqual(brace.to_old_station_mm, brace.to_new_station_mm)
        self.assertEqual(brace.new_member.start, (3850.0, 85.0))
        self.assertEqual(brace.new_member.end, (5850.0, 10085.0))
        self.assertEqual(
            (
                brace.new_member.end[0] - brace.new_member.start[0],
                brace.new_member.end[1] - brace.new_member.start[1],
            ),
            (2000.0, 10000.0),
        )
        self.assertAlmostEqual(
            math.dist(brace.new_member.start, brace.new_member.end),
            math.dist(brace.old_member.start, brace.old_member.end),
        )
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
        summary = format_adjustment_plan(plan)
        self.assertIn("共同平移", summary)
        self.assertIn("From station", summary)
        self.assertIn("To station", summary)
        self.assertNotIn("圍令位置：3000.000 → 3000.000", summary)

    def test_refined_corner_axis_is_the_contact_adjustment_baseline(self):
        refined_corner = replace(
            _corner(),
            start=(4540.0, 0.0),
            end=(5000.0, 460.0),
            world_start=(4540.0, 0.0),
            world_end=(5000.0, 460.0),
        )
        result = initialize_waler_contact_review(
            replace(
                _result(with_corner=False),
                corner_braces=(refined_corner,),
            )
        )

        self.assertEqual(len(result.corner_brace_connections), 1)
        connection = result.corner_brace_connections[0]
        self.assertEqual(connection.baseline_waler_attachment, (4540.0, 0.0))
        self.assertEqual(connection.baseline_strut_attachment, (5000.0, 460.0))
        self.assertAlmostEqual(connection.strut_hole_station_mm, 460.0)
        self.assertAlmostEqual(
            connection.fixed_length_mm,
            math.hypot(460.0, 460.0),
        )

        plan = plan_waler_contact_adjustment(result, "W1", **_dimensions())

        self.assertTrue(plan.can_apply, [item.message for item in plan.messages])
        change = plan.corner_brace_changes[0]
        self.assertAlmostEqual(change.strut_hole_station_mm, 460.0)
        self.assertAlmostEqual(change.fixed_length_mm, math.hypot(460.0, 460.0))
        self.assertEqual(change.new_member.start, (4540.0, 85.0))
        self.assertEqual(change.new_member.end, (5000.0, 545.0))

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
        self.assertNotIn("brace_adjustment_baselines", debug)
        self.assertEqual(rows["braces"][0]["StartX"], 3850)
        self.assertEqual(rows["braces"][0]["StartY"], 85)
        self.assertEqual(rows["braces"][0]["EndX"], 5850)
        self.assertEqual(rows["braces"][0]["EndY"], 10085)

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
        horizontal_w2 = _waler(
            "W2", (0.0, 10000.0), (10000.0, 10000.0)
        )
        result = initialize_waler_contact_review(
            replace(
                base,
                walers=(base.walers[0], horizontal_w2),
                braces=(),
                corner_braces=(top_corner,),
                waler_contact_reviews=(),
                brace_adjustment_baselines=(),
                corner_brace_connections=(),
            )
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

    def test_incomplete_brace_does_not_enter_adjustment_baseline_or_plan(self):
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
        self.assertEqual(result.brace_adjustment_baselines, ())
        self.assertTrue(plan.can_apply)
        self.assertEqual(plan.brace_changes, ())

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
