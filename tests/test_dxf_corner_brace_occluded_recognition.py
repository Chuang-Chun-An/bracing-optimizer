import unittest
from dataclasses import replace
from pathlib import Path
import tempfile

import ezdxf

from dxf_import.corner_brace_repair import (
    apply_corner_brace_repair,
    plan_corner_brace_repair,
)
from dxf_import.importer import (
    DXFImporter,
    Y05_LAYER_MAPPING,
    Y1A_LAYER_MAPPING,
    Y29_LAYER_MAPPING,
    import_dxf,
)
from dxf_import.models import ExcludedSource, GeometryTolerances
from dxf_import.review_workflow import DXFReviewWorkflow
from dxf_import.source_exclusion import (
    capture_manual_overrides,
    replay_manual_overrides,
)
from dxf_import.recognition import (
    _Candidate,
    _GeometryGroup,
    _Primitive,
    _corner_brace_candidates_from_group,
    _corner_brace_center_axis,
    _engineering_line_candidates,
    _refine_corner_brace_axis_intersections,
)
from dxf_import.validation import build_problem_records, build_review_items
from tests.sample_dxf_assets import Y05_DXF_PATH, Y1A_DXF_PATH, Y29_DXF_PATH


LAYER_USE_TO_ROLE = {
    "圍令": "waler",
    "支撐": "strut",
    "斜撐": "brace",
    "中間柱": "column",
    "托梁": "beam",
    "角撐": "corner_brace",
    "連續壁": "continuous_wall",
    "輔助線": "auxiliary",
    "忽略": "ignore",
}


def _complete_corner_group(
    separation: float,
    *,
    reverse_second: bool = False,
) -> _GeometryGroup:
    first = ((0.0, 0.0), (1000.0, 0.0))
    second = ((0.0, separation), (1000.0, separation))
    if reverse_second:
        second = second[1], second[0]
    segments = (
        first,
        second,
        ((0.0, 0.0), (0.0, separation)),
        ((1000.0, 0.0), (1000.0, separation)),
    )
    return _group_from_segments(segments)


def _mitered_corner_group(*, reverse_segments: bool = False) -> _GeometryGroup:
    """Closed four-edge body with unequal parallel rails."""

    segments = (
        ((0.0, 0.0), (1000.0, 0.0)),
        ((-300.0, 300.0), (1300.0, 300.0)),
        ((-300.0, 300.0), (0.0, 0.0)),
        ((1000.0, 0.0), (1300.0, 300.0)),
    )
    return _group_from_segments(
        tuple(reversed(segments)) if reverse_segments else segments
    )


def _group_from_segments(
    segments,
    *,
    key="corner_brace:H1",
) -> _GeometryGroup:
    return _GeometryGroup(
        key=key,
        role="corner_brace",
        layer="CORNER",
        primitives=[
            _Primitive(list(segment), False, "LINE", key.split(":")[-1])
            for segment in segments
        ],
        handles={key.split(":")[-1]},
        entity_types={"INSERT", "LINE"},
        block_instances=[],
        root_handle=key.split(":")[-1],
        root_entity_type="INSERT",
    )


def _occluded_corner_group(
    short_start_x: float = 200.0,
    *,
    occluder=((150.0, 250.0), (150.0, 350.0)),
    y_offset: float = 0.0,
    key: str = "corner_brace:H1",
) -> _GeometryGroup:
    segments = [
        ((0.0, y_offset), (1000.0, y_offset)),
        (
            (short_start_x, y_offset + 300.0),
            (1000.0, y_offset + 300.0),
        ),
        ((1000.0, y_offset), (1000.0, y_offset + 300.0)),
    ]
    if occluder is not None:
        segments.append(
            tuple(
                (point[0], point[1] + y_offset)
                for point in occluder
            )
        )
    return _group_from_segments(segments, key=key)


def _member_candidate(start, end, *, handle) -> _Candidate:
    return _Candidate(
        start=start,
        end=end,
        recognition_method="existing_centerline",
        centerline_computed=True,
        source_width=0.0,
        confidence=1.0,
        layer="MEMBER",
        handles={handle},
        entity_types={"LINE"},
        block_instances=[],
        source_keys={handle},
        warnings=[],
        boundary_lines=((start, end),),
        recognized_axis=(start, end),
    )


