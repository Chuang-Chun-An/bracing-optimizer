from dataclasses import fields
import math
import unittest

from dxf_import.corner_brace_recognition import (
    CornerBraceSourceSegment,
    assess_corner_brace_relationship,
    build_corner_brace_body_hypotheses,
    build_corner_brace_rail_tracks,
    canonical_direction,
)
from dxf_import.models import (
    CornerBraceBodyGeometryEvidence,
    GeometryTolerances,
)


def _source(identifier, start, end):
    return CornerBraceSourceSegment(identifier, identifier.split(":")[0], (start, end))


class CornerBraceRailTrackTests(unittest.TestCase):
    def test_canonical_direction_is_independent_of_line_order(self):
        self.assertEqual(
            canonical_direction(((0.0, 0.0), (-100.0, -100.0))),
            canonical_direction(((-100.0, -100.0), (0.0, 0.0))),
        )

    def test_normal_offset_hypotheses_are_order_independent_and_not_first_fit(self):
        sources = (
            _source("A:0", (0.0, 40.0), (500.0, 40.0)),
            _source("A:1", (0.0, 0.0), (500.0, 0.0)),
            _source("A:2", (0.0, 20.0), (500.0, 20.0)),
        )
        settings = GeometryTolerances()
        forward = build_corner_brace_rail_tracks(sources, settings)
        reverse = build_corner_brace_rail_tracks(tuple(reversed(sources)), settings)
        forward_sets = {frozenset(item.id for item in track.fragments) for track in forward}
        reverse_sets = {frozenset(item.id for item in track.fragments) for track in reverse}
        self.assertEqual(forward_sets, reverse_sets)
        self.assertEqual(
            forward_sets,
            {frozenset(("A:0", "A:2")), frozenset(("A:1", "A:2"))},
        )

    def test_track_seam_includes_50_but_not_50_plus_epsilon(self):
        settings = GeometryTolerances()
        at_limit = build_corner_brace_rail_tracks(
            (
                _source("A:0", (0.0, 0.0), (100.0, 0.0)),
                _source("A:1", (150.0, 0.0), (250.0, 0.0)),
            ),
            settings,
        )[0]
        over_limit = build_corner_brace_rail_tracks(
            (
                _source("A:0", (0.0, 0.0), (100.0, 0.0)),
                _source("A:1", (150.000001, 0.0), (250.000001, 0.0)),
            ),
            settings,
        )[0]
        self.assertEqual(len(at_limit.merged_intervals), 1)
        self.assertEqual(len(over_limit.merged_intervals), 2)

    def test_body_separation_interval_is_open_then_closed(self):
        settings = GeometryTolerances()

        def count(separation):
            return len(
                build_corner_brace_body_hypotheses(
                    "G",
                    ("A",),
                    (
                        _source("A:0", (0.0, 0.0), (1000.0, 0.0)),
                        _source("A:1", (0.0, separation), (1000.0, separation)),
                    ),
                    settings,
                )
            )

        self.assertEqual(count(250.0), 0)
        self.assertEqual(count(250.000001), 1)
        self.assertEqual(count(600.0), 1)
        self.assertEqual(count(600.000001), 0)

    def test_direction_seed_and_normal_spread_boundaries(self):
        settings = GeometryTolerances()
        self.assertEqual(
            build_corner_brace_rail_tracks(
                (_source("A:0", (0.0, 0.0), (99.999999, 0.0)),),
                settings,
            ),
            (),
        )
        at_seed = build_corner_brace_rail_tracks(
            (
                _source("A:0", (0.0, 0.0), (100.0, 0.0)),
                _source("A:1", (150.0, 0.0), (200.0, 0.0)),
            ),
            settings,
        )
        self.assertEqual(
            {fragment.id for fragment in at_seed[0].fragments},
            {"A:0", "A:1"},
        )
        at_spread = build_corner_brace_rail_tracks(
            (
                _source("A:0", (0.0, 0.0), (500.0, 0.0)),
                _source("A:1", (0.0, 25.0), (500.0, 25.0)),
            ),
            settings,
        )
        over_spread = build_corner_brace_rail_tracks(
            (
                _source("A:0", (0.0, 0.0), (500.0, 0.0)),
                _source("A:1", (0.0, 25.000001), (500.0, 25.000001)),
            ),
            settings,
        )
        self.assertTrue(
            any(len(track.fragments) == 2 for track in at_spread)
        )
        self.assertFalse(
            any(len(track.fragments) == 2 for track in over_spread)
        )

    def test_direction_difference_accepts_two_degrees_only(self):
        settings = GeometryTolerances()

        def endpoint(angle):
            radians = math.radians(angle)
            return 500.0 * math.cos(radians), 500.0 * math.sin(radians)

        at_limit = build_corner_brace_rail_tracks(
            (
                _source("A:0", (0.0, 0.0), (500.0, 0.0)),
                _source("A:1", (0.0, 0.0), endpoint(2.0)),
            ),
            settings,
        )
        over_limit = build_corner_brace_rail_tracks(
            (
                _source("A:0", (0.0, 0.0), (500.0, 0.0)),
                _source("A:1", (0.0, 0.0), endpoint(2.000001)),
            ),
            settings,
        )
        self.assertTrue(any(len(track.fragments) == 2 for track in at_limit))
        self.assertFalse(any(len(track.fragments) == 2 for track in over_limit))


