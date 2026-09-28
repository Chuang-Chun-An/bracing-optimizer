import math
import unittest

from bracing_optimizer.domain.project_domain import LineSegment, Point
from bracing_optimizer.domain.support_adjacency import (
    ZONING_ANGLE_OUT_OF_TOLERANCE,
    ZONING_LENGTH_OUT_OF_TOLERANCE,
    ZONING_PROJECTION_TIE,
    ZONING_ZERO_LENGTH_AXIS,
    build_axis_fact,
    project_support_units,
    validate_support_axes,
)


def axis(member_id, start, end):
    return build_axis_fact(
        member_id,
        LineSegment(Point(*start), Point(*end)),
    )


class SupportAdjacencyDirectionTests(unittest.TestCase):
    def test_common_direction_is_independent_of_order_and_endpoint_direction(self):
        original = (
            axis("S1", (0, 0), (10000, 0)),
            axis("S2", (0, 1000), (10000, 1000)),
            axis("S3", (0, 2000), (10000, 2000)),
        )
        reversed_and_reordered = (
            axis("S3", (10000, 2000), (0, 2000)),
            axis("S1", (10000, 0), (0, 0)),
            axis("S2", (10000, 1000), (0, 1000)),
        )

        first = validate_support_axes(original, zoning="Z1")
        second = validate_support_axes(reversed_and_reordered, zoning="Z1")

        self.assertEqual(first.issues, ())
        self.assertEqual(second.issues, ())
        self.assertAlmostEqual(first.common_direction[0], second.common_direction[0])
        self.assertAlmostEqual(first.common_direction[1], second.common_direction[1])
        self.assertAlmostEqual(first.row_direction[0], second.row_direction[0])
        self.assertAlmostEqual(first.row_direction[1], second.row_direction[1])

    def test_vertical_and_slightly_rotated_axes_have_stable_semantics(self):
        angle = math.radians(4.0)
        result = validate_support_axes((
            axis("S1", (0, 0), (0, 10000)),
            axis(
                "S2",
                (1000, 0),
                (1000 - 10000 * math.sin(angle), 10000 * math.cos(angle)),
            ),
        ))

        self.assertEqual(result.issues, ())
        self.assertIsNotNone(result.common_direction)


class SupportAdjacencyValidationTests(unittest.TestCase):
    def test_zero_length_axis_has_structured_issue(self):
        result = validate_support_axes((axis("S1", (1, 2), (1, 2)),), zoning="Z1")

        issue = result.issues[0]
        self.assertEqual(issue.code, ZONING_ZERO_LENGTH_AXIS)
        self.assertEqual(issue.zoning, "Z1")
        self.assertEqual(issue.member_ids, ("S1",))

    def test_angle_boundary_is_inclusive_and_excess_is_rejected(self):
        def angled(member_id, degrees):
            radians = math.radians(degrees)
            return axis(
                member_id,
                (0, 1000 if member_id == "S2" else 0),
                (10000 * math.cos(radians),
                 (1000 if member_id == "S2" else 0) + 10000 * math.sin(radians)),
            )

        accepted = validate_support_axes((angled("S1", 0), angled("S2", 5)))
        rejected = validate_support_axes((angled("S1", 0), angled("S2", 5.01)))

        self.assertFalse(any(
            issue.code == ZONING_ANGLE_OUT_OF_TOLERANCE
            for issue in accepted.issues
        ))
        issue = next(
            item for item in rejected.issues
            if item.code == ZONING_ANGLE_OUT_OF_TOLERANCE
        )
        self.assertEqual(issue.member_ids, ("S1", "S2"))
        self.assertGreater(issue.actual_value, issue.tolerance)

    def test_length_boundary_is_inclusive_and_excess_is_rejected(self):
        accepted = validate_support_axes((
            axis("S1", (0, 0), (10000, 0)),
            axis("S2", (0, 1000), (10005, 1000)),
        ))
        rejected = validate_support_axes((
            axis("S1", (0, 0), (10000, 0)),
            axis("S2", (0, 1000), (10005.01, 1000)),
        ))

        self.assertFalse(any(
            issue.code == ZONING_LENGTH_OUT_OF_TOLERANCE
            for issue in accepted.issues
        ))
        issue = next(
            item for item in rejected.issues
            if item.code == ZONING_LENGTH_OUT_OF_TOLERANCE
        )
        self.assertEqual(issue.member_ids, ("S1", "S2"))
        self.assertGreater(issue.actual_value, issue.tolerance)


class SupportAdjacencyProjectionTests(unittest.TestCase):
    def test_one_millimetre_projection_difference_is_invalid(self):
        result = project_support_units(
            (
                ("U1", ("S1",), Point(0, 0)),
                ("U2", ("S2",), Point(0, 1)),
            ),
            (0, 1),
            zoning="Z1",
        )

        self.assertEqual(result.issues[0].code, ZONING_PROJECTION_TIE)
        self.assertEqual(result.issues[0].actual_value, 1.0)
        self.assertEqual(result.issues[0].tolerance, 1.0)

    def test_projection_above_tolerance_has_geometry_order(self):
        units = (
            ("U3", ("S3",), Point(0, 3000)),
            ("U1", ("S1",), Point(0, 0)),
            ("U2", ("S2",), Point(0, 1000)),
        )
        result = project_support_units(units, (0, 1), zoning="Z1")

        self.assertEqual(result.issues, ())
        self.assertEqual(
            tuple(item.unit_id for item in result.projections),
            ("U1", "U2", "U3"),
        )

    def test_tie_is_not_resolved_by_id_or_input_order(self):
        first = project_support_units((
            ("B", ("S2",), Point(0, 0)),
            ("A", ("S1",), Point(0, 0)),
        ), (0, 1))
        second = project_support_units((
            ("A", ("S1",), Point(0, 0)),
            ("B", ("S2",), Point(0, 0)),
        ), (0, 1))

        self.assertEqual(first.issues[0].code, ZONING_PROJECTION_TIE)
        self.assertEqual(second.issues[0].code, ZONING_PROJECTION_TIE)


if __name__ == "__main__":
    unittest.main()