class CornerBraceRailMaterialRuleTests(unittest.TestCase):
    def test_rail_separation_must_be_strictly_greater_than_250(self):
        tolerances = GeometryTolerances()

        boundary, _messages = _corner_brace_candidates_from_group(
            _complete_corner_group(250.0),
            tolerances,
        )
        above, _messages = _corner_brace_candidates_from_group(
            _complete_corner_group(250.001),
            tolerances,
        )

        self.assertEqual(boundary, [])
        self.assertEqual(len(above), 1)
        self.assertAlmostEqual(above[0].source_width, 250.001)

    def test_rail_measurement_is_independent_of_endpoint_order(self):
        tolerances = GeometryTolerances()
        direct, _messages = _corner_brace_candidates_from_group(
            _complete_corner_group(300.0),
            tolerances,
        )
        reversed_pair, _messages = _corner_brace_candidates_from_group(
            _complete_corner_group(300.0, reverse_second=True),
            tolerances,
        )

        self.assertEqual(len(direct), 1)
        self.assertEqual(len(reversed_pair), 1)
        self.assertEqual(direct[0].source_width, 300.0)
        self.assertEqual(reversed_pair[0].source_width, 300.0)
        self.assertEqual(
            direct[0].selected_rail_lines,
            reversed_pair[0].selected_rail_lines,
        )

    def test_selected_rails_drive_center_axis_and_public_line_evidence(self):
        selected = (
            ((0.0, 0.0), (1000.0, 0.0)),
            ((0.0, 320.0), (1000.0, 320.0)),
        )
        longer_narrow_pair = (
            ((-100.0, 50.0), (1100.0, 50.0)),
            ((-100.0, 205.0), (1100.0, 205.0)),
        )
        candidate = _Candidate(
            start=(0.0, 160.0),
            end=(1000.0, 160.0),
            recognition_method="connection_plate_midpoints",
            centerline_computed=True,
            source_width=320.0,
            confidence=0.99,
            layer="CORNER",
            handles={"H1"},
            entity_types={"INSERT", "LINE"},
            block_instances=[],
            source_keys={"corner_brace:H1"},
            warnings=[],
            boundary_lines=(*selected, *longer_narrow_pair),
            selected_rail_lines=selected,
            corner_brace_candidate_kind="complete",
            corner_brace_group_key="corner_brace:H1",
        )

        axis = _corner_brace_center_axis(candidate, GeometryTolerances())
        line_candidates = _engineering_line_candidates("corner_brace", candidate)

        self.assertEqual(axis, ((0.0, 160.0), (1000.0, 160.0)))
        selected_evidence = tuple(
            item
            for item in line_candidates
            if item.source == "recognized_corner_brace_rail"
        )
        self.assertEqual(len(selected_evidence), 2)
        self.assertEqual(
            {item.label for item in selected_evidence},
            {"角撐本體 rail 1", "角撐本體 rail 2"},
        )


class CornerBraceCompleteEnumerationTests(unittest.TestCase):
    def test_mitered_closed_body_accepts_unequal_rails_without_fallback(self):
        candidates, messages = _corner_brace_candidates_from_group(
            _mitered_corner_group(),
            GeometryTolerances(),
        )

        self.assertEqual(messages, [])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].corner_brace_candidate_kind, "body")
        self.assertAlmostEqual(candidates[0].source_width, 300.0, places=6)
        self.assertIsNotNone(candidates[0].corner_brace_body_evidence)
        self.assertTrue(
            candidates[0].corner_brace_body_evidence.terminal_plate_evidence
        )

        reordered, reordered_messages = _corner_brace_candidates_from_group(
            _mitered_corner_group(reverse_segments=True),
            GeometryTolerances(),
        )
        self.assertEqual(reordered_messages, [])
        self.assertEqual(len(reordered), 1)
        self.assertEqual(
            reordered[0].selected_rail_lines,
            candidates[0].selected_rail_lines,
        )
        self.assertEqual(reordered[0].source_width, candidates[0].source_width)

    def test_arbitrary_closed_outline_without_parallel_body_rails_is_rejected(self):
        group = _group_from_segments(
            (
                ((0.0, 0.0), (1000.0, 0.0)),
                ((-300.0, 300.0), (1300.0, 500.0)),
                ((-300.0, 300.0), (0.0, 0.0)),
                ((1000.0, 0.0), (1300.0, 500.0)),
            )
        )

        candidates, messages = _corner_brace_candidates_from_group(
            group,
            GeometryTolerances(),
        )

        self.assertEqual(candidates, [])
        self.assertEqual(
            [message.code for message in messages],
            ["CORNER_BRACE_BODY_UNRESOLVED"],
        )

    def test_disjoint_complete_candidates_are_all_created_regardless_of_order(self):
        segments = (
            ((0.0, 0.0), (1000.0, 0.0)),
            ((0.0, 300.0), (1000.0, 300.0)),
            ((0.0, 0.0), (0.0, 300.0)),
            ((1000.0, 0.0), (1000.0, 300.0)),
            ((0.0, 1000.0), (1000.0, 1000.0)),
            ((0.0, 1300.0), (1000.0, 1300.0)),
            ((0.0, 1000.0), (0.0, 1300.0)),
            ((1000.0, 1000.0), (1000.0, 1300.0)),
        )

        direct, direct_messages = _corner_brace_candidates_from_group(
            _group_from_segments(segments),
            GeometryTolerances(),
        )
        reversed_order, reversed_messages = (
            _corner_brace_candidates_from_group(
                _group_from_segments(tuple(reversed(segments))),
                GeometryTolerances(),
            )
        )

        self.assertEqual(direct_messages, [])
        self.assertEqual(reversed_messages, [])
        self.assertEqual(len(direct), 2)
        self.assertEqual(len(reversed_order), 2)
        self.assertEqual(
            {candidate.selected_rail_lines for candidate in direct},
            {candidate.selected_rail_lines for candidate in reversed_order},
        )

    def test_competing_complete_candidates_are_ambiguity_without_fallback(self):
        group = _group_from_segments(
            (
                ((0.0, 0.0), (1000.0, 0.0)),
                ((0.0, 300.0), (1000.0, 300.0)),
                ((0.0, 600.0), (1000.0, 600.0)),
                ((0.0, 0.0), (0.0, 300.0)),
                ((1000.0, 0.0), (1000.0, 300.0)),
                ((0.0, 300.0), (0.0, 600.0)),
                ((1000.0, 300.0), (1000.0, 600.0)),
                # This would support fallback if complete ambiguity were
                # incorrectly allowed to enter the second-stage path.
                ((150.0, 250.0), (150.0, 350.0)),
            )
        )

        candidates, messages = _corner_brace_candidates_from_group(
            group,
            GeometryTolerances(),
        )

        self.assertGreaterEqual(len(candidates), 2)
        self.assertTrue(
            all(
                candidate.corner_brace_body_resolution == "multiple"
                for candidate in candidates
            )
        )
        self.assertEqual(
            [message.code for message in messages],
            ["CORNER_BRACE_BODY_UNRESOLVED"],
        )
        self.assertIn("multiple_body_hypotheses", messages[0].message)