class CornerBraceRelationshipAssessmentTests(unittest.TestCase):
    def _body(self, rail_intervals, separation=300.0):
        sources = []
        for rail, y in enumerate((0.0, separation)):
            for index, (start, end) in enumerate(rail_intervals[rail]):
                sources.append(
                    _source(f"A:{rail}:{index}", (start, y), (end, y))
                )
        bodies = build_corner_brace_body_hypotheses(
            "G", ("A",), tuple(sources), GeometryTolerances()
        )
        self.assertEqual(len(bodies), 1)
        return bodies[0]

    def _assess(self, body, start, end, occluders=()):
        return assess_corner_brace_relationship(
            body,
            waler_source_handles=("W",),
            strut_source_handles=("S",),
            waler_intersection=(start, 150.0),
            strut_intersection=(end, 150.0),
            occluding_lines=occluders,
            tolerances=GeometryTolerances(),
        )

    def test_body_evidence_has_no_relationship_dependent_fields(self):
        names = {item.name for item in fields(CornerBraceBodyGeometryEvidence)}
        forbidden = {
            "expected_span_mm",
            "expected_slenderness_ratio",
            "per_rail_union_coverage",
            "internal_gaps",
            "terminal_gaps",
            "gap_occluder_assignments",
            "per_end_extensions_mm",
            "classification",
            "hard_valid",
            "rejection_reasons",
        }
        self.assertTrue(names.isdisjoint(forbidden))

    def test_zero_one_or_two_terminal_plates_do_not_change_eligibility(self):
        settings = GeometryTolerances()
        outcomes = []
        for plate_count in (0, 1, 2):
            sources = [
                _source("A:0", (0.0, 0.0), (1000.0, 0.0)),
                _source("A:1", (0.0, 300.0), (1000.0, 300.0)),
            ]
            if plate_count >= 1:
                sources.append(
                    _source("A:P0", (0.0, 0.0), (0.0, 300.0))
                )
            if plate_count == 2:
                sources.append(
                    _source("A:P1", (1000.0, 0.0), (1000.0, 300.0))
                )
            body = build_corner_brace_body_hypotheses(
                "G", ("A",), tuple(sources), settings
            )[0]
            assessment = self._assess(body, 0.0, 1000.0)
            outcomes.append(
                (
                    len(body.terminal_plate_evidence),
                    assessment.hard_valid,
                    assessment.classification,
                    assessment.per_rail_union_coverage,
                )
            )
        self.assertEqual([item[0] for item in outcomes], [0, 1, 2])
        self.assertEqual(
            {(item[1], item[2], item[3]) for item in outcomes},
            {(True, "complete", (1.0, 1.0))},
        )

    def test_exact_half_coverage_of_2121_320_span_passes_coverage_gate(self):
        half = 1060.660
        body = self._body((((0.0, half),), ((0.0, half),)))
        assessment = self._assess(
            body,
            0.0,
            2121.320,
            occluders=(
                ((half, 0.0), (2121.320, 0.0)),
                ((half, 300.0), (2121.320, 300.0)),
            ),
        )
        self.assertEqual(assessment.per_rail_union_coverage, (0.5, 0.5))
        self.assertNotIn("rail_1_coverage_below_minimum", assessment.rejection_reasons)
        self.assertNotIn("rail_2_coverage_below_minimum", assessment.rejection_reasons)

    def test_600_extension_is_legal_but_does_not_repair_coverage(self):
        body = self._body((((600.0, 1600.0),), ((600.0, 1600.0),)))
        assessment = self._assess(body, 0.0, 2200.0)
        self.assertEqual(assessment.per_end_extensions_mm, (600.0, 600.0))
        self.assertNotIn("waler_end_extension_above_maximum", assessment.rejection_reasons)
        self.assertNotIn("strut_end_extension_above_maximum", assessment.rejection_reasons)
        self.assertIn("rail_1_coverage_below_minimum", assessment.rejection_reasons)

    def test_coverage_can_pass_while_800_extension_fails(self):
        body = self._body((((800.0, 2000.0),), ((800.0, 2000.0),)))
        assessment = self._assess(body, 0.0, 2000.0)
        self.assertGreaterEqual(assessment.per_rail_union_coverage[0], 0.5)
        self.assertIn("waler_end_extension_above_maximum", assessment.rejection_reasons)

    def test_gap_over_50_requires_its_own_finite_occluder(self):
        body = self._body(
            (
                ((0.0, 500.0), (550.000001, 1000.0)),
                ((0.0, 500.0), (550.000001, 1000.0)),
            )
        )
        missing = self._assess(body, 0.0, 1000.0)
        self.assertEqual(missing.classification, "hard_invalid")
        self.assertIn("gap_without_finite_occluder", missing.rejection_reasons)
        explained = self._assess(
            body,
            0.0,
            1000.0,
            occluders=(
                ((525.0, -100.0), (525.0, 400.0)),
            ),
        )
        self.assertNotIn("gap_without_finite_occluder", explained.rejection_reasons)

    def test_expected_slenderness_three_is_inclusive(self):
        body = self._body((((0.0, 900.0),), ((0.0, 900.0),)))
        at_limit = self._assess(body, 0.0, 900.0)
        below = self._assess(body, 0.0, 899.999999)
        self.assertNotIn(
            "expected_slenderness_below_minimum", at_limit.rejection_reasons
        )
        self.assertIn(
            "expected_slenderness_below_minimum", below.rejection_reasons
        )

    def test_coverage_and_extension_epsilon_boundaries(self):
        coverage_body = self._body(
            (((300.0, 800.0 - 0.000001),), ((300.0, 800.0 - 0.000001),))
        )
        coverage = self._assess(coverage_body, 0.0, 1000.0)
        self.assertIn("rail_1_coverage_below_minimum", coverage.rejection_reasons)

        extension_body = self._body(
            (((600.000001, 1600.000001),), ((600.000001, 1600.000001),))
        )
        extension = self._assess(extension_body, 0.0, 2200.0)
        self.assertIn(
            "waler_end_extension_above_maximum",
            extension.rejection_reasons,
        )

    def test_same_body_relationship_assessments_are_isolated(self):
        body = self._body((((300.0, 900.0),), ((300.0, 900.0),)))
        sixty = self._assess(body, 0.0, 1000.0)
        forty_five = self._assess(body, 0.0, 1333.3333333333)
        self.assertAlmostEqual(sixty.per_rail_union_coverage[0], 0.6)
        self.assertAlmostEqual(
            forty_five.per_rail_union_coverage[0], 0.45, places=6
        )
        self.assertTrue(sixty.hard_valid)
        self.assertFalse(forty_five.hard_valid)
        self.assertEqual(body.merged_source_intervals[0], ((300.0, 900.0),))

    def test_near_parallel_occluder_requires_half_gap_overlap(self):
        body = self._body(
            (
                ((0.0, 400.0), (600.0, 1000.0)),
                ((0.0, 400.0), (600.0, 1000.0)),
            )
        )
        accepted = self._assess(
            body,
            0.0,
            1000.0,
            occluders=(
                ((500.0, 0.0), (600.0, 0.0)),
                ((500.0, 300.0), (600.0, 300.0)),
            ),
        )
        rejected = self._assess(
            body,
            0.0,
            1000.0,
            occluders=(
                ((500.000001, 0.0), (600.0, 0.0)),
                ((500.000001, 300.0), (600.0, 300.0)),
            ),
        )
        self.assertNotIn(
            "gap_without_finite_occluder", accepted.rejection_reasons
        )
        self.assertTrue(accepted.hard_valid)
        self.assertEqual(accepted.classification, "occluded")
        self.assertIn(
            "gap_without_finite_occluder", rejected.rejection_reasons
        )

    def test_each_of_two_gaps_requires_its_own_finite_segment(self):
        body = self._body(
            (
                ((0.0, 300.0), (400.0, 600.0), (700.0, 1000.0)),
                ((0.0, 300.0), (400.0, 600.0), (700.0, 1000.0)),
            )
        )
        assessment = self._assess(
            body,
            0.0,
            1000.0,
            occluders=(((350.0, -100.0), (350.0, 400.0)),),
        )
        explained = tuple(
            assignment
            for assignment in assessment.gap_occluder_assignments
            if assignment.occluder_lines
        )
        unexplained = tuple(
            assignment
            for assignment in assessment.gap_occluder_assignments
            if not assignment.occluder_lines
        )
        self.assertEqual(len(explained), 2)
        self.assertEqual(len(unexplained), 2)
        self.assertIn(
            "gap_without_finite_occluder", assessment.rejection_reasons
        )

    def test_infinite_extension_or_nearby_segment_is_not_occluder(self):
        body = self._body(
            (
                ((0.0, 400.0), (600.0, 1000.0)),
                ((0.0, 400.0), (600.0, 1000.0)),
            )
        )
        assessment = self._assess(
            body,
            0.0,
            1000.0,
            occluders=(((500.0, 400.0), (500.0, 500.0)),),
        )
        self.assertIn(
            "gap_without_finite_occluder", assessment.rejection_reasons
        )


if __name__ == "__main__":
    unittest.main()