class CornerBraceOcclusionEvidenceTests(unittest.TestCase):
    def test_body_stage_does_not_apply_relationship_coverage_gate(self):
        boundary, boundary_messages = _corner_brace_candidates_from_group(
            _occluded_corner_group(250.0, occluder=((225.0, 250.0), (225.0, 350.0))),
            GeometryTolerances(),
        )
        below, below_messages = _corner_brace_candidates_from_group(
            _occluded_corner_group(250.001, occluder=((225.0, 250.0), (225.0, 350.0))),
            GeometryTolerances(),
        )

        self.assertEqual(len(boundary), 1)
        self.assertEqual(boundary_messages, [])
        self.assertEqual(boundary[0].corner_brace_candidate_kind, "body")
        self.assertEqual(len(below), 1)
        self.assertEqual(below_messages, [])

    def test_nearby_infinite_only_and_nonterminal_lines_are_not_evidence(self):
        cases = {
            "nearby": ((150.0, 340.0), (150.0, 440.0)),
            "infinite_only": ((150.0, 400.0), (150.0, 500.0)),
            "other_rail_position": ((800.0, 250.0), (800.0, 350.0)),
        }
        for name, occluder in cases.items():
            with self.subTest(name=name):
                candidates, messages = _corner_brace_candidates_from_group(
                    _occluded_corner_group(200.0, occluder=occluder),
                    GeometryTolerances(),
                )

                self.assertEqual(len(candidates), 1)
                self.assertEqual(messages, [])

    def test_external_recognized_brace_must_be_finite_at_terminal(self):
        group = _occluded_corner_group(200.0, occluder=None)

        accepted, _messages = _corner_brace_candidates_from_group(
            group,
            GeometryTolerances(),
            external_occluding_lines=(((150.0, 250.0), (150.0, 350.0)),),
        )
        rejected, rejected_messages = _corner_brace_candidates_from_group(
            group,
            GeometryTolerances(),
            external_occluding_lines=(((150.0, 400.0), (150.0, 500.0)),),
        )

        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected_messages, [])

    def test_zero_connection_plates_still_produces_body_evidence(self):
        group = _group_from_segments(
            (
                ((0.0, 0.0), (1000.0, 0.0)),
                ((200.0, 300.0), (1000.0, 300.0)),
                ((150.0, 250.0), (150.0, 350.0)),
            )
        )

        candidates, messages = _corner_brace_candidates_from_group(
            group,
            GeometryTolerances(),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(messages, [])
        self.assertEqual(
            candidates[0].corner_brace_body_evidence.terminal_plate_evidence,
            (),
        )

    def test_multiple_non_equivalent_fallbacks_remain_unresolved(self):
        first = _occluded_corner_group(y_offset=0.0)
        second = _occluded_corner_group(y_offset=1000.0)
        group = _group_from_segments(
            tuple(
                segment
                for source in (first, second)
                for primitive in source.primitives
                for segment in primitive.segments()
            )
        )
        candidates, candidate_messages = _corner_brace_candidates_from_group(
            group,
            GeometryTolerances(),
        )
        self.assertEqual(candidate_messages, [])
        self.assertEqual(len(candidates), 2)
        staged = {
            "waler": [
                _member_candidate(
                    (0.0, -100.0),
                    (0.0, 1500.0),
                    handle="W1",
                )
            ],
            "strut": [
                _member_candidate(
                    (1000.0, -100.0),
                    (1000.0, 1500.0),
                    handle="S1",
                )
            ],
            "corner_brace": candidates,
        }

        messages = _refine_corner_brace_axis_intersections(
            staged,
            GeometryTolerances(),
        )

        self.assertEqual(len(staged["corner_brace"]), 2)
        self.assertEqual(messages, [])


class CornerBraceFiniteRelationshipTests(unittest.TestCase):
    def _provisional(self):
        candidates, messages = _corner_brace_candidates_from_group(
            _occluded_corner_group(),
            GeometryTolerances(),
        )
        self.assertEqual(messages, [])
        self.assertEqual(len(candidates), 1)
        return candidates[0]

    def test_unique_finite_waler_and_strut_relationship_is_adopted(self):
        candidate = self._provisional()
        staged = {
            "waler": [_member_candidate((0.0, -100.0), (0.0, 500.0), handle="W1")],
            "strut": [_member_candidate((1000.0, -100.0), (1000.0, 500.0), handle="S1")],
            "corner_brace": [candidate],
        }

        messages = _refine_corner_brace_axis_intersections(
            staged,
            GeometryTolerances(),
        )

        self.assertEqual(messages, [])
        self.assertEqual(staged["corner_brace"], [candidate])
        self.assertEqual(candidate.recognition_method, "occluded_parallel_rails")
        self.assertEqual((candidate.start, candidate.end), ((0.0, 150.0), (1000.0, 150.0)))

    def test_missing_or_competing_finite_relationship_is_unresolved(self):
        for name, walers in (
            (
                "missing",
                [_member_candidate((-1000.0, -100.0), (-1000.0, 500.0), handle="W0")],
            ),
            (
                "competing",
                [
                    _member_candidate((0.0, -100.0), (0.0, 500.0), handle="W1"),
                    _member_candidate((-100.0, -100.0), (-100.0, 500.0), handle="W2"),
                ],
            ),
        ):
            with self.subTest(name=name):
                candidate = self._provisional()
                staged = {
                    "waler": walers,
                    "strut": [
                        _member_candidate(
                            (1000.0, -100.0),
                            (1000.0, 500.0),
                            handle="S1",
                        )
                    ],
                    "corner_brace": [candidate],
                }

                messages = _refine_corner_brace_axis_intersections(
                    staged,
                    GeometryTolerances(),
                )

                self.assertEqual(staged["corner_brace"], [])
                self.assertEqual(
                    [message.code for message in messages],
                    ["CORNER_BRACE_RELATIONSHIP_UNRESOLVED"],
                )
                self.assertEqual(messages[0].source_handles, ("H1",))

    def test_coincident_active_walers_remain_distinct_and_order_independent(self):
        outcomes = []
        for waler_handles in (("W7", "W8"), ("W8", "W7")):
            candidates, candidate_messages = _corner_brace_candidates_from_group(
                _mitered_corner_group(),
                GeometryTolerances(),
            )
            self.assertEqual(candidate_messages, [])
            candidate = candidates[0]
            staged = {
                "waler": [
                    _member_candidate(
                        (-150.0, -100.0),
                        (-150.0, 500.0),
                        handle=handle,
                    )
                    for handle in waler_handles
                ],
                "strut": [
                    _member_candidate(
                        (1150.0, -100.0),
                        (1150.0, 500.0),
                        handle="S2",
                    )
                ],
                "corner_brace": [candidate],
            }

            messages = _refine_corner_brace_axis_intersections(
                staged,
                GeometryTolerances(),
            )

            self.assertEqual(staged["corner_brace"], [])
            self.assertEqual(len(messages), 1)
            self.assertEqual(
                messages[0].code,
                "CORNER_BRACE_RELATIONSHIP_UNRESOLVED",
            )
            self.assertIn("hard_valid_count=2", messages[0].message)
            self.assertEqual(
                {
                    assessment.waler_source_handles
                    for assessment in candidate.corner_brace_relationship_assessments
                    if assessment.hard_valid
                },
                {("W7",), ("W8",)},
            )
            outcomes.append(messages[0].message)

        self.assertEqual(outcomes[0], outcomes[1])

    def test_single_active_waler_completes_mitered_connection(self):
        candidates, candidate_messages = _corner_brace_candidates_from_group(
            _mitered_corner_group(),
            GeometryTolerances(),
        )
        self.assertEqual(candidate_messages, [])
        candidate = candidates[0]
        staged = {
            "waler": [
                _member_candidate(
                    (-150.0, -100.0),
                    (-150.0, 500.0),
                    handle="W8",
                )
            ],
            "strut": [
                _member_candidate(
                    (1150.0, -100.0),
                    (1150.0, 500.0),
                    handle="S2",
                )
            ],
            "corner_brace": [candidate],
        }

        messages = _refine_corner_brace_axis_intersections(
            staged,
            GeometryTolerances(),
        )

        self.assertEqual(messages, [])
        self.assertEqual(staged["corner_brace"], [candidate])
        self.assertEqual(
            (candidate.start, candidate.end),
            ((-150.0, 150.0), (1150.0, 150.0)),
        )
        self.assertIn("waler_source_handles=W8", candidate.corner_brace_evidence)

    def test_each_recognized_component_role_can_supply_finite_gap_evidence(self):
        group = _group_from_segments(
            (
                ((0.0, 0.0), (400.0, 0.0)),
                ((600.0, 0.0), (1000.0, 0.0)),
                ((0.0, 300.0), (400.0, 300.0)),
                ((600.0, 300.0), (1000.0, 300.0)),
            )
        )
        for role in ("waler", "strut", "brace", "column", "beam"):
            with self.subTest(role=role):
                candidates, candidate_messages = (
                    _corner_brace_candidates_from_group(
                        group,
                        GeometryTolerances(),
                    )
                )
                self.assertEqual(candidate_messages, [])
                occluder = _member_candidate(
                    (500.0, 0.0),
                    (600.0, 0.0),
                    handle=f"O-{role}",
                )
                occluder.boundary_lines = (
                    ((500.0, 0.0), (600.0, 0.0)),
                    ((500.0, 300.0), (600.0, 300.0)),
                )
                staged = {
                    "waler": [
                        _member_candidate(
                            (0.0, -100.0),
                            (0.0, 500.0),
                            handle="W1",
                        )
                    ],
                    "strut": [
                        _member_candidate(
                            (1000.0, -100.0),
                            (1000.0, 500.0),
                            handle="S1",
                        )
                    ],
                    "corner_brace": candidates,
                }
                staged.setdefault(role, []).append(occluder)

                messages = _refine_corner_brace_axis_intersections(
                    staged,
                    GeometryTolerances(),
                )

                self.assertEqual(messages, [])
                self.assertEqual(len(staged["corner_brace"]), 1)
                assessment = staged["corner_brace"][
                    0
                ].corner_brace_relationship_assessments[0]
                self.assertTrue(assessment.hard_valid)
                self.assertEqual(assessment.classification, "occluded")


@unittest.skipUnless(Y05_DXF_PATH is not None, "Y05 DXF fixture unavailable")
class Y05CornerBraceOcclusionRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.importer = DXFImporter(Y05_DXF_PATH).read()
        cls.result = cls.importer.convert(
            layer_roles={
                layer: LAYER_USE_TO_ROLE[use]
                for layer, use in Y05_LAYER_MAPPING.items()
                if layer in cls.importer.layer_names
            }
        )

    def test_cb58_source_uses_outer_occluded_rails_and_true_width(self):
        members = [
            member
            for member in self.result.corner_braces
            if "F9E" in member.source_handles
        ]

        self.assertEqual(len(members), 1)
        member = members[0]
        self.assertEqual(member.recognition_method, "occluded_parallel_rails")
        self.assertAlmostEqual(member.source_width, 300.0, places=5)
        selected_rails = [
            line
            for line in member.line_candidates
            if line.source == "recognized_corner_brace_rail"
        ]
        self.assertEqual(len(selected_rails), 2)
        connections = [
            connection
            for connection in self.result.corner_brace_connections
            if connection.corner_brace_id == member.id
        ]
        self.assertEqual(len(connections), 1)
        self.assertEqual(
            (connections[0].waler_id, connections[0].strut_id),
            ("W2", "S2"),
        )
        self.assertTrue(member.candidate_points)
        self.assertGreaterEqual(len(self.result.corner_braces), 60)
        self.assertFalse(
            any(
                message.code == "CORNER_BRACE_RELATIONSHIP_UNRESOLVED"
                and "F9E" in message.source_handles
                for message in self.result.messages
            )
        )

    def test_cb58_endpoint_calibration_remains_stable(self):
        member = next(
            member
            for member in self.result.corner_braces
            if "F9E" in member.source_handles
        )

        self.assertAlmostEqual(member.start[0], -54969.5, places=3)
        self.assertAlmostEqual(member.start[1], 9450.0, places=3)
        self.assertAlmostEqual(member.end[0], -53469.5, places=3)
        self.assertAlmostEqual(member.end[1], 7950.0, places=3)

    def test_named_redesign_cases_preserve_body_and_relationship_outcomes(self):
        bodies = {
            body.source_handles[0]: body
            for body in self.result.corner_brace_body_evidence
            if len(body.source_handles) == 1
            and body.source_handles[0] in {"104C", "1081", "F9E", "FB7"}
        }
        self.assertEqual(set(bodies), {"104C", "1081", "F9E", "FB7"})
        members = {
            member.source_handles[0]: member
            for member in self.result.corner_braces
            if len(member.source_handles) == 1
            and member.source_handles[0] in bodies
        }
        self.assertEqual(set(members), {"1081", "F9E"})
        self.assertTrue(
            all(
                len(member.body_geometry_evidence.rail_tracks) == 2
                and member.relationship_assessment.hard_valid
                for member in members.values()
            )
        )
        assessments = {
            handle: tuple(
                assessment
                for assessment in self.result.corner_brace_relationship_assessments
                if assessment.body_signature == body.signature
            )
            for handle, body in bodies.items()
        }
        self.assertTrue(
            any(
                "rail_2_coverage_below_minimum"
                in assessment.rejection_reasons
                for assessment in assessments["104C"]
            )
        )
        self.assertTrue(
            any(
                "rail_2_coverage_below_minimum"
                in assessment.rejection_reasons
                for assessment in assessments["FB7"]
            )
        )

    def test_expected_slenderness_population_remains_valid(self):
        self.assertGreaterEqual(len(self.result.corner_braces), 60)
        self.assertTrue(
            all(
                member.relationship_assessment is not None
                and member.relationship_assessment.expected_slenderness_ratio >= 3.0
                for member in self.result.corner_braces
            )
        )


@unittest.skipUnless(Y1A_DXF_PATH.is_file(), "Y1A DXF fixture unavailable")
class Y1ACornerBraceRegressionTests(unittest.TestCase):
    def test_existing_corner_braces_keep_connections_and_true_width(self):
        importer = DXFImporter(Y1A_DXF_PATH).read()
        result = importer.convert(
            layer_roles={
                layer: LAYER_USE_TO_ROLE[use]
                for layer, use in Y1A_LAYER_MAPPING.items()
                if layer in importer.layer_names
            }
        )

        self.assertEqual(
            (
                len(result.corner_braces),
                len(result.walers),
                len(result.struts),
                len(result.braces),
                len(result.columns),
                len(result.beams),
            ),
            (52, 4, 15, 16, 30, 20),
        )
        self.assertEqual(
            {member.recognition_method for member in result.corner_braces},
            {"corner_brace_complete_tracks"},
        )
        self.assertTrue(
            all(abs(member.source_width - 300.0) < 0.01 for member in result.corner_braces)
        )
        self.assertFalse(
            any(
                message.code in {
                    "CORNER_BRACE_BODY_UNRESOLVED",
                    "CORNER_BRACE_RELATIONSHIP_UNRESOLVED",
                }
                for message in result.messages
            )
        )


@unittest.skipUnless(Y29_DXF_PATH.is_file(), "Y29 DXF fixture unavailable")
class Y29CornerBraceDuplicateWalerRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.importer = DXFImporter(Y29_DXF_PATH).read()
        cls.layer_roles = {
            layer: LAYER_USE_TO_ROLE[use]
            for layer, use in Y29_LAYER_MAPPING.items()
            if layer in cls.importer.layer_names
        }
        cls.both_active = cls.importer.convert(layer_roles=cls.layer_roles)
        cls.without_w7 = cls.importer.convert(
            layer_roles=cls.layer_roles,
            excluded_sources=(ExcludedSource("waler", ("25E",)),),
        )
        cls.without_w8 = cls.importer.convert(
            layer_roles=cls.layer_roles,
            excluded_sources=(ExcludedSource("waler", ("260",)),),
        )

    @staticmethod
    def _source_4c_members(result):
        return [
            member
            for member in result.corner_braces
            if "4C" in member.source_handles
        ]

    def test_both_active_walers_preserve_body_diagnostics_without_connection(self):
        self.assertEqual(
            (
                len(self.both_active.walers),
                len(self.both_active.struts),
                len(self.both_active.braces),
                len(self.both_active.columns),
                len(self.both_active.beams),
            ),
            (20, 40, 32, 68, 56),
        )
        self.assertEqual(self._source_4c_members(self.both_active), [])
        problems = [
            message
            for message in self.both_active.messages
            if message.code == "CORNER_BRACE_RELATIONSHIP_UNRESOLVED"
            and "4C" in message.source_handles
        ]

        self.assertEqual(len(problems), 1)
        self.assertIn("hard_valid_count=2", problems[0].message)
        review_items = [
            item
            for item in build_review_items(
                self.both_active,
                build_problem_records(self.both_active),
            )
            if item.role == "corner_brace" and "4C" in item.source_handles
        ]
        self.assertEqual(len(review_items), 1)
        self.assertEqual(review_items[0].status, "unresolved")
        self.assertTrue(
            any(
                problem.code == "CORNER_BRACE_RELATIONSHIP_UNRESOLVED"
                for problem in review_items[0].problems
            )
        )
        self.assertTrue(
            any(
                geometry.source_handle == "4C"
                for geometry in self.both_active.source_geometry
            )
        )
        repair_plan = plan_corner_brace_repair(
            self.both_active,
            review_items[0],
            base_revision=0,
            review_items=build_review_items(
                self.both_active,
                build_problem_records(self.both_active),
            ),
        )
        self.assertEqual(repair_plan.selection_mode, "body_relationship_selection")
        self.assertEqual(len(repair_plan.candidates), 2)
        self.assertEqual(
            {
                candidate.relationship_assessment.waler_source_handles
                for candidate in repair_plan.candidates
            },
            {("25E",), ("260",)},
        )
        self.assertFalse(self.both_active.can_import)

    def test_relationship_selection_apply_uses_only_selected_waler_identity(self):
        items = build_review_items(
            self.both_active,
            build_problem_records(self.both_active),
        )
        item = next(
            value
            for value in items
            if value.role == "corner_brace" and "4C" in value.source_handles
        )
        plan = plan_corner_brace_repair(
            self.both_active,
            item,
            base_revision=0,
            review_items=items,
        )
        original_count = len(self.both_active.corner_braces)
        for candidate in plan.candidates:
            with self.subTest(waler=candidate.target_waler_id):
                updated, member_id = apply_corner_brace_repair(
                    self.both_active,
                    item,
                    plan,
                    candidate.id,
                    explicit_adoption=True,
                )
                connections = tuple(
                    connection
                    for connection in updated.corner_brace_connections
                    if connection.corner_brace_id == member_id
                )
                self.assertEqual(len(connections), 1)
                self.assertEqual(
                    connections[0].waler_id,
                    candidate.target_waler_id,
                )
                created = next(
                    member
                    for member in updated.corner_braces
                    if member.id == member_id
                )
                self.assertEqual(
                    created.repair_provenance.selection_mode,
                    "body_relationship_selection",
                )
                self.assertEqual(
                    created.repair_provenance.body_signature,
                    candidate.body_signature,
                )
                self.assertEqual(
                    len(updated.corner_braces),
                    original_count + 1,
                )
        self.assertEqual(len(self.both_active.corner_braces), original_count)

    def test_relationship_selection_replays_only_the_saved_body_and_relationship(self):
        items = build_review_items(
            self.both_active,
            build_problem_records(self.both_active),
        )
        item = next(
            value
            for value in items
            if value.role == "corner_brace" and "4C" in value.source_handles
        )
        plan = plan_corner_brace_repair(
            self.both_active,
            item,
            base_revision=0,
            review_items=items,
        )
        selected = plan.candidates[0]
        updated, member_id = apply_corner_brace_repair(
            self.both_active,
            item,
            plan,
            selected.id,
            explicit_adoption=True,
        )
        overrides = capture_manual_overrides(updated)

        replayed, report = replay_manual_overrides(self.both_active, overrides)

        self.assertEqual(report.needs_review, ())
        self.assertEqual(report.disabled, ())
        self.assertTrue(report.preserved)
        replayed_member = next(
            value for value in replayed.corner_braces if value.id == member_id
        )
        assert replayed_member.repair_provenance is not None
        self.assertEqual(
            replayed_member.repair_provenance.selection_mode,
            "body_relationship_selection",
        )
        self.assertEqual(
            replayed_member.repair_provenance.body_signature,
            selected.body_signature,
        )
        self.assertEqual(
            replayed_member.repair_provenance.target_waler_identity,
            next(
                value.corner_brace_repair.target_waler_identity
                for value in overrides
                if value.corner_brace_repair is not None
            ),
        )

        changed_overrides = tuple(
            replace(
                value,
                corner_brace_repair=replace(
                    value.corner_brace_repair,
                    body_signature=f"{value.corner_brace_repair.body_signature}-CHANGED",
                ),
            )
            if value.corner_brace_repair is not None
            else value
            for value in overrides
        )
        rejected, rejected_report = replay_manual_overrides(
            self.both_active,
            changed_overrides,
        )
        self.assertEqual(rejected.corner_braces, self.both_active.corner_braces)
        self.assertTrue(rejected_report.needs_review)
        self.assertEqual(rejected_report.preserved, ())

    def test_expected_slenderness_population_remains_52_of_52(self):
        self.assertEqual(len(self.both_active.corner_braces), 52)
        self.assertTrue(
            all(
                member.relationship_assessment is not None
                and member.relationship_assessment.expected_slenderness_ratio >= 3.0
                for member in self.both_active.corner_braces
            )
        )

    def test_relationship_selection_rejects_tampered_preview_atomically(self):
        class _Importer:
            tolerances = GeometryTolerances()
            source_fingerprint = self.both_active.source_fingerprint
            layer_names = self.both_active.layer_names

        workflow = DXFReviewWorkflow(
            _Importer(),
            self.both_active.source_path,
            initial_world_result=self.both_active,
        )
        item = next(
            value
            for value in workflow.review_items
            if value.role == "corner_brace" and "4C" in value.source_handles
        )
        plan = workflow.plan_corner_brace_repair(item)
        selected = plan.candidates[0]
        tampered = replace(
            plan,
            candidates=(
                replace(
                    selected,
                    world_start=(selected.world_start[0] + 1.0, selected.world_start[1]),
                ),
                *plan.candidates[1:],
            ),
        )
        baseline = workflow.snapshot
        with self.assertRaisesRegex(Exception, "過期|符合資格"):
            workflow.commit_corner_brace_repair(tampered, selected.id)
        self.assertIs(workflow.world_result, baseline.world_result)
        self.assertIs(workflow.result, baseline.result)
        self.assertEqual(workflow.revision, baseline.revision)

    def test_excluding_w7_reruns_and_completes_against_w8(self):
        members = self._source_4c_members(self.without_w7)

        self.assertEqual(len(members), 1)
        self.assertAlmostEqual(members[0].source_width, 300.0, places=5)
        self.assertEqual(
            [
                waler.source_handles
                for waler in self.without_w7.walers
                if set(waler.source_handles).intersection({"25E", "260"})
            ],
            [("260",)],
        )
        connection = next(
            connection
            for connection in self.without_w7.corner_brace_connections
            if connection.corner_brace_id == members[0].id
        )
        connected_waler = next(
            waler
            for waler in self.without_w7.walers
            if waler.id == connection.waler_id
        )
        self.assertEqual(connected_waler.source_handles, ("260",))
        self.assertFalse(
            any("4C" in message.source_handles for message in self.without_w7.messages)
        )

    def test_excluding_w8_reruns_and_completes_against_w7(self):
        members = self._source_4c_members(self.without_w8)

        self.assertEqual(len(members), 1)
        self.assertAlmostEqual(members[0].source_width, 300.0, places=5)
        self.assertEqual(
            [
                waler.source_handles
                for waler in self.without_w8.walers
                if set(waler.source_handles).intersection({"25E", "260"})
            ],
            [("25E",)],
        )
        connection = next(
            connection
            for connection in self.without_w8.corner_brace_connections
            if connection.corner_brace_id == members[0].id
        )
        connected_waler = next(
            waler
            for waler in self.without_w8.walers
            if waler.id == connection.waler_id
        )
        self.assertEqual(connected_waler.source_handles, ("25E",))
        self.assertFalse(
            any("4C" in message.source_handles for message in self.without_w8.messages)
        )
        self.assertEqual(members[0].start, self._source_4c_members(self.without_w7)[0].start)
        self.assertEqual(members[0].end, self._source_4c_members(self.without_w7)[0].end)


class CornerBraceUnresolvedReviewIntegrationTests(unittest.TestCase):
    def test_unresolved_source_remains_locatable_and_blocks_completion(self):
        document = ezdxf.new("R2010")
        for layer in ("WALER", "STRUT", "CORNER"):
            document.layers.add(layer)
        model = document.modelspace()
        model.add_line(
            (0.0, -100.0),
            (0.0, 500.0),
            dxfattribs={"layer": "WALER"},
        )
        model.add_line(
            (1000.0, -100.0),
            (1000.0, 500.0),
            dxfattribs={"layer": "STRUT"},
        )
        block = document.blocks.new("INVALID_250_CORNER")
        block.add_line((0.0, 0.0), (1000.0, 0.0))
        block.add_line((0.0, 250.0), (1000.0, 250.0))
        block.add_line((0.0, 0.0), (0.0, 250.0))
        block.add_line((1000.0, 0.0), (1000.0, 250.0))
        source = model.add_blockref(
            "INVALID_250_CORNER",
            (0.0, 0.0),
            dxfattribs={"layer": "CORNER"},
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unresolved_corner.dxf"
            document.saveas(path)
            result = import_dxf(
                path,
                layer_roles={
                    "WALER": "waler",
                    "STRUT": "strut",
                    "CORNER": "corner_brace",
                },
            )

        source_handle = str(source.dxf.handle)
        unresolved = [
            item
            for item in build_review_items(
                result,
                build_problem_records(result),
            )
            if source_handle in item.source_handles
        ]

        self.assertTrue(result.walers)
        self.assertTrue(result.struts)
        self.assertEqual(result.corner_braces, ())
        self.assertFalse(result.can_import)
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0].status, "unresolved")
        self.assertEqual(unresolved[0].role, "corner_brace")
        self.assertTrue(
            any(
                problem.code == "CORNER_BRACE_BODY_UNRESOLVED"
                for problem in unresolved[0].problems
            )
        )
        self.assertTrue(
            any(
                geometry.source_handle == source_handle
                for geometry in result.source_geometry
            )
        )


if __name__ == "__main__":
    unittest.main()
